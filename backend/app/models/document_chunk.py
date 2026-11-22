import uuid
from datetime import datetime
from typing import Any, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, Text, UniqueConstraint, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocumentChunk(Base):
    """
    SQLAlchemy model representing a structure-aware document chunk and its dense vector embedding.
    Matches the existing Supabase PostgreSQL 'document_chunks' table schema.
    """

    __tablename__ = "document_chunks"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal document chunk UUID identifier",
    )
    document_version_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("document_versions.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key referencing the associated document version",
    )
    chunk_index = Column(
        Integer,
        nullable=False,
        comment="Zero-based contiguous sequential chunk index within the document version",
    )
    page_number = Column(
        Integer,
        nullable=True,
        comment="1-based physical PDF page number; strictly NULL for DOCX and TXT",
    )
    section_title = Column(
        Text,
        nullable=True,
        comment="Immediate section heading or title for this chunk",
    )
    chunk_text = Column(
        Text,
        nullable=False,
        comment="Complete plain text content of the chunk",
    )
    embedding = Column(
        Vector(384),
        nullable=True,
        comment="384-dimensional dense numerical vector embedding",
    )
    token_count = Column(
        Integer,
        nullable=True,
        comment="Calculated or approximate token count of chunk_text",
    )
    embedding_model = Column(
        Text,
        nullable=True,
        comment="HuggingFace model identifier (e.g. 'sentence-transformers/all-MiniLM-L6-v2')",
    )
    metadata_ = Column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
        comment="JSONB structured metadata (provenance, section hierarchy, unit indices)",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when chunk record was created",
    )

    __table_args__ = (
        UniqueConstraint(
            "document_version_id",
            "chunk_index",
            name="document_chunks_document_version_id_chunk_index_key",
        ),
    )

    # Relationships
    version = relationship("DocumentVersion", back_populates="chunks")

    def __repr__(self) -> str:
        return (
            f"<DocumentChunk id={self.id} version_id={self.document_version_id} "
            f"index={self.chunk_index} page={self.page_number}>"
        )
