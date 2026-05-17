# UI Overview

The user interface is built with **Streamlit** and consists of four pages managed via `st.session_state.current_page`. The entry point is `app.py`.

## Pages

| Page | File | Route | Description |
|------|------|-------|-------------|
| Home | `ui/home.py` | `home` | Introduction, disclaimer, navigation |
| Questionnaire | `ui/questionnaire_ui.py` | `questionnaire` | CPS 230 assessment form |
| Report | `ui/report_ui.py` | `report` | Gap findings with CSV export |
| Admin | `ui/admin.py` | `admin` | Standards ingestion controls |

## Navigation

Navigation is handled through a sidebar selectbox:

```python
_pages = ["Home", "Questionnaire", "Gap Report", "Admin"]
_page_map = {
    "Home": "home",
    "Questionnaire": "questionnaire",
    "Gap Report": "report",
    "Admin": "admin",
}
```

The admin page can also be accessed via the URL parameter `?page=admin`.

## Session State

The app uses `st.session_state` for:

| Key | Type | Description |
|-----|------|-------------|
| `current_page` | `str` | Currently active page |
| `answers` | `dict[str, Any]` | User's questionnaire answers |

## Page Routing

In `app.py`, pages are routed based on `st.session_state.current_page`:

```python
if st.session_state.current_page == "home":
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
```

## Resource Initialization

The app initializes shared resources at the top level:

- **ChromaDB client** — `_init_chroma_client()` — Gracefully degrades if ChromaDB is unavailable
- **Gap rules** — `_load_gap_rules()` — Gracefully degrades if rules file is missing

## Configuration

Page configuration in `app.py`:

```python
st.set_page_config(
    page_title="Compliance Gap Analyser",
    page_icon="📊",
    layout="wide",
)
```

Version displayed in sidebar: `Compliance Gap Analyser v0.1.0`
