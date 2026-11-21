import io
import logging
import os
import re
import uuid
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.models.document import Document

logger = logging.getLogger("app.services.document")

# Allowed MIME types per file extension (preliminary verification)
MIME_TYPE_MAPPINGS: dict[str, set[str]] = {
    "pdf": {
        "application/pdf",
        "application/x-pdf",
        "application/acrobat",
        "applications/vnd.pdf",
        "text/pdf",
        "application/octet-stream",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/docx",
        "application/msword",
        "application/x-zip-compressed",
        "application/zip",
        "application/octet-stream",
    },
    "txt": {
        "text/plain",
        "text/markdown",
        "text/csv",
        "text/tab-separated-values",
        "application/octet-stream",
    },
}


def sanitize_filename(raw_filename: Optional[str]) -> str:
    """
    Sanitizes an uploaded filename to prevent path traversal, null-byte injection,
    and dangerous filesystem characters.

    Args:
        raw_filename: Client-supplied original filename.

    Returns:
        Safe, sanitized filename string.

    Raises:
        HTTPException (400): If filename is empty, contains null bytes, or cannot be sanitized.
    """
    if not raw_filename or not raw_filename.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty.",
        )

    # Reject null-byte poisoning
    if "\x00" in raw_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: null bytes detected.",
        )

    # Strip directory separators and path traversal components
    # Extract only the base name (handles both Unix '/' and Windows '\')
    normalized = raw_filename.replace("\\", "/")
    base_name = os.path.basename(normalized)

    # Also extract via pathlib as a secondary safeguard
    pure_name = Path(base_name).name

    # Remove dangerous or control characters; allow alphanumeric, spaces, dots, dashes, underscores, parentheses, brackets
    cleaned = re.sub(r"[^\w\s\.\-\(\)\[\]]", "", pure_name).strip()

    # Reject filenames that reduce to dots or empty
    if not cleaned or cleaned.replace(".", "") == "":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid filename: filename contains only unsafe characters or directory traversal dots.",
        )

    # Restrict maximum length to 255 characters while preserving extension
    if len(cleaned) > 255:
        stem = Path(cleaned).stem[:240]
        ext = Path(cleaned).suffix
        cleaned = f"{stem}{ext}"

    return cleaned


def validate_file_extension(filename: str) -> str:
    """
    Validates that the file has an allowed extension (.pdf, .docx, .txt).

    Args:
        filename: Sanitized filename.

    Returns:
        Normalized lowercase extension without dot (e.g., 'pdf', 'docx', 'txt').

    Raises:
        HTTPException (400): If missing or unsupported extension.
    """
    if "." not in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File lacks an extension. Supported extensions: {', '.join(sorted(settings.ALLOWED_FILE_EXTENSIONS))}.",
        )

    ext = filename.rsplit(".", 1)[-1].lower().strip()
    if ext not in settings.ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '.{ext}'. Supported extensions: {', '.join(sorted(settings.ALLOWED_FILE_EXTENSIONS))}.",
        )

    return ext


def validate_mime_type(content_type: Optional[str], file_type: str) -> None:
    """
    Preliminary check verifying the client-provided MIME type against expected types for the file extension.

    Args:
        content_type: Browser or client-provided Content-Type header.
        file_type: Normalized file type ('pdf', 'docx', 'txt').

    Raises:
        HTTPException (400): If MIME type is present but incompatible.
    """
    if not content_type:
        return

    # Strip optional charset or boundary parameters (e.g., 'text/plain; charset=utf-8')
    mime_base = content_type.split(";")[0].strip().lower()

    allowed_mimes = MIME_TYPE_MAPPINGS.get(file_type, set())
    if mime_base not in allowed_mimes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid MIME type '{mime_base}' for {file_type.upper()} file. Expected one of: {', '.join(sorted(allowed_mimes))}.",
        )


def validate_file_size(content: bytes) -> None:
    """
    Validates that the file content is neither empty nor exceeding the configured maximum size limit.

    Args:
        content: Uploaded file byte content.

    Raises:
        HTTPException (400): If file is 0 bytes.
        HTTPException (413): If file exceeds MAX_UPLOAD_SIZE_BYTES.
    """
    size_bytes = len(content)

    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes). Please upload a valid document.",
        )

    if size_bytes > settings.MAX_UPLOAD_SIZE_BYTES:
        max_mb = round(settings.MAX_UPLOAD_SIZE_BYTES / (1024 * 1024), 2)
        actual_mb = round(size_bytes / (1024 * 1024), 2)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size ({actual_mb} MB) exceeds maximum allowed limit of {max_mb} MB.",
        )


