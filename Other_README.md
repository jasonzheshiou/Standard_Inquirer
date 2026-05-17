# 🇦🇺 Australia TPD Incidence Experience Analysis Dashboard

> **AI-powered experience analysis, audit-ready reporting, and modular design – built for life insurance actuaries.**

[![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit)](https://streamlit.io)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge)](LICENSE)
[![Status: In Development](https://img.shields.io/badge/Status-In%20Development-orange?style=for-the-badge)](#)

**Docs:** [AI Guide](./AI_GUIDE.md) | [Architecture](./README_Architecture.md) | [Methodology](./README_Methodology.md) | [Configuration](./README_Configuration.md) | [Development](./README_Development.md) | [Dev Rules](./DEVELOPMENT_RULES.md) | [License](./LICENSE)

---

## ⚠️ In Development — Expect Bugs & Inconsistencies

**This project is actively under development.** You may encounter bugs, inconsistent methodologies, or incomplete features.

**NO WARRANTY:** This software is provided "as is", without warranty of any kind, express or implied. Use entirely at your own risk.

---

## 🤖 AI Showcase

**Built using the local LLM `Qwen3.6-35B-A3B`.**

This project demonstrates that a **full-featured Life Insurance Actuarial Application** can be developed with local LLMs — no API keys or cloud dependencies required.

---

## 📋 Quick Navigation

<details>
<summary><strong>🚀 Quick Start</strong></summary>

```bash
# Install dependencies
pip install streamlit pandas numpy pyarrow scipy scikit-learn

# Generate sample data (optional)
python generate_dummy_tpd_data.py

# Run dashboard
streamlit run app.py
```

Opens at `http://localhost:8501`.

```bash
# Build documentation
python auto_generate_docs.py
python build_wiki.py
```

</details>

<details>
<summary><strong>✨ Key Features</strong></summary>

| Feature | Description |
|---------|-------------|
| **📊 Interactive Dashboard** | 5 sections, 17 slides, configurable parameters |
| **🔄 Modular Pipeline** | Dynamic module discovery, cached execution, error isolation |
| **📈 Statistical Methods** | Credibility, A/E ratios, Mann-Kendall, GLM, RF, GBM, MOB |
| **🛡️ Audit-Ready** | Data quality metrics, pipeline tracking, session persistence |
| **🤖 AI-Optimized** | 20 development rules, auto-documentation, template-driven |

</details>

<details>
<summary><strong>📊 Dashboard Sections</strong></summary>

| Section | Icon | Slides | Purpose |
|---------|------|--------|---------|
| **Dashboard** | 📊 | 01-04 | Overview, portfolio, methodology |
| **Experience Analysis** | 📈 | 05-07 | Incidence rates, A/E ratios, termination |
| **Model Diagnostics** | 🔬 | 08-09 | Trends, statistical tests |
| **Assumption Setting** | ⚙️ | 13-16 | Industry baselines, ML, MOB, exports |
| **Pipeline Audit** | 🔍 | 10-12, 17 | Data quality, pipeline tracking, wiki |

</details>

<details>
<summary><strong>📐 Data Coverage</strong></summary>

| Data Type | Records | Description |
|-----------|---------|-------------|
| Exposure | ~200,000 | Policy records (2010–2024) |
| TPD Claims | ~8,000 | Full lifecycle records |
| Benchmarks | Per 1,000 | Industry rates by age/occ/gender |

**7 occupation classes**: Professional through Hazardous
**7 diagnosis categories**: Musculoskeletal, Mental Health, Cancer, Cardiovascular, Neurological, Injury/Accident, Other

</details>

<details>
<summary><strong>👥 Who Is This For?</strong></summary>

| Role | Use Case |
|------|----------|
| **Actuaries** | Experience studies, assumption setting, regulatory submissions |
| **Pricing Actuaries** | Premium rate adjustments and loadings |
| **Reserving Actuaries** | IBNR/IBNER assumption validation |
| **Data Scientists** | Claim pattern exploration, predictive modeling |
| **Reinsurance** | Portfolio risk assessment |

</details>

---

## 📚 Detailed Documentation

This README is split into multiple files for readability. Click below to expand:

<details>
<summary><strong>🏗️ Architecture & Design</strong></summary>

See [README_Architecture.md](README_Architecture.md) for:
- High-level architecture diagram
- Data flow (loaders → transforms → slides)
- Section architecture
- Key design decisions

</details>

<details>
<summary><strong>📐 Statistical Methodologies</strong></summary>

See [README_Methodology.md](README_Methodology.md) for:
- Incidence rate calculation
- A/E ratio analysis with Byar's CI
- Limited fluctuation credibility
- Chi-squared GOF test
- Mann-Kendall trend test
- GLM, Random Forest, GBM
- Model-based Recursive Partitioning (MOB)
- Final assumption setting

</details>

<details>
<summary><strong>⚙️ Configuration</strong></summary>

See [README_Configuration.md](README_Configuration.md) for:
- Global configuration parameters
- Data requirements (tpd_claims.parquet, tpd_exposure.parquet)
- Benchmark file specifications

</details>

<details>
<summary><strong>🛠️ Adding New Content</strong></summary>

See [README_Development.md](README_Development.md) for:
- Adding new slides
- Adding new transforms
- Adding new sections
- Development rules (20 mandatory)
- AI-assisted development guide

</details>

<details>
<summary><strong>🔍 Auditing & Tracking</strong></summary>

- Pipeline error tracking with full stack traces
- Data quality metrics (missing values, column completeness)
- Transform I/O logging
- Session state persistence
- 100% reproducible analysis

</details>

<details>
<summary><strong>📚 Wiki & Documentation</strong></summary>

```bash
# Build wiki from docstrings
python build_wiki.py

# Serve locally with MkDocs
mkdocs serve

# Build static site
mkdocs build
```

Wiki components:
- `wiki_build/index.md` — Table of contents
- `wiki_build/loaders/` — Data loading specs
- `wiki_build/transforms/` — Transform I/O specs
- `wiki_build/helpers/` — Utility documentation
- `wiki_build/guides/` — How-to guides

</details>

<details>
<summary><strong>📁 Project Structure</strong></summary>

See [README_Architecture.md](README_Architecture.md) for full directory tree.

</details>

<details>
<summary><strong>🤝 Contributing</strong></summary>

1. Read `DEVELOPMENT_RULES.md`
2. Follow existing patterns
3. Test with `streamlit run app.py`
4. Update docs with `python auto_generate_docs.py`
5. Commit with conventional format

</details>

<details>
<summary><strong>📄 License</strong></summary>

MIT License. See [LICENSE](LICENSE).

**Built with ❤️ and 🤖 using Qwen3.6-35B-A3B**

</details>

---

*Last updated: 2025 | Project Status: In Development*
