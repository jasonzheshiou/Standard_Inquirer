"""End-to-end tests for the Compliance Gap Analyser pipeline.

Tests the full analysis flow using real data files:
    - data/questionnaire.json
    - data/gap_rules.json

Covers:
    - Full analysis pipeline with real data
    - All "No" answers → all 8 rules trigger
    - All "Yes" answers → 0 findings
    - Severity ordering (high → medium → low)
    - CSV export validity
    - Partial answers
    - Engine importability without Streamlit
"""

from __future__ import annotations

import csv
import io
import inspect

import pytest

from engine.gap_analyzer import analyze, evaluate_rule, load_gap_rules
from engine.questionnaire import get_all_questions, load_questionnaire
from engine.schemas import GapFinding


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _clear_caches():
    """Clear Streamlit caches on module import so tests are repeatable."""
    from engine import gap_analyzer as ga_mod
    from engine import questionnaire as q_mod

    if hasattr(ga_mod._load_raw_rules, "cache_clear"):
        ga_mod._load_raw_rules.cache_clear()  # type: ignore[attr-defined]
    if hasattr(q_mod._load_raw, "cache_clear"):
        q_mod._load_raw.cache_clear()  # type: ignore[attr-defined]

    yield


# ---------------------------------------------------------------------------
# Engine importability tests
# ---------------------------------------------------------------------------


class TestEngineImport:
    """Verify the engine is importable without Streamlit running."""

    def test_engine_importable_without_streamlit(self) -> None:
        """Engine imports should succeed even when Streamlit is absent.

        Verifies that the gap_analyzer and questionnaire modules use
        no-op fallbacks when Streamlit is not available by checking
        the source code patterns.
        """

        from engine import gap_analyzer as ga_mod
        from engine import questionnaire as q_mod

        # Both modules should define a no-op decorator for when Streamlit is absent
        ga_source = inspect.getsource(ga_mod)
        q_source = inspect.getsource(q_mod)

        # The no-op fallback pattern should be present
        assert "except ImportError" in ga_source
        assert "_cache_resource" in ga_source
        assert "except ImportError" in q_source
        assert "_cache_data" in q_source

        # Core functions should be callable (they are, regardless of Streamlit)
        assert callable(ga_mod.analyze)
        assert callable(ga_mod.evaluate_rule)
        assert callable(ga_mod.load_gap_rules)
        assert callable(q_mod.get_all_questions)
        assert callable(q_mod.get_sections)
        assert callable(q_mod.load_questionnaire)

    def test_engine_public_api(self) -> None:
        """All expected symbols should be exported from engine.__all__."""
        from engine import __all__

        expected = {
            "analyze",
            "evaluate_rule",
            "load_gap_rules",
            "get_all_questions",
            "get_sections",
            "load_questionnaire",
        }
        assert set(__all__) == expected


# ---------------------------------------------------------------------------
# Full pipeline tests with real data
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end tests using the real data/questionnaire.json and data/gap_rules.json."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Clear caches before each test in this class."""
        from engine import gap_analyzer as ga_mod
        from engine import questionnaire as q_mod

        if hasattr(ga_mod._load_raw_rules, "cache_clear"):
            ga_mod._load_raw_rules.cache_clear()  # type: ignore[attr-defined]
        if hasattr(q_mod._load_raw, "cache_clear"):
            q_mod._load_raw.cache_clear()  # type: ignore[attr-defined]

    def test_load_questionnaire_real_data(self):
        """Real questionnaire should load with 8 questions in 4 sections."""
        qs = load_questionnaire()
        assert len(qs.sections) == 4
        all_q = get_all_questions()
        assert len(all_q) == 8

    def test_load_gap_rules_real_data(self):
        """Real gap rules should load with 8 rules."""
        rules = load_gap_rules()
        assert len(rules) == 8

    def test_all_no_answers_all_gaps(self):
        """When all 8 questions are answered 'No', all 8 rules should trigger."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        assert len(findings) == 8

    def test_all_yes_answers_zero_findings(self):
        """When all 8 questions are answered 'Yes', no gaps should be found."""
        answers = {q.id: "Yes" for q in get_all_questions()}
        findings = analyze(answers)
        assert len(findings) == 0

    def test_severity_ordering(self):
        """Findings must be sorted: high → medium → low."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        severities = [f.gap_severity for f in findings]
        assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])

    def test_finding_fields_populated(self):
        """Each finding should have all required fields populated."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        for f in findings:
            assert f.requirement_id
            assert f.clause_reference
            assert f.question
            assert f.user_answer == "No"
            assert f.gap_severity in ("high", "medium", "low")
            assert f.mitigation
            assert isinstance(f.evidence_text, str)

    def test_partial_answers_only_answered_trigger(self):
        """Only answered questions should trigger gaps."""
        # Answer only 3 questions
        all_qs = get_all_questions()
        answers = {all_qs[0].id: "No", all_qs[1].id: "No", all_qs[2].id: "No"}
        findings = analyze(answers)
        assert len(findings) == 3

    def test_partial_answers_mixed_yes_no(self):
        """Mixed Yes/No answers should produce correct subset of findings."""
        all_qs = get_all_questions()
        answers = {all_qs[0].id: "No", all_qs[1].id: "Yes", all_qs[2].id: "No", all_qs[3].id: "Yes"}
        answers.update({q.id: "Yes" for q in all_qs[4:]})
        findings = analyze(answers)
        assert len(findings) == 2

    def test_unanswered_questions_no_gap(self):
        """Unanswered questions should not trigger any gaps."""
        answers = {}
        findings = analyze(answers)
        assert len(findings) == 0

    def test_finding_requirement_ids_unique(self):
        """Each finding should have a unique requirement_id."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        req_ids = [f.requirement_id for f in findings]
        assert len(req_ids) == len(set(req_ids))


