"""
Deterministic Unit Tests for Task 05A — Query Understanding & Groq LLM Client.

Covers:
1. Intent classification across all supported QueryIntent values.
2. Conversational query rewriting with history and reference_date.
3. Retrieval hints extraction, deduplication, and explicit date/version hints.
4. Strict preservation of original_query regardless of LLM payload.
5. Input validation (empty, whitespace-only, length limits, history limits).
6. Malformed/incomplete LLM output handling (no silent fabricated fallback).
7. GroqLLMClient configuration, HTTP errors, timeouts, and secret redaction.
"""

import json
from datetime import date
from unittest.mock import MagicMock

import httpx
import pytest

from app.core.config import Settings
from app.core.database import sanitize_error_message
from app.schemas.query_understanding import (
    ConversationTurn,
    QueryIntent,
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from app.services.llm_client import (
    GroqLLMClient,
    LLMConfigurationError,
    LLMProviderError,
)
from app.services.query_understanding_service import (
    InvalidQueryInputError,
    LLMOutputValidationError,
    QueryUnderstandingService,
)


def _make_mock_llm(payload: dict | str, model: str = "llama-3.1-8b-instant") -> MagicMock:
    """Creates a mock LLMClient returning serialized JSON or raw string."""
    mock_client = MagicMock()
    mock_client.default_model = model
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    mock_client.complete_json.return_value = (raw, model)
    return mock_client


# ---------------------------------------------------------------------------
# QueryUnderstandingService Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent_value,query,topic,rewritten",
    [
        (
            "policy_lookup",
            "What is the meal per diem?",
            "travel reimbursement",
            "meal per diem allowance travel reimbursement policy",
        ),
        (
            "eligibility",
            "Are contractors eligible for parental leave?",
            "parental leave",
            "contractor eligibility for parental leave policy",
        ),
        (
            "comparison",
            "How did travel meal limits change from v1.0 to v2.0?",
            "travel reimbursement",
            "compare travel meal allowance v1.0 vs v2.0",
        ),
        (
            "summarization",
            "Summarize the remote work equipment policy.",
            "remote and hybrid work",
            "summary of remote work equipment reimbursement policy",
        ),
        (
            "clarification",
            "What is the limit?",
            "unknown",
            "What is the limit?",
        ),
        (
            "out_of_scope",
            "What is the weather in London?",
            "out of scope",
            "What is the weather in London?",
        ),
    ],
)
def test_understand_query_all_intents(
    intent_value: str,
    query: str,
    topic: str,
    rewritten: str,
) -> None:
    """All 6 supported intents validate cleanly into QueryUnderstandingResult."""
    mock_llm = _make_mock_llm(
        {
            "intent": intent_value,
            "primary_topic": topic,
            "rewritten_query": rewritten,
            "retrieval_hints": {
                "keywords": ["policy", topic],
                "entities": [],
            },
            "needs_clarification": intent_value == "clarification",
            "clarification_reason": "Needs policy context." if intent_value == "clarification" else None,
        }
    )
    service = QueryUnderstandingService(llm_client=mock_llm)
    result = service.understand_query(query)

    assert isinstance(result, QueryUnderstandingResult)
    assert result.original_query == query
    assert result.intent == QueryIntent(intent_value)
    assert result.primary_topic == topic
    assert result.rewritten_query == rewritten
    assert result.model_used == "llama-3.1-8b-instant"


