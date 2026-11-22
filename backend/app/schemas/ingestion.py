import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class IngestionJobResponse(BaseModel):
    """
    Structured response model representing an ingestion job tracking record.
    Provides complete state visibility for background ingestion orchestration.
    """

    job_id: uuid.UUID = Field(
        ...,
        description="Universal ingestion job UUID identifier",
        examples=["550e8400-e29b-41d4-a716-446655440000"],
    )
    document_id: uuid.UUID = Field(
        ...,
        description="UUID of the associated parent document record",
        examples=["660e8400-e29b-41d4-a716-446655440001"],
    )
    status: str = Field(
        ...,
        description="Current state of ingestion: 'pending', 'processing', 'completed', or 'failed'",
        examples=["completed"],
    )
    total_pages: Optional[int] = Field(
        None,
        description="Total physical pages processed (PDF only, NULL for DOCX/TXT)",
        examples=[4],
    )
    total_chunks: Optional[int] = Field(
        None,
        description="Total chunks generated and persisted into document_chunks table",
        examples=[14],
    )
    error_message: Optional[str] = Field(
        None,
        description="Sanitized failure description if ingestion failed, with all secrets redacted",
    )
    started_at: Optional[datetime] = Field(
        None,
        description="Timestamp when job processing started",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="Timestamp when job processing completed or failed",
    )
    created_at: datetime = Field(
        ...,
        description="Timestamp when ingestion job was registered",
    )

    model_config = ConfigDict(from_attributes=True)
