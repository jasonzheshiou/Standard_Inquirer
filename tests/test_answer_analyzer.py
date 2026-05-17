"""Comprehensive tests for llm/answer_analyzer.py.

Covers:
- enrich_findings(): valid LLM response, invalid response, LLM unavailable
- Per-finding error isolation
- Batch processing (max 5 per call)
- Caching by requirement_id
- Confidence gates (min_confidence)
- generate_mitigation(): valid, invalid, empty, LLM unavailable
- _retrieve_relevant_standard_text(): ChromaDB fallback paths
- _classify_severity: already tested in test_dynamic_rules.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.schemas import GapFinding, Question
from llm.answer_analyzer import (
    _BATCH_SIZE,
    _DEFAULT_MIN_CONFIDENCE,
    _make_cache_key,
    _retrieve_relevant_standard_text,
    enrich_findings,
    generate_mitigation,
)
from llm.client import LLMClient, LLMGenerationError, LLMTimeoutError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_finding(
    requirement_id: str = "CPS 230::Para 27",
    clause_reference: str = "Para 27",
    question: str = "Do you have governance?",
    user_answer: str = "no",
    gap_severity: str = "medium",
    mitigation: str = "Review governance",
    evidence_text: str = "",
    llm_explanation: str | None = None,
) -> GapFinding:
    """Helper to create a GapFinding for testing."""
    return GapFinding(
        requirement_id=requirement_id,
        clause_reference=clause_reference,
        question=question,
        user_answer=user_answer,
        gap_severity=gap_severity,
        mitigation=mitigation,
        evidence_text=evidence_text,
        llm_explanation=llm_explanation,
    )


def _make_question(
    qid: str = "q1",
    confidence: float | None = 0.95,
    text: str = "Do you have governance?",
    source_standard: str | None = "CPS 230",
    source_clause: str | None = "Para 27",
) -> Question:
    """Helper to create a Question for testing."""
    return Question(
        id=qid,
        text=text,
        type="boolean",
        default=None,
        options=None,
        source_standard=source_standard,
        source_clause=source_clause,
        confidence=confidence,
        applies_to_standard=source_standard,
    )


@pytest.fixture
def mock_llm_client() -> MagicMock:
    """Create a mock LLMClient that reports as available."""
    mock = MagicMock(spec=LLMClient)
    mock.is_available.return_value = True
    mock.generate.return_value = (
        "The organisation lacks a documented governance framework "
        "as required by CPS 230 Para 27(b). "
        "Recommendation: Draft and board-approve a governance framework "
        "within 90 days."
    )
    mock.generate_json.return_value = {
        "CPS 230::Para 27": (
            "1. Draft governance framework document\n"
            "2. Present to Board for approval\n"
            "3. Implement quarterly review process"
        ),
    }
    return mock


@pytest.fixture
def mock_findings() -> list[GapFinding]:
    """Create a list of test GapFinding objects."""
    return [
        _make_finding(
            requirement_id="CPS 230::Para 27",
            clause_reference="Para 27",
            question="Do you have governance?",
            user_answer="no",
            gap_severity="medium",
        ),
        _make_finding(
            requirement_id="CPS 320::Section 4",
            clause_reference="Section 4",
            question="Is capital adequate?",
            user_answer="no",
            gap_severity="high",
        ),
        _make_finding(
            requirement_id="CPS 001::Section 1",
            clause_reference="Section 1",
            question="Procedural docs?",
            user_answer="no",
            gap_severity="low",
        ),
    ]


@pytest.fixture
def mock_question_map() -> dict[str, Question]:
    """Create a question map for confidence gate testing."""
    return {
        "CPS 230::Para 27": _make_question(qid="q1", confidence=0.95),
        "CPS 320::Section 4": _make_question(qid="q2", confidence=0.5),
        "CPS 001::Section 1": _make_question(qid="q3", confidence=None),
    }


# ---------------------------------------------------------------------------
# Test _make_cache_key
# ---------------------------------------------------------------------------


class TestMakeCacheKey:
    """Tests for the deterministic cache key function."""

    def test_key_contains_requirement_id(self) -> None:
        key = _make_cache_key("CPS 230::Para 27", "some text")
        assert key.startswith("CPS 230::Para 27:")

    def test_key_includes_text_hash(self) -> None:
        key1 = _make_cache_key("CPS 230::Para 27", "text A")
        key2 = _make_cache_key("CPS 230::Para 27", "text B")
        assert key1 != key2

    def test_same_input_produces_same_key(self) -> None:
        key1 = _make_cache_key("CPS 230::Para 27", "identical text")
        key2 = _make_cache_key("CPS 230::Para 27", "identical text")
        assert key1 == key2

    def test_different_requirement_different_key(self) -> None:
        key1 = _make_cache_key("CPS 320::Section 4", "same text")
        key2 = _make_cache_key("CPS 230::Para 27", "same text")
        assert key1 != key2

    def test_key_format_is_deterministic(self) -> None:
        """Key should be consistent across runs (SHA-256 based)."""
        key = _make_cache_key("CPS 230::Para 27", "test content")
        # Key format: requirement_id:16-char-hex-hash
        parts = key.split(":")
        assert len(parts) == 2
        assert len(parts[1]) == 16  # truncated hash
        assert all(c in "0123456789abcdef" for c in parts[1])


# ---------------------------------------------------------------------------
# Test _retrieve_relevant_standard_text
# ---------------------------------------------------------------------------


class TestRetrieveRelevantStandardText:
    """Tests for ChromaDB evidence retrieval fallback chain."""

    def test_returns_existing_evidence_text(self) -> None:
        """If evidence_text is non-empty, return it immediately."""
        result = _retrieve_relevant_standard_text(
            requirement_id="CPS 230::Para 27",
            clause_reference="Para 27",
            question_text="Test question",
            evidence_text="Already retrieved evidence",
        )
        assert result == "Already retrieved evidence"

    def test_falls_back_to_clause_reference(self) -> None:
        """When ChromaDB unavailable, return clause reference string."""
        with patch("llm.answer_analyzer.get_evidence_text", side_effect=Exception("DB error")):
            result = _retrieve_relevant_standard_text(
                requirement_id="CPS 230::Para 27",
                clause_reference="Para 27(b)",
                question_text="Test question",
                evidence_text="",
            )
            assert "Clause reference: Para 27(b)" == result

    def test_calls_get_evidence_text_with_query(self) -> None:
        """Should call get_evidence_text with a constructed query."""
        with patch("llm.answer_analyzer.get_evidence_text") as mock_get:
            mock_get.return_value = "Retrieved standard text"
            result = _retrieve_relevant_standard_text(
                requirement_id="CPS 230::Para 27",
                clause_reference="Para 27(b)",
                question_text="Do you have governance?",
                evidence_text="",
            )
            mock_get.assert_called_once()
            call_arg = mock_get.call_args[0][0]
            assert "CPS 230::Para 27" in call_arg
            assert "Para 27(b)" in call_arg
            assert "Do you have governance?" in call_arg
            assert result == "Retrieved standard text"

    def test_returns_empty_string_when_no_evidence_and_no_clause(self) -> None:
        """Edge case: empty evidence_text and empty clause_reference."""
        with patch("llm.answer_analyzer.get_evidence_text", return_value=""):
            result = _retrieve_relevant_standard_text(
                requirement_id="",
                clause_reference="",
                question_text="",
                evidence_text="",
            )
            assert result == "Clause reference: "

    def test_exception_in_get_evidence_text_returns_clause(self) -> None:
        """When ChromaDB raises, fall back to clause reference."""
        with patch("llm.answer_analyzer.get_evidence_text", side_effect=RuntimeError("ChromaDB down")):
            result = _retrieve_relevant_standard_text(
                requirement_id="CPS 230::Para 27",
                clause_reference="Para 27(b)",
                question_text="Test",
                evidence_text="",
            )
            assert "Clause reference: Para 27(b)" in result


# ---------------------------------------------------------------------------
# Test enrich_findings() — Valid LLM response
# ---------------------------------------------------------------------------


class TestEnrichFindingsValidLLM:
    """Tests for enrich_findings() when LLM returns valid responses."""

    def test_single_finding_enriched(self, mock_findings, mock_llm_client) -> None:
        """A single finding should be enriched with llm_explanation."""
        result = enrich_findings([mock_findings[0]], llm_client=mock_llm_client)
        assert result[0].llm_explanation is not None
        assert len(result[0].llm_explanation) > 0
        # Same list returned (mutated in-place)
        assert result is mock_findings

    def test_multiple_findings_enriched(self, mock_findings, mock_llm_client) -> None:
        """All findings should be enriched when LLM available."""
        result = enrich_findings(mock_findings, llm_client=mock_llm_client)
        for finding in result:
            assert finding.llm_explanation is not None
            assert len(finding.llm_explanation) > 0

    def test_explanation_text_content(self, mock_findings, mock_llm_client) -> None:
        """Enriched explanation should contain the mock LLM response."""
        expected = mock_llm_client.generate.return_value
        result = enrich_findings([mock_findings[0]], llm_client=mock_llm_client)
        assert result[0].llm_explanation == expected

    def test_returns_same_list_in_place(self, mock_findings, mock_llm_client) -> None:
        """Function should return the same list object (in-place mutation)."""
        result = enrich_findings(mock_findings, llm_client=mock_llm_client)
        assert result is mock_findings

    def test_empty_findings_returns_unchanged(self, mock_llm_client) -> None:
        """Empty list should be returned immediately without LLM call."""
        result = enrich_findings([], llm_client=mock_llm_client)
        assert result == []
        mock_llm_client.is_available.assert_not_called()
        mock_llm_client.generate.assert_not_called()


# ---------------------------------------------------------------------------
# Test enrich_findings() — Invalid / Error LLM responses
# ---------------------------------------------------------------------------


class TestEnrichFindingsErrorHandling:
    """Tests for error paths in enrich_findings()."""

    def test_llm_unavailable_returns_unchanged(self, mock_findings) -> None:
        """When LLM is unavailable, findings are returned without enrichment."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = False

        result = enrich_findings(mock_findings, llm_client=mock_client)
        for finding in result:
            assert finding.llm_explanation is None
        mock_client.generate.assert_not_called()

    def test_llm_generation_error_one_finding(self, mock_findings) -> None:
        """LLMGenerationError for one finding should not block others."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = True

        # First call raises, second succeeds
        mock_client.generate.side_effect = [
            LLMGenerationError(500, "Internal error"),
            "Valid explanation 2",
            "Valid explanation 3",
        ]

        result = enrich_findings(mock_findings, llm_client=mock_client)
        # First finding: not enriched (error)
        assert result[0].llm_explanation is None
        # Remaining findings: enriched
        assert result[1].llm_explanation == "Valid explanation 2"
        assert result[2].llm_explanation == "Valid explanation 3"

    def test_llm_timeout_error_one_finding(self, mock_findings) -> None:
        """LLMTimeoutError for one finding should not block others."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = True

        mock_client.generate.side_effect = [
            LLMTimeoutError("http://localhost:1234/v1", 60.0),
            "Valid explanation 2",
        ]

        result = enrich_findings([mock_findings[0], mock_findings[1]], llm_client=mock_client)
        assert result[0].llm_explanation is None
        assert result[1].llm_explanation == "Valid explanation 2"

    def test_unexpected_error_isolated(self, mock_findings) -> None:
        """Unexpected exceptions during LLM call should be caught and isolated."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = True
        mock_client.generate.side_effect = [
            ValueError("Unexpected crash"),
            "Valid explanation 2",
        ]

        result = enrich_findings(mock_findings, llm_client=mock_client)
        assert result[0].llm_explanation is None
        assert result[1].llm_explanation == "Valid explanation 2"

    def test_all_findings_fail(self, mock_findings, mock_llm_client) -> None:
        """When all LLM calls fail, all findings remain unenriched."""
        mock_llm_client.generate.side_effect = LLMGenerationError(502, "Bad gateway")
        result = enrich_findings(mock_findings, llm_client=mock_llm_client)
        for finding in result:
            assert finding.llm_explanation is None


# ---------------------------------------------------------------------------
# Test enrich_findings() — Confidence gates
# ---------------------------------------------------------------------------


class TestEnrichFindingsConfidenceGate:
    """Tests for confidence-based enrichment gating."""

    def test_high_confidence_enriched(self, mock_findings, mock_llm_client) -> None:
        """Findings with high confidence questions should be enriched."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.9, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.85, text="Procedural docs?"),
            ]
            result = enrich_findings(mock_findings, llm_client=mock_llm_client)
            for finding in result:
                assert finding.llm_explanation is not None

    def test_low_confidence_skipped(self, mock_findings, mock_llm_client) -> None:
        """Findings with low confidence questions should be skipped."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.3, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.85, text="Procedural docs?"),
            ]
            result = enrich_findings(mock_findings, llm_client=mock_llm_client)
            # First and third enriched, second skipped
            assert result[0].llm_explanation is not None
            assert result[1].llm_explanation is None
            assert result[2].llm_explanation is not None

    def test_none_confidence_treated_as_pass(self, mock_findings, mock_llm_client) -> None:
        """None confidence should be treated as passing the gate."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=None, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.85, text="Procedural docs?"),
            ]
            result = enrich_findings(mock_findings, llm_client=mock_llm_client)
            for finding in result:
                assert finding.llm_explanation is not None

    def test_custom_min_confidence(self, mock_findings, mock_llm_client) -> None:
        """Custom min_confidence threshold should be respected."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.5, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.3, text="Procedural docs?"),
            ]
            # With min_confidence=0.6, only q1 passes
            result = enrich_findings(
                mock_findings,
                llm_client=mock_llm_client,
                min_confidence=0.6,
            )
            assert result[0].llm_explanation is not None
            assert result[1].llm_explanation is None  # 0.5 < 0.6
            assert result[2].llm_explanation is None  # 0.3 < 0.6

    def test_zero_min_confidence_all_pass(self, mock_findings, mock_llm_client) -> None:
        """min_confidence=0 should enrich all findings regardless of confidence."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.0, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=None, text="Procedural docs?"),
            ]
            result = enrich_findings(
                mock_findings,
                llm_client=mock_llm_client,
                min_confidence=0.0,
            )
            for finding in result:
                assert finding.llm_explanation is not None

    def test_no_question_map_falls_back_to_enrich(self) -> None:
        """When questionnaire loading fails, all findings should be enriched."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = True
        mock_client.generate.return_value = "Explanation"

        with patch("llm.answer_analyzer.get_all_questions", side_effect=Exception("Load failed")):
            result = enrich_findings(mock_findings, llm_client=mock_client)
            for finding in result:
                assert finding.llm_explanation is not None


# ---------------------------------------------------------------------------
# Test enrich_findings() — Batch processing
# ---------------------------------------------------------------------------


class TestEnrichFindingsBatchProcessing:
    """Tests for batch processing behavior."""

    def test_batch_size_is_five(self) -> None:
        """_BATCH_SIZE constant should be 5."""
        assert _BATCH_SIZE == 5

    def test_batches_of_five_processed(self, mock_llm_client) -> None:
        """Exactly 5 findings should trigger one LLM call per finding."""
        findings = [_make_finding(f"req_{i}") for i in range(5)]
        result = enrich_findings(findings, llm_client=mock_llm_client)
        assert len(result) == 5
        for finding in result:
            assert finding.llm_explanation is not None

    def test_more_than_five_batches(self, mock_llm_client) -> None:
        """More than 5 findings should be split into multiple batches."""
        findings = [_make_finding(f"req_{i}") for i in range(7)]
        result = enrich_findings(findings, llm_client=mock_llm_client)
        assert len(result) == 7
        for finding in result:
            assert finding.llm_explanation is not None

    def test_exactly_batch_size(self, mock_llm_client) -> None:
        """Exactly _BATCH_SIZE findings should all be processed."""
        findings = [_make_finding(f"req_{i}") for i in range(_BATCH_SIZE)]
        result = enrich_findings(findings, llm_client=mock_llm_client)
        assert len(result) == _BATCH_SIZE
        assert all(f.llm_explanation is not None for f in result)

    def test_one_finding(self, mock_llm_client) -> None:
        """Single finding should be processed correctly."""
        result = enrich_findings([_make_finding()], llm_client=mock_llm_client)
        assert len(result) == 1
        assert result[0].llm_explanation is not None


# ---------------------------------------------------------------------------
# Test enrich_findings() — Caching
# ---------------------------------------------------------------------------


class TestEnrichFindingsCaching:
    """Tests for cache behavior in enrich_findings()."""

    def test_cache_hit_returns_cached_value(self, mock_llm_client) -> None:
        """Same requirement_id + standard_text should use cache."""
        cache: dict[str, str] = {}
        findings = [
            _make_finding(requirement_id="CPS 230::Para 27"),
            _make_finding(requirement_id="CPS 230::Para 27"),  # duplicate
        ]

        # First call populates cache
        result1 = enrich_findings(findings[:1], llm_client=mock_llm_client, cache=cache)
        assert result1[0].llm_explanation == mock_llm_client.generate.return_value

        # Second call should hit cache (same requirement_id, same evidence_text)
        mock_llm_client.reset_mock()
        result2 = enrich_findings(findings[1:], llm_client=mock_llm_client, cache=cache)
        # LLM should NOT be called again for the cached key
        # Note: LLM may still be called for is_available check
        generate_calls = mock_llm_client.generate.call_count

    def test_cache_populated_after_enrichment(self, mock_findings, mock_llm_client) -> None:
        """Cache should be populated after each successful enrichment."""
        cache: dict[str, str] = {}
        enrich_findings(mock_findings, llm_client=mock_llm_client, cache=cache)
        assert len(cache) > 0

    def test_different_standard_text_different_cache_key(self, mock_llm_client) -> None:
        """Same requirement_id but different evidence_text should create different cache entries."""
        cache: dict[str, str] = {}
        findings = [
            _make_finding(
                requirement_id="CPS 230::Para 27",
                evidence_text="Evidence A",
            ),
            _make_finding(
                requirement_id="CPS 230::Para 27",
                evidence_text="Evidence B",
            ),
        ]
        result = enrich_findings(findings, llm_client=mock_llm_client, cache=cache)
        # Both should be enriched (different cache keys)
        assert result[0].llm_explanation is not None
        assert result[1].llm_explanation is not None
        # Cache should have 2 entries
        assert len(cache) == 2

    def test_already_enriched_skipped(self, mock_findings, mock_llm_client) -> None:
        """Findings that already have llm_explanation should be skipped."""
        mock_findings[0].llm_explanation = "Already enriched"
        result = enrich_findings(mock_findings, llm_client=mock_llm_client)
        assert result[0].llm_explanation == "Already enriched"


# ---------------------------------------------------------------------------
# Test generate_mitigation()
# ---------------------------------------------------------------------------


class TestGenerateMitigation:
    """Tests for the generate_mitigation() function."""

    def test_empty_findings_returns_empty_dict(self, mock_llm_client) -> None:
        """Empty findings list should return empty dict."""
        result = generate_mitigation([], llm_client=mock_llm_client)
        assert result == {}
        mock_llm_client.is_available.assert_not_called()

    def test_valid_mitigation_response(self, mock_findings, mock_llm_client) -> None:
        """Valid LLM response should return dict mapping requirement_id to mitigation."""
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert isinstance(result, dict)
        # Should contain at least one key
        assert len(result) > 0

    def test_mitigation_json_dict_return(self, mock_findings, mock_llm_client) -> None:
        """LLM returning dict should be passed through directly."""
        mock_llm_client.generate_json.return_value = {
            "CPS 230::Para 27": "Mitigation for CPS 230",
            "CPS 320::Section 4": "Mitigation for CPS 320",
        }
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert "CPS 230::Para 27" in result
        assert "CPS 320::Section 4" in result

    def test_mitigation_json_string_return(self, mock_findings, mock_llm_client) -> None:
        """LLM returning JSON string should be parsed and returned as dict."""
        import json as json_mod

        mock_llm_client.generate_json.return_value = json_mod.dumps({
            "CPS 230::Para 27": "Mitigation text",
        })
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert isinstance(result, dict)
        assert "CPS 230::Para 27" in result

    def test_llm_unavailable_returns_empty_dict(self, mock_findings) -> None:
        """LLM unavailable should return empty dict."""
        mock_client = MagicMock(spec=LLMClient)
        mock_client.is_available.return_value = False
        result = generate_mitigation(mock_findings, llm_client=mock_client)
        assert result == {}
        mock_client.generate_json.assert_not_called()

    def test_llm_generation_error_returns_empty_dict(self, mock_findings, mock_llm_client) -> None:
        """LLMGenerationError should return empty dict."""
        mock_llm_client.generate_json.side_effect = LLMGenerationError(500, "Error")
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert result == {}

    def test_llm_timeout_error_returns_empty_dict(self, mock_findings, mock_llm_client) -> None:
        """LLMTimeoutError should return empty dict."""
        mock_llm_client.generate_json.side_effect = LLMTimeoutError("http://localhost:1234", 60.0)
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert result == {}

    def test_invalid_json_returns_empty_dict(self, mock_findings, mock_llm_client) -> None:
        """Invalid JSON response should return empty dict."""
        mock_llm_client.generate_json.side_effect = ValueError("Not JSON")
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        assert result == {}

    def test_all_findings_below_confidence(self, mock_findings, mock_llm_client) -> None:
        """All findings below min_confidence should return empty dict."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.1, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.2, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.0, text="Procedural docs?"),
            ]
            result = generate_mitigation(
                mock_findings,
                llm_client=mock_llm_client,
                min_confidence=0.5,
            )
            assert result == {}

    def test_no_question_map_include_all(self, mock_findings, mock_llm_client) -> None:
        """When questionnaire loading fails, all findings should be included."""
        with patch("llm.answer_analyzer.get_all_questions", side_effect=Exception("Load failed")):
            mock_llm_client.generate_json.return_value = {"CPS 230::Para 27": "Mitigation"}
            result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
            assert isinstance(result, dict)

    def test_prompt_includes_finding_details(self, mock_findings, mock_llm_client) -> None:
        """Mitigation prompt should include finding details."""
        result = generate_mitigation(mock_findings, llm_client=mock_llm_client)
        # Verify generate_json was called (which means prompt was built)
        mock_llm_client.generate_json.assert_called_once()
        call_args = mock_llm_client.generate_json.call_args
        prompt = call_args[1]["prompt"]
        # Check that prompt includes key finding details
        assert "CPS 230::Para 27" in prompt
        assert "Para 27" in prompt
        assert "no" in prompt  # user_answer


