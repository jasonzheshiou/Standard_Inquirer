# TPD Dashboard — Statistical Methodologies

> Detailed explanation of all statistical methods used in the dashboard.

---

## 1. Incidence Rate Calculation

**Purpose**: Estimate TPD claim rates per 1,000 exposed lives.

**Formula**:
```
Incidence Rate = (Number of Claims / Total Exposure Years) × 1,000
```

**Dimensions**: Age band (5-year groups, capped at 60-64), occupation class, gender, diagnosis, employment status, waiting period, benefit period, distribution channel, smoker status.

**Confidence Intervals**: Normal approximation for large samples:
```
CI = Rate ± z × √(Rate / Exposure)
```

---

## 2. Actual/Expected (A/E) Ratio Analysis

**Purpose**: Compare actual claim experience against industry benchmarks.

**Expected Claims**:
```
Expected = Σ (Industry Rateᵢ × Exposure Yearsᵢ) / 1,000
```

**A/E Ratio**:
```
A/E = Actual / Expected
```

| A/E Value | Interpretation |
|-----------|---------------|
| 1.0 | Matches industry |
| > 1.0 | Higher claims (worse) |
| < 1.0 | Lower claims (better) |

**Confidence Intervals — Byar's Approximation**:
```
Lower CI = O × (1 - 1/(9O) - z/(3√O))³ / E
Upper CI = (O+1) × (1 - 1/(9(O+1)) + z/(3√(O+1)))³ / E
```

Statistical significance: CI **does not include 1.0**.

---

## 3. Limited Fluctuation (Classical) Credibility

**Purpose**: Weight observed A/E ratios by reliability.

**Credibility Factor**:
```
Z = min(n / n_full, 1.0)
```

**Full Credibility Threshold** (default 1,082.41):
```
n_full = (z_{α/2} / k)² = (1.96 / 0.05)² ≈ 1,537
```

**Credibility-Weighted Rate**:
```
Weighted = Z × Observed + (1 - Z) × Industry
```

| Z Range | Interpretation |
|---------|---------------|
| 0.0 – 0.3 | Very low → rely on industry |
| 0.3 – 0.6 | Partial → blend observed & industry |
| 0.6 – 0.9 | High → mostly observed |
| 0.9 – 1.0 | Full → use observed |

---

## 4. Chi-Squared Goodness of Fit

```
χ² = Σ (Observedᵢ - Expectedᵢ)² / Expectedᵢ
```

| p-value | Interpretation |
|---------|---------------|
| p < 0.05 | Significant difference from industry |
| p ≥ 0.05 | Consistent with industry |

---

## 5. Mann-Kendall Trend Test

Non-parametric test for monotonic trends in time series.

**Output**:
- **Tau (τ)**: Trend strength (-1 to +1)
- **p-value**: Significance
- **Direction**: Increasing, Decreasing, or No Trend

---

## 6. Generalized Linear Model (GLM)

**Specification**:
- Distribution: Poisson
- Link: Log
- Offset: log(Exposure)
- Features: Age, occupation, gender, diagnosis, employment, smoker, channel

```
log(E[Claims]) = β₀ + β₁X₁ + ... + βₖXₖ + log(Exposure)
```

**Output**: Coefficients, feature importance, predicted vs actual A/E.

---

## 7. Random Forest

- Algorithm: Random Forest Regressor (scikit-learn)
- Target: A/E ratio
- Hyperparameters: 200 estimators, default max_depth
- Output: Feature importance, partial dependence plots, OOB error

---

## 8. Gradient Boosting Machine (GBM)

- Algorithm: Gradient Boosting Regressor
- Target: A/E ratio
- Hyperparameters: 300 estimators, learning_rate=0.05, max_depth=4
- Output: Feature rankings, predicted A/E, residual analysis

---

## 9. Model-based Recursive Partitioning (MOB)

Discovers natural segments with distinct A/E patterns.

**Algorithm**:
1. Fit base GLM to full dataset
2. Test for parameter instability across features
3. If significant, find optimal split point
4. Recursively repeat on each partition
5. Stop when no further significant splits or min sample reached

**Parameters**:
- max_depth: 4
- min_samples_leaf: 30
- min_samples_split: 60

**Output**: Terminal segments with A/E multipliers, split rules, segment sizes.

---

## 10. Final Assumption Setting

```
Final Assumptionᵢ = Industry Baselineᵢ × MOB A/E Multiplierᵢ
```

**Process**:
1. Start with industry benchmarks
2. Apply ML-derived adjustments (GLM/RF/GBM ensemble)
3. Apply MOB segment multipliers
4. Apply credibility weighting
5. Export final assumption table

**Output**: CSV with final assumptions by age, occupation, gender.
