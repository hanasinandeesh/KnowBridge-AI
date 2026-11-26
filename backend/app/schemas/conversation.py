import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationCreate(BaseModel):
    """Payload for creating a new conversation thread."""

    title: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Optional title for the conversation. Defaults to 'New Conversation' if omitted.",
        examples=["Travel Reimbursement Policy Inquiry"],
    )

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_stripped = v.strip()
            return v_stripped if v_stripped else None
        return None

    model_config = ConfigDict(extra="forbid")


class ConversationUpdate(BaseModel):
    """Payload for updating an existing conversation's metadata."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Updated conversation title (must not be empty or whitespace-only)",
        examples=["Updated Travel Reimbursement Guidelines"],
    )

    @field_validator("title", mode="before")
    @classmethod
    def validate_and_strip_title(cls, v: str) -> str:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                raise ValueError("Title cannot be empty or whitespace only.")
            return v_stripped
        return v

    model_config = ConfigDict(extra="forbid")


class ConversationResponse(BaseModel):
    """Public representation of a conversation thread."""

    id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier for the conversation thread",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    title: str = Field(
        ...,
        description="Conversation title",
        examples=["Travel Reimbursement Policy Inquiry"],
    )
    message_count: int = Field(
        default=0,
        description="Total number of messages currently recorded in this conversation",
        examples=[4],
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when conversation thread was created",
    )
    updated_at: datetime = Field(
        ...,
        description="Timestamp when conversation thread was last modified",
    )

    model_config = ConfigDict(from_attributes=True)


class ConversationListResponse(BaseModel):
    """Paginated list envelope for conversation threads."""

    items: List[ConversationResponse] = Field(
        default_factory=list,
        description="List of conversation items for the current page",
    )
    total: int = Field(
        ...,
        ge=0,
        description="Total count of conversations matching query criteria",
        examples=[42],
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
        description="Number of items returned per page",
        examples=[20],
    )
    total_pages: int = Field(
        ...,
        ge=0,
        description="Total number of pages calculated from total and page_size",
        examples=[3],
    )
    has_next: bool = Field(
        ...,
        description="Whether a subsequent page of conversations is available",
        examples=[True],
    )
    has_prev: bool = Field(
        ...,
        description="Whether a previous page of conversations is available",
        examples=[False],
    )

    model_config = ConfigDict(from_attributes=True)
