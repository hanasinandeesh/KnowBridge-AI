"""
Conversation History & Context Builder Service — Task 06D.

Provides business logic for loading recent conversation history, selecting a bounded
context window, resolving follow-up questions into standalone search-ready queries,
and preparing inputs for the downstream QueryUnderstanding pipeline.
"""

import json
import logging
import re
import uuid
from typing import Any, Optional, Union

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import sanitize_error_message
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.context_builder import ContextBuilderRequest, ContextBuilderResult
from app.schemas.query_understanding import ConversationTurn
from app.services.llm_client import LLMClient, LLMError, get_llm_client
from app.services.message_service import ConversationNotFoundError

logger = logging.getLogger("app.services.context_builder")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_CONTEXT_RESOLVER_SYSTEM_PROMPT = """You are the Conversation History & Context Resolver for KnowBridge AI, an enterprise policy-aware RAG platform.
Your task is to analyze the employee's new question in light of recent conversation history and rewrite it into a clear, standalone, search-ready query for policy document retrieval.

Rules:
1. PRESERVE ORIGINAL INTENT: The standalone query must express exactly what the user is asking in their new question.
2. GROUND IN HISTORY: Resolve pronouns ("it", "they", "this", "that", "these") and elliptical follow-up questions (e.g., "How many can I carry forward?", "Does this apply to contractors?", "What is the eligibility?") using ONLY the policy subjects and entities explicitly mentioned in the recent conversation history.
3. NO HALLUCINATION: NEVER invent facts, policy rules, numerical allowances, or requirements that are not in the conversation history.
4. UNRELATED QUESTIONS: If the employee asks an unrelated new question (e.g., previous turn was about travel expenses, but the new question asks "What is the remote work policy?"), DO NOT inject previous context. Keep the question standalone as asked, and set "is_follow_up": false.
5. AMBIGUITY & CLARIFICATION: If the question contains an ambiguous reference that cannot be resolved from the conversation context (e.g., "Can you explain that again?" or "What about the other one?"), set "requires_clarification": true and provide a concise "clarification_reason". Otherwise, set "requires_clarification": false and "clarification_reason": null.

Return ONLY a single valid JSON object matching this exact structure:
{
  "standalone_query": "Clear standalone search query...",
  "is_follow_up": true,
  "requires_clarification": false,
  "clarification_reason": null
}"""


class ContextBuilderError(Exception):
    """Base exception for ContextBuilderService failures."""
    pass


class InvalidContextBuilderInputError(ContextBuilderError):
    """Raised when input parameters fail validation."""
    pass


def _strip_markdown_fences(raw_text: str) -> str:
    """Removes optional ```json ... ``` wrappers around JSON text."""
    return _CODE_FENCE_RE.sub("", raw_text.strip()).strip()


