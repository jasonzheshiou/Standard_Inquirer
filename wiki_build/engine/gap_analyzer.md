# Gap Analyzer

The `engine.gap_analyzer` module contains the core gap-analysis engine. It evaluates user questionnaire answers against CPS 230 gap rules and produces severity-ranked findings.

## Functions

### `analyze(answers: dict[str, Any]) -> list[GapFinding]`

Run the full gap analysis against user answers.

**Parameters:**
- `answers` — Mapping of question ID to user answer value.

**Returns:** List of `GapFinding` objects sorted by severity (high → medium → low).

**Flow:**
1. Load gap rules via `load_gap_rules()`
2. Load all questions via `get_all_questions()`
3. For each rule, evaluate against answers via `evaluate_rule()`
4. For triggered rules, create `GapFinding` objects
5. Attempt ChromaDB evidence enrichment via `get_evidence_text()`
6. Sort findings by severity and return

```python
from engine.gap_analyzer import analyze

answers = {
    "q_risk_governance": "No",
    "q_model_inventory": "Yes",
    # ...
}
findings = analyze(answers)
# findings: list[GapFinding] sorted by severity
```

### `evaluate_rule(rule: GapRule, answers: dict[str, Any]) -> bool`

Evaluate a single gap rule against user answers. Returns `True` if a gap **exists** (the rule is triggered).

**Supported logic operators:**

| Operator | Description |
|----------|-------------|
| `equals` | User answer must equal `rule.gap_condition.value` |

**Flow:**
1. Extract `question_id` and `logic` from `rule.gap_condition`
2. Look up the user's answer
3. If no answer exists, return `False` (no gap)
4. Apply the logic operator
5. Return `True` if the gap condition is met

```python
from engine.gap_analyzer import evaluate_rule
from engine.schemas import GapRule

rule = GapRule(...)
answers = {"q_risk_governance": "No"}
is_gap = evaluate_rule(rule, answers)  # True if gap exists
```

### `get_evidence_text(requirement_description: str, collection: Any = None, k: int = 1) -> str`

Retrieve evidence text via ChromaDB similarity search.

**Parameters:**
- `requirement_description` — Text to search for (the rule description)
- `collection` — ChromaDB collection instance. If `None`, returns `""`
- `k` — Number of top results to retrieve

**Returns:** Text of the top matching document, or `""` if unavailable.

**Flow:**
1. If collection is `None`, return `""`
2. Encode `requirement_description` using the configured sentence-transformers model
3. Query ChromaDB collection with the embedding
4. Return the top document text

**Note:** LLM-based evidence generation is a future enhancement — this function currently relies on ChromaDB vector similarity only.

### `load_gap_rules(path: str | None = None) -> list[GapRule]`

Load and validate gap rules from JSON.

**Parameters:**
- `path` — Optional override path. Defaults to `settings.gap_rules_path`.

**Returns:** List of validated `GapRule` objects.

**Supported formats:**
- Bare list: `[ {...}, {...} ]`
- Wrapper object: `{ "requirements": [ {...}, {...} ] }`

```python
from engine.gap_analyzer import load_gap_rules

rules = load_gap_rules()  # Uses default path from settings
rules = load_gap_rules("/custom/path/gap_rules.json")  # Custom path
```

## Severity Ordering

Findings are sorted using the internal `_severity_key()` function:

| Severity | Key |
|----------|-----|
| high | 0 |
| medium | 1 |
| low | 2 |
| other | 99 |

## Error Handling

The module defines `GapAnalysisError` for loading/validation failures:

```python
from engine.gap_analyzer import GapAnalysisError

try:
    rules = load_gap_rules()
except GapAnalysisError as exc:
    logger.error(f"Failed to load gap rules: {exc}")
```
