"""
Persistent User Memory API Routes.
Task 06E — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Provides REST endpoints to:
1. GET /api/v1/memories: Retrieve unexpired user memories for a session namespace.
2. GET /api/v1/memories/context: Retrieve structured active context profile for RAG pipelines.
3. POST /api/v1/memories: Store or upsert a verified user memory record.
4. DELETE /api/v1/memories/{memory_id}: Permanently delete a single memory record.
5. DELETE /api/v1/memories/session/{session_key}: Purge all memories for a session namespace.
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
from app.schemas.memory import (
    ActiveMemoryContext,
    MemoryCreate,
    MemoryListResponse,
    MemoryResponse,
)
from app.services.memory_service import (
    MemoryDatabaseError,
    MemoryService,
    get_memory_service,
)

logger = logging.getLogger("app.api.memories")
router = APIRouter(tags=["memories"])


@router.get(
    "",
    response_model=MemoryListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Active User Memories",
    description="Retrieves active (unexpired) user memories for a given session namespace, ordered by confidence and recency.",
)
def list_memories(
    session_key: str = Query(
        "default",
        max_length=100,
        description="Session or user namespace identifier",
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Maximum number of memory items to return",
    ),
    include_expired: bool = Query(
        False,
        description="Whether to include expired memory records",
    ),
    db: Session = Depends(get_db),
) -> MemoryListResponse:
    try:
        service = get_memory_service(db=db)
        items = service.get_active_memories(
            session_key=session_key,
            limit=limit,
            include_expired=include_expired,
        )
        return MemoryListResponse(
            items=items,
            total=len(items),
            session_key=session_key,
        )
    except MemoryDatabaseError as exc:
        logger.error("Failed to list memories: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve memory records from database.",
        ) from exc


@router.get(
    "/context",
    response_model=ActiveMemoryContext,
    status_code=status.HTTP_200_OK,
    summary="Get Active Memory Context",
    description="Returns structured active profile and constraint context for a session namespace.",
)
def get_memory_context(
    session_key: str = Query(
        "default",
        max_length=100,
        description="Session or user namespace identifier",
    ),
    db: Session = Depends(get_db),
) -> ActiveMemoryContext:
    try:
        service = get_memory_service(db=db)
        return service.get_active_memory_context(session_key=session_key)
    except MemoryDatabaseError as exc:
        logger.error("Failed to get memory context: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to compile memory context from database.",
        ) from exc


@router.post(
    "",
    response_model=MemoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or Upsert Memory",
    description="Persists a verified factual user memory. Automatically updates or supersedes existing facts.",
)
def create_memory(
    payload: MemoryCreate,
    db: Session = Depends(get_db),
) -> MemoryResponse:
    try:
        service = get_memory_service(db=db)
        return service.store_memory(payload=payload)
    except MemoryDatabaseError as exc:
        logger.error("Failed to store memory: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store memory record in database.",
        ) from exc


@router.delete(
    "/{memory_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Single Memory",
    description="Permanently deletes a specific memory record by its UUID.",
)
def delete_single_memory(
    memory_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> Response:
    try:
        service = get_memory_service(db=db)
        deleted = service.delete_memory(memory_id=memory_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Memory record '{memory_id}' not found.",
            )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except MemoryDatabaseError as exc:
        logger.error("Failed to delete memory %s: %s", memory_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete memory record from database.",
        ) from exc


@router.delete(
    "/session/{session_key}",
    status_code=status.HTTP_200_OK,
    summary="Purge Session Memories",
    description="Deletes all stored memories for a given session namespace.",
)
def clear_session(
    session_key: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        service = get_memory_service(db=db)
        deleted_count = service.clear_session_memories(session_key=session_key)
        return {
            "session_key": session_key,
            "deleted_count": deleted_count,
        }
    except MemoryDatabaseError as exc:
        logger.error("Failed to clear session %s: %s", session_key, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to clear session memories from database.",
        ) from exc