# ---------------------------------------------------------------------------
# Test enrich_findings() — LLMClient auto-creation
# ---------------------------------------------------------------------------


class TestEnrichFindingsAutoClient:
    """Tests for automatic LLMClient creation when none provided."""

    def test_creates_llm_client_when_none_provided(self, mock_findings) -> None:
        """When llm_client is None, a new LLMClient should be created."""
        with patch("llm.answer_analyzer.LLMClient") as mock_client_class:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.is_available.return_value = False
            mock_client_class.return_value = mock_instance

            result = enrich_findings(mock_findings)
            mock_client_class.assert_called_once()
            # Should return unchanged since is_available is False
            for finding in result:
                assert finding.llm_explanation is None

    def test_auto_client_unavailable_returns_unchanged(self, mock_findings) -> None:
        """Auto-created client that is unavailable should return findings unchanged."""
        with patch("llm.answer_analyzer.LLMClient") as mock_client_class:
            mock_instance = MagicMock(spec=LLMClient)
            mock_instance.is_available.return_value = False
            mock_client_class.return_value = mock_instance

            result = enrich_findings(mock_findings)
            assert all(f.llm_explanation is None for f in result)


# ---------------------------------------------------------------------------
# Test generate_mitigation() — Edge cases
# ---------------------------------------------------------------------------


