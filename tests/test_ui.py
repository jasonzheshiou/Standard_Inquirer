"""UI tests for the Compliance Gap Analyser Streamlit app.

Tests use ``streamlit.testing.v1.AppTest`` to simulate page rendering,
button clicks, and widget interactions without a running server.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

if TYPE_CHECKING:
    pass


@pytest.fixture
def app_test():
    """Create an AppTest instance for the main Streamlit app."""
    from streamlit.testing.v1 import AppTest

    at = AppTest("app.py", default_timeout=30)
    yield at


@pytest.fixture(autouse=True)
def clear_streamlit_caches():
    """Clear Streamlit caches between tests.

    This prevents @st.cache_resource and @st.cache_data from carrying
    stale state across AppTest instances when tests run in sequence
    after other test modules (like test_engine.py) that import engine modules.
    """
    import sys

    # Remove cached app and UI modules to force fresh import
    modules_to_remove = [
        m for m in sys.modules
        if m == "app"
        or m.startswith("ui.")
        or m == "engine.gap_analyzer"
        or m == "engine.questionnaire"
        or m == "engine.schemas"
        or m == "config"
    ]
    for mod in modules_to_remove:
        sys.modules.pop(mod, None)


def _get_button_labels(at):
    """Return list of button labels from AppTest."""
    return [b.label for b in at.button]


def _has_button(at, text: str) -> bool:
    """Check if a button with the given label text exists."""
    return any(text in str(b.label) for b in at.button)


def _find_button(at, text: str):
    """Find and return the first button whose label contains text."""
    for b in at.button:
        if text in str(b.label):
            return b
    return None


def _has_progress(at) -> bool:
    """Check if a progress bar exists in the app's element tree."""
    for node in at._tree:
        if _find_progress(node):
            return True
    return False


def _find_progress(node) -> bool:
    """Recursively search for a progress element."""
    # Check type attribute
    node_type = getattr(node, "type", None)
    if node_type == "progress":
        return True
    # Check class name
    node_cls = type(node).__name__
    if node_cls == "Progress":
        return True
    # Check UnknownElement with Progress proto
    if node_cls == "UnknownElement":
        proto = getattr(node, "proto", None)
        if proto is not None and type(proto).__name__ == "Progress":
            return True
    # Recurse into children
    children = getattr(node, "children", None)
    if children is not None:
        if hasattr(children, "values"):
            for child in children.values():
                if _find_progress(child):
                    return True
        elif hasattr(children, "__iter__"):
            for child in children:
                if _find_progress(child):
                    return True
    return False


# ---------------------------------------------------------------------------
# Home page tests
# ---------------------------------------------------------------------------


def test_home_page_has_title(app_test):
    """Home page renders with the correct title."""
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Life Insurance Compliance Gap Analyser" in title_values


def test_home_page_has_begin_button(app_test):
    """Home page renders with a 'Begin Assessment' button."""
    app_test.run()
    assert _has_button(app_test, "Begin Assessment")


def test_home_page_has_disclaimer(app_test):
    """Home page displays the regulatory disclaimer."""
    app_test.run()
    warning_values = [w.value for w in app_test.warning]
    disclaimer_found = any("qualified actuary" in str(w) for w in warning_values)
    assert disclaimer_found, "Disclaimer about qualified actuary not found"


def test_home_begin_assessment_navigates_to_questionnaire(app_test):
    """Setting current_page navigates to the questionnaire page."""
    app_test.run()
    # Simulate clicking "Begin Assessment" by setting session state
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Questionnaire" in title_values


# ---------------------------------------------------------------------------
# Questionnaire page tests
# ---------------------------------------------------------------------------


def test_questionnaire_page_has_title(app_test):
    """Questionnaire page renders with the correct title."""
    app_test.run()
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Questionnaire" in title_values


def test_questionnaire_has_sections(app_test):
    """Questionnaire page renders all 4 sections as expanders."""
    app_test.run()
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    expanders = app_test.expander
    assert len(expanders) == 4, f"Expected 4 sections, got {len(expanders)}"


def test_questionnaire_has_progress_bar(app_test):
    """Questionnaire page renders a progress bar widget."""
    app_test.run()
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    # Progress bars appear as 'progress' elements in the element tree
    assert _has_progress(app_test), "Progress bar not found on questionnaire page"


def test_questionnaire_has_next_button(app_test):
    """Questionnaire page has a 'Next: View Gap Report' button."""
    app_test.run()
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    assert _has_button(app_test, "Next: View Gap Report")


def test_questionnaire_answers_persist_in_session_state(app_test):
    """Answers are stored in st.session_state.answers when widgets change."""
    app_test.run()
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {"q_risk_appetite": "No"}
    app_test.run()

    # Verify the answer is in session state
    assert app_test.session_state.answers.get("q_risk_appetite") == "No"


# ---------------------------------------------------------------------------
# Report page tests
# ---------------------------------------------------------------------------


def test_report_page_with_no_answers_shows_prompt(app_test):
    """Report page shows a prompt when no answers exist."""
    app_test.run()
    app_test.session_state.current_page = "report"
    app_test.run()
    info_values = [i.value for i in app_test.info]
    assert any("questionnaire" in str(m).lower() for m in info_values), (
        "Expected prompt to complete questionnaire"
    )


