# Architecture

This document describes the system architecture and data flow of the Compliance Gap Analyser.

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                     Streamlit UI                         │
│  ┌──────────┬──────────────┬───────────┬─────────────┐  │
│  │  Home    │ Questionnaire│  Report   │    Admin    │  │
│  └──────────┴──────────────┴───────────┴─────────────┘  │
└──────────────────────────┬──────────────────────────────┘
                           │ st.session_state.answers
                           ▼
┌─────────────────────────────────────────────────────────┐
│                    Engine Layer                          │
│  ┌──────────────┐  ┌──────────────────┐                 │
│  │ gap_analyzer │  │  questionnaire   │                 │
│  │  .analyze()  │  │  .get_sections() │                 │
│  └──────┬───────┘  └──────────────────┘                 │
│         │                                                │
│         ▼                                                │
│  ┌──────────────────┐                                   │
│  │     schemas      │  (GapRule, Question, GapFinding)  │
│  └──────────────────┘                                   │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│                  Data Layer                              │
│  ┌───────────────┐  ┌──────────────────┐                │
│  │ gap_rules.json│  │ questionnaire.json│               │
│  └───────────────┘  └──────────────────┘                │
│  ┌──────────────────────────────────────────┐           │
│  │         ChromaDB (data/chroma_db)        │           │
│  │   ┌──────────────────────────────────┐   │           │
│  │   │  standards_collection            │   │           │
│  │   │  (embedded regulatory PDF chunks)│   │           │
│  │   └──────────────────────────────────┘   │           │
│  └──────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────┘
                           ▲
                           │
┌─────────────────────────────────────────────────────────┐
│              Ingestion Pipeline                          │
│  ┌──────────┐  ┌──────┐  ┌───────┐  ┌──────────────┐  │
│  │ Downloader│→│Parser│→│Chunker │→│  Embedder     │  │
│  │ (PDFs)    │  │(fitz)│  │(LCTS) │  │ (ChromaDB)   │  │
│  └──────────┘  └──────┘  └───────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Component Descriptions

### User Interface (`ui/`)

Four Streamlit pages managed via `st.session_state.current_page`:

| Page | File | Purpose |
|------|------|---------|
| Home | `ui/home.py` | Introduction, session management |
| Questionnaire | `ui/questionnaire_ui.py` | CPS 230 assessment form |
| Report | `ui/report_ui.py` | Gap findings with CSV export |
| Admin | `ui/admin.py` | Standards ingestion controls |

### Engine (`engine/`)

The core analysis engine:

| Module | Purpose |
|--------|---------|
| `schemas.py` | Pydantic data models (GapRule, Question, GapFinding, etc.) |
| `gap_analyzer.py` | Core analysis: `analyze()`, `evaluate_rule()`, `load_gap_rules()` |
| `questionnaire.py` | Question loading: `load_questionnaire()`, `get_sections()`, `get_all_questions()` |

### Ingestion Pipeline (`standards_ingestion/`)

Four-stage pipeline for regulatory document ingestion:

| Stage | Module | Function |
|-------|--------|----------|
| Download | `downloader.py` | `download_source()` — PDF download with ETag/Last-Modified |
| Parse | `parser.py` | `extract_text_from_pdf()` — PyMuPDF text extraction |
| Chunk | `parser.py` | `chunk_text()` — RecursiveCharacterTextSplitter |
| Embed | `embedder.py` | `upsert_documents()` — ChromaDB vector storage |

### Configuration (`config.py`)

Pydantic Settings singleton providing:

- `chroma_persist_directory` — ChromaDB storage path
- `embedding_model_name` — Sentence-transformers model
- `ingestion_schedule_hours` — Re-ingestion interval
- `standards_sources_file` — YAML sources config
- `gap_rules_path` — Gap rules JSON path
- `questionnaire_path` — Questionnaire JSON path

## Data Flow

### Gap Analysis Flow

```
User answers questionnaire
       │
       ▼
st.session_state.answers (dict[str, Any])
       │
       ▼
engine/gap_analyzer.analyze(answers)
       │
       ├── load_gap_rules() → list[GapRule]
       ├── get_all_questions() → list[Question]
       │
       ▼
For each rule: evaluate_rule(rule, answers)
       │
       ├── question_id extracted from gap_condition
       ├── logic operator applied (currently: equals)
       └── Returns True if gap triggered
       │
       ▼
GapFinding objects created
       │
       ├── ChromaDB evidence lookup (optional)
       └── Sorted by severity (high → medium → low)
       │
       ▼
Report page displays findings + CSV export
```

### Ingestion Flow

```
Admin clicks "Update Standards Now"
       │
       ▼
Load sources from standards_ingestion/sources.yaml
       │
       ▼
For each source:
  1. download_source() → data/raw_pdfs/{slug}.pdf
  2. extract_text_from_pdf() → cleaned text
  3. chunk_text() → list[Document] with clause metadata
  4. upsert_documents() → ChromaDB collection
       │
       ▼
Save timestamp to data/last_update.json
```

## Directory Structure

```
Compliance_Gap_Analyser/
├── app.py                    # Streamlit entry point
├── config.py                 # Pydantic settings
├── mkdocs.yml                # MkDocs wiki configuration
├── build_wiki.py             # Wiki build script
├── engine/                   # Core analysis engine
│   ├── __init__.py
│   ├── schemas.py            # Pydantic models
│   ├── gap_analyzer.py       # Gap analysis logic
│   └── questionnaire.py      # Question management
├── standards_ingestion/      # Document ingestion pipeline
│   ├── __init__.py
│   ├── downloader.py         # PDF download
│   ├── parser.py             # Text extraction & chunking
│   ├── embedder.py           # ChromaDB embedding
│   └── sources.yaml          # Standards source config
├── ui/                       # Streamlit pages
│   ├── __init__.py
│   ├── home.py               # Home page
│   ├── questionnaire_ui.py   # Questionnaire page
│   ├── report_ui.py          # Report page
│   └── admin.py              # Admin panel
├── api/                      # FastAPI stub (future)
├── llm/                      # LLM integration stub (future)
├── scripts/                  # CLI scripts
│   ├── run_ingestion.py      # Pipeline runner
│   └── seed_questionnaire.py # Questionnaire seed script
├── data/                     # Runtime data
│   ├── gap_rules.json        # Gap analysis rules
│   ├── questionnaire.json    # Questionnaire data
│   └── chroma_db/            # ChromaDB persistence
└── tests/                    # Test suite
    ├── test_engine.py
    ├── test_ingestion.py
    ├── test_ui.py
    ├── test_gap_rules.py
    ├── test_schemas.py
    └── test_e2e.py
```
