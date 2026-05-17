"""LLM-powered gap finding enrichment engine.

Provides ``enrich_findings()`` and ``generate_mitigation()`` to augment
deterministic gap findings with LLM-generated explanations and tailored
mitigation suggestions.

Key design decisions
--------------------
* **Batch processing** — findings are processed in batches of up to 5 to
  reduce LLM API calls.
* **Per-finding error isolation** — a failure for one finding never blocks
  others; the original finding is returned unchanged.
* **Caching by requirement_id** — identical findings are never re-processed.
* **Confidence-aware** — only findings whose associated Question has
  ``confidence > 0.7`` are enriched (configurable via *min_confidence*).
* **Fallback** — when the LLM is unavailable, findings are returned
  unchanged with a warning logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
from engine.schemas import GapFinding, Question

from llm.client import LLMClient, LLMGenerationError, LLMTimeoutError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = (
    "You are an Australian life insurance compliance expert. "
    "Your task is to explain gap findings in clear, actionable terms. "
    "Reference the specific regulatory requirement and suggest a "
    "tailored mitigation. Keep your explanation to 2–3 concise sentences."
)

_BATCH_SIZE: int = 5
_DEFAULT_MIN_CONFIDENCE: float = 0.7

# ---------------------------------------------------------------------------
# ChromaDB helper
# ---------------------------------------------------------------------------


def _retrieve_relevant_standard_text(
    requirement_id: str,
    clause_reference: str,
    question_text: str,
    evidence_text: str,
) -> str:
    """Retrieve relevant standard text from ChromaDB for a single finding.

    Falls back to *evidence_text* (already populated by
    ``gap_analyzer.get_evidence_text``) and then to the raw clause
    reference when ChromaDB is unavailable.

    Args:
        requirement_id: The rule/requirement identifier.
        clause_reference: Specific clause reference from the standard.
        question_text: The questionnaire question related to this finding.
        evidence_text: Already-retrieved ChromaDB evidence (may be empty).

    Returns:
        A text snippet containing the most relevant standard text.
    """
    # Re-use existing evidence_text if ChromaDB was already queried
    if evidence_text:
        return evidence_text

    # Try ChromaDB retrieval via gap_analyzer's get_evidence_text
    # which already handles the embedding + query logic.
    try:
        from engine.gap_analyzer import get_evidence_text

        # Build a concise search query from the finding context
        search_query = f"{requirement_id}: {clause_reference}. {question_text}"
        result = get_evidence_text(search_query)
        if result:
            return result
    except Exception:  # pragma: no cover
        pass

    # Last resort: return the clause reference so the LLM at least has
    # something to work with.
    return f"Clause reference: {clause_reference}"


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


def _make_cache_key(requirement_id: str, standard_text: str) -> str:
    """Deterministic cache key for a LLM enrichment request.

    Combines *requirement_id* and a truncated hash of *standard_text*
    so that findings with different retrieved standard text are cached
    independently.
    """
    text_hash = hashlib.sha256(standard_text.encode()).hexdigest()[:16]
    return f"{requirement_id}:{text_hash}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enrich_findings(
    findings: list[GapFinding],
    llm_client: LLMClient | None = None,
    cache: dict[str, str] | None = None,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> list[GapFinding]:
    """Enrich a list of gap findings with LLM-generated explanations.

    For each finding whose associated Question has confidence above
    *min_confidence*, the function:

    1. Retrieves relevant standard text from ChromaDB.
    2. Constructs a prompt referencing the specific requirement.
    3. Calls the LLM to generate a 2–3 sentence explanation.
    4. Caches the result by *requirement_id*.
    5. Attaches the explanation as ``finding.llm_explanation``.

    **Batch processing:** findings are processed in batches of up to 5
    to reduce the number of LLM API calls.

    **Error isolation:** a failure for one finding does not block others.
    The original finding is returned unchanged and a warning is logged.

    **Fallback:** when no ``llm_client`` is provided or the LLM is
    unavailable, findings are returned unchanged with a warning logged.

    Args:
        findings: List of :class:`GapFinding` objects to enrich.
        llm_client: Optional LLMClient instance.  When ``None``, a
            singleton is created automatically.
        cache: Optional dict for caching LLM responses keyed by
            ``requirement_id``.
        min_confidence: Minimum confidence threshold.  Only findings
            whose associated Question has confidence >= this value
            will be enriched.  Set to ``0.0`` to disable.

    Returns:
        The same list of :class:`GapFinding` objects (mutated in-place).
    """
    if not findings:
        return findings

    # --- health check / fallback ----------------------------------------
    if llm_client is None:
        llm_client = LLMClient()

    if not llm_client.is_available():
        logger.warning(
            "LLM server is unavailable — returning %d findings without enrichment.",
            len(findings),
        )
        return findings

    cache = cache or {}

    # --- resolve confidence for each finding ----------------------------
    # The GapFinding model itself does not carry a confidence score.
    # We look up the associated Question to determine if enrichment is
    # warranted.
    try:
        from engine.questionnaire import get_all_questions

        question_map: dict[str, Question] = {q.id: q for q in get_all_questions()}
    except Exception:  # pragma: no cover
        question_map = {}

    # --- batch enrichment -----------------------------------------------
    enriched_count = 0
    skipped_count = 0

    for i in range(0, len(findings), _BATCH_SIZE):
        batch = findings[i : i + _BATCH_SIZE]
        for finding in batch:
            # Confidence gate
            question = question_map.get(finding.requirement_id)
            if question and (question.confidence is None or question.confidence < min_confidence):
                skipped_count += 1
                continue

            # Skip if already enriched
            if finding.llm_explanation:
                enriched_count += 1
                continue

            # Retrieve standard text
            standard_text = _retrieve_relevant_standard_text(
                requirement_id=finding.requirement_id,
                clause_reference=finding.clause_reference,
                question_text=finding.question,
                evidence_text=finding.evidence_text,
            )

            # Check cache
            cache_key = _make_cache_key(finding.requirement_id, standard_text)
            if cache_key in cache:
                finding.llm_explanation = cache[cache_key]
                enriched_count += 1
                logger.debug("Cache hit for %s", cache_key)
                continue

            # Build prompt
            prompt = (
                f"Gap Finding for {finding.clause_reference}:\n"
                f"  Requirement: {finding.requirement_id}\n"
                f"  Question: {finding.question}\n"
                f"  User Answer: {finding.user_answer}\n"
                f"  Severity: {finding.gap_severity}\n"
                f"\nRelevant Standard Text:\n{standard_text}\n"
                f"\nProvide a 2–3 sentence explanation referencing the "
                f"specific requirement and suggesting tailored mitigation."
            )

            # Call LLM
            try:
                explanation = llm_client.generate(
                    prompt=prompt,
                    system_prompt=_SYSTEM_PROMPT,
                )
            except (LLMGenerationError, LLMTimeoutError) as exc:
                logger.warning(
                    "LLM generation failed for %s: %s",
                    finding.requirement_id,
                    exc,
                )
                continue
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Unexpected LLM error for %s: %s",
                    finding.requirement_id,
                    exc,
                )
                continue

            # Attach and cache
            finding.llm_explanation = explanation
            cache[cache_key] = explanation
            enriched_count += 1
            logger.info("Enriched %s (%d chars)", finding.requirement_id, len(explanation))

    logger.info(
        "Enrichment complete: %d enriched, %d skipped (confidence), %d total",
        enriched_count,
        skipped_count,
        len(findings),
    )
    return findings


def generate_mitigation(
    findings: list[GapFinding],
    llm_client: LLMClient | None = None,
    min_confidence: float = _DEFAULT_MIN_CONFIDENCE,
) -> dict[str, str]:
    """Generate tailored mitigation strategies for a batch of findings.

    Unlike ``enrich_findings()`` which annotates individual findings,
    this function produces a single dict mapping ``requirement_id`` →
    a detailed mitigation plan (3–5 sentences).

    **Batch processing:** all findings are sent in a single LLM call
    to reduce latency and cost.

    **Error isolation:** if the LLM call fails, an empty dict is
    returned and a warning is logged.

    Args:
        findings: List of :class:`GapFinding` objects.
        llm_client: Optional LLMClient instance.
        min_confidence: Minimum confidence threshold.

    Returns:
        A dict mapping ``requirement_id`` to a mitigation suggestion.
    """
    if not findings:
        return {}

    if llm_client is None:
        llm_client = LLMClient()

    if not llm_client.is_available():
        logger.warning(
            "LLM server is unavailable — returning empty mitigation dict.",
        )
        return {}

    # Confidence gate
    try:
        from engine.questionnaire import get_all_questions

        question_map: dict[str, Question] = {q.id: q for q in get_all_questions()}
    except Exception:  # pragma: no cover
        question_map = {}

    # Filter to findings that pass confidence gate
    eligible: list[GapFinding] = []
    for f in findings:
        question = question_map.get(f.requirement_id)
        if question is None:
            # No associated question → include by default
            eligible.append(f)
            continue
        conf = question.confidence
        if conf is None or conf >= min_confidence:
            eligible.append(f)

    if not eligible:
        logger.info("No findings pass confidence gate for mitigation generation.")
        return {}

    # Build a consolidated prompt
    mitigation_prompt_lines: list[str] = []
    for f in eligible:
        mitigation_prompt_lines.append(
            f"- **{f.clause_reference}** ({f.requirement_id}): "
            f"{f.question}\n"
            f"  Answer: {f.user_answer} | Severity: {f.gap_severity}\n"
            f"  Existing mitigation: {f.mitigation}"
        )

    mitigation_prompt = (
        "You are an Australian life insurance compliance expert. "
        "For each of the following gap findings, provide a tailored "
        "mitigation plan (3–5 sentences) that includes specific steps "
        "the organisation should take.\n\n"
        "Return your response as a JSON object where keys are "
        "requirement IDs and values are the mitigation text.\n\n"
        "Findings:\n"
        + "\n".join(mitigation_prompt_lines)
    )

    try:
        result = llm_client.generate_json(
            prompt=mitigation_prompt,
            system_prompt=_SYSTEM_PROMPT,
        )
        # The LLM may return a single string or a dict — normalise
        if isinstance(result, dict):
            return result
        # If it returned a JSON string, parse it
        if isinstance(result, str):
            return json.loads(result)
    except (LLMGenerationError, LLMTimeoutError) as exc:
        logger.warning("LLM mitigation generation failed: %s", exc)
    except json.JSONDecodeError as exc:  # pragma: no cover
        logger.warning("LLM returned invalid JSON for mitigation: %s", exc)
    except Exception as exc:  # pragma: no cover
        logger.warning("Unexpected error during mitigation generation: %s", exc)

    return {}
