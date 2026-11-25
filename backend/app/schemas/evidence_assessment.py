"""
Pydantic schemas for Task 05B — Evidence Sufficiency & Conflict Detection.

Defines validated request, decision, support level, conflict, and explainability
schemas built directly on Task 04 (`EvidencePackage`, `RetrievalResult`) and
Task 05A (`QueryUnderstandingResult`) contracts.
"""

import uuid
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.query_understanding import QueryUnderstandingResult
from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult


class EvidenceDecision(str, Enum):
    """High-level evidence assessment outcome guiding downstream synthesis or abstention."""

    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"
    CONFLICT = "CONFLICT"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"


class SupportLevel(str, Enum):
    """Granular completeness of the retrieved evidence relative to the question."""

    FULL = "FULL"
    PARTIAL = "PARTIAL"
    NONE = "NONE"


class EvidenceReference(BaseModel):
    """Verified reference pointing to a retrieved `EvidenceItem`."""

    citation_index: int = Field(..., ge=1, description="1-based citation index from EvidencePackage")
    chunk_id: uuid.UUID = Field(..., description="Unique UUID of the source chunk")
    document_title: str = Field(..., min_length=1, description="Source document title")
    version_label: Optional[str] = Field(default=None, description="Document version label")
    page_number: Optional[int] = Field(default=None, ge=1, description="1-based PDF page number")
    citation_tag: str = Field(..., min_length=1, description="Formatted citation tag")

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_evidence_item(cls, item: EvidenceItem) -> "EvidenceReference":
        """Builds an EvidenceReference directly from a Task 04 EvidenceItem."""
        return cls(
            citation_index=item.citation_index,
            chunk_id=item.chunk_id,
            document_title=item.document_title,
            version_label=item.version_label,
            page_number=item.page_number,
            citation_tag=item.citation_tag,
        )


class PolicyConflictItem(BaseModel):
    """Structured representation of a contradiction or overlapping-version conflict."""

    conflict_id: str = Field(..., min_length=1, max_length=64, description="Deterministic conflict ID")
    conflict_type: Literal["cross_document_contradiction", "version_overlap_ambiguity"] = Field(
        ...,
        description="Category of policy conflict detected",
    )
    description: str = Field(..., min_length=1, max_length=500, description="Summary of the conflict")
    claim_a: str = Field(..., min_length=1, max_length=500, description="First conflicting policy claim")
    source_a: EvidenceReference = Field(..., description="Verified source for claim_a")
    claim_b: str = Field(..., min_length=1, max_length=500, description="Second conflicting policy claim")
    source_b: EvidenceReference = Field(..., description="Verified source for claim_b")


class EvidenceAssessmentRequest(BaseModel):
    """Input payload for EvidenceAssessmentService."""

    query_understanding: QueryUnderstandingResult = Field(
        ...,
        description="Structured output from Task 05A QueryUnderstandingService",
    )
    evidence_package: EvidencePackage = Field(
        ...,
        description="Retrieved evidence package from Task 04 RetrievalService",
    )
    retrieval_result: Optional[RetrievalResult] = Field(
        default=None,
        description="Optional full RetrievalResult providing version/ambiguity metadata",
    )
    min_similarity_threshold: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity cutoff required to treat evidence as relevant",
    )


class EvidenceAssessmentResult(BaseModel):
    """Validated, explainable output from EvidenceAssessmentService."""

    decision: EvidenceDecision = Field(..., description="Overall evidence assessment decision")
    support_level: SupportLevel = Field(..., description="Degree to which evidence covers the question")
    is_relevant: bool = Field(..., description="True if retrieved evidence addresses the question")
    reasoning: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Concise explanation of why the decision was reached",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Specific gaps identified when support is PARTIAL or NONE",
    )
    supporting_evidence: list[EvidenceReference] = Field(
        default_factory=list,
        description="Verified evidence references supporting the assessment",
    )
    conflicts: list[PolicyConflictItem] = Field(
        default_factory=list,
        description="Detected contradictions or overlapping active version conflicts",
    )
    ignored_superseded_sources: list[EvidenceReference] = Field(
        default_factory=list,
        description="Non-current/superseded sources excluded from active conflict evaluation",
    )
    model_used: Optional[str] = Field(
        default=None,
        max_length=120,
        description="LLM model identifier if semantic assessment ran; None if resolved deterministically",
    )

    model_config = ConfigDict(from_attributes=True)

    @field_validator("reasoning")
    @classmethod
    def strip_reasoning(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("reasoning cannot be empty or whitespace-only.")
        return cleaned
