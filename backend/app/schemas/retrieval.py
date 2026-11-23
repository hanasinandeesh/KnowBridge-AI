import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RetrievedChunk(BaseModel):
    """
    Structured representation of a single retrieved document chunk with full provenance.
    """

    chunk_id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier of the document chunk",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Parent document UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440001"],
    )
    document_title: str = Field(
        ...,
        description="Human-readable title of the document",
        examples=["Enterprise Travel & Reimbursement Policy"],
    )
    chunk_text: str = Field(
        ...,
        description="Text content of the retrieved chunk passage",
        examples=["Section 2.1 Meal Per Diem: Employees traveling domestically..."],
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score (bounded between 0.0 and 1.0)",
        examples=[0.825],
    )
    page_number: Optional[int] = Field(
        None,
        ge=1,
        description="1-based physical page number (for PDF); None for DOCX and TXT",
        examples=[3],
    )
    section_title: Optional[str] = Field(
        None,
        description="Immediate section title or heading for this chunk",
        examples=["2.1 Meal Per Diem"],
    )
    document_version: Optional[str] = Field(
        None,
        description="Document version identifier or label",
        examples=["1.0", "v2.0"],
    )
    version_label: Optional[str] = Field(
        None,
        description="Document version identifier or label",
        examples=["1.0", "v2.0"],
    )
    category: Optional[str] = Field(
        None,
        description="Policy category classification (e.g., 'HR', 'Finance')",
        examples=["HR"],
    )
    department: Optional[str] = Field(
        None,
        description="Originating corporate department (e.g., 'Human Resources')",
        examples=["Human Resources"],
    )
    is_current: Optional[bool] = Field(
        None,
        description="True if this chunk belongs to the currently active document revision",
        examples=[True],
    )
    effective_from: Optional[date] = Field(
        None,
        description="Policy start validity date for this version",
    )
    effective_until: Optional[date] = Field(
        None,
        description="Policy sunset/expiration date for this version",
    )
    is_ambiguous: bool = Field(
        default=False,
        description="True if multiple overlapping versions exist for this document on the requested date",
        examples=[False],
    )
    chunk_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured JSONB metadata preserved from the document chunk",
    )

    model_config = ConfigDict(from_attributes=True)


class EvidenceItem(BaseModel):
    """
    Structured evidence citation item prepared for LLM synthesis and citation tracing.
    """

    citation_index: int = Field(
        ...,
        ge=1,
        description="1-based ordinal citation index (e.g. 1 for [1])",
        examples=[1],
    )
    chunk_id: uuid.UUID = Field(
        ...,
        description="Unique UUID identifier of the source document chunk",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Parent document UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440001"],
    )
    document_title: str = Field(
        ...,
        description="Human-readable title of the document",
        examples=["Enterprise Travel & Reimbursement Policy"],
    )
    version_label: Optional[str] = Field(
        None,
        description="Document version identifier or label",
        examples=["1.0", "v2.0"],
    )
    effective_from: Optional[date] = Field(
        None,
        description="Policy start validity date for this version",
    )
    effective_until: Optional[date] = Field(
        None,
        description="Policy sunset/expiration date for this version",
    )
    chunk_text: str = Field(
        ...,
        description="Verbatim text passage of the evidence chunk",
        examples=["Section 2.1 Meal Per Diem: Employees traveling domestically..."],
    )
    similarity_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Cosine similarity score bounded between 0.0 and 1.0",
        examples=[0.825],
    )
    page_number: Optional[int] = Field(
        None,
        ge=1,
        description="1-based physical page number if available (for PDF); None for DOCX/TXT",
        examples=[3],
    )
    section_title: Optional[str] = Field(
        None,
        description="Immediate section title or heading if available",
        examples=["2.1 Meal Per Diem"],
    )
    citation_tag: str = Field(
        ...,
        description="Human-readable citation identifier (e.g., '[Enterprise Travel Policy, p. 3]')",
        examples=["[Enterprise Travel Policy, p. 3]"],
    )

    model_config = ConfigDict(from_attributes=True)


class EvidencePackage(BaseModel):
    """
    Consolidated, deterministic evidence package ready for downstream prompt ingestion.
    """

    query: str = Field(
        ...,
        description="The user question or query",
        examples=["What is the meal allowance per diem?"],
    )
    total_evidence_count: int = Field(
        ...,
        ge=0,
        description="Total number of evidence items in this package",
        examples=[2],
    )
    items: list[EvidenceItem] = Field(
        default_factory=list,
        description="Ranked, deduplicated evidence items",
    )
    formatted_context: str = Field(
        ...,
        description="Formatted text block containing numbered citations and source context for LLM prompt",
    )
    has_conflicts: bool = Field(
        default=False,
        description="True if version ambiguity or conflicting policy versions were detected",
    )
    is_sufficient: bool = Field(
        default=True,
        description="True if evidence is available; False if empty or below threshold",
    )
    applied_limit: int = Field(
        ...,
        ge=1,
        description="Final limit applied to the evidence items",
        examples=[5],
    )

    model_config = ConfigDict(from_attributes=True)


class RetrievalResult(BaseModel):
    """
    Structured result model for semantic retrieval operations.
    """

    query: str = Field(
        ...,
        description="The natural-language question or search query",
        examples=["What is the meal allowance per diem?"],
    )
    total_retrieved: int = Field(
        ...,
        ge=0,
        description="Number of candidate chunks returned",
        examples=[3],
    )
    chunks: list[RetrievedChunk] = Field(
        default_factory=list,
        description="Ranked candidate chunks ordered by descending similarity score",
    )
    similarity_threshold: float = Field(
        ...,
        description="Minimum cosine similarity cutoff applied during vector search",
        examples=[0.65],
    )
    top_k: int = Field(
        ...,
        description="Maximum number of candidate chunks requested",
        examples=[5],
    )
    applied_limit: Optional[int] = Field(
        None,
        description="Configurable result limit applied to final chunks",
        examples=[5],
    )
    target_date: Optional[date] = Field(
        None,
        description="Temporal validity date applied for active policy resolution",
    )
    category_filter: Optional[str] = Field(
        None,
        description="Category filter applied to search results",
    )
    department_filter: Optional[str] = Field(
        None,
        description="Department filter applied to search results",
    )
    version_filter: Optional[str] = Field(
        None,
        description="Specific version filter applied to search results",
    )
    is_current_only: bool = Field(
        default=True,
        description="True if search was restricted strictly to currently active policy revisions",
    )
    has_version_ambiguity: bool = Field(
        default=False,
        description="True if overlapping or ambiguous policy versions were detected for any retrieved document",
    )
    ambiguity_notes: list[str] = Field(
        default_factory=list,
        description="Descriptive notes explaining version ambiguities or overlaps found in candidates",
    )
    evidence_package: Optional[EvidencePackage] = Field(
        None,
        description="Consolidated, deterministic evidence package for LLM synthesis",
    )

    model_config = ConfigDict(from_attributes=True)
