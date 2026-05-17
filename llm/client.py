"""LLM client for LMStudio's OpenAI-compatible API.

Wraps the ``/v1/chat/completions`` endpoint with retry logic,
timeout handling, and structured error classes.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Custom error classes
# ------------------------------------------------------------------

class LLMConnectionError(Exception):
    """Raised when the LLM server cannot be reached.

    Attributes:
        url: The URL that failed.
        cause: The underlying ``requests`` exception message.
    """

    def __init__(self, url: str, cause: str = "") -> None:
        message = f"Cannot connect to LLM server at {url}"
        if cause:
            message += f": {cause}"
        super().__init__(message)
        self.url = url
        self.cause = cause


class LLMTimeoutError(Exception):
    """Raised when the LLM API request times out.

    Attributes:
        url: The URL that timed out.
        timeout: The configured timeout in seconds.
    """

    def __init__(self, url: str, timeout: float) -> None:
        super().__init__(f"Request to {url} timed out after {timeout}s")
        self.url = url
        self.timeout = timeout


class LLMGenerationError(Exception):
    """Raised when the LLM API returns an error response.

    Attributes:
        status_code: HTTP status code from the API.
        message: Parsed error message from the response body.
    """

    def __init__(self, status_code: int, message: str = "") -> None:
        super().__init__(f"LLM API error (HTTP {status_code}): {message}")
        self.status_code = status_code
        self.message = message


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

class LLMSettings(BaseSettings):
    """LLM-specific settings loaded from environment / ``.env`` file.

    Attributes:
        llm_base_url: Base URL of the OpenAI-compatible API endpoint.
        llm_model: Model name to use for completions.
        llm_timeout: Connection + read timeout in seconds.
        llm_max_retries: Maximum number of retry attempts.
        llm_temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative).
        llm_max_tokens: Maximum number of tokens in the model's response.
    """

    llm_base_url: str = "http://192.168.1.59:1234/v1"
    llm_model: str = "qwen/qwen3.6-35b-a3b"
    llm_timeout: float = 3600.0
    llm_max_retries: int = 2
    llm_temperature: float = 0.3
    llm_max_tokens: int = 200000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton
_llm_settings = LLMSettings()


# ------------------------------------------------------------------
# Client
# ------------------------------------------------------------------

class LLMClient:
    """Thin wrapper around LMStudio's OpenAI-compatible chat API.

    The client uses the ``requests`` library directly (no LangChain or
    OpenAI SDK dependency) and implements exponential-backoff retries
    for transient failures.

    Args:
        settings: Optional ``LLMSettings`` override.  When ``None``, the
            module-level singleton is used.
    """

    def __init__(self, settings: LLMSettings | None = None) -> None:
        self._settings = settings or _llm_settings
        self._base_url: str = self._settings.llm_base_url.rstrip("/")
        self._model: str = self._settings.llm_model
        self._timeout: float = self._settings.llm_timeout
        self._max_retries: int = self._settings.llm_max_retries
        self._temperature: float = self._settings.llm_temperature
        self._max_tokens: int = self._settings.llm_max_tokens

    # -- properties (convenience access to settings) --------------------

    @property
    def base_url(self) -> str:
        """The API base URL."""
        return self._base_url

    @property
    def model(self) -> str:
        """The model name."""
        return self._model

    @property
    def timeout(self) -> float:
        """Request timeout in seconds."""
        return self._timeout

    @property
    def max_retries(self) -> int:
        """Maximum retry count."""
        return self._max_retries

    @property
    def temperature(self) -> float:
        """Sampling temperature (0.0 = deterministic, 1.0 = creative)."""
        return self._temperature

    @property
    def max_tokens(self) -> int:
        """Maximum number of tokens in the model's response."""
        return self._max_tokens

    # -- public API ----------------------------------------------------

    def generate(
        self,
        prompt: str,
        system_prompt: str,
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Send a chat-completions request and return the raw text response.

        Args:
            prompt: The user message to send to the model.
            system_prompt: The system-level instruction message.
            response_format: Optional ``{"type": "json_object"}`` dict to
                request JSON-mode response.

        Returns:
            The model's text response.

        Raises:
            LLMConnectionError: When the server cannot be reached.
            LLMTimeoutError: When the request exceeds the timeout.
            LLMGenerationError: When the API returns a non-2xx status.
        """
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }

        if response_format is not None:
            # LMStudio may not support 'response_format' — only add if explicitly requested
            # Most models produce valid JSON without it; the caller handles parsing
            logger.debug("Adding response_format hint to payload")
            payload["response_format"] = response_format

        last_exc: Exception | None = None
        delay: float = 1.0  # initial back-off

        for attempt in range(self._max_retries + 1):
            try:
                logger.debug("Attempt %d/%d — POST %s", attempt + 1, self._max_retries + 1, self._base_url + "/chat/completions")
                resp = requests.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    timeout=self._timeout,
                )

                # If response_format caused a 400, retry without it
                if resp.status_code == 400 and "response_format" in payload:
                    try:
                        error_body = resp.json() if isinstance(resp.json(), dict) else {}
                    except Exception:
                        error_body = {}
                    error_msg = error_body.get("error", {}).get("message", "") if isinstance(error_body.get("error"), dict) else ""
                    if not error_msg:
                        error_msg = error_body.get("error", "") if isinstance(error_body.get("error"), str) else ""
                    if "response_format" in error_msg.lower() or "json_schema" in error_msg.lower():
                        logger.warning("response_format not supported by this server, retrying without it")
                        del payload["response_format"]
                        continue

                resp.raise_for_status()
                body = resp.json()
                content = body["choices"][0]["message"]["content"].strip()
                # Diagnostic: log raw response for troubleshooting
                if len(content) > 500:
                    logger.info("LLM raw response: %d chars (first 500: %s...)", len(content), content[:500])
                else:
                    logger.info("LLM raw response: %d chars — %s", len(content), content)
                logger.info("LLM response received (%d chars)", len(content))
                return content

            except requests.exceptions.Timeout as exc:
                last_exc = exc
                logger.warning("Attempt %d timed out: %s", attempt + 1, exc)
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                logger.warning("Attempt %d connection error: %s", attempt + 1, exc)
            except requests.exceptions.HTTPError as exc:
                # Non-retryable — surface immediately
                try:
                    error_body = exc.response.json()
                    error_msg = error_body.get("error", {}).get("message", str(exc))
                except Exception:
                    error_msg = str(exc)
                raise LLMGenerationError(exc.response.status_code, error_msg) from exc
            except Exception as exc:
                last_exc = exc
                logger.error("Unexpected error during generation: %s", exc)

            # Back-off before next attempt (skip on last try)
            if attempt < self._max_retries:
                logger.info("Retrying in %.1f seconds …", delay)
                import time
                time.sleep(delay)
                delay *= 2  # exponential

        # All retries exhausted
        raise LLMConnectionError(
            f"{self._base_url}/chat/completions",
            cause=str(last_exc) if last_exc else "unknown",
        ) from last_exc

    def generate_json(
        self,
        prompt: str,
        system_prompt: str,
    ) -> dict[str, Any]:
        """Generate a JSON response and parse it.

        Convenience wrapper around ``generate()`` that requests JSON-mode
        from the model and parses the returned string.

        Args:
            prompt: The user message.
            system_prompt: The system-level instruction.

        Returns:
            Parsed ``dict`` from the JSON response.

        Raises:
            LLMConnectionError: When the server cannot be reached.
            LLMTimeoutError: When the request exceeds the timeout.
            LLMGenerationError: When the API returns a non-2xx status.
            json.JSONDecodeError: When the response is not valid JSON.
        """
        raw = self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            response_format={"type": "json_object"},
        )
        return json.loads(raw)

    def is_available(self) -> bool:
        """Check whether the LLM server is reachable.

        Sends a lightweight health-check request and returns ``True``
        only when the server responds with HTTP 200.

        Returns:
            ``True`` if the server is available, ``False`` otherwise.
        """
        try:
            resp = requests.get(
                f"{self._base_url}/models",
                timeout=self._timeout,
            )
            return resp.status_code == 200
        except Exception:
            return False
