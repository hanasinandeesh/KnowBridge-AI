"""
SQLAlchemy model for persistent user memory.
Task 06E — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Matches the Supabase PostgreSQL 'user_memories' table schema exactly.
Stores persistent extracted employee context (department, role, location, constraints)
across conversation sessions.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserMemory(Base):
    """
    SQLAlchemy model representing a persistent extracted memory or user profile fact.
    Survives across conversation sessions and provides cross-session context.
    """

    __tablename__ = "user_memories"

    id = Column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
        comment="Universal memory UUID identifier",
    )
    session_key = Column(
        String(100),
        nullable=False,
        default="default",
        index=True,
        comment="Session or user scope identifier ('default' in single-workspace MVP)",
    )
    memory_key = Column(
        String(100),
        nullable=False,
        index=True,
        comment="Structured identifier for the fact (e.g., 'department', 'work_location')",
    )
    memory_value = Column(
        Text,
        nullable=False,
        comment="Extracted value for the fact (e.g., 'Engineering', 'London')",
    )
    memory_text = Column(
        Text,
        nullable=False,
        comment="Natural-language description of the memory fact",
    )
    memory_type = Column(
        String(50),
        nullable=False,
        default="profile",
        index=True,
        comment="Category: 'department', 'role', 'location', 'preference', 'constraint'",
    )
    source_conversation_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Originating conversation thread UUID (ON DELETE SET NULL)",
    )
    confidence_score = Column(
        Float,
        nullable=False,
        default=1.0,
        comment="Confidence score from 0.0 to 1.0",
    )
    metadata_json = Column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        comment="Structured metadata (audit history, previous values, source turns)",
    )
    expires_at = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
        comment="Optional expiration timestamp for temporary assignments/constraints",
    )
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        comment="Timestamp when memory was extracted and created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        comment="Timestamp when memory was last modified or reaffirmed",
    )

    # Optional relationship back to originating conversation
    conversation = relationship(
        "Conversation",
        back_populates="user_memories",
        foreign_keys=[source_conversation_id],
    )

    def __repr__(self) -> str:
        return f"<UserMemory id={self.id} key='{self.memory_key}' value='{self.memory_value}' session='{self.session_key}'>"
