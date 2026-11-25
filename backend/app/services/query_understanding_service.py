"""
Query Understanding Service — Task 05A.

Converts an employee's natural-language question (plus optional conversation
history) into a validated, structured `QueryUnderstandingResult` that guides
downstream retrieval without modifying or replacing Task 04's policy/version logic.
"""

import json
import logging
import re
from datetime import date
from typing import Any, Optional, Union

from pydantic import ValidationError

from app.core.database import sanitize_error_message
from app.schemas.query_understanding import (
    QueryIntent,
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from app.services.llm_client import (
    LLMClient,
    LLMError,
    get_llm_client,
)

logger = logging.getLogger("app.services.query_understanding")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_SYSTEM_PROMPT = """You are the Query Understanding component for KnowBridge AI, an enterprise policy RAG assistant.
Analyze the employee's question (and optional recent conversation history) and return a single JSON object.

Allowed "intent" values:
- "policy_lookup": Direct question about a policy rule, limit, allowance, or procedure.
- "eligibility": Question about who qualifies for a policy, benefit, or exception.
- "comparison": Question comparing policies, versions, regions, or scenarios.
- "summarization": Request for an overview or summary of a policy or section.
- "clarification": Ambiguous or underspecified question that cannot be answered without more context.
- "out_of_scope": Non-policy, chit-chat, or general knowledge unrelated to company policies.

Rules:
1. Preserve original meaning. NEVER invent facts, numbers, dates, or policy details not present in the question or conversation history.
2. "rewritten_query" must be a clear, standalone search-oriented query suitable for semantic policy search. Resolve pronouns using conversation history when unambiguous.
3. "primary_topic" should name the core policy/subject (e.g., "travel reimbursement", "parental leave", "IT acceptable use", or "unknown" if underspecified).
4. "retrieval_hints":
   - "keywords": up to 10 concise search terms.
   - "entities": up to 10 named entities (locations, roles, policy IDs, amounts) explicitly mentioned.
   - "department_hint": optional advisory department (e.g., "Human Resources", "Finance", "IT") or null.
   - "category_hint": optional advisory policy category or null.
   - "effective_date_hint": ISO date "YYYY-MM-DD" ONLY if a specific date is explicitly mentioned or unambiguously resolved against reference_date; otherwise null.
   - "version_hint": explicit version string (e.g., "1.0", "v2.0") ONLY if mentioned; otherwise null.
5. Set "needs_clarification": true (and a brief "clarification_reason") when intent is "clarification" or the question is too vague to search reliably. Otherwise false and null.

Return ONLY valid JSON matching this exact structure:
{
  "intent": "...",
  "primary_topic": "...",
  "rewritten_query": "...",
  "retrieval_hints": {
    "keywords": ["..."],
    "entities": ["..."],
    "department_hint": null,
    "category_hint": null,
    "effective_date_hint": null,
    "version_hint": null
  },
  "needs_clarification": false,
  "clarification_reason": null
}"""


class QueryUnderstandingError(Exception):
    """Base exception for query understanding operations."""


class InvalidQueryInputError(QueryUnderstandingError):
    """Raised when the caller supplies invalid or empty query input."""


class LLMOutputValidationError(QueryUnderstandingError):
    """Raised when the LLM returns malformed JSON or schema-invalid output."""


def _strip_markdown_fences(raw_text: str) -> str:
    """Removes optional ```json ... ``` wrappers around JSON text."""
    return _CODE_FENCE_RE.sub("", raw_text.strip()).strip()


class QueryUnderstandingService:
    """
    Converts natural-language employee questions into validated
    `QueryUnderstandingResult` objects using a configured `LLMClient`.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        self._llm_client: LLMClient = llm_client or get_llm_client()

    def understand_query(
        self,
        request: Union[QueryUnderstandingRequest, str],
    ) -> QueryUnderstandingResult:
        """
        Analyzes an employee's question and returns a validated structured representation.

        Args:
            request: Either a `QueryUnderstandingRequest` or a raw query string.

        Returns:
            Validated `QueryUnderstandingResult` preserving `original_query`.

        Raises:
            InvalidQueryInputError: If input validation fails.
            LLMConfigurationError: If Groq credentials/settings are missing.
            LLMProviderError: If the upstream LLM API fails or times out.
            LLMOutputValidationError: If the LLM returns malformed or invalid JSON.
        """
        validated_req = self._validate_request(request)
        ref_date = validated_req.reference_date or date.today()
        messages = self._build_messages(validated_req, ref_date)

        raw_content, model_used = self._llm_client.complete_json(
            messages=messages,
            temperature=0.0,
            max_tokens=512,
        )

        parsed = self._parse_and_validate_output(
            raw_content=raw_content,
            original_query=validated_req.query,
            model_used=model_used,
        )

        logger.info(
            "Query understood: intent=%s topic=%r needs_clarification=%s model=%s",
            parsed.intent.value,
            parsed.primary_topic,
            parsed.needs_clarification,
            parsed.model_used,
        )
        return parsed

    @staticmethod
    def _validate_request(
        request: Union[QueryUnderstandingRequest, str],
    ) -> QueryUnderstandingRequest:
        try:
            if isinstance(request, str):
                return QueryUnderstandingRequest(query=request)
            if isinstance(request, QueryUnderstandingRequest):
                return request
            return QueryUnderstandingRequest.model_validate(request)
        except ValidationError as exc:
            raise InvalidQueryInputError(f"Invalid query understanding input: {exc}") from exc

    @staticmethod
    def _build_messages(
        request: QueryUnderstandingRequest,
        reference_date: date,
    ) -> list[dict[str, str]]:
        history_block = ""
        if request.conversation_history:
            turns = "\n".join(
                f"- {turn.role.upper()}: {turn.content}"
                for turn in request.conversation_history
            )
            history_block = f"Recent conversation history:\n{turns}\n\n"

        user_prompt = (
            f"Reference date: {reference_date.isoformat()}\n\n"
            f"{history_block}"
            f"Employee question: {request.query}"
        )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _parse_and_validate_output(
        raw_content: str,
        original_query: str,
        model_used: str,
    ) -> QueryUnderstandingResult:
        cleaned = _strip_markdown_fences(raw_content)
        try:
            payload: Any = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning("LLM returned invalid JSON for query understanding: %s", sanitized)
            raise LLMOutputValidationError(
                f"LLM output is not valid JSON: {sanitized}"
            ) from exc

        if not isinstance(payload, dict):
            raise LLMOutputValidationError(
                f"LLM output must be a JSON object, got {type(payload).__name__}."
            )

        # Always preserve the exact employee question and model identifier
        payload["original_query"] = original_query
        payload["model_used"] = model_used

        # Ensure clarification consistency if intent is CLARIFICATION
        if payload.get("intent") == QueryIntent.CLARIFICATION.value:
            payload.setdefault("needs_clarification", True)

        try:
            return QueryUnderstandingResult.model_validate(payload)
        except ValidationError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning("LLM output failed schema validation: %s", sanitized)
            raise LLMOutputValidationError(
                f"LLM output failed schema validation: {sanitized}"
            ) from exc


def get_query_understanding_service(
    llm_client: Optional[LLMClient] = None,
) -> QueryUnderstandingService:
    """FastAPI/application dependency provider for QueryUnderstandingService."""
    return QueryUnderstandingService(llm_client=llm_client or get_llm_client())


__all__ = [
    "QueryUnderstandingService",
    "QueryUnderstandingError",
    "InvalidQueryInputError",
    "LLMOutputValidationError",
    "LLMError",
    "get_query_understanding_service",
]
