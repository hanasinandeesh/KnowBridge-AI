import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, SmallInteger, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Message(Base):
    """
    SQLAlchemy model representing an interaction turn within a conversation.
    Matches the existing Supabase PostgreSQL 'messages' table schema exactly.
    """

    __tablename__ = "messages"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal message UUID identifier",
    )
    conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Foreign key to the parent conversation thread",
    )
    role = Column(
        String(20),
        nullable=False,
        comment="Interaction role: 'user', 'assistant', or 'system'",
    )
    content = Column(
        Text,
        nullable=False,
        comment="Text content of the message prompt or generated response",
    )
    citations = Column(
        JSONB,
        nullable=True,
        default=list,
        comment="Structured citation list: [{doc_title, page, snippet}]",
    )
    evidence_status = Column(
        String(50),
        nullable=True,
        comment="Evidence assessment state: 'SUPPORTED', 'INSUFFICIENT', 'CONFLICTING'",
    )
    trace_id = Column(
        String(100),
        nullable=True,
        comment="Observability trace ID linking feedback to Langfuse",
    )
    feedback_score = Column(
        SmallInteger,
        nullable=True,
        comment="User feedback: -1 (negative), 0 (neutral), 1 (positive)",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when message record was created",
    )

    # Relationship back to parent conversation
    conversation = relationship("Conversation", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message id={self.id} conv_id={self.conversation_id} role='{self.role}'>"
