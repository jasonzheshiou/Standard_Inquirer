"""Questionnaire intake page for the Compliance Gap Analyser.

Provides a guided form for users to specify their organisation type,
describe what they want to check, and trigger LLM-powered questionnaire
generation.

Rendered via ``render_intake()`` and navigated to from the sidebar or
the home page "Begin Assessment" button.
"""

from __future__ import annotations

import logging

import streamlit as st

from engine.schemas import Questionnaire
from llm.client import LLMClient
from llm.question_generator import QuestionGenerationError, _check_chromadb_status, generate_questionnaire

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constants
# ------------------------------------------------------------------

ORG_TYPES: list[tuple[str, str]] = [
    ("life_insurer", "Life Insurer"),
    ("life_reinsurer", "Life Reinsurer"),
    ("friendly_society", "Friendly Society"),
    ("superannuation_fund", "Superannuation Fund"),
    ("other", "Other"),
]

EXAMPLE_PROMPTS: list[str] = [
    "Check my capital adequacy compliance",
    "AASB 17 readiness assessment",
    "CPS 320 actuarial compliance",
    "Reinsurance risk management review",
    "Operational risk framework gap analysis",
    "LPS 115 insurance risk charge verification",
]

MAX_INPUT_LENGTH: int = 500

# ------------------------------------------------------------------
# Session state helpers
# ------------------------------------------------------------------


