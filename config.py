"""Application configuration using pydantic-settings.

Reads settings from environment variables and a .env file.
"""

from __future__ import annotations


from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application-wide settings loaded from environment / .env file.

    Attributes:
        chroma_persist_directory: Path to the ChromaDB persistence directory.
        embedding_model_name: HuggingFace sentence-transformers model name.
        ingestion_schedule_hours: Hours between standards re-ingestion.
        standards_sources_file: Path to the YAML list of standards sources.
        gap_rules_path: Path to the JSON gap-rules file.
        questionnaire_path: Path to the JSON questionnaire file.
        llm_base_url: Base URL of the LMStudio OpenAI-compatible API.
        llm_model: Model name to use (must match a loaded LMStudio model).
        llm_timeout: Request timeout in seconds.
        llm_max_retries: Maximum retry attempts for failed LLM requests.
        llm_temperature: Sampling temperature (0.0 = deterministic).
        llm_max_tokens: Maximum tokens in the LLM response.
    """

    chroma_persist_directory: str = "data/chroma_db"
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    ingestion_schedule_hours: int = 168
    standards_sources_file: str = "standards_ingestion/sources.yaml"
    gap_rules_path: str = "data/gap_rules.json"
    questionnaire_path: str = "data/questionnaire.json"
    llm_base_url: str = "http://192.168.1.59:1234/v1"
    llm_model: str = "qwen/qwen3.6-35b-a3b"
    llm_timeout: int = 60
    llm_max_retries: int = 2
    llm_temperature: float = 0.3
    llm_max_tokens: int = 4096

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton instance — importable anywhere in the project
settings = Settings()
