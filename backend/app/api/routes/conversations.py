"""
Conversation & Message Management API Routes.
Tasks 06B & 06C — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Provides REST endpoints to:
1. POST /api/v1/conversations: Create a new conversation thread.
2. GET /api/v1/conversations: List conversations with deterministic pagination and message count.
3. GET /api/v1/conversations/{conversation_id}: Retrieve single conversation details.
4. PATCH /api/v1/conversations/{conversation_id}: Update conversation title.
5. DELETE /api/v1/conversations/{conversation_id}: Permanently delete conversation and cascade.
6. POST /api/v1/conversations/{conversation_id}/messages: Persist user or assistant message.
7. GET /api/v1/conversations/{conversation_id}/messages: Retrieve chronological messages with pagination.
"""

import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.conversation import (
    ConversationCreate,
    ConversationListResponse,
    ConversationResponse,
    ConversationUpdate,
)
from app.schemas.message import (
    MessageCreate,
    MessageListResponse,
    MessageResponse,
)
from app.services.conversation_service import (
    ConversationService,
    ConversationServiceError,
)
from app.services.message_service import (
    ConversationNotFoundError,
    MessageService,
    MessageServiceError,
)

logger = logging.getLogger("app.api.conversations")
router = APIRouter(tags=["conversations"])


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Conversation",
    description="Creates a new conversation thread with an optional title. Defaults to 'New Conversation'.",
)
def create_conversation(
    payload: Optional[ConversationCreate] = None,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Creates a new conversation session record."""
    service = ConversationService(db)
    try:
        return service.create_conversation(payload)
    except ConversationServiceError as exc:
        logger.error("Failed to create conversation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create conversation due to an internal database error.",
        ) from exc


@router.get(
    "",
    response_model=ConversationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Conversations",
    description="Lists conversations ordered deterministically by updated_at DESC with pagination and message counts.",
)
def list_conversations(
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page (1 to 100)"),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    """Retrieves a paginated list of conversations."""
    service = ConversationService(db)
    try:
        return service.list_conversations(page=page, page_size=page_size)
    except ConversationServiceError as exc:
        logger.error("Failed to list conversations: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversations due to an internal database error.",
        ) from exc


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Conversation",
    description="Retrieves metadata, timestamps, and message count for a specific conversation UUID.",
)
def get_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Retrieves single conversation by UUID."""
    service = ConversationService(db)
    try:
        conv = service.get_conversation(conversation_id)
    except ConversationServiceError as exc:
        logger.error("Failed to retrieve conversation %s: %s", conversation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve conversation due to an internal database error.",
        ) from exc

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found.",
        )
    return conv


@router.patch(
    "/{conversation_id}",
    response_model=ConversationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Conversation",
    description="Updates supported conversation fields (title) and refreshes updated_at timestamp.",
)
def update_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    """Updates a conversation title."""
    service = ConversationService(db)
    try:
        conv = service.update_conversation(conversation_id, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ConversationServiceError as exc:
        logger.error("Failed to update conversation %s: %s", conversation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update conversation due to an internal database error.",
        ) from exc

    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found.",
        )
    return conv


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Conversation",
    description="Permanently deletes a conversation and cascades to its messages.",
)
def delete_conversation(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    """Deletes a conversation by UUID."""
    service = ConversationService(db)
    try:
        deleted = service.delete_conversation(conversation_id)
    except ConversationServiceError as exc:
        logger.error("Failed to delete conversation %s: %s", conversation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete conversation due to an internal database error.",
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Message Persistence Endpoints (Task 06C)
# ---------------------------------------------------------------------------


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Message",
    description="Persists a new user or assistant message linked to the specified conversation.",
)
def create_message(
    conversation_id: uuid.UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
) -> MessageResponse:
    """Creates and stores a message in a conversation thread."""
    service = MessageService(db)
    try:
        return service.create_message(conversation_id, payload)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except MessageServiceError as exc:
        logger.error("Failed to create message for conversation %s: %s", conversation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist message due to an internal database error.",
        ) from exc


@router.get(
    "/{conversation_id}/messages",
    response_model=MessageListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Messages",
    description="Retrieves a chronologically ordered paginated list of messages for the specified conversation.",
)
def list_messages(
    conversation_id: uuid.UUID,
    page: int = Query(default=1, ge=1, description="1-based page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Messages per page (1 to 100)"),
    db: Session = Depends(get_db),
) -> MessageListResponse:
    """Retrieves paginated chronological messages for a conversation."""
    service = MessageService(db)
    try:
        return service.get_messages(conversation_id, page=page, page_size=page_size)
    except ConversationNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except MessageServiceError as exc:
        logger.error("Failed to list messages for conversation %s: %s", conversation_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve messages due to an internal database error.",
        ) from exc
