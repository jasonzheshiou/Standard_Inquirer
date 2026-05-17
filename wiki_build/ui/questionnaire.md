# Questionnaire Page

The Questionnaire page (`ui/questionnaire_ui.py`) renders the CPS 230 governance assessment form with progress tracking.

## Function

### `render_questionnaire() -> None`

Render the questionnaire page with sections, widgets, and progress.

## Page Content

### Progress Tracking

A progress bar shows completion status:

```python
total_questions = len(all_questions)  # 8
answered_count = sum(1 for q in all_questions if q.id in st.session_state.answers)
progress = answered_count / total_questions
st.progress(progress)
st.caption(f"{answered_count} / {total_questions} questions answered")
```

### Section Rendering

Each section from the loaded questionnaire is displayed as an `st.expander`:

```python
sections = get_sections()
for section in sections:
    with st.expander(f"{section.title}", expanded=True):
        for question in section.questions:
            # Render appropriate widget based on question type
            ...
```

### Question Widgets

Widgets are rendered based on the question type:

| Type | Widget | Options |
|------|--------|---------|
| `boolean` | `st.radio` | "Yes", "No" |
| `multi_choice` | `st.radio` | From `question.options` |
| `text` (default) | `st.text_area` | Free text (80px height) |

### Answer Persistence

Answers are persisted via Streamlit callbacks:

```python
def _answer_callback(question_id: str) -> None:
    widget_value = st.session_state.get(f"ans_{question_id}")
    if widget_value is not None:
        st.session_state.answers[question_id] = widget_value
```

Each widget uses a unique key (`ans_{question_id}`) and triggers the callback on change.

### Navigation

A "Next: View Gap Report" button navigates to the Report page:

```python
if st.button("Next: View Gap Report", type="primary", ...):
    st.session_state.current_page = "report"
    st.rerun()
```

## Questionnaire Sections

### 1. Board & Senior Management Oversight
- `q_risk_appetite` — Board risk appetite statement
- `q_risk_governance` — Model risk governance framework

### 2. Model Inventory & Validation
- `q_model_inventory` — Comprehensive model inventory
- `q_model_validation` — Independent model validation

### 3. Data Governance
- `q_data_governance` — Data governance framework
- `q_documentation` — Model documentation standards

### 4. Risk Escalation & Reporting
- `q_escalation` — Model issue escalation process
- `q_concentration_risk` — Concentration risk assessment
