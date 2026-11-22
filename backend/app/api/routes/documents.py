import logging
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db, sanitize_error_message
from app.models.document import Document
from app.parsers.base import (
    CorruptedDocumentError,
    EncryptedDocumentError,
    UnsupportedDocumentError,
)
from app.schemas.chunking import DocumentChunkingResult
from app.schemas.document import DocumentUploadResponse
from app.schemas.embedding import DocumentEmbeddingResult
from app.schemas.extraction import DocumentExtractionResult
from app.schemas.persistence import DocumentPersistenceResponse
from app.services.document_chunker import (
    DocumentChunkerService,
    get_document_chunker,
)
from app.services.document_extractor import (
    DocumentExtractorService,
    DocumentNotFoundError,
    get_document_extractor,
)
from app.services.embedding_service import (
    EmbeddingError,
    EmbeddingService,
    get_embedding_service,
)
from app.services.chunk_persistence import (
    AlignmentError,
    ChunkPersistenceService,
    DocumentVersionResolutionError,
    EmbeddingValidationError,
    PersistenceError,
    get_chunk_persistence_service,
)
from app.services.document_service import (
    create_document_record,
    process_and_validate_upload,
)
from app.services.storage_service import (
    StorageConfigurationError,
    StorageDownloadError,
    StorageService,
    StorageUploadError,
    generate_storage_path,
    get_content_type,
    get_storage_service,
)

logger = logging.getLogger("app.api.documents")
router = APIRouter(tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload Enterprise Document",
    description=(
        "Accepts a single PDF, DOCX, or TXT file via multipart/form-data. "
        "Performs comprehensive validation (filename safety, extension, MIME type, file signature, size), "
        "permanently stores the binary in Supabase Storage bucket 'knowledge-documents', "
        "and creates an initial metadata record in the database with status 'uploaded'."
    ),
)
async def upload_document(
    file: UploadFile = File(
        ...,
        description="The document file binary to upload (supported: PDF, DOCX, TXT).",
    ),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
) -> DocumentUploadResponse:
    """
    Handles end-to-end document upload workflow:
    1. Validates filename, extension, MIME type, size, and content magic signatures.
    2. Validates Supabase Storage configuration and credentials.
    3. Generates document UUID and unique, safe storage object path.
    4. Permanently uploads the binary to the private Supabase Storage bucket.
    5. Persists the document metadata record in PostgreSQL with the real storage_path.
    6. If the database transaction fails after storage upload, triggers compensating cleanup
       to delete the newly uploaded object, preventing orphaned files.
    7. Returns structured metadata response including document_id, filename, file_type, status, and storage_path.
    """
    logger.info("Received document upload request for filename: '%s'", file.filename)

    # 1. Validate file integrity, safety, format, and content signature (Task 003A)
    safe_filename, file_type, content_bytes = await process_and_validate_upload(file)

    # 2. Verify Supabase Storage configuration
    if not storage.is_configured:
        logger.error(
            "Upload rejected for '%s': Supabase storage is not configured (missing required credentials).",
            safe_filename,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service configuration error: Supabase storage credentials are not configured.",
        )

    # 3. Generate unique document UUID and predictable, safe storage path
    document_id = uuid.uuid4()
    storage_path = generate_storage_path(document_id, safe_filename)
    mime_type = get_content_type(file_type, file.content_type)

    # 4. Upload original binary to private Supabase Storage bucket
    try:
        await storage.upload_file(
            object_path=storage_path,
            content=content_bytes,
            content_type=mime_type,
        )
    except StorageConfigurationError as exc:
        logger.error("Storage configuration error during upload of '%s': %s", safe_filename, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service configuration error: Supabase storage credentials are not configured.",
        )
    except StorageUploadError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error(
            "Storage upload failure for '%s' at '%s': %s",
            safe_filename,
            storage_path,
            sanitized_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service error: failed to upload document binary.",
        )

    # 5. Persist document metadata in Supabase PostgreSQL
    try:
        document = create_document_record(
            db=db,
            safe_filename=safe_filename,
            file_type=file_type,
            doc_id=document_id,
            storage_path=storage_path,
        )
    except Exception as db_exc:
        # Storage upload succeeded, but database write failed.
        # Execute compensating cleanup: delete the newly uploaded object from Supabase Storage.
        logger.warning(
            "Database insertion failed for document id=%s ('%s') after storage upload. Initiating compensating cleanup of '%s'...",
            document_id,
            safe_filename,
            storage_path,
        )
        try:
            await storage.delete_file(object_path=storage_path)
            logger.info(
                "Compensating cleanup succeeded: Deleted orphaned storage object '%s'.",
                storage_path,
            )
        except Exception as cleanup_exc:
            sanitized_cleanup_err = sanitize_error_message(str(cleanup_exc))
            logger.error(
                "COMPENSATING CLEANUP FAILED: Unable to delete orphaned storage object '%s' from bucket '%s': %s",
                storage_path,
                storage.bucket_name,
                sanitized_cleanup_err,
            )
        # Re-raise the database exception (or HTTP 500) so error is not swallowed
        raise db_exc

    # 6. Safely free temporary binary content bytes from memory
    del content_bytes

    return DocumentUploadResponse(
        document_id=document.id,
        filename=document.original_filename,
        file_type=document.file_type,
        status=document.status,
        storage_path=document.storage_path,
    )


