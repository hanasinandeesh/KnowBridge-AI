import abc
from typing import Optional
import uuid

from app.schemas.extraction import DocumentExtractionResult


class ExtractionError(Exception):
    """Base exception for all document text extraction errors."""
    pass


class CorruptedDocumentError(ExtractionError):
    """Raised when the document binary is malformed, truncated, or unreadable."""
    pass


class EncryptedDocumentError(ExtractionError):
    """Raised when a document is password-protected or encrypted without supplied credentials."""
    pass


class EmptyDocumentError(ExtractionError):
    """Raised when a document contains no extractable text layer or is completely blank."""
    pass


class UnsupportedDocumentError(ExtractionError):
    """Raised when an unrecognized or unsupported document format is encountered."""
    pass


class BaseDocumentParser(abc.ABC):
    """Abstract base class for format-specific document parsers."""

    @abc.abstractmethod
    def parse(
        self,
        content: bytes,
        filename: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> DocumentExtractionResult:
        """
        Parses document byte sequence and produces a structured extraction result.

        Args:
            content: Raw document binary bytes.
            filename: Original document filename.
            document_id: Optional UUID of the document record.

        Returns:
            DocumentExtractionResult with extracted text, structured units, and metadata.

        Raises:
            CorruptedDocumentError: If document binary is corrupt or invalid.
            EncryptedDocumentError: If document is password-protected.
            UnsupportedDocumentError: If document structure is unsupported.
        """
        pass
