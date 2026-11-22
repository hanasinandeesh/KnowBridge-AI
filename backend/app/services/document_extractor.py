import logging
import os
import uuid
from typing import Optional, Union

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.models.document import Document
from app.parsers.base import (
    BaseDocumentParser,
    CorruptedDocumentError,
    EmptyDocumentError,
    EncryptedDocumentError,
    ExtractionError,
    UnsupportedDocumentError,
)
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.schemas.extraction import DocumentExtractionResult
from app.services.storage_service import (
    StorageConfigurationError,
    StorageDownloadError,
    StorageService,
    get_storage_service,
)

logger = logging.getLogger("app.services.document_extractor")


class DocumentNotFoundError(ExtractionError):
    """Raised when a requested document ID does not exist in the database."""
    pass


class DocumentExtractorService:
    """
    Central document text extraction service for KnowBridge AI.
    Retrieves original document binaries from private Supabase Storage,
    dispatches to the appropriate format-specific parser (PDF, DOCX, TXT),
    and returns consistent structured extraction output preserving logical units and provenance.
    """

    def __init__(self, storage_service: Optional[StorageService] = None) -> None:
        self.storage = storage_service or get_storage_service()
        self._parsers: dict[str, BaseDocumentParser] = {
            "pdf": PDFParser(),
            "docx": DOCXParser(),
            "txt": TXTParser(),
        }

    def get_parser(self, file_type: str) -> BaseDocumentParser:
        """
        Retrieves the registered parser instance for the specified file format.

        Args:
            file_type: Normalized file extension ('pdf', 'docx', 'txt').

        Returns:
            BaseDocumentParser instance.

        Raises:
            UnsupportedDocumentError: If the format is not supported.
        """
        normalized_type = file_type.lower().strip().lstrip(".")
        if normalized_type not in self._parsers:
            raise UnsupportedDocumentError(
                f"Unsupported document format '{normalized_type}'. "
                f"Supported formats: {', '.join(sorted(self._parsers.keys()))}."
            )
        return self._parsers[normalized_type]

    def extract_from_bytes(
        self,
        content: bytes,
        filename: str,
        file_type: Optional[str] = None,
        document_id: Optional[uuid.UUID] = None,
        raise_on_error: bool = True,
    ) -> DocumentExtractionResult:
        """
        Extracts structured text and logical units directly from in-memory binary bytes.

        Args:
            content: Raw document binary bytes.
            filename: Document filename.
            file_type: Optional explicit file type ('pdf', 'docx', 'txt'). Inferred from filename if None.
            document_id: Optional document UUID.
            raise_on_error: If True, raises ExtractionError subclasses on parse failure;
                            if False, returns result with extraction_status='failed'.

        Returns:
            DocumentExtractionResult with extracted text, units, and provenance.
        """
        inferred_type = file_type
        if not inferred_type:
            _, ext = os.path.splitext(filename)
            inferred_type = ext.lstrip(".").lower()

        try:
            parser = self.get_parser(inferred_type)
            result = parser.parse(content=content, filename=filename, document_id=document_id)
            return result

        except (CorruptedDocumentError, EncryptedDocumentError, UnsupportedDocumentError, EmptyDocumentError) as exc:
            if raise_on_error:
                raise
            status = "unsupported" if isinstance(exc, UnsupportedDocumentError) else "failed"
            logger.warning("Extraction error for '%s' (status=%s): %s", filename, status, exc)
            return DocumentExtractionResult(
                document_id=document_id,
                filename=filename,
                file_type=inferred_type or "unknown",
                extraction_status=status,
                total_pages=None,
                total_characters=0,
                extracted_text="",
                pages=[],
                metadata={
                    "error": str(exc),
                    "error_type": exc.__class__.__name__,
                },
            )

    async def extract_document(
        self,
        document_or_id: Union[Document, uuid.UUID, str],
        db: Session,
        storage: Optional[StorageService] = None,
        raise_on_error: bool = True,
    ) -> DocumentExtractionResult:
        """
        Asynchronously retrieves the document binary from Supabase Storage and executes structured text extraction.

        Args:
            document_or_id: Document ORM instance, UUID, or UUID string.
            db: Active SQLAlchemy database session.
            storage: Optional StorageService instance (uses self.storage if omitted).
            raise_on_error: Whether to raise extraction exceptions or return structured failure response.

        Returns:
            DocumentExtractionResult with extracted units and metadata.

        Raises:
            DocumentNotFoundError: If document record does not exist.
            StorageDownloadError: If binary download from Supabase Storage fails.
            ExtractionError: If document binary is corrupt, encrypted, or unsupported (when raise_on_error=True).
        """
        doc = self._resolve_document(document_or_id, db)
        storage_client = storage or self.storage

        logger.info(
            "Initiating document extraction: document_id=%s, filename='%s', storage_path='%s'",
            doc.id,
            doc.original_filename,
            doc.storage_path,
        )

        # Download original file binary from private Supabase Storage bucket
        try:
            content_bytes = await storage_client.download_file(doc.storage_path)
        except (StorageConfigurationError, StorageDownloadError) as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Storage download failure for document %s: %s", doc.id, sanitized)
            raise

        return self.extract_from_bytes(
            content=content_bytes,
            filename=doc.original_filename,
            file_type=doc.file_type,
            document_id=doc.id,
            raise_on_error=raise_on_error,
        )

    def extract_document_sync(
        self,
        document_or_id: Union[Document, uuid.UUID, str],
        db: Session,
        storage: Optional[StorageService] = None,
        raise_on_error: bool = True,
    ) -> DocumentExtractionResult:
        """
        Synchronous version of extract_document for CLI scripts, background workers, and synchronous testing.
        """
        doc = self._resolve_document(document_or_id, db)
        storage_client = storage or self.storage

        logger.info(
            "Initiating synchronous document extraction: document_id=%s, filename='%s', storage_path='%s'",
            doc.id,
            doc.original_filename,
            doc.storage_path,
        )

        try:
            content_bytes = storage_client.download_file_sync(doc.storage_path)
        except (StorageConfigurationError, StorageDownloadError) as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Storage download failure for document %s: %s", doc.id, sanitized)
            raise

        return self.extract_from_bytes(
            content=content_bytes,
            filename=doc.original_filename,
            file_type=doc.file_type,
            document_id=doc.id,
            raise_on_error=raise_on_error,
        )

    def _resolve_document(
        self,
        document_or_id: Union[Document, uuid.UUID, str],
        db: Session,
    ) -> Document:
        """Resolves Document entity from instance, UUID, or string identifier."""
        if isinstance(document_or_id, Document):
            return document_or_id

        doc_uuid: uuid.UUID
        if isinstance(document_or_id, str):
            try:
                doc_uuid = uuid.UUID(document_or_id)
            except ValueError as exc:
                raise DocumentNotFoundError(f"Invalid document UUID: '{document_or_id}'") from exc
        elif isinstance(document_or_id, uuid.UUID):
            doc_uuid = document_or_id
        else:
            raise DocumentNotFoundError(f"Unsupported document identifier type: {type(document_or_id)}")

        doc = db.query(Document).filter(Document.id == doc_uuid).first()
        if not doc:
            raise DocumentNotFoundError(f"Document with ID '{doc_uuid}' not found.")
        return doc


def get_document_extractor(
    storage: StorageService = Depends(get_storage_service),
) -> DocumentExtractorService:
    """FastAPI dependency provider returning DocumentExtractorService configured with StorageService."""
    return DocumentExtractorService(storage_service=storage)
