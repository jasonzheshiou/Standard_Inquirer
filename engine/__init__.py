"""Compliance Gap Analyser engine package.

Public API:
    - load_questionnaire, get_all_questions, get_sections (from questionnaire)
    - analyze, evaluate_rule, load_gap_rules (from gap_analyzer)
"""

from engine.gap_analyzer import analyze, evaluate_rule, load_gap_rules
from engine.questionnaire import get_all_questions, get_sections, load_questionnaire

__all__ = [
    "analyze",
    "evaluate_rule",
    "load_gap_rules",
    "get_all_questions",
    "get_sections",
    "load_questionnaire",
]
