"""Pydantic data models for the Compliance Gap Analyser engine.

All models support JSON round-trip serialization via
``model_dump_json()`` and ``model_validate_json()``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GapRule(BaseModel):
    """A single gap-analysis rule tied to a regulatory standard.

    The ``gap_condition`` field is a plain ``dict`` to allow flexible
    logic definitions (e.g. field-match, regex, threshold) without
    locking into a rigid sub-model.

    Attributes:
        id: Unique rule identifier.
        standard: Name of the governing standard or regulation.
        clause: Specific clause or section reference.
        description: Human-readable rule description.
        category: Logical grouping (e.g. "Model Risk", "Documentation").
        gap_condition: Condition dict that determines when a gap exists.
        severity_if_gap: Severity level when the gap is triggered.
        mitigation: Suggested mitigation for the gap.
        reference_url: URL to the full standard text.
    """

    id: str = Field(..., min_length=1, description="Unique rule identifier.")
    standard: str = Field(..., description="Governing standard or regulation name.")
    clause: str = Field(..., description="Specific clause or section reference.")
    description: str = Field(..., description="Human-readable rule description.")
    category: str = Field(..., description="Logical grouping category.")
    gap_condition: dict[str, Any] = Field(
        ..., description="Condition dict determining when a gap exists."
    )
    severity_if_gap: str = Field(..., description="Severity level when gap is triggered.")
    mitigation: str = Field(..., description="Suggested mitigation for the gap.")
    reference_url: str = Field(..., description="URL to the full standard text.")


class Question(BaseModel):
    """A single questionnaire question.

    Attributes:
        id: Unique question identifier.
        text: The question text presented to the user.
        type: Answer type (e.g. "boolean", "text", "choice").
        default: Default value for the answer.
        options: Allowed options for choice-type questions (``None`` if not applicable).
        source_standard: Standard name (e.g. "CPS 230", "LPS 115").
        source_clause: Specific clause reference (e.g. "Paragraph 27(b)").
        confidence: LLM confidence score 0.0-1.0.
        applies_to_standard: For gap engine matching.
    """

    id: str = Field(..., description="Unique question identifier.")
    text: str = Field(..., description="Question text presented to the user.")
    type: str = Field(..., description="Answer type (boolean, text, choice, etc.).")
    default: Any = Field(None, description="Default answer value.")
    options: list[str] | None = Field(None, description="Allowed options for choice questions.")
    source_standard: str | None = Field(None, description="Standard name (e.g. CPS 230, LPS 115).")
    source_clause: str | None = Field(None, description="Specific clause reference (e.g. Paragraph 27(b)).")
    confidence: float | None = Field(None, description="LLM confidence score 0.0-1.0.")
    applies_to_standard: str | None = Field(None, description="For gap engine matching.")


class QuestionSection(BaseModel):
    """A group of related questionnaire questions.

    Attributes:
        title: Section heading.
        questions: Ordered list of questions in this section.
    """

    title: str = Field(..., description="Section heading.")
    questions: list[Question] = Field(..., min_length=1, description="Questions in this section.")


class Answer(BaseModel):
    """A single user answer to a questionnaire question.

    Attributes:
        question_id: The question this answer corresponds to.
        value: The user's answer value.
    """

    question_id: str = Field(..., description="Question this answer corresponds to.")
    value: Any = Field(..., description="The user's answer value.")


class GapFinding(BaseModel):
    """A finding produced when a gap rule is triggered.

    Attributes:
        requirement_id: The rule/requirement that was violated.
        clause_reference: The specific clause reference from the standard.
        question: The questionnaire question related to this finding.
        user_answer: The user's answer that led to the gap.
        gap_severity: Severity level of the gap.
        mitigation: Suggested mitigation text.
        evidence_text: Optional free-text evidence or explanation.
        llm_explanation: Optional LLM-generated explanation for this finding.
    """

    requirement_id: str = Field(..., description="Rule/requirement that was violated.")
    clause_reference: str = Field(..., description="Specific clause reference from the standard.")
    question: str = Field(..., description="Questionnaire question related to this finding.")
    user_answer: Any = Field(..., description="User's answer that led to the gap.")
    gap_severity: str = Field(..., description="Severity level of the gap.")
    mitigation: str = Field(..., description="Suggested mitigation text.")
    evidence_text: str = Field(
        default="", description="Optional free-text evidence or explanation."
    )
    llm_explanation: str | None = Field(None, description="Optional LLM-generated explanation for this finding.")


class Questionnaire(BaseModel):
    """A full questionnaire composed of multiple sections.

    Attributes:
        sections: Ordered list of question sections.
        generated_by: "llm" or "manual".
        generated_at: ISO timestamp of generation.
        organization_type: Org type used for generation.
        user_input: Original free-text input.
    """

    sections: list[QuestionSection] = Field(..., min_length=1, description="Ordered list of question sections.")
    generated_by: str | None = Field(None, description="Generation source: 'llm' or 'manual'.")
    generated_at: str | None = Field(None, description="ISO timestamp of generation.")
    organization_type: str | None = Field(None, description="Organization type used for generation.")
    user_input: str | None = Field(None, description="Original free-text input.")


class StandardsSource(BaseModel):
    """A single external standards source to ingest.

    Attributes:
        name: Human-readable source name.
        url: URL where the standard document can be fetched.
        category: Category tag (e.g. "APRA", "ASX").
        expected_last_modified: Optional ISO-8601 date for freshness checks.
    """

    name: str = Field(..., description="Human-readable source name.")
    url: str = Field(..., description="URL to fetch the standard document.")
    category: str = Field(..., description="Category tag (e.g. APRA, ASX).")
    expected_last_modified: str | None = Field(
        None, description="Optional ISO-8601 date for freshness checks."
    )
