"""Chat-based assessment page for the Compliance Gap Analyser.

Replaces the legacy Intake and Questionnaire pages with a pure
conversational flow — no intake form. The AI greets the user,
introduces itself, and asks about their needs organically.

The page has two states controlled by ``chat_initialised``:

    - ``False`` — AI greeting not yet sent (initialises on first load)
    - ``True``  — chat active, or extraction in progress

Rendered via ``render_assessment()`` and navigated to from the sidebar
or the home page.

"""

from __future__ import annotations

import logging
from typing import Any

import streamlit as st

from llm.chat_conductor import ChatConductor
from llm.client import LLMClient, LLMSettings

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

MAX_INPUT_LENGTH: int = 500

# ------------------------------------------------------------------
# Session state helpers
# ------------------------------------------------------------------


def _ensure_session_state() -> None:
    """Initialise all session-state keys used by the chat assessment page.

    Creates defaults for chat history, conductor instance, initialisation
    flag, organisation type, focus text, LLM settings, and extraction
    status.  Only sets keys that are not already present.
    """
    defaults: dict[str, Any] = {
        "chat_initialised": False,
        "chat_messages": [],
        "chat_conductor": None,
        "chat_org_type": "life_insurer",
        "chat_focus": "",
        "chat_assessment_ready": False,
        "assessment_questionnaire": None,
        "assessment_answers": None,
        "chat_model": "qwen/qwen3.6-35b-a3b",
        "chat_temperature": 0.3,
        "chat_extraction_status": "idle",
        "chat_extraction_error": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_chat() -> None:
    """Reset all chat session-state keys to their default values.

    Clears chat history, the conductor instance, initialisation flag,
    extraction state, and any stored questionnaire or answers.
    """
    st.session_state.chat_initialised = False
    st.session_state.chat_messages = []
    st.session_state.chat_conductor = None
    st.session_state.chat_org_type = "life_insurer"
    st.session_state.chat_focus = ""
    st.session_state.chat_assessment_ready = False
    st.session_state.assessment_questionnaire = None
    st.session_state.assessment_answers = None
    st.session_state.chat_extraction_status = "idle"
    st.session_state.chat_extraction_error = None
    st.session_state.answers = {}
    st.session_state.generated_questionnaire = None


# ------------------------------------------------------------------
# Conductor factory
# ------------------------------------------------------------------


def _create_conductor() -> ChatConductor:
    """Build a ``ChatConductor`` with custom LLM settings from user choices.

    Reads the model name and temperature from session state and creates
    an ``LLMClient`` with the configured endpoint.

    Returns:
        A configured ``ChatConductor`` instance.
    """
    custom_settings = LLMSettings(
        llm_base_url="http://192.168.1.59:1234/v1",
        llm_model=st.session_state.chat_model,
        llm_temperature=st.session_state.chat_temperature,
        llm_timeout=3600.0,
        llm_max_tokens=200000,
    )
    llm_client = LLMClient(settings=custom_settings)
    return ChatConductor(
        org_type=st.session_state.chat_org_type,
        focus=st.session_state.chat_focus,
        llm_client=llm_client,
    )


# ------------------------------------------------------------------
# Context extraction from conversation
# ------------------------------------------------------------------


def _extract_context_from_conversation(
    messages: list[dict[str, str]],
) -> tuple[str, str]:
    """Extract org_type and focus from conversation history.

    Scans user messages for keywords matching known organisation type
    codes and focus area descriptions.  Returns the detected org_type
    and focus as a tuple.

    Args:
        messages: List of chat message dicts with 'role' and 'content'.

    Returns:
        Tuple of (org_type, focus) detected from the conversation.
    """
    org_type = st.session_state.chat_org_type
    focus = st.session_state.chat_focus

    for msg in messages:
        if msg.get("role") != "user":
            continue
        text = msg.get("content", "").lower()

        for value, _label in ORG_TYPES:
            if value.replace("_", " ") in text:
                org_type = value
                break

        if not focus and text.strip():
            focus = text.strip()

    return (org_type, focus)


# ------------------------------------------------------------------
# Conversation lifecycle
# ------------------------------------------------------------------


def _initialise_conversation() -> None:
    """Create the conductor and send the AI's opening greeting.

    Builds a ``ChatConductor`` with the default org type, generates the
    initial greeting message, appends it to the chat history, and sets
    the initialisation flag.  Then triggers a rerun to display the
    greeting.
    """
    st.session_state.chat_conductor = _create_conductor()
    initial_message = st.session_state.chat_conductor.get_initial_message()
    st.session_state.chat_messages = [{"role": "assistant", "content": initial_message}]
    st.session_state.chat_initialised = True
    st.rerun()


def _handle_message(user_message: str) -> None:
    """Process a user message through the conductor and update state.

    Extracts org_type and focus from the conversation context, processes
    the message via the conductor, appends both user and AI messages to
    the history, and checks for the assessment-ready signal.

    Args:
        user_message: The user's input text to process.
    """
    # Update context from conversation
    org_type, focus = _extract_context_from_conversation(
        st.session_state.chat_messages,
    )
    if org_type != st.session_state.chat_org_type:
        st.session_state.chat_org_type = org_type
    if focus and not st.session_state.chat_focus:
        st.session_state.chat_focus = focus

    # Process via conductor (already appends user + assistant messages
    # to conductor._messages internally)
    conductor = st.session_state.chat_conductor
    ai_response, is_ready = conductor.process_user_message(user_message)

    # Sync chat_messages from conductor's authoritative message list
    st.session_state.chat_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in conductor.messages
    ]

    # Check if assessment is ready
    if is_ready:
        st.session_state.chat_assessment_ready = True

    st.rerun()


