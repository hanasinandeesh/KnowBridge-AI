"""
Chunk and Embedding Database Persistence Service.
Task 003F – KnowBridge AI Enterprise RAG Knowledge Platform.

Persists document chunks and their corresponding 384-dimensional embeddings into
the Supabase PostgreSQL document_chunks table using SQLAlchemy and pgvector.
Reuses existing extraction (Task 003C), chunking (Task 003D), and embedding (Task 003E) services.
"""

import logging
import math
import re
import uuid
from datetime import date, datetime
from typing import Any, Optional, Sequence, Union

from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.parsers.base import (
    CorruptedDocumentError,
    EncryptedDocumentError,
    UnsupportedDocumentError,
)
from app.services.document_extractor import (
    DocumentExtractorService,
    DocumentNotFoundError as BaseDocumentNotFoundError,
)
from app.schemas.chunking import DocumentChunk as ChunkSchema, DocumentChunkingResult
from app.schemas.embedding import ChunkEmbedding, DocumentEmbeddingResult
from app.schemas.extraction import DocumentExtractionResult
from app.schemas.persistence import DocumentPersistenceResponse
from app.services.document_chunker import DocumentChunkerService
from app.services.embedding_service import EmbeddingError, EmbeddingService
from app.services.storage_service import StorageDownloadError, StorageService

logger = logging.getLogger("app.services.chunk_persistence")


# ============================================================================
# Exceptions
# ============================================================================

class PersistenceError(Exception):
    """Base exception for chunk and embedding database persistence failures."""
    pass


class DocumentNotFoundError(BaseDocumentNotFoundError, PersistenceError):
    """Raised when target document does not exist in the database."""
    pass


class DocumentVersionResolutionError(PersistenceError):
    """Raised when document version cannot be determined safely or reliably."""
    pass


class EmbeddingValidationError(PersistenceError):
    """Raised when embeddings fail dimension, finiteness, or model validation."""
    pass


class AlignmentError(PersistenceError):
    """Raised when chunks and embeddings do not align in count or order."""
    pass


# ============================================================================
# Helper Functions
# ============================================================================

