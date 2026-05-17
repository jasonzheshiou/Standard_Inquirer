"""Gap report page for the Compliance Gap Analyser.

Displays severity-ranked findings from the gap analysis engine,
with summary metrics, expandable detail rows, LLM-enriched
explanations, and CSV/JSON export.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

import streamlit as st

from engine.gap_analyzer import analyze
from engine.schemas import GapFinding
from llm.answer_analyzer import enrich_findings
from llm.client import LLMClient
from ui.questionnaire_ui import _load_questionnaire

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENRICHMENT_STATUS_KEY = "enrichment_status"
_ENRICHED_FINDINGS_KEY = "enriched_findings"
_LLM_AVAILABLE_KEY = "llm_available"


def _get_enrichment_status() -> str:
    """Return the current enrichment status from session state."""
    return st.session_state.get(_ENRICHMENT_STATUS_KEY, "idle")


def _set_enrichment_status(status: str) -> None:
    """Set the enrichment status in session state."""
    st.session_state[_ENRICHMENT_STATUS_KEY] = status


def _get_enriched_findings() -> list[GapFinding] | None:
    """Return previously enriched findings, or None."""
    return st.session_state.get(_ENRICHED_FINDINGS_KEY)  # type: ignore[return-value]


def _set_enriched_findings(findings: list[GapFinding] | None) -> None:
    """Store enriched findings in session state."""
    st.session_state[_ENRICHED_FINDINGS_KEY] = findings


def _is_llm_available() -> bool:
    """Check LLM availability and cache the result in session state."""
    if _LLM_AVAILABLE_KEY not in st.session_state:
        try:
            client = LLMClient()
            st.session_state[_LLM_AVAILABLE_KEY] = client.is_available()
        except Exception:
            st.session_state[_LLM_AVAILABLE_KEY] = False
    return st.session_state[_LLM_AVAILABLE_KEY]  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _render_finding_detail(f: GapFinding) -> None:
    """Render the expandable detail section for a single finding."""
    st.write(f"**Question:** {f.question}")
    st.write(f"**Your Answer:** {f.user_answer}")
    st.write(f"**Severity:** {f.gap_severity}")

    # Original mitigation (always shown)
    st.write(f"**Mitigation:** {f.mitigation}")

    # LLM explanation (if available)
    if f.llm_explanation:
        st.divider()
        st.markdown("**LLM Explanation:**")
        st.info(f.llm_explanation)

    # LLM mitigation (if available, alongside original)
    # We store LLM-generated mitigation in a separate attribute on the
    # GapFinding object at runtime (not a Pydantic field).
    llm_mitigation = getattr(f, "_llm_mitigation", None)
    if llm_mitigation:
        st.divider()
        st.markdown("**LLM Mitigation:**")
        st.success(llm_mitigation)

    # Evidence (if available)
    if f.evidence_text:
        st.divider()
        st.write(f"**Evidence:** {f.evidence_text}")

    # Source standard link (if available)
    source_standard = getattr(f, "_source_standard", None)
    source_clause = getattr(f, "_source_clause", None)
    if source_standard or source_clause:
        st.divider()
        link_label = source_clause or source_standard or ""
        link_url = "https://www.apra.gov.au/" if source_standard and "APRA" in source_standard else "#"
        st.markdown(f"**Source Standard:** [{link_label}]({link_url})")


def _export_csv(findings: list[GapFinding]) -> str:
    """Export findings to CSV format (original format, unchanged)."""
    csv_buffer = io.StringIO()
    writer = csv.DictWriter(
        csv_buffer,
        fieldnames=[
            "Requirement",
            "Clause",
            "Severity",
            "Question",
            "User Answer",
            "Mitigation",
            "Evidence",
        ],
    )
    writer.writeheader()
    for f in findings:
        writer.writerow({
            "Requirement": f.requirement_id,
            "Clause": f.clause_reference,
            "Severity": f.gap_severity,
            "Question": f.question,
            "User Answer": f.user_answer,
            "Mitigation": f.mitigation,
            "Evidence": f.evidence_text,
        })
    return csv_buffer.getvalue()


def _export_json_with_explanations(findings: list[GapFinding]) -> str:
    """Export findings to JSON format including LLM explanations."""
    export_data = []
    for f in findings:
        entry: dict[str, Any] = {
            "requirement_id": f.requirement_id,
            "clause_reference": f.clause_reference,
            "severity": f.gap_severity,
            "question": f.question,
            "user_answer": f.user_answer,
            "mitigation": f.mitigation,
            "evidence": f.evidence_text,
            "llm_explanation": f.llm_explanation,
        }
        # Include LLM mitigation if present
        llm_mitigation = getattr(f, "_llm_mitigation", None)
        if llm_mitigation:
            entry["llm_mitigation"] = llm_mitigation

        # Include source standard info if present
        source_standard = getattr(f, "_source_standard", None)
        source_clause = getattr(f, "_source_clause", None)
        if source_standard:
            entry["source_standard"] = source_standard
        if source_clause:
            entry["source_clause"] = source_clause

        export_data.append(entry)

    return json.dumps(export_data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main page renderer
# ---------------------------------------------------------------------------


def render_report() -> None:
    """Render the gap analysis report page.

    Calls the gap analysis engine with answers from
    ``st.session_state.answers`` and displays:
        - Summary metrics (total, high, medium, low severity counts)
        - A data table of all findings
        - Expandable rows with full details (including LLM enrichments)
        - CSV export button
        - "Export with Explanations" JSON export button
        - "Enrich with LLM" button for LLM-powered gap explanations
        - "New Assessment" button to reset and start over

    If no answers exist, shows a prompt to complete the questionnaire first.
    """
    st.title("Gap Analysis Report")

    answers = st.session_state.get("answers", {})

    if not answers:
        st.info("Please complete the questionnaire first.")
        if st.button("Go to Questionnaire", type="primary"):
            st.session_state.current_page = "questionnaire"
            st.rerun()
        return

    # Run analysis (with questionnaire for LLM gap analysis)
    llm_client = LLMClient() if _is_llm_available() else None
    questionnaire = _load_questionnaire()
    findings = analyze(answers, questionnaire=questionnaire, llm_client=llm_client)

    if not findings:
        st.success("No gaps identified. Your governance appears compliant with the assessed rules.")
    else:
        # Summary metrics
        total = len(findings)
        high_count = sum(1 for f in findings if f.gap_severity.lower() == "high")
        medium_count = sum(1 for f in findings if f.gap_severity.lower() == "medium")
        low_count = sum(1 for f in findings if f.gap_severity.lower() == "low")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Gaps", total)
        col2.metric("High", high_count, delta_color="inverse")
        col3.metric("Medium", medium_count)
        col4.metric("Low", low_count)

        st.divider()

        # ------------------------------------------------------------------
        # LLM Enrichment controls
        # ------------------------------------------------------------------
        enrich_status = _get_enrichment_status()
        enriched_findings = _get_enriched_findings()

        # Show enrichment status messages
        if enrich_status == "enriching":
            with st.spinner("Enriching findings with LLM explanations…"):
                pass
        elif enrich_status == "complete":
            st.success("Findings enriched with LLM explanations.")
        elif enrich_status == "error":
            st.error("LLM enrichment failed. Original mitigations are shown.")

        # "Enrich with LLM" button
        llm_available = _is_llm_available()

        with st.columns(2)[0]:
            if (
                st.button(
                    "Enrich with LLM",
                    type="primary",
                    disabled=not llm_available or enrich_status == "enriching",
                    use_container_width=True,
                )
                and llm_available
                and enrich_status not in ("enriching", "complete")
            ):
                _set_enrichment_status("enriching")
                st.rerun()

        # Handle enrichment action (after rerun)
        if enrich_status == "enriching" and llm_available:
            with st.spinner("Enriching findings with LLM explanations…"):
                try:
                    enriched = enrich_findings(findings, llm_client=LLMClient())
                    _set_enriched_findings(enriched)
                    _set_enrichment_status("complete")
                    st.rerun()
                except Exception as exc:
                    logger.warning("LLM enrichment failed: %s", exc)
                    _set_enrichment_status("error")
                    st.error(f"LLM enrichment failed: {exc}. Showing original mitigations.")

        # "Clear enrichment" button (when enriched)
        if enriched_findings and enrich_status == "complete":
            if st.button("Clear Enrichment", type="secondary", use_container_width=True):
                _set_enriched_findings(None)
                _set_enrichment_status("idle")
                st.rerun()

        st.divider()

        # ------------------------------------------------------------------
        # Findings table
        # ------------------------------------------------------------------
        st.subheader("Findings")

        rows = []
        for f in findings:
            rows.append({
                "Requirement": f.requirement_id,
                "Clause": f.clause_reference,
                "Severity": f.gap_severity,
                "Question": f.question,
                "Mitigation": f.mitigation,
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)

        # ------------------------------------------------------------------
        # Expandable detail rows
        # ------------------------------------------------------------------
        st.subheader("Detailed Findings")

        # Use enriched findings if available, fall back to original
        display_findings = enriched_findings if enriched_findings else findings

        for idx, f in enumerate(display_findings):
            with st.expander(f"[{f.gap_severity.upper()}] {f.requirement_id} — {f.clause_reference}"):
                _render_finding_detail(f)

        st.divider()

        # ------------------------------------------------------------------
        # Export buttons
        # ------------------------------------------------------------------
        col_csv, col_json = st.columns(2)

        with col_csv:
            csv_content = _export_csv(findings)
            st.download_button(
                label="Export CSV",
                data=csv_content,
                file_name="gap_report.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_json:
            json_content = _export_json_with_explanations(display_findings)
            st.download_button(
                label="Export with Explanations" if enriched_findings else "Export JSON",
                data=json_content,
                file_name="gap_report_with_explanations.json" if enriched_findings else "gap_report.json",
                mime="application/json",
                use_container_width=True,
            )

    st.divider()

    if st.button("New Assessment", type="secondary"):
        st.session_state.answers = {}
        st.session_state[_ENRICHMENT_STATUS_KEY] = "idle"
        st.session_state[_ENRICHED_FINDINGS_KEY] = None
        st.session_state[_LLM_AVAILABLE_KEY] = False
        st.session_state.current_page = "home"
        st.rerun()