def test_conversational_rewrite_with_history_and_hints() -> None:
    """Conversation history and reference_date are passed to LLM and hints are validated."""
    mock_llm = _make_mock_llm(
        {
            "intent": "policy_lookup",
            "primary_topic": "travel hotel reimbursement",
            "rewritten_query": "hotel reimbursement cap for London travel under v1.0",
            "retrieval_hints": {
                "keywords": ["hotel", "cap", "London", "HOTEL", "  "],
                "entities": ["London", "v1.0"],
                "department_hint": "Human Resources",
                "category_hint": "Human Resources & Corporate Travel",
                "effective_date_hint": "2025-06-01",
                "version_hint": "v1.0",
            },
            "needs_clarification": False,
            "clarification_reason": None,
        }
    )
    service = QueryUnderstandingService(llm_client=mock_llm)
    req = QueryUnderstandingRequest(
        query="What about London in June 2025 under v1.0?",
        conversation_history=[
            ConversationTurn(role="user", content="What is the domestic hotel cap?"),
            ConversationTurn(role="assistant", content="The domestic hotel cap is $200/night."),
        ],
        reference_date=date(2026, 11, 25),
    )

    result = service.understand_query(req)

    assert result.original_query == "What about London in June 2025 under v1.0?"
    assert result.retrieval_hints.keywords == ["hotel", "cap", "London"]
    assert result.retrieval_hints.entities == ["London", "v1.0"]
    assert result.retrieval_hints.effective_date_hint == date(2025, 6, 1)
    assert result.retrieval_hints.version_hint == "v1.0"
    assert result.retrieval_hints.department_hint == "Human Resources"

    # Verify prompt included reference date and history
    sent_messages = mock_llm.complete_json.call_args.kwargs["messages"]
    assert "2026-11-25" in sent_messages[1]["content"]
    assert "domestic hotel cap" in sent_messages[1]["content"]


def test_preserves_original_query_even_if_llm_changes_it() -> None:
    """Service always preserves the caller's exact query as original_query."""
    mock_llm = _make_mock_llm(
        {
            "original_query": "LLM fabricated different query",
            "intent": "policy_lookup",
            "primary_topic": "annual leave",
            "rewritten_query": "annual leave carryover policy",
            "retrieval_hints": {"keywords": ["annual leave", "carryover"]},
            "needs_clarification": False,
        }
    )
    service = QueryUnderstandingService(llm_client=mock_llm)
    result = service.understand_query("  How many PTO days roll over?  ")

    assert result.original_query == "How many PTO days roll over?"


def test_strips_markdown_fences_around_valid_json() -> None:
    """Markdown ```json fences returned by an LLM are stripped safely."""
    fenced = """```json
    {
      "intent": "policy_lookup",
      "primary_topic": "expense reimbursement",
      "rewritten_query": "expense report submission deadline",
      "retrieval_hints": {"keywords": ["expense", "deadline"]},
      "needs_clarification": false
    }
    ```"""
    mock_llm = _make_mock_llm(fenced)
    service = QueryUnderstandingService(llm_client=mock_llm)
    result = service.understand_query("When must I submit expenses?")

    assert result.intent == QueryIntent.POLICY_LOOKUP
    assert result.primary_topic == "expense reimbursement"


@pytest.mark.parametrize("bad_query", ["", "   ", "\n\t"])
def test_rejects_empty_or_whitespace_query(bad_query: str) -> None:
    """Empty or whitespace queries fail fast without calling the LLM."""
    mock_llm = _make_mock_llm({})
    service = QueryUnderstandingService(llm_client=mock_llm)

    with pytest.raises(InvalidQueryInputError):
        service.understand_query(bad_query)

    mock_llm.complete_json.assert_not_called()


def test_rejects_oversized_query() -> None:
    """Queries exceeding 2000 characters are rejected."""
    mock_llm = _make_mock_llm({})
    service = QueryUnderstandingService(llm_client=mock_llm)

    with pytest.raises(InvalidQueryInputError):
        service.understand_query("a" * 2001)

    mock_llm.complete_json.assert_not_called()


