"""
Reusable LLM Client Integration (Groq Cloud OpenAI-Compatible API via httpx).

Provides a clean protocol (`LLMClient`) and a production `GroqLLMClient`
with strict configuration validation, timeout handling, and credential-safe
error sanitization. Designed to be shared across Task 05+ AI services.
"""

import logging
import time
from functools import lru_cache
from typing import Any, Optional, Protocol

import httpx

from app.core.config import settings
from app.core.database import sanitize_error_message

logger = logging.getLogger("app.services.llm_client")


class LLMError(Exception):
    """Base exception for LLM provider operations."""


class LLMConfigurationError(LLMError):
    """Raised when LLM API credentials or model settings are missing or invalid."""


class LLMProviderError(LLMError):
    """Raised when the upstream LLM API fails, times out, or returns an unexpected payload."""


class LLMClient(Protocol):
    """Provider-agnostic protocol for chat-completion JSON calls."""

    @property
    def default_model(self) -> str: ...

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> tuple[str, str]:
        """
        Executes a JSON-mode chat completion request.

        Returns:
            Tuple of (raw_content_string, model_used).
        """
        ...


class GroqLLMClient:
    """
    Synchronous Groq Cloud API client built on `httpx`.
    Uses Groq's OpenAI-compatible `/chat/completions` endpoint with `json_object` response format.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[float] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._api_key = (api_key if api_key is not None else settings.GROQ_API_KEY).strip()
        self._base_url = (base_url if base_url is not None else settings.GROQ_BASE_URL).rstrip("/")
        self._default_model = (
            default_model if default_model is not None else settings.GROQ_QUERY_MODEL
        ).strip()
        self._timeout = timeout if timeout is not None else settings.GROQ_TIMEOUT
        self._http_client = http_client

    @property
    def default_model(self) -> str:
        return self._default_model

    def _validate_configuration(self) -> None:
        """Ensures Groq API key and model are configured without placeholder values."""
        placeholder_indicators = ("[YOUR-", "YOUR_ACTUAL_", "<your-")
        if not self._api_key or any(token in self._api_key for token in placeholder_indicators):
            raise LLMConfigurationError(
                "GROQ_API_KEY is not configured. Set a valid key in backend/.env."
            )
        if not self._default_model:
            raise LLMConfigurationError("GROQ_QUERY_MODEL is not configured.")

    def complete_json(
        self,
        messages: list[dict[str, str]],
        *,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> tuple[str, str]:
        """
        Sends a chat completion request to Groq requesting JSON output.

        Args:
            messages: List of OpenAI-style role/content message dicts.
            model: Optional model override; defaults to `self._default_model`.
            temperature: Sampling temperature (default 0.0 for deterministic extraction).
            max_tokens: Maximum completion tokens.

        Returns:
            Tuple of (raw JSON content string, model identifier used).

        Raises:
            LLMConfigurationError: If API key or model is missing.
            LLMProviderError: On timeout, network error, non-200 HTTP status, or malformed payload.
        """
        self._validate_configuration()
        target_model = (model or self._default_model).strip()
        endpoint = f"{self._base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if self._http_client is not None:
                    response = self._http_client.post(
                        endpoint,
                        headers=headers,
                        json=payload,
                        timeout=self._timeout,
                    )
                else:
                    with httpx.Client(timeout=self._timeout) as client:
                        response = client.post(endpoint, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                sanitized = sanitize_error_message(str(exc))
                logger.warning("Groq API request timed out after %.1fs: %s", self._timeout, sanitized)
                raise LLMProviderError(
                    f"LLM provider request timed out after {self._timeout}s."
                ) from exc
            except httpx.RequestError as exc:
                sanitized = sanitize_error_message(str(exc))
                logger.warning("Groq API network error: %s", sanitized)
                raise LLMProviderError(f"LLM provider network error: {sanitized}") from exc

            if response.status_code == 429:
                if attempt < max_retries - 1:
                    wait_sec = 8.0 * (attempt + 1)
                    logger.warning(
                        "Groq API returned HTTP 429 (rate limit). Retrying in %.1fs (attempt %d/%d)...",
                        wait_sec,
                        attempt + 1,
                        max_retries,
                    )
                    time.sleep(wait_sec)
                    continue

            if response.status_code != 200:
                body_preview = sanitize_error_message(response.text[:300])
                logger.warning(
                    "Groq API returned HTTP %d: %s", response.status_code, body_preview
                )
                raise LLMProviderError(
                    f"LLM provider returned HTTP {response.status_code}: {body_preview}"
                )

            break

        try:
            data = response.json()
            choices = data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise ValueError("Missing 'choices' in Groq response.")
            content = choices[0].get("message", {}).get("content")
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty 'message.content' in Groq response.")
            resolved_model = str(data.get("model") or target_model)
            return content.strip(), resolved_model
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            sanitized = sanitize_error_message(str(exc))
            raise LLMProviderError(
                f"Malformed response payload from LLM provider: {sanitized}"
            ) from exc


@lru_cache()
def get_llm_client() -> GroqLLMClient:
    """Returns a cached GroqLLMClient instance configured from application settings."""
    return GroqLLMClient()
