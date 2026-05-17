"""Questionnaire page for the Compliance Gap Analyser.

Renders the CPS 230 questionnaire sections with appropriate input widgets,
tracks answers in ``st.session_state.answers``, and displays a progress bar.

Supports both static (JSON-file) and dynamic (LLM-generated) questionnaires.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, cast

import streamlit as st

from engine.schemas import Question, Questionnaire

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Session state helpers
# ------------------------------------------------------------------


def _ensure_questionnaire_session_state() -> None:
    """Initialise session-state keys used by the questionnaire page."""
    defaults = {
        "answers": {},
        "generated_questionnaire": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _prepopulate_answers(questionnaire: Questionnaire) -> None:
    """Pre-populate st.session_state.answers with default values for all questions.

    This ensures that boolean and multi_choice questions have their default
    values captured even if the user never changes from the default selection.
    Without this, the on_change callback never fires for unchanging widgets,
    and the LLM receives empty strings for those answers.

    Only sets values that are not already present in st.session_state.answers.

    Args:
        questionnaire: The loaded questionnaire with all questions.
    """
    if "answers" not in st.session_state:
        st.session_state.answers = {}

    for section in questionnaire.sections:
        for question in section.questions:
            if question.id in st.session_state.answers:
                continue  # Already answered, don't overwrite

            if question.type == "boolean":
                default = question.default or "Yes"
                st.session_state.answers[question.id] = default
            elif question.type == "multi_choice" and question.options:
                default = question.default or question.options[0]
                st.session_state.answers[question.id] = default
            else:
                # Text questions: default is empty string
                default = question.default or ""
                st.session_state.answers[question.id] = default


# ------------------------------------------------------------------
# Questionnaire loader (dynamic-first)
# ------------------------------------------------------------------


def _load_questionnaire() -> Questionnaire | None:
    """Load a questionnaire — dynamic first, then static fallback.

    Checks ``st.session_state.generated_questionnaire`` (a JSON string)
    first.  If present, parses and returns it.  Otherwise falls back
    to the static ``load_questionnaire()`` from ``engine.questionnaire``.

    Returns:
        A validated :class:`Questionnaire`, or ``None`` on failure.
    """
    # -- Dynamic (LLM-generated) -------------------------------------------
    gen_q = st.session_state.get("generated_questionnaire")
    if gen_q:
        try:
            if isinstance(gen_q, str):
                return Questionnaire.model_validate_json(gen_q)
            # Already a dict (edge-case from direct assignment)
            return Questionnaire.model_validate(gen_q)
        except Exception as exc:
            logger.warning("Failed to parse generated questionnaire: %s", exc)
            st.session_state.generated_questionnaire = None
            # Fall through to static

    # -- Static (JSON file) fallback ---------------------------------------
    try:
        from engine.questionnaire import load_questionnaire as _static_load

        return _static_load()
    except Exception as exc:
        logger.error("Static questionnaire load failed: %s", exc)
        return None


def _is_generated() -> bool:
    """Return ``True`` when a dynamic questionnaire is active."""
    return st.session_state.get("generated_questionnaire") is not None


# ------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------


def _render_source_badges(question: Question) -> None:
    """Render source_standard / source_clause badges for a question.

    Each badge is clickable and opens the relevant standard clause
    excerpt from ChromaDB (via a st.popover).

    Args:
        question: A :class:`Question` instance.
    """
    source_standard: str | None = question.source_standard
    source_clause: str | None = question.source_clause

    if not source_standard and not source_clause:
        return

    # Build a compact display label
    label = source_standard or ""
    if source_clause:
        label += f" \u00b7 {source_clause}"

    if not label:
        return

    # Clickable badge using a popover for the clause detail
    with st.popover(f":blue[{label}]"):
        if source_standard:
            st.caption("**Standard**")
            st.text(source_standard)
        if source_clause:
            st.caption("**Clause**")
            st.text(source_clause)
        # Confidence indicator
        confidence: float | None = question.confidence
        if confidence is not None:
            st.progress(confidence)


def _render_question(question: Question) -> None:
    """Render a single question with its input widget.

    Args:
        question: A :class:`Question` instance.
    """
    key = f"ans_{question.id}"

    # Source badges
    _render_source_badges(question)

    # Question text
    question_text: str = question.text

    if question.type == "boolean":
        default = question.default or "Yes"
        st.radio(
            question_text,
            options=["Yes", "No"],
            index=0 if default == "Yes" else 1,
            key=key,
            on_change=_answer_callback,
            args=(question.id,),
            horizontal=True,
        )

    elif question.type == "multi_choice" and question.options:
        default = question.default or question.options[0]
        st.radio(
            question_text,
            options=question.options,
            index=question.options.index(default) if default in question.options else 0,
            key=key,
            on_change=_answer_callback,
            args=(question.id,),
            horizontal=True,
        )

    else:
        # Treat as text
        default = question.default or ""
        st.text_area(
            question_text,
            value=default,
            key=key,
            on_change=_answer_callback,
            args=(question.id,),
            height=80,
        )


def _render_dynamic_header(questionnaire: Questionnaire) -> None:
    """Render header for a dynamically-generated questionnaire."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:8px;margin-bottom:4px;'>"
        "<span style='font-size:0.85em;color:#6c757d;'>Generated by LLM</span>"
        "<span style='background:#e8f5e9;color:#2e7d32;padding:2px 8px;border-radius:10px;font-size:0.75em;'>LLM</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    org_type: str | None = questionnaire.organization_type
    user_input: str | None = questionnaire.user_input
    gen_at: str | None = questionnaire.generated_at

    meta_parts = []
    if org_type:
        meta_parts.append(f"Org type: {org_type}")
    if gen_at:
        try:
            dt = datetime.fromisoformat(gen_at)
            meta_parts.append(f"Generated {dt.strftime('%Y-%m-%d %H:%M')}")
        except (ValueError, TypeError):
            meta_parts.append(f"Generated {gen_at}")

    if meta_parts:
        st.caption(" \u00b7 ".join(meta_parts))  # noqa: ISC001

    if user_input:
        st.caption(f"Focus: {user_input}")


