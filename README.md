# Standard_Inquirer

> **AI-Driven Compliance Assessment for Australian Financial Services**

⚠️ **In Development — Expect Bugs & Inconsistencies**

This project is actively under development. You may encounter bugs, inconsistent methodologies, or incomplete features. Breaking changes between versions are possible.

**This is intentional** — the project demonstrates what can be built using local LLMs for regulatory compliance work.

---

## 🤖 AI-Generated Project Showcase

**This entire application was developed using the local LLM `Qwen3.6-35B-A3B`.**

The purpose of this project is to demonstrate that a **full-featured Compliance Assessment Application** can be built entirely with:

- **Local LLM**: Qwen3.6-35B-A3B (no API keys, no cloud dependency)
- **Open-source tools**: Streamlit, Plotly, pandas, pytest
- **Iterative AI-assisted development**: Code generation, debugging, refactoring, and documentation were all handled by the LLM

---

## Overview

Standard_Inquirer is a **Streamlit-based web application** that helps Australian financial services organisations assess their compliance with APRA prudential standards. Instead of filling out static forms, users have a natural conversation with an AI consultant that adapts to their organisation type and compliance focus.

### Key Features

- **AI-driven chat assessment** — A conversational interface where an AI consultant asks adaptive questions based on your organisation type and compliance focus area
- **Multi-standard coverage** — Supports 40+ APRA prudential standards (CPS, LPS, LRS, CPG, LPG, and Actuarial Standards) via vector knowledge base retrieval
- **Smart answer extraction** — Three-phase extraction pipeline (LLM → conversation-based fallback → manual) ensures user responses are captured reliably
- **Compliance review reports** — Severity-ranked findings with gap conditions mapped to specific standard clauses
- **Vector knowledge base** — ChromaDB stores embedded regulatory standards for evidence retrieval and context-aware questioning
- **Standards ingestion pipeline** — Automatically downloads, parses, and indexes regulatory documents from APRA and Actuaries Institute
- **LLM-powered enrichment** — Optional LLM analysis for gap explanations and mitigation suggestions
- **Wiki documentation** — Auto-generated documentation site with search

### Demo