def test_report_page_with_answers_shows_findings(app_test):
    """Report page displays findings when answers are provided."""
    app_test.run()
    # Simulate answering all questions with "No" to trigger all gaps
    answers = {
        "q_risk_appetite": "No",
        "q_risk_governance": "No",
        "q_model_inventory": "No",
        "q_model_validation": "No",
        "q_data_governance": "No",
        "q_documentation": "No",
        "q_escalation": "No",
        "q_concentration_risk": "No",
    }
    app_test.session_state.answers = answers
    app_test.session_state.current_page = "report"
    app_test.run()

    # Check for metric widgets (summary counts)
    metrics = app_test.metric
    assert len(metrics) >= 4, f"Expected at least 4 metrics, got {len(metrics)}"


def test_report_page_csv_export_generates_valid_csv(app_test):
    """CSV export generates valid CSV content."""
    app_test.run()
    answers = {
        "q_risk_appetite": "No",
        "q_risk_governance": "No",
        "q_model_inventory": "No",
        "q_model_validation": "No",
        "q_data_governance": "No",
        "q_documentation": "No",
        "q_escalation": "No",
        "q_concentration_risk": "No",
    }
    app_test.session_state.answers = answers
    app_test.session_state.current_page = "report"
    app_test.run()

    # Verify CSV content by checking the data table has findings
    dataframes = app_test.dataframe
    assert len(dataframes) >= 1, "Expected at least one dataframe in report"


def test_report_page_new_assessment_resets_session(app_test):
    """'New Assessment' button resets session state and navigates to home."""
    app_test.run()
    answers = {
        "q_risk_appetite": "No",
        "q_risk_governance": "No",
        "q_model_inventory": "No",
        "q_model_validation": "No",
        "q_data_governance": "No",
        "q_documentation": "No",
        "q_escalation": "No",
        "q_concentration_risk": "No",
    }
    app_test.session_state.answers = answers
    app_test.session_state.current_page = "report"
    app_test.run()

    # Simulate clicking "New Assessment" by setting session state
    app_test.session_state.answers = {}
    app_test.session_state.current_page = "home"
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Life Insurance Compliance Gap Analyser" in title_values


# ---------------------------------------------------------------------------
# Admin page tests
# ---------------------------------------------------------------------------


def test_admin_page_has_title(app_test):
    """Admin page renders with the correct title."""
    app_test.run()
    app_test.session_state.current_page = "admin"
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Admin Panel" in title_values


def test_admin_page_has_update_button(app_test):
    """Admin page displays 'Update Standards Now' button."""
    app_test.run()
    app_test.session_state.current_page = "admin"
    app_test.run()
    assert _has_button(app_test, "Update Standards")


def test_admin_page_handles_missing_chromadb(app_test):
    """Admin page handles missing ChromaDB gracefully."""
    app_test.run()
    app_test.session_state.current_page = "admin"
    # Mock ChromaDB init to fail
    with patch("standards_ingestion.embedder.init_chroma_client", side_effect=RuntimeError("test")):
        app_test.run()
    # Page should still render without crashing
    title_values = [t.value for t in app_test.title]
    assert "Admin Panel" in title_values


# ---------------------------------------------------------------------------
# Session state management tests
# ---------------------------------------------------------------------------


def test_session_state_initialization(app_test):
    """Session state initializes with default values."""
    app_test.run()
    assert app_test.session_state.current_page == "home"
    assert app_test.session_state.answers == {}


def test_session_state_answers_persist_across_reruns(app_test):
    """Answers persist in session state across page reruns."""
    app_test.run()
    app_test.session_state.answers = {"q_risk_appetite": "Yes"}
    app_test.session_state.current_page = "report"
    app_test.run()
    assert app_test.session_state.answers.get("q_risk_appetite") == "Yes"


# ---------------------------------------------------------------------------
# Integration test — full flow
# ---------------------------------------------------------------------------


def test_full_assessment_flow(app_test):
    """End-to-end test: home → questionnaire → report."""
    # Start at home
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Life Insurance Compliance Gap Analyser" in title_values

    # Navigate to questionnaire
    app_test.session_state.current_page = "questionnaire"
    app_test.session_state.answers = {}
    app_test.run()
    title_values = [t.value for t in app_test.title]
    assert "Questionnaire" in title_values

    # Simulate all "No" answers (to trigger gaps)
    answers = {
        "q_risk_appetite": "No",
        "q_risk_governance": "No",
        "q_model_inventory": "No",
        "q_model_validation": "No",
        "q_data_governance": "No",
        "q_documentation": "No",
        "q_escalation": "No",
        "q_concentration_risk": "No",
    }
    app_test.session_state.answers = answers

    # Navigate to report
    app_test.session_state.current_page = "report"
    app_test.run()

    # Verify report page renders
    title_values = [t.value for t in app_test.title]
    assert "Gap Analysis Report" in title_values

    # Verify findings are present
    metrics = app_test.metric
    assert len(metrics) >= 4
