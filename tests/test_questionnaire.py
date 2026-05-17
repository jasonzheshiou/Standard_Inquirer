"""Tests for data/questionnaire.json structure and integrity.

Covers:
- Sections array is non-empty
- Every question has required fields (id, text, type)
- Valid question types (boolean, multi_choice, text)
- No duplicate question_ids
- Total question count between 5 and 10
- JSON round-trip serialization
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

VALID_TYPES = {"boolean", "multi_choice", "text"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
QUESTIONNAIRE_PATH = DATA_DIR / "questionnaire.json"


@pytest.fixture(scope="module")
def questionnaire():
    """Load questionnaire.json once per module."""
    assert QUESTIONNAIRE_PATH.exists(), f"questionnaire.json not found at {QUESTIONNAIRE_PATH}"
    with open(QUESTIONNAIRE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def all_question_ids(questionnaire):
    """Flatten all question ids across sections."""
    ids = []
    for section in questionnaire["sections"]:
        for q in section["questions"]:
            ids.append(q["id"])
    return ids


class TestQuestionnaireStructure:
    """Tests for questionnaire JSON structure."""

    def test_sections_non_empty(self, questionnaire):
        sections = questionnaire.get("sections")
        assert isinstance(sections, list), "sections must be a list"
        assert len(sections) > 0, "sections must not be empty"

    def test_section_has_title(self, questionnaire):
        for section in questionnaire["sections"]:
            assert "title" in section, f"Section missing 'title': {section}"
            assert isinstance(section["title"], str) and len(section["title"]) > 0

    def test_section_has_questions(self, questionnaire):
        for section in questionnaire["sections"]:
            questions = section.get("questions")
            assert isinstance(questions, list), f"Section '{section.get('title')}' questions must be a list"
            assert len(questions) > 0, f"Section '{section.get('title')}' must have at least one question"

    def test_total_question_count_range(self, questionnaire):
        total = sum(len(s["questions"]) for s in questionnaire["sections"])
        assert 5 <= total <= 10, f"Total questions must be between 5 and 10, got {total}"


class TestQuestionFields:
    """Tests for individual question field validation."""

    def test_question_has_required_fields(self, questionnaire):
        required = {"id", "text", "type"}
        for section in questionnaire["sections"]:
            for q in section["questions"]:
                missing = required - set(q.keys())
                assert not missing, f"Question '{q.get('id', '?')}' missing fields: {missing}"

    def test_question_type_is_valid(self, questionnaire):
        for section in questionnaire["sections"]:
            for q in section["questions"]:
                assert q["type"] in VALID_TYPES, (
                    f"Question '{q['id']}' has invalid type '{q['type']}'. "
                    f"Must be one of {VALID_TYPES}"
                )

    def test_question_text_is_non_empty(self, questionnaire):
        for section in questionnaire["sections"]:
            for q in section["questions"]:
                assert isinstance(q["text"], str) and len(q["text"]) > 0, (
                    f"Question '{q['id']}' text must be a non-empty string"
                )

    def test_question_id_is_non_empty(self, questionnaire):
        for section in questionnaire["sections"]:
            for q in section["questions"]:
                assert isinstance(q["id"], str) and len(q["id"]) > 0, (
                    "Question id must be a non-empty string"
                )


class TestNoDuplicateIds:
    """Tests for uniqueness of question ids."""

    def test_no_duplicate_question_ids(self, all_question_ids):
        seen = set()
        for qid in all_question_ids:
            assert qid not in seen, f"Duplicate question_id: {qid}"
            seen.add(qid)

    def test_all_ids_unique(self, all_question_ids):
        assert len(all_question_ids) == len(set(all_question_ids)), (
            f"Duplicate question_ids found. Total: {len(all_question_ids)}, Unique: {len(set(all_question_ids))}"
        )


class TestJsonRoundTrip:
    """Tests for JSON serialization integrity."""

    def test_json_round_trip(self, questionnaire):
        """Serialize to JSON and parse back — structure must be preserved."""
        json_str = json.dumps(questionnaire)
        restored = json.loads(json_str)
        assert restored["sections"] == questionnaire["sections"]

    def test_json_round_trip_preserves_question_count(self, questionnaire):
        json_str = json.dumps(questionnaire)
        restored = json.loads(json_str)
        original_total = sum(len(s["questions"]) for s in questionnaire["sections"])
        restored_total = sum(len(s["questions"]) for s in restored["sections"])
        assert original_total == restored_total
