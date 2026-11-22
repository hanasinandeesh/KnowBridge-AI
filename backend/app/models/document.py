import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Text, Uuid, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Document(Base):
    """
    SQLAlchemy model representing the core enterprise document record.
    Matches the existing Supabase PostgreSQL 'documents' table schema exactly.
    """

    __tablename__ = "documents"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal document UUID identifier",
    )
    title = Column(
        Text,
        nullable=False,
        comment="Human-readable document title",
    )
    original_filename = Column(
        Text,
        nullable=False,
        comment="Sanitized original document filename at upload",
    )
    file_type = Column(
        Text,
        nullable=False,
        comment="Document format type: 'pdf', 'docx', or 'txt'",
    )
    storage_path = Column(
        Text,
        nullable=False,
        unique=True,
        comment="Storage reference path/key for the document binary",
    )
    category = Column(
        Text,
        nullable=True,
        default="general",
        comment="Policy category classification (e.g., 'HR', 'Finance', 'IT')",
    )
    department = Column(
        Text,
        nullable=True,
        comment="Originating corporate department",
    )
    description = Column(
        Text,
        nullable=True,
        comment="Optional document summary or scope description",
    )
    status = Column(
        Text,
        nullable=False,
        default="uploaded",
        comment="Current processing status: 'uploaded', 'processing', 'completed', 'failed'",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when document record was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Timestamp when document record was last updated",
    )

    # Relationships
    versions = relationship(
        "DocumentVersion",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(DocumentVersion.created_at)",
    )
    ingestion_jobs = relationship(
        "IngestionJob",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(IngestionJob.created_at)",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename='{self.original_filename}' file_type='{self.file_type}' status='{self.status}'>"
