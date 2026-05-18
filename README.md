# Compliance Gap Analyser

> **Australian Life Insurance Model Governance Gap Analysis Tool**

⚠️ **In Development — Expect Bugs & Inconsistencies**

This project is actively under development. You may encounter bugs, inconsistent methodologies, or incomplete features. Breaking changes between versions are possible. Statistical methods are still being refined.

**This is intentional** — the project demonstrates what can be built using local LLMs.

---

## 🤖 AI-Generated Project Showcase

**This entire application was developed using the local LLM `Qwen3.6-35B-A3B`.**

The purpose of this project is to demonstrate that a **full-featured Compliance Gap Analysis Application** can be built entirely with:

- **Local LLM**: Qwen3.6-35B-A3B (no API keys, no cloud dependency)
- **Open-source tools**: Streamlit, Plotly, pandas, pytest
- **Iterative AI-assisted development**: Code generation, debugging, refactoring, and documentation were all handled by the LLM

---

## Overview

The Compliance Gap Analyser is a **Streamlit-based web application** that helps Australian life insurance organisations assess their compliance with prudential standards (primarily APRA CPS 230 on Operational Risk Management).

### Key Features

- **Free-text questionnaire** — Answer compliance questions with detailed explanations rather than simple Yes/No responses
- **Gap analysis engine** — Evaluates answers against APRA CPS 230 rules with severity-ranked findings
- **Vector knowledge base** — ChromaDB stores embedded regulatory standards for evidence retrieval
- **Standards ingestion pipeline** — Automatically downloads, parses, and indexes regulatory documents
- **LLM-powered enrichment** — Optional LLM analysis for gap explanations and mitigation suggestions
- **Interactive gap reports** — Severity-sorted findings with expandable details and CSV/JSON export
- **Wiki documentation** — Auto-generated documentation site with search

---

<details>
<summary><strong>🏗️ Architecture</strong></summary>

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit UI                        │
│  Intake │ Home │ Questionnaire │ Report │ Admin     │
└──────────────────┬──────────────────────────────────┘
                   │
                   v
┌─────────────────────────────────────────────────────┐
│            Gap Analysis Engine                       │
│  • Rule evaluation (deterministic)                   │
│  • LLM-powered gap analysis (optional)              │
│  • ChromaDB evidence retrieval                      │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
           v                       v
┌──────────────────┐     ┌────────────────────────────┐
│  Structured Rules │     │  Vector Knowledge Base     │
│  (gap_rules.json) │     │  (ChromaDB)                │
│  • CPS 230 rules  │     │  • Standards chunks        │
│  • Severity maps  │     │  • Embeddings              │
└──────────────────┘     └────────────────────────────┘
                                    ^
                                    │ (update)
                           ┌────────────────────┐
                           │ Standards Ingestion  │
                           │ Pipeline             │
                           │ • Download PDFs      │
                           │ • Parse & chunk      │
                           │ • Embed & store      │
                           └────────────────────┘
```

</details>

---

## Installation

### Prerequisites

- Python 3.10 or later
- Local LLM server (optional, for LLM features) — e.g., [LMStudio](https://lmstudio.ai/) or [Ollama](https://ollama.com/)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd Compliance_Gap_Analyser

# Install dependencies (choose one):
pip install -e ".[dev]"          # via pyproject.toml (recommended)
# or
pip install -r requirements.txt  # via requirements.txt (production only)

# Configure environment
cp .env.example .env
# Edit .env with your settings (LLM URL, etc.)
```

### Environment Configuration

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://192.168.1.59:1234/v1` | LMStudio/OpenAI-compatible API URL |
| `LLM_MODEL` | `qwen/qwen3.6-35b-a3b` | Model name (must match loaded model) |
| `LLM_TIMEOUT` | `60` | Request timeout in seconds |
| `LLM_MAX_TOKENS` | `4096` | Max tokens in LLM response |
| `CHROMA_PERSIST_DIRECTORY` | `data/chroma_db` | ChromaDB storage path |
| `EMBEDDING_MODEL_NAME` | `sentence-transformers/all-MiniLM-L6-v2` | Embedding model |

---

## Usage

### Running the Application

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` with six pages:

| Page | Purpose |
|------|---------|
| **Intake** | Select organisation type and compliance focus area |
| **Home** | Introduction, LLM status, recent assessments |
| **Questionnaire** | Answer compliance questions (free text) |
| **Gap Report** | View severity-ranked compliance findings |
| **Admin** | Standards ingestion controls and ChromaDB status |
| **Standards** | Manage built-in and custom compliance standards |

### Standards Ingestion Pipeline

Download and index regulatory standards:

```bash
# Run the ingestion pipeline
python -m scripts.run_ingestion

# Or via the Admin page in the Streamlit app
```

### Generating Wiki Documentation

```bash
# Quick launch (generates + opens in browser)
python launch_wiki.py

# Generate only (standalone HTML + MkDocs)
python build_wiki.py --both

# Generate MkDocs site only
python build_wiki.py --mkdocs

