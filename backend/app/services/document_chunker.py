import logging
import re
import uuid
from typing import Any, Optional

from app.core.config import settings
from app.schemas.chunking import DocumentChunk, DocumentChunkingResult
from app.schemas.extraction import ContentUnit, DocumentExtractionResult

logger = logging.getLogger("app.services.chunker")

# Regex pattern to identify structured section and heading titles
HEADING_REGEX = re.compile(
    r"^(?:Section\s+[0-9A-Z]+|[0-9]+(?:\.[0-9]+)+\s+[A-Za-z]|[0-9]+\.\s+[A-Za-z]|Appendix\s+[A-Z]|#{1,6}\s+.*).*",
    re.IGNORECASE,
)

# Standard separator hierarchy ordered from highest semantic cohesion to atomic characters
DEFAULT_SEPARATORS = [
    "\n\n",
    ".\n",
    "?\n",
    "!\n",
    "\n",
    ". ",
    "? ",
    "! ",
    "; ",
    ", ",
    " ",
    "",
]


def extract_clean_overlap(text: str, overlap_limit: int) -> str:
    """
    Extracts up to overlap_limit characters from the end of text while strictly
    preserving complete word boundaries and preferring sentence boundaries.
    Ensures that the overlap does not slice words in half and does not duplicate
    the entire source text.
    """
    if overlap_limit <= 0 or not text:
        return ""

    stripped = text.strip()
    if len(stripped) <= overlap_limit:
        return ""

    candidate = stripped[-overlap_limit:]

    # Check if candidate slices through a word (char immediately before candidate is non-whitespace)
    cut_idx = len(stripped) - overlap_limit
    if cut_idx > 0 and not stripped[cut_idx - 1].isspace() and not candidate[0].isspace():
        # Find first whitespace or sentence boundary in candidate to align with word start
        first_space = -1
        for i, char in enumerate(candidate):
            if char.isspace():
                first_space = i
                break
        if first_space != -1:
            candidate = candidate[first_space + 1 :]
        else:
            # Candidate contains no boundary (single oversized token); omit overlap to avoid partial words
            return ""

    clean = candidate.strip()
    if clean == stripped:
        return ""
    return clean


def split_text_recursive(
    text: str,
    chunk_size: int,
    chunk_overlap: int,
    separators: Optional[list[str]] = None,
) -> list[str]:
    """
    Splits text recursively using the separator priority:
    1. Section / Paragraph boundaries (\\n\\n)
    2. Sentence boundaries (. , ? , ! , \\n)
    3. Word boundaries (' ')
    4. Characters ('') as last resort.

    Guarantees that each chunk <= chunk_size, words are kept intact whenever possible,
    consecutive chunks have clean overlap, and splitting always makes forward progress.
    """
    clean_text = text.strip()
    if not clean_text:
        return []

    if len(clean_text) <= chunk_size:
        return [clean_text]

    seps = separators if separators is not None else DEFAULT_SEPARATORS

    # Find the highest-priority separator present in text
    chosen_sep = ""
    for sep in seps:
        if sep == "":
            chosen_sep = ""
            break
        if sep in clean_text:
            chosen_sep = sep
            break

    # If character separator reached, slice strictly
    if chosen_sep == "":
        chunks: list[str] = []
        step = max(1, chunk_size - chunk_overlap)
        for i in range(0, len(clean_text), step):
            chunk = clean_text[i : i + chunk_size].strip()
            if chunk:
                chunks.append(chunk)
        return chunks

    # Split text by chosen separator
    splits = clean_text.split(chosen_sep)
    remaining_seps = seps[seps.index(chosen_sep) + 1 :] if chosen_sep in seps else seps

    # Recursively split any parts that still exceed chunk_size
    normalized_parts: list[str] = []
    for part in splits:
        p_stripped = part.strip()
        if not p_stripped:
            continue
        if len(p_stripped) > chunk_size:
            sub_chunks = split_text_recursive(
                p_stripped,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=remaining_seps,
            )
            normalized_parts.extend(sub_chunks)
        else:
            normalized_parts.append(p_stripped)

    if not normalized_parts:
        return []

    # Merge parts into chunks <= chunk_size with overlap
    chunks = []
    current_parts: list[str] = []
    current_length = 0

    join_str = chosen_sep if chosen_sep in ("\n\n", "\n", " ") else " "

    for part in normalized_parts:
        candidate_len = current_length + (len(join_str) if current_parts else 0) + len(part)
        if current_parts and candidate_len > chunk_size:
            chunk_content = join_str.join(current_parts).strip()
            if chunk_content:
                chunks.append(chunk_content)

            overlap_context = extract_clean_overlap(chunk_content, chunk_overlap)
            if overlap_context and (len(overlap_context) + len(join_str) + len(part) <= chunk_size):
                current_parts = [overlap_context, part]
                current_length = len(overlap_context) + len(join_str) + len(part)
            else:
                current_parts = [part]
                current_length = len(part)
        else:
            current_parts.append(part)
            current_length = candidate_len

    if current_parts:
        final_chunk = join_str.join(current_parts).strip()
        if final_chunk:
            # Avoid duplicate-only last chunk
            if not chunks or final_chunk != chunks[-1]:
                chunks.append(final_chunk)

    return chunks


