# TPD Dashboard — Configuration

> Global parameters, data requirements, and benchmark specifications.

---

## Global Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `min_cohort_size` | 30 | Minimum exposure years for incidence rate |
| `confidence_level` | 0.95 | Confidence level for A/E ratio intervals |
| `full_credibility_threshold` | 1082.41 | Exposure years for full credibility (Z=1.0) |
| `scale_factor` | 1000 | Scale factor for incidence rates (per 1,000) |

---

## Data Requirements

### tpd_claims.parquet

| Column | Type | Description |
|--------|------|-------------|
| ClaimID | string | Unique claim identifier |
| PolicyID | string | Link to policy |
| InsuredID | string | Unique insured identifier |
| ClaimOnsetDate | datetime | Date of disability onset |
| ClaimOutcome | string | Accepted/Declined/Withdrawn/Pending |
| PrimaryDiagnosisCategory | string | Diagnosis category |
| AttainedAgeAtOnset | int | Age at claim onset |
| Gender | string | Male/Female |
| OccupationClass | string | Occupation class |
| BenefitAmount | float | Benefit paid |
| TerminationReason | string | Reason for termination (if applicable) |

### tpd_exposure.parquet

| Column | Type | Description |
|--------|------|-------------|
| PolicyID | string | Unique policy identifier |
| InsuredID | string | Unique insured identifier |
| DateOfBirth | datetime | Date of birth |
| Gender | string | Male/Female |
| OccupationClass | string | Occupation class |
| PolicyIssueDate | datetime | Policy start date |
| PolicyExpiryDate | datetime | Policy end date |
| SumInsured | float | TPD benefit amount |
| AnnualPremium | float | Annual premium paid |
| PolicyStatus | string | In Force/Lapsed/Claimed/etc. |

---

## Benchmark Files (Optional)

Place in `data/benchmarks/` for A/E analysis:

- `tpd_industry_benchmark.csv` — Rates by age, gender, occupation
- `tpd_occ_benchmark.csv` — Occupation class multipliers