# Serve MkDocs locally
mkdocs serve
```

---

<details>
<summary><strong>📂 Project Structure</strong></summary>

```
Compliance_Gap_Analyser/
├── app.py                     # Streamlit entry point
├── config.py                  # Pydantic settings (.env)
├── launch_wiki.py             # One-click wiki launcher
├── build_wiki.py              # Wiki documentation generator
├── pyproject.toml             # Project config (deps, black, ruff, mypy)
├── .env.example               # Environment template
├── .gitignore                 # Git exclusion rules
├── mkdocs.yml                 # MkDocs site configuration
│
├── engine/                    # Core gap analysis engine
│   ├── schemas.py             # Pydantic data models
│   ├── gap_analyzer.py        # Rule evaluation + LLM analysis
│   └── questionnaire.py       # Questionnaire loading/validation
│
├── llm/                       # LLM integration
│   ├── client.py              # LMStudio API client
│   ├── question_generator.py  # LLM questionnaire generation
│   ├── answer_analyzer.py     # LLM gap finding enrichment
│   └── session.py             # Session persistence
│
├── standards_ingestion/       # Standards processing pipeline
│   ├── downloader.py          # PDF/HTML download with caching
│   ├── parser.py              # Text extraction & chunking
│   ├── embedder.py            # Embedding + ChromaDB upsert
│   ├── sources.yaml           # Standards catalog
│   └── custom_loader.py       # Custom standards from YAML
│
├── ui/                        # Streamlit pages
│   ├── home.py                # Home/introduction page
│   ├── questionnaire_intake.py  # Organisation type + focus input
│   ├── questionnaire_ui.py    # Questionnaire rendering
│   ├── report_ui.py           # Gap report display
│   ├── admin.py               # Admin panel
│   └── standards_manager.py   # Standards CRUD
│
├── data/                      # Application data
│   ├── gap_rules.json         # CPS 230 gap rules (8 rules)
│   ├── questionnaire.json     # Static questionnaire (4 sections, 8 questions)
│   ├── custom_standards.yaml  # Custom standards config
│   ├── chroma_db/             # ChromaDB vector store (gitignored)
│   ├── raw_pdfs/              # Downloaded standards (gitignored)
│   └── sessions/              # Questionnaire sessions
│
├── scripts/                   # Utility scripts
│   ├── run_ingestion.py       # CLI ingestion pipeline
│   └── seed_questionnaire.py  # Questionnaire validation
│
├── tests/                     # Test suite
├── wiki_build/                # MkDocs source Markdown
├── wiki_site/                 # Built MkDocs HTML (gitignored)
└── api/                       # Future FastAPI layer
```

</details>

---

<details>
<summary><strong>📋 Questionnaire</strong></summary>

The questionnaire uses **free-text answers** instead of multiple choice, allowing users to provide detailed explanations of their compliance posture.

### Current Coverage

| Section | Questions |
|---------|-----------|
| Board & Senior Management Oversight | 2 |
| Model Inventory & Validation | 2 |
| Data Governance | 2 |
| Risk Escalation & Reporting | 2 |

### Gap Detection Logic

Free-text answers are evaluated for non-compliance indicators including:

- Empty responses (no answer provided)
- Negative responses ("no", "n/a", "not applicable")
- Incomplete responses ("not documented", "not established", "not in place")
- Case-insensitive matching

</details>

---

<details>
<summary><strong>📜 Compliance Standards</strong></summary>

### Implemented

| Standard | Category | Rules | Status |
|----------|----------|-------|--------|
| APRA CPS 230 | Operational Risk | 8 | ✅ Implemented |

### Planned

| Standard | Category |
|----------|----------|
| APRA CPS 220 | Risk Management |
| APRA CPS 510 | Governance |
| APRA LPS 110 | Capital Adequacy |
| APRA LPS 220 | Risk Management (Life) |
| AI PS 200 | Life Insurance Valuation |
| AI PS 300 | Actuarial Reporting |
| AI PS 400 | Model Governance |

</details>

---

<details>
<summary><strong>🧪 Testing</strong></summary>

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run with ruff linting
ruff check .

# Run mypy type checking
mypy .
```

</details>

---

<details>
<summary><strong>⚙️ Configuration</strong></summary>

All configurable settings are managed through `config.py` using `pydantic-settings`. Settings are loaded from:

1. Environment variables
2. `.env` file (if present)
3. Default values

See `.env.example` for all available configuration options.

</details>

---

<details>
<summary><strong>📚 Documentation</strong></summary>

- **Wiki**: `python launch_wiki.py` — Auto-generated documentation site
- **Architecture**: See `wiki_build/guides/architecture.md`
- **Engine API**: See `wiki_build/engine/overview.md`
- **Ingestion Pipeline**: See `wiki_build/ingestion/overview.md`
- **UI Reference**: See `wiki_build/ui/overview.md`

</details>

---

<details>
<summary><strong>🔧 Development</strong></summary>

### Code Quality

This project uses:

- **Black** — Code formatting (100-char line length)
- **Ruff** — Linting
- **mypy** — Strict type checking

### Adding New Standards

1. Add the standard to `standards_ingestion/sources.yaml`
2. Run the ingestion pipeline: `python -m scripts.run_ingestion`
3. Add gap rules to `data/gap_rules.json`
4. Add questionnaire items to `data/questionnaire.json`

### Adding New Questionnaire Items

1. Add the question to `data/questionnaire.json` with `type: "text"`
2. Add a corresponding gap rule to `data/gap_rules.json`
3. Run `python -m scripts.seed_questionnaire` to validate

</details>

---

## Disclaimer

> ⚠️ **This tool provides sample guidance only.** All rules, mitigations, and gap conditions must be reviewed by a **qualified actuary** before being relied upon for regulatory compliance. The automated analysis is not a substitute for professional regulatory advice.

---

<details>
<summary><strong>📄 License</strong></summary>

**MIT License**

Copyright (c) 2026 Compliance Gap Analyser

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

</details>

---

*Built with local LLMs. No cloud dependencies required.*
# Standard_Inquirer
