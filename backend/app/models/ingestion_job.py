import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, Uuid, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class IngestionJob(Base):
    """
    SQLAlchemy model representing an ingestion tracking job for a document.
    Matches the existing Supabase PostgreSQL 'ingestion_jobs' table schema.
    """

    __tablename__ = "ingestion_jobs"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal ingestion job UUID identifier",
    )
    document_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key referencing the parent document record",
    )
    status = Column(
        Text,
        nullable=False,
        default="pending",
        comment="Current ingestion state: 'pending', 'processing', 'completed', 'failed'",
    )
    error_message = Column(
        Text,
        nullable=True,
        comment="Sanitized failure description if ingestion failed",
    )
    total_pages = Column(
        Integer,
        nullable=True,
        comment="Total document pages processed (PDF only, NULL for DOCX/TXT)",
    )
    total_chunks = Column(
        Integer,
        nullable=True,
        comment="Total chunks generated and persisted",
    )
    started_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when job processing started",
    )
    completed_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when job processing completed or failed",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when ingestion job was registered",
    )

    # Relationships
    document = relationship("Document", back_populates="ingestion_jobs")

    def __repr__(self) -> str:
        return (
            f"<IngestionJob id={self.id} doc_id={self.document_id} "
            f"status='{self.status}' chunks={self.total_chunks}>"
        )