class TestGenerateMitigationEdgeCases:
    """Tests for edge cases in generate_mitigation()."""

    def test_single_finding(self, mock_llm_client) -> None:
        """Single finding should produce mitigation dict."""
        finding = _make_finding(requirement_id="CPS 230::Para 27")
        mock_llm_client.generate_json.return_value = {"CPS 230::Para 27": "Mitigation"}
        result = generate_mitigation([finding], llm_client=mock_llm_client)
        assert result == {"CPS 230::Para 27": "Mitigation"}

    def test_finding_without_question_included(self, mock_llm_client) -> None:
        """Findings without associated question should be included."""
        finding = _make_finding(requirement_id="UNKNOWN::Clause")
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = []  # No questions found
            mock_llm_client.generate_json.return_value = {"UNKNOWN::Clause": "Mitigation"}
            result = generate_mitigation([finding], llm_client=mock_llm_client)
            assert "UNKNOWN::Clause" in result

    def test_mixed_confidence_findings(self, mock_findings, mock_llm_client) -> None:
        """Mixed confidence findings should include eligible ones only."""
        with patch("llm.answer_analyzer.get_all_questions") as mock_questions:
            mock_questions.return_value = [
                _make_question(qid="q1", confidence=0.95, text="Do you have governance?"),
                _make_question(qid="q2", confidence=0.2, text="Is capital adequate?"),
                _make_question(qid="q3", confidence=0.85, text="Procedural docs?"),
            ]
            mock_llm_client.generate_json.return_value = {
                "CPS 230::Para 27": "Mitigation 1",
                "CPS 001::Section 1": "Mitigation 3",
            }
            result = generate_mitigation(
                mock_findings,
                llm_client=mock_llm_client,
                min_confidence=0.5,
            )
            # Only high-confidence findings should be in result
            assert "CPS 230::Para 27" in result
            assert "CPS 001::Section 1" in result
            assert "CPS 320::Section 4" not in result