def _render_static_header() -> None:
    """Render header for the static (default) questionnaire."""
    st.caption("Default CPS 230 compliance questionnaire")


def _render_action_buttons() -> None:
    """Render Regenerate and Export buttons."""
    st.divider()
    col1, col2 = st.columns([1, 1])

    # Regenerate button (dynamic only)
    with col1:
        if _is_generated():
            if st.button("Regenerate Questionnaire", use_container_width=True, type="secondary"):
                st.session_state.answers = {}
                st.session_state.generated_questionnaire = None
                st.session_state.current_page = "intake"
                st.rerun()

    # Export button (dynamic only)
    with col2:
        if _is_generated():
            if st.button("Export Questionnaire", use_container_width=True, type="secondary"):
                _export_questionnaire()


def _export_questionnaire() -> None:
    """Export the current questionnaire as a downloadable JSON file."""
    gen_q = st.session_state.get("generated_questionnaire")
    if not gen_q:
        return

    try:
        if isinstance(gen_q, str):
            data = json.loads(gen_q)
        else:
            data = gen_q

        # Build a serialisable dict
        export_data = {
            "sections": [],
            "generated_by": getattr(data, "generated_by", "llm") if isinstance(data, dict) else None,
            "generated_at": getattr(data, "generated_at", None),
            "organization_type": getattr(data, "organization_type", None),
            "user_input": getattr(data, "user_input", None),
        }

        # Handle both dict and model instances
        if isinstance(data, dict):
            export_data["generated_by"] = data.get("generated_by")
            export_data["generated_at"] = data.get("generated_at")
            export_data["organization_type"] = data.get("organization_type")
            export_data["user_input"] = data.get("user_input")
            _raw: Any = data.get("sections")
        else:
            _raw = getattr(data, "sections", None)

        if _raw is None:
            _raw = []

        _process_sections(cast("list[Any]", _raw), cast("list[Any]", export_data["sections"]))

        json_str = json.dumps(export_data, indent=2, default=str)

        st.download_button(
            label="Download JSON",
            data=json_str,
            file_name="questionnaire.json",
            mime="application/json",
        )
    except Exception as exc:
        logger.error("Export failed: %s", exc)
        st.error("Failed to export questionnaire.")


