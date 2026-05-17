"""Gap-analysis engine for the Compliance Gap Analyser.

Evaluates user questionnaire answers against CPS 230 gap rules and
produces severity-ranked findings.  The core ``analyze()`` function
is fully importable and testable without a running Streamlit instance.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import settings
from engine.questionnaire import get_all_questions
from engine.schemas import GapFinding, GapRule, Question, Questionnaire

logger = logging.getLogger(__name__)

try:
    import streamlit as st

    _cache_resource = st.cache_resource  # type: ignore[has-type]
except ImportError:  # pragma: no cover

    def _cache_resource(func: Any) -> Any:
        """No-op decorator when Streamlit is not installed."""
        return func


class GapAnalysisError(Exception):
    """Raised when gap analysis cannot be performed."""


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


def _severity_key(finding: GapFinding) -> int:
    """Return sort key for a finding's severity (ascending)."""
    return _SEVERITY_ORDER.get(finding.gap_severity.lower(), 99)


# ---------------------------------------------------------------------------
# Rule loading
# ---------------------------------------------------------------------------


@_cache_resource
def _load_raw_rules(path: str) -> list[GapRule]:
    """Load and validate gap rules from JSON.

    The JSON file is expected to contain an object with a ``requirements``
    key holding a list of rule objects.  This structure matches the
    ``gap_rules.json`` shipped with the project.

    Args:
        path: Path to the gap-rules JSON file.

    Returns:
        List of validated :class:`GapRule` objects.

    Raises:
        GapAnalysisError: If the file cannot be read or validated.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise GapAnalysisError(f"Gap rules file not found: {path}")

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GapAnalysisError(f"Cannot read gap rules file: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise GapAnalysisError(f"Invalid JSON in gap rules file: {exc}") from exc

    # Support both bare list and wrapper-object formats
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("requirements", [])
    else:
        raise GapAnalysisError(
            f"Unexpected JSON structure in gap rules file: expected list or object, got {type(data).__name__}"
        )

    rules: list[GapRule] = []
    for item in items:
        try:
            rules.append(GapRule.model_validate(item))
        except Exception as exc:
            raise GapAnalysisError(f"Rule validation failed: {exc}") from exc

    return rules


def load_gap_rules(path: str | None = None) -> list[GapRule]:
    """Load and validate gap rules.

    Args:
        path: Optional override path.  Defaults to
            ``settings.gap_rules_path``.

    Returns:
        List of validated :class:`GapRule` objects.

    Raises:
        GapAnalysisError: If loading or validation fails.
    """
    target = path or settings.gap_rules_path
    return _load_raw_rules(target)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------


def evaluate_rule(rule: GapRule, answers: dict[str, Any]) -> bool:
    """Evaluate a single gap rule against user answers.

    The function retrieves the user's answer for the question referenced
    by ``rule.gap_condition`` and checks whether the condition is met.
    A ``True`` return means a gap **exists** (the rule is triggered).

    Supported logic operators:

    * ``equals`` — user answer must equal ``rule.gap_condition.value``
    * ``contains_noncompliance`` — user answer indicates non-compliance
      (empty string, "no", "n/a", "not addressed", etc.)

    Args:
        rule: The gap rule to evaluate.
        answers: Mapping of question ID to user answer value.

    Returns:
        ``True`` if the gap condition is triggered, ``False`` otherwise.
    """
    condition = rule.gap_condition
    question_id: str = condition.get("question_id", "")
    logic: str = condition.get("logic", "equals")

    user_answer = answers.get(question_id)

    # If the question was not answered, do not trigger a gap
    if user_answer is None:
        return False

    if logic == "equals":
        expected = condition.get("value")
        return str(user_answer) == str(expected)

    if logic == "contains_noncompliance":
        return _is_noncompliant(str(user_answer))

    # Future: add more logic operators (regex, threshold, etc.)
    return False


# Non-compliance indicators for free-text answer evaluation.
_NONCOMPLIANCE_PATTERNS: list[str] = [
    "",
    "no",
    "n/a",
    "na",
    "not addressed",
    "not applicable",
    "not documented",
    "not established",
    "not in place",
    "not yet",
    "none",
    "none",
    "no documentation",
    "no process",
    "no framework",
    "no inventory",
    "no validation",
    "no answer",
]


def _is_noncompliant(answer: str) -> bool:
    """Check if a free-text answer indicates non-compliance.

    An answer is considered non-compliant if it is empty or matches
    any of the known non-compliance indicators (case-insensitive).

    Args:
        answer: The user's free-text answer.

    Returns:
        ``True`` if the answer indicates a compliance gap, ``False`` otherwise.
    """
    normalized = answer.strip().lower()
    for pattern in _NONCOMPLIANCE_PATTERNS:
        if normalized == pattern.lower():
            return True
    # Also check if answer starts with "no" (e.g. "no, we don't have that")
    if normalized.startswith("no") and (len(normalized) == 2 or normalized[2] in (" ", ".", ",", "!")):
        return True
    return False


# ---------------------------------------------------------------------------
# Evidence retrieval (ChromaDB)
# ---------------------------------------------------------------------------


def get_evidence_text(
    requirement_description: str,
    collection: Any = None,
    k: int = 1,
) -> str:
    """Retrieve evidence text via ChromaDB similarity search.

    Generates an embedding for *requirement_description* and queries the
    provided ChromaDB collection for the most similar documents.

    If *collection* is ``None`` or ChromaDB is unavailable, returns an
    empty string.

    Args:
        requirement_description: Text to search for (the rule description).
        collection: A ChromaDB collection instance.  If ``None``, no
            search is performed.
        k: Number of top results to retrieve.

    Returns:
        Text of the top matching document, or ``""`` if unavailable.

    Note:
        LLM-based evidence generation is a future enhancement — this
        function currently relies on ChromaDB vector similarity only.
    """
    if collection is None:
        return ""

    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.embedding_model_name)
        embedding = model.encode(requirement_description).tolist()

        results = collection.query(
            query_embeddings=[embedding],
            n_results=k,
        )

        # ChromaDB returns dicts with 'documents' key
        documents = results.get("documents", [])
        if documents and documents[0]:
            return documents[0][0]
    except Exception:  # pragma: no cover
        # Gracefully degrade when ChromaDB or embedding model is missing
        pass

    return ""


# ---------------------------------------------------------------------------
# Dynamic rule generation from questionnaire metadata
# ---------------------------------------------------------------------------

# Severity classification for dynamic rule generation.
# High: Governance / capital standards — critical compliance gaps.
# Medium: Documentation / reporting standards — material gaps.
# Low: Operational / procedural standards — lower-impact gaps.
_HIGH_SEVERITY_PATTERNS: list[str] = [
    "CPS 320",
    "LPS 100",
    "LPS 101",
    "LPS 102",
    "LPS 103",
    "LPS 104",
    "LPS 105",
    "LPS 106",
    "LPS 107",
    "LPS 108",
    "LPS 109",
    "LPS 110",
    "LPS 111",
    "LPS 112",
    "LPS 113",
    "LPS 114",
    "LPS 115",
    "LPS 116",
    "LPS 117",
    "LPS 118",
    "LPS 230",
    "LPS 340",
    "APS 201",
    "APS 202",
]

_MEDIUM_SEVERITY_PATTERNS: list[str] = [
    "CPS 230",
    "CPS 220",
    "CPS 510",
    "AASB 17",
    "IFRS 17",
    "PG ",
]

_LOW_SEVERITY_PATTERNS: list[str] = [
    "CPS 001",
    "CPS 190",
    "CPS 234",
    "CPG ",
    "LRS ",
]


def _classify_severity(standard_name: str) -> str:
    """Classify a standard name into a severity level.

    Checks patterns in priority order: high → medium → low.
    Falls back to ``"medium"`` when no pattern matches.

    Uses word-boundary matching to avoid false positives
    (e.g. ``"PG"`` must not match ``"CPG guidelines"``).

    Args:
        standard_name: Standard name (e.g. ``"CPS 230"``, ``"LPS 115"``, ``"AASB 17"``).

    Returns:
        One of ``"high"``, ``"medium"``, ``"low"``.
    """
    import re

    for pattern in _HIGH_SEVERITY_PATTERNS:
        token = pattern.rstrip()
        if re.search(r"\b" + re.escape(token) + r"\b", standard_name):
            return "high"
    for pattern in _MEDIUM_SEVERITY_PATTERNS:
        token = pattern.rstrip()
        if re.search(r"\b" + re.escape(token) + r"\b", standard_name):
            return "medium"
    for pattern in _LOW_SEVERITY_PATTERNS:
        token = pattern.rstrip()
        if re.search(r"\b" + re.escape(token) + r"\b", standard_name):
            return "low"
    return "medium"  # default


def get_dynamic_rules(questionnaire: Questionnaire) -> list[GapRule]:
    """Generate ``GapRule`` objects from a questionnaire's metadata.

    Iterates every question across all sections.  For questions that carry
    ``source_standard`` and ``source_clause`` metadata, a ``GapRule`` is
    synthesised with:

    * ``id`` — derived from ``source_standard`` + ``source_clause``
    * ``standard`` — the ``source_standard`` value
    * ``clause`` — the ``source_clause`` value
    * ``description`` — the question text
    * ``severity_if_gap`` — classified via :func:`_classify_severity`
    * ``gap_condition`` — a simple ``{"question_id": <question.id>, "logic": "equals", "value": "no"}``
      so that a ``"no"`` answer triggers the gap.

    Questions **without** ``source_standard`` / ``source_clause`` are
    silently skipped (they will be handled by ChromaDB fallback).

    Args:
        questionnaire: A validated :class:`Questionnaire` instance.

    Returns:
        List of dynamically generated :class:`GapRule` objects.
    """
    rules: list[GapRule] = []
    seen_ids: set[str] = set()

    for section in questionnaire.sections:
        for question in section.questions:
            std = question.source_standard
            clause = question.source_clause

            # Skip questions without explicit standard metadata
            if not std or not clause:
                continue

            # Deduplicate: multiple questions may reference the same clause
            rule_id = f"{std}::{clause}"
            if rule_id in seen_ids:
                continue
            seen_ids.add(rule_id)

            severity = _classify_severity(std)

            rule = GapRule(
                id=rule_id,
                standard=std,
                clause=clause,
                description=question.text,
                category=std,
                gap_condition={
                    "question_id": question.id,
                    "logic": "contains_noncompliance",
                    "value": "",
                },
                severity_if_gap=severity,
                mitigation=f"Review compliance with {std} clause {clause}. Consult actuarial professional standards.",
                reference_url="",
            )
            rules.append(rule)

    return rules


def map_questions_to_rules(
    questions: list[Question],
    gap_rules: list[GapRule],
) -> dict[str, str]:
    """Map question IDs to rule IDs by matching source metadata.

    Primary matching: ``source_standard`` + ``source_clause`` on each
    question is compared against the ``standard`` + ``clause`` on each
    rule.

    Fallback: for questions that have ``source_standard`` but no explicit
    rule match, a ChromaDB similarity search is attempted against the
    rule descriptions to find the best-matching rule.

    Args:
        questions: List of :class:`Question` objects.
        gap_rules: List of :class:`GapRule` objects (static or dynamic).

    Returns:
        Dictionary mapping ``question_id`` → ``rule_id``.
    """
    mapping: dict[str, str] = {}

    # --- Primary: exact metadata match ---
    for question in questions:
        if question.source_standard and question.source_clause:
            rule_id = f"{question.source_standard}::{question.source_clause}"
            mapping[question.id] = rule_id
            continue

        # --- Fallback: ChromaDB similarity search ---
        if question.source_standard and question.text:
            matched_rule = _find_rule_by_similarity(question, gap_rules)
            if matched_rule:
                mapping[question.id] = matched_rule.id

    return mapping


def _find_rule_by_similarity(
    question: Question,
    gap_rules: list[GapRule],
) -> GapRule | None:
    """Find the best-matching rule for a question via ChromaDB or heuristic.

    If ChromaDB is unavailable, falls back to keyword overlap scoring
    between the question text and rule descriptions.

    Args:
        question: The question to match.
        gap_rules: Candidate rules.

    Returns:
        The best-matching :class:`GapRule`, or ``None``.
    """
    # Try ChromaDB first
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(settings.embedding_model_name)
        q_embedding = model.encode(question.text).tolist()

        # Import ChromaDB collection
        import chromadb

        client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        collection = client.get_collection("standards_collection")

        results = collection.query(
            query_embeddings=[q_embedding],
            n_results=min(5, len(gap_rules)),
        )
        documents = results.get("documents") or []
        distances = results.get("distances") or []

        if documents and documents[0]:
            best_idx = 0
            best_dist = distances[0][0] if distances else float("inf")
            for i, dist in enumerate(distances[0]):
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
            if best_dist < 1.5:  # similarity threshold
                return gap_rules[best_idx]
    except Exception:
        pass

    # Fallback: keyword overlap scoring
    return _keyword_match(question, gap_rules)


def _keyword_match(
    question: Question,
    gap_rules: list[GapRule],
) -> GapRule | None:
    """Simple keyword-overlap scoring as ChromaDB fallback.

    Counts shared bigrams between the question text and each rule
    description.  Returns the rule with the highest overlap score.

    Args:
        question: The question to match.
        gap_rules: Candidate rules.

    Returns:
        The best-matching :class:`GapRule`, or ``None``.
    """
    import re

    q_terms = set(re.findall(r"\w+", question.text.lower()))
    best_rule: GapRule | None = None
    best_score = 0

    for rule in gap_rules:
        r_terms = set(re.findall(r"\w+", rule.description.lower()))
        score = len(q_terms & r_terms)
        if score > best_score:
            best_score = score
            best_rule = rule

    return best_rule


# ---------------------------------------------------------------------------
# LLM-powered gap analysis
# ---------------------------------------------------------------------------

_LLM_GAP_SYSTEM_PROMPT: str = (
    "You are an Australian life insurance compliance expert. "
    "Your task is to analyze questionnaire answers and determine compliance gaps. "
    "For each question-answer pair, evaluate whether there is a compliance gap "
    "based on the referenced standard and clause.\n\n"
    "OUTPUT REQUIREMENTS:\n"
    "1. Return ONLY valid JSON — no markdown, no explanation, no code fences.\n"
    "2. The JSON must match this schema exactly:\n"
    "   {\n"
    '     "findings": [\n'
    '       {\n'
    '         "question_id": "CPS230_1_01",\n'
    '         "has_gap": true,\n'
    '         "gap_severity": "high",\n'
    '         "requirement_id": "CPS 230::1",\n'
    '         "clause_reference": "1",\n'
    '         "question": "Question text here",\n'
    '         "user_answer": "No",\n'
    '         "mitigation": "Suggested mitigation text",\n'
    '         "evidence_text": "",\n'
    '         "explanation": "Detailed explanation of why this gap exists and its implications"\n'
    "       }\n"
    "     ]\n"
    "   }\n"
    "3. Only include findings where has_gap is true (gap exists).\n"
    "4. severity must be one of: \"high\", \"medium\", \"low\".\n"
    "5. If the answer indicates non-compliance, partial compliance, or risk — has_gap should be true.\n"
    "6. If the answer indicates full compliance with no risk — has_gap should be false (omit from findings).\n"
    "7. Be strict: gaps in governance, capital, actuarial matters are typically \"high\" severity.\n"
    "8. Documentation/reporting gaps are typically \"medium\" severity.\n"
    "9. Operational/procedural gaps are typically \"low\" severity.\n"
    "10. ALWAYS include a detailed \"explanation\" field describing why the gap exists and its implications."
)


def analyze_gaps_with_llm(
    questionnaire: Questionnaire,
    answers: dict[str, Any],
    llm_client: Any = None,
) -> list[GapFinding]:
    """Use the LLM to analyze questionnaire answers and determine compliance gaps.

    Sends the questionnaire structure, all answers, and standard metadata to the LLM.
    The LLM evaluates each question-answer pair against the referenced standard
    and returns structured GapFinding objects.

    Args:
        questionnaire: A validated :class:`Questionnaire` instance.
        answers: Mapping of question ID to user answer value.
        llm_client: Optional LLMClient instance. When ``None``, a default is created.

    Returns:
        List of :class:`GapFinding` objects sorted by severity.
    """
    from llm.client import LLMClient

    if llm_client is None:
        llm_client = LLMClient()

    # Check LLM availability
    if not llm_client.is_available():
        logger.warning("LLM unavailable for gap analysis — falling back to deterministic rules")
        return []

    # Build a compact representation of questionnaire + answers for the LLM
    questions_data: list[dict[str, Any]] = []
    for section in questionnaire.sections:
        for question in section.questions:
            answer_val = answers.get(question.id, "")
            questions_data.append({
                "id": question.id,
                "text": question.text,
                "type": question.type,
                "source_standard": question.source_standard or "",
                "source_clause": question.source_clause or "",
                "answer": str(answer_val) if answer_val is not None else "",
            })

    # Build the LLM prompt
    llm_prompt = (
        "You are reviewing compliance for a life insurance organisation.\n\n"
        f"Organisation type: {questionnaire.organization_type or 'unknown'}\n"
        f"Focus area: {questionnaire.user_input or 'general'}\n\n"
        "Below are the questionnaire questions and the organisation's answers.\n"
        "For each question, evaluate whether there is a compliance gap\n"
        "based on the referenced standard and clause.\n\n"
        "--- Questions and Answers ---\n"
    )

    for q in questions_data:
        std = q["source_standard"]
        clause = q["source_clause"]
        ref = f" [{std}::{clause}]" if std and clause else ""
        llm_prompt += f"\nQ{q['id']}{ref}:\n"
        llm_prompt += f"  Question: {q['text']}\n"
        llm_prompt += f"  Answer: {q['answer']}\n"

    llm_prompt += "\n\nReturn ONLY a JSON object with a 'findings' array. " \
                  "Only include findings where has_gap is true."

    # Call LLM
    try:
        raw_response = llm_client.generate(
            prompt=llm_prompt,
            system_prompt=_LLM_GAP_SYSTEM_PROMPT,
        )
    except Exception as exc:
        logger.warning("LLM gap analysis failed: %s", exc)
        return []

    # Parse LLM response
    if not raw_response or not raw_response.strip():
        logger.warning("LLM returned empty response for gap analysis")
        return []

    # Extract JSON from response
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Find balanced braces
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

    # Parse JSON
    import json
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.warning("LLM gap analysis JSON parse failed: %s", exc)
        return []

    findings: list[GapFinding] = []
    findings_data = data.get("findings", []) if isinstance(data, dict) else []

    for f in findings_data:
        if not isinstance(f, dict):
            continue
        if not f.get("has_gap"):
            continue

        finding = GapFinding(
            requirement_id=f.get("requirement_id", ""),
            clause_reference=f.get("clause_reference", ""),
            question=f.get("question", ""),
            user_answer=f.get("user_answer", ""),
            gap_severity=f.get("gap_severity", "medium"),
            mitigation=f.get("mitigation", ""),
            evidence_text=f.get("evidence_text", ""),
            llm_explanation=f.get("explanation", None),
        )
        findings.append(finding)

    # Sort by severity
    findings.sort(key=_severity_key)
    logger.info("LLM gap analysis: %d findings", len(findings))
    return findings


def evaluate_dynamic_rules(
    answers: dict[str, Any],
    questionnaire: Questionnaire,
    llm_client: Any = None,
) -> list[GapFinding]:
    """Evaluate gap findings using LLM-powered analysis of questionnaire answers.

    1. First, try LLM-powered gap analysis (reads answers and determines gaps).
    2. If LLM is unavailable or returns no findings, fall back to deterministic rules.
    3. Enrich findings with ChromaDB evidence.
    4. Return findings sorted by severity (high → medium → low).

    Args:
        answers: Mapping of question ID to user answer value.
        questionnaire: A validated :class:`Questionnaire` instance.
        llm_client: Optional LLMClient instance.

    Returns:
        List of :class:`GapFinding` objects sorted by severity.
    """
    # Try LLM-powered gap analysis first
    llm_findings = analyze_gaps_with_llm(questionnaire, answers, llm_client)
    if llm_findings:
        # Enrich with ChromaDB evidence
        for finding in llm_findings:
            if not finding.evidence_text:
                evidence = get_evidence_text(finding.question)
                if evidence:
                    finding.evidence_text = evidence
        return llm_findings

    # Fallback: deterministic rule evaluation
    dynamic_rules = get_dynamic_rules(questionnaire)
    questions = []
    for section in questionnaire.sections:
        questions.extend(section.questions)

    question_map: dict[str, str] = {q.id: q.text for q in questions}
    mapping = map_questions_to_rules(questions, dynamic_rules)

    # Build a rule lookup by id for quick access
    rule_by_id: dict[str, GapRule] = {r.id: r for r in dynamic_rules}

    findings: list[GapFinding] = []
    evaluated_rule_ids: set[str] = set()

    for question in questions:
        qid = question.id
        rule_id = mapping.get(qid)

        # Skip questions that couldn't be mapped
        if not rule_id or rule_id not in rule_by_id:
            continue

        rule = rule_by_id[rule_id]

        # Skip if this rule was already evaluated via another question
        if rule_id in evaluated_rule_ids:
            continue

        # Evaluate the rule
        if evaluate_rule(rule, answers):
            evaluated_rule_ids.add(rule_id)
            question_text = question_map.get(qid, rule.description)
            user_answer = answers.get(qid, "")

            # Build requirement_id from source_standard + source_clause
            req_id = rule_id
            clause_ref = rule.clause

            # Source standard for requirement_id clarity
            if question.source_standard:
                req_id = f"{question.source_standard}::{rule.clause}"

            finding = GapFinding(
                requirement_id=req_id,
                clause_reference=clause_ref,
                question=question_text,
                user_answer=user_answer,
                gap_severity=rule.severity_if_gap,
                mitigation=rule.mitigation,
                evidence_text="",
                llm_explanation=None,
            )

            # Enrich with ChromaDB evidence
            evidence = get_evidence_text(rule.description)
            if evidence:
                finding.evidence_text = evidence

            findings.append(finding)

    # Sort by severity: high (0) → medium (1) → low (2)
    findings.sort(key=_severity_key)

    return findings


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def analyze(
    answers: dict[str, Any],
    questionnaire: Questionnaire | None = None,
    llm_client: Any = None,
) -> list[GapFinding]:
    """Run the full gap analysis against user answers.

    When *questionnaire* is provided, LLM-powered gap analysis is used
    to evaluate answers against the referenced standards.  When
    *questionnaire* is ``None``, the existing static ``gap_rules.json``
    is used — this preserves backward compatibility.

    Args:
        answers: Mapping of question ID to user answer value.
        questionnaire: Optional validated :class:`Questionnaire` for
            LLM-powered gap analysis.  When ``None``, static rules are used.
        llm_client: Optional LLMClient instance for gap analysis.

    Returns:
        List of :class:`GapFinding` objects sorted by severity
        (high → medium → low).
    """
    if questionnaire is not None:
        return evaluate_dynamic_rules(answers, questionnaire, llm_client)

    # ── Static path (backward compatible) ──
    rules = load_gap_rules()
    questions = get_all_questions()

    # Build a lookup: question_id -> question text
    question_map: dict[str, str] = {q.id: q.text for q in questions}

    findings: list[GapFinding] = []

    for rule in rules:
        if evaluate_rule(rule, answers):
            question_text = question_map.get(rule.id, rule.description)
            # The rule ID is the requirement_id; we look up the question
            # text from the questionnaire using the question_id from the
            # gap_condition (not the rule id itself).
            qid = rule.gap_condition.get("question_id", "")
            question_text = question_map.get(qid, rule.description)

            user_answer = answers.get(qid, "")

            finding = GapFinding(
                requirement_id=rule.id,
                clause_reference=rule.clause,
                question=question_text,
                user_answer=user_answer,
                gap_severity=rule.severity_if_gap,
                mitigation=rule.mitigation,
                evidence_text="",  # Populated below if ChromaDB available
                llm_explanation=None,
            )

            # Try to enrich with ChromaDB evidence
            evidence = get_evidence_text(rule.description)
            if evidence:
                finding.evidence_text = evidence

            findings.append(finding)

    # Sort by severity: high (0) → medium (1) → low (2)
    findings.sort(key=_severity_key)

    return findings
