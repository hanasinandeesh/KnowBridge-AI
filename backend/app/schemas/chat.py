"""
Pydantic schemas for Task 06F — End-to-End Chat & Feedback APIs.

Defines client contracts for conversational RAG queries, structured answers
with citations and evidence status, and user feedback ratings.
"""

from datetime import date, datetime
from typing import Any, Literal, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.answer_generation import AnswerCitation


class ChatRequest(BaseModel):
    """Input payload for POST /api/v1/chat endpoint."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Employee's natural-language policy question",
    )
    conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Optional existing conversation thread UUID. If omitted, a new conversation is created.",
    )
    session_key: str = Field(
        default="default",
        max_length=100,
        description="Session or user namespace identifier for persistent memory retrieval",
    )
    reference_date: Optional[date] = Field(
        default=None,
        description="Optional date for relative temporal resolution",
    )
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional override for chunk similarity threshold",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional override for number of candidate policy chunks retrieved",
    )

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query cannot be empty or whitespace-only.")
        return cleaned

    @field_validator("session_key")
    @classmethod
    def strip_session_key(cls, value: str) -> str:
        cleaned = value.strip()
        return cleaned or "default"


class ChatResponse(BaseModel):
    """Output payload from POST /api/v1/chat endpoint."""

    conversation_id: uuid.UUID = Field(
        ...,
        description="Conversation thread UUID (created or continued)",
    )
    user_message_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Persisted user message UUID in database",
    )
    assistant_message_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Persisted assistant answer UUID in database",
    )
    original_query: str = Field(
        ...,
        description="Employee's verbatim question as asked",
    )
    standalone_query: str = Field(
        ...,
        description="Search-ready standalone query resolved from context",
    )
    is_follow_up: bool = Field(
        default=False,
        description="Whether the query was resolved as an elliptical follow-up",
    )
    answer: str = Field(
        ...,
        description="Grounded assistant answer, safe abstention, or conflict notice",
    )
    citations: list[AnswerCitation] = Field(
        default_factory=list,
        description="Structured citations linking statements to source policy documents",
    )
    evidence_status: str = Field(
        default="SUPPORTED",
        description="Status: 'SUPPORTED', 'INSUFFICIENT', 'CONFLICT', or 'CLARIFICATION_REQUIRED'",
    )
    active_memory_used: Optional[dict[str, Any]] = Field(
        default=None,
        description="Active employee profile attributes applied during query understanding",
    )
    workflow_status: Literal["completed", "failed"] = Field(
        default="completed",
        description="Status of the LangGraph execution",
    )
    error_stage: Optional[str] = Field(
        default=None,
        description="Stage name where failure occurred if workflow failed",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Sanitized failure message if workflow failed",
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Completion timestamp",
    )

    model_config = ConfigDict(from_attributes=True)


class FeedbackRequest(BaseModel):
    """Payload for submitting user thumbs up/down feedback."""

    message_id: uuid.UUID = Field(
        ...,
        description="Target assistant message UUID",
    )
    feedback_score: int = Field(
        ...,
        ge=-1,
        le=1,
        description="Feedback score: 1 for thumbs up, -1 for thumbs down, 0 for neutral",
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional employee explanation or feedback comments",
    )


class FeedbackResponse(BaseModel):
    """Response after recording user feedback."""

    message_id: uuid.UUID
    feedback_score: int
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
