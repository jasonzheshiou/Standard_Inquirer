"""Helper script to validate questionnaire.json and gap_rules.json consistency.

Usage:
    python -m scripts.seed_questionnaire

Checks:
    - All question_ids in rules exist in questionnaire
    - All question_ids in questionnaire have at least one rule mapping
    - Reports orphan questions (no rule mapping) and orphan rules (no matching question)

Exit code:
    0 — consistent
    1 — issues found
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from loguru import logger

# Resolve paths relative to project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONNAIRE_PATH = PROJECT_ROOT / "data" / "questionnaire.json"
GAP_RULES_PATH = PROJECT_ROOT / "data" / "gap_rules.json"


def load_json(path: Path) -> dict[str, object]:
    """Load and return parsed JSON from *path*."""
    raw = path.read_text(encoding="utf-8")
    return json.loads(raw)


def get_question_ids(data: dict) -> set[str]:
    """Extract all question IDs from a questionnaire JSON structure."""
    ids: set[str] = set()
    for section in data.get("sections", []):
        for question in section.get("questions", []):
            ids.add(question["id"])
    return ids


def get_rule_question_ids(data: dict) -> set[str]:
    """Extract all question_id references from gap rules."""
    ids: set[str] = set()
    requirements = data.get("requirements", data if isinstance(data, list) else [])
    if isinstance(requirements, list):
        for rule in requirements:
            condition = rule.get("gap_condition", {})
            qid = condition.get("question_id")
            if qid:
                ids.add(qid)
    return ids


def main() -> int:
    """Validate questionnaire ↔ gap_rules consistency.

    Returns:
        0 if consistent, 1 if issues found.
    """
    logger.info("Validating questionnaire and gap rules consistency...")

    # Load data files
    questionnaire = load_json(QUESTIONNAIRE_PATH)
    rules_data = load_json(GAP_RULES_PATH)

    # Extract IDs
    question_ids = get_question_ids(questionnaire)
    rule_question_ids = get_rule_question_ids(rules_data)

    # Count rules
    requirements = rules_data.get("requirements", rules_data if isinstance(rules_data, list) else [])
    total_rules = len(requirements) if isinstance(requirements, list) else 0
    total_questions = len(question_ids)

    # Find orphans
    orphan_questions = question_ids - rule_question_ids  # questions with no rule mapping
    orphan_rules = rule_question_ids - question_ids  # rules referencing non-existent questions

    # Report
    logger.info("Questionnaire: {} questions, {} rules", total_questions, total_rules)

    if orphan_questions:
        logger.warning("Orphan questions (no rule mapping): {}", sorted(orphan_questions))
    else:
        logger.info("All questionnaire questions have at least one rule mapping.")

    if orphan_rules:
        logger.warning("Orphan rule references (no matching question): {}", sorted(orphan_rules))
    else:
        logger.info("All rule question_id references match questionnaire questions.")

    # Summary
    issues = len(orphan_questions) + len(orphan_rules)
    logger.info(
        "Summary: {} questions, {} rules, {} orphan questions, {} orphan rules",
        total_questions,
        total_rules,
        len(orphan_questions),
        len(orphan_rules),
    )

    if issues > 0:
        logger.error("Found {} issue(s). Inconsistency detected.", issues)
        return 1

    logger.info("Validation passed — no issues found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
