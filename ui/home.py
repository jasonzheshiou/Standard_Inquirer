"""Home page for the Compliance Gap Analyser.

Displays an introduction, disclaimer, LLM status, navigation buttons
to begin a new assessment or load a previous session, and a list of
recent assessments.
"""

from __future__ import annotations

import json
import logging

import streamlit as st

from llm.client import LLMClient
from llm.session import delete_session, list_sessions, load_session

logger = logging.getLogger(__name__)


def _is_llm_available() -> bool:
    """Check whether the LLM server is reachable.

    Result is cached in ``st.session_state.llm_available`` to avoid
    repeated health-check requests on every rerun.
    """
    if "llm_available" not in st.session_state:
        try:
            llm = LLMClient()
            st.session_state.llm_available = llm.is_available()
        except Exception:
            st.session_state.llm_available = False
    return st.session_state.llm_available  # type: ignore[no-any-return]


def _render_llm_status() -> None:
    """Render an LLM availability indicator."""
    available = _is_llm_available()
    if available:
        st.success(
            "\U0001f916 **LLM Connected** — AI-powered questionnaire generation is enabled."
        )
    else:
        st.warning(
            "\U0001f50c **LLM Unavailable** — AI-powered features are currently "
            "unreachable. You can still use the default CPS 230 questionnaire."
        )


def _render_action_buttons() -> None:
    """Render the two primary action buttons."""
    col1, col2 = st.columns(2)

    with col1:
        if st.button(
            "\U0001f916 Start LLM-Powered Assessment",
            type="primary",
            use_container_width=True,
            disabled=not _is_llm_available(),
        ):
            st.session_state.current_page = "intake"
            st.session_state.intake_org_type = "life_insurer"
            st.session_state.generated_questionnaire = None
            st.session_state.answers = {}
            st.rerun()

    with col2:
        if st.button(
            "\u2699\ufe0f  Use Default CPS 230 Questionnaire",
            use_container_width=True,
            type="secondary",
        ):
            st.session_state.current_page = "intake"
            st.session_state.intake_org_type = "life_insurer"
            st.session_state.generated_questionnaire = None
            st.session_state.answers = {}
            st.rerun()


def _render_whats_new() -> None:
    """Render the 'What's New' section explaining LLM features."""
    with st.expander("\u2728 What's New in This Version", expanded=False):
        st.markdown(
            """
            This release adds **AI-powered compliance assessment** features:

            - **Free-text questionnaire generation** — Describe your compliance
              focus area and the LLM will generate a tailored questionnaire
              covering all relevant Australian Life Insurance Actuarial standards.

            - **Comprehensive standards coverage** — The LLM draws from a
              knowledge base spanning CPS, LPS, LRS, AASB, and other
              regulatory frameworks.

            - **LLM-enriched gap findings** — After answering the questionnaire,
              each gap finding can be enriched with AI-generated explanations
              and suggested mitigations for faster analysis.

            > **Note:** The LLM provides sample guidance only. All rules and
            > mitigations must be reviewed by a qualified actuary before
            > being relied upon for regulatory compliance.
            """
        )


def _render_recent_assessments() -> None:
    """Render the Recent Assessments section with resume and delete actions."""
    st.subheader("\U0001f4cb Recent Assessments")

    sessions = list_sessions()

    if not sessions:
        st.info("\U0001f4cc No previous assessments found. Start a new assessment to begin.")
        return

    st.caption(f"{len(sessions)} assessment{'s' if len(sessions) != 1 else ''} saved")

    for session in sessions:
        sid = session["id"]
        created = session.get("created_at") or "Unknown date"
        org_type = session.get("organization_type") or "Unknown"
        user_input = session.get("user_input") or ""

        # Format date for display
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(created)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            pass

        label = user_input[:60] + ("..." if len(user_input) > 60 else "") or f"{org_type} assessment"

        col_left, col_right = st.columns([4, 1])
        with col_left:
            if st.button(
                f"\U0001f4c4 Resume: {label}",
                key=f"resume_{sid}",
                use_container_width=True,
                type="secondary",
            ):
                try:
                    data = load_session(sid)
                    st.session_state.answers = data["answers"]
                    st.session_state.generated_questionnaire = (
                        data["questionnaire"].model_dump_json()
                        if hasattr(data["questionnaire"], "model_dump_json")
                        else json.dumps(data["questionnaire"])
                    )
                    st.session_state.current_page = "questionnaire"
                    st.rerun()
                except FileNotFoundError:
                    st.error(f"Session '{sid}' not found on disk.")
                except (ValueError, KeyError) as exc:
                    logger.error("Failed to load session %s: %s", sid, exc)
                    st.error(f"Could not load session '{sid}'. The file may be corrupted.")
                except Exception as exc:
                    logger.exception("Unexpected error loading session %s: %s", sid, exc)
                    st.error(f"Unexpected error loading session '{sid}'.")

        with col_right:
            if st.button(
                "\U0001f5d1\ufe0f",
                key=f"delete_{sid}",
                use_container_width=True,
                type="secondary",
                help=f"Delete assessment: {label}",
            ):
                if delete_session(sid):
                    st.success(f"Assessment '{label}' deleted.")
                    st.rerun()
                else:
                    st.warning(f"Could not delete session '{sid}'.")


