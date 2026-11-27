"""
Message Persistence Service.
Task 06C — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Provides business logic for creating and retrieving conversation messages
with deterministic chronological sorting, citation persistence, and transactional integrity.
"""

import logging
import math
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import sanitize_error_message
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.message import (
    EvidenceStatusEnum,
    MessageCreate,
    MessageListResponse,
    MessageResponse,
    MessageRole,
)

logger = logging.getLogger("app.services.message_service")


class MessageServiceError(Exception):
    """Base exception for message service failures."""
    pass


class ConversationNotFoundError(MessageServiceError):
    """Raised when parent conversation is missing."""
    pass


class MessageService:
    """Encapsulates database operations and business logic for message persistence."""

    def __init__(self, db: Session):
        self.db = db

    def create_message(
        self,
        conversation_id: uuid.UUID,
        payload: MessageCreate,
    ) -> MessageResponse:
        """
        Creates and stores a new message record linked to an existing conversation thread.
        Updates the parent conversation's updated_at timestamp atomically.

        Raises:
            ConversationNotFoundError: If the specified conversation does not exist.
            MessageServiceError: If database transaction fails.
        """
        try:
            # Verify parent conversation exists
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                logger.warning("Attempted to add message to nonexistent conversation %s", conversation_id)
                raise ConversationNotFoundError(f"Conversation with ID '{conversation_id}' not found.")

            # Serialize structured citations to JSON-compatible dicts if present
            serialized_citations = []
            if payload.citations:
                serialized_citations = [
                    cit.model_dump(mode="json") if hasattr(cit, "model_dump") else cit
                    for cit in payload.citations
                ]

            role_str = payload.role.value if isinstance(payload.role, MessageRole) else str(payload.role)
            evidence_status_str = (
                payload.evidence_status.value
                if isinstance(payload.evidence_status, EvidenceStatusEnum)
                else payload.evidence_status
            )

            msg = Message(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                role=role_str,
                content=payload.content.strip(),
                citations=serialized_citations,
                evidence_status=evidence_status_str,
                trace_id=payload.trace_id,
                feedback_score=None,
            )

            # Atomically update conversation updated_at timestamp
            conv.updated_at = datetime.now(timezone.utc)

            self.db.add(msg)
            self.db.commit()
            self.db.refresh(msg)

            logger.info("Created %s message %s for conversation %s", msg.role, msg.id, conversation_id)
            return MessageResponse(
                id=msg.id,
                conversation_id=msg.conversation_id,
                role=msg.role,
                content=msg.content,
                citations=msg.citations or [],
                evidence_status=msg.evidence_status,
                trace_id=msg.trace_id,
                feedback_score=msg.feedback_score,
                created_at=msg.created_at,
            )
        except ConversationNotFoundError:
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to create message for conversation %s: %s", conversation_id, sanitized)
            raise MessageServiceError(f"Database error creating message: {sanitized}") from exc

    def get_messages(
        self,
        conversation_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> MessageListResponse:
        """
        Retrieves messages for a conversation ordered chronologically (created_at ASC, id ASC).
        Supports deterministic pagination.

        Raises:
            ConversationNotFoundError: If the specified conversation does not exist.
            MessageServiceError: If database query fails.
        """
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        try:
            # Verify parent conversation exists
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                logger.warning("Attempted to retrieve messages for nonexistent conversation %s", conversation_id)
                raise ConversationNotFoundError(f"Conversation with ID '{conversation_id}' not found.")

            total = (
                self.db.scalar(
                    select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
                )
                or 0
            )
            total_pages = math.ceil(total / page_size) if total > 0 else 0

            offset = (page - 1) * page_size
            stmt = (
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .offset(offset)
                .limit(page_size)
            )

            rows = self.db.execute(stmt).scalars().all()

            items = [
                MessageResponse(
                    id=m.id,
                    conversation_id=m.conversation_id,
                    role=m.role,
                    content=m.content,
                    citations=m.citations or [],
                    evidence_status=m.evidence_status,
                    trace_id=m.trace_id,
                    feedback_score=m.feedback_score,
                    created_at=m.created_at,
                )
                for m in rows
            ]

            return MessageListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1 and total_pages > 0,
            )
        except ConversationNotFoundError:
            raise
        except SQLAlchemyError as exc:
            self.db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to retrieve messages for conversation %s: %s", conversation_id, sanitized)
            raise MessageServiceError(f"Database error retrieving messages: {sanitized}") from exc


def get_message_service(db: Session) -> MessageService:
    """Dependency injection provider for MessageService."""
    return MessageService(db=db)
