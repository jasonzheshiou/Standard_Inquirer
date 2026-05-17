# Compliance Registry

The compliance registry is the core knowledge base of the tool. It maps regulatory standards to concrete, testable gap rules that are evaluated against user questionnaire answers.

## How It Works

Each regulatory standard is represented by one or more **gap rules**. A gap rule defines:

1. **The requirement** — which clause of the standard applies
2. **The condition** — what questionnaire answer triggers a gap
3. **The severity** — how critical the gap is (high / medium / low)
4. **The mitigation** — suggested remediation steps

## Registry Structure

Rules are stored in `data/gap_rules.json`:

```json
{
  "standards_version": "2025-04-01",
  "requirements": [
    {
      "id": "CPS230-6",
      "standard": "CPS 230",
      "clause": "Paragraph 6",
      "description": "The Board must establish a documented model risk governance framework.",
      "category": "Board Oversight",
      "gap_condition": {
        "question_id": "q_risk_governance",
        "logic": "equals",
        "value": "No"
      },
      "severity_if_gap": "high",
      "mitigation": "Establish a formal model risk governance framework...",
      "reference_url": "https://www.apra.gov.au/prudential-standards/cps-230"
    }
  ]
}
```

## Adding New Standards

To add a new regulatory standard (e.g., APRA CPS 220):

### 1. Add gap rules to `data/gap_rules.json`

```json
{
  "id": "CPS220-1",
  "standard": "CPS 220",
  "clause": "Paragraph 1",
  "description": "The Board must approve a risk management strategy.",
  "category": "Risk Strategy",
  "gap_condition": {
    "question_id": "q_risk_strategy",
    "logic": "equals",
    "value": "No"
  },
  "severity_if_gap": "high",
  "mitigation": "Draft and obtain Board approval for a documented risk management strategy.",
  "reference_url": "https://www.apra.gov.au/prudential-standards/cps-220"
}
```

### 2. Add corresponding questionnaire questions to `data/questionnaire.json`

```json
{
  "id": "q_risk_strategy",
  "text": "Has the Board approved a risk management strategy?",
  "type": "boolean",
  "default": null
}
```

### 3. Add the standard to the ingestion sources

Edit `standards_ingestion/sources.yaml`:

```yaml
sources:
  - name: "CPS 220"
    url: "https://www.apra.gov.au/prudential-standards/cps-220"
    category: "APRA"
```

### 4. Update the compliance registry table

Update `wiki_build/index.md` to reflect the new standard's status.

## Extending the System

### Adding New Logic Operators

The `evaluate_rule()` function in `engine/gap_analyzer.py` currently supports:

- **`equals`** — exact match against the expected value

To add new operators, extend the function:

```python
if logic == "regex":
    import re
    expected = condition.get("pattern", "")
    return bool(re.search(expected, str(user_answer)))
```

### Adding Threshold-Based Rules

For rules that require numerical thresholds (e.g., "validation coverage > 80%"):

1. Add a new question type with numeric input
2. Add a `threshold` logic operator to `evaluate_rule()`
3. Define the threshold in `gap_condition`

### Adding LLM-Based Evidence

The `get_evidence_text()` function currently uses ChromaDB vector similarity. To add LLM-based evidence:

1. Integrate an LLM client (e.g., OpenAI, local model)
2. Pass the rule description and ChromaDB results to the LLM
3. Return a generated summary as `evidence_text`
