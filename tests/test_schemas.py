"""Comprehensive tests for engine.schemas Pydantic models.

Covers:
- Valid input validation for every model
- Invalid input rejection (missing/empty required fields)
- JSON round-trip serialization (model_dump_json / model_validate_json)
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from pydantic import ValidationError

from engine.schemas import (
    Answer,
    GapFinding,
    GapRule,
    Question,
    QuestionSection,
    Questionnaire,
    StandardsSource,
)


# ---------------------------------------------------------------------------
# GapRule
# ---------------------------------------------------------------------------

_VALID_GAP_RULE: dict[str, Any] = {
    "id": "GR-001",
    "standard": "APRA SRE-231",
    "clause": "Section 4.2",
    "description": "Models must undergo independent validation.",
    "category": "Model Risk",
    "gap_condition": {"type": "field_match", "field": "validation_independent", "expected": True},
    "severity_if_gap": "High",
    "mitigation": "Engage independent validation team.",
    "reference_url": "https://www.apra.gov.au/sre-231",
}


class TestGapRule:
    """Tests for the GapRule model."""

    def test_valid_gap_rule(self):
        rule = GapRule(**_VALID_GAP_RULE)
        assert rule.id == "GR-001"
        assert rule.severity_if_gap == "High"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            rule_dict = copy.copy(_VALID_GAP_RULE)
            del rule_dict["id"]
            GapRule(**rule_dict)

    def test_empty_id_raises(self):
        with pytest.raises(ValidationError):
            rule_dict = copy.copy(_VALID_GAP_RULE)
            rule_dict["id"] = ""
            GapRule(**rule_dict)

    def test_json_round_trip(self):
        rule = GapRule(**_VALID_GAP_RULE)
        json_str = rule.model_dump_json()
        restored = GapRule.model_validate_json(json_str)
        assert restored.id == rule.id
        assert restored.gap_condition == rule.gap_condition

    def test_model_dump_dict(self):
        rule = GapRule(**_VALID_GAP_RULE)
        d = rule.model_dump()
        assert isinstance(d, dict)
        assert d["id"] == "GR-001"

    def test_gap_condition_is_dict(self):
        rule = GapRule(**_VALID_GAP_RULE)
        assert isinstance(rule.gap_condition, dict)


# ---------------------------------------------------------------------------
# Question
# ---------------------------------------------------------------------------

_VALID_QUESTION: dict[str, Any] = {
    "id": "Q-001",
    "text": "Is the model independently validated?",
    "type": "boolean",
    "default": False,
    "options": None,
}

_VALID_QUESTION_CHOICE: dict[str, Any] = {
    "id": "Q-002",
    "text": "Which validation approach is used?",
    "type": "choice",
    "default": None,
    "options": ["Internal", "External", "Both"],
}


class TestQuestion:
    """Tests for the Question model."""

    def test_valid_question(self):
        q = Question(**_VALID_QUESTION)
        assert q.type == "boolean"
        assert q.default is False

    def test_question_with_options(self):
        q = Question(**_VALID_QUESTION_CHOICE)
        assert q.options == ["Internal", "External", "Both"]

    def test_missing_text_raises(self):
        with pytest.raises(ValidationError):
            q_dict = copy.copy(_VALID_QUESTION)
            del q_dict["text"]
            Question(**q_dict)

    def test_json_round_trip(self):
        q = Question(**_VALID_QUESTION)
        json_str = q.model_dump_json()
        restored = Question.model_validate_json(json_str)
        assert restored.id == q.id
        assert restored.default == q.default


# ---------------------------------------------------------------------------
# QuestionSection
# ---------------------------------------------------------------------------

_VALID_SECTION: dict[str, Any] = {
    "title": "Governance",
    "questions": [_VALID_QUESTION, _VALID_QUESTION_CHOICE],
}


class TestQuestionSection:
    """Tests for the QuestionSection model."""

    def test_valid_section(self):
        sec = QuestionSection(**_VALID_SECTION)
        assert len(sec.questions) == 2
        assert sec.questions[0].id == "Q-001"

    def test_empty_questions_raises(self):
        with pytest.raises(ValidationError):
            QuestionSection(title="Empty", questions=[])

    def test_json_round_trip(self):
        sec = QuestionSection(**_VALID_SECTION)
        json_str = sec.model_dump_json()
        restored = QuestionSection.model_validate_json(json_str)
        assert restored.title == sec.title
        assert len(restored.questions) == len(sec.questions)


# ---------------------------------------------------------------------------
# Answer
# ---------------------------------------------------------------------------

_VALID_ANSWER: dict[str, Any] = {
    "question_id": "Q-001",
    "value": True,
}


class TestAnswer:
    """Tests for the Answer model."""

    def test_valid_answer(self):
        a = Answer(**_VALID_ANSWER)
        assert a.question_id == "Q-001"
        assert a.value is True

    def test_answer_text_value(self):
        a = Answer(question_id="Q-002", value="External")
        assert a.value == "External"

    def test_missing_question_id_raises(self):
        with pytest.raises(ValidationError):
            a_dict: dict[str, Any] = {"value": True}
            Answer(**a_dict)

    def test_json_round_trip(self):
        a = Answer(**_VALID_ANSWER)
        json_str = a.model_dump_json()
        restored = Answer.model_validate_json(json_str)
        assert restored.value == a.value


# ---------------------------------------------------------------------------
# GapFinding
# ---------------------------------------------------------------------------

_VALID_FINDING: dict[str, Any] = {
    "requirement_id": "GR-001",
    "clause_reference": "Section 4.2",
    "question": "Is the model independently validated?",
    "user_answer": False,
    "gap_severity": "High",
    "mitigation": "Engage independent validation team.",
    "evidence_text": "No independent validation found in documentation.",
}


class TestGapFinding:
    """Tests for the GapFinding model."""

    def test_valid_finding(self):
        f = GapFinding(**_VALID_FINDING)
        assert f.gap_severity == "High"
        assert f.evidence_text == "No independent validation found in documentation."

    def test_empty_evidence_text_is_allowed(self):
        f_dict = copy.copy(_VALID_FINDING)
        del f_dict["evidence_text"]
        f = GapFinding(**f_dict)
        assert f.evidence_text == ""

    def test_missing_requirement_id_raises(self):
        with pytest.raises(ValidationError):
            f_dict = copy.copy(_VALID_FINDING)
            del f_dict["requirement_id"]
            GapFinding(**f_dict)

    def test_json_round_trip(self):
        f = GapFinding(**_VALID_FINDING)
        json_str = f.model_dump_json()
        restored = GapFinding.model_validate_json(json_str)
        assert restored.requirement_id == f.requirement_id
        assert restored.user_answer == f.user_answer


# ---------------------------------------------------------------------------
# Questionnaire
# ---------------------------------------------------------------------------

_VALID_QUESTIONNAIRE: dict[str, Any] = {
    "sections": [
        QuestionSection(
            title="Governance", questions=[Question(**_VALID_QUESTION)]
        ),
        QuestionSection(
            title="Documentation", questions=[Question(**_VALID_QUESTION_CHOICE)]
        ),
    ]
}


class TestQuestionnaire:
    """Tests for the Questionnaire model."""

    def test_valid_questionnaire(self):
        q = Questionnaire(**_VALID_QUESTIONNAIRE)
        assert len(q.sections) == 2

    def test_empty_sections_raises(self):
        with pytest.raises(ValidationError):
            Questionnaire(sections=[])

    def test_json_round_trip(self):
        q = Questionnaire(**_VALID_QUESTIONNAIRE)
        json_str = q.model_dump_json()
        restored = Questionnaire.model_validate_json(json_str)
        assert len(restored.sections) == len(q.sections)
        assert restored.sections[0].title == q.sections[0].title


# ---------------------------------------------------------------------------
# StandardsSource
# ---------------------------------------------------------------------------

_VALID_SOURCE: dict[str, Any] = {
    "name": "APRA SRE-231",
    "url": "https://www.apra.gov.au/prudential-standards/sre-231",
    "category": "APRA",
    "expected_last_modified": "2024-01-15",
}

_VALID_SOURCE_NO_DATE: dict[str, Any] = {
    "name": "ASX Corporate Governance Principles",
    "url": "https://www.asx.com.au/documents/corporate-governance-principles.pdf",
    "category": "ASX",
    "expected_last_modified": None,
}


class TestStandardsSource:
    """Tests for the StandardsSource model."""

    def test_valid_source(self):
        s = StandardsSource(**_VALID_SOURCE)
        assert s.category == "APRA"
        assert s.expected_last_modified == "2024-01-15"

    def test_source_without_date(self):
        s = StandardsSource(**_VALID_SOURCE_NO_DATE)
        assert s.expected_last_modified is None

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            src_dict = copy.copy(_VALID_SOURCE)
            del src_dict["name"]
            StandardsSource(**src_dict)

    def test_json_round_trip(self):
        s = StandardsSource(**_VALID_SOURCE)
        json_str = s.model_dump_json()
        restored = StandardsSource.model_validate_json(json_str)
        assert restored.name == s.name
        assert restored.expected_last_modified == s.expected_last_modified


# ---------------------------------------------------------------------------
# Config import verification
# ---------------------------------------------------------------------------

class TestConfigImport:
    """Tests that config.Settings can be imported and instantiated."""

    def test_settings_import(self):
        from config import Settings

        s = Settings()
        assert s.chroma_persist_directory == "data/chroma_db"
        assert s.embedding_model_name == "sentence-transformers/all-MiniLM-L6-v2"
        assert s.ingestion_schedule_hours == 168

    def test_settings_defaults(self):
        from config import Settings

        s = Settings()
        assert s.standards_sources_file == "standards_ingestion/sources.yaml"
        assert s.gap_rules_path == "data/gap_rules.json"
        assert s.questionnaire_path == "data/questionnaire.json"
