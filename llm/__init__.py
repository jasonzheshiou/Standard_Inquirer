"""LLM integration for Compliance Gap Analyser.

Features:
    - ChromaDB-backed semantic retrieval of regulatory standards
    - LLM-powered questionnaire generation with schema validation
    - Fallback to default questionnaire when LLM is unavailable
    - Session persistence (save / load / list / delete)

Shared dependencies:
    - engine.gap_analyzer (analyze function)
    - engine.schemas (Questionnaire, Question, QuestionSection models)
    - standards_ingestion.embedder (ChromaDB client)
"""

from llm.question_generator import (
    QuestionGenerationError,
    generate_questionnaire,
)
from llm.answer_analyzer import enrich_findings
from llm.session import delete_session
from llm.session import list_sessions
from llm.session import load_session
from llm.session import save_session

__all__ = [
    "QuestionGenerationError",
    "delete_session",
    "enrich_findings",
    "generate_questionnaire",
    "list_sessions",
    "load_session",
    "save_session",
]
