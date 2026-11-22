"""
Ingestion Job Status and Orchestration Routes.
Task 003G – KnowBridge AI Enterprise RAG Knowledge Platform.

Provides REST endpoints to:
1. Poll ingestion job status by job_id.
2. Poll the latest ingestion job status for a given document_id.
3. Asynchronously trigger end-to-end ingestion processing for a document.
"""

import logging
import uuid
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, sanitize_error_message
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.schemas.ingestion import IngestionJobResponse
from app.services.ingestion_service import (
    IngestionService,
    get_ingestion_service,
)

logger = logging.getLogger("app.api.ingestion")
router = APIRouter(tags=["ingestion"])


@router.get(
    "/{job_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Ingestion Job Status",
    description=(
        "Retrieves the current state, progress metrics (total pages, total chunks), "
        "timestamps, and sanitized failure reasons of a specific ingestion job."
    ),
)
def get_ingestion_job(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    """
    Polls an ingestion job by UUID:
    - Returns job status ('pending', 'processing', 'completed', 'failed').
    - Returns total_pages and total_chunks when available.
    - If failed, returns sanitized error_message with all secrets redacted.
    """
    logger.info("Polling ingestion job status for job_id: %s", job_id)
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        logger.warning("Ingestion job %s not found.", job_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ingestion job with ID '{job_id}' not found.",
        )

    return IngestionJobResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        total_pages=job.total_pages,
        total_chunks=job.total_chunks,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


@router.get(
    "/document/{document_id}",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Latest Ingestion Job for Document",
    description=(
        "Retrieves the most recent ingestion job tracking record for the specified document."
    ),
)
def get_latest_job_for_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> IngestionJobResponse:
    """
    Polls the latest ingestion job for a given document UUID:
    - Verifies document exists.
    - Returns most recent IngestionJob record.
    """
    logger.info("Polling latest ingestion job for document_id: %s", document_id)
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.warning("Document %s not found for job lookup.", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    job = (
        db.query(IngestionJob)
        .filter(IngestionJob.document_id == document_id)
        .order_by(IngestionJob.created_at.desc())
        .first()
    )
    if not job:
        logger.warning("No ingestion jobs registered for document %s.", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No ingestion jobs found for document '{document_id}'.",
        )

    return IngestionJobResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        total_pages=job.total_pages,
        total_chunks=job.total_chunks,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


@router.post(
    "/{document_id}/process",
    response_model=IngestionJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger Asynchronous Document Ingestion",
    description=(
        "Enqueues the full extraction, chunking, embedding, and persistence pipeline "
        "as an asynchronous background job. Returns immediately with HTTP 202 Accepted "
        "and the queued job details for status polling."
    ),
)
def process_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    chunk_size: Optional[int] = Query(
        None,
        gt=0,
        le=10000,
        description="Chunk size in characters (defaults to system settings if omitted)",
    ),
    chunk_overlap: Optional[int] = Query(
        None,
        ge=0,
        le=2000,
        description="Chunk overlap in characters (defaults to system settings if omitted)",
    ),
    batch_size: Optional[int] = Query(
        None,
        gt=0,
        le=512,
        description="Batch size for generating embeddings (defaults to system settings if omitted)",
    ),
    version_label: Optional[str] = Query(
        None,
        description="Explicit document version label (e.g. '1.0', 'v2.0'). Resolved automatically if omitted.",
    ),
    db: Session = Depends(get_db),
    service: IngestionService = Depends(get_ingestion_service),
) -> IngestionJobResponse:
    """
    Initiates asynchronous end-to-end ingestion:
    1. Validates document exists in PostgreSQL.
    2. Validates chunk parameters (chunk_overlap strictly < chunk_size).
    3. Checks concurrency guard against multiple simultaneous processing jobs.
    4. Registers an IngestionJob in 'pending' state.
    5. Dispatches background execution and returns HTTP 202 Accepted.
    """
    logger.info("Received request to trigger ingestion for document_id: %s", document_id)

    eff_size = chunk_size or settings.CHUNK_SIZE
    eff_overlap = chunk_overlap or settings.CHUNK_OVERLAP
    if eff_overlap >= eff_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chunk_overlap ({eff_overlap}) must be strictly less than chunk_size ({eff_size}).",
        )

    try:
        job = service.trigger_ingestion(
            db=db,
            document_id=document_id,
            background_tasks=background_tasks,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            version_label=version_label,
        )
    except ValueError as exc:
        sanitized = sanitize_error_message(str(exc))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=sanitized,
        )

    return IngestionJobResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        total_pages=job.total_pages,
        total_chunks=job.total_chunks,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )
