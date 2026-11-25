"""
Pydantic schemas for Task 05C — Grounded LLM Answer Generation.

Defines validated request, citation, status, and response schemas built on
Task 04 (`EvidencePackage`), Task 05A (`QueryUnderstandingResult`), and
Task 05B (`EvidenceAssessmentResult`).
"""

import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.evidence_assessment import (
    EvidenceAssessmentResult,
    EvidenceReference,
    PolicyConflictItem,
)
from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.retrieval import EvidenceItem, EvidencePackage


class AnswerStatus(str, Enum):
    """Outcome status of the answer generation step."""

    ANSWERED = "ANSWERED"
    PARTIALLY_SUPPORTED_ABSTAINED = "PARTIALLY_SUPPORTED_ABSTAINED"
    ABSTAINED = "ABSTAINED"
    CONFLICT_DETECTED = "CONFLICT_DETECTED"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class AnswerCitation(BaseModel):
    """Verified citation referencing an exact retrieved EvidenceItem."""

    citation_index: int = Field(..., ge=1, description="1-based citation index")
    chunk_id: uuid.UUID = Field(..., description="Unique UUID of the source chunk")
    document_id: Optional[uuid.UUID] = Field(default=None, description="Parent document UUID")
    document_title: str = Field(..., min_length=1, description="Human-readable document title")
    version_label: Optional[str] = Field(default=None, description="Document version label")
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based physical page number (for PDF); None for DOCX/TXT",
    )
    section_title: Optional[str] = Field(default=None, description="Section heading if available")
    citation_tag: str = Field(..., min_length=1, description="Formatted source citation tag")
    snippet: str = Field(
        ...,
        min_length=1,
        max_length=300,
        description="Short verbatim excerpt from the source chunk",
    )

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_evidence_item(cls, item: EvidenceItem) -> "AnswerCitation":
        """Builds a verified AnswerCitation strictly from a Task 04 EvidenceItem."""
        text = item.chunk_text.strip()
        snippet = text[:297].rstrip() + "..." if len(text) > 300 else text
        return cls(
            citation_index=item.citation_index,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_title=item.document_title,
            version_label=item.version_label,
            page_number=item.page_number,
            section_title=item.section_title,
            citation_tag=item.citation_tag,
            snippet=snippet or item.citation_tag,
        )


class AnswerGenerationRequest(BaseModel):
    """Input payload for AnswerGenerationService."""

    original_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Original employee question preserved verbatim",
    )
    query_understanding: QueryUnderstandingResult = Field(
        ...,
        description="Structured output from Task 05A QueryUnderstandingService",
    )
    evidence_package: EvidencePackage = Field(
        ...,
        description="Retrieved evidence package from Task 04 RetrievalService",
    )
    evidence_assessment: EvidenceAssessmentResult = Field(
        ...,
        description="Validated assessment output from Task 05B EvidenceAssessmentService",
    )

    @field_validator("original_query")
    @classmethod
    def validate_original_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("original_query cannot be empty or whitespace-only.")
        return cleaned


class AnswerGenerationResult(BaseModel):
    """Validated final response produced by AnswerGenerationService."""

    original_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Original employee question preserved verbatim",
    )
    answer: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="Grounded answer, safe abstention, conflict disclosure, or clarification prompt",
    )
    status: AnswerStatus = Field(..., description="Generation outcome status")
    citations: list[AnswerCitation] = Field(
        default_factory=list,
        description="Verified citations backing factual claims in the answer",
    )
    supporting_evidence: list[EvidenceReference] = Field(
        default_factory=list,
        description="Supporting evidence references preserved from Task 05B",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Missing details preserved from Task 05B when applicable",
    )
    conflicts: list[PolicyConflictItem] = Field(
        default_factory=list,
        description="Policy conflicts preserved from Task 05B when applicable",
    )
    model_used: Optional[str] = Field(
        default=None,
        max_length=120,
        description="LLM model used for synthesis; None for deterministic abstention/conflict",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("original_query", "answer")
    @classmethod
    def strip_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace-only.")
        return cleaned
