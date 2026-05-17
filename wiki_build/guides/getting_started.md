# Getting Started

This guide walks you through installing, configuring, and running the Compliance Gap Analyser.

## Prerequisites

- **Python 3.10+** (3.11 recommended)
- **pip** or **conda** for package management
- A modern web browser (for the Streamlit UI)

## Installation

### 1. Clone or download the project

```bash
cd Compliance_Gap_Analyser
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

Key dependencies include:

| Package | Purpose |
|---------|---------|
| `streamlit` | Web UI framework |
| `pydantic` + `pydantic-settings` | Data validation and configuration |
| `requests` | HTTP client for PDF downloads |
| `PyMuPDF (fitz)` | PDF text extraction |
| `langchain-text-splitters` | Text chunking |
| `chromadb` | Vector database for embeddings |
| `sentence-transformers` | Embedding model inference |
| `loguru` | Structured logging |
| `pyyaml` | YAML config parsing |

### 4. Configure the application

Copy the example environment file and adjust as needed:

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
```

Key settings in `.env`:

| Setting | Default | Description |
|---------|---------|-------------|
| `CHROMA_PERSIST_DIRECTORY` | `data/chroma_db` | ChromaDB data directory |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |
| `INGESTION_SCHEDULE_HOURS` | `168` | Re-ingestion interval (weekly) |
| `STANDARDS_SOURCES_FILE` | `standards_ingestion/sources.yaml` | Sources config |
| `GAP_RULES_PATH` | `data/gap_rules.json` | Gap rules JSON file |
| `QUESTIONNAIRE_PATH` | `data/questionnaire.json` | Questionnaire JSON file |

## Running the Application

### Start the Streamlit app

```bash
streamlit run app.py
```

This launches the web UI at `http://localhost:8501` with four pages:

1. **Home** — Introduction and session management
2. **Questionnaire** — CPS 230 governance assessment
3. **Gap Report** — Severity-ranked findings
4. **Admin** — Standards ingestion controls

### Run the ingestion pipeline (CLI)

```bash
python -m scripts.run_ingestion
```

This runs the full pipeline: download → parse → chunk → embed for all configured standards sources.

## Using the Questionnaire

1. Navigate to the **Questionnaire** page from the sidebar
2. Answer each question (Yes/No boolean, or text input)
3. Progress is tracked via a progress bar
4. Click **Next: View Gap Report** to see results

## Generating the Wiki

To build the MkDocs-based wiki:

```bash
python build_wiki.py --both
```

This generates:

| Output | Location | Description |
|--------|----------|-------------|
| Markdown files | `wiki_build/` | Raw wiki pages |
| Standalone HTML | `wiki_build/wiki_standalone.html` | Single-file HTML wiki |
| MkDocs site | `wiki_site/` | Full static site |

Open `wiki_site/index.html` in a browser to view the full wiki.
