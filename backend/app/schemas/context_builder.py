"""
Pydantic v2 schemas for Task 06D — Conversation History & Context Builder.

Defines validated input (`ContextBuilderRequest`) and output (`ContextBuilderResult`)
contracts for loading recent conversation turns, resolving follow-up references,
and preparing standalone queries for downstream policy RAG retrieval.
"""

import uuid
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingRequest


class ContextBuilderRequest(BaseModel):
    """Input payload for building conversation context and resolving follow-up queries."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Raw natural-language question or follow-up prompt from the employee",
        examples=["How many can I carry forward?"],
    )
    conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional UUID of the conversation thread to load history from",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    max_history_turns: int = Field(
        default=6,
        ge=1,
        le=10,
        description="Maximum number of recent conversation messages to include in the context window (bounded 1 to 10)",
        examples=[6],
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query cannot be empty or whitespace-only.")
        return cleaned

    model_config = ConfigDict(extra="forbid")


class ContextBuilderResult(BaseModel):
    """
    Validated structured result produced by ContextBuilderService.
    Preserves original query, standalone resolved query, and bounded conversation history.
    """

    original_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Original employee question preserved verbatim for traceability",
        examples=["How many can I carry forward?"],
    )
    standalone_query: str = Field(
        ...,
        min_length=1,
        max_length=2500,
        description="Context-resolved standalone query suitable for search/retrieval",
        examples=["What does the annual leave policy say about carrying forward unused annual leave?"],
    )
    conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID of the parent conversation thread, if provided",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    history_message_count: int = Field(
        default=0,
        ge=0,
        description="Number of historical messages extracted and included in the context window",
        examples=[2],
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Chronological list of recent conversation turns (oldest to newest)",
    )
    is_follow_up: bool = Field(
        default=False,
        description="True if contextual resolution or pronoun rewriting was applied",
        examples=[True],
    )
    requires_clarification: bool = Field(
        default=False,
        description="True if the follow-up question is too ambiguous to resolve from context",
        examples=[False],
    )
    clarification_reason: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Brief explanation when requires_clarification is True",
    )
    model_used: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Identifier of LLM used for resolution, or None if resolved deterministically",
        examples=["llama-3.3-70b-versatile"],
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("original_query", "standalone_query")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace-only.")
        return cleaned

    def to_query_understanding_request(self, reference_date=None) -> QueryUnderstandingRequest:
        """
        Convenience adapter to convert this result directly into a Task 05A QueryUnderstandingRequest.
        Uses standalone_query as the input query while passing along the conversation_history.
        """
        return QueryUnderstandingRequest(
            query=self.standalone_query,
            conversation_history=self.conversation_history,
            reference_date=reference_date,
        )
