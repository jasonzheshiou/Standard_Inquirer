"""LLM-powered questionnaire generation engine.

Generates compliance questionnaires for Australian life insurance
organisations by retrieving relevant regulatory standards from ChromaDB
and using an LLM to produce structured JSON output.

Usage::

    from llm.question_generator import generate_questionnaire

    questionnaire = generate_questionnaire(
        user_input="We are a life insurer with reinsurance arrangements",
        organization_type="life_insurer",
    )

"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from engine.schemas import (
    Question,
    Questionnaire,
    QuestionSection,
)

from standards_ingestion.custom_loader import load_custom_standards
from llm.client import (
    LLMClient,
    LLMConnectionError,
    LLMGenerationError,
    LLMTimeoutError,
)
from standards_ingestion.embedder import (
    get_or_create_collection,
    init_chroma_client,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

MAX_STANDARDS = 3
MAX_RETRIES = 3
SOURCES_YAML_PATH = Path(__file__).resolve().parent.parent / "standards_ingestion" / "sources.yaml"

# ------------------------------------------------------------------
# Custom error class
# ------------------------------------------------------------------


class QuestionGenerationError(Exception):
    """Raised when questionnaire generation fails.

    Attributes:
        cause: The underlying exception, if any.
        message: Human-readable error description.
    """

    def __init__(self, message: str, cause: Exception | None = None) -> None:
        self.cause = cause
        if cause:
            message = f"{message}: {cause}"
        super().__init__(message)


# ------------------------------------------------------------------
# Standards source loader
# ------------------------------------------------------------------


def _load_sources() -> list[dict[str, Any]]:
    """Load and merge standards sources from sources.yaml and custom_standards.yaml.

    Built-in sources are loaded first, then custom sources are overlaid on top.
    If a custom source shares the same ``name`` as a built-in source, the custom
    source replaces the built-in one (custom takes precedence).

    Returns:
        List of source dicts with at least 'name', 'url', 'category'.
    """
    # Load built-in sources
    if SOURCES_YAML_PATH.exists():
        try:
            with open(SOURCES_YAML_PATH, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            built_in = data.get("sources", []) or []  # type: ignore[assignment]
        except Exception as exc:
            logger.warning("Failed to load sources.yaml: %s", exc)
            built_in = []
    else:
        built_in = []

    # Load custom sources
    custom = load_custom_standards()

    # Merge: custom overrides built-in on name conflict (built-in first, then custom)
    seen: dict[str, dict[str, Any]] = {}
    for src in built_in:
        name = src.get("name")
        if name is not None:
            seen[name] = src
    for src in custom:
        name = src.get("name")
        if name is not None:
            seen[name] = src

    return list(seen.values())


# ------------------------------------------------------------------
# ChromaDB helpers
# ------------------------------------------------------------------


def _check_chromadb_status() -> tuple[bool, int]:
    """Check whether the ChromaDB standards collection has documents.

    Returns:
        Tuple of (has_documents, document_count).
    """
    try:
        client = init_chroma_client()
        collection = get_or_create_collection(client)
        count = collection.count()
        return (count > 0, count)
    except Exception:
        return (False, 0)


# ------------------------------------------------------------------
# ChromaDB retrieval
# ------------------------------------------------------------------


def _retrieve_relevant_standards(
    user_input: str,
    organization_type: str,
    k: int = MAX_STANDARDS,
) -> list[dict[str, Any]]:
    """Query ChromaDB for relevant standard chunks.

    Filters results to only include standards applicable to the given
    organisation type, then returns the top-k most relevant chunks.

    Args:
        user_input: Free-text description of the organisation or request.
        organization_type: Organisation type (e.g. "life_insurer", "general_insurer").
        k: Maximum number of chunks to return (auto-limited to 10).

    Returns:
        List of dicts with keys: standard_name, standard_category,
        clause, document, source_url.
    """
    k = min(k, MAX_STANDARDS)

    # Check ChromaDB has documents before querying
    has_docs, doc_count = _check_chromadb_status()
    if not has_docs:
        logger.warning(
            "ChromaDB standards collection is empty (0 documents). "
            "Populate it via the Standards page before generating questionnaires. "
            "Without indexed standards, the LLM cannot reference regulatory text."
        )
        return []

    # Load all available standards for org-type filtering
    all_sources = _load_sources()
    applicable_categories: set[str] = set()

    # Map org types to relevant standard categories
    org_category_map: dict[str, list[str]] = {
        "life_insurer": ["APRA", "AASB", "IFRS"],
        "general_insurer": ["APRA", "AASB", "IFRS"],
        "health_insurer": ["APRA", "AASB", "IFRS"],
        "superannuation": ["APRA", "AASB", "IFRS"],
        "friendly_society": ["APRA", "AASB", "IFRS"],
        "reinsurer": ["APRA", "AASB", "IFRS"],
    }

    # Default to all categories for unknown types
    applicable_categories = set(org_category_map.get(organization_type.lower(), ["APRA", "AASB", "IFRS"]))

    # Filter sources by applicable categories
    applicable_sources: dict[str, str] = {}  # name -> category
    for source in all_sources:
        cat = source.get("category", "")
        if cat in applicable_categories:
            applicable_sources[source["name"]] = cat

    if not applicable_sources:
        return []

    try:
        client = init_chroma_client()
        collection = get_or_create_collection(client)

        # Query ChromaDB for relevant chunks
        query_text = f"{user_input} {organization_type}"
        results = collection.query(
            query_texts=[query_text],
            n_results=min(k * 3, 30),  # fetch extra for filtering
            include=["documents", "metadatas", "distances"],
        )

        chunks: list[dict[str, Any]] = []
        seen_standards: set[str] = set()

        docs_list = results.get("documents")
        metas_list = results.get("metadatas")
        dists_list = results.get("distances")

        if not docs_list or not metas_list or not dists_list:
            return []

        documents = docs_list[0] or []
        metadatas = metas_list[0] or []
        distances = dists_list[0] or []

        for doc_text, meta, dist in zip(documents, metadatas, distances):
            std_name = meta.get("standard_name", "")
            if not isinstance(std_name, str) or not std_name:
                continue
            if std_name not in applicable_sources:
                continue
            if std_name in seen_standards:
                continue
            seen_standards.add(std_name)

            # Ensure clause is a string before encoding
            clause_val = meta.get("clause", "")
            clause_str = str(clause_val) if not isinstance(clause_val, str) else clause_val
            clause_clean = clause_str.encode("ascii", "replace").decode("ascii")
            # Ensure document is a string before encoding
            doc_val = doc_text if isinstance(doc_text, str) else str(doc_text)
            doc_clean = doc_val.encode("utf-8", "replace").decode("utf-8")

            chunks.append(
                {
                    "standard_name": std_name,
                    "standard_category": applicable_sources[std_name],
                    "clause": clause_clean,
                    "document": doc_clean,
                    "source_url": meta.get("source_url", ""),
                    "distance": dist,
                }
            )

            if len(chunks) >= k:
                break

        logger.info("Retrieved %d relevant standard chunks for '%s'", len(chunks), organization_type)
        return chunks

    except Exception as exc:
        logger.warning("ChromaDB retrieval failed: %s", exc)
        # Return no chunks rather than failing entirely — LLM can still
        # generate a reasonable questionnaire from the user input alone.
        return []


# ------------------------------------------------------------------
# Prompt construction
# ------------------------------------------------------------------


def _build_prompt(
    user_input: str,
    organization_type: str,
    relevant_standards: list[dict[str, Any]],
) -> tuple[str, str]:
    """Construct system + user prompts for the LLM.

    Args:
        user_input: Free-text user input.
        organization_type: Organisation type.
        relevant_standards: ChromaDB retrieval results.

    Returns:
        Tuple of (system_prompt, user_prompt).
    """
    system_prompt = (
        "You are an Australian life insurance compliance expert. "
        "Your task is to generate a structured compliance questionnaire "
        "based on the user's organisation description and applicable "
        "regulatory standards.\n\n"
        "OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY valid JSON — no markdown, no explanation, no code fences.\n"
        "2. The JSON must match this schema exactly:\n"
        "   {\n"
        '     "sections": [...],\n'
        '     "generated_by": "llm",\n'
        '     "generated_at": "2026-01-01T00:00:00+00:00",\n'
        '     "organization_type": "life_insurer",\n'
        '     "user_input": "user description"\n'
        "   }\n"
        "3. Question ID format: {standard_code}_{clause}_{seq} "
        "(e.g., CPS230_27_01, LPS115_15_02). "
        "standard_code is the short form (CPS, LPS, AASB, etc.). "
        "clause is the clause number. seq is a zero-padded 2-digit sequence.\n"
        "4. Include source_standard, source_clause, and confidence for EACH question.\n"
        "5. Only include standards that apply to the organisation type.\n"
        "6. Generate at least 3 sections with at least 1 question each.\n"
        "7. Use type 'boolean' for yes/no questions, 'text' for open-ended, "
        "'multi_choice' for multiple-choice questions.\n"
        "8. For 'multi_choice' questions, you MUST include an 'options' field "
        "with a list of at least 2 string choices (e.g., ['Option A', 'Option B']).\n"
        "9. Confidence MUST reflect how directly the standard applies: "
        "1.0 = directly applicable, 0.8 = strongly applicable, "
        "0.6 = partially applicable, 0.4 = tangentially related, "
        "0.3 = tangential. Do NOT use 1.0 for all questions.\n"
        "10. Keep the questionnaire focused and practical — no more than 15 questions total.\n"
        "11. If the user mentions specific topics (e.g., reinsurance, risk management), "
        "prioritise those standards."
    )

    # Build standard context block
    standards_context = ""
    for i, std in enumerate(relevant_standards, 1):
        standards_context += (
            f"\n--- Standard {i}: {std['standard_name']} "
            f"[{std['standard_category']}] ---\n"
        )
        if std.get("clause"):
            standards_context += f"Clause: {std['clause']}\n"
        if std.get("source_url"):
            standards_context += f"URL: {std['source_url']}\n"
        # Truncate document to avoid overflowing the prompt
        doc = std.get("document", "")
        if len(doc) > 500:
            doc = doc[:500] + "... [truncated]"
        standards_context += f"Content:\n{doc}\n"

    standards_header = "--- Relevant Standards ---\n" if standards_context else ""
    user_prompt = (
        f"Organisation type: {organization_type}\n"
        f"User description: {user_input}\n\n"
        f"Below are relevant regulatory standards retrieved from the standards database.\n"
        f"Use them to generate a compliance questionnaire tailored to this organisation.\n\n"
        f"{standards_header}"
        f"{standards_context}"
        f"\nPlease generate the questionnaire JSON now."
    )

    return system_prompt, user_prompt


# ------------------------------------------------------------------
# JSON parsing & validation
# ------------------------------------------------------------------


def _parse_questionnaire(json_str: str) -> Questionnaire:
    """Validate JSON string against the Questionnaire schema.

    Args:
        json_str: Raw JSON string from the LLM response.

    Returns:
        A validated Questionnaire Pydantic model.

    Raises:
        QuestionGenerationError: If JSON is invalid or fails schema validation.
    """
    # Clean up potential markdown code fences
    cleaned = json_str.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # Remove first and last lines if they are code fence markers
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Strip any trailing text after the JSON (e.g., explanations)
    # Find the outermost balanced braces
    brace_count = 0
    json_end = -1
    for i, ch in enumerate(cleaned):
        if ch == "{":
            brace_count += 1
        elif ch == "}":
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1

    if json_end > 0:
        cleaned = cleaned[:json_end]

    # Attempt to parse JSON, with repair for common LLM JSON errors
    data = None
    parse_errors: list[str] = []

    # Try 1: Direct parse
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        parse_errors.append(str(exc))

    # Try 2: Fix common LLM JSON issues
    if data is None:
        repaired = cleaned
        # Remove control characters that break JSON (\x00-\x1f except \n, \r, \t which are valid)
        repaired = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', repaired)
        # Fix trailing commas before } or ]
        repaired = re.sub(r',(\s*[\]}])', r'\1', repaired)
        # Fix single quotes to double quotes (basic — only for JSON-like patterns)
        repaired = repaired.replace("'", '"')
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            parse_errors.append('repair attempt 1: ' + str(exc))

    # Try 3: More aggressive repair — find JSON object boundaries
    if data is None:
        repaired = cleaned
        # Strip everything before first { and after last }
        first_brace = repaired.find('{')
        last_brace = repaired.rfind('}')
        if first_brace > 0:
            repaired = repaired[first_brace:]
        if last_brace < len(repaired) - 1:
            repaired = repaired[:last_brace + 1]
        # Remove control characters again after trimming
        repaired = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', repaired)
        # Fix trailing commas
        repaired = re.sub(r',(\s*[\]}])', r'\1', repaired)
        # Fix single quotes
        repaired = repaired.replace("'", '"')
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            parse_errors.append('repair attempt 2: ' + str(exc))

    # Try 4: Try to extract JSON array if outer structure is an array
    if data is None:
        first_bracket = cleaned.find('[')
        last_bracket = cleaned.rfind(']')
        if first_bracket >= 0 and last_bracket > first_bracket:
            array_str = cleaned[first_bracket:last_bracket + 1]
            array_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', array_str)
            array_str = re.sub(r',(\s*[\]}])', r'\1', array_str)
            try:
                data = json.loads(array_str)
            except json.JSONDecodeError as exc:
                parse_errors.append('repair attempt 3 (array): ' + str(exc))

    # Try 5: Fix truncated/incomplete JSON — close open brackets and strings
    if data is None:
        repaired = cleaned
        # Strip everything before first { and after last }
        first_brace = repaired.find('{')
        last_brace = repaired.rfind('}')
        if first_brace > 0:
            repaired = repaired[first_brace:]
        if last_brace < len(repaired) - 1:
            repaired = repaired[:last_brace + 1]
        # Count open/close braces and brackets to find what's missing
        brace_stack = []
        in_string = False
        escape_next = False
        for ch in repaired:
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in '{[':
                brace_stack.append(ch)
            elif ch in '}]' and brace_stack:
                brace_stack.pop()
        # Close any remaining open brackets/braces
        while brace_stack:
            opener = brace_stack.pop()
            closer = '}' if opener == '{' else ']'
            repaired += closer
        # Fix unterminated strings at end: find last unclosed string and close it
        # Find all strings and check if the last one is closed
        string_pattern = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', repaired)
        # Count unmatched quotes (quotes not inside a string)
        temp = repaired
        temp = re.sub(r'"[^"\\]*(?:\\.[^"\\]*)*"', '""', temp)  # remove strings
        remaining_quotes = temp.count('"')
        if remaining_quotes % 2 == 1:
            # Odd number of quotes outside strings — one string is unterminated
            # Find the last partial string and close it
            last_partial = repaired.rfind('"')
            if last_partial > 0:
                repaired = repaired[:last_partial] + '"' + repaired[last_partial + 1:]
        # Remove control characters
        repaired = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', repaired)
        # Fix trailing commas
        repaired = re.sub(r',(\s*[\]}])', r'\1', repaired)
        # Fix single quotes
        repaired = repaired.replace("'", '"')
        try:
            data = json.loads(repaired)
        except json.JSONDecodeError as exc:
            parse_errors.append('repair attempt 4 (truncated): ' + str(exc))

    if data is None:
        raise QuestionGenerationError(
            "LLM returned invalid JSON (tried %d attempts)" % len(parse_errors),
            cause=json.JSONDecodeError("; ".join(parse_errors), cleaned, 0),
        )

    # Normalize field names — LLMs use inconsistent names
    if isinstance(data, dict):
        # Normalize section field names
        if "sections" in data and isinstance(data["sections"], list):
            for section in data["sections"]:
                if not isinstance(section, dict):
                    continue
                # section title: map section_title/section_name → title
                if "title" not in section:
                    for key in ("section_title", "section_name"):
                        if key in section:
                            section["title"] = section.pop(key)
                            break
                # Normalize question field names
                if "questions" in section and isinstance(section["questions"], list):
                    for question in section["questions"]:
                        if not isinstance(question, dict):
                            continue
                        # id: map question_id → id
                        if "id" not in question and "question_id" in question:
                            question["id"] = question.pop("question_id")
                        # text: map question_text/question → text
                        if "text" not in question:
                            for key in ("question_text", "question"):
                                if key in question:
                                    question["text"] = question.pop(key)
                                    break
                        # confidence: map confidence_score/conf → confidence
                        if "confidence" not in question:
                            for key in ("confidence_score", "conf"):
                                if key in question:
                                    question["confidence"] = question.pop(key)
                                    break
                        # source_clause: ensure it's a string (LLM may return int)
                        if "source_clause" in question and question["source_clause"] is not None:
                            question["source_clause"] = str(question["source_clause"])
                        # confidence: ensure it's a float (LLM may return string)
                        if "confidence" in question and question["confidence"] is not None:
                            try:
                                question["confidence"] = float(question["confidence"])
                            except (ValueError, TypeError):
                                question["confidence"] = 1.0
                        # options: map choices → options
                        if "options" not in question and "choices" in question:
                            question["options"] = question.pop("choices")

    # Validate against schema
    try:
        return Questionnaire.model_validate(data)
    except ValidationError as exc:
        raise QuestionGenerationError(
            f"LLM JSON failed schema validation: {exc}",
            cause=exc,
        ) from exc


# ------------------------------------------------------------------
# Default questionnaire (fallback)
# ------------------------------------------------------------------


def _default_questionnaire(organization_type: str, user_input: str | None = None) -> Questionnaire:
    """Return a default questionnaire when the LLM is unavailable.

    Provides baseline questions for common Australian life insurance
    regulatory standards (CPS 230, LPS 115, AASB 17).

    Args:
        organization_type: Organisation type for context.
        user_input: Original user input, stored for traceability.

    Returns:
        A Questionnaire instance built from the default template.
    """
    sections: list[QuestionSection] = [
        QuestionSection(
            title="Operational Risk Management (CPS 230)",
            questions=[
                Question(
                    id="CPS230_1_01",
                    text="Does the organisation have a documented operational risk management framework?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="CPS 230 — Operational Risk Management",
                    source_clause="Paragraph 1",
                    confidence=0.95,
                    applies_to_standard="CPS 230",
                ),
                Question(
                    id="CPS230_5_01",
                    text="Has the organisation identified and assessed its key operational risks?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="CPS 230 — Operational Risk Management",
                    source_clause="Paragraph 5",
                    confidence=0.90,
                    applies_to_standard="CPS 230",
                ),
                Question(
                    id="CPS230_12_01",
                    text="Does the organisation have incident reporting and escalation procedures in place?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="CPS 230 — Operational Risk Management",
                    source_clause="Paragraph 12",
                    confidence=0.85,
                    applies_to_standard="CPS 230",
                ),
            ],
        ),
        QuestionSection(
            title="Insurance Risk Charge (LPS 115)",
            questions=[
                Question(
                    id="LPS115_1_01",
                    text="Has the organisation calculated its insurance risk charge in accordance with LPS 115?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="LPS 115 — Capital Adequacy: Insurance Risk Charge",
                    source_clause="Paragraph 1",
                    confidence=0.95,
                    applies_to_standard="LPS 115",
                ),
                Question(
                    id="LPS115_15_01",
                    text="Does the organisation have adequate reinsurance arrangements to mitigate insurance risk?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="LPS 115 — Capital Adequacy: Insurance Risk Charge",
                    source_clause="Paragraph 15",
                    confidence=0.85,
                    applies_to_standard="LPS 115",
                ),
            ],
        ),
        QuestionSection(
            title="Insurance Contracts (AASB 17)",
            questions=[
                Question(
                    id="AASB17_1_01",
                    text="Has the organisation implemented AASB 17 insurance contract accounting?",
                    type="boolean",
                    default=False,
                    options=None,
                    source_standard="AASB 17 — Insurance Contracts",
                    source_clause="Paragraph 1",
                    confidence=0.95,
                    applies_to_standard="AASB 17",
                ),
                Question(
                    id="AASB17_30_01",
                    text="Does the organisation measure insurance contracts using the general measurement model (GMM)?",
                    type="multi_choice",
                    default=None,
                    options=["GMM", "Premium Allocation Approach (PAA)", "Variable Fee Approach (VFA)"],
                    source_standard="AASB 17 — Insurance Contracts",
                    source_clause="Paragraph 30",
                    confidence=0.90,
                    applies_to_standard="AASB 17",
                ),
            ],
        ),
    ]

    return Questionnaire(
        sections=sections,
        generated_by="fallback",
        generated_at=datetime.now(timezone.utc).isoformat(),
        organization_type=organization_type,
        user_input=user_input,
    )


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------


def generate_questionnaire(
    user_input: str,
    organization_type: str,
    llm_client: LLMClient | None = None,
) -> Questionnaire:
    """Generate a compliance questionnaire using LLM + ChromaDB retrieval.

    The function retrieves relevant regulatory standards from ChromaDB,
    constructs a prompt for the LLM, and parses the resulting JSON into
    a validated Questionnaire.

    On LLM failure (after retries) or unavailability, falls back to a
    default questionnaire covering common standards.

    Args:
        user_input: Free-text description of the organisation or request.
        organization_type: Organisation type (e.g. "life_insurer").
        llm_client: Optional LLMClient instance. When None, a default
            client is created using settings from llm.client.LLMSettings.

    Returns:
        A validated Questionnaire Pydantic model.

    Raises:
        QuestionGenerationError: If generation fails after all retries
            and the LLM is unavailable (should not happen — falls back).
    """
    # Determine LLM client
    client = llm_client or LLMClient()

    # Check ChromaDB status
    has_docs, doc_count = _check_chromadb_status()

    # Step 1: Retrieve relevant standards from ChromaDB
    relevant_standards = _retrieve_relevant_standards(user_input, organization_type, k=MAX_STANDARDS)

    # Step 2: Build prompts
    system_prompt, user_prompt = _build_prompt(user_input, organization_type, relevant_standards)

    # Step 3: Check LLM availability
    llm_available = client.is_available()
    if not llm_available:
        logger.warning("LLM unavailable — using default questionnaire")
        return _default_questionnaire(organization_type, user_input)

    # Step 4: Attempt LLM call with retry
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            raw_response = client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                # No response_format — LMStudio doesn't support it, and the LLM produces valid JSON anyway
            )
            logger.info("LLM response received (%d chars, attempt %d)", len(raw_response), attempt + 1)

            # Handle empty response — retry immediately
            if not raw_response or not raw_response.strip():
                logger.warning("LLM returned empty response on attempt %d/%d", attempt + 1, MAX_RETRIES + 1)
                if attempt < MAX_RETRIES:
                    logger.info("Retrying LLM call (attempt %d/%d)...", attempt + 2, MAX_RETRIES + 1)
                    continue
                else:
                    logger.warning("All attempts returned empty — using default questionnaire")
                    return _default_questionnaire(organization_type, user_input)

            # Parse and validate
            questionnaire = _parse_questionnaire(raw_response)
            logger.info(
                "Questionnaire generated: %d sections, %d questions",
                len(questionnaire.sections),
                sum(len(s.questions) for s in questionnaire.sections),
            )
            return questionnaire

        except (QuestionGenerationError, ValidationError) as exc:
            last_exc = exc
            logger.warning(
                "JSON validation failed on attempt %d/%d: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                exc,
            )
            if attempt < MAX_RETRIES:
                logger.info("Retrying LLM call (attempt %d/%d)...", attempt + 2, MAX_RETRIES + 1)
                continue

        except (LLMConnectionError, LLMTimeoutError, LLMGenerationError) as exc:
            logger.warning(
                "LLM error on attempt %d/%d: %s",
                attempt + 1,
                MAX_RETRIES + 1,
                exc,
            )
            if attempt < MAX_RETRIES:
                logger.info("Retrying LLM call (attempt %d/%d)...", attempt + 2, MAX_RETRIES + 1)
                continue

    # All retries exhausted — fall back to default
    logger.warning("All LLM attempts failed — using default questionnaire")
    return _default_questionnaire(organization_type, user_input)