class SectionHierarchyTracker:
    """
    Maintains hierarchical section nesting (e.g. ['1.0 Policy', '1.1 Travel', '1.1.1 Approval']).
    Updates hierarchy level deterministically based on heading styles and numerical numbering.
    """

    def __init__(self) -> None:
        self.levels: list[tuple[int, str]] = []

    def update(self, heading_text: str, level: int = 1) -> None:
        """Updates hierarchy tree, popping shallower or sibling levels."""
        clean = heading_text.splitlines()[0].strip().lstrip("# ").strip()
        if not clean:
            return
        while self.levels and self.levels[-1][0] >= level:
            self.levels.pop()
        self.levels.append((level, clean))

    def detect_level(self, text: str, style_name: Optional[str] = None) -> int:
        """Infers hierarchical heading level from style or numerical section notation."""
        if style_name:
            style_lower = style_name.lower()
            m = re.search(r"heading\s*(\d+)", style_lower)
            if m:
                return max(1, int(m.group(1)))
            if style_lower in ("title",):
                return 1
            if style_lower in ("subtitle",):
                return 2

        clean = text.splitlines()[0].strip()
        hash_match = re.match(r"^(#{1,6})\s+", clean)
        if hash_match:
            return len(hash_match.group(1))

        # Pattern: 1.0 (level 1), 1.1 (level 2), 1.1.1 (level 3)
        num_match = re.search(r"(?:Section\s+)?(\d+(?:\.\d+)*)", clean, re.IGNORECASE)
        if num_match:
            dots = num_match.group(1).count(".")
            return max(1, dots + 1)

        return 1

    @property
    def current_section(self) -> Optional[str]:
        return self.levels[-1][1] if self.levels else None

    @property
    def hierarchy(self) -> list[str]:
        return [title for _, title in self.levels]


