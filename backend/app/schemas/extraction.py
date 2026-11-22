import uuid
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ContentUnit(BaseModel):
    """
    Represents a discrete page (PDF) or logical content unit (DOCX/TXT).
    Preserves document structure, ordering, and provenance for downstream chunking and citation generation.
    """

    unit_index: int = Field(
        ...,
        description="Zero-based sequence index of this unit in document order",
        examples=[0],
    )
    unit_type: str = Field(
        ...,
        description="Type of content unit: 'page' (PDF), 'paragraph', 'heading', 'table' (DOCX), or 'text_block' (TXT)",
        examples=["page"],
    )
    page_number: Optional[int] = Field(
        None,
        description="1-based physical PDF page number. Strictly None for DOCX and TXT (no fabricated pagination).",
        examples=[1],
    )
    section_title: Optional[str] = Field(
        None,
        description="Detected section, title, or heading under which this unit falls, if available",
        examples=["Section 1.0: Scope and Objectives"],
    )
    text: str = Field(
        ...,
        description="Raw text content extracted from this page or logical content unit",
        examples=["KnowBridge AI Policy Document..."],
    )
    character_count: int = Field(
        ...,
        description="Number of characters in this content unit",
        examples=[1250],
    )
    is_empty: bool = Field(
        False,
        description="True if the unit contains no extractable or readable text (e.g. whitespace-only or scanned image)",
        examples=[False],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Unit-level provenance and parsing details (e.g. heading_level, table_dimensions, rows)",
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentExtractionResult(BaseModel):
    """
    Standardized structured response model containing extracted document content,
    structural units, and provenance metadata across all supported formats (PDF, DOCX, TXT).
    """

    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Database document UUID identifier if extraction was performed against a stored document",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    filename: str = Field(
        ...,
        description="Original sanitized document filename",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
    )
    file_type: str = Field(
        ...,
        description="Normalized document format: 'pdf', 'docx', or 'txt'",
        examples=["pdf"],
    )
    extraction_status: str = Field(
        ...,
        description="Result status: 'completed', 'empty_content', 'failed', or 'unsupported'",
        examples=["completed"],
    )
    total_pages: Optional[int] = Field(
        None,
        description="Total physical pages (PDF only). Strictly None for DOCX and TXT documents.",
        examples=[4],
    )
    total_characters: int = Field(
        ...,
        description="Total character count across all extracted text",
        examples=[11551],
    )
    extracted_text: str = Field(
        ...,
        description="Complete document text with preserved paragraph, table, and page boundary delimiters",
    )
    pages: list[ContentUnit] = Field(
        default_factory=list,
        description="Ordered list of page units (PDF) or logical content units (DOCX, TXT)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extraction-level provenance and audit metadata (parser library, version, warnings)",
    )

    model_config = ConfigDict(from_attributes=True)
