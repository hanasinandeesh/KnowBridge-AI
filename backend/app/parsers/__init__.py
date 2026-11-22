"""Document parsers package for KnowBridge AI."""
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

__all__ = [
    "BaseDocumentParser",
    "ExtractionError",
    "CorruptedDocumentError",
    "EncryptedDocumentError",
    "EmptyDocumentError",
    "UnsupportedDocumentError",
    "PDFParser",
    "DOCXParser",
    "TXTParser",
]
