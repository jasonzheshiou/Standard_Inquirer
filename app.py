"""Streamlit entry point for the Compliance Gap Analyser.

Routes between five pages:
    - Intake — organisation type selector and questionnaire generation
    - Home — introduction and session management
    - Questionnaire — CPS 230 governance questions
    - Gap Report — severity-ranked findings
    - Admin — standards ingestion controls

Page navigation is managed via ``st.session_state.current_page``.
The admin page is accessible via sidebar toggle or the URL parameter
``?page=admin``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import streamlit as st

# Ensure the project root is on the path (for local dev)
_project_root = Path(__file__).parent.resolve()
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Compliance Gap Analyser",
    page_icon="📊",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if "current_page" not in st.session_state and "page" in st.query_params:
    st.session_state.current_page = st.query_params["page"]
if "current_page" not in st.session_state:
    st.session_state.current_page = "intake"
if "answers" not in st.session_state:
    st.session_state.answers = {}

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("Navigation")

    _pages = ["Intake", "Home", "Questionnaire", "Gap Report", "Admin", "Standards"]
    _page_map = {
        "Intake": "intake",
        "Home": "home",
        "Questionnaire": "questionnaire",
        "Gap Report": "report",
        "Admin": "admin",
        "Standards": "standards",
    }

    _current = st.session_state.current_page
    _initial_idx = 0
    for i, p in enumerate(_pages):
        if _page_map.get(p) == _current:
            _initial_idx = i
            break

    page = st.selectbox(
        "Go to:",
        _pages,
        index=_initial_idx,
        label_visibility="collapsed",
    )

    st.session_state.current_page = _page_map[page]

    st.divider()
    st.caption("Compliance Gap Analyser v0.1.0")

# ---------------------------------------------------------------------------
# Resource initialization
# ---------------------------------------------------------------------------


def _init_chroma_client():
    """Initialize the ChromaDB client."""
    try:
        from standards_ingestion.embedder import init_chroma_client

        return init_chroma_client()
    except Exception as exc:
        logger.warning("Could not initialize ChromaDB: %s", exc)
        return None


def _load_gap_rules():
    """Load gap rules."""
    try:
        from engine.gap_analyzer import load_gap_rules

        return load_gap_rules()
    except Exception as exc:
        logger.warning("Could not load gap rules: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Page routing
# ---------------------------------------------------------------------------

try:
    if st.session_state.current_page == "intake":
        from ui.questionnaire_intake import render_intake

        render_intake()

    elif st.session_state.current_page == "home":
        from ui.home import render_home

        render_home()

    elif st.session_state.current_page == "questionnaire":
        from ui.questionnaire_ui import render_questionnaire

        render_questionnaire()

    elif st.session_state.current_page == "report":
        from ui.report_ui import render_report

        render_report()

    elif st.session_state.current_page == "admin":
        from ui.admin import render_admin

        render_admin()

    elif st.session_state.current_page == "standards":
        from ui.standards_manager import render_standards_manager

        render_standards_manager()

    else:
        st.error(f"Unknown page: {st.session_state.current_page}")

except Exception as exc:  # pragma: no cover
    logger.exception("Error rendering page: %s", exc)
    st.error(f"An error occurred while rendering the page. Details: {exc}")