@router.post(
    "/{document_id}/extract",
    response_model=DocumentExtractionResult,
    status_code=status.HTTP_200_OK,
    summary="Extract Structured Document Text",
    description=(
        "Retrieves the original document binary from private Supabase Storage "
        "and extracts structured text, preserving page numbers for PDFs, "
        "logical content units (paragraphs and tables) for DOCX, and text blocks for TXT."
    ),
)
async def extract_document_text(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    extractor: DocumentExtractorService = Depends(get_document_extractor),
) -> DocumentExtractionResult:
    """
    Executes structured text extraction for an uploaded enterprise document:
    1. Resolves document record from PostgreSQL by document_id.
    2. Downloads original binary from Supabase Storage bucket 'knowledge-documents'.
    3. Parses content using PyMuPDF (PDF), python-docx (DOCX), or UTF-8 text parser (TXT).
    4. Returns structured DocumentExtractionResult preserving page numbers and document structure.
    """
    logger.info("Received extraction request for document_id: %s", document_id)

    # 1. Fetch document metadata from database
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.warning("Document extraction failed: document %s not found.", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 2. Check storage service configuration
    if not storage.is_configured:
        logger.error("Storage service unconfigured during extraction for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service configuration error: Supabase storage credentials are not configured.",
        )

    # 3. Download binary from Supabase Storage
    try:
        content_bytes = await storage.download_file(doc.storage_path)
    except StorageDownloadError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Storage download failure for document %s: %s", document_id, sanitized_err)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original document binary not found in storage at '{doc.storage_path}'.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document binary from storage service.",
        )

    # 4. Extract structured text using format-specific parser
    try:
        result = extractor.extract_from_bytes(
            content=content_bytes,
            filename=doc.original_filename,
            file_type=doc.file_type,
            document_id=doc.id,
            raise_on_error=True,
        )
        return result
    except CorruptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Corrupted document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except EncryptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.warning("Password-protected document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except UnsupportedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Unsupported document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported document format: {sanitized_err}",
        )
    finally:
        del content_bytes


