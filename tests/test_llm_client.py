"""Comprehensive tests for llm/client.py.

Covers:
- LLMSettings defaults and custom config
- LLMClient initialization with defaults and custom settings
- generate(): successful response, retry logic, timeout, HTTP errors
- generate_json(): JSON parsing with valid/invalid responses
- is_available(): health check with server available/unavailable
- Custom error classes: attributes and messages
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import responses

from llm.client import (
    LLMClient,
    LLMConnectionError,
    LLMGenerationError,
    LLMSettings,
    LLMTimeoutError,
)


# ---------------------------------------------------------------------------
# LLMSettings tests
# ---------------------------------------------------------------------------


class TestLLMSettings:
    """Tests for the LLMSettings configuration model."""

    def test_default_base_url(self) -> None:
        settings = LLMSettings()
        assert settings.llm_base_url == "http://192.168.1.59:1234/v1"

    def test_default_model(self) -> None:
        settings = LLMSettings()
        assert settings.llm_model == "qwen/qwen3.6-35b-a3b"

    def test_default_timeout(self) -> None:
        settings = LLMSettings()
        assert settings.llm_timeout == 60.0

    def test_default_max_retries(self) -> None:
        settings = LLMSettings()
        assert settings.llm_max_retries == 2

    def test_default_temperature(self) -> None:
        settings = LLMSettings()
        assert settings.llm_temperature == 0.3

    def test_default_max_tokens(self) -> None:
        settings = LLMSettings()
        assert settings.llm_max_tokens == 4096

    def test_custom_values(self) -> None:
        settings = LLMSettings(
            llm_base_url="http://localhost:8080/v1",
            llm_model="test-model",
            llm_timeout=30.0,
            llm_max_retries=5,
            llm_temperature=0.7,
            llm_max_tokens=2048,
        )
        assert settings.llm_base_url == "http://localhost:8080/v1"
        assert settings.llm_model == "test-model"
        assert settings.llm_timeout == 30.0
        assert settings.llm_max_retries == 5
        assert settings.llm_temperature == 0.7
        assert settings.llm_max_tokens == 2048


# ---------------------------------------------------------------------------
# LLMClient initialization tests
# ---------------------------------------------------------------------------


class TestLLMClientInit:
    """Tests for LLMClient construction."""

    def test_init_with_defaults(self) -> None:
        """LLMClient should use module-level singleton settings when no override provided."""
        client = LLMClient()
        assert client.base_url == "http://192.168.1.59:1234/v1"
        assert client.model == "qwen/qwen3.6-35b-a3b"
        assert client.timeout == 60.0
        assert client.max_retries == 2
        assert client.temperature == 0.3
        assert client.max_tokens == 4096

    def test_init_with_custom_settings(self) -> None:
        """LLMClient should use provided LLMSettings override."""
        custom = LLMSettings(
            llm_base_url="http://custom:9999/v1",
            llm_model="custom-model",
            llm_timeout=120.0,
            llm_max_retries=10,
            llm_temperature=0.9,
            llm_max_tokens=8192,
        )
        client = LLMClient(settings=custom)
        assert client.base_url == "http://custom:9999/v1"
        assert client.model == "custom-model"
        assert client.timeout == 120.0
        assert client.max_retries == 10
        assert client.temperature == 0.9
        assert client.max_tokens == 8192

    def test_base_url_strips_trailing_slash(self) -> None:
        """LLMClient should strip trailing slash from base_url."""
        custom = LLMSettings(llm_base_url="http://example.com/v1/")
        client = LLMClient(settings=custom)
        assert client.base_url == "http://example.com/v1"

    def test_properties_are_readonly(self) -> None:
        """Properties should not be directly settable."""
        client = LLMClient()
        with pytest.raises(AttributeError):
            client.base_url = "http://hacked.com"
        with pytest.raises(AttributeError):
            client.model = "hacked-model"


# ---------------------------------------------------------------------------
# generate() tests
# ---------------------------------------------------------------------------


class TestGenerate:
    """Tests for LLMClient.generate() with mocked HTTP."""

    @responses.activate
    def test_successful_generation(self) -> None:
        """Successful API call should return the model's text response."""
        mock_response = {"choices": [{"message": {"content": "Hello from LLM"}}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        client = LLMClient()
        result = client.generate(
            prompt="What is 2+2?",
            system_prompt="You are a math tutor.",
        )

        assert result == "Hello from LLM"
        assert len(responses.calls) == 1

    @responses.activate
    def test_successful_generation_strips_whitespace(self) -> None:
        """Response content should be stripped of leading/trailing whitespace."""
        mock_response = {"choices": [{"message": {"content": "  \nHello\n  "}}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        client = LLMClient()
        result = client.generate("prompt", "system")
        assert result == "Hello"

    @responses.activate
    def test_request_payload_structure(self) -> None:
        """POST request should contain correct payload structure."""
        mock_response = {"choices": [{"message": {"content": "OK"}}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        client = LLMClient()
        client.generate("user msg", "system msg")

        assert len(responses.calls) == 1
        payload = json.loads(responses.calls[0].request.body)
        assert payload["model"] == "qwen/qwen3.6-35b-a3b"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][0]["content"] == "system msg"
        assert payload["messages"][1]["role"] == "user"
        assert payload["messages"][1]["content"] == "user msg"
        assert payload["temperature"] == 0.3
        assert payload["max_tokens"] == 4096

    @responses.activate
    def test_custom_settings_payload(self) -> None:
        """POST request should use custom settings values."""
        mock_response = {"choices": [{"message": {"content": "OK"}}]}
        responses.add(
            responses.POST,
            "http://custom:9999/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        custom = LLMSettings(
            llm_base_url="http://custom:9999/v1",
            llm_model="my-model",
            llm_temperature=0.8,
            llm_max_tokens=1024,
        )
        client = LLMClient(settings=custom)
        client.generate("prompt", "system")

        payload = json.loads(responses.calls[0].request.body)
        assert payload["model"] == "my-model"
        assert payload["temperature"] == 0.8
        assert payload["max_tokens"] == 1024

    @responses.activate
    def test_response_format_passed_when_provided(self) -> None:
        """response_format dict should be included in the payload."""
        mock_response = {"choices": [{"message": {"content": "{}"}}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        client = LLMClient()
        client.generate("prompt", "system", response_format={"type": "json_object"})

        payload = json.loads(responses.calls[0].request.body)
        assert "response_format" in payload
        assert payload["response_format"] == {"type": "json_object"}

    @responses.activate
    def test_response_format_not_passed_when_none(self) -> None:
        """response_format should not be in payload when not provided."""
        mock_response = {"choices": [{"message": {"content": "OK"}}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=mock_response,
            status=200,
        )

        client = LLMClient()
        client.generate("prompt", "system")

        payload = json.loads(responses.calls[0].request.body)
        assert "response_format" not in payload

    @responses.activate
    def test_retry_on_connection_error(self) -> None:
        """Should retry on ConnectionError and succeed on second attempt."""
        # First two calls fail, third succeeds
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            body=responses.ConnectionError("Connection refused"),
        )
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            body=responses.ConnectionError("Connection refused"),
        )
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": "Recovered"}}]},
            status=200,
        )

        client = LLMClient()
        result = client.generate("prompt", "system")

        assert result == "Recovered"
        assert len(responses.calls) == 3

    @responses.activate
    def test_retry_on_timeout(self) -> None:
        """Should retry on Timeout and succeed on second attempt."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            body=responses.Timeout("Request timed out"),
        )
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": "OK"}}]},
            status=200,
        )

        client = LLMClient()
        result = client.generate("prompt", "system")

        assert result == "OK"
        assert len(responses.calls) == 2

    @responses.activate
    def test_all_retries_exhausted_raises_connection_error(self) -> None:
        """When all retries exhausted, should raise LLMConnectionError."""
        for _ in range(3):
            responses.add(
                responses.POST,
                "http://192.168.1.59:1234/v1/chat/completions",
                body=responses.ConnectionError("Connection refused"),
            )

        client = LLMClient()
        with pytest.raises(LLMConnectionError) as exc_info:
            client.generate("prompt", "system")

        assert "http://192.168.1.59:1234/v1/chat/completions" in str(exc_info.value)
        assert exc_info.value.url == "http://192.168.1.59:1234/v1/chat/completions"
        assert len(exc_info.value.cause) > 0

    @responses.activate
    def test_http_error_raises_generation_error(self) -> None:
        """Non-2xx HTTP response should raise LLMGenerationError immediately."""
        error_body = {"error": {"message": "Model not found"}}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json=error_body,
            status=404,
        )

        client = LLMClient()
        with pytest.raises(LLMGenerationError) as exc_info:
            client.generate("prompt", "system")

        assert exc_info.value.status_code == 404
        assert "Model not found" in exc_info.value.message
        assert len(responses.calls) == 1  # No retry for HTTP errors

    @responses.activate
    def test_http_error_without_json_body(self) -> None:
        """HTTP error without JSON body should still raise LLMGenerationError."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            body="Internal Server Error",
            status=500,
        )

        client = LLMClient()
        with pytest.raises(LLMGenerationError) as exc_info:
            client.generate("prompt", "system")

        assert exc_info.value.status_code == 500

    @responses.activate
    def test_malformed_response_raises_attribute_error(self) -> None:
        """Missing 'choices' in response should propagate the error."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"error": "bad response"},
            status=200,
        )

        client = LLMClient()
        # Should raise KeyError since there are no 'choices'
        with pytest.raises(KeyError):
            client.generate("prompt", "system")

    @responses.activate
    def test_empty_choices_message_raises_key_error(self) -> None:
        """Empty choices list should raise KeyError."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": []},
            status=200,
        )

        client = LLMClient()
        with pytest.raises(KeyError):
            client.generate("prompt", "system")

    @responses.activate
    def test_empty_message_content(self) -> None:
        """Empty message content should return empty string after strip."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": ""}}]},
            status=200,
        )

        client = LLMClient()
        result = client.generate("prompt", "system")
        assert result == ""


# ---------------------------------------------------------------------------
# generate_json() tests
# ---------------------------------------------------------------------------


class TestGenerateJson:
    """Tests for LLMClient.generate_json()."""

    @responses.activate
    def test_successful_json_generation(self) -> None:
        """Valid JSON response should be parsed and returned as dict."""
        expected = {"sections": [{"title": "Test", "questions": []}]}
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": json.dumps(expected)}}]},
            status=200,
        )

        client = LLMClient()
        result = client.generate_json("prompt", "system")

        assert result == expected

    @responses.activate
    def test_json_generation_includes_response_format(self) -> None:
        """generate_json should pass response_format={type: json_object}."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": "{}"}}]},
            status=200,
        )

        client = LLMClient()
        client.generate_json("prompt", "system")

        payload = json.loads(responses.calls[0].request.body)
        assert payload["response_format"] == {"type": "json_object"}

    @responses.activate
    def test_invalid_json_raises_json_decode_error(self) -> None:
        """Invalid JSON response should raise json.JSONDecodeError."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            json={"choices": [{"message": {"content": "not valid json"}}]},
            status=200,
        )

        client = LLMClient()
        with pytest.raises(json.JSONDecodeError):
            client.generate_json("prompt", "system")

    @responses.activate
    def test_json_generation_fails_on_connection_error(self) -> None:
        """Connection errors should propagate LLMConnectionError."""
        responses.add(
            responses.POST,
            "http://192.168.1.59:1234/v1/chat/completions",
            body=responses.ConnectionError("Connection refused"),
        )

        client = LLMClient()
        with pytest.raises(LLMConnectionError):
            client.generate_json("prompt", "system")


# ---------------------------------------------------------------------------
# is_available() tests
# ---------------------------------------------------------------------------


class TestIsAvailable:
    """Tests for LLMClient.is_available()."""

    @responses.activate
    def test_available_returns_true(self) -> None:
        """HTTP 200 from /models should return True."""
        responses.add(
            responses.GET,
            "http://192.168.1.59:1234/v1/models",
            json={"data": []},
            status=200,
        )

        client = LLMClient()
        assert client.is_available() is True

    @responses.activate
    def test_unavailable_returns_false(self) -> None:
        """Non-200 response should return False."""
        responses.add(
            responses.GET,
            "http://192.168.1.59:1234/v1/models",
            json={"error": "not found"},
            status=503,
        )

        client = LLMClient()
        assert client.is_available() is False

    @responses.activate
    def test_connection_error_returns_false(self) -> None:
        """Connection errors should return False."""
        responses.add(
            responses.GET,
            "http://192.168.1.59:1234/v1/models",
            body=responses.ConnectionError("Connection refused"),
        )

        client = LLMClient()
        assert client.is_available() is False

    @responses.activate
    def test_timeout_returns_false(self) -> None:
        """Timeout should return False."""
        responses.add(
            responses.GET,
            "http://192.168.1.59:1234/v1/models",
            body=responses.Timeout("Timed out"),
        )

        client = LLMClient()
        assert client.is_available() is False

    @responses.activate
    def test_custom_base_url_used(self) -> None:
        """is_available should use client's base_url."""
        responses.add(
            responses.GET,
            "http://custom:9999/v1/models",
            json={"data": []},
            status=200,
        )

        custom = LLMSettings(llm_base_url="http://custom:9999/v1")
        client = LLMClient(settings=custom)
        assert client.is_available() is True


