# Questionnaire

The `engine.questionnaire` module provides functions to load, validate, and query the CPS 230 questionnaire stored as JSON. All loaders cache results via Streamlit's `@st.cache_data` when available.

## Functions

### `load_questionnaire(path: str | None = None) -> Questionnaire`

Load the questionnaire from JSON and validate it against the `Questionnaire` schema.

**Parameters:**
- `path` — Optional override path. Defaults to `settings.questionnaire_path`.

**Returns:** A validated `Questionnaire` model.

**Raises:** `QuestionnaireError` if loading or validation fails.

```python
from engine.questionnaire import load_questionnaire

qa = load_questionnaire()  # Uses default path
qa = load_questionnaire("/custom/questionnaire.json")  # Custom path
```

### `get_all_questions() -> list[Question]`

Return a flat list of all questions across every section.

**Returns:** List of `Question` objects in document order.

```python
from engine.questionnaire import get_all_questions

all_qs = get_all_questions()
# all_qs: [Question(id='q_risk_appetite', ...), Question(id='q_risk_governance', ...), ...]
```

### `get_sections() -> list[QuestionSection]`

Return the list of question sections with questions grouped by section.

**Returns:** List of `QuestionSection` objects in document order.

```python
from engine.questionnaire import get_sections

sections = get_sections()
for section in sections:
    print(f"=== {section.title} ===")
    for q in section.questions:
        print(f"  {q.id}: {q.text}")
```

## Questionnaire Structure

The questionnaire is stored in `data/questionnaire.json` and organized into 4 sections with 8 total questions:

### Section 1: Board & Senior Management Oversight
| ID | Question |
|----|----------|
| `q_risk_appetite` | Has the Board approved a documented risk appetite statement that covers model risk? |
| `q_risk_governance` | Is there a documented model risk governance framework approved by the Board? |

### Section 2: Model Inventory & Validation
| ID | Question |
|----|----------|
| `q_model_inventory` | Does the organisation maintain a comprehensive inventory of all models in use? |
| `q_model_validation` | Are models independently validated before deployment and at least annually thereafter? |

### Section 3: Data Governance
| ID | Question |
|----|----------|
| `q_data_governance` | Is there a documented data governance framework covering model inputs and outputs? |
| `q_documentation` | Are model documentation standards met including assumptions, limitations, and methodology? |

### Section 4: Risk Escalation & Reporting
| ID | Question |
|----|----------|
| `q_escalation` | Is there a documented process for escalating model-related issues to the Board? |
| `q_concentration_risk` | Does the risk framework address concentration risk in model inputs and outputs? |

## Caching

When running within Streamlit, `_load_raw()` is decorated with `@st.cache_data` to avoid re-parsing the JSON file on every call. Outside of Streamlit, a no-op decorator is used.

## Error Handling

The module defines `QuestionnaireError` for loading/validation failures:

```python
from engine.questionnaire import QuestionnaireError

try:
    sections = get_sections()
except QuestionnaireError as exc:
    logger.error(f"Failed to load questionnaire: {exc}")
```
