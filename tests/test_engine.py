"""Comprehensive tests for the engine package (questionnaire + gap_analyzer).

Covers:
- Questionnaire loading, validation, and query helpers
- Gap rule loading and validation
- Rule evaluation with "equals" logic
- Full analysis pipeline (severity ordering, missing answers, all-yes)
- ChromaDB evidence retrieval with mock collection
- Error handling for invalid JSON and missing files
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from engine.gap_analyzer import (
    GapAnalysisError,
    analyze,
    evaluate_rule,
    get_evidence_text,
    load_gap_rules,
)
from engine.questionnaire import (
    QuestionnaireError,
    get_all_questions,
    get_sections,
    load_questionnaire,
)
from engine.schemas import GapRule, Questionnaire


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_QUESTIONNAIRE: dict[str, Any] = {
    "sections": [
        {
            "title": "Governance",
            "questions": [
                {"id": "q1", "text": "Q1 text?", "type": "boolean", "default": None},
                {"id": "q2", "text": "Q2 text?", "type": "boolean", "default": None},
            ],
        },
        {
            "title": "Documentation",
            "questions": [
                {"id": "q3", "text": "Q3 text?", "type": "boolean", "default": None},
            ],
        },
    ]
}

_VALID_GAP_RULES: list[dict[str, Any]] = [
    {
        "id": "r1",
        "standard": "CPS 230",
        "clause": "P1",
        "description": "Must have governance.",
        "category": "Governance",
        "gap_condition": {"question_id": "q1", "logic": "equals", "value": "No"},
        "severity_if_gap": "high",
        "mitigation": "Fix it.",
        "reference_url": "http://example.com",
    },
    {
        "id": "r2",
        "standard": "CPS 230",
        "clause": "P2",
        "description": "Must document.",
        "category": "Documentation",
        "gap_condition": {"question_id": "q2", "logic": "equals", "value": "No"},
        "severity_if_gap": "medium",
        "mitigation": "Document it.",
        "reference_url": "http://example.com",
    },
    {
        "id": "r3",
        "standard": "CPS 230",
        "clause": "P3",
        "description": "Must report.",
        "category": "Reporting",
        "gap_condition": {"question_id": "q3", "logic": "equals", "value": "No"},
        "severity_if_gap": "low",
        "mitigation": "Report it.",
        "reference_url": "http://example.com",
    },
]

# Wrapper format (matches the real gap_rules.json structure)
_VALID_GAP_RULES_WRAPPER: dict[str, Any] = {
    "standards_version": "2025-04-01",
    "requirements": _VALID_GAP_RULES,
}


@pytest.fixture()
def temp_questionnaire_file() -> Path:
    """Create a temporary questionnaire JSON file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_VALID_QUESTIONNAIRE, f)
    yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture()
def temp_gap_rules_file() -> Path:
    """Create a temporary gap-rules JSON file (bare list) and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_VALID_GAP_RULES, f)
    yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


@pytest.fixture()
def temp_gap_rules_wrapper_file() -> Path:
    """Create a temporary gap-rules JSON file (wrapper format) and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(_VALID_GAP_RULES_WRAPPER, f)
    yield Path(f.name)
    Path(f.name).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Questionnaire tests
# ---------------------------------------------------------------------------


