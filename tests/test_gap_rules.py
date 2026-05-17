"""Tests for data/gap_rules.json structure and cross-references.

Covers:
- standards_version field exists
- requirements array has at least 5 entries
- Every rule's gap_condition.question_id exists in the questionnaire
- Every rule has valid severity (high/medium/low)
- No duplicate rule ids
- JSON round-trip serialization
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

VALID_SEVERITIES = {"high", "medium", "low"}
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GAP_RULES_PATH = DATA_DIR / "gap_rules.json"
QUESTIONNAIRE_PATH = DATA_DIR / "questionnaire.json"


@pytest.fixture(scope="module")
def gap_rules():
    """Load gap_rules.json once per module."""
    assert GAP_RULES_PATH.exists(), f"gap_rules.json not found at {GAP_RULES_PATH}"
    with open(GAP_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def questionnaire():
    """Load questionnaire.json once per module."""
    assert QUESTIONNAIRE_PATH.exists(), f"questionnaire.json not found at {QUESTIONNAIRE_PATH}"
    with open(QUESTIONNAIRE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def valid_question_ids(questionnaire):
    """Flatten all question ids from the questionnaire."""
    ids = set()
    for section in questionnaire["sections"]:
        for q in section["questions"]:
            ids.add(q["id"])
    return ids


@pytest.fixture(scope="module")
def all_rule_ids(gap_rules):
    """Flatten all rule ids."""
    return [r["id"] for r in gap_rules["requirements"]]


class TestGapRulesStructure:
    """Tests for gap_rules JSON structure."""

    def test_standards_version_exists(self, gap_rules):
        assert "standards_version" in gap_rules, "gap_rules must have 'standards_version'"
        assert isinstance(gap_rules["standards_version"], str)
        assert len(gap_rules["standards_version"]) > 0

    def test_requirements_array_exists(self, gap_rules):
        reqs = gap_rules.get("requirements")
        assert isinstance(reqs, list), "requirements must be a list"

    def test_requirements_count_at_least_5(self, gap_rules):
        count = len(gap_rules["requirements"])
        assert count >= 5, f"Must have at least 5 requirements, got {count}"


class TestRuleFields:
    """Tests for individual rule field validation."""

    REQUIRED_FIELDS = {"id", "standard", "clause", "description", "category", "gap_condition", "severity_if_gap", "mitigation", "reference_url"}

    def test_rule_has_required_fields(self, gap_rules):
        for rule in gap_rules["requirements"]:
            missing = self.REQUIRED_FIELDS - set(rule.keys())
            assert not missing, f"Rule '{rule.get('id', '?')}' missing fields: {missing}"

    def test_rule_id_is_non_empty(self, gap_rules):
        for rule in gap_rules["requirements"]:
            assert isinstance(rule["id"], str) and len(rule["id"]) > 0

    def test_rule_description_is_non_empty(self, gap_rules):
        for rule in gap_rules["requirements"]:
            assert isinstance(rule["description"], str) and len(rule["description"]) > 0

    def test_rule_mitigation_is_non_empty(self, gap_rules):
        for rule in gap_rules["requirements"]:
            assert isinstance(rule["mitigation"], str) and len(rule["mitigation"]) > 0

    def test_rule_reference_url_is_non_empty(self, gap_rules):
        for rule in gap_rules["requirements"]:
            assert isinstance(rule["reference_url"], str) and len(rule["reference_url"]) > 0


class TestGapCondition:
    """Tests for gap_condition structure and questionnaire references."""

    def test_gap_condition_has_question_id(self, gap_rules):
        for rule in gap_rules["requirements"]:
            gc = rule["gap_condition"]
            assert "question_id" in gc, f"Rule '{rule['id']}' gap_condition missing 'question_id'"

    def test_gap_condition_question_id_exists_in_questionnaire(self, gap_rules, valid_question_ids):
        for rule in gap_rules["requirements"]:
            qid = rule["gap_condition"]["question_id"]
            assert qid in valid_question_ids, (
                f"Rule '{rule['id']}' references question_id '{qid}' which does not exist in questionnaire"
            )

    def test_gap_condition_has_logic(self, gap_rules):
        for rule in gap_rules["requirements"]:
            gc = rule["gap_condition"]
            assert "logic" in gc, f"Rule '{rule['id']}' gap_condition missing 'logic'"

    def test_gap_condition_has_value(self, gap_rules):
        for rule in gap_rules["requirements"]:
            gc = rule["gap_condition"]
            assert "value" in gc, f"Rule '{rule['id']}' gap_condition missing 'value'"


class TestSeverity:
    """Tests for severity_if_gap values."""

    def test_severity_is_valid(self, gap_rules):
        for rule in gap_rules["requirements"]:
            sev = rule["severity_if_gap"]
            assert sev in VALID_SEVERITIES, (
                f"Rule '{rule['id']}' has invalid severity '{sev}'. Must be one of {VALID_SEVERITIES}"
            )

    def test_severity_is_string(self, gap_rules):
        for rule in gap_rules["requirements"]:
            assert isinstance(rule["severity_if_gap"], str), (
                f"Rule '{rule['id']}' severity_if_gap must be a string"
            )


class TestNoDuplicateIds:
    """Tests for uniqueness of rule ids."""

    def test_no_duplicate_rule_ids(self, all_rule_ids):
        seen = set()
        for rid in all_rule_ids:
            assert rid not in seen, f"Duplicate rule id: {rid}"
            seen.add(rid)

    def test_all_ids_unique(self, all_rule_ids):
        assert len(all_rule_ids) == len(set(all_rule_ids)), (
            f"Duplicate rule ids found. Total: {len(all_rule_ids)}, Unique: {len(set(all_rule_ids))}"
        )


class TestJsonRoundTrip:
    """Tests for JSON serialization integrity."""

    def test_json_round_trip(self, gap_rules):
        json_str = json.dumps(gap_rules)
        restored = json.loads(json_str)
        assert restored["requirements"] == gap_rules["requirements"]

    def test_standards_version_preserved(self, gap_rules):
        json_str = json.dumps(gap_rules)
        restored = json.loads(json_str)
        assert restored["standards_version"] == gap_rules["standards_version"]