# ---------------------------------------------------------------------------
# CSV export tests
# ---------------------------------------------------------------------------


class TestCSVExport:
    """Verify CSV export content is valid and matches findings."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Clear caches before each test."""
        from engine import gap_analyzer as ga_mod
        from engine import questionnaire as q_mod

        if hasattr(ga_mod._load_raw_rules, "cache_clear"):
            ga_mod._load_raw_rules.cache_clear()  # type: ignore[attr-defined]
        if hasattr(q_mod._load_raw, "cache_clear"):
            q_mod._load_raw.cache_clear()  # type: ignore[attr-defined]

    def _findings_to_csv(self, findings: list[GapFinding]) -> str:
        """Serialize findings to CSV string (mimicking Streamlit export)."""
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "requirement_id",
            "clause_reference",
            "question",
            "user_answer",
            "gap_severity",
            "mitigation",
            "evidence_text",
        ])
        for f in findings:
            writer.writerow([
                f.requirement_id,
                f.clause_reference,
                f.question,
                f.user_answer,
                f.gap_severity,
                f.mitigation,
                f.evidence_text,
            ])
        return output.getvalue()

    def test_csv_valid_with_findings(self):
        """CSV export should produce valid CSV with all findings."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        csv_text = self._findings_to_csv(findings)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Header + 8 findings
        assert len(rows) == 9
        # First data row should have 7 columns
        assert len(rows[1]) == 7

    def test_csv_valid_with_no_findings(self):
        """CSV export should produce valid CSV with only header when no findings."""
        answers = {q.id: "Yes" for q in get_all_questions()}
        findings = analyze(answers)
        csv_text = self._findings_to_csv(findings)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # Only header row
        assert len(rows) == 1
        assert rows[0] == [
            "requirement_id",
            "clause_reference",
            "question",
            "user_answer",
            "gap_severity",
            "mitigation",
            "evidence_text",
        ]

    def test_csv_content_matches_findings(self):
        """CSV row content should exactly match finding fields."""
        answers = {q.id: "No" for q in get_all_questions()}
        findings = analyze(answers)
        csv_text = self._findings_to_csv(findings)
        reader = csv.DictReader(io.StringIO(csv_text))
        csv_rows = list(reader)
        assert len(csv_rows) == len(findings)
        for i, row in enumerate(csv_rows):
            assert row["requirement_id"] == findings[i].requirement_id
            assert row["clause_reference"] == findings[i].clause_reference
            assert row["gap_severity"] == findings[i].gap_severity
            assert row["user_answer"] == findings[i].user_answer


# ---------------------------------------------------------------------------
# Rule evaluation edge cases
# ---------------------------------------------------------------------------


class TestEvaluateRuleEdgeCases:
    """Edge cases for rule evaluation with real rule structure."""

    def test_evaluate_rule_with_real_rule(self):
        """evaluate_rule should work with real GapRule objects."""
        rules = load_gap_rules()
        assert len(rules) > 0
        rule = rules[0]
        # "No" answer should trigger the gap
        assert evaluate_rule(rule, {rule.gap_condition["question_id"]: "No"}) is True
        # "Yes" answer should not trigger
        assert evaluate_rule(rule, {rule.gap_condition["question_id"]: "Yes"}) is False

    def test_evaluate_rule_missing_question(self):
        """evaluate_rule should return False when question is not in answers."""
        rules = load_gap_rules()
        rule = rules[0]
        assert evaluate_rule(rule, {}) is False
        assert evaluate_rule(rule, {"nonexistent": "No"}) is False