# ------------------------------------------------------------------
# Section processing helper
# ------------------------------------------------------------------


def _process_sections(sections: list[Any], dest: list[Any]) -> None:
    """Append section dicts to the destination list.

    Handles both dict-based and model-based section objects.

    Args:
        sections: List of section objects or dicts.
        dest: Destination list to append to.
    """
    for section in sections:
        if isinstance(section, dict):
            dest.append({
                "title": section.get("title", ""),
                "questions": section.get("questions", []),
            })
        else:
            dest.append({
                "title": getattr(section, "title", ""),
                "questions": [
                    {k: getattr(q, k) for k in q.model_fields} if hasattr(q, "model_fields") else q
                    for q in getattr(section, "questions", [])
                ],
            })


# ------------------------------------------------------------------
# Answer callback
# ------------------------------------------------------------------


def _answer_callback(question_id: str) -> None:
    """Streamlit on_change callback to persist a question answer.

    Reads the current widget value and stores it in
    ``st.session_state.answers`` keyed by the question ID.

    Args:
        question_id: The unique identifier of the answered question.
    """
    widget_value = st.session_state.get(f"ans_{question_id}")
    if widget_value is not None:
        st.session_state.answers[question_id] = widget_value


# ------------------------------------------------------------------
# Main render function
# ------------------------------------------------------------------


def render_questionnaire() -> None:
    """Render the questionnaire page with sections, widgets, and progress.

    Checks for a dynamically-generated questionnaire in session state
    first.  If none exists, falls back to the static CPS 230
    questionnaire loaded from the project's JSON data file.

    Each section is displayed as an ``st.expander``.  Questions are
    rendered with appropriate input widgets based on their type
    (boolean, multi_choice, or text).

    Answers are persisted in ``st.session_state.answers`` and a
    progress bar shows completion status.  A "Next: View Gap Report"
    button navigates to the report page when clicked.
    """
    _ensure_questionnaire_session_state()

    # Load questionnaire (dynamic-first, static fallback)
    questionnaire = _load_questionnaire()

    if questionnaire is None:
        st.error("No questionnaire available. Please go back and generate or select one.")
        if st.button("Go to Intake", type="primary"):
            st.session_state.current_page = "intake"
            st.rerun()
        return

    # Pre-populate answers with default values (so unchanging selections are captured)
    _prepopulate_answers(questionnaire)

    # Determine source and render header
    if _is_generated():
        _render_dynamic_header(questionnaire)
    else:
        _render_static_header()

    st.title("Questionnaire")

    # Sections from the loaded questionnaire
    sections = questionnaire.sections
    all_questions: list[Question] = []
    for section in sections:
        all_questions.extend(section.questions)

    total_questions = len(all_questions)
    answered_count = sum(1 for q in all_questions if q.id in st.session_state.answers)

    # Progress bar
    progress = answered_count / total_questions if total_questions else 0.0
    st.progress(progress)
    st.caption(f"{answered_count} / {total_questions} questions answered")

    # Render each section
    for section in sections:
        with st.expander(f"{section.title}", expanded=True):
            for question in section.questions:
                _render_question(question)

    # Action buttons
    _render_action_buttons()

    # Navigation to gap report
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Next: View Gap Report", type="primary", use_container_width=True):
            st.session_state.current_page = "report"
            st.rerun()
