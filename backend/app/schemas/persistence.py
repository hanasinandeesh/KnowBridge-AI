import uuid
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class DocumentPersistenceRequest(BaseModel):
    """
    Optional payload for configuring chunking, embedding, and persistence parameters.
    """

    chunk_size: Optional[int] = Field(
        None,
        gt=0,
        le=10000,
        description="Chunk size in characters (defaults to system settings if omitted)",
    )
    chunk_overlap: Optional[int] = Field(
        None,
        ge=0,
        le=2000,
        description="Chunk overlap in characters (defaults to system settings if omitted)",
    )
    batch_size: Optional[int] = Field(
        None,
        gt=0,
        le=512,
        description="Batch size for generating embeddings (defaults to system settings if omitted)",
    )
    version_label: Optional[str] = Field(
        None,
        description="Explicit document version label (e.g. '1.0', 'v2.0'). If omitted, safely resolved from document metadata.",
    )

    model_config = ConfigDict(from_attributes=True)


class DocumentPersistenceResponse(BaseModel):
    """
    Standard response model returned after successful document chunk and embedding persistence.
    """

    document_id: uuid.UUID = Field(
        ...,
        description="Universal document UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    document_version_id: uuid.UUID = Field(
        ...,
        description="Verified associated document version UUID identifier",
        examples=["660e8400-e29b-41d4-a716-446655440001"],
    )
    version_label: str = Field(
        ...,
        description="Associated version label (e.g. '1.0', 'v2.0')",
        examples=["1.0"],
    )
    persisted_chunk_count: int = Field(
        ...,
        ge=0,
        description="Total number of chunks successfully persisted in document_chunks",
        examples=[14],
    )
    embedding_model: str = Field(
        ...,
        description="Sentence Transformers model identifier used for generation",
        examples=["sentence-transformers/all-MiniLM-L6-v2"],
    )
    embedding_dimension: int = Field(
        default=384,
        description="Dimension size of persisted vectors (strictly 384)",
        examples=[384],
    )
    persistence_status: str = Field(
        ...,
        description="Result status: 'completed' or 'failed'",
        examples=["completed"],
    )
    ingestion_job_id: Optional[uuid.UUID] = Field(
        None,
        description="UUID of the associated ingestion job tracking this operation",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Audit metadata, timing, and execution details",
    )

    model_config = ConfigDict(from_attributes=True)