@router.post(
    "/{document_id}/chunk",
    response_model=DocumentChunkingResult,
    status_code=status.HTTP_200_OK,
    summary="Chunk Extracted Document",
    description=(
        "Retrieves the extracted document structure using the existing extraction service "
        "and transforms it into deterministic, structure-aware document chunks preserving "
        "section hierarchy, table layouts, and provenance (1-based PDF pages, DOCX/TXT unit order)."
    ),
)
async def chunk_document(
    document_id: uuid.UUID,
    chunk_size: Optional[int] = Query(
        None,
        ge=50,
        le=10000,
        description="Chunk size in characters (defaults to system settings if omitted)",
    ),
    chunk_overlap: Optional[int] = Query(
        None,
        ge=0,
        le=2000,
        description="Chunk overlap in characters (defaults to system settings if omitted)",
    ),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    extractor: DocumentExtractorService = Depends(get_document_extractor),
    chunker: DocumentChunkerService = Depends(get_document_chunker),
) -> DocumentChunkingResult:
    """
    Executes structure-aware chunking for an enterprise document:
    1. Validates document exists in PostgreSQL.
    2. Validates chunk parameters (chunk_overlap strictly < chunk_size).
    3. Retrieves document binary from Supabase Storage and executes structured extraction.
    4. Transforms structured extraction output into deterministic DocumentChunks.
    5. Returns DocumentChunkingResult with full provenance metadata.
    """
    logger.info(
        "Received chunking request for document_id: %s (chunk_size=%s, chunk_overlap=%s)",
        document_id,
        chunk_size,
        chunk_overlap,
    )

    # 1. Parameter validation
    eff_size = chunk_size if chunk_size is not None else chunker.default_chunk_size
    eff_overlap = chunk_overlap if chunk_overlap is not None else chunker.default_chunk_overlap
    if eff_overlap >= eff_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chunk_overlap ({eff_overlap}) must be strictly less than chunk_size ({eff_size}).",
        )

    # 2. Fetch document metadata from database
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.warning("Document chunking failed: document %s not found.", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 3. Check storage service configuration
    if not storage.is_configured:
        logger.error("Storage service unconfigured during chunking for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service configuration error: Supabase storage credentials are not configured.",
        )

    # 4. Download binary from Supabase Storage
    try:
        content_bytes = await storage.download_file(doc.storage_path)
    except StorageDownloadError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Storage download failure for document %s: %s", document_id, sanitized_err)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original document binary not found in storage at '{doc.storage_path}'.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document binary from storage service.",
        )

    # 5. Extract structured text using format-specific parser
    try:
        extraction_result = extractor.extract_from_bytes(
            content=content_bytes,
            filename=doc.original_filename,
            file_type=doc.file_type,
            document_id=doc.id,
            raise_on_error=True,
        )
    except CorruptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Corrupted document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except EncryptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.warning("Password-protected document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except UnsupportedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Unsupported document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported document format: {sanitized_err}",
        )
    finally:
        del content_bytes

    # 6. Generate chunks using DocumentChunkerService
    chunking_result = chunker.chunk_document(
        extraction_result=extraction_result,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return chunking_result


@router.post(
    "/{document_id}/embed",
    response_model=DocumentEmbeddingResult,
    summary="Generate Embeddings for Stored Document Chunks",
    description=(
        "Retrieves a document from Supabase Storage, extracts text units (Task 003C), "
        "chunks text structure-aware (Task 003D), and generates 384-dimensional dense "
        "vector embeddings (Task 003E) using local Sentence Transformers (all-MiniLM-L6-v2). "
        "Preserves all chunk provenance and metadata. Does not persist embeddings to database."
    ),
)
async def embed_document(
    document_id: uuid.UUID,
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
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    extractor: DocumentExtractorService = Depends(get_document_extractor),
    chunker: DocumentChunkerService = Depends(get_document_chunker),
    embedder: EmbeddingService = Depends(get_embedding_service),
) -> DocumentEmbeddingResult:
    """
    Executes end-to-end extraction, chunking, and embedding generation for a stored document:
    1. Validates document exists in PostgreSQL.
    2. Validates chunk parameters (chunk_overlap strictly < chunk_size).
    3. Retrieves document binary from Supabase Storage and executes structured extraction.
    4. Generates structure-aware DocumentChunks.
    5. Converts chunks to 384-dimensional normalized dense vector embeddings in batches.
    6. Returns structured DocumentEmbeddingResult with full provenance.
    """
    logger.info(
        "Received embedding request for document_id: %s (chunk_size=%s, chunk_overlap=%s, batch_size=%s)",
        document_id,
        chunk_size,
        chunk_overlap,
        batch_size,
    )

    # 1. Parameter validation
    eff_size = chunk_size if chunk_size is not None else chunker.default_chunk_size
    eff_overlap = chunk_overlap if chunk_overlap is not None else chunker.default_chunk_overlap
    if eff_overlap >= eff_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chunk_overlap ({eff_overlap}) must be strictly less than chunk_size ({eff_size}).",
        )

    # 2. Fetch document metadata from database
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.warning("Document embedding failed: document %s not found.", document_id)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID '{document_id}' not found.",
        )

    # 3. Check storage service configuration
    if not storage.is_configured:
        logger.error("Storage service unconfigured during embedding for document %s", document_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service configuration error: Supabase storage credentials are not configured.",
        )

    # 4. Download binary from Supabase Storage
    try:
        content_bytes = await storage.download_file(doc.storage_path)
    except StorageDownloadError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Storage download failure for document %s: %s", document_id, sanitized_err)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original document binary not found in storage at '{doc.storage_path}'.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document binary from storage service.",
        )

    # 5. Extract structured text using format-specific parser
    try:
        extraction_result = extractor.extract_from_bytes(
            content=content_bytes,
            filename=doc.original_filename,
            file_type=doc.file_type,
            document_id=doc.id,
            raise_on_error=True,
        )
    except CorruptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Corrupted document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except EncryptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.warning("Password-protected document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except UnsupportedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Unsupported document %s ('%s'): %s", document_id, doc.original_filename, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported document format: {sanitized_err}",
        )
    finally:
        del content_bytes

    # 6. Generate chunks using DocumentChunkerService
    chunking_result = chunker.chunk_document(
        extraction_result=extraction_result,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )

    # 7. Generate vector embeddings using EmbeddingService
    try:
        embedding_result = embedder.embed_document_result(
            chunking_result=chunking_result,
            batch_size=batch_size,
        )
        return embedding_result
    except EmbeddingError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Embedding generation failure for document %s: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding generation failed: {sanitized_err}",
        )


