# Report Page

The Report page (`ui/report_ui.py`) displays severity-ranked findings from the gap analysis engine, with summary metrics and CSV export.

## Function

### `render_report() -> None`

Render the gap analysis report page.

## Page Content

### Empty State

If no answers exist, a prompt is shown:

```python
if not answers:
    st.info("Please complete the questionnaire first.")
    if st.button("Go to Questionnaire", type="primary"):
        st.session_state.current_page = "questionnaire"
        st.rerun()
    return
```

### Success State

If no gaps are identified:

```python
if not findings:
    st.success("No gaps identified. Your governance appears compliant with the assessed rules.")
```

### Summary Metrics

When gaps are found, four metric cards display:

| Metric | Description |
|--------|-------------|
| Total Gaps | Total number of findings |
| High | Count of high-severity findings (inverse delta color) |
| Medium | Count of medium-severity findings |
| Low | Count of low-severity findings |

### Findings Table

A data table displays all findings:

| Column | Source |
|--------|--------|
| Requirement | `f.requirement_id` |
| Clause | `f.clause_reference` |
| Severity | `f.gap_severity` |
| Question | `f.question` |
| Mitigation | `f.mitigation` |

```python
st.dataframe(rows, use_container_width=True, hide_index=True)
```

### Detailed Findings

Expandable rows show full details for each finding:

```python
for f in findings:
    with st.expander(f"[{f.gap_severity.upper()}] {f.requirement_id} — {f.clause_reference}"):
        st.write(f"**Question:** {f.question}")
        st.write(f"**Your Answer:** {f.user_answer}")
        st.write(f"**Severity:** {f.gap_severity}")
        st.write(f"**Mitigation:** {f.mitigation}")
        if f.evidence_text:
            st.write(f"**Evidence:** {f.evidence_text}")
```

### CSV Export

A download button exports findings to CSV:

```python
st.download_button(
    label="Export CSV",
    data=csv_content,
    file_name="gap_report.csv",
    mime="text/csv",
    use_container_width=True,
)
```

CSV columns: Requirement, Clause, Severity, Question, User Answer, Mitigation, Evidence

### Reset

A "New Assessment" button resets all answers and returns to the Home page:

```python
if st.button("New Assessment", type="secondary"):
    st.session_state.answers = {}
    st.session_state.current_page = "home"
    st.rerun()
```

## Analysis Flow

```
st.session_state.answers
       │
       ▼
analyze(answers) → list[GapFinding]
       │
       ▼
Summary metrics (total, high, medium, low)
       │
       ▼
Findings data table
       │
       ▼
Expandable detail rows
       │
       ▼
CSV export button
```
