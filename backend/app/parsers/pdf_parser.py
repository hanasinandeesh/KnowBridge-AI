import logging
import re
import uuid
from typing import Any, Optional

import pymupdf

from app.parsers.base import (
    BaseDocumentParser,
    CorruptedDocumentError,
    EncryptedDocumentError,
)
from app.schemas.extraction import ContentUnit, DocumentExtractionResult

logger = logging.getLogger("app.parsers.pdf")


HEADING_PATTERN = re.compile(
    r"^(?:Section\s+[0-9A-Z]+|[0-9]+(?:\.[0-9]+)+\s+[A-Za-z]|[0-9]+\.\s+[A-Za-z]|Appendix\s+[A-Z]).*"
)


class PDFParser(BaseDocumentParser):
    """
    Production-grade PDF text extraction parser powered by PyMuPDF (fitz).
    Preserves exact 1-based page numbers, detects empty/scanned pages without claiming OCR support,
    and isolates page boundaries.
    """

    def parse(
        self,
        content: bytes,
        filename: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> DocumentExtractionResult:
        """
        Extracts structured text from a PDF binary.

        Args:
            content: Raw PDF bytes.
            filename: Original PDF filename.
            document_id: Optional UUID of the document record.

        Returns:
            DocumentExtractionResult containing per-page units and extraction metadata.

        Raises:
            CorruptedDocumentError: If the PDF binary is corrupted or malformed.
            EncryptedDocumentError: If the PDF is password-protected.
        """
        if not content:
            raise CorruptedDocumentError("PDF content is empty (0 bytes).")

        doc: Optional[pymupdf.Document] = None
        try:
            doc = pymupdf.open(stream=content, filetype="pdf")
        except Exception as exc:
            logger.error("Failed to open PDF binary for '%s': %s", filename, exc)
            raise CorruptedDocumentError(f"Corrupted or invalid PDF file: {exc}") from exc

        try:
            # 1. Handle Password Protection / Encryption
            if doc.is_encrypted and doc.needs_pass:
                logger.warning("PDF '%s' is password-protected and cannot be extracted.", filename)
                raise EncryptedDocumentError(
                    f"PDF document '{filename}' is password-protected and cannot be extracted."
                )

            total_pages = len(doc)
            logger.info("Parsing PDF '%s' with %d pages", filename, total_pages)

            if total_pages == 0:
                logger.warning("PDF '%s' contains 0 pages.", filename)
                return DocumentExtractionResult(
                    document_id=document_id,
                    filename=filename,
                    file_type="pdf",
                    extraction_status="empty_content",
                    total_pages=0,
                    total_characters=0,
                    extracted_text="",
                    pages=[],
                    metadata={
                        "parser": "PyMuPDF",
                        "parser_version": pymupdf.__version__,
                        "scanned_only": False,
                        "ocr_supported": False,
                        "empty_page_count": 0,
                        "warning": "PDF contains zero pages.",
                    },
                )

            # 2. Extract Document Table of Contents / Bookmarks if available
            toc_by_page: dict[int, str] = {}
            try:
                toc = doc.get_toc()
                for item in toc:
                    # item format: [level, title, page_number] (1-based page_number)
                    if len(item) >= 3 and isinstance(item[2], int):
                        pno = item[2]
                        if pno not in toc_by_page:
                            toc_by_page[pno] = item[1].strip()
            except Exception as exc:
                logger.debug("Could not read PDF outline/TOC for '%s': %s", filename, exc)

            # 3. Extract text page by page (1-based indexing)
            pages: list[ContentUnit] = []
            extracted_text_parts: list[str] = []
            total_chars = 0
            empty_pages_count = 0
            current_section: Optional[str] = None

            for page_idx in range(total_pages):
                page_number = page_idx + 1  # Strictly 1-based page number
                page = doc[page_idx]

                # Update current section title from TOC if available for this page
                if page_number in toc_by_page:
                    current_section = toc_by_page[page_number]

                raw_page_text = page.get_text("text") or ""
                stripped_text = raw_page_text.strip()
                page_char_count = len(stripped_text)

                # Heading heuristic to detect section transitions
                page_heading: Optional[str] = None
                if stripped_text:
                    for line in stripped_text.splitlines():
                        candidate = line.strip()
                        if 3 < len(candidate) < 120 and HEADING_PATTERN.match(candidate):
                            page_heading = candidate
                            current_section = candidate
                            break
                            current_section = candidate
                            break

                effective_section = current_section or page_heading

                is_empty_page = (page_char_count == 0)
                if is_empty_page:
                    empty_pages_count += 1

                unit_metadata: dict[str, Any] = {
                    "width": round(page.rect.width, 2),
                    "height": round(page.rect.height, 2),
                    "rotation": page.rotation,
                }

                # Check if page contains images (e.g. scanned image)
                image_list = page.get_images(full=True)
                unit_metadata["image_count"] = len(image_list)
                if is_empty_page and len(image_list) > 0:
                    unit_metadata["detected_type"] = "scanned_or_image_only"

                unit = ContentUnit(
                    unit_index=page_idx,
                    unit_type="page",
                    page_number=page_number,
                    section_title=effective_section,
                    text=stripped_text,
                    character_count=page_char_count,
                    is_empty=is_empty_page,
                    metadata=unit_metadata,
                )
                pages.append(unit)

                if stripped_text:
                    extracted_text_parts.append(
                        f"--- [Page {page_number}] ---\n{stripped_text}"
                    )
                    total_chars += page_char_count

            # 4. Determine overall extraction status
            # Distinguish between successful extraction and unreadable / scanned-only PDF
            all_pages_empty = (empty_pages_count == total_pages)
            if all_pages_empty:
                extraction_status = "empty_content"
                logger.warning(
                    "PDF '%s' has %d pages but 0 extractable characters (scanned or blank).",
                    filename,
                    total_pages,
                )
            else:
                extraction_status = "completed"

            full_extracted_text = "\n\n".join(extracted_text_parts)

            doc_metadata: dict[str, Any] = {
                "parser": "PyMuPDF",
                "parser_version": pymupdf.__version__,
                "total_pages": total_pages,
                "empty_pages_count": empty_pages_count,
                "scanned_only": all_pages_empty,
                "ocr_supported": False,
            }

            if all_pages_empty:
                doc_metadata["note"] = (
                    "Document contains no extractable digital text layer. "
                    "Pages may be scanned images or empty. OCR is not supported."
                )

            return DocumentExtractionResult(
                document_id=document_id,
                filename=filename,
                file_type="pdf",
                extraction_status=extraction_status,
                total_pages=total_pages,
                total_characters=total_chars,
                extracted_text=full_extracted_text,
                pages=pages,
                metadata=doc_metadata,
            )

        finally:
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass
