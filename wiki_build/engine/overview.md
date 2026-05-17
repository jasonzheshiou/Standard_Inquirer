# Engine Overview

The `engine` package contains the core analysis logic for the Compliance Gap Analyser. It is designed to be fully importable and testable without a running Streamlit instance.

## Package Structure

```
engine/
├── __init__.py          # Package init (empty)
├── schemas.py           # Pydantic data models
├── gap_analyzer.py      # Core gap analysis engine
└── questionnaire.py     # Questionnaire loading and management
```

## Modules

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `schemas` | Data model definitions | `GapRule`, `Question`, `GapFinding`, `Questionnaire`, `StandardsSource`, `Answer`, `QuestionSection` |
| `gap_analyzer` | Gap evaluation and analysis | `analyze()`, `evaluate_rule()`, `get_evidence_text()`, `load_gap_rules()` |
| `questionnaire` | Question loading and querying | `load_questionnaire()`, `get_all_questions()`, `get_sections()` |

## Design Principles

1. **Testability** — Core functions (`analyze()`, `evaluate_rule()`) accept plain dicts and return plain objects. No Streamlit dependency.
2. **Caching** — When Streamlit is available, loaders are decorated with `@st.cache_data` or `@st.cache_resource` for fast repeated calls.
3. **Graceful degradation** — If Streamlit is not installed, no-op decorators are used. If ChromaDB is unavailable, evidence retrieval returns an empty string.
4. **Severity ordering** — Findings are always sorted: high (0) → medium (1) → low (2).

## Dependencies

- `pydantic` — Data validation
- `streamlit` — Optional caching
- `config` — Application settings (singleton)
- `sentence-transformers` — Optional (ChromaDB evidence)
- `chromadb` — Optional (vector similarity search)
