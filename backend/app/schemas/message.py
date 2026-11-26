"""
Pydantic v2 schemas for Message Persistence.
Task 06C — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Defines schemas for message creation, serialization, structured citations,
evidence status, and paginated message history retrieval.
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MessageRole(str, Enum):
    """Permitted message sender roles matching database CHECK constraint."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class EvidenceStatusEnum(str, Enum):
    """Permitted evidence evaluation outcomes matching database CHECK constraint."""

    SUPPORTED = "SUPPORTED"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICTING = "CONFLICTING"


class CitationItem(BaseModel):
    """
    Structured citation reference metadata for assistant responses.
    Aligns directly with Task 04/05 AnswerCitation schema.
    """

    citation_index: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based citation index in generated response",
        examples=[1],
    )
    chunk_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID of source document chunk",
    )
    document_id: Optional[uuid.UUID] = Field(
        default=None,
        description="UUID of parent policy document",
    )
    document_title: str = Field(
        ...,
        min_length=1,
        description="Human-readable title of the cited document",
        examples=["HR-TRV-001 Travel & Reimbursement Policy"],
    )
    version_label: Optional[str] = Field(
        default=None,
        description="Document version label (e.g., 'v2.0')",
        examples=["v2.0"],
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based physical page number if applicable (PDF)",
        examples=[4],
    )
    section_title: Optional[str] = Field(
        default=None,
        description="Section header or title if available",
        examples=["4.2 Daily Meal Allowances"],
    )
    citation_tag: Optional[str] = Field(
        default=None,
        description="Short citation tag (e.g., '[HR-TRV-001 p.4]')",
        examples=["[HR-TRV-001 p.4]"],
    )
    snippet: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Verbatim excerpt from the source chunk supporting the claim",
        examples=["Daily meal reimbursement is capped at $75 per day for domestic travel."],
    )

    model_config = ConfigDict(extra="forbid")


class MessageCreate(BaseModel):
    """Payload for creating and persisting a message in a conversation thread."""

    role: MessageRole = Field(
        ...,
        description="Message role: 'user', 'assistant', or 'system'",
        examples=["user"],
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Text content of the message prompt or assistant response (must not be empty)",
        examples=["What is the maximum daily meal allowance for domestic travel?"],
    )
    citations: Optional[List[CitationItem]] = Field(
        default_factory=list,
        description="Structured citations backing factual claims (primarily for assistant responses)",
    )
    evidence_status: Optional[EvidenceStatusEnum] = Field(
        default=None,
        description="Evidence assessment state: 'SUPPORTED', 'INSUFFICIENT', or 'CONFLICTING'",
        examples=["SUPPORTED"],
    )
    trace_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Observability trace ID linking generation to Langfuse spans",
        examples=["trace-01936c50-8b4b-7000-84cf-cb6014e3001a"],
    )

    @field_validator("content", mode="before")
    @classmethod
    def validate_and_strip_content(cls, v: Any) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Message content cannot be empty or whitespace only.")
            return v_stripped
        return v

    model_config = ConfigDict(extra="forbid")


class MessageResponse(BaseModel):
    """Public representation of a persisted conversation message."""

    id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier for the message",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    conversation_id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier of the parent conversation thread",
        examples=["550e8400-e29b-41d4-a716-446655440001"],
    )
    role: str = Field(
        ...,
        description="Message role ('user', 'assistant', or 'system')",
        examples=["user"],
    )
    content: str = Field(
        ...,
        description="Text content of the message",
        examples=["What is the maximum daily meal allowance for domestic travel?"],
    )
    citations: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Structured citations list stored with the message",
    )
    evidence_status: Optional[str] = Field(
        default=None,
        description="Evidence assessment state: 'SUPPORTED', 'INSUFFICIENT', or 'CONFLICTING'",
        examples=["SUPPORTED"],
    )
    trace_id: Optional[str] = Field(
        default=None,
        description="Observability trace ID for Langfuse span linking",
        examples=["trace-01936c50-8b4b-7000-84cf-cb6014e3001a"],
    )
    feedback_score: Optional[int] = Field(
        default=None,
        description="User feedback score (-1, 0, or 1)",
        examples=[1],
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when message was recorded",
    )

    model_config = ConfigDict(from_attributes=True)


class MessageListResponse(BaseModel):
    """Paginated list envelope for messages in a conversation."""

    items: List[MessageResponse] = Field(
        default_factory=list,
        description="List of messages in chronological order for the current page",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total count of messages in this conversation thread",
        examples=[12],
    )
    page: int = Field(
        ...,
        ge=1,
        description="Current 1-based page number",
        examples=[1],
    )
    page_size: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of messages returned per page",
        examples=[50],
    )
    total_pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages calculated from total and page_size",
        examples=[1],
    )
    has_next: bool = Field(
        ...,
        description="Whether a subsequent page of messages is available",
        examples=[False],
    )
    has_prev: bool = Field(
        ...,
        description="Whether a previous page of messages is available",
        examples=[False],
    )

    model_config = ConfigDict(from_attributes=True)
