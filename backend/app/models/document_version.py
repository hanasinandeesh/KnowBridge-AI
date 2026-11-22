import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Text, UniqueConstraint, Uuid, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class DocumentVersion(Base):
    """
    SQLAlchemy model representing a revision/version release of an enterprise document.
    Matches the existing Supabase PostgreSQL 'document_versions' table schema.
    """

    __tablename__ = "document_versions"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal document version UUID identifier",
    )
    document_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        comment="Foreign key to the parent document record",
    )
    version_label = Column(
        Text,
        nullable=False,
        comment="Human-readable or semantic version label (e.g. '1.0', 'v2.0')",
    )
    effective_from = Column(
        Date,
        nullable=True,
        comment="Policy validity start date",
    )
    effective_until = Column(
        Date,
        nullable=True,
        comment="Policy sunset/expiration date",
    )
    is_current = Column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if this version is the currently active revision",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when version record was created",
    )

    __table_args__ = (
        UniqueConstraint("document_id", "version_label", name="document_versions_document_id_version_label_key"),
    )

    # Relationships
    document = relationship("Document", back_populates="versions")
    chunks = relationship(
        "DocumentChunk",
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )

    def __repr__(self) -> str:
        return (
            f"<DocumentVersion id={self.id} doc_id={self.document_id} "
            f"label='{self.version_label}' is_current={self.is_current}>"
        )