class TestLoadQuestionnaire:
    """Tests for load_questionnaire."""

    def test_loads_valid_json(self, temp_questionnaire_file: Path) -> None:
        qs = load_questionnaire(str(temp_questionnaire_file))
        assert isinstance(qs, Questionnaire)
        assert len(qs.sections) == 2

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(QuestionnaireError, match="not found"):
            load_questionnaire("/nonexistent/path/questionnaire.json")

    def test_raises_on_invalid_json(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("not valid json {{{")
            fname = f.name
        try:
            with pytest.raises(QuestionnaireError, match="Invalid JSON"):
                load_questionnaire(fname)
        finally:
            Path(fname).unlink(missing_ok=True)

    def test_raises_on_invalid_schema(self) -> None:
        bad = {"sections": []}  # min_length=1 violated
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(bad, f)
            fname = f.name
        try:
            with pytest.raises(QuestionnaireError, match="validation failed"):
                load_questionnaire(fname)
        finally:
            Path(fname).unlink(missing_ok=True)


class TestGetAllQuestions:
    """Tests for get_all_questions."""

    def test_returns_flat_list(self, temp_questionnaire_file: Path) -> None:
        with patch("engine.questionnaire.settings") as mock_settings:
            mock_settings.questionnaire_path = str(temp_questionnaire_file)
            # Force reload by clearing cache
            from engine import questionnaire as q_mod

            if hasattr(q_mod._load_raw, "cache_clear"):
                q_mod._load_raw.cache_clear()
            questions = get_all_questions()
        assert len(questions) == 3
        assert questions[0].id == "q1"
        assert questions[2].id == "q3"

    def test_preserves_order(self, temp_questionnaire_file: Path) -> None:
        with patch("engine.questionnaire.settings") as mock_settings:
            mock_settings.questionnaire_path = str(temp_questionnaire_file)
            from engine import questionnaire as q_mod

            if hasattr(q_mod._load_raw, "cache_clear"):
                q_mod._load_raw.cache_clear()
            questions = get_all_questions()
        ids = [q.id for q in questions]
        assert ids == ["q1", "q2", "q3"]


class TestGetSections:
    """Tests for get_sections."""

    def test_returns_sections(self, temp_questionnaire_file: Path) -> None:
        with patch("engine.questionnaire.settings") as mock_settings:
            mock_settings.questionnaire_path = str(temp_questionnaire_file)
            from engine import questionnaire as q_mod

            if hasattr(q_mod._load_raw, "cache_clear"):
                q_mod._load_raw.cache_clear()
            sections = get_sections()
        assert len(sections) == 2
        assert sections[0].title == "Governance"
        assert sections[1].title == "Documentation"

    def test_sections_have_questions(self, temp_questionnaire_file: Path) -> None:
        with patch("engine.questionnaire.settings") as mock_settings:
            mock_settings.questionnaire_path = str(temp_questionnaire_file)
            from engine import questionnaire as q_mod

            if hasattr(q_mod._load_raw, "cache_clear"):
                q_mod._load_raw.cache_clear()
            sections = get_sections()
        assert len(sections[0].questions) == 2
        assert len(sections[1].questions) == 1


# ---------------------------------------------------------------------------
# Gap rule loading tests
# ---------------------------------------------------------------------------


class TestLoadGapRules:
    """Tests for load_gap_rules."""

    def test_loads_bare_list(self, temp_gap_rules_file: Path) -> None:
        rules = load_gap_rules(str(temp_gap_rules_file))
        assert len(rules) == 3
        assert all(isinstance(r, GapRule) for r in rules)

    def test_loads_wrapper_format(self, temp_gap_rules_wrapper_file: Path) -> None:
        rules = load_gap_rules(str(temp_gap_rules_wrapper_file))
        assert len(rules) == 3

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(GapAnalysisError, match="not found"):
            load_gap_rules("/nonexistent/path/gap_rules.json")

    def test_raises_on_invalid_json(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{broken")
            fname = f.name
        try:
            with pytest.raises(GapAnalysisError, match="Invalid JSON"):
                load_gap_rules(fname)
        finally:
            Path(fname).unlink(missing_ok=True)

    def test_raises_on_invalid_rule_schema(self) -> None:
        bad = [{"id": ""}]  # empty id violates min_length=1
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(bad, f)
            fname = f.name
        try:
            with pytest.raises(GapAnalysisError, match="validation failed"):
                load_gap_rules(fname)
        finally:
            Path(fname).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Rule evaluation tests
# ---------------------------------------------------------------------------


class TestEvaluateRule:
    """Tests for evaluate_rule with 'equals' logic."""

    def _make_rule(self, question_id: str = "q1", value: str = "No") -> GapRule:
        return GapRule(
            id="r-test",
            standard="CPS 230",
            clause="P1",
            description="test",
            category="Test",
            gap_condition={"question_id": question_id, "logic": "equals", "value": value},
            severity_if_gap="high",
            mitigation="test",
            reference_url="http://x",
        )

    def test_triggered_when_answer_matches(self) -> None:
        rule = self._make_rule(value="No")
        assert evaluate_rule(rule, {"q1": "No"}) is True

    def test_not_triggered_when_answer_differs(self) -> None:
        rule = self._make_rule(value="No")
        assert evaluate_rule(rule, {"q1": "Yes"}) is False

    def test_not_triggered_when_answer_missing(self) -> None:
        rule = self._make_rule(value="No")
        assert evaluate_rule(rule, {}) is False

    def test_not_triggered_when_question_not_in_answers(self) -> None:
        rule = self._make_rule(value="No")
        assert evaluate_rule(rule, {"q2": "No"}) is False

    def test_case_sensitive_equality(self) -> None:
        # "No" should match "No" but not "no" (string comparison)
        rule = self._make_rule(value="No")
        assert evaluate_rule(rule, {"q1": "No"}) is True
        assert evaluate_rule(rule, {"q1": "no"}) is False

    def test_string_coercion(self) -> None:
        # Values are compared as strings
        rule = self._make_rule(value="0")
        assert evaluate_rule(rule, {"q1": 0}) is True  # int 0 → str "0"


# ---------------------------------------------------------------------------
# Full analysis tests
# ---------------------------------------------------------------------------


class TestAnalyze:
    """Tests for the analyze() pipeline."""

    def _setup(self, rules_path: str | None = None) -> None:
        """Patch settings to use temporary files and clear caches."""
        from engine import gap_analyzer as ga_mod
        from engine import questionnaire as q_mod

        if hasattr(ga_mod._load_raw_rules, "cache_clear"):
            ga_mod._load_raw_rules.cache_clear()
        if hasattr(q_mod._load_raw, "cache_clear"):
            q_mod._load_raw.cache_clear()

        # Patch config.settings so analyze() loads from temp files
        if rules_path is not None:
            from config import settings
            settings.gap_rules_path = rules_path

    def test_correct_findings_count(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """When all three questions are answered 'No', all 3 rules should trigger."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            answers = {"q1": "No", "q2": "No", "q3": "No"}
            findings = analyze(answers)

        assert len(findings) == 3

    def test_severity_ordering(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """Findings must be sorted: high → medium → low."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            answers = {"q1": "No", "q2": "No", "q3": "No"}
            findings = analyze(answers)

        severities = [f.gap_severity for f in findings]
        assert severities == ["high", "medium", "low"]

    def test_all_yes_returns_zero_findings(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """When all answers are 'Yes', no gaps should be found."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            answers = {"q1": "Yes", "q2": "Yes", "q3": "Yes"}
            findings = analyze(answers)

        assert len(findings) == 0

    def test_missing_answers_no_gap(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """Rules with unanswered questions should not trigger gaps."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            # Only answer q1; q2 and q3 are missing
            answers = {"q1": "No"}
            findings = analyze(answers)

        assert len(findings) == 1
        assert findings[0].requirement_id == "r1"

    def test_finding_fields_populated(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """A finding should contain all expected fields."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            answers = {"q1": "No"}
            findings = analyze(answers)

        f = findings[0]
        assert f.requirement_id == "r1"
        assert f.clause_reference == "P1"
        assert f.user_answer == "No"
        assert f.gap_severity == "high"
        assert f.mitigation == "Fix it."
        assert f.evidence_text == ""  # No ChromaDB

    def test_partial_answers_mixed_severity(
        self,
        temp_questionnaire_file: Path,
        temp_gap_rules_file: Path,
    ) -> None:
        """Mixed answers should produce correct subset of findings in severity order."""
        self._setup(str(temp_gap_rules_file))

        with patch("engine.questionnaire.settings") as mock_qs:
            mock_qs.questionnaire_path = str(temp_questionnaire_file)
            # q1=No (high), q2=Yes, q3=No (low)
            answers = {"q1": "No", "q2": "Yes", "q3": "No"}
            findings = analyze(answers)

        assert len(findings) == 2
        assert findings[0].gap_severity == "high"
        assert findings[1].gap_severity == "low"


# ---------------------------------------------------------------------------
# ChromaDB evidence retrieval tests
# ---------------------------------------------------------------------------


class TestGetEvidenceText:
    """Tests for get_evidence_text with mock ChromaDB."""

    def setup_method(self) -> None:
        """Inject a mock sentence_transformers module into sys.modules."""
        mock_st_class = MagicMock()
        mock_st_module = ModuleType("sentence_transformers")
        mock_st_module.SentenceTransformer = mock_st_class
        self._mock_st_class = mock_st_class
        sys.modules["sentence_transformers"] = mock_st_module

    def teardown_method(self) -> None:
        """Remove the mock module from sys.modules."""
        sys.modules.pop("sentence_transformers", None)

    def test_returns_empty_when_collection_none(self) -> None:
        result = get_evidence_text("test description", collection=None)
        assert result == ""

    def test_returns_empty_on_exception(self) -> None:
        """Should gracefully degrade when ChromaDB raises."""
        self._mock_st_class.side_effect = RuntimeError("model not found")
        bad_collection = MagicMock()
        bad_collection.query.side_effect = RuntimeError("connection failed")
        result = get_evidence_text("test description", collection=bad_collection)
        assert result == ""

    def test_returns_document_text_on_success(self) -> None:
        """Should return the top document text on successful query."""
        mock_encode_result = MagicMock()
        mock_encode_result.tolist.return_value = [0.1, 0.2, 0.3]
        self._mock_st_class.return_value.encode = mock_encode_result
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["Evidence text from vector search"]],
        }
        result = get_evidence_text("test description", collection=mock_collection)
        assert result == "Evidence text from vector search"

    def test_returns_empty_on_empty_results(self) -> None:
        """Should return empty string when no documents match."""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {"documents": [[]]}
        result = get_evidence_text("test description", collection=mock_collection)
        assert result == ""

    def test_returns_empty_on_missing_documents_key(self) -> None:
        """Should handle unexpected ChromaDB response format."""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {"results": []}
        result = get_evidence_text("test description", collection=mock_collection)
        assert result == ""


# ---------------------------------------------------------------------------
# Engine package import tests
# ---------------------------------------------------------------------------


class TestEnginePackage:
    """Tests that the engine package exports the correct public API."""

    def test_public_api_importable(self) -> None:
        from engine import (
            analyze,
            evaluate_rule,
            get_all_questions,
            get_sections,
            load_gap_rules,
            load_questionnaire,
        )

        assert callable(analyze)
        assert callable(evaluate_rule)
        assert callable(load_gap_rules)
        assert callable(get_all_questions)
        assert callable(get_sections)
        assert callable(load_questionnaire)

    def test_all_in___all__(self) -> None:
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
