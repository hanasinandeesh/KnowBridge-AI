import logging
from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.document import DocumentUploadResponse
from app.services.document_service import (
    create_document_record,
    process_and_validate_upload,
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
        "and creates an initial metadata record in the database with status 'uploaded'."
    ),
)
async def upload_document(
    file: UploadFile = File(
        ...,
        description="The document file binary to upload (supported: PDF, DOCX, TXT).",
    ),
    db: Session = Depends(get_db),
) -> DocumentUploadResponse:
    """
    Handles document upload endpoint:
    1. Validates filename, extension, MIME type, size, and magic signatures.
    2. Persists document record with status 'uploaded' in the documents table.
    3. Safely discards temporary uploaded binary bytes (Supabase Storage integration in Task 003B/04).
    4. Returns structured metadata response.
    """
    logger.info("Received document upload request for filename: '%s'", file.filename)

    # Validate file integrity, safety, format, and content signature
    safe_filename, file_type, content_bytes = await process_and_validate_upload(file)

    # Persist document metadata in Supabase PostgreSQL
    document = create_document_record(
        db=db,
        safe_filename=safe_filename,
        file_type=file_type,
    )

    # Discard temporary content bytes (Task 003A only persists metadata)
    del content_bytes

    return DocumentUploadResponse(
        document_id=document.id,
        filename=document.original_filename,
        file_type=document.file_type,
        status=document.status,
    )