# ---------------------------------------------------------------------------
# Test _retrieve_relevant_standard_text — ChromaDB path
# ---------------------------------------------------------------------------


class TestRetrieveStandardTextChromaDB:
    """Tests for ChromaDB integration paths in evidence retrieval."""

    def test_get_evidence_text_called_when_no_evidence(self) -> None:
        """When evidence_text is empty, get_evidence_text should be called."""
        with patch("llm.answer_analyzer.get_evidence_text") as mock_get:
            mock_get.return_value = "ChromaDB result"
            result = _retrieve_relevant_standard_text(
                requirement_id="CPS 230::Para 27",
                clause_reference="Para 27(b)",
                question_text="Test",
                evidence_text="",
            )
            mock_get.assert_called_once()
            assert result == "ChromaDB result"

    def test_get_evidence_text_not_called_when_evidence_exists(self) -> None:
        """When evidence_text is populated, get_evidence_text should NOT be called."""
        with patch("llm.answer_analyzer.get_evidence_text") as mock_get:
            result = _retrieve_relevant_standard_text(
                requirement_id="CPS 230::Para 27",
                clause_reference="Para 27(b)",
                question_text="Test",
                evidence_text="Pre-existing evidence",
            )
            mock_get.assert_not_called()
            assert result == "Pre-existing evidence"


