"""
End-to-End Ingestion Orchestrator Service.
Task 003G – KnowBridge AI Enterprise RAG Knowledge Platform.

Automates the full upload -> extraction -> chunking -> embedding -> persistence pipeline
with asynchronous background job execution, status tracking, concurrency guards,
and sanitized error reporting.
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db, sanitize_error_message
from app.models.document import Document
from app.models.ingestion_job import IngestionJob
from app.services.chunk_persistence import (
    ChunkPersistenceService,
    get_chunk_persistence_service,
)
from app.services.document_chunker import (
    DocumentChunkerService,
    get_document_chunker,
)
from app.services.document_extractor import (
    DocumentExtractorService,
    get_document_extractor,
)
from app.services.embedding_service import (
    EmbeddingService,
    get_embedding_service,
)
from app.services.storage_service import (
    StorageService,
    get_storage_service,
)

logger = logging.getLogger("app.services.ingestion")


class IngestionService:
    """
    Central coordinator service for asynchronous document ingestion pipelines.
    Manages job lifecycle (pending -> processing -> completed / failed),
    concurrency guards against duplicate processing, and delegates execution
    to ChunkPersistenceService.
    """

    def __init__(
        self,
        persistence_service: Optional[ChunkPersistenceService] = None,
        storage_service: Optional[StorageService] = None,
        extractor_service: Optional[DocumentExtractorService] = None,
        chunker_service: Optional[DocumentChunkerService] = None,
        embedding_service: Optional[EmbeddingService] = None,
    ) -> None:
        self.persistence = persistence_service or get_chunk_persistence_service()
        self.storage = storage_service or get_storage_service()
        self.extractor = extractor_service or get_document_extractor(self.storage)
        self.chunker = chunker_service or get_document_chunker()
        self.embedder = embedding_service or get_embedding_service()

    def get_job_by_id(self, db: Session, job_id: uuid.UUID) -> Optional[IngestionJob]:
        """Retrieves an IngestionJob record by its universal UUID."""
        return db.query(IngestionJob).filter(IngestionJob.id == job_id).first()

    def get_latest_job_for_document(
        self, db: Session, document_id: uuid.UUID
    ) -> Optional[IngestionJob]:
        """Retrieves the most recently created IngestionJob for a document."""
        return (
            db.query(IngestionJob)
            .filter(IngestionJob.document_id == document_id)
            .order_by(IngestionJob.created_at.desc())
            .first()
        )

    def trigger_ingestion(
        self,
        db: Session,
        document_id: uuid.UUID,
        background_tasks: BackgroundTasks,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        batch_size: Optional[int] = None,
        version_label: Optional[str] = None,
    ) -> IngestionJob:
        """
        Registers an IngestionJob and enqueues the background ingestion pipeline.

        Args:
            db: Active database session.
            document_id: Target document UUID.
            background_tasks: FastAPI BackgroundTasks manager.
            chunk_size: Optional chunk character size override.
            chunk_overlap: Optional chunk character overlap override.
            batch_size: Optional embedding batch size override.
            version_label: Optional version label.

        Returns:
            The queued IngestionJob instance (in 'pending' state).
        """
        # 1. Verify document exists
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            raise ValueError(f"Document with ID '{document_id}' not found.")

        # 2. Check for existing active processing job (concurrency guard)
        active_job = (
            db.query(IngestionJob)
            .filter(
                IngestionJob.document_id == document_id,
                IngestionJob.status.in_(["pending", "processing"]),
            )
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
        if active_job:
            logger.info(
                "Document %s already has an active ingestion job %s (status='%s'). Reusing existing job.",
                document_id,
                active_job.id,
                active_job.status,
            )
            return active_job

        # 3. Create fresh IngestionJob in pending state
        job = IngestionJob(
            id=uuid.uuid4(),
            document_id=document_id,
            status="pending",
        )
        db.add(job)
        db.commit()
        db.refresh(job)

        # 4. Dispatch background task
        background_tasks.add_task(
            run_background_ingestion,
            document_id=document_id,
            job_id=job.id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            version_label=version_label,
            ingestion_service=self,
        )

        logger.info(
            "Enqueued asynchronous background ingestion: job_id=%s, document_id=%s",
            job.id,
            document_id,
        )
        return job

    async def execute_ingestion(
        self,
        db: Session,
        document_id: uuid.UUID,
        job_id: Optional[uuid.UUID] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        batch_size: Optional[int] = None,
        version_label: Optional[str] = None,
    ) -> None:
        """
        Executes the full ingestion pipeline using the provided database session.
        Applies concurrency guards and fault-tolerant error recording.
        """
        logger.info(
            "Executing ingestion pipeline for document_id=%s (job_id=%s)",
            document_id,
            job_id,
        )

        # 1. Fetch document record
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.error("Ingestion failed: document %s not found.", document_id)
            if job_id:
                job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
                if job:
                    job.status = "failed"
                    job.error_message = f"Document '{document_id}' not found."
                    job.completed_at = datetime.utcnow()
                    db.commit()
            return

        # 2. Concurrency check: verify another active job isn't currently processing
        active_job = (
            db.query(IngestionJob)
            .filter(
                IngestionJob.document_id == document_id,
                IngestionJob.status == "processing",
            )
            .first()
        )
        if active_job and (job_id is None or active_job.id != job_id):
            msg = (
                f"Document '{document_id}' is already being processed by active job '{active_job.id}'."
            )
            logger.warning(msg)
            if job_id:
                job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
                if job and job.id != active_job.id:
                    job.status = "failed"
                    job.error_message = msg
                    job.completed_at = datetime.utcnow()
                    db.commit()
            return

        # 3. Delegate to ChunkPersistenceService.persist_document
        try:
            await self.persistence.persist_document(
                db=db,
                document_id=document_id,
                storage=self.storage,
                extractor=self.extractor,
                chunker=self.chunker,
                embedder=self.embedder,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                batch_size=batch_size,
                version_label=version_label,
            )
            logger.info(
                "Ingestion pipeline completed successfully for document_id=%s",
                document_id,
            )
        except Exception as exc:
            db.rollback()
            sanitized_err = sanitize_error_message(str(exc))
            logger.error(
                "Ingestion pipeline error for document %s: %s",
                document_id,
                sanitized_err,
            )
            # Ensure failure state is permanently recorded on job and document
            try:
                if job_id:
                    j = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
                    if j and j.status != "failed":
                        j.status = "failed"
                        j.error_message = sanitized_err
                        j.completed_at = datetime.utcnow()
                doc = db.query(Document).filter(Document.id == document_id).first()
                if doc and doc.status != "failed":
                    doc.status = "failed"
                db.commit()
            except Exception as cleanup_exc:
                db.rollback()
                logger.error(
                    "Failed to record failure status during error handling: %s",
                    cleanup_exc,
                )


async def run_background_ingestion(
    document_id: uuid.UUID,
    job_id: Optional[uuid.UUID] = None,
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    batch_size: Optional[int] = None,
    version_label: Optional[str] = None,
    ingestion_service: Optional[IngestionService] = None,
    db: Optional[Session] = None,
) -> None:
    """
    Top-level asynchronous background task entrypoint.
    Executes IngestionService with provided or fresh database session.
    Guarantees session closure if managed internally.
    """
    service = ingestion_service or IngestionService()
    owns_session = False
    session = db

    if session is None:
        if SessionLocal is None:
            raise RuntimeError(
                "Database engine is uninitialized. Ensure DATABASE_URL is set in backend/.env"
            )
        session = SessionLocal()
        owns_session = True

    try:
        await service.execute_ingestion(
            db=session,
            document_id=document_id,
            job_id=job_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            version_label=version_label,
        )
    finally:
        if owns_session and session is not None:
            try:
                session.close()
            except Exception:
                pass


def get_ingestion_service(
    persistence: ChunkPersistenceService = Depends(get_chunk_persistence_service),
    storage: StorageService = Depends(get_storage_service),
    extractor: DocumentExtractorService = Depends(get_document_extractor),
    chunker: DocumentChunkerService = Depends(get_document_chunker),
    embedder: EmbeddingService = Depends(get_embedding_service),
) -> IngestionService:
    """FastAPI dependency provider returning configured IngestionService."""
    return IngestionService(
        persistence_service=persistence,
        storage_service=storage,
        extractor_service=extractor,
        chunker_service=chunker,
        embedding_service=embedder,
    )