def _ensure_session_state() -> None:
    """Initialise all session-state keys used by the intake page."""
    defaults = {
        "intake_org_type": "life_insurer",
        "intake_user_input": "",
        "intake_advanced_open": False,
        "intake_model": "qwen/qwen3.6-35b-a3b",
        "intake_temperature": 0.3,
        "generated_questionnaire": None,
        "intake_status": "idle",
        "intake_error": None,
        "intake_standards_preview": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ------------------------------------------------------------------
# UI helpers
# ------------------------------------------------------------------


def _render_org_type_selector() -> None:
    """Render the organisation-type radio selector."""
    st.subheader("1. What type of organisation are you?")

    selected = st.radio(
        "Organisation type",
        options=[label for _, label in ORG_TYPES],
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        help="Select the category that best describes your organisation.",
    )

    # Map display label back to value
    for value, label in ORG_TYPES:
        if label == selected:
            st.session_state.intake_org_type = value
            break


def _render_user_input() -> None:
    """Render the free-text input area with example chips."""
    st.subheader("2. What would you like to check?")

    current: str = st.session_state.intake_user_input  # type: ignore[assignment]

    # Example prompt chips
    st.caption("**Try an example:**")
    cols = st.columns(min(3, len(EXAMPLE_PROMPTS)))
    for i, prompt in enumerate(EXAMPLE_PROMPTS):
        with cols[i % 3]:
            if st.button(prompt, key=f"chip_{i}", use_container_width=True, type="secondary"):
                st.session_state.intake_user_input = prompt
                st.rerun()

    placeholder_text = "e.g. 'Check my capital adequacy compliance', 'AASB 17 readiness assessment', 'CPS 320 actuarial compliance'"
    st.text_area(
        "Describe your compliance focus",
        value=current,
        placeholder=placeholder_text,
        max_chars=MAX_INPUT_LENGTH,
        height=100,
        key="intake_user_input",
        label_visibility="collapsed",
        help=f"Describe what you'd like the questionnaire to cover. Maximum {MAX_INPUT_LENGTH} characters.",
    )
    current_length: int = len(current)  # type: ignore[assignment]
    st.caption(f"{current_length} / {MAX_INPUT_LENGTH} characters")


def _render_advanced_options() -> None:
    """Render the advanced LLM options expander."""
    with st.expander("Advanced options", expanded=False):
        model_val: str = st.session_state.intake_model  # type: ignore[assignment]
        st.text_input(
            "LLM Model",
            value=model_val,
            key="intake_model",
            help="The model identifier to use for questionnaire generation.",
        )
        temp_val: float = float(st.session_state.intake_temperature)  # type: ignore[assignment]
        st.slider(
            "Temperature",
            min_value=0.0,
            max_value=1.0,
            value=temp_val,
            step=0.05,
            key="intake_temperature",
            help="Controls randomness: 0 = deterministic, 1 = creative.",
        )


def _render_loading() -> None:
    """Show a loading spinner while the LLM generates the questionnaire."""
    st.info("Generating your compliance questionnaire ...")
    st.spinner("This may take a moment as the LLM retrieves relevant standards and builds your questionnaire.")


def _render_success(questionnaire: Questionnaire) -> None:
    """Render a success message with standards preview and generation details."""
    st.success("Questionnaire generated successfully!")

    total_questions = sum(len(s.questions) for s in questionnaire.sections)
    gen_at = questionnaire.generated_at or "just now"
    st.caption(f"{len(questionnaire.sections)} sections · {total_questions} questions · Generated {gen_at}")

    # Generation details
    llm_called = st.session_state.get("gen_llm_called", False)
    chromadb_docs = st.session_state.get("gen_chromadb_docs", 0)
    standards_retrieved = st.session_state.get("gen_standards_retrieved", 0)
    fallback_used = st.session_state.get("gen_fallback_used", False)

    with st.expander("⚙️  Generation Details", expanded=False):
        st.write(f"**ChromaDB documents:** {chromadb_docs}")
        st.write(f"**Standards retrieved:** {standards_retrieved}")
        if llm_called:
            st.success("✅ LLM was called — questionnaire generated from your input + regulatory standards")
        elif fallback_used:
            st.warning("⚠️  LLM was unavailable — using default questionnaire (your input stored in metadata)")
        else:
            st.warning("⚠️  ChromaDB was empty — no regulatory context available. Go to Standards page → 'Populate ChromaDB'")

    # Standards preview
    standards_preview: list[str] = []
    for section in questionnaire.sections:
        for question in section.questions:
            if question.source_standard and question.source_standard not in standards_preview:
                standards_preview.append(question.source_standard)

    if standards_preview:
        with st.expander("Relevant standards included", expanded=True):
            for std in standards_preview[:10]:  # cap display
                st.caption(f"• {std}")
            if len(standards_preview) > 10:
                st.caption(f"… and {len(standards_preview) - 10} more")

    _, col2 = st.columns([1, 2])
    with col2:
        if st.button("Review Questionnaire", type="primary", use_container_width=True):
            st.session_state.current_page = "questionnaire"
            st.rerun()

    _, col2 = st.columns([1, 2])
    with col2:
        if st.button("Start Fresh", use_container_width=True):
            st.session_state.current_page = "home"
            st.rerun()


def _render_error(message: str) -> None:
    """Render an error state with fallback options."""
    st.error(f"Generation failed: {message}")

    st.warning("You can still proceed with a default questionnaire:")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Use default CPS 230 questionnaire", use_container_width=True, type="primary"):
            st.session_state.intake_status = "idle"
            st.session_state.intake_error = None
            # Generate fallback directly
            try:
                # ruff: noqa: SLF001 -- intentional access to private fallback function
                from llm.question_generator import _default_questionnaire

                org_type: str = st.session_state.intake_org_type  # type: ignore[assignment]
                user_input: str | None = st.session_state.intake_user_input  # type: ignore[assignment]
                fallback = _default_questionnaire(org_type, user_input)
                st.session_state.generated_questionnaire = fallback.model_dump_json()
                st.session_state.current_page = "questionnaire"
                st.rerun()
            except Exception as exc:
                logger.error("Fallback questionnaire generation failed: %s", exc)
                st.error("Could not load default questionnaire. Please try again.")
    with col2:
        if st.button("Edit input & try again", use_container_width=True):
            st.session_state.intake_status = "idle"
            st.session_state.intake_error = None
            st.rerun()


def _render_fallback_prompt() -> None:
    """Render a fallback prompt when no questionnaire has been generated."""
    tip_text = "Click any example chip above to auto-fill your input, or type your own compliance focus area."
    st.info(f"\U0001f4a1 **Tip:** {tip_text}")


# ------------------------------------------------------------------
# Main render function
# ------------------------------------------------------------------


def render_intake() -> None:
    """Render the questionnaire intake page.

    The page guides users through three steps:

        1. Select their **organisation type** (radio buttons).
        2. Describe what they want to check (free-text input with chips).
        3. Click **Generate Questionnaire** to trigger LLM-powered generation.

    After generation the user is navigated to the questionnaire page.
    On failure, fallback options are presented.
    """
    _ensure_session_state()

    st.title("New Compliance Assessment")

    st.markdown(
        "Answer a few quick questions and the LLM will generate a "
        "**tailored compliance questionnaire** based on your organisation "
        "type and regulatory requirements."
    )

    st.divider()

    # -- Step 1: Organisation type -----------------------------------------
    _render_org_type_selector()

    # -- Step 2: User input --------------------------------------------------
    _render_user_input()

    # -- Advanced options ----------------------------------------------------
    _render_advanced_options()

    # -- Status rendering ----------------------------------------------------
    status: str = st.session_state.intake_status  # type: ignore[assignment]

    if status == "generating":
        st.divider()
        _render_loading()

    elif status == "success" and st.session_state.generated_questionnaire:
        st.divider()
        try:
            gen_q: str = st.session_state.generated_questionnaire  # type: ignore[assignment]
            questionnaire = Questionnaire.model_validate_json(gen_q)
            _render_success(questionnaire)
        except Exception:
            logger.exception("Failed to parse generated questionnaire JSON")
            st.session_state.intake_status = "error"
            st.session_state.intake_error = "Generated questionnaire could not be parsed."

    elif status == "error":
        st.divider()
        err_msg: str = st.session_state.intake_error or "An unknown error occurred."  # type: ignore[assignment]
        _render_error(err_msg)

    else:
        # Idle state \u2014 show tip
        _render_fallback_prompt()

    # -- Generate button (always at bottom) ----------------------------------
    st.divider()

    user_input: str = st.session_state.intake_user_input.strip()  # type: ignore[assignment]
    disabled = not user_input

    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        generated = st.button(
            "Generate Questionnaire",
            type="primary",
            use_container_width=True,
            disabled=disabled,
        )

    if generated and not disabled:
        st.session_state.intake_status = "generating"

        # Build LLM client from user settings
        try:
            from llm.client import LLMSettings
            model_val: str = st.session_state.intake_model  # type: ignore[assignment]
            temp_val: float = float(st.session_state.intake_temperature)  # type: ignore[assignment]
            custom_settings = LLMSettings(
                llm_base_url="http://192.168.1.59:1234/v1",
                llm_model=model_val,
                llm_temperature=temp_val,
                llm_timeout=3600.0,  # 1 hour — 35B model on CPU can take minutes
                llm_max_tokens=200000,  # increased — prompt is ~4000 tokens, need room for full JSON response
            )
            llm_client = LLMClient(settings=custom_settings)
        except Exception as exc:
            logger.error("Failed to create LLM client: %s", exc)
            st.session_state.intake_status = "error"
            st.session_state.intake_error = "Could not initialise the LLM client. Please check your configuration."
            st.rerun()

        try:
            org_type: str = st.session_state.intake_org_type  # type: ignore[assignment]
            questionnaire = generate_questionnaire(
                user_input=user_input,
                organization_type=org_type,
                llm_client=llm_client,
            )

            # Track generation details for UI feedback
            has_docs, doc_count = _check_chromadb_status()
            st.session_state.gen_llm_called = True
            st.session_state.gen_chromadb_docs = doc_count
            st.session_state.gen_standards_retrieved = len(questionnaire.sections)
            st.session_state.gen_fallback_used = False

            # Persist the generated questionnaire
            st.session_state.generated_questionnaire = questionnaire.model_dump_json()
            st.session_state.intake_status = "success"
            st.session_state.intake_error = None
            st.session_state.intake_standards_preview = [
                q.source_standard
                for s in questionnaire.sections
                for q in s.questions
                if q.source_standard
            ]

            logger.info(
                "Questionnaire generated: %d sections, %d questions for '%s'",
                len(questionnaire.sections),
                sum(len(s.questions) for s in questionnaire.sections),
                org_type,
            )

            # Navigate to questionnaire page
            st.session_state.current_page = "questionnaire"
            st.rerun()

        except QuestionGenerationError as exc:
            logger.warning("Question generation failed: %s", exc)
            st.session_state.intake_status = "error"
            st.session_state.intake_error = str(exc)

        except Exception as exc:
            logger.exception("Unexpected error during questionnaire generation")
            st.session_state.intake_status = "error"
            st.session_state.intake_error = f"An unexpected error occurred: {exc}"

        finally:
            st.rerun()