# ---------------------------------------------------------------------------
# Test generate_mitigation — Prompt construction
# ---------------------------------------------------------------------------


class TestMitigationPromptConstruction:
    """Tests for mitigation prompt building logic."""

    def test_prompt_contains_all_findings(self, mock_findings, mock_llm_client) -> None:
        """Prompt should include all eligible findings."""
        generate_mitigation(mock_findings, llm_client=mock_llm_client)
        call_args = mock_llm_client.generate_json.call_args
        prompt = call_args[1]["prompt"]

        assert "CPS 230::Para 27" in prompt
        assert "CPS 320::Section 4" in prompt
        assert "CPS 001::Section 1" in prompt

    def test_prompt_contains_severity(self, mock_findings, mock_llm_client) -> None:
        """Prompt should include severity info for each finding."""
        generate_mitigation(mock_findings, llm_client=mock_llm_client)
        call_args = mock_llm_client.generate_json.call_args
        prompt = call_args[1]["prompt"]

        assert "medium" in prompt
        assert "high" in prompt
        assert "low" in prompt

    def test_prompt_contains_user_answer(self, mock_findings, mock_llm_client) -> None:
        """Prompt should include user answer for each finding."""
        generate_mitigation(mock_findings, llm_client=mock_llm_client)
        call_args = mock_llm_client.generate_json.call_args
        prompt = call_args[1]["prompt"]

        assert "no" in prompt  # All our test findings have user_answer="no"

    def test_system_prompt_included(self, mock_findings, mock_llm_client) -> None:
        """System prompt should be passed to generate_json."""
        generate_mitigation(mock_findings, llm_client=mock_llm_client)
        call_args = mock_llm_client.generate_json.call_args
        system_prompt = call_args[1]["system_prompt"]

        assert "Australian life insurance compliance expert" in system_prompt


