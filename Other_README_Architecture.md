# TPD Dashboard — Architecture & Design

> High-level architecture, data flow, and design decisions.

---

## Philosophy

1. **Separation of Concerns**: Business logic in transforms, presentation in slides
2. **Single Source of Truth**: All data flows through shared `data_store` dictionary
3. **Convention Over Configuration**: Strict patterns for naming, structure, behavior

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Streamlit UI (app.py)                     │
│                 Entry Point & Pipeline Orchestrator              │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   Sidebar    │  │   Main Area  │  │   Session State      │  │
│  │  - Sections  │  │   - Slides   │  │   - data_store       │  │
│  │  - Slides    │  │   - Tabs     │  │   - config           │  │
│  │  - Config    │  │   - Charts   │  │   - selections       │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌────────────────▼────────────────┐
           │       Module Discovery           │
           │                                  │
           │  • pipeline/loaders/ (2 modules) │
           │  • pipeline/transforms/ (5)      │
           │  • pipeline/sections/ (5)        │
           │  • pipeline/slides/ (17)         │
           │  • pipeline/helpers/ (11)        │
           └────────────────┬─────────────────┘
                            │
           ┌────────────────▼─────────────────┐
           │       Data Pipeline               │
           │                                   │
           │  Phase 1: Loaders                 │
           │    ↓ Read parquet → data_store    │
           │                                   │
           │  Phase 2: Transforms (cached)     │
           │    ↓ Enrich, analyze, score       │
           │                                   │
           │  Phase 3: Slides (presentation)   │
           │    ↓ Read data_store → render UI  │
           └────────────────┬──────────────────┘
                            │
           ┌────────────────▼─────────────────┐
           │       Shared Data Store           │
           │                                   │
           │  tpd_claims_raw, tpd_exposure_raw │
           │  tpd_claims, tpd_exposure         │
           │  incidence_by_*, ae_by_*          │
           │  credibility_scores, ml_analysis  │
           │  final_assumptions, mob_segments  │
           └───────────────────────────────────┘
```

---

## Data Flow

```
Parquet Files
  ├─ data/tpd_claims.parquet (8K claims)
  └─ data/tpd_exposure.parquet (200K policies)
       │
       ▼
LOADERS (run once, uncached)
  ├─ loader_01_tpd_claims.py  →  tpd_claims_raw
  └─ loader_02_tpd_exposure.py →  tpd_exposure_raw
       │
       ▼
TRANSFORMS (@st.cache_data, run when config changes)
  ├─ transform_00_data_prep.py
  │    Input:  tpd_claims_raw, tpd_exposure_raw
  │    Output: tpd_claims, tpd_exposure, data_quality
  │
  ├─ transform_01_incidence.py
  │    Input:  tpd_claims, tpd_exposure
  │    Output: incidence_by_age/occ/gender/diagnosis/...
  │
  ├─ transform_03_experience.py
  │    Input:  tpd_claims, tpd_exposure
  │    Output: ae_by_age/occ/gender, credibility_scores, ...
  │
  └─ transform_04_assumptions.py
       Input:  tpd_claims, tpd_exposure
       Output: industry_baseline, ml_analysis, mob_segments, ...
       │
       ▼
SLIDES (pure presentation, no business logic)
  ├─ Dashboard (📊): slides 01-04
  ├─ Experience Analysis (📈): slides 05-07
  ├─ Model Diagnostics (🔬): slides 08-09
  ├─ Assumption Setting (⚙️): slides 13-16
  └─ Pipeline Audit (🔍): slides 10-12, 17
```

---

## Section Architecture

| Section | Icon | Slides | Purpose |
|---------|------|--------|---------|
| **Dashboard** | 📊 | 01-04 | High-level overview, portfolio summary, methodology |
| **Experience Analysis** | 📈 | 05-07 | Incidence rates, A/E ratios, termination analysis |
| **Model Diagnostics** | 🔬 | 08-09 | Trend detection, statistical significance tests |
| **Assumption Setting** | ⚙️ | 13-16 | Industry baselines, ML insights, MOB, exports |
| **Pipeline Audit** | 🔍 | 10-12, 17 | Data quality, pipeline tracking, wiki |

---

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Modular Pipeline** | Each step is independent, testable, and cacheable |
| **Dynamic Discovery** | Add slides/transforms by dropping files — no registry updates |
| **Shared data_store** | Single source of truth; no duplicate computation |
| **@st.cache_data** | Automatic caching with invalidation on config change |
| **Error Isolation** | Try/except per module; one failure doesn't crash app |
| **Separation of Concerns** | Transforms = business logic, Slides = presentation |
| **Absolute Paths** | No relative path issues; works from any directory |
| **No Global Mutation** | All transformations return new objects |

---

## Project Structure

```
tpd_dashboard/
├── app.py                              # Main entry point
├── generate_dummy_tpd_data.py          # Synthetic data generator
├── auto_generate_docs.py               # Auto-documentation script
├── build_wiki.py                       # Wiki builder
├── mkdocs.yml                          # MkDocs configuration
├── README.md                           # This hub file
├── README_Architecture.md              # ← You are here
├── README_Methodology.md               # Statistical methods
├── README_Configuration.md             # Config & data requirements
├── README_Development.md               # Adding content & rules
├── ARCHITECTURE.md                     # Detailed architecture docs
├── DEVELOPMENT_RULES.md                # 20 mandatory coding rules
├── AI_GUIDE.md                         # AI-assisted development guide
│
├── data/
│   ├── tpd_claims.parquet
│   ├── tpd_exposure.parquet
│   └── benchmarks/
│       ├── tpd_industry_benchmark.csv
│       └── tpd_occ_benchmark.csv
│
├── pipeline/
│   ├── loaders/           # Data ingestion (2 modules)
│   ├── transforms/        # Business logic (5 modules)
│   ├── helpers/           # Shared utilities (11 modules)
│   ├── sections/          # Section config (5 modules)
│   └── slides/            # UI renderers (17 slides)
│
├── wiki_build/            # Auto-generated wiki source
├── wiki_site/             # Built static wiki site
└── .github/workflows/     # GitHub Actions (Qwen automation)
```