![Standard_Inquirer Demo](https://raw.githubusercontent.com/jasonzheshiou/Standard_Inquirer/main/Animation.gif)

> 📝 **Note:** All questions and answers shown in the demo were generated randomly by AI for demonstration purposes.

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

### 🤖 LLM Backend — OpenAI-Compatible APIs

This app uses the **OpenAI Chat Completions API** format under the hood. That means you can swap the default local LLM server with **any OpenAI-compatible API** — no code changes required, just update the environment variables.

#### Default: Local LMStudio Server

```bash
LLM_BASE_URL=http://192.168.1.59:1234/v1
LLM_MODEL=qwen/qwen3.6-35b-a3b
```

#### Alternative: Ollama

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=qwen2.5:32b
```

#### Alternative: vLLM

```bash
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=meta-llama/Llama-3-70b
```

#### Alternative: OpenAI API (cloud)

```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o
# Also set: OPENAI_API_KEY=your-key-here
```

#### Alternative: Any OpenAI-Compatible Provider

Drop-in replacements that support the OpenAI Chat Completions API:

| Provider | Base URL Example |
|----------|-----------------|
| Groq | `https://api.groq.com/openai/v1` |
| Together AI | `https://api.together.xyz/v1` |
| Fireworks AI | `https://api.fireworks.ai/inference/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| LiteLLM Proxy | `http://localhost:4000/v1` |
| Text Generation Inference | `http://localhost:8080/v1` |

> **Note:** The model name (`LLM_MODEL`) must match a model available on your chosen backend. Check the provider's model catalog for the exact name.

---

## Usage

### Running the Application

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501` with six pages:

| Page | Purpose |
|------|---------|
| **Assessment** | AI-driven conversational compliance assessment — chat with the AI consultant |
| **Home** | Introduction, LLM status, recent assessments |
| **Compliance Review** | View severity-ranked compliance findings |
| **Questionnaire** | Legacy form-based questionnaire (fallback for static assessment) |
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
<summary><strong>🏗️ Architecture</strong></summary>

```
┌─────────────────────────────────────────────────────┐
│                  Streamlit UI                        │
│  Assessment │ Home │ Compliance Review │ Questionnaire │ Admin │ Standards
└─────────────────────────────────────────────────────┘
                    │
                    v
┌─────────────────────────────────────────────────────┐
│         AI Conversation Engine (ChatConductor)       │
│  • Standards retrieval from ChromaDB                │
│  • Multi-turn LLM conversation                      │
│  • Smart answer extraction (3-phase pipeline)       │
│  • Structured questionnaire generation              │
└──────────┬───────────────────────┬──────────────────┘
           │                       │
           v                       v
┌──────────────────┐     ┌────────────────────────────┐
│  Gap Analysis     │     │  Vector Knowledge Base     │
│  Engine           │     │  (ChromaDB)                │
│  • Rule evaluation │     │  • 40+ APRA standards      │
│  • LLM enrichment  │     │  • Actuarial standards     │
│  • Severity ranking│     │  • Embeddings              │
└──────────────────┘     └────────────────────────────┘
                                      ^
                                      │ (update)
                             ┌────────────────────┐
                             │ Standards Ingestion  │
                             │ Pipeline             │
                             │ • Download PDFs/HTML │
                             │ • Parse & chunk      │
                             │ • Embed & store      │
                             └────────────────────┘
```

</details>

---

<details>
<summary><strong>📖 How It Works</strong></summary>

### AI-Driven Assessment

The Assessment page is a conversational chat interface — there are no forms to fill out. The experience works like this:

1. **Greeting** — The AI consultant introduces itself and asks about your organisation type (life insurer, reinsurer, friendly society, superannuation fund, or other) and what compliance area you'd like to focus on
2. **Adaptive conversation** — Based on your responses, the AI asks targeted follow-up questions one at a time, referencing specific APRA standards and clauses relevant to your context (e.g. CPS 510 for governance, CPS 230 for operational risk, Privacy Act for data privacy). The AI adapts its line of questioning based on your answers — if you mention you have a framework, it digs deeper into controls; if you say you don't, it acknowledges that and moves on
3. **Warm, professional tone** — The AI uses a professional yet approachable tone, acknowledging your answers before moving on, and never being judgmental about gaps in compliance
4. **Completion** — The AI signals when it has enough information to produce a review (or after 30 turns maximum). You can also end the assessment at any time by clicking **"I'm Done — Generate My Report"** in the sidebar, or start over with **"Start Over"**
5. **Data extraction** — The conversation is analysed to extract structured questionnaire data and your answers, which feed into the compliance review report

### Compliance Review

After the assessment, the Compliance Review page displays:

- **Severity-ranked findings** — High, medium, and low severity gaps mapped to specific standard clauses
- **Gap conditions** — What's missing or non-compliant based on your responses
- **Mitigation suggestions** — Actionable steps to close each gap
- **Standard references** — Direct links to the relevant APRA standard

### Static Questionnaire (Fallback)

The legacy form-based questionnaire is still available for organisations that prefer structured forms over conversation. It covers CPS 230 with 8 questions across 4 sections (Board Oversight, Model Inventory & Validation, Data Governance, Risk Escalation & Reporting).

</details>

---

<details>
<summary><strong>📜 Compliance Standards</strong></summary>

### Supported Standards (via Vector Knowledge Base)

The application indexes **40+ regulatory standards** from APRA and the Actuaries Institute, including:

| Category | Standards |
|----------|-----------|
| **APRA CPS** | CPS 001, CPS 190, CPS 220, CPS 226, CPS 230, CPS 234, CPS 320, CPS 510, CPS 511, CPS 520, CPS 900 |
| **APRA LPS** | LPS 100, LPS 110, LPS 112, LPS 114, LPS 115, LPS 117, LPS 118, LPS 200, LPS 230, LPS 340, LPS 360, LPS 370, LPS 600, LPS 700 |
| **APRA LRS** | LRS 001, LRS 110.0, LRS 111.0, LRS 112.0, LRS 112.3, LRS 114.0, LRS 114.2, LRS 114.3, LRS 115.0, LRS 117.0, LRS 118.0, LRS 200.0, LRS 300.0, LRS 310.0, LRS 311.0, LRS 340.0, LRS 750 |
| **APRA CPG** | CPG 110, CPG 190, CPG 220, CPG 230, CPG 234, CPG 320, CPG 900 |
| **APRA LPG** | LPG 230, LPG 240, LPG 250, LPG 260, LPG 270, LPG 520, LPG 700 |
| **Actuarial** | PS 1, PS 102, PS 103, PS 201, PS 202, PG 1, PG 4, PG 5, PG 6A, PG 6B, PG 101, PG 199.02, PG 199.03 |
| **Accounting** | AASB 17, IFRS 17 |

### Implemented Gap Rules

The gap analysis engine currently has **8 deterministic rules** implemented for **CPS 230 (Operational Risk Management)** covering:

| Clause | Requirement | Severity |
|--------|-------------|----------|
| CPS 230 ¶27(b) | Board-approved risk appetite statement covering model risk | High |
| CPS 230 ¶6 | Documented model risk governance framework | High |
| CPS 230 ¶21 | Comprehensive model inventory | Medium |
| CPS 230 ¶22 | Independent model validation | High |
| CPS 230 ¶27 | Data governance framework for model inputs/outputs | Medium |
| CPS 230 ¶28 | Model documentation standards | Medium |
| CPS 230 ¶30 | Model issue escalation process | High |
| CPS 230 ¶29 | Concentration risk in model inputs/outputs | Medium |

> **More standards and rules are being added.** The vector knowledge base supports all 40+ indexed standards — gap rules for additional standards are planned.

</details>

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
│   ├── client.py              # OpenAI-compatible API client
│   ├── chat_conductor.py      # AI conversation engine
│   ├── question_generator.py  # LLM questionnaire generation
│   └── session.py             # Session persistence
│
├── standards_ingestion/       # Standards processing pipeline
│   ├── downloader.py          # PDF/HTML download with caching
│   ├── parser.py              # Text extraction & chunking
│   ├── embedder.py            # Embedding + ChromaDB upsert
│   ├── sources.yaml           # Standards catalog (40+ standards)
│   └── custom_loader.py       # Custom standards from YAML
│
├── ui/                        # Streamlit pages
│   ├── home.py                # Home/introduction page
│   ├── chat_ui.py             # AI chat-based assessment page
│   ├── questionnaire_ui.py    # Legacy form-based questionnaire
│   ├── report_ui.py           # Compliance review report display
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

> ⚠️ **This tool provides sample guidance only.** All rules, mitigations, and gap conditions must be reviewed by a **qualified professional** before being relied upon for regulatory compliance. The automated analysis is not a substitute for professional regulatory advice.

---

## License

**MIT License**

Copyright (c) 2026 Standard_Inquirer

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

---

*Built with local LLMs. No cloud dependencies required.*