# ------------------------------------------------------------------
# Chat message renderer
# ------------------------------------------------------------------


def _render_chat_messages() -> None:
    """Render all chat messages with custom-styled chat bubbles.

    AI messages appear as light-grey bubbles aligned left.
    User messages appear as light-blue bubbles aligned right.
    Each uses st.chat_message with injected CSS for larger fonts.
    """
    for msg in st.session_state.chat_messages:
        role = msg.get("role", "assistant")
        content = msg.get("content", "")
        with st.chat_message(role):
            if role == "assistant":
                st.markdown(
                    '<div class="ai-message">' + content + "</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    '<div class="user-message">' + content + "</div>",
                    unsafe_allow_html=True,
                )


# ------------------------------------------------------------------
# Extraction renderer
# ------------------------------------------------------------------


def _render_extraction() -> None:
    """Render the extraction and transition state.

    When the user signals they are done, the assistant analyses the
    conversation and extracts structured data (questionnaire + answers).
    On success, provides a button to navigate to the compliance review.
    On failure, offers retry and start-over options.
    """
    st.success(
        "Thank you for the conversation! Let me prepare your compliance review..."
    )

    # -- Extraction phase --------------------------------------------------
    if st.session_state.chat_extraction_status == "idle":
        st.session_state.chat_extraction_status = "extracting"
        st.rerun()

    if st.session_state.chat_extraction_status == "extracting":
        with st.spinner("Analysing your responses and preparing the compliance review..."):
            try:
                conductor = st.session_state.chat_conductor
                questionnaire, answers = conductor.extract_structured_data()

                st.session_state.assessment_questionnaire = questionnaire.model_dump_json()
                st.session_state.assessment_answers = answers
                st.session_state.generated_questionnaire = questionnaire.model_dump_json()
                st.session_state.answers = answers
                st.session_state.chat_extraction_status = "done"
                st.rerun()
            except Exception as exc:
                logger.error("Extraction failed: %s", exc)
                st.session_state.chat_extraction_status = "error"
                st.session_state.chat_extraction_error = str(exc)
                st.rerun()

    if st.session_state.chat_extraction_status == "done":
        st.success("Your compliance review is ready!")

        if st.button("View Compliance Review", type="primary", use_container_width=True):
            st.session_state.current_page = "report"
            st.rerun()

        if st.button("Start New Assessment", use_container_width=True):
            _reset_chat()
            st.rerun()

    if st.session_state.chat_extraction_status == "error":
        err_msg: str = (
            st.session_state.chat_extraction_error
            or "An unknown error occurred."
        )
        st.error(f"Failed to prepare review: {err_msg}")

        if st.button("Try Again", use_container_width=True):
            st.session_state.chat_extraction_status = "idle"
            st.rerun()

        if st.button("Start Over", use_container_width=True):
            _reset_chat()
            st.rerun()


# ------------------------------------------------------------------
# Main render function
# ------------------------------------------------------------------


def _inject_chat_css() -> None:
    """Inject custom CSS for chat bubble styling.

    Styles AI messages (light grey, left-aligned) and user messages
    (light blue, right-aligned) with larger fonts.
    """
    st.markdown(
        """
<style>
.ai-message {
    font-size: 18px;
    line-height: 1.6;
    color: #1f1f1f;
    padding: 14px 18px;
    background-color: #f0f2f6;
    border-radius: 18px 18px 18px 4px;
    display: inline-block;
    max-width: 100%;
    margin-bottom: 8px;
}
.user-message {
    font-size: 17px;
    line-height: 1.6;
    color: #ffffff;
    padding: 14px 18px;
    background-color: #4a90d9;
    border-radius: 18px 18px 4px 18px;
    display: inline-block;
    max-width: 100%;
    margin-bottom: 8px;
}
.stChatMessageContainer {
    padding: 4px 0;
}
</style>
""",
        unsafe_allow_html=True,
    )


def _render_sidebar_controls() -> None:
    """Render action buttons in the sidebar below the chat."""
    with st.sidebar:
        st.divider()

        if st.button(
            "\U0001f4cb I'm Done \u2014 Generate My Report",
            type="primary",
            use_container_width=True,
        ):
            st.session_state.chat_assessment_ready = True
            st.rerun()

        if st.button("\U0001f501 Start Over", use_container_width=True, type="secondary"):
            _reset_chat()
            st.rerun()

        turn_count = sum(
            1 for m in st.session_state.chat_messages if m["role"] == "user"
        )
        st.caption(f"Turns: {turn_count}")


def render_assessment() -> None:
    """Render the chat-based compliance assessment page.

    Initialises session state and dispatches based on
    ``chat_initialised``:

        - ``False`` \u2192 initialise the conversation with an AI greeting
        - ``True``  \u2192 show chat messages, handle input, and display
          controls (or the extraction flow if the assessment is ready)
    """
    _ensure_session_state()

    # Inject custom chat CSS once
    _inject_chat_css()

    # Initialise AI greeting on first load
    if not st.session_state.chat_initialised:
        _initialise_conversation()
        return

    # Show chat messages
    _render_chat_messages()

    # Chat input with built-in green submit button
    user_input = st.chat_input(
        "Type your response...",
        max_chars=MAX_INPUT_LENGTH,
    )

    if user_input and user_input.strip():
        _handle_message(user_input.strip())
        return

    # Check if ready for extraction
    if st.session_state.chat_assessment_ready:
        _render_extraction()
        return

    # Sidebar controls
    _render_sidebar_controls()
