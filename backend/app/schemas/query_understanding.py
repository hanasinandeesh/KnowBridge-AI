"""
Pydantic schemas for Task 05A — Query Understanding.

Defines request, intent, retrieval hint, and structured output models
for converting employee natural-language questions into validated,
search-oriented representations.
"""

from datetime import date
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QueryIntent(str, Enum):
    """Supported enterprise policy query intent categories."""

    POLICY_LOOKUP = "policy_lookup"
    ELIGIBILITY = "eligibility"
    COMPARISON = "comparison"
    SUMMARIZATION = "summarization"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"


class ConversationTurn(BaseModel):
    """Single historical turn passed for conversational query disambiguation."""

    role: Literal["user", "assistant"] = Field(
        ...,
        description="Speaker role in the conversation turn",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Turn message text",
    )

    @field_validator("content")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Conversation turn content cannot be empty or whitespace-only.")
        return cleaned


class QueryUnderstandingRequest(BaseModel):
    """Input payload for the query understanding service."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Raw natural-language question from the employee",
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=10,
        description="Recent conversation turns for pronoun/context resolution",
    )
    reference_date: Optional[date] = Field(
        default=None,
        description="Optional reference date for resolving relative temporal expressions (defaults to today)",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query cannot be empty or whitespace-only.")
        return cleaned


def _clean_string_list(items: list[str], max_items: int, max_len: int) -> list[str]:
    """Strips, deduplicates (case-insensitive), and bounds a list of short strings."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = item.strip()
        if not text:
            continue
        if len(text) > max_len:
            text = text[:max_len].strip()
        key = text.lower()
        if key not in seen:
            seen.add(key)
            cleaned.append(text)
        if len(cleaned) >= max_items:
            break
    return cleaned


class RetrievalHints(BaseModel):
    """
    Advisory retrieval hints extracted from the user's question.
    Assists Task 04 RetrievalService without overriding its policy/version logic.
    """

    keywords: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Key search terms extracted for retrieval",
    )
    entities: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="Named entities (roles, locations, amounts, policy codes) mentioned in the query",
    )
    department_hint: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Advisory department hint (e.g., 'Human Resources', 'Finance', 'IT')",
    )
    category_hint: Optional[str] = Field(
        default=None,
        max_length=120,
        description="Advisory policy category hint",
    )
    effective_date_hint: Optional[date] = Field(
        default=None,
        description="Explicitly mentioned or unambiguously resolved policy applicability date",
    )
    version_hint: Optional[str] = Field(
        default=None,
        max_length=32,
        description="Explicitly mentioned policy version label (e.g., '1.0', 'v2.0')",
    )

    @field_validator("keywords")
    @classmethod
    def validate_keywords(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value, max_items=10, max_len=80)

    @field_validator("entities")
    @classmethod
    def validate_entities(cls, value: list[str]) -> list[str]:
        return _clean_string_list(value, max_items=10, max_len=100)

    @field_validator("department_hint", "category_hint", "version_hint")
    @classmethod
    def normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class QueryUnderstandingResult(BaseModel):
    """Validated structured output produced by the query understanding component."""

    original_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Original employee question preserved verbatim for traceability",
    )
    intent: QueryIntent = Field(
        ...,
        description="Detected question intent category",
    )
    primary_topic: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Primary policy or subject identified (or 'unknown' if underspecified)",
    )
    rewritten_query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Clear, search-oriented standalone query preserving original meaning",
    )
    retrieval_hints: RetrievalHints = Field(
        default_factory=RetrievalHints,
        description="Advisory keywords, entities, and explicit temporal/version hints",
    )
    needs_clarification: bool = Field(
        default=False,
        description="True when the query is too ambiguous or underspecified for reliable retrieval",
    )
    clarification_reason: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Brief explanation when needs_clarification is True",
    )
    model_used: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Identifier of the LLM model that produced this analysis",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("original_query", "primary_topic", "rewritten_query", "model_used")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace-only.")
        return cleaned

    @field_validator("clarification_reason")
    @classmethod
    def normalize_clarification_reason(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
