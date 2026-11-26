"""
Conversation Management Service.
Task 06B — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Provides business logic for creating, retrieving, listing, updating,
and deleting conversational sessions with transactional integrity.
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
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)

logger = logging.getLogger("app.services.conversation_service")


class ConversationServiceError(Exception):
    """Base exception for conversation service failures."""
    pass


class ConversationService:
    """Encapsulates database operations and business logic for conversations."""

    def __init__(self, db: Session):
        self.db = db

    def create_conversation(
        self,
        payload: Optional[ConversationCreate] = None,
    ) -> ConversationResponse:
        """
        Creates a new conversation thread record.

        - Generates a UUID v4 identifier.
        - Applies title or falls back to 'New Conversation'.
        - Commits transaction atomically.
        """
        raw_title = payload.title if payload and payload.title else None
        title = raw_title.strip() if raw_title and raw_title.strip() else "New Conversation"

        conv = Conversation(
            id=uuid.uuid4(),
            title=title,
        )

        try:
            self.db.add(conv)
            self.db.commit()
            self.db.refresh(conv)
            logger.info("Created conversation %s with title '%s'", conv.id, conv.title)
            return ConversationResponse(
                id=conv.id,
                title=conv.title,
                message_count=0,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to create conversation: %s", sanitized)
            raise ConversationServiceError(f"Database error creating conversation: {sanitized}") from exc

    def get_conversation(self, conversation_id: uuid.UUID) -> Optional[ConversationResponse]:
        """
        Retrieves a conversation thread by its UUID, including its message count.
        Returns None if no matching conversation exists.
        """
        try:
            msg_count_subquery = (
                select(func.count(Message.id))
                .where(Message.conversation_id == Conversation.id)
                .scalar_subquery()
            )

            stmt = (
                select(Conversation, func.coalesce(msg_count_subquery, 0).label("message_count"))
                .where(Conversation.id == conversation_id)
            )

            row = self.db.execute(stmt).first()
            if not row:
                return None

            conv, msg_count = row
            return ConversationResponse(
                id=conv.id,
                title=conv.title,
                message_count=msg_count,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        except SQLAlchemyError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to retrieve conversation %s: %s", conversation_id, sanitized)
            raise ConversationServiceError(f"Database error retrieving conversation: {sanitized}") from exc

    def list_conversations(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> ConversationListResponse:
        """
        Retrieves a paginated list of conversations ordered deterministically by
        updated_at DESC, then id DESC.
        """
        page = max(1, page)
        page_size = min(max(1, page_size), 100)

        try:
            total = self.db.scalar(select(func.count(Conversation.id))) or 0
            total_pages = math.ceil(total / page_size) if total > 0 else 0

            msg_count_subquery = (
                select(func.count(Message.id))
                .where(Message.conversation_id == Conversation.id)
                .scalar_subquery()
            )

            offset = (page - 1) * page_size
            stmt = (
                select(Conversation, func.coalesce(msg_count_subquery, 0).label("message_count"))
                .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
                .offset(offset)
                .limit(page_size)
            )

            rows = self.db.execute(stmt).all()

            items = [
                ConversationResponse(
                    id=conv.id,
                    title=conv.title,
                    message_count=msg_count,
                    created_at=conv.created_at,
                    updated_at=conv.updated_at,
                )
                for conv, msg_count in rows
            ]

            return ConversationListResponse(
                items=items,
                total=total,
                page=page,
                page_size=page_size,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_prev=page > 1 and total_pages > 0,
            )
        except SQLAlchemyError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to list conversations: %s", sanitized)
            raise ConversationServiceError(f"Database error listing conversations: {sanitized}") from exc

    def update_conversation(
        self,
        conversation_id: uuid.UUID,
        payload: ConversationUpdate,
    ) -> Optional[ConversationResponse]:
        """
        Updates supported fields of a conversation (initially title) and refreshes timestamps.
        Returns None if conversation does not exist.
        """
        clean_title = payload.title.strip()
        if not clean_title:
            raise ValueError("Conversation title cannot be empty or whitespace only.")

        try:
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return None

            conv.title = clean_title
            conv.updated_at = datetime.now(timezone.utc)

            self.db.commit()
            self.db.refresh(conv)

            # Retrieve current message count
            msg_count = (
                self.db.scalar(
                    select(func.count(Message.id)).where(Message.conversation_id == conv.id)
                )
                or 0
            )

            logger.info("Updated conversation %s title to '%s'", conv.id, conv.title)
            return ConversationResponse(
                id=conv.id,
                title=conv.title,
                message_count=msg_count,
                created_at=conv.created_at,
                updated_at=conv.updated_at,
            )
        except SQLAlchemyError as exc:
            self.db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to update conversation %s: %s", conversation_id, sanitized)
            raise ConversationServiceError(f"Database error updating conversation: {sanitized}") from exc

    def delete_conversation(self, conversation_id: uuid.UUID) -> bool:
        """
        Deletes a conversation by its UUID.
        Database cascading automatically removes child messages (ON DELETE CASCADE)
        and sets source_conversation_id to NULL on user_memories (ON DELETE SET NULL).

        Returns True if deleted, False if nonexistent.
        """
        try:
            conv = self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return False

            self.db.delete(conv)
            self.db.commit()
            logger.info("Deleted conversation %s", conversation_id)
            return True
        except SQLAlchemyError as exc:
            self.db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to delete conversation %s: %s", conversation_id, sanitized)
            raise ConversationServiceError(f"Database error deleting conversation: {sanitized}") from exc