class ContextBuilderService:
    """
    Loads recent conversation turns and resolves follow-up queries
    into standalone search-ready queries for downstream RAG retrieval.
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self.db = db
        self._llm_client: LLMClient = llm_client or get_llm_client()

    def load_history(
        self,
        conversation_id: uuid.UUID,
        max_turns: int = 6,
    ) -> list[ConversationTurn]:
        """
        Loads the most recent conversation turns from the database in chronological order.

        Args:
            conversation_id: UUID of the conversation thread.
            max_turns: Maximum number of recent messages to retrieve (bounded 1 to 10).

        Returns:
            List of `ConversationTurn` objects ordered chronologically (oldest to newest).

        Raises:
            ConversationNotFoundError: If the conversation thread does not exist.
            ContextBuilderError: If database access is not configured or query fails.
        """
        if not self.db:
            raise ContextBuilderError("Database session is required to load conversation history.")

        max_turns = min(max(1, max_turns), 10)

        try:
            # Verify parent conversation exists
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                logger.warning("Conversation %s not found when loading history", conversation_id)
                raise ConversationNotFoundError(f"Conversation with ID '{conversation_id}' not found.")

            # Efficiently query the most recent N messages (descending), filtering out system messages
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .where(Message.role.in_(["user", "assistant"]))
                .order_by(Message.created_at.desc(), Message.id.desc())
                .limit(max_turns)
            )

            recent_messages = self.db.execute(stmt).scalars().all()

            # Reverse back into ascending chronological order (oldest -> newest)
            chronological_messages = list(reversed(recent_messages))

            return [
                ConversationTurn(role=m.role, content=m.content)
                for m in chronological_messages
            ]
        except ConversationNotFoundError:
            raise
        except SQLAlchemyError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to load conversation history for %s: %s", conversation_id, sanitized)
            raise ContextBuilderError(f"Database error loading conversation history: {sanitized}") from exc

    def build_context(
        self,
        request: Union[ContextBuilderRequest, str],
        in_memory_history: Optional[list[ConversationTurn]] = None,
    ) -> ContextBuilderResult:
        """
        Builds conversation context and resolves follow-up questions.

        Args:
            request: Either a `ContextBuilderRequest` or a raw query string.
            in_memory_history: Optional explicit history turns (bypasses database query if provided).

        Returns:
            Validated `ContextBuilderResult` preserving both `original_query` and `standalone_query`.
        """
        validated_req = self._validate_request(request)

        # 1. Obtain conversation history
        history: list[ConversationTurn] = []
        if in_memory_history is not None:
            # Use bounded slice of provided in-memory history
            history = in_memory_history[-validated_req.max_history_turns:]
        elif validated_req.conversation_id is not None:
            history = self.load_history(
                conversation_id=validated_req.conversation_id,
                max_turns=validated_req.max_history_turns,
            )

        # 2. Deterministic fast-path: If history is empty, no resolution needed
        if not history:
            return ContextBuilderResult(
                original_query=validated_req.query,
                standalone_query=validated_req.query,
                conversation_id=validated_req.conversation_id,
                history_message_count=0,
                conversation_history=[],
                is_follow_up=False,
                requires_clarification=False,
                clarification_reason=None,
                model_used=None,
            )

        # 3. Contextual LLM Follow-up Resolution
        return self._resolve_with_llm(
            query=validated_req.query,
            history=history,
            conversation_id=validated_req.conversation_id,
        )

    def _resolve_with_llm(
        self,
        query: str,
        history: list[ConversationTurn],
        conversation_id: Optional[uuid.UUID],
    ) -> ContextBuilderResult:
        """Invokes Groq LLM to rewrite ambiguous or follow-up query into a standalone query."""
        history_text = "\n".join(
            f"- {turn.role.upper()}: {turn.content}"
            for turn in history
        )

        user_content = (
            f"Recent conversation history:\n{history_text}\n\n"
            f"Employee new question: {query}"
        )

        messages = [
            {"role": "system", "content": _CONTEXT_RESOLVER_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            raw_content, model_used = self._llm_client.complete_json(
                messages=messages,
                temperature=0.0,
                max_tokens=512,
            )
            parsed = self._parse_llm_response(raw_content)

            standalone = parsed.get("standalone_query") or query
            is_follow_up = bool(parsed.get("is_follow_up", False))
            requires_clarification = bool(parsed.get("requires_clarification", False))
            clarification_reason = parsed.get("clarification_reason")

            logger.info(
                "Resolved context for query: is_follow_up=%s requires_clarification=%s model=%s",
                is_follow_up,
                requires_clarification,
                model_used,
            )

            return ContextBuilderResult(
                original_query=query,
                standalone_query=standalone,
                conversation_id=conversation_id,
                history_message_count=len(history),
                conversation_history=history,
                is_follow_up=is_follow_up,
                requires_clarification=requires_clarification,
                clarification_reason=clarification_reason,
                model_used=model_used,
            )
        except (LLMError, json.JSONDecodeError, ValidationError) as exc:
            # Graceful fallback: Never crash the request pipeline if resolution fails
            sanitized = sanitize_error_message(str(exc))
            logger.warning(
                "LLM context resolution failed (%s). Falling back gracefully to original query.",
                sanitized,
            )
            return ContextBuilderResult(
                original_query=query,
                standalone_query=query,
                conversation_id=conversation_id,
                history_message_count=len(history),
                conversation_history=history,
                is_follow_up=False,
                requires_clarification=False,
                clarification_reason=None,
                model_used="fallback-original",
            )

    @staticmethod
    def _validate_request(
        request: Union[ContextBuilderRequest, str],
    ) -> ContextBuilderRequest:
        try:
            if isinstance(request, str):
                return ContextBuilderRequest(query=request)
            if isinstance(request, ContextBuilderRequest):
                return request
            return ContextBuilderRequest.model_validate(request)
        except ValidationError as exc:
            raise InvalidContextBuilderInputError(f"Invalid context builder input: {exc}") from exc

    @staticmethod
    def _parse_llm_response(raw_content: str) -> dict[str, Any]:
        cleaned = _strip_markdown_fences(raw_content)
        payload = json.loads(cleaned)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object, got {type(payload).__name__}")
        return payload


def get_context_builder_service(
    db: Session,
    llm_client: Optional[LLMClient] = None,
) -> ContextBuilderService:
    """Dependency provider for ContextBuilderService."""
    return ContextBuilderService(db=db, llm_client=llm_client)