def _render_load_previous_session() -> None:
    """Render the legacy 'Load Previous Session' dropdown for backwards compatibility."""
    st.subheader("\U0001f4e2 Load Previous Session")

    sessions = list_sessions()

    if not sessions:
        st.info("No previous sessions found.")
        return

    session_ids = [s["id"] for s in sessions]
    selected = st.selectbox(
        "Select a session to load",
        options=session_ids,
        format_func=lambda sid: (
            f"{sid} — {sessions[session_ids.index(sid)].get('created_at', 'Unknown')}"
        ),
        key="load_session_select",
    )

    if selected and st.button("Load Selected Session", type="primary", use_container_width=True):
        try:
            data = load_session(selected)
            st.session_state.answers = data["answers"]
            st.session_state.generated_questionnaire = (
                data["questionnaire"].model_dump_json()
                if hasattr(data["questionnaire"], "model_dump_json")
                else json.dumps(data["questionnaire"])
            )
            st.session_state.current_page = "questionnaire"
            st.rerun()
        except FileNotFoundError:
            st.error(f"Session '{selected}' not found on disk.")
        except (ValueError, KeyError) as exc:
            logger.error("Failed to load session %s: %s", selected, exc)
            st.error(f"Could not load session '{selected}'. The file may be corrupted.")
        except Exception as exc:
            logger.exception("Unexpected error loading session %s: %s", selected, exc)
            st.error(f"Unexpected error loading session '{selected}'.")


def render_home() -> None:
    """Render the home page with introduction and navigation buttons.

    The page presents the tool's purpose, an LLM status indicator,
    navigation options (LLM-powered or default questionnaire), a
    "What's New" section explaining AI features, a list of recent
    assessments, and a legacy session loader.
    """
    st.title("Life Insurance Compliance Gap Analyser")

    st.markdown(
        """
        This tool guides you through a **CPS 230** governance questionnaire
        and produces a gap analysis report identifying compliance deficiencies
        against regulatory requirements.

        ### How it works
        1. **Answer** each questionnaire section (boolean, multiple-choice, and text questions).
        2. **Review** the gap analysis report with severity-ranked findings.
        3. **Export** findings as CSV for further analysis.
        """
    )

    # -- LLM Status -----------------------------------------------------------
    st.divider()
    _render_llm_status()

    # -- Action Buttons -------------------------------------------------------
    st.divider()
    st.subheader("\U0001f680 Get Started")
    _render_action_buttons()

    # -- What's New -----------------------------------------------------------
    st.divider()
    _render_whats_new()

    # -- Recent Assessments ---------------------------------------------------
    st.divider()
    _render_recent_assessments()

    # -- Legacy Load Session --------------------------------------------------
    st.divider()
    _render_load_previous_session()

    # -- Disclaimer -----------------------------------------------------------
    st.divider()
    st.warning(
        "\u26a0\ufe0f **Disclaimer:** This tool provides sample guidance only. "
        "LLM-generated content is AI-assisted and may contain inaccuracies. "
        "All rules, mitigations, and gap findings must be reviewed by a "
        "qualified actuary before being relied upon for regulatory compliance."
    )
