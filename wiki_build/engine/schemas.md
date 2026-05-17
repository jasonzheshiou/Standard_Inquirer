# Schemas

The `engine.schemas` module defines all Pydantic data models used throughout the Compliance Gap Analyser. Every model supports JSON round-trip serialization via `model_dump_json()` and `model_validate_json()`.

## Models

### GapRule

A single gap-analysis rule tied to a regulatory standard.

```python
class GapRule(BaseModel):
    id: str                          # Unique rule identifier
    standard: str                    # Governing standard name
    clause: str                      # Clause/section reference
    description: str                 # Human-readable description
    category: str                    # Logical grouping (e.g. "Board Oversight")
    gap_condition: dict[str, Any]    # Condition dict (question_id, logic, value)
    severity_if_gap: str             # "high", "medium", or "low"
    mitigation: str                  # Suggested remediation
    reference_url: str               # URL to full standard text
```

**Example:**

```python
rule = GapRule(
    id="CPS230-6",
    standard="CPS 230",
    clause="Paragraph 6",
    description="The Board must establish a documented model risk governance framework.",
    category="Board Oversight",
    gap_condition={"question_id": "q_risk_governance", "logic": "equals", "value": "No"},
    severity_if_gap="high",
    mitigation="Establish a formal model risk governance framework...",
    reference_url="https://www.apra.gov.au/prudential-standards/cps-230",
)
```

### Question

A single questionnaire question.

```python
class Question(BaseModel):
    id: str            # Unique question identifier
    text: str          # Question text
    type: str          # "boolean", "multi_choice", or "text"
    default: Any       # Default value
    options: list[str] | None  # Allowed options for choice questions
```

### QuestionSection

A group of related questionnaire questions.

```python
class QuestionSection(BaseModel):
    title: str            # Section heading
    questions: list[Question]  # Ordered list of questions
```

### Answer

A single user answer to a questionnaire question.

```python
class Answer(BaseModel):
    question_id: str  # Question this answer corresponds to
    value: Any        # The user's answer value
```

### GapFinding

A finding produced when a gap rule is triggered.

```python
class GapFinding(BaseModel):
    requirement_id: str    # Rule/requirement that was violated
    clause_reference: str  # Specific clause reference
    question: str          # Related questionnaire question text
    user_answer: Any       # User's answer that led to the gap
    gap_severity: str      # Severity level
    mitigation: str        # Suggested mitigation text
    evidence_text: str     # Optional ChromaDB evidence
```

### Questionnaire

A full questionnaire composed of multiple sections.

```python
class Questionnaire(BaseModel):
    sections: list[QuestionSection]  # Ordered list of sections
```

### StandardsSource

A single external standards source to ingest.

```python
class StandardsSource(BaseModel):
    name: str                    # Human-readable source name
    url: str                     # URL to fetch the document
    category: str                # Category tag (e.g. "APRA", "ASX")
    expected_last_modified: str | None  # Optional ISO-8601 freshness date
```

## Error Classes

Each module defines its own exception:

| Exception | Module | Raised When |
|-----------|--------|-------------|
| `GapAnalysisError` | `gap_analyzer` | Gap rules cannot be loaded or validated |
| `QuestionnaireError` | `questionnaire` | Questionnaire cannot be loaded or validated |
