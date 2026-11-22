import logging
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db, sanitize_error_message
from app.schemas.document import DocumentUploadResponse
from app.services.document_service import (
    create_document_record,
    process_and_validate_upload,
)
from app.services.storage_service import (
    StorageConfigurationError,
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