class TableSplitter:
    """
    Handles structure-aware splitting of Markdown tables and structured grids.
    Repeats table headers across splits, preserves rows and column labels,
    and applies row-level continuity.
    """

    @staticmethod
    def split_table_unit(
        unit: ContentUnit,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[dict[str, Any]]:
        """
        Splits a table unit into multiple structured table chunks if it exceeds chunk_size,
        repeating the table header row and separator in every split chunk.
        """
        table_grid: list[list[str]] = unit.metadata.get("table_grid", [])
        raw_text = unit.text.strip()

        # If table fits completely within chunk_size, return as single chunk
        if len(raw_text) <= chunk_size:
            return [
                {
                    "text": raw_text,
                    "metadata": {
                        "is_table": True,
                        "headers": unit.metadata.get("headers", []),
                        "num_rows": unit.metadata.get("num_rows", len(table_grid)),
                        "table_part": 1,
                        "total_parts": 1,
                    },
                }
            ]

        # Case A: Structured 2D table grid available from Task 003C
        if table_grid and len(table_grid) >= 2:
            headers = table_grid[0]
            header_line = "| " + " | ".join(headers) + " |"
            sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
            header_prefix = f"{header_line}\n{sep_line}"

            data_rows = table_grid[1:]
            chunks_data: list[list[str]] = []
            current_chunk_rows: list[str] = []
            current_len = len(header_prefix)

            for row in data_rows:
                row_str = "| " + " | ".join(row) + " |"
                projected = current_len + 1 + len(row_str)

                if current_chunk_rows and projected > chunk_size:
                    chunks_data.append(list(current_chunk_rows))
                    # Row overlap: if configured, retain the last row for context continuity
                    if chunk_overlap > len(current_chunk_rows[-1]) and len(current_chunk_rows) > 1:
                        last_row = current_chunk_rows[-1]
                        current_chunk_rows = [last_row, row_str]
                        current_len = len(header_prefix) + 1 + len(last_row) + 1 + len(row_str)
                    else:
                        current_chunk_rows = [row_str]
                        current_len = len(header_prefix) + 1 + len(row_str)
                else:
                    current_chunk_rows.append(row_str)
                    current_len = projected

            if current_chunk_rows:
                chunks_data.append(list(current_chunk_rows))

            total_parts = len(chunks_data)
            results: list[dict[str, Any]] = []
            for idx, part_rows in enumerate(chunks_data):
                table_md = f"{header_prefix}\n" + "\n".join(part_rows)
                results.append(
                    {
                        "text": table_md,
                        "metadata": {
                            "is_table": True,
                            "headers": headers,
                            "table_part": idx + 1,
                            "total_parts": total_parts,
                            "rows_in_chunk": len(part_rows),
                        },
                    }
                )
            return results

        # Case B: Raw Markdown table text fallback
        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        if len(lines) >= 3 and lines[1].startswith("| ---") or "---" in lines[1]:
            header_prefix = f"{lines[0]}\n{lines[1]}"
            data_lines = lines[2:]

            chunks_lines: list[list[str]] = []
            cur_lines: list[str] = []
            cur_len = len(header_prefix)

            for line in data_lines:
                proj = cur_len + 1 + len(line)
                if cur_lines and proj > chunk_size:
                    chunks_lines.append(list(cur_lines))
                    if chunk_overlap > len(cur_lines[-1]) and len(cur_lines) > 1:
                        cur_lines = [cur_lines[-1], line]
                        cur_len = len(header_prefix) + 1 + len(cur_lines[0]) + 1 + len(line)
                    else:
                        cur_lines = [line]
                        cur_len = len(header_prefix) + 1 + len(line)
                else:
                    cur_lines.append(line)
                    cur_len = proj

            if cur_lines:
                chunks_lines.append(list(cur_lines))

            total_parts = len(chunks_lines)
            results = []
            for idx, p_lines in enumerate(chunks_lines):
                table_md = f"{header_prefix}\n" + "\n".join(p_lines)
                results.append(
                    {
                        "text": table_md,
                        "metadata": {
                            "is_table": True,
                            "table_part": idx + 1,
                            "total_parts": total_parts,
                        },
                    }
                )
            return results

        # If table cannot be parsed into rows, treat as plain text
        sub_texts = split_text_recursive(raw_text, chunk_size, chunk_overlap)
        return [
            {
                "text": st,
                "metadata": {"is_table": True, "table_part": i + 1, "total_parts": len(sub_texts)},
            }
            for i, st in enumerate(sub_texts)
        ]


class DocumentChunkerService:
    """
    Production-grade document chunking service for KnowBridge AI.
    Transforms Task 003C structured extraction results (PDF, DOCX, TXT)
    into deterministic, structure-aware chunks while preserving source provenance,
    page numbers, section hierarchies, and table integrity.
    """

    def __init__(
        self,
        default_chunk_size: Optional[int] = None,
        default_chunk_overlap: Optional[int] = None,
    ) -> None:
        self.default_chunk_size = default_chunk_size or settings.CHUNK_SIZE
        self.default_chunk_overlap = default_chunk_overlap or settings.CHUNK_OVERLAP

    def chunk_document(
        self,
        extraction_result: DocumentExtractionResult,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> DocumentChunkingResult:
        """
        Executes structure-aware chunking on a DocumentExtractionResult.

        Args:
            extraction_result: Standardized result from Task 003C extraction service.
            chunk_size: Optional chunk size override (defaults to settings.CHUNK_SIZE).
            chunk_overlap: Optional chunk overlap override (defaults to settings.CHUNK_OVERLAP).

        Returns:
            DocumentChunkingResult containing ordered, deterministic DocumentChunks with full provenance.
        """
        effective_chunk_size = chunk_size if chunk_size is not None else self.default_chunk_size
        effective_chunk_overlap = chunk_overlap if chunk_overlap is not None else self.default_chunk_overlap

        if effective_chunk_size <= 0:
            raise ValueError(f"chunk_size must be positive, got {effective_chunk_size}")
        if effective_chunk_overlap < 0:
            raise ValueError(f"chunk_overlap cannot be negative, got {effective_chunk_overlap}")
        if effective_chunk_overlap >= effective_chunk_size:
            raise ValueError(
                f"chunk_overlap ({effective_chunk_overlap}) must be strictly less than chunk_size ({effective_chunk_size})"
            )

        # Handle empty extraction output gracefully
        if (
            extraction_result.extraction_status == "empty_content"
            or not extraction_result.pages
            or extraction_result.total_characters == 0
        ):
            logger.info("Empty extraction result for '%s'; returning 0 chunks.", extraction_result.filename)
            return DocumentChunkingResult(
                document_id=extraction_result.document_id,
                filename=extraction_result.filename,
                file_type=extraction_result.file_type,
                total_chunks=0,
                chunk_size=effective_chunk_size,
                chunk_overlap=effective_chunk_overlap,
                chunks=[],
                metadata={
                    "status": "empty_content",
                    "note": "Document contains no extractable text or content units.",
                },
            )

        file_type = extraction_result.file_type.lower()
        if file_type == "pdf":
            chunks = self._chunk_pdf(extraction_result, effective_chunk_size, effective_chunk_overlap)
        elif file_type == "docx":
            chunks = self._chunk_docx(extraction_result, effective_chunk_size, effective_chunk_overlap)
        elif file_type == "txt":
            chunks = self._chunk_txt(extraction_result, effective_chunk_size, effective_chunk_overlap)
        else:
            # Fallback for unrecognized formats
            chunks = self._chunk_txt(extraction_result, effective_chunk_size, effective_chunk_overlap)

        return DocumentChunkingResult(
            document_id=extraction_result.document_id,
            filename=extraction_result.filename,
            file_type=extraction_result.file_type,
            total_chunks=len(chunks),
            chunk_size=effective_chunk_size,
            chunk_overlap=effective_chunk_overlap,
            chunks=chunks,
            metadata={
                "parser_source": extraction_result.metadata.get("parser", "unknown"),
                "total_source_characters": extraction_result.total_characters,
                "total_source_units": len(extraction_result.pages),
            },
        )

    def _chunk_pdf(
        self,
        extraction_result: DocumentExtractionResult,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[DocumentChunk]:
        """
        Chunks PDF content page-by-page.
        Preserves exact 1-based page numbers from Task 003C and avoids combining text
        across different pages so citation provenance remains unambiguous.
        """
        chunks: list[DocumentChunk] = []
        chunk_idx = 0
        section_tracker = SectionHierarchyTracker()

        for unit in extraction_result.pages:
            # Skip empty or unreadable pages
            if unit.is_empty or not unit.text.strip():
                continue

            # Update section tracker if page has a detected section title
            if unit.section_title:
                level = section_tracker.detect_level(unit.section_title)
                section_tracker.update(unit.section_title, level)

            page_text = unit.text.strip()
            page_pno = unit.page_number  # Strictly 1-based integer

            # Detect inline section boundaries on this page
            page_lines = page_text.splitlines()
            current_section_lines: list[str] = []

            for line in page_lines:
                clean_line = line.strip()
                if (
                    3 < len(clean_line) < 120
                    and HEADING_REGEX.match(clean_line)
                    and not clean_line.endswith((".", ",", ";"))
                ):
                    # Process accumulated lines under previous heading
                    if current_section_lines:
                        sec_text = "\n".join(current_section_lines).strip()
                        sub_chunks = split_text_recursive(sec_text, chunk_size, chunk_overlap)
                        for sc in sub_chunks:
                            chunk = self._build_chunk(
                                chunk_index=chunk_idx,
                                chunk_text=sc,
                                document_id=extraction_result.document_id,
                                filename=extraction_result.filename,
                                file_type="pdf",
                                page_number=page_pno,
                                section_title=section_tracker.current_section,
                                section_hierarchy=section_tracker.hierarchy,
                                source_unit_indices=[unit.unit_index],
                                source_unit_type="page",
                                metadata={"page_number": page_pno},
                            )
                            chunks.append(chunk)
                            chunk_idx += 1
                        current_section_lines = []

                    # Update section hierarchy for newly encountered heading
                    h_level = section_tracker.detect_level(clean_line)
                    section_tracker.update(clean_line, h_level)

                current_section_lines.append(line)

            # Flush remaining lines on page
            if current_section_lines:
                sec_text = "\n".join(current_section_lines).strip()
                sub_chunks = split_text_recursive(sec_text, chunk_size, chunk_overlap)
                for sc in sub_chunks:
                    chunk = self._build_chunk(
                        chunk_index=chunk_idx,
                        chunk_text=sc,
                        document_id=extraction_result.document_id,
                        filename=extraction_result.filename,
                        file_type="pdf",
                        page_number=page_pno,
                        section_title=section_tracker.current_section,
                        section_hierarchy=section_tracker.hierarchy,
                        source_unit_indices=[unit.unit_index],
                        source_unit_type="page",
                        metadata={"page_number": page_pno},
                    )
                    chunks.append(chunk)
                    chunk_idx += 1

        return chunks

    def _chunk_docx(
        self,
        extraction_result: DocumentExtractionResult,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[DocumentChunk]:
        """
        Chunks DOCX content preserving paragraph and table order.
        Keeps page_number strictly None. Splits large tables repeating headers.
        Prevents bleeding across unrelated section boundaries.
        """
        chunks: list[DocumentChunk] = []
        chunk_idx = 0
        section_tracker = SectionHierarchyTracker()

        accumulated_texts: list[str] = []
        accumulated_indices: list[int] = []

        def flush_accumulator() -> None:
            nonlocal chunk_idx, accumulated_texts, accumulated_indices
            if not accumulated_texts:
                return

            merged_text = "\n\n".join(accumulated_texts).strip()
            sub_chunks = split_text_recursive(merged_text, chunk_size, chunk_overlap)
            for sc in sub_chunks:
                chunk = self._build_chunk(
                    chunk_index=chunk_idx,
                    chunk_text=sc,
                    document_id=extraction_result.document_id,
                    filename=extraction_result.filename,
                    file_type="docx",
                    page_number=None,  # Strictly None for DOCX
                    section_title=section_tracker.current_section,
                    section_hierarchy=section_tracker.hierarchy,
                    source_unit_indices=list(accumulated_indices),
                    source_unit_type="paragraph" if len(accumulated_indices) == 1 else "composite",
                )
                chunks.append(chunk)
                chunk_idx += 1

            accumulated_texts = []
            accumulated_indices = []

        for unit in extraction_result.pages:
            if unit.is_empty or not unit.text.strip():
                continue

            # Update section tracker if unit has an explicit section title
            if unit.section_title and not section_tracker.current_section:
                level = section_tracker.detect_level(unit.section_title)
                section_tracker.update(unit.section_title, level)

            if unit.unit_type == "heading":
                # Flush previous section content before beginning new section
                flush_accumulator()
                style = unit.metadata.get("style", "")
                level = section_tracker.detect_level(unit.text, style)
                section_tracker.update(unit.text, level)
                accumulated_texts.append(f"## {unit.text.strip()}")
                accumulated_indices.append(unit.unit_index)

            elif unit.unit_type == "table":
                # Flush pending paragraphs before emitting table
                flush_accumulator()
                table_parts = TableSplitter.split_table_unit(unit, chunk_size, chunk_overlap)
                for part in table_parts:
                    meta = dict(part.get("metadata", {}))
                    chunk = self._build_chunk(
                        chunk_index=chunk_idx,
                        chunk_text=part["text"],
                        document_id=extraction_result.document_id,
                        filename=extraction_result.filename,
                        file_type="docx",
                        page_number=None,  # Strictly None for DOCX
                        section_title=section_tracker.current_section,
                        section_hierarchy=section_tracker.hierarchy,
                        source_unit_indices=[unit.unit_index],
                        source_unit_type="table",
                        metadata=meta,
                    )
                    chunks.append(chunk)
                    chunk_idx += 1

            else:
                # Paragraph unit: accumulate within current section
                para_text = unit.text.strip()
                current_len = sum(len(t) for t in accumulated_texts) + (
                    2 * (len(accumulated_texts) - 1) if accumulated_texts else 0
                )
                projected_len = current_len + (2 if accumulated_texts else 0) + len(para_text)

                if accumulated_texts and projected_len > chunk_size:
                    # Flush current accumulator
                    flush_accumulator()

                    # If paragraph itself is oversized, split it directly
                    if len(para_text) > chunk_size:
                        sub_chunks = split_text_recursive(para_text, chunk_size, chunk_overlap)
                        for sc in sub_chunks:
                            chunk = self._build_chunk(
                                chunk_index=chunk_idx,
                                chunk_text=sc,
                                document_id=extraction_result.document_id,
                                filename=extraction_result.filename,
                                file_type="docx",
                                page_number=None,
                                section_title=section_tracker.current_section,
                                section_hierarchy=section_tracker.hierarchy,
                                source_unit_indices=[unit.unit_index],
                                source_unit_type="paragraph",
                            )
                            chunks.append(chunk)
                            chunk_idx += 1
                    else:
                        accumulated_texts.append(para_text)
                        accumulated_indices.append(unit.unit_index)
                else:
                    accumulated_texts.append(para_text)
                    accumulated_indices.append(unit.unit_index)

        flush_accumulator()
        return chunks

    def _chunk_txt(
        self,
        extraction_result: DocumentExtractionResult,
        chunk_size: int,
        chunk_overlap: int,
    ) -> list[DocumentChunk]:
        """
        Chunks TXT content preserving logical text blocks and order.
        Keeps page_number strictly None.
        """
        chunks: list[DocumentChunk] = []
        chunk_idx = 0
        section_tracker = SectionHierarchyTracker()

        accumulated_texts: list[str] = []
        accumulated_indices: list[int] = []

        def flush_accumulator() -> None:
            nonlocal chunk_idx, accumulated_texts, accumulated_indices
            if not accumulated_texts:
                return

            merged_text = "\n\n".join(accumulated_texts).strip()
            sub_chunks = split_text_recursive(merged_text, chunk_size, chunk_overlap)
            for sc in sub_chunks:
                chunk = self._build_chunk(
                    chunk_index=chunk_idx,
                    chunk_text=sc,
                    document_id=extraction_result.document_id,
                    filename=extraction_result.filename,
                    file_type="txt",
                    page_number=None,  # Strictly None for TXT
                    section_title=section_tracker.current_section,
                    section_hierarchy=section_tracker.hierarchy,
                    source_unit_indices=list(accumulated_indices),
                    source_unit_type="text_block" if len(accumulated_indices) == 1 else "composite",
                )
                chunks.append(chunk)
                chunk_idx += 1

            accumulated_texts = []
            accumulated_indices = []

        for unit in extraction_result.pages:
            if unit.is_empty or not unit.text.strip():
                continue

            # Update section tracker if unit has an explicit section title
            if unit.section_title and not section_tracker.current_section:
                level = section_tracker.detect_level(unit.section_title)
                section_tracker.update(unit.section_title, level)

            if unit.unit_type == "heading":
                flush_accumulator()
                level = section_tracker.detect_level(unit.text)
                section_tracker.update(unit.text, level)
                accumulated_texts.append(unit.text.strip())
                accumulated_indices.append(unit.unit_index)

            else:
                block_text = unit.text.strip()
                current_len = sum(len(t) for t in accumulated_texts) + (
                    2 * (len(accumulated_texts) - 1) if accumulated_texts else 0
                )
                projected_len = current_len + (2 if accumulated_texts else 0) + len(block_text)

                if accumulated_texts and projected_len > chunk_size:
                    flush_accumulator()
                    if len(block_text) > chunk_size:
                        sub_chunks = split_text_recursive(block_text, chunk_size, chunk_overlap)
                        for sc in sub_chunks:
                            chunk = self._build_chunk(
                                chunk_index=chunk_idx,
                                chunk_text=sc,
                                document_id=extraction_result.document_id,
                                filename=extraction_result.filename,
                                file_type="txt",
                                page_number=None,
                                section_title=section_tracker.current_section,
                                section_hierarchy=section_tracker.hierarchy,
                                source_unit_indices=[unit.unit_index],
                                source_unit_type="text_block",
                            )
                            chunks.append(chunk)
                            chunk_idx += 1
                    else:
                        accumulated_texts.append(block_text)
                        accumulated_indices.append(unit.unit_index)
                else:
                    accumulated_texts.append(block_text)
                    accumulated_indices.append(unit.unit_index)

        flush_accumulator()
        return chunks

    def _build_chunk(
        self,
        chunk_index: int,
        chunk_text: str,
        document_id: Optional[uuid.UUID],
        filename: str,
        file_type: str,
        page_number: Optional[int],
        section_title: Optional[str],
        section_hierarchy: list[str],
        source_unit_indices: list[int],
        source_unit_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> DocumentChunk:
        """Constructs a standardized DocumentChunk instance with calculated counts and context."""
        char_count = len(chunk_text)
        token_count = max(1, round(char_count / 4))

        meta = dict(metadata or {})
        meta["character_count"] = char_count
        meta["token_count"] = token_count
        if section_hierarchy:
            meta["section_breadcrumb"] = " > ".join(section_hierarchy)

        return DocumentChunk(
            chunk_id=uuid.uuid4(),
            document_id=document_id,
            chunk_index=chunk_index,
            chunk_text=chunk_text,
            character_count=char_count,
            token_count=token_count,
            page_number=page_number,
            section_title=section_title,
            section_hierarchy=list(section_hierarchy),
            source_unit_indices=source_unit_indices,
            source_unit_type=source_unit_type,
            filename=filename,
            file_type=file_type,
            metadata=meta,
        )


def get_document_chunker() -> DocumentChunkerService:
    """FastAPI dependency provider returning configured DocumentChunkerService."""
    return DocumentChunkerService()
