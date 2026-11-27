"""
Conversational Chat & Feedback API Routes.
Task 06F — KnowBridge AI Policy-Aware Enterprise RAG Platform.

Provides REST endpoints to:
1. POST /api/v1/chat: Execute end-to-end conversational RAG with thread management,
   context resolution, active memory injection, and message persistence.
2. POST /api/v1/feedback: Record employee ratings (+1 / -1) on assistant answers.
"""

from datetime import datetime, timezone
import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import get_db, sanitize_error_message
from app.graph.workflow import get_rag_orchestrator
from app.models.message import Message
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    FeedbackResponse,
)

logger = logging.getLogger("app.api.chat")
router = APIRouter(tags=["chat"])
feedback_router = APIRouter(tags=["feedback"])


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Conversational Policy Chat",
    description=(
        "Executes policy RAG for an employee question. Resolves follow-ups against "
        "conversation history, retrieves relevant enterprise policy evidence, "
        "incorporates active user memories, enforces citations, and persists the interaction."
    ),
)
def chat_endpoint(
    request: ChatRequest,
    db: Session = Depends(get_db),
) -> ChatResponse:
    try:
        orchestrator = get_rag_orchestrator(db=db)
        return orchestrator.chat(request=request, db=db)
    except Exception as exc:
        sanitized = sanitize_error_message(str(exc))
        logger.error("Chat endpoint execution failed: %s", sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the conversation: {sanitized}",
        ) from exc


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Answer Feedback",
    description="Submits a thumbs up (+1) or thumbs down (-1) rating on an assistant answer message.",
)
@feedback_router.post(
    "",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit Answer Feedback",
    description="Submits a thumbs up (+1) or thumbs down (-1) rating on an assistant answer message.",
)
def submit_feedback(
    payload: FeedbackRequest,
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    try:
        stmt = select(Message).where(Message.id == payload.message_id)
        message = db.execute(stmt).scalars().first()
        if not message:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Message with ID '{payload.message_id}' not found.",
            )

        message.feedback_score = payload.feedback_score
        db.commit()
        db.refresh(message)

        logger.info(
            "Recorded feedback score %d for message %s",
            payload.feedback_score,
            payload.message_id,
        )

        return FeedbackResponse(
            message_id=message.id,
            feedback_score=message.feedback_score,
            updated_at=datetime.now(timezone.utc),
        )
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        sanitized = sanitize_error_message(str(exc))
        logger.error("Failed to record feedback for message %s: %s", payload.message_id, sanitized)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record user feedback.",
        ) from exc