def parse_iso_or_custom_date(date_str: str) -> Optional[date]:
    """
    Safely parses common date formats (e.g. '01 April 2025', '2025-04-01', '01-04-2025').
    Returns date object or None if unparseable without inventing dates.
    """
    cleaned = date_str.strip()
    # Try formats
    formats = [
        "%d %B %Y",
        "%d %b %Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%d/%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


# ============================================================================
# Chunk Persistence Service
# ============================================================================

class ChunkPersistenceService:
    """
    Dedicated database persistence service for document chunks and vector embeddings.
    Adheres strictly to the existing Supabase schema and pgvector VECTOR(384) column.
    """

    def __init__(
        self,
        expected_dimension: int = 384,
        expected_model: str = "sentence-transformers/all-MiniLM-L6-v2",
    ):
        self.expected_dimension = expected_dimension
        self.expected_model = expected_model

    # ------------------------------------------------------------------------
    # 1. Validation Logic
    # ------------------------------------------------------------------------

    def validate_embedding_vector(self, embedding: Sequence[float], index: int = 0) -> None:
        """
        Validates that a single embedding vector:
        1. Has length exactly matching expected_dimension (384).
        2. Contains only finite numeric values (no NaN, Inf, -Inf).
        """
        if embedding is None:
            raise EmbeddingValidationError(f"Embedding at index {index} is None.")

        if len(embedding) != self.expected_dimension:
            raise EmbeddingValidationError(
                f"Embedding dimension mismatch at chunk index {index}: "
                f"expected {self.expected_dimension}, got {len(embedding)}."
            )

        for elem_idx, val in enumerate(embedding):
            if not isinstance(val, (int, float)):
                raise EmbeddingValidationError(
                    f"Non-numeric vector element at chunk index {index}, element {elem_idx}: {val}"
                )
            if not math.isfinite(val):
                raise EmbeddingValidationError(
                    f"Non-finite vector element ({val}) at chunk index {index}, element {elem_idx}."
                )

    def validate_chunk_embeddings(
        self,
        chunk_embeddings: list[Union[ChunkEmbedding, dict[str, Any]]],
    ) -> None:
        """
        Validates an entire list of chunk embeddings for:
        1. Vector dimension (384).
        2. Finite numeric values.
        3. Model name match.
        4. Contiguous chunk index order.
        """
        for i, item in enumerate(chunk_embeddings):
            if isinstance(item, ChunkEmbedding):
                vec = item.embedding
                model = item.embedding_model
                chunk_idx = item.chunk_index
            elif isinstance(item, dict):
                vec = item.get("embedding")
                model = item.get("embedding_model")
                chunk_idx = item.get("chunk_index", i)
            else:
                raise EmbeddingValidationError(
                    f"Unexpected chunk embedding type at index {i}: {type(item).__name__}"
                )

            # Validate vector structure and contents
            self.validate_embedding_vector(vec, index=i)

            # Validate model name if provided
            if model and model.strip() != self.expected_model.strip():
                raise EmbeddingValidationError(
                    f"Embedding model mismatch at chunk index {i}: "
                    f"expected '{self.expected_model}', got '{model}'."
                )

            # Validate sequential chunk index
            if chunk_idx != i:
                logger.warning(
                    "Non-sequential chunk_index at position %d: chunk_index=%d",
                    i,
                    chunk_idx,
                )

    # ------------------------------------------------------------------------
    # 2. Document Version Resolution
    # ------------------------------------------------------------------------

    def resolve_or_create_version(
        self,
        db: Session,
        document: Document,
        extracted_text: Optional[str] = None,
        explicit_version_label: Optional[str] = None,
    ) -> DocumentVersion:
        """
        Resolves or creates the appropriate DocumentVersion record for persistence:
        1. If explicit_version_label is provided:
           - Look for existing DocumentVersion with (document_id, explicit_version_label).
           - If not found, safely create it.
        2. If no explicit_version_label is provided:
           - Retrieve existing versions for this document.
           - If a version is marked is_current=True, select it.
           - If versions exist but none is marked current, select the most recently created version.
           - If NO version exists at all for this document:
             Determine version label from reliable source info:
             a. Check filename for version pattern (e.g. '_v1.0', '_v2.0').
             b. Check extracted text for 'VERSION: <ver>'.
             c. If neither is available, use project standard initial version convention: '1.0'.
             d. Extract effective_from and effective_until from document text if reliably present.
             e. Populate is_current=True for this initial version.
             f. Avoid creating duplicate document versions during retries.
        """
        # Case 1: Caller specified an explicit version label
        if explicit_version_label and explicit_version_label.strip():
            target_label = explicit_version_label.strip()
            existing_ver = (
                db.query(DocumentVersion)
                .filter(
                    DocumentVersion.document_id == document.id,
                    DocumentVersion.version_label == target_label,
                )
                .first()
            )
            if existing_ver:
                logger.info(
                    "Resolved existing DocumentVersion %s (label='%s') for document %s",
                    existing_ver.id,
                    existing_ver.version_label,
                    document.id,
                )
                return existing_ver

            # Create specified version
            return self._create_version_record(
                db=db,
                document=document,
                version_label=target_label,
                extracted_text=extracted_text,
                is_current=True,
            )

        # Case 2: Inspect existing versions in database
        existing_versions = (
            db.query(DocumentVersion)
            .filter(DocumentVersion.document_id == document.id)
            .order_by(DocumentVersion.created_at.desc())
            .all()
        )

        if existing_versions:
            # Look for active/current version
            for ver in existing_versions:
                if ver.is_current:
                    logger.info(
                        "Resolved current DocumentVersion %s (label='%s') for document %s",
                        ver.id,
                        ver.version_label,
                        document.id,
                    )
                    return ver

            # Fallback to the latest existing version to preserve historical versions
            latest_ver = existing_versions[0]
            logger.info(
                "No version marked is_current; selecting latest DocumentVersion %s (label='%s') for document %s",
                latest_ver.id,
                latest_ver.version_label,
                document.id,
            )
            return latest_ver

        # Case 3: No version exists yet – determine initial version safely
        version_label = self._extract_version_label(
            filename=document.original_filename,
            extracted_text=extracted_text,
        )

        # Guard against race condition: double-check if version was created in concurrent session
        existing_ver = (
            db.query(DocumentVersion)
            .filter(
                DocumentVersion.document_id == document.id,
                DocumentVersion.version_label == version_label,
            )
            .first()
        )
        if existing_ver:
            return existing_ver

        return self._create_version_record(
            db=db,
            document=document,
            version_label=version_label,
            extracted_text=extracted_text,
            is_current=True,
        )

    def _extract_version_label(
        self,
        filename: str,
        extracted_text: Optional[str] = None,
    ) -> str:
        """
        Extracts version label from reliable sources:
        1. Filename suffix with 'v' prefix (e.g. '_v1.0' -> '1.0' or 'v2.0' -> '2.0').
        2. Extracted text header pattern 'VERSION: <num>'.
        3. Fallback to default project initial version '1.0'.
        """
        # 1. Filename regex strictly requiring 'v' (prevents false matches on IDs like -001)
        fn_match = re.search(r"[_\-\s]v(\d+(?:\.\d+)?)", filename, re.IGNORECASE)
        if fn_match:
            return fn_match.group(1)

        # 2. Text header match (e.g. 'VERSION: 1.0')
        if extracted_text:
            txt_match = re.search(r"VERSION:\s*([0-9.]+)", extracted_text, re.IGNORECASE)
            if txt_match:
                return txt_match.group(1).strip()

        # 3. Default initial project convention
        return "1.0"

    def _create_version_record(
        self,
        db: Session,
        document: Document,
        version_label: str,
        extracted_text: Optional[str] = None,
        is_current: bool = True,
    ) -> DocumentVersion:
        """
        Creates and flushes a new DocumentVersion record with safe metadata extraction.
        Never invents dates.
        """
        effective_from: Optional[date] = None
        effective_until: Optional[date] = None

        if extracted_text:
            # Look for 'EFFECTIVE DATE: 01 April 2025' or 'EFFECTIVE: ...'
            eff_match = re.search(
                r"EFFECTIVE(?:\s+DATE)?:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
                extracted_text,
                re.IGNORECASE,
            )
            if eff_match:
                effective_from = parse_iso_or_custom_date(eff_match.group(1))

            # Look for 'EXPIRY DATE: ...' or 'SUNSET DATE: ...'
            sunset_match = re.search(
                r"(?:EXPIRY|SUNSET)(?:\s+DATE)?:\s*([0-9]{1,2}\s+[A-Za-z]+\s+[0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2})",
                extracted_text,
                re.IGNORECASE,
            )
            if sunset_match:
                effective_until = parse_iso_or_custom_date(sunset_match.group(1))

        new_version = DocumentVersion(
            id=uuid.uuid4(),
            document_id=document.id,
            version_label=version_label,
            effective_from=effective_from,
            effective_until=effective_until,
            is_current=is_current,
        )

        db.add(new_version)
        try:
            db.flush()
            logger.info(
                "Created new DocumentVersion id=%s label='%s' (effective_from=%s, is_current=%s) for document %s",
                new_version.id,
                new_version.version_label,
                new_version.effective_from,
                new_version.is_current,
                document.id,
            )
            return new_version
        except SQLAlchemyError as exc:
            db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error(
                "Failed to create DocumentVersion for document %s: %s",
                document.id,
                sanitized,
            )
            raise DocumentVersionResolutionError(
                f"Database failure creating document version: {sanitized}"
            ) from exc

    # ------------------------------------------------------------------------
    # 3. Database Persistence & Idempotency
    # ------------------------------------------------------------------------

    def persist_chunks_for_version(
        self,
        db: Session,
        version: DocumentVersion,
        chunk_embeddings: list[Union[ChunkEmbedding, dict[str, Any]]],
        document_file_type: str = "pdf",
    ) -> int:
        """
        Persists chunks and embeddings for a specific document version within an atomic transaction.

        Idempotency Guarantee:
        - Deletes any existing chunks belonging to this document_version_id only.
        - Chunks belonging to other versions are strictly untouched.
        - Inserts all validated chunks and 384-dimensional vectors.
        - Deletion and insertion execute in the same atomic transaction.
        - Rolls back on any failure without leaving partial records.

        Returns:
            Count of persisted chunks.
        """
        # Validate inputs first before any DB modification
        self.validate_chunk_embeddings(chunk_embeddings)

        if not chunk_embeddings:
            logger.info(
                "Empty chunk list provided for version %s. Cleaning up any existing chunks.",
                version.id,
            )
            try:
                db.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.document_version_id == version.id
                    )
                )
                db.flush()
                return 0
            except SQLAlchemyError as exc:
                db.rollback()
                raise PersistenceError(f"Database error deleting chunks: {sanitize_error_message(str(exc))}") from exc

        # Build DocumentChunk ORM instances
        records_to_insert: list[DocumentChunk] = []
        is_pdf = document_file_type.lower() == "pdf"

        for i, item in enumerate(chunk_embeddings):
            if isinstance(item, ChunkEmbedding):
                c_id = item.chunk_id or uuid.uuid4()
                c_text = item.chunk_text
                c_sec = item.section_title
                c_page = item.page_number if is_pdf else None
                c_vec = item.embedding
                c_model = item.embedding_model or self.expected_model
                c_meta = dict(item.metadata) if item.metadata else {}
                c_tokens = getattr(item, "token_count", None)
            else:
                c_id = item.get("chunk_id") or uuid.uuid4()
                c_text = item.get("chunk_text", "")
                c_sec = item.get("section_title")
                c_page = item.get("page_number") if is_pdf else None
                c_vec = item.get("embedding")
                c_model = item.get("embedding_model", self.expected_model)
                c_meta = dict(item.get("metadata", {}))
                c_tokens = item.get("token_count")

            # Enrich metadata to preserve provenance without silently discarding attributes
            if "character_count" not in c_meta:
                c_meta["character_count"] = len(c_text)
            if "file_type" not in c_meta:
                c_meta["file_type"] = document_file_type

            chunk_record = DocumentChunk(
                id=c_id if isinstance(c_id, uuid.UUID) else uuid.UUID(str(c_id)),
                document_version_id=version.id,
                chunk_index=i,  # Contiguous zero-based index
                page_number=c_page,
                section_title=c_sec,
                chunk_text=c_text,
                embedding=c_vec,
                token_count=c_tokens,
                embedding_model=c_model,
                metadata_=c_meta,
            )
            records_to_insert.append(chunk_record)

        try:
            # 1. Atomic deletion of previous chunks for this version only
            db.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.document_version_id == version.id
                )
            )

            # 2. Bulk insertion of new chunks
            db.add_all(records_to_insert)

            # 3. Flush to execute SQL and enforce constraints
            db.flush()

            logger.info(
                "Successfully staged %d chunks for version %s (document %s)",
                len(records_to_insert),
                version.id,
                version.document_id,
            )
            return len(records_to_insert)

        except SQLAlchemyError as exc:
            db.rollback()
            sanitized_err = sanitize_error_message(str(exc))
            logger.error(
                "Transaction failure persisting chunks for version %s: %s",
                version.id,
                sanitized_err,
            )
            raise PersistenceError(
                f"Database transaction failure persisting chunks: {sanitized_err}"
            ) from exc

    # ------------------------------------------------------------------------
    # 4. Ingestion Job Tracking
    # ------------------------------------------------------------------------

    def get_or_create_ingestion_job(
        self,
        db: Session,
        document_id: uuid.UUID,
    ) -> IngestionJob:
        """
        Retrieves an existing pending or processing ingestion job for the document,
        or creates a new job record to avoid duplicate jobs during retries.
        """
        job = (
            db.query(IngestionJob)
            .filter(
                IngestionJob.document_id == document_id,
                IngestionJob.status.in_(["pending", "processing"]),
            )
            .order_by(IngestionJob.created_at.desc())
            .first()
        )
        if not job:
            job = IngestionJob(
                id=uuid.uuid4(),
                document_id=document_id,
                status="pending",
            )
            db.add(job)
            db.flush()
        return job

    def mark_job_processing(self, db: Session, job: IngestionJob) -> None:
        """Updates job state to processing with start timestamp."""
        job.status = "processing"
        job.started_at = datetime.utcnow()
        job.error_message = None
        db.flush()

    def mark_job_completed(
        self,
        db: Session,
        job: IngestionJob,
        total_chunks: int,
        total_pages: Optional[int] = None,
    ) -> None:
        """Updates job state to completed with final chunk and page counts."""
        job.status = "completed"
        job.completed_at = datetime.utcnow()
        job.total_chunks = total_chunks
        if total_pages is not None:
            job.total_pages = total_pages
        job.error_message = None
        db.flush()

    def mark_job_failed(
        self,
        db: Session,
        job: IngestionJob,
        error_msg: str,
    ) -> None:
        """Updates job state to failed with sanitized error message."""
        job.status = "failed"
        job.completed_at = datetime.utcnow()
        job.error_message = sanitize_error_message(error_msg)
        db.flush()

    # ------------------------------------------------------------------------
    # 5. End-to-End Orchestrator
    # ------------------------------------------------------------------------

    async def persist_document(
        self,
        db: Session,
        document_id: uuid.UUID,
        storage: StorageService,
        extractor: DocumentExtractorService,
        chunker: DocumentChunkerService,
        embedder: EmbeddingService,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        batch_size: Optional[int] = None,
        version_label: Optional[str] = None,
    ) -> DocumentPersistenceResponse:
        """
        Coordinates the complete document persistence workflow:
        1. Verifies document exists in PostgreSQL.
        2. Retrieves or creates IngestionJob in 'processing' state.
        3. Retrieves binary from Supabase Storage and executes structured extraction.
        4. Resolves or creates the appropriate DocumentVersion.
        5. Executes structure-aware chunking (preserving hierarchy and provenance).
        6. Generates 384-dimensional dense embeddings using local MiniLM.
        7. Validates and persists all chunks and embeddings into document_chunks.
        8. Updates IngestionJob and Document status to 'completed'.
        9. Commits the transaction and returns DocumentPersistenceResponse.

        Fault tolerance:
        - If any step fails, transaction is rolled back.
        - IngestionJob is marked 'failed' with sanitized error message.
        - Document status is updated to 'failed'.
        - Zero partial chunks are left in PostgreSQL.
        """
        logger.info("Starting persistence workflow for document %s", document_id)

        # 1. Fetch document metadata
        document = db.query(Document).filter(Document.id == document_id).first()
        if not document:
            logger.warning("Document persistence failed: document %s not found.", document_id)
            raise DocumentNotFoundError(f"Document with ID '{document_id}' not found.")

        # 2. Register/update IngestionJob
        job = self.get_or_create_ingestion_job(db, document.id)
        self.mark_job_processing(db, job)
        document.status = "processing"
        db.commit()  # Commit initial processing status so monitoring/telemetry can observe it

        try:
            # 3. Check storage configuration and download binary
            if not storage.is_configured:
                raise PersistenceError(
                    "Storage service configuration error: Supabase storage credentials are not configured."
                )

            content_bytes = await storage.download_file(document.storage_path)

            # 4. Extract structured units
            extraction_result = extractor.extract_from_bytes(
                content=content_bytes,
                filename=document.original_filename,
                file_type=document.file_type,
                document_id=document.id,
                raise_on_error=True,
            )
            total_pages = extraction_result.total_pages

            # Free binary content memory
            del content_bytes

            # 5. Resolve or create DocumentVersion
            version = self.resolve_or_create_version(
                db=db,
                document=document,
                extracted_text=extraction_result.extracted_text,
                explicit_version_label=version_label,
            )

            # 6. Generate structure-aware chunks
            chunking_result = chunker.chunk_document(
                extraction_result=extraction_result,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )

            # 7. Generate embeddings
            embedding_result = embedder.embed_document_result(
                chunking_result=chunking_result,
                batch_size=batch_size,
            )

            # 8. Persist chunks and embeddings in single atomic transaction
            persisted_count = self.persist_chunks_for_version(
                db=db,
                version=version,
                chunk_embeddings=embedding_result.embeddings,
                document_file_type=document.file_type,
            )

            # 9. Update job and document status to completed
            self.mark_job_completed(
                db=db,
                job=job,
                total_chunks=persisted_count,
                total_pages=total_pages,
            )
            document.status = "completed"
            db.commit()

            logger.info(
                "Document %s persistence completed successfully: version_id=%s (%s), chunks=%d",
                document.id,
                version.id,
                version.version_label,
                persisted_count,
            )

            return DocumentPersistenceResponse(
                document_id=document.id,
                document_version_id=version.id,
                version_label=version.version_label,
                persisted_chunk_count=persisted_count,
                embedding_model=self.expected_model,
                embedding_dimension=self.expected_dimension,
                persistence_status="completed",
                ingestion_job_id=job.id,
                metadata={
                    "total_pages": total_pages,
                    "file_type": document.file_type,
                    "original_filename": document.original_filename,
                },
            )

        except Exception as exc:
            db.rollback()
            sanitized_msg = sanitize_error_message(str(exc))
            logger.error(
                "Persistence failed for document %s: %s",
                document.id,
                sanitized_msg,
            )

            # In a fresh transaction, record job failure and document failure
            try:
                job.status = "failed"
                job.completed_at = datetime.utcnow()
                job.error_message = sanitized_msg
                document.status = "failed"
                db.commit()
            except Exception as job_exc:
                db.rollback()
                logger.error("Failed to update ingestion job failure status: %s", job_exc)

            # Re-raise original exception or wrap appropriately
            if isinstance(exc, (
                DocumentNotFoundError,
                DocumentVersionResolutionError,
                EmbeddingValidationError,
                AlignmentError,
                PersistenceError,
                CorruptedDocumentError,
                EncryptedDocumentError,
                UnsupportedDocumentError,
                StorageDownloadError,
                EmbeddingError,
            )):
                raise exc

            raise PersistenceError(f"Document persistence failed: {sanitized_msg}") from exc


# ============================================================================
# FastAPI Dependency Provider
# ============================================================================

def get_chunk_persistence_service() -> ChunkPersistenceService:
    """FastAPI dependency provider returning configured ChunkPersistenceService."""
    return ChunkPersistenceService(
        expected_dimension=settings.EMBEDDING_DIMENSION,
        expected_model=settings.EMBEDDING_MODEL_NAME,
    )
