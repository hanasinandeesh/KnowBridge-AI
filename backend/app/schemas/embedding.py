import uuid
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class ChunkEmbedding(BaseModel):
    """
    Structured embedding representation of an individual document chunk.
    Maintains full provenance, source metadata, and the 384-dimensional vector.
    """

    chunk_id: Optional[uuid.UUID] = Field(
        None,
        description="Unique identifier for the chunk",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Database document UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    filename: Optional[str] = Field(
        None,
        description="Original document filename",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
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
    section_title: Optional[str] = Field(
        None,
        description="Immediate section title or heading under which this chunk falls",
        examples=["1.1 Travel Authorization"],
    )
    page_number: Optional[int] = Field(
        None,
        ge=1,
        description="1-based physical PDF page number. Strictly None for DOCX and TXT documents.",
        examples=[1],
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Existing source metadata and extended chunk attributes",
    )
    embedding: list[float] = Field(
        ...,
        description="384-dimensional dense numerical vector representation",
    )
    embedding_model: str = Field(
        ...,
        description="Hugging Face model identifier used to generate this embedding",
        examples=["sentence-transformers/all-MiniLM-L6-v2"],
    )
    dimension: int = Field(
        default=384,
        description="Dimension count of the embedding vector (strictly 384)",
        examples=[384],
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentEmbeddingResult(BaseModel):
    """
    Response model for document embedding operations containing all generated chunk embeddings
    and summary metadata.
    """

    document_id: Optional[uuid.UUID] = Field(
        None,
        description="Database document UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    filename: Optional[str] = Field(
        None,
        description="Original document filename",
        examples=["HR-TRV-001_Travel_Reimbursement_v1.0.pdf"],
    )
    total_chunks: int = Field(
        ...,
        ge=0,
        description="Total number of chunks successfully embedded",
        examples=[12],
    )
    embedding_model: str = Field(
        ...,
        description="Sentence Transformers model identifier used for generation",
        examples=["sentence-transformers/all-MiniLM-L6-v2"],
    )
    embedding_dimension: int = Field(
        default=384,
        description="Dimension size of returned vectors",
        examples=[384],
    )
    embeddings: list[ChunkEmbedding] = Field(
        default_factory=list,
        description="Ordered list of structured chunk embeddings preserving original chunk order",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Embedding execution statistics, batching details, and audit metadata",
    )

    model_config = ConfigDict(from_attributes=True)


class QueryEmbedding(BaseModel):
    """
    Structured representation of a natural-language query embedding.
    Ensures mathematical and dimensional alignment with stored document chunks.
    """

    query: str = Field(
        ...,
        description="Original natural-language search query or question",
        examples=["What is the maximum domestic per diem allowance?"],
    )
    embedding: list[float] = Field(
        ...,
        description="384-dimensional dense numerical vector representation",
    )
    embedding_model: str = Field(
        ...,
        description="Sentence Transformers model identifier used for generation",
        examples=["sentence-transformers/all-MiniLM-L6-v2"],
    )
    dimension: int = Field(
        default=384,
        description="Dimension count of the embedding vector (strictly 384)",
        examples=[384],
    )
    is_normalized: bool = Field(
        default=True,
        description="Whether the embedding is unit L2 normalized",
        examples=[True],
    )

    model_config = ConfigDict(from_attributes=True)

