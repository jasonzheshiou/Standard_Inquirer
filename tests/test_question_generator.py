"""Comprehensive tests for llm/question_generator.py.

Covers:
- _load_sources(): YAML loading, missing file, invalid YAML
- _retrieve_relevant_standards(): ChromaDB retrieval with mocked client
- _build_prompt(): output structure, standards context
- _parse_questionnaire(): JSON validation, markdown fences, schema errors
- _default_questionnaire(): structure and fields
- generate_questionnaire(): full flow with LLM success, failure, fallback
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
import responses
import yaml

from llm.question_generator import (
    MAX_RETRIES,
    MAX_STANDARDS,
    QuestionGenerationError,
    _build_prompt,
    _default_questionnaire,
    _load_sources,
    _parse_questionnaire,
    _retrieve_relevant_standards,
    generate_questionnaire,
)
from llm.client import LLMClient, LLMConnectionError, LLMGenerationError, LLMTimeoutError
from engine.schemas import Question, Questionnaire, QuestionSection


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_valid_questionnaire_json() -> str:
    """Return a valid questionnaire JSON string for testing."""
    data = {
        "sections": [
            {
                "title": "Operational Risk",
                "questions": [
                    {
                        "id": "CPS230_1_01",
                        "text": "Does the org have risk framework?",
                        "type": "boolean",
                        "default": False,
                        "options": None,
                        "source_standard": "CPS 230",
                        "source_clause": "Paragraph 1",
                        "confidence": 0.95,
                    }
                ],
            },
            {
                "title": "Capital Adequacy",
                "questions": [
                    {
                        "id": "LPS115_1_01",
                        "text": "Has org calculated risk charge?",
                        "type": "boolean",
                        "default": False,
                        "options": None,
                        "source_standard": "LPS 115",
                        "source_clause": "Paragraph 1",
                        "confidence": 0.90,
                    }
                ],
            },
        ],
        "generated_by": "llm",
        "generated_at": "2026-01-01T00:00:00+00:00",
        "organization_type": "life_insurer",
        "user_input": "Test input",
    }
    return json.dumps(data)


def _make_minimal_valid_questionnaire_json() -> str:
    """Return a minimal valid questionnaire JSON (3 sections, 1 question each)."""
    data = {
        "sections": [
            {"title": "Section A", "questions": [{"id": "A_1_01", "text": "Q1?", "type": "boolean", "default": False}]},
            {"title": "Section B", "questions": [{"id": "B_1_01", "text": "Q2?", "type": "text", "default": None}]},
            {"title": "Section C", "questions": [{"id": "C_1_01", "text": "Q3?", "type": "multi_choice", "default": None, "options": ["X", "Y"]}]},
        ],
    }
    return json.dumps(data)


# ---------------------------------------------------------------------------
# _load_sources tests
# ---------------------------------------------------------------------------


class TestLoadSources:
    """Tests for _load_sources()."""

    def test_returns_list_when_file_exists(self) -> None:
        """Should return a list when sources.yaml exists."""
        result = _load_sources()
        assert isinstance(result, list)

    def test_returns_list_when_file_missing(self) -> None:
        """Should return empty list when sources.yaml is missing."""
        # The file exists in this project, so test by temporarily renaming
        sources_path = Path(__file__).resolve().parent.parent / "standards_ingestion" / "sources.yaml"
        if not sources_path.exists():
            # File genuinely missing - just verify empty list returned
            assert _load_sources() == []
            return

        # Temporarily rename the file
        backup_path = sources_path.with_suffix(".yaml.bak")
        try:
            sources_path.rename(backup_path)
            assert _load_sources() == []
        finally:
            backup_path.rename(sources_path)

    def test_returns_empty_list_on_invalid_yaml(self, tmp_path: Path) -> None:
        """Should return empty list when YAML is malformed."""
        sources_dir = tmp_path / "standards_ingestion"
        sources_dir.mkdir()
        yaml_path = sources_dir / "sources.yaml"
        yaml_path.write_text("{invalid yaml:::", encoding="utf-8")

        # Patch the path constant
        with patch("llm.question_generator.SOURCES_YAML_PATH", yaml_path):
            result = _load_sources()
            assert result == []

    def test_returns_sources_with_required_fields(self) -> None:
        """Each source dict should have name, url, category."""
        sources = _load_sources()
        if not sources:
            pytest.skip("sources.yaml is empty")

        for source in sources:
            assert "name" in source
            assert "url" in source
            assert "category" in source


# ---------------------------------------------------------------------------
# _retrieve_relevant_standards tests
# ---------------------------------------------------------------------------


class TestRetrieveRelevantStandards:
    """Tests for _retrieve_relevant_standards() with mocked ChromaDB."""

    def setup_method(self) -> None:
        """Patch ChromaDB and sources.yaml."""
        self._mock_client = MagicMock()
        self._mock_collection = MagicMock()
        self._mock_collection.name = "standards_collection"
        self._mock_collection.query.return_value = {
            "documents": [["doc1 content", "doc2 content"]],
            "metadatas": [
                [
                    {"standard_name": "CPS 230", "clause": "27(b)", "source_url": "http://example.com"},
                    {"standard_name": "LPS 115", "clause": "1", "source_url": "http://example.com"},
                ]
            ],
            "distances": [[0.1, 0.2]],
        }
        self._mock_client.get_or_create_collection.return_value = self._mock_collection

        # Patch in the embedder module's namespace
        import standards_ingestion.embedder as embedder_mod
        self._orig_init = embedder_mod.init_chroma_client
        self._orig_get = embedder_mod.get_or_create_collection
        embedder_mod.init_chroma_client = MagicMock(return_value=self._mock_client)
        embedder_mod.get_or_create_collection = MagicMock(return_value=self._mock_collection)

        # Create a temp sources.yaml for testing
        self._tmp_dir = tempfile.TemporaryDirectory()
        self._sources_dir = Path(self._tmp_dir.name) / "standards_ingestion"
        self._sources_dir.mkdir(parents=True)
        self._yaml_path = self._sources_dir / "sources.yaml"
        sources_data = {
            "sources": [
                {"name": "CPS 230", "url": "http://example.com/cps230.pdf", "category": "APRA"},
                {"name": "LPS 115", "url": "http://example.com/lps115.pdf", "category": "AASB"},
                {"name": "IFRS 17", "url": "http://example.com/ifrs17.pdf", "category": "IFRS"},
            ]
        }
        with open(self._yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(sources_data, f)

        # Patch SOURCES_YAML_PATH
        self._patch_sources = patch("llm.question_generator.SOURCES_YAML_PATH", self._yaml_path)
        self._patch_sources.start()

    def teardown_method(self) -> None:
        """Restore originals and clean up."""
        import standards_ingestion.embedder as embedder_mod
        embedder_mod.init_chroma_client = self._orig_init
        embedder_mod.get_or_create_collection = self._orig_get
        self._patch_sources.stop()
        self._tmp_dir.cleanup()

    def test_returns_chunks_with_correct_structure(self) -> None:
        """Should return chunks with standard_name, standard_category, clause, document, source_url, distance."""
        result = _retrieve_relevant_standards("test input", "life_insurer")

        assert len(result) == 2
        for chunk in result:
            assert "standard_name" in chunk
            assert "standard_category" in chunk
            assert "clause" in chunk
            assert "document" in chunk
            assert "source_url" in chunk
            assert "distance" in chunk

        assert result[0]["standard_name"] == "CPS 230"
        assert result[0]["standard_category"] == "APRA"
        assert result[0]["clause"] == "27(b)"
        assert result[0]["distance"] == 0.1

    def test_respects_max_standards_limit(self) -> None:
        """Should not return more than MAX_STANDARDS chunks."""
        # Mock ChromaDB to return more results than MAX_STANDARDS
        n = MAX_STANDARDS + 5
        docs = [f"doc{i}" for i in range(n)]
        metas = [{"standard_name": f"STD{i}", "clause": "1", "source_url": ""} for i in range(n)]
        dists = [float(i) for i in range(n)]
        self._mock_collection.query.return_value = {
            "documents": [docs],
            "metadatas": [metas],
            "distances": [dists],
        }

        # Also update sources to include all the mocked standards
        sources_data = {
            "sources": [{"name": f"STD{i}", "url": "http://example.com", "category": "APRA"} for i in range(n)]
        }
        with open(self._yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(sources_data, f)

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert len(result) <= MAX_STANDARDS

    def test_filters_by_org_type(self) -> None:
        """Should filter results by organization type's applicable categories."""
        # life_insurer maps to APRA, AASB, IFRS
        # CPS 230 is APRA -> included
        # LPS 115 is AASB -> included
        result = _retrieve_relevant_standards("test", "life_insurer")
        names = [r["standard_name"] for r in result]
        assert "CPS 230" in names
        assert "LPS 115" in names

    def test_returns_empty_when_no_applicable_sources(self) -> None:
        """Should return empty list when no sources match org type categories."""
        # Create sources with a category that's not in the org_category_map
        sources_data = {
            "sources": [
                {"name": "XYZ Standard", "url": "http://example.com", "category": "UNKNOWN_CAT"},
            ]
        }
        with open(self._yaml_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(sources_data, f)

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert result == []

    def test_deduplicates_standards(self) -> None:
        """Should not return duplicate standard_name entries."""
        # Mock ChromaDB to return the same standard multiple times
        self._mock_collection.query.return_value = {
            "documents": [["doc1", "doc1", "doc2"]],
            "metadatas": [
                [
                    {"standard_name": "CPS 230", "clause": "1", "source_url": ""},
                    {"standard_name": "CPS 230", "clause": "2", "source_url": ""},
                    {"standard_name": "LPS 115", "clause": "1", "source_url": ""},
                ]
            ],
            "distances": [[0.1, 0.2, 0.3]],
        }

        result = _retrieve_relevant_standards("test", "life_insurer")
        names = [r["standard_name"] for r in result]
        assert names.count("CPS 230") == 1

    def test_handles_chromadb_missing_results(self) -> None:
        """Should return empty list when ChromaDB results are missing fields."""
        self._mock_collection.query.return_value = {}

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert result == []

    def test_handles_empty_documents(self) -> None:
        """Should return empty list when ChromaDB returns empty documents."""
        self._mock_collection.query.return_value = {
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert result == []

    def test_handles_missing_standard_name(self) -> None:
        """Should skip entries with missing/empty standard_name."""
        self._mock_collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [
                [
                    {"clause": "1", "source_url": ""},  # No standard_name
                    {"standard_name": "CPS 230", "clause": "1", "source_url": ""},
                ]
            ],
            "distances": [[0.1, 0.2]],
        }

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert len(result) == 1
        assert result[0]["standard_name"] == "CPS 230"

    def test_chromadb_error_returns_empty(self) -> None:
        """ChromaDB exceptions should return empty list, not raise."""
        self._mock_collection.query.side_effect = Exception("ChromaDB down")

        result = _retrieve_relevant_standards("test", "life_insurer")
        assert result == []

    def test_org_type_unknown_defaults_to_all_categories(self) -> None:
        """Unknown org type should default to APRA, AASB, IFRS."""
        result = _retrieve_relevant_standards("test", "unknown_org")
        # Should include CPS 230 (APRA) and LPS 115 (AASB) since both are in default set
        names = [r["standard_name"] for r in result]
        assert "CPS 230" in names


# ---------------------------------------------------------------------------
# _build_prompt tests
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    """Tests for _build_prompt()."""

    def test_returns_tuple_of_two_strings(self) -> None:
        system, user = _build_prompt("test input", "life_insurer", [])
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_system_prompt_contains_instructions(self) -> None:
        system, _ = _build_prompt("test input", "life_insurer", [])
        assert "JSON" in system
        assert "schema" in system.lower() or "SCHEMA" in system
        assert "sections" in system
        assert "questions" in system

    def test_user_prompt_contains_org_type(self) -> None:
        _, user = _build_prompt("test input", "life_insurer", [])
        assert "life_insurer" in user
        assert "test input" in user

    def test_user_prompt_contains_standards_context(self) -> None:
        standards = [
            {
                "standard_name": "CPS 230",
                "standard_category": "APRA",
                "clause": "27(b)",
                "document": "Test document content",
                "source_url": "http://example.com",
                "distance": 0.1,
            }
        ]
        _, user = _build_prompt("test input", "life_insurer", standards)
        assert "CPS 230" in user
        assert "APRA" in user
        assert "27(b)" in user
        assert "Test document content" in user

    def test_standards_context_truncated_at_2000_chars(self) -> None:
        """Document content longer than 2000 chars should be truncated."""
        long_doc = "x" * 3000
        standards = [
            {
                "standard_name": "CPS 230",
                "standard_category": "APRA",
                "clause": "1",
                "document": long_doc,
                "source_url": "",
                "distance": 0.1,
            }
        ]
        _, user = _build_prompt("test", "life_insurer", standards)
        assert "... [truncated]" in user

    def test_no_standards_context_block_when_empty(self) -> None:
        """When no standards provided, context block should be absent."""
        _, user = _build_prompt("test input", "life_insurer", [])
        assert "--- Relevant Standards ---" not in user

    def test_system_prompt_has_output_requirements(self) -> None:
        """System prompt should list output requirements."""
        system, _ = _build_prompt("test", "life_insurer", [])
        for i in range(1, 11):
            assert str(i) in system  # numbered requirements

    def test_multiple_standards_in_context(self) -> None:
        """Multiple standards should each have a numbered context block."""
        standards = [
            {"standard_name": "CPS 230", "standard_category": "APRA", "clause": "1", "document": "Doc1", "source_url": "", "distance": 0.1},
            {"standard_name": "LPS 115", "standard_category": "AASB", "clause": "2", "document": "Doc2", "source_url": "", "distance": 0.2},
            {"standard_name": "IFRS 17", "standard_category": "IFRS", "clause": "3", "document": "Doc3", "source_url": "", "distance": 0.3},
        ]
        _, user = _build_prompt("test", "life_insurer", standards)
        assert "Standard 1: CPS 230" in user
        assert "Standard 2: LPS 115" in user
        assert "Standard 3: IFRS 17" in user
        assert "Doc1" in user
        assert "Doc2" in user
        assert "Doc3" in user


# ---------------------------------------------------------------------------
# _parse_questionnaire tests
# ---------------------------------------------------------------------------


class TestParseQuestionnaire:
    """Tests for _parse_questionnaire()."""

    def test_valid_json_parsed_and_validated(self) -> None:
        """Valid JSON should be parsed and validated successfully."""
        json_str = _make_minimal_valid_questionnaire_json()
        result = _parse_questionnaire(json_str)

        assert isinstance(result, Questionnaire)
        assert len(result.sections) == 3

    def test_valid_json_with_all_fields(self) -> None:
        """JSON with all fields should validate correctly."""
        json_str = _make_valid_questionnaire_json()
        result = _parse_questionnaire(json_str)

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "llm"
        assert result.organization_type == "life_insurer"
        assert result.user_input == "Test input"

    def test_invalid_json_raises_question_generation_error(self) -> None:
        """Invalid JSON should raise QuestionGenerationError."""
        with pytest.raises(QuestionGenerationError, match="invalid JSON"):
            _parse_questionnaire("not json at all")

    def test_invalid_json_syntax_raises_question_generation_error(self) -> None:
        """Malformed JSON syntax should raise QuestionGenerationError."""
        with pytest.raises(QuestionGenerationError, match="invalid JSON"):
            _parse_questionnaire('{"sections": [invalid}')

    def test_valid_json_invalid_schema_raises_question_generation_error(self) -> None:
        """Valid JSON but failing schema validation should raise QuestionGenerationError."""
        # Missing required 'sections' field
        with pytest.raises(QuestionGenerationError, match="schema validation"):
            _parse_questionnaire(json.dumps({"not_sections": []}))

    def test_sections_empty_raises_question_generation_error(self) -> None:
        """Empty sections list should fail schema validation."""
        with pytest.raises(QuestionGenerationError, match="schema validation"):
            _parse_questionnaire(json.dumps({"sections": []}))

    def test_section_without_questions_raises_error(self) -> None:
        """Section without questions should fail schema validation."""
        data = {"sections": [{"title": "Empty Section", "questions": []}]}
        with pytest.raises(QuestionGenerationError, match="schema validation"):
            _parse_questionnaire(json.dumps(data))

    def test_question_without_required_fields_raises_error(self) -> None:
        """Question missing required fields should fail schema validation."""
        data = {
            "sections": [
                {"title": "Section", "questions": [{"id": "Q1"}]}  # missing text, type
            ]
        }
        with pytest.raises(QuestionGenerationError, match="schema validation"):
            _parse_questionnaire(json.dumps(data))

    def test_markdown_code_fences_stripped(self) -> None:
        """JSON wrapped in markdown code fences should be cleaned."""
        json_str = _make_minimal_valid_questionnaire_json()
        fenced = f"```json\n{json_str}\n```"
        result = _parse_questionnaire(fenced)

        assert isinstance(result, Questionnaire)
        assert len(result.sections) == 3

    def test_plain_code_fences_stripped(self) -> None:
        """Plain ``` fences (no language tag) should also be stripped."""
        json_str = _make_minimal_valid_questionnaire_json()
        fenced = f"```\n{json_str}\n```"
        result = _parse_questionnaire(fenced)

        assert isinstance(result, Questionnaire)

    def test_trailing_text_after_json_stripped(self) -> None:
        """Trailing text after JSON should be handled gracefully."""
        json_str = _make_minimal_valid_questionnaire_json()
        with_trailing = f"{json_str}\n\nThis is trailing text that should be ignored."
        result = _parse_questionnaire(with_trailing)

        assert isinstance(result, Questionnaire)

    def test_whitespace_around_json_handled(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        json_str = _make_minimal_valid_questionnaire_json()
        padded = f"\n\n  {json_str}  \n\n"
        result = _parse_questionnaire(padded)

        assert isinstance(result, Questionnaire)

    def test_multi_choice_with_options_validates(self) -> None:
        """Multi-choice question with options should validate."""
        data = {
            "sections": [
                {
                    "title": "Section",
                    "questions": [
                        {
                            "id": "Q1",
                            "text": "Question?",
                            "type": "multi_choice",
                            "options": ["A", "B", "C"],
                        }
                    ],
                }
            ]
        }
        result = _parse_questionnaire(json.dumps(data))
        assert result.sections[0].questions[0].options == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# _default_questionnaire tests
# ---------------------------------------------------------------------------


class TestDefaultQuestionnaire:
    """Tests for _default_questionnaire()."""

    def test_returns_questionnaire(self) -> None:
        result = _default_questionnaire("life_insurer", "Test input")
        assert isinstance(result, Questionnaire)

    def test_has_three_sections(self) -> None:
        result = _default_questionnaire("life_insurer")
        assert len(result.sections) == 3

    def test_section_titles(self) -> None:
        result = _default_questionnaire("life_insurer")
        titles = [s.title for s in result.sections]
        assert "Operational Risk Management (CPS 230)" in titles
        assert "Insurance Risk Charge (LPS 115)" in titles
        assert "Insurance Contracts (AASB 17)" in titles

    def test_total_questions(self) -> None:
        result = _default_questionnaire("life_insurer")
        total = sum(len(s.questions) for s in result.sections)
        assert total == 8  # 3 + 2 + 3

    def test_first_section_questions(self) -> None:
        result = _default_questionnaire("life_insurer")
        ops_section = result.sections[0]
        assert ops_section.title == "Operational Risk Management (CPS 230)"
        assert len(ops_section.questions) == 3

        q = ops_section.questions[0]
        assert q.id == "CPS230_1_01"
        assert q.type == "boolean"
        assert q.default is False
        assert q.source_standard == "CPS 230 — Operational Risk Management"
        assert q.source_clause == "Paragraph 1"
        assert q.confidence == 0.95

    def test_metadata_fields_set(self) -> None:
        result = _default_questionnaire("life_insurer", "Test description")
        assert result.generated_by == "fallback"
        assert result.organization_type == "life_insurer"
        assert result.user_input == "Test description"
        assert result.generated_at is not None

    def test_multi_choice_question_has_options(self) -> None:
        result = _default_questionnaire("life_insurer")
        # AASB 17 section has a multi_choice question
        aasb_section = result.sections[2]
        multi_choice_q = aasb_section.questions[1]
        assert multi_choice_q.type == "multi_choice"
        assert multi_choice_q.options is not None
        assert "GMM" in multi_choice_q.options
        assert "PAA" in multi_choice_q.options
        assert "VFA" in multi_choice_q.options


# ---------------------------------------------------------------------------
# generate_questionnaire integration tests
# ---------------------------------------------------------------------------


class TestGenerateQuestionnaire:
    """Tests for generate_questionnaire() with mocked dependencies."""

    def setup_method(self) -> None:
        """Create a mock LLMClient."""
        self._mock_client = MagicMock(spec=LLMClient)
        self._mock_client.is_available.return_value = True

    def test_successful_generation_returns_questionnaire(self) -> None:
        """Successful LLM call should return a validated Questionnaire."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert len(result.sections) == 3
        self._mock_client.generate.assert_called_once()

    def test_calls_chroma_retrieval(self) -> None:
        """Should call _retrieve_relevant_standards with correct parameters."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        with patch("llm.question_generator._retrieve_relevant_standards") as mock_retrieve:
            mock_retrieve.return_value = []
            generate_questionnaire(
                user_input="Test input",
                organization_type="life_insurer",
                llm_client=self._mock_client,
            )

            mock_retrieve.assert_called_once_with("Test input", "life_insurer", k=10)

    def test_llm_unavailable_returns_default(self) -> None:
        """LLM unavailable should return default questionnaire."""
        self._mock_client.is_available.return_value = False

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "fallback"
        assert self._mock_client.generate.call_count == 0

    def test_llm_failure_all_retries_falls_back(self) -> None:
        """All LLM failures should fall back to default questionnaire."""
        self._mock_client.is_available.return_value = True
        self._mock_client.generate.side_effect = LLMConnectionError("http://test/v1", "Connection refused")

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "fallback"
        # Should have been called MAX_RETRIES + 1 times
        assert self._mock_client.generate.call_count == MAX_RETRIES + 1

    def test_json_validation_failure_retries(self) -> None:
        """JSON validation failure should retry the LLM call."""
        # First call returns invalid JSON, second call returns valid
        self._mock_client.is_available.return_value = True
        self._mock_client.generate.side_effect = [
            "not valid json",  # First attempt: invalid JSON
            _make_minimal_valid_questionnaire_json(),  # Second attempt: valid
        ]

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert self._mock_client.generate.call_count == 2

    def test_json_validation_failure_all_retries_falls_back(self) -> None:
        """All JSON validation failures should fall back to default."""
        self._mock_client.is_available.return_value = True
        self._mock_client.generate.side_effect = ["invalid", "also invalid", "still invalid"]

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "fallback"
        assert self._mock_client.generate.call_count == MAX_RETRIES + 1

    def test_timeout_error_falls_back(self) -> None:
        """LLMTimeoutError should trigger fallback."""
        self._mock_client.is_available.return_value = True
        self._mock_client.generate.side_effect = LLMTimeoutError("http://test/v1", 60.0)

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "fallback"

    def test_generation_error_falls_back(self) -> None:
        """LLMGenerationError should trigger fallback."""
        self._mock_client.is_available.return_value = True
        self._mock_client.generate.side_effect = LLMGenerationError(500, "Model error")

        result = generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert isinstance(result, Questionnaire)
        assert result.generated_by == "fallback"

    def test_creates_default_llm_client_when_none_provided(self) -> None:
        """When llm_client is None, should create a default LLMClient."""
        json_str = _make_minimal_valid_questionnaire_json()

        with patch("llm.question_generator.LLMClient") as MockClient:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = False
            MockClient.return_value = mock_instance

            generate_questionnaire(
                user_input="Test input",
                organization_type="life_insurer",
            )

            MockClient.assert_called_once()
            # Falls back because is_available returns False
            assert MockClient.return_value.generate.call_count == 0

    def test_prompt_structure_with_standards(self) -> None:
        """Should build prompt with retrieved standards context."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        standards = [
            {
                "standard_name": "CPS 230",
                "standard_category": "APRA",
                "clause": "27(b)",
                "document": "Test content",
                "source_url": "http://example.com",
                "distance": 0.1,
            }
        ]

        with patch("llm.question_generator._retrieve_relevant_standards") as mock_retrieve:
            mock_retrieve.return_value = standards
            generate_questionnaire(
                user_input="Test input",
                organization_type="life_insurer",
                llm_client=self._mock_client,
            )

            # Verify generate was called with correct prompt args
            call_args = self._mock_client.generate.call_args
            assert call_args is not None
            # Check the user prompt contains the standard
            user_prompt = call_args[1]["prompt"]
            assert "CPS 230" in user_prompt
            assert "APRA" in user_prompt
            assert "Test content" in user_prompt

    def test_response_format_json_object_passed(self) -> None:
        """Should pass response_format={type: json_object} to LLM."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        generate_questionnaire(
            user_input="Test input",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        call_kwargs = self._mock_client.generate.call_args[1]
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_empty_standards_produces_prompt_without_context(self) -> None:
        """When no standards retrieved, prompt should still be built."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        with patch("llm.question_generator._retrieve_relevant_standards") as mock_retrieve:
            mock_retrieve.return_value = []
            generate_questionnaire(
                user_input="Test input",
                organization_type="life_insurer",
                llm_client=self._mock_client,
            )

            call_args = self._mock_client.generate.call_args
            assert call_args is not None
            user_prompt = call_args[1]["prompt"]
            assert "Test input" in user_prompt
            assert "life_insurer" in user_prompt

    def test_questionnaire_has_correct_section_count(self) -> None:
        """Generated questionnaire should have at least 3 sections."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        result = generate_questionnaire(
            user_input="Test",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        assert len(result.sections) >= 3

    def test_questionnaire_has_correct_question_count(self) -> None:
        """Generated questionnaire should have at least 1 question per section."""
        json_str = _make_minimal_valid_questionnaire_json()
        self._mock_client.generate.return_value = json_str

        result = generate_questionnaire(
            user_input="Test",
            organization_type="life_insurer",
            llm_client=self._mock_client,
        )

        for section in result.sections:
            assert len(section.questions) >= 1