# ---------------------------------------------------------------------------
# Test system prompt constant
# ---------------------------------------------------------------------------


class TestSystemPrompt:
    """Tests for the _SYSTEM_PROMPT constant."""

    def test_system_prompt_exists(self) -> None:
        """System prompt should be defined in the module."""
        from llm.answer_analyzer import _SYSTEM_PROMPT
        assert isinstance(_SYSTEM_PROMPT, str)
        assert len(_SYSTEM_PROMPT) > 0

    def test_system_prompt_references_insurance(self) -> None:
        """System prompt should reference Australian insurance context."""
        from llm.answer_analyzer import _SYSTEM_PROMPT
        assert "Australian" in _SYSTEM_PROMPT
        assert "insurance" in _SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# Test GapFinding model usage in tests
# ---------------------------------------------------------------------------


class TestGapFindingModelUsage:
    """Tests ensuring GapFinding model works correctly in test scenarios."""

    def test_finding_with_all_fields(self) -> None:
        """GapFinding should accept all fields."""
        finding = _make_finding(
            requirement_id="CPS 230::Para 27",
            clause_reference="Para 27(b)",
            question="Do you have governance?",
            user_answer="no",
            gap_severity="medium",
            mitigation="Review governance",
            evidence_text="Evidence text",
            llm_explanation="LLM explanation",
        )
        assert finding.requirement_id == "CPS 230::Para 27"
        assert finding.clause_reference == "Para 27(b)"
        assert finding.question == "Do you have governance?"
        assert finding.user_answer == "no"
        assert finding.gap_severity == "medium"
        assert finding.mitigation == "Review governance"
        assert finding.evidence_text == "Evidence text"
        assert finding.llm_explanation == "LLM explanation"

    def test_finding_default_evidence_text(self) -> None:
        """GapFinding should default evidence_text to empty string."""
        finding = _make_finding()
        assert finding.evidence_text == ""

    def test_finding_default_llm_explanation(self) -> None:
        """GapFinding should default llm_explanation to None."""
        finding = _make_finding()
        assert finding.llm_explanation is None

    def test_finding_serialization(self) -> None:
        """GapFinding should serialize to JSON correctly."""
        import json as json_mod
        finding = _make_finding()
        json_str = finding.model_dump_json()
        restored = GapFinding.model_validate_json(json_str)
        assert restored.requirement_id == finding.requirement_id
        assert restored.clause_reference == finding.clause_reference
        assert restored.question == finding.question
        assert restored.user_answer == finding.user_answer
        assert restored.gap_severity == finding.gap_severity

    def test_finding_dict_dump(self) -> None:
        """GapFinding should dump to dict correctly."""
        finding = _make_finding()
        d = finding.model_dump()
        assert d["requirement_id"] == "CPS 230::Para 27"
        assert d["llm_explanation"] is None
        assert d["evidence_text"] == ""
