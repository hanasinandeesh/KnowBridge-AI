import codecs
import logging
import re
import uuid
from typing import Any, Optional

from app.parsers.base import (
    BaseDocumentParser,
    CorruptedDocumentError,
)
from app.schemas.extraction import ContentUnit, DocumentExtractionResult

logger = logging.getLogger("app.parsers.txt")

TXT_HEADING_PATTERN = re.compile(
    r"^(?:Section\s+[0-9A-Z]+|[0-9]+(?:\.[0-9]+)+\s+[A-Za-z]|[0-9]+\.\s+[A-Za-z]|Appendix\s+[A-Z]|#{1,6}\s+.*).*"
)


class TXTParser(BaseDocumentParser):
    """
    Production-grade plain text document parser.
    Supports standard UTF-8 and UTF-8 with BOM (Byte Order Mark),
    handles decoding errors safely, preserves line breaks and paragraph boundaries,
    and isolates logical text blocks without fabricating page numbers.
    """

    def parse(
        self,
        content: bytes,
        filename: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> DocumentExtractionResult:
        """
        Parses plain text document binary into structured logical text units.

        Args:
            content: Raw text document bytes.
            filename: Original filename.
            document_id: Optional UUID of the document record.

        Returns:
            DocumentExtractionResult containing structured text units.

        Raises:
            CorruptedDocumentError: If text is empty (0 bytes) or invalid encoding.
        """
        if not content:
            raise CorruptedDocumentError("Text content is empty (0 bytes).")

        # Reject binary null bytes
        if b"\x00" in content:
            raise CorruptedDocumentError(
                "Invalid text document: binary data detected (null bytes present)."
            )

        # 1. Safe Decoding (UTF-8 BOM, standard UTF-8, ASCII fallback)
        decoded_text: str = ""
        encoding_used: str = "utf-8"
        has_bom: bool = content.startswith(codecs.BOM_UTF8)

        if has_bom:
            try:
                decoded_text = content.decode("utf-8-sig")
                encoding_used = "utf-8-sig"
            except UnicodeDecodeError as exc:
                logger.error("Failed to decode UTF-8 BOM text for '%s': %s", filename, exc)
                raise CorruptedDocumentError(
                    f"Invalid UTF-8 BOM text encoding in '{filename}': {exc}"
                ) from exc
        else:
            try:
                decoded_text = content.decode("utf-8")
                encoding_used = "utf-8"
            except UnicodeDecodeError:
                try:
                    decoded_text = content.decode("ascii")
                    encoding_used = "ascii"
                except UnicodeDecodeError as exc:
                    logger.error("Failed to decode text as UTF-8/ASCII for '%s': %s", filename, exc)
                    raise CorruptedDocumentError(
                        f"Invalid text encoding in '{filename}': text could not be decoded as valid UTF-8 or ASCII."
                    ) from exc

        # Normalize line endings (\r\n -> \n, \r -> \n)
        normalized_text = decoded_text.replace("\r\n", "\n").replace("\r", "\n")
        stripped_total = normalized_text.strip()

        if not stripped_total:
            logger.warning("TXT file '%s' contains only whitespace.", filename)
            return DocumentExtractionResult(
                document_id=document_id,
                filename=filename,
                file_type="txt",
                extraction_status="empty_content",
                total_pages=None,  # Strictly None for TXT
                total_characters=0,
                extracted_text="",
                pages=[],
                metadata={
                    "parser": "txt_parser",
                    "encoding": encoding_used,
                    "has_bom": has_bom,
                    "warning": "Text file contains only whitespace characters.",
                },
            )

        # 2. Extract logical content units (preserving paragraph boundaries and line breaks)
        # Split on two or more consecutive newlines
        raw_blocks = re.split(r"\n\s*\n", normalized_text)
        units: list[ContentUnit] = []
        current_section: Optional[str] = None
        unit_counter = 0
        total_chars = 0
        heading_count = 0
        block_count = 0

        for block in raw_blocks:
            clean_block = block.strip()
            if not clean_block:
                continue

            # Check if block is a heading/section title
            is_heading = False
            lines = clean_block.splitlines()
            first_line = lines[0].strip() if lines else ""

            # Case A: Single line heading
            if len(lines) == 1 and (
                (len(clean_block) < 100 and TXT_HEADING_PATTERN.match(first_line))
                or (first_line.isupper() and 3 < len(first_line) < 80)
            ):
                is_heading = True
                current_section = first_line.lstrip("# ").strip()
                heading_count += 1
                unit_type = "heading"
            # Case B: Underlined heading (e.g. Title\n------- or Title\n=======)
            elif len(lines) == 2 and re.match(r"^[-=]+$", lines[1].strip()):
                is_heading = True
                current_section = first_line.lstrip("# ").strip()
                heading_count += 1
                unit_type = "heading"
            else:
                unit_type = "text_block"
                block_count += 1

            char_count = len(clean_block)
            total_chars += char_count

            unit = ContentUnit(
                unit_index=unit_counter,
                unit_type=unit_type,
                page_number=None,  # Strictly None for TXT (no invented page numbers)
                section_title=current_section,
                text=clean_block,
                character_count=char_count,
                is_empty=False,
                metadata={
                    "line_count": len(clean_block.splitlines()),
                    "is_heading": is_heading,
                },
            )
            units.append(unit)
            unit_counter += 1

        metadata: dict[str, Any] = {
            "parser": "txt_parser",
            "encoding": encoding_used,
            "has_bom": has_bom,
            "total_logical_units": len(units),
            "heading_count": heading_count,
            "text_block_count": block_count,
            "pagination_note": "Plain text documents do not have pages; page numbers are omitted.",
        }

        return DocumentExtractionResult(
            document_id=document_id,
            filename=filename,
            file_type="txt",
            extraction_status="completed",
            total_pages=None,  # Strictly None for TXT
            total_characters=total_chars,
            extracted_text=stripped_total,
            pages=units,
            metadata=metadata,
        )
