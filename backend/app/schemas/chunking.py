import uuid
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentChunk(BaseModel):
    """
    Structured document chunk model representing a deterministic, structure-aware segment
    of extracted document text with full provenance, section context, and source unit attribution.
    """

    chunk_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Unique identifier for this chunk",
    )
    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Database document UUID identifier if chunking was performed against a stored document",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    chunk_index: int = Field(
        ...,
        ge=0,
        description="Zero-based contiguous sequential chunk index within the document",
        examples=[0],
    )
    chunk_text: str = Field(
        ...,
        description="Text content of this chunk with preserved boundaries and structure",
        examples=["Section 1.0 Travel Authorization..."],
    )
    character_count: int = Field(
        ...,
        ge=0,
        description="Exact character count of chunk_text",
        examples=[942],
    )
    token_count: int = Field(
        ...,
        ge=0,
        description="Approximate token count of chunk_text (deterministic heuristic)",
        examples=[235],
    )
    page_number: Optional[int] = Field(
        None,
        ge=1,
        description="1-based physical PDF page number. Strictly None for DOCX and TXT documents.",
        examples=[1],
    )
    section_title: Optional[str] = Field(
        None,
        description="Immediate section title or heading under which this chunk falls, if available",
        examples=["1.1 Travel Authorization"],
    )
    section_hierarchy: list[str] = Field(
        default_factory=list,
        description="Ordered hierarchical ancestry of headings leading to this chunk (e.g. ['1.0 Policy', '1.1 Scope'])",
        examples=[["1.0 Travel and Expense Policy", "1.1 Travel Authorization"]],
    )
    source_unit_indices: list[int] = Field(
        default_factory=list,
        description="Zero-based indices of original ContentUnits (pages, paragraphs, tables) comprising this chunk",
        examples=[[0, 1]],
    )
    source_unit_type: str = Field(
        ...,
        description="Source content type: 'page' (PDF), 'paragraph', 'table', 'heading', 'text_block', or 'composite'",
        examples=["paragraph"],
    )
    filename: str = Field(
        ...,
        description="Original sanitized document filename",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
    )
    file_type: str = Field(
        ...,
        description="Document format: 'pdf', 'docx', or 'txt'",
        examples=["pdf"],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extended chunk metadata (overlap character counts, table structure, row spans, etc.)",
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkingResult(BaseModel):
    """
    Response model for document chunking operation containing all generated chunks
    and summary metadata.
    """

    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Database document UUID identifier if chunking was performed against a stored document",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    filename: str = Field(
        ...,
        description="Original document filename",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
    )
    file_type: str = Field(
        ...,
        description="Normalized document format ('pdf', 'docx', 'txt')",
        examples=["pdf"],
    )
    total_chunks: int = Field(
        ...,
        ge=0,
        description="Total number of chunks produced",
        examples=[12],
    )
    chunk_size: int = Field(
        ...,
        gt=0,
        description="Configured maximum chunk size in characters",
        examples=[1000],
    )
    chunk_overlap: int = Field(
        ...,
        ge=0,
        description="Configured overlap in characters",
        examples=[150],
    )
    chunks: list[DocumentChunk] = Field(
        default_factory=list,
        description="Ordered list of generated document chunks",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunking execution statistics and audit metadata",
    )

    model_config = ConfigDict(from_attributes=True)
