# Home Page

The Home page (`ui/home.py`) is the landing page of the Compliance Gap Analyser. It presents the tool's purpose, a regulatory disclaimer, and navigation options.

## Function

### `render_home() -> None`

Render the home page with introduction and navigation buttons.

## Page Content

### Title

```
Life Insurance Compliance Gap Analyser
```

### Description

The page explains the tool's three-step workflow:

1. **Answer** each questionnaire section (boolean, multiple-choice, and text questions)
2. **Review** the gap analysis report with severity-ranked findings
3. **Export** findings as CSV for further analysis

### Disclaimer

A warning banner is displayed:

> ⚠️ **Disclaimer:** This tool provides sample guidance only. All rules and mitigations must be reviewed by a qualified actuary before being relied upon for regulatory compliance.

### Navigation Buttons

Two buttons are displayed side by side:

| Button | Action |
|--------|--------|
| **Begin Assessment** | Resets `st.session_state.answers` to `{}` and navigates to the Questionnaire page |
| **Load Previous Session** | Loads answers from `data/session.json` if it exists, then navigates to the Questionnaire page |

## Session Management

Previous sessions are stored in `data/session.json`:

```python
session_path = Path("data/session.json")
if session_path.exists():
    answers = json.loads(session_path.read_text(encoding="utf-8"))
    st.session_state.answers = answers
```

If no previous session exists, an info message is shown: "No previous session found."

## Code Structure

```python
def render_home() -> None:
    st.title("Life Insurance Compliance Gap Analyser")
    st.markdown("""...""")
    st.warning("⚠️ **Disclaimer:** ...")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Begin Assessment", ...):
            st.session_state.current_page = "questionnaire"
            st.session_state.answers = {}
            st.rerun()
    
    with col2:
        if session_path.exists() and st.button("Load Previous Session", ...):
            # Load from data/session.json
            ...
```
