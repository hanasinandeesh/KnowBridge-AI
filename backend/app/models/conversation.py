import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, String, Uuid, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class Conversation(Base):
    """
    SQLAlchemy model representing a conversational session and chat thread.
    Matches the existing Supabase PostgreSQL 'conversations' table schema exactly.
    """

    __tablename__ = "conversations"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal conversation UUID identifier (used as LangGraph thread_id)",
    )
    title = Column(
        String(255),
        nullable=False,
        default="New Conversation",
        comment="Human-readable conversation title or summary",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when conversation was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Timestamp when conversation was last updated",
    )

    # Relationship to messages with database cascade delete awareness
    messages = relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.created_at",
    )

    # Relationship to user memories with SET NULL on conversation deletion
    user_memories = relationship(
        "UserMemory",
        back_populates="conversation",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Conversation id={self.id} title='{self.title}'>"