@pytest.mark.parametrize(
    "bad_output",
    [
        "not json at all",
        '["a", "list", "not", "object"]',
        json.dumps({"intent": "invented_intent", "primary_topic": "leave", "rewritten_query": "leave"}),
        json.dumps({"intent": "policy_lookup", "primary_topic": "leave"}),  # missing rewritten_query
        json.dumps(
            {
                "intent": "policy_lookup",
                "primary_topic": "leave",
                "rewritten_query": "x" * 501,  # exceeds max_length=500
            }
        ),
    ],
)
def test_malformed_or_invalid_llm_output_raises_validation_error(bad_output: str) -> None:
    """Malformed JSON or schema violations raise LLMOutputValidationError without fallback."""
    mock_llm = _make_mock_llm(bad_output)
    service = QueryUnderstandingService(llm_client=mock_llm)

    with pytest.raises(LLMOutputValidationError):
        service.understand_query("What is the leave policy?")


# ---------------------------------------------------------------------------
# GroqLLMClient & Configuration Tests
# ---------------------------------------------------------------------------


def test_groq_client_missing_or_placeholder_key_raises_config_error() -> None:
    """Missing or placeholder API key raises LLMConfigurationError before HTTP call."""
    for bad_key in ("", "   ", "[YOUR-GROQ-API-KEY]"):
        client = GroqLLMClient(api_key=bad_key, default_model="llama-3.1-8b-instant")
        with pytest.raises(LLMConfigurationError):
            client.complete_json([{"role": "user", "content": "hi"}])


def test_groq_client_http_error_sanitizes_api_key() -> None:
    """HTTP error responses from Groq raise LLMProviderError and redact gsk_ keys."""
    secret_key = "gsk_test_secret_1234567890"
    mock_http = MagicMock(spec=httpx.Client)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 429
    mock_response.text = f"Rate limit exceeded for key {secret_key}"
    mock_http.post.return_value = mock_response

    client = GroqLLMClient(
        api_key=secret_key,
        base_url="https://api.groq.com/openai/v1",
        default_model="llama-3.1-8b-instant",
        http_client=mock_http,
    )

    with pytest.raises(LLMProviderError) as exc_info:
        client.complete_json([{"role": "user", "content": "hi"}])

    assert "429" in str(exc_info.value)
    assert secret_key not in str(exc_info.value)
    assert "gsk_*****" in str(exc_info.value)


def test_groq_client_timeout_raises_provider_error() -> None:
    """Network timeouts raise LLMProviderError."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_http.post.side_effect = httpx.ReadTimeout("timed out")

    client = GroqLLMClient(
        api_key="gsk_valid_dummy_key",
        default_model="llama-3.1-8b-instant",
        timeout=5.0,
        http_client=mock_http,
    )

    with pytest.raises(LLMProviderError, match="timed out"):
        client.complete_json([{"role": "user", "content": "hi"}])


def test_groq_client_success_parses_choice_content() -> None:
    """Successful 200 response returns raw content and model identifier."""
    mock_http = MagicMock(spec=httpx.Client)
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "model": "llama-3.1-8b-instant",
        "choices": [{"message": {"content": '{"intent": "policy_lookup"}'}}],
    }
    mock_http.post.return_value = mock_response

    client = GroqLLMClient(
        api_key="gsk_valid_dummy_key",
        default_model="llama-3.1-8b-instant",
        http_client=mock_http,
    )
    content, model_used = client.complete_json([{"role": "user", "content": "hi"}])

    assert content == '{"intent": "policy_lookup"}'
    assert model_used == "llama-3.1-8b-instant"


def test_settings_is_llm_configured_and_key_sanitization() -> None:
    """Verify Settings.is_llm_configured and sanitize_error_message for Groq keys."""
    unconfigured = Settings(_env_file=None, GROQ_API_KEY="[YOUR-GROQ-API-KEY]")
    assert unconfigured.is_llm_configured is False

    configured = Settings(_env_file=None, GROQ_API_KEY="gsk_valid_key_abc")
    assert configured.is_llm_configured is True
    assert configured.GROQ_QUERY_MODEL == "openai/gpt-oss-20b"

    redacted = sanitize_error_message("Bearer gsk_abc123xyz failed")
    assert "gsk_abc123xyz" not in redacted
