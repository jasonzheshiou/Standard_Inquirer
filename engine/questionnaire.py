"""Questionnaire loading and validation for the Compliance Gap Analyser.

Provides functions to load, validate, and query the CPS 230
questionnaire stored as JSON.  All loaders cache results via
Streamlit's ``@st.cache_data`` when available so repeated calls
during a session are fast.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import settings
from engine.schemas import Question, Questionnaire, QuestionSection

try:
    import streamlit as st

    _cache_data = st.cache_data  # type: ignore[has-type]
except ImportError:  # pragma: no cover

    def _cache_data(func: Any) -> Any:
        """No-op decorator when Streamlit is not installed."""
        return func


class QuestionnaireError(Exception):
    """Raised when a questionnaire cannot be loaded or validated."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


@_cache_data
def _load_raw(path: str) -> Questionnaire:
    """Load and validate questionnaire JSON from *path*.

    This function is intentionally decorated with ``@st.cache_data`` so
    that repeated calls within a Streamlit session avoid re-parsing the
    file.  The decorator is applied at import time; if Streamlit is not
    installed the no-op wrapper is used instead.

    Args:
        path: Absolute or relative path to the questionnaire JSON file.

    Returns:
        A validated :class:`Questionnaire` model.

    Raises:
        QuestionnaireError: If the file cannot be read or does not
            validate against the :class:`Questionnaire` schema.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise QuestionnaireError(f"Questionnaire file not found: {path}")

    try:
        raw = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QuestionnaireError(f"Cannot read questionnaire file: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise QuestionnaireError(f"Invalid JSON in questionnaire file: {exc}") from exc

    try:
        return Questionnaire.model_validate(data)
    except Exception as exc:
        raise QuestionnaireError(f"Questionnaire validation failed: {exc}") from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_questionnaire(path: str | None = None) -> Questionnaire:
    """Load the questionnaire from JSON and validate it.

    Args:
        path: Optional override path.  Defaults to
            ``settings.questionnaire_path``.

    Returns:
        A validated :class:`Questionnaire` model.

    Raises:
        QuestionnaireError: If loading or validation fails.
    """
    target = path or settings.questionnaire_path
    return _load_raw(target)


def get_all_questions() -> list[Question]:
    """Return a flat list of all questions across every section.

    Returns:
        List of :class:`Question` objects in document order.
    """
    questionnaire = load_questionnaire()
    questions: list[Question] = []
    for section in questionnaire.sections:
        questions.extend(section.questions)
    return questions


def get_sections() -> list[QuestionSection]:
    """Return the list of question sections with questions grouped.

    Returns:
        List of :class:`QuestionSection` objects in document order.
    """
    questionnaire = load_questionnaire()
    return questionnaire.sections
