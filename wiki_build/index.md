# Compliance Gap Analyser — Wiki

## Overview

The **Compliance Gap Analyser** is a Streamlit-based tool for assessing governance compliance of Australian life insurance organisations against regulatory standards — starting with **APRA CPS 230 (Operational Risk)** and extending to other APRA and Actuaries Institute standards.

The tool guides users through a structured questionnaire, evaluates answers against gap-analysis rules, and produces a severity-ranked findings report with suggested mitigations. An optional standards ingestion pipeline downloads, parses, chunks, and embeds regulatory PDF documents into ChromaDB for vector-similarity evidence retrieval.

---

## Compliance Registry

> **Status Legend:** ✅ Implemented · 🚧 In Progress · 🔲 Planned

| Standard | Category | Status | Rules | Questions | Source URL |
|----------|----------|--------|-------|-----------|------------|
| APRA CPS 230 | Operational Risk | ✅ Implemented | 8 | 8 | [Link](https://www.apra.gov.au/prudential-standards/cps-230) |
| APRA CPS 220 | Risk Management | 🔲 Planned | — | — | — |
| APRA CPS 510 | Governance | 🔲 Planned | — | — | — |
| APRA LPS 110 | Capital Adequacy | 🔲 Planned | — | — | — |
| APRA LPS 220 | Risk Management (Life) | 🔲 Planned | — | — | — |
| AI PS 200 | Life Insurance Valuation | 🔲 Planned | — | — | — |
| AI PS 300 | Actuarial Reporting | 🔲 Planned | — | — | — |
| AI PS 400 | Model Governance | 🔲 Planned | — | — | — |

### Implemented: APRA CPS 230 — Gap Rules

The following **8 gap rules** are currently implemented for CPS 230:

| Rule ID | Clause | Category | Severity |
|---------|--------|----------|----------|
| CPS230-6 | Paragraph 6 | Board Oversight | High |
| CPS230-27b | Paragraph 27(b) | Board Oversight | High |
| CPS230-22 | Paragraph 22 | Model Validation | High |
| CPS230-30 | Paragraph 30 | Risk Escalation | High |
| CPS230-21 | Paragraph 21 | Model Inventory | Medium |
| CPS230-27 | Paragraph 27 | Data Governance | Medium |
| CPS230-28 | Paragraph 28 | Documentation | Medium |
| CPS230-29 | Paragraph 29 | Risk Management | Medium |

---

## Quick Links

### Guides
- [Getting Started](guides/getting_started.md) — Installation and first run
- [Compliance Registry](guides/compliance_registry.md) — How standards and rules are managed
- [Architecture](guides/architecture.md) — System design and data flow

### Engine
- [Engine Overview](engine/overview.md) — Package structure
- [Schemas](engine/schemas.md) — Pydantic data models
- [Gap Analyzer](engine/gap_analyzer.md) — Core analysis engine
- [Questionnaire](engine/questionnaire.md) — Question loading and management

### Ingestion Pipeline
- [Ingestion Overview](ingestion/overview.md) — Pipeline stages
- [Downloader](ingestion/downloader.md) — PDF download with ETag support
- [Parser](ingestion/parser.md) — Text extraction and chunking
- [Embedder](ingestion/embedder.md) — ChromaDB vector storage

### User Interface
- [UI Overview](ui/overview.md) — Streamlit pages
- [Home](ui/home.md) — Landing page
- [Questionnaire](ui/questionnaire.md) — Assessment form
- [Report](ui/report.md) — Gap findings and export
- [Admin](ui/admin.md) — Standards ingestion controls

---

!!! warning "Disclaimer"

    This tool provides **sample guidance only**. All rules, mitigations, and gap conditions must be reviewed by a **qualified actuary** before being relied upon for regulatory compliance. The questionnaire answers and resulting findings are illustrative and do not constitute formal regulatory advice.
