"""
Pydantic schemas for Task 06E — Persistent Memory System.

Defines schemas for extracting, validating, persisting, retrieving,
and managing persistent user memory context across conversation sessions.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryType(str, Enum):
    """Categorization for persistent user memory items."""

    DEPARTMENT = "department"
    ROLE = "role"
    EMPLOYMENT_TYPE = "employment_type"
    LOCATION = "location"
    POLICY_PREFERENCE = "policy_preference"
    USER_CONSTRAINT = "user_constraint"
    GENERAL = "general"


class ExtractedMemoryItem(BaseModel):
    """
    A single factual attribute extracted from conversational dialogue.
    Produced by the LLM extraction step before database validation and storage.
    """

    memory_key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Structured machine key for the fact (e.g. 'department', 'work_location')",
    )
    memory_value: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Factual value extracted (e.g. 'Engineering', 'London', 'Contractor')",
    )
    memory_text: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Natural language summary statement of the fact",
    )
    memory_type: MemoryType = Field(
        default=MemoryType.GENERAL,
        description="Category classification of the memory item",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score in the extraction from 0.0 to 1.0",
    )
    is_durable: bool = Field(
        default=True,
        description="Whether this fact is a durable attribute versus a transient/fleeting situation",
    )
    is_sensitive_pii: bool = Field(
        default=False,
        description="Flagged true if the fact contains sensitive personal data (SSN, credit card, passwords)",
    )
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="Optional shelf-life in days for time-bounded attributes",
    )

    @field_validator("memory_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        cleaned = value.strip().lower().replace(" ", "_").replace("-", "_")
        if not cleaned:
            raise ValueError("memory_key cannot be blank.")
        return cleaned

    @field_validator("memory_value", "memory_text")
    @classmethod
    def strip_value(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only.")
        return cleaned


class MemoryCreate(BaseModel):
    """Payload to persist or upsert a verified memory into database storage."""

    session_key: str = Field(
        default="default",
        max_length=100,
        description="User or workspace session namespace identifier",
    )
    memory_key: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Structured key (e.g. 'department', 'role')",
    )
    memory_value: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Factual value (e.g. 'Engineering', 'Sydney')",
    )
    memory_text: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Natural language statement. Defaults to generated value if omitted.",
    )
    memory_type: MemoryType = Field(
        default=MemoryType.GENERAL,
        description="Category classification",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0",
    )
    source_conversation_id: Optional[uuid.UUID] = Field(
        default=None,
        description="Originating conversation thread UUID",
    )
    expires_at: Optional[datetime] = Field(
        default=None,
        description="Optional timestamp when memory expires",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Audit history and extraction provenance metadata",
    )

    @field_validator("memory_key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        return value.strip().lower().replace(" ", "_").replace("-", "_")

    @field_validator("memory_value")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()


class MemoryResponse(BaseModel):
    """Response model for a persisted user memory record."""

    id: uuid.UUID
    session_key: str
    memory_key: str
    memory_value: str
    memory_text: str
    memory_type: str
    source_conversation_id: Optional[uuid.UUID] = None
    confidence_score: float
    metadata: dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MemoryListResponse(BaseModel):
    """Paginated or bounded list response for memories."""

    items: list[MemoryResponse]
    total: int
    session_key: str


class ActiveMemoryContext(BaseModel):
    """
    Active unexpired user context packaged for downstream RAG consumption.
    Can be used by Query Understanding (Task 05A) and Orchestration (Task 06F).
    """

    session_key: str = "default"
    department: Optional[str] = None
    role: Optional[str] = None
    employment_type: Optional[str] = None
    location: Optional[str] = None
    constraints: list[str] = Field(default_factory=list)
    preferences: list[str] = Field(default_factory=list)
    raw_memories: list[MemoryResponse] = Field(default_factory=list)

    def to_context_string(self) -> str:
        """Renders active memory as a concise bulleted block for LLM prompts."""
        lines = []
        if self.department:
            lines.append(f"- Department: {self.department}")
        if self.role:
            lines.append(f"- Role: {self.role}")
        if self.employment_type:
            lines.append(f"- Employment Type: {self.employment_type}")
        if self.location:
            lines.append(f"- Location: {self.location}")
        for c in self.constraints:
            lines.append(f"- Constraint: {c}")
        for p in self.preferences:
            lines.append(f"- Preference: {p}")
        return "\n".join(lines)
