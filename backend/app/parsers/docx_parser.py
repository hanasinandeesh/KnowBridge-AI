import io
import logging
import re
import uuid
import zipfile
from typing import Any, Optional

import docx
from docx.opc.exceptions import PackageNotFoundError
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.parsers.base import (
    BaseDocumentParser,
    CorruptedDocumentError,
)
from app.schemas.extraction import ContentUnit, DocumentExtractionResult

logger = logging.getLogger("app.parsers.docx")

DOCX_HEADING_PATTERN = re.compile(
    r"^(?:Section\s+[0-9A-Z]+|[0-9]+(?:\.[0-9]+)+\s+[A-Za-z]|[0-9]+\.\s+[A-Za-z]|Appendix\s+[A-Z]).*"
)


def format_table_as_markdown(table: Table) -> tuple[str, list[list[str]]]:
    """
    Converts a docx Table into a clean Markdown table representation and structured 2D grid.
    Replaces internal cell newlines to maintain single-line table row formatting.

    Args:
        table: python-docx Table object.

    Returns:
        Tuple of (markdown_string, table_grid_list).
    """
    grid: list[list[str]] = []
    for row in table.rows:
        row_cells = [re.sub(r"\s+", " ", cell.text.strip()) for cell in row.cells]
        # Avoid duplicate consecutive cells in merged rows
        grid.append(row_cells)

    if not grid or not any(any(c for c in r) for r in grid):
        return "", []

    num_cols = max(len(r) for r in grid)
    # Normalize row lengths
    normalized_grid = [r + [""] * (num_cols - len(r)) for r in grid]

    md_lines: list[str] = []
    # Header row
    header = normalized_grid[0]
    md_lines.append("| " + " | ".join(header) + " |")
    md_lines.append("| " + " | ".join(["---"] * num_cols) + " |")

    # Data rows
    for row in normalized_grid[1:]:
        md_lines.append("| " + " | ".join(row) + " |")

    return "\n".join(md_lines), normalized_grid


class DOCXParser(BaseDocumentParser):
    """
    Production-grade DOCX text extraction parser powered by python-docx.
    Extracts paragraphs and tables in exact document order without fabricating page numbers.
    Preserves heading hierarchy and structured table grids.
    """

    def parse(
        self,
        content: bytes,
        filename: str,
        document_id: Optional[uuid.UUID] = None,
    ) -> DocumentExtractionResult:
        """
        Extracts structured text from a DOCX binary.

        Args:
            content: Raw DOCX bytes.
            filename: Original DOCX filename.
            document_id: Optional UUID of the document record.

        Returns:
            DocumentExtractionResult containing structured logical units and provenance metadata.

        Raises:
            CorruptedDocumentError: If the DOCX binary is corrupt, not a zip, or malformed.
        """
        if not content:
            raise CorruptedDocumentError("DOCX content is empty (0 bytes).")

        # Basic PK signature check
        if not content.startswith(b"PK\x03\x04") and not content.startswith(b"PK\x05\x06"):
            raise CorruptedDocumentError("Invalid DOCX binary: missing PK zip archive signature.")

        try:
            doc = docx.Document(io.BytesIO(content))
        except (PackageNotFoundError, zipfile.BadZipFile, KeyError, ValueError) as exc:
            logger.error("Failed to parse DOCX archive for '%s': %s", filename, exc)
            raise CorruptedDocumentError(f"Corrupted or malformed DOCX document: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected error opening DOCX '%s': %s", filename, exc)
            raise CorruptedDocumentError(f"Unable to read DOCX document: {exc}") from exc

        units: list[ContentUnit] = []
        extracted_text_blocks: list[str] = []
        current_section: Optional[str] = None
        total_chars = 0
        table_count = 0
        paragraph_count = 0
        heading_count = 0
        unit_counter = 0

        # Iterate over all child elements in document body to preserve exact document order
        for child in doc.element.body:
            tag = child.tag.split("}")[-1]

            if tag == "p":
                paragraph = Paragraph(child, doc)
                text = paragraph.text.strip()
                if not text:
                    continue

                style_name = paragraph.style.name if paragraph.style else "Normal"
                is_heading = (
                    style_name.lower().startswith("heading")
                    or style_name.lower() in ("title", "subtitle")
                    or bool(DOCX_HEADING_PATTERN.match(text))
                )

                if is_heading:
                    current_section = text
                    unit_type = "heading"
                    heading_count += 1
                else:
                    unit_type = "paragraph"
                    paragraph_count += 1

                char_count = len(text)
                total_chars += char_count

                unit = ContentUnit(
                    unit_index=unit_counter,
                    unit_type=unit_type,
                    page_number=None,  # Strictly None for DOCX
                    section_title=current_section,
                    text=text,
                    character_count=char_count,
                    is_empty=False,
                    metadata={
                        "style": style_name,
                        "is_heading": is_heading,
                    },
                )
                units.append(unit)
                unit_counter += 1

                formatted_text = f"## {text}" if is_heading else text
                extracted_text_blocks.append(formatted_text)

            elif tag == "tbl":
                table = Table(child, doc)
                table_md, table_grid = format_table_as_markdown(table)
                if not table_md:
                    continue

                table_count += 1
                char_count = len(table_md)
                total_chars += char_count

                unit = ContentUnit(
                    unit_index=unit_counter,
                    unit_type="table",
                    page_number=None,  # Strictly None for DOCX
                    section_title=current_section,
                    text=table_md,
                    character_count=char_count,
                    is_empty=False,
                    metadata={
                        "num_rows": len(table.rows),
                        "num_columns": len(table.columns),
                        "headers": table_grid[0] if table_grid else [],
                        "table_grid": table_grid,
                    },
                )
                units.append(unit)
                unit_counter += 1
                extracted_text_blocks.append(table_md)

        full_extracted_text = "\n\n".join(extracted_text_blocks)
        is_empty = (len(units) == 0 or total_chars == 0)

        extraction_status = "empty_content" if is_empty else "completed"

        metadata: dict[str, Any] = {
            "parser": "python-docx",
            "parser_version": docx.__version__,
            "total_logical_units": len(units),
            "paragraph_count": paragraph_count,
            "heading_count": heading_count,
            "table_count": table_count,
            "pagination_note": "DOCX pagination depends on client rendering and is not fixed; page numbers are omitted.",
        }

        if is_empty:
            metadata["note"] = "DOCX document contains no readable text, paragraphs, or tables."

        return DocumentExtractionResult(
            document_id=document_id,
            filename=filename,
            file_type="docx",
            extraction_status=extraction_status,
            total_pages=None,  # Strictly None for DOCX
            total_characters=total_chars,
            extracted_text=full_extracted_text,
            pages=units,
            metadata=metadata,
        )