@router.post(
    "/{document_id}/persist",
    response_model=DocumentPersistenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Persist Extracted Chunks and 384D Embeddings",
    description=(
        "Executes end-to-end extraction (Task 003C), chunking (Task 003D), and embedding generation (Task 003E), "
        "and persists the resulting chunks with their 384-dimensional dense vectors into the Supabase PostgreSQL "
        "'document_chunks' table using pgvector and SQLAlchemy (Task 003F). "
        "Ensures document version association, idempotency via atomic transaction replacement, and ingestion job tracking."
    ),
)
async def persist_document_chunks(
    document_id: uuid.UUID,
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
        description="Explicit document version label (e.g. '1.0', 'v2.0'). If omitted, safely resolved from document metadata.",
    ),
    db: Session = Depends(get_db),
    storage: StorageService = Depends(get_storage_service),
    extractor: DocumentExtractorService = Depends(get_document_extractor),
    chunker: DocumentChunkerService = Depends(get_document_chunker),
    embedder: EmbeddingService = Depends(get_embedding_service),
    persistence: ChunkPersistenceService = Depends(get_chunk_persistence_service),
) -> DocumentPersistenceResponse:
    """
    Coordinates end-to-end extraction, chunking, embedding, and database persistence:
    1. Verifies document exists in PostgreSQL.
    2. Validates chunk overlap strictly < chunk size.
    3. Retrieves binary from Supabase Storage and parses structured text units.
    4. Resolves or creates the appropriate DocumentVersion record.
    5. Transforms structured units into deterministic DocumentChunks.
    6. Generates 384-dimensional normalized vector embeddings.
    7. Atomically persists chunks into PostgreSQL using pgvector VECTOR(384).
    8. Records ingestion job status and returns structured persistence summary.
    """
    logger.info(
        "Received chunk and embedding persistence request for document_id: %s (chunk_size=%s, chunk_overlap=%s, batch_size=%s, version_label=%s)",
        document_id,
        chunk_size,
        chunk_overlap,
        batch_size,
        version_label,
    )

    # 1. Parameter validation
    eff_size = chunk_size if chunk_size is not None else chunker.default_chunk_size
    eff_overlap = chunk_overlap if chunk_overlap is not None else chunker.default_chunk_overlap
    if eff_overlap >= eff_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"chunk_overlap ({eff_overlap}) must be strictly less than chunk_size ({eff_size}).",
        )

    try:
        response = await persistence.persist_document(
            db=db,
            document_id=document_id,
            storage=storage,
            extractor=extractor,
            chunker=chunker,
            embedder=embedder,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            batch_size=batch_size,
            version_label=version_label,
        )
        return response

    except DocumentNotFoundError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.warning("Persistence rejected: document not found: %s", sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=sanitized_err,
        )
    except StorageDownloadError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Storage download failure during persistence of %s: %s", document_id, sanitized_err)
        if "not found" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Original document binary not found in storage: {sanitized_err}",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve document binary from storage service.",
        )
    except CorruptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Corrupted document %s during persistence: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except EncryptedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.warning("Password-protected document %s during persistence: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Document parsing failed: {sanitized_err}",
        )
    except UnsupportedDocumentError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Unsupported document format for %s: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported document format: {sanitized_err}",
        )
    except (EmbeddingValidationError, AlignmentError, DocumentVersionResolutionError) as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Validation error during persistence of %s: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=sanitized_err,
        )
    except EmbeddingError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Embedding generation failure during persistence of %s: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding generation failed: {sanitized_err}",
        )
    except PersistenceError as exc:
        sanitized_err = sanitize_error_message(str(exc))
        logger.error("Database persistence failure for document %s: %s", document_id, sanitized_err)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database persistence failed: {sanitized_err}",
        )