# ---------------------------------------------------------------------------
# Error class tests
# ---------------------------------------------------------------------------


class TestErrorClasses:
    """Tests for custom error classes."""

    def test_llm_connection_error_attributes(self) -> None:
        error = LLMConnectionError("http://example.com/v1", cause="Connection refused")
        assert error.url == "http://example.com/v1"
        assert error.cause == "Connection refused"
        assert "Cannot connect to LLM server at http://example.com/v1" in str(error)
        assert "Connection refused" in str(error)

    def test_llm_connection_error_without_cause(self) -> None:
        error = LLMConnectionError("http://example.com/v1")
        assert error.url == "http://example.com/v1"
        assert error.cause == ""
        assert "Cannot connect to LLM server at http://example.com/v1" in str(error)

    def test_llm_timeout_error_attributes(self) -> None:
        error = LLMTimeoutError("http://example.com/v1/chat/completions", 30.0)
        assert error.url == "http://example.com/v1/chat/completions"
        assert error.timeout == 30.0
        assert "timed out after 30.0s" in str(error)

    def test_llm_generation_error_attributes(self) -> None:
        error = LLMGenerationError(500, "Internal server error")
        assert error.status_code == 500
        assert error.message == "Internal server error"
        assert "HTTP 500" in str(error)
        assert "Internal server error" in str(error)

    def test_llm_generation_error_without_message(self) -> None:
        error = LLMGenerationError(502)
        assert error.status_code == 502
        assert error.message == ""
        assert "HTTP 502" in str(error)