def validate_file_content(content: bytes, file_type: str) -> None:
    """
    Validates file magic signatures and structural format to prevent file spoofing.
    Never trusts browser Content-Type headers alone.

    Args:
        content: File byte buffer.
        file_type: Normalized file type ('pdf', 'docx', 'txt').

    Raises:
        HTTPException (400): If content fails signature or format validation.
    """
    if file_type == "pdf":
        # PDF Specification: Header must contain '%PDF-' within the initial 1024 bytes
        if b"%PDF-" not in content[:1024]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF content: file header missing '%PDF-' signature.",
            )

    elif file_type == "docx":
        # DOCX is an OpenXML ZIP package. Must begin with standard ZIP local file header 'PK\x03\x04'
        if not content.startswith(b"PK\x03\x04") and not content.startswith(b"PK\x05\x06"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX content: missing standard ZIP/PK archive signature.",
            )

        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                namelist = zf.namelist()
                has_content_types = "[Content_Types].xml" in namelist
                has_word_content = any(name.startswith("word/") for name in namelist)
                if not (has_content_types or has_word_content):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid DOCX content: archive does not contain Word document structures.",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX content: corrupted or unreadable ZIP archive.",
            )

    elif file_type == "txt":
        # Plain text must not contain binary null bytes and must decode cleanly as UTF-8 or ASCII
        if b"\x00" in content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid TXT content: binary data detected (null bytes).",
            )

        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                content.decode("ascii")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid TXT content: text is not valid UTF-8 or ASCII encoded text.",
                )


async def process_and_validate_upload(file: UploadFile) -> tuple[str, str, bytes]:
    """
    Coordinates end-to-end validation of an uploaded file:
    1. Safe filename handling
    2. Extension validation
    3. Preliminary MIME-type validation
    4. Reading bytes and file size check
    5. Deep content signature and format validation

    Args:
        file: FastAPI UploadFile multipart object.

    Returns:
        Tuple of (safe_filename, file_type, content_bytes).
    """
    # 1. Sanitize filename
    safe_name = sanitize_filename(file.filename)

    # 2. Validate file extension
    file_type = validate_file_extension(safe_name)

    # 3. Preliminary MIME-type check
    validate_mime_type(file.content_type, file_type)

    # 4. Read bytes safely
    try:
        content = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded file stream: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to read uploaded file content stream.",
        )
    finally:
        # Safely close underlying temporary file handle immediately after reading
        await file.close()

    # 5. Check size (empty file & max size)
    validate_file_size(content)

    # 6. Deep file signature and content verification
    validate_file_content(content, file_type)

    return safe_name, file_type, content


def create_document_record(
    db: Session,
    safe_filename: str,
    file_type: str,
    doc_id: Optional[uuid.UUID] = None,
) -> Document:
    """
    Creates an initial document metadata record in the database.
    Populates only columns that exist in the inspected schema:
    id, title, original_filename, file_type, storage_path, category, status.

    Args:
        db: SQLAlchemy database session.
        safe_filename: Sanitized original filename.
        file_type: Normalized file type ('pdf', 'docx', 'txt').
        doc_id: Optional predetermined UUID (generated automatically if None).

    Returns:
        Persisted Document model instance.

    Raises:
        HTTPException (500): On database transaction failure.
    """
    document_id = doc_id or uuid.uuid4()
    title = Path(safe_filename).stem or safe_filename
    # storage_path satisfies NOT NULL and UNIQUE constraint
    # Reflects the target key for subsequent Supabase Storage upload in Task 04/003B
    storage_path = f"pending/{document_id}/{safe_filename}"

    document = Document(
        id=document_id,
        title=title,
        original_filename=safe_filename,
        file_type=file_type,
        storage_path=storage_path,
        category="general",
        status="uploaded",
    )

    db.add(document)
    try:
        db.commit()
        db.refresh(document)
        logger.info(
            "Document metadata record created successfully: id=%s, filename='%s', type='%s', status='%s'",
            document.id,
            document.original_filename,
            document.file_type,
            document.status,
        )
        return document
    except SQLAlchemyError as exc:
        db.rollback()
        sanitized_err = sanitize_error_message(str(exc))
        logger.error(
            "Database failure persisting document record for '%s': %s",
            safe_filename,
            sanitized_err,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error: unable to persist document metadata record.",
        )
