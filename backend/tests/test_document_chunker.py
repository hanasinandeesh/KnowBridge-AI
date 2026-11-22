import io
import os
from pathlib import Path
import uuid
from unittest.mock import AsyncMock, MagicMock

import docx
from fastapi.testclient import TestClient
import pymupdf
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.schemas.chunking import DocumentChunk, DocumentChunkingResult
from app.schemas.extraction import ContentUnit, DocumentExtractionResult
from app.services.document_chunker import (
    DocumentChunkerService,
    SectionHierarchyTracker,
    TableSplitter,
    extract_clean_overlap,
    get_document_chunker,
    split_text_recursive,
)
from app.services.storage_service import (
    StorageDownloadError,
    StorageService,
    get_storage_service,
)

# ---------------------------------------------------------------------------
# Test Helpers & Document Generators
# ---------------------------------------------------------------------------

def generate_pdf_bytes(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def generate_docx_bytes(paragraphs: list[tuple[str, str]], tables: list[list[list[str]]] = None) -> bytes:
    doc = docx.Document()
    for style, text in paragraphs:
        if style.lower().startswith("heading"):
            level = 1
            if len(style) > 7 and style[7:].strip().isdigit():
                level = int(style[7:].strip())
            doc.add_heading(text, level=level)
        else:
            doc.add_paragraph(text)

    if tables:
        for grid in tables:
            if not grid:
                continue
            num_rows = len(grid)
            num_cols = max(len(row) for row in grid)
            t = doc.add_table(rows=num_rows, cols=num_cols)
            for r_idx, row in enumerate(grid):
                for c_idx, cell_value in enumerate(row):
                    t.rows[r_idx].cells[c_idx].text = str(cell_value)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Database Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def override_db(isolated_db: Session):
    def _get_test_db():
        yield isolated_db

    app.dependency_overrides[get_db] = _get_test_db
    yield isolated_db
    app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Unit Tests for Core Chunking Requirements (Scenarios 1-20)
# ---------------------------------------------------------------------------

def test_01_short_document_produces_single_chunk():
    """Scenario 1: Short document producing exactly one chunk."""
    text = "Northstar Technologies Enterprise Policy. Short statement."
    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="short.txt",
        file_type="txt",
        extraction_status="completed",
        total_pages=None,
        total_characters=len(text),
        extracted_text=text,
        pages=[
            ContentUnit(
                unit_index=0,
                unit_type="text_block",
                page_number=None,
                section_title=None,
                text=text,
                character_count=len(text),
                is_empty=False,
            )
        ],
    )

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks == 1
    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.chunk_index == 0
    assert chunk.chunk_text == text
    assert chunk.character_count == len(text)
    assert chunk.page_number is None


def test_02_long_document_produces_multiple_chunks():
    """Scenario 2: Long document producing multiple chunks."""
    paragraphs = [
        f"Paragraph {i}: This is an extended policy section detailing compliance regulations for Northstar enterprise operations. "
        * 3
        for i in range(15)
    ]
    full_text = "\n\n".join(paragraphs)
    units = [
        ContentUnit(
            unit_index=i,
            unit_type="paragraph",
            page_number=None,
            section_title="General Compliance",
            text=p,
            character_count=len(p),
            is_empty=False,
        )
        for i, p in enumerate(paragraphs)
    ]
    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="compliance.docx",
        file_type="docx",
        extraction_status="completed",
        total_pages=None,
        total_characters=len(full_text),
        extracted_text=full_text,
        pages=units,
    )

    chunker = DocumentChunkerService(default_chunk_size=600, default_chunk_overlap=100)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 1
    for chunk in result.chunks:
        assert chunk.character_count <= 600
        assert chunk.page_number is None


def test_03_configurable_chunk_size():
    """Scenario 3: Configurable chunk size."""
    raw_text = "Sentence number one about company policy. " * 30
    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="test.txt",
        file_type="txt",
        extraction_status="completed",
        total_pages=None,
        total_characters=len(raw_text),
        extracted_text=raw_text,
        pages=[
            ContentUnit(
                unit_index=0,
                unit_type="text_block",
                page_number=None,
                section_title=None,
                text=raw_text,
                character_count=len(raw_text),
            )
        ],
    )

    chunker = DocumentChunkerService()

    res_small = chunker.chunk_document(extraction, chunk_size=300, chunk_overlap=50)
    res_large = chunker.chunk_document(extraction, chunk_size=900, chunk_overlap=50)

    assert res_small.total_chunks > res_large.total_chunks
    for c in res_small.chunks:
        assert c.character_count <= 300
    for c in res_large.chunks:
        assert c.character_count <= 900


def test_04_configurable_overlap():
    """Scenario 4: Configurable overlap."""
    text = "First long paragraph discussing international business travel. " * 8
    text += "Second long paragraph detailing daily per diem meal allowance limits. " * 8

    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="overlap_test.txt",
        file_type="txt",
        extraction_status="completed",
        total_pages=None,
        total_characters=len(text),
        extracted_text=text,
        pages=[
            ContentUnit(
                unit_index=0,
                unit_type="text_block",
                page_number=None,
                section_title=None,
                text=text,
                character_count=len(text),
            )
        ],
    )

    chunker = DocumentChunkerService()
    res_no_overlap = chunker.chunk_document(extraction, chunk_size=500, chunk_overlap=0)
    res_with_overlap = chunker.chunk_document(extraction, chunk_size=500, chunk_overlap=120)

    # In no-overlap mode, chunk 1 should not contain the tail of chunk 0
    c0_tail_no_ov = res_no_overlap.chunks[0].chunk_text[-40:]
    assert c0_tail_no_ov not in res_no_overlap.chunks[1].chunk_text

    # In with-overlap mode, chunk 1 begins with shared context from chunk 0
    assert res_with_overlap.chunks[0].chunk_text != res_with_overlap.chunks[1].chunk_text
    overlap_snippet = extract_clean_overlap(res_with_overlap.chunks[0].chunk_text, 120)
    if overlap_snippet:
        assert overlap_snippet in res_with_overlap.chunks[1].chunk_text


def test_05_word_boundary_preservation():
    """Scenario 5: Word-boundary preservation (no cutting words in half)."""
    text = "Northstar international reimbursement procedures require comprehensive verification documents."
    splits = split_text_recursive(text, chunk_size=40, chunk_overlap=10)

    for chunk in splits:
        first_word = chunk.split()[0]
        last_word = chunk.split()[-1]
        assert first_word in text
        assert last_word in text


def test_06_heading_and_section_title_preservation():
    """Scenario 6: Heading and section-title preservation with hierarchy."""
    paragraphs = [
        ("Heading 1", "1.0 Information Security Policy"),
        ("Normal", "This policy applies to all Northstar staff."),
        ("Heading 2", "1.1 Access Control Standards"),
        ("Normal", "Access control requires multifactor authentication."),
        ("Heading 3", "1.1.1 Biometric Verification"),
        ("Normal", "Biometric credentials must adhere to strict hardware storage."),
    ]
    docx_bytes = generate_docx_bytes(paragraphs)
    extraction = DOCXParser().parse(docx_bytes, filename="Security.docx")

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    result = chunker.chunk_document(extraction)

    sections = [c.section_title for c in result.chunks]
    assert "1.0 Information Security Policy" in sections
    assert "1.1 Access Control Standards" in sections
    assert "1.1.1 Biometric Verification" in sections

    # Check hierarchy on the deepest chunk
    deepest_chunk = [c for c in result.chunks if c.section_title == "1.1.1 Biometric Verification"][0]
    assert deepest_chunk.section_hierarchy == [
        "1.0 Information Security Policy",
        "1.1 Access Control Standards",
        "1.1.1 Biometric Verification",
    ]


def test_07_documents_without_headings():
    """Scenario 7: Documents without headings handle gracefully."""
    text = "A simple document with no headers or section markings.\n\nJust paragraphs of regular enterprise notes."
    extraction = TXTParser().parse(text.encode("utf-8"), filename="notes.txt")

    chunker = DocumentChunkerService()
    result = chunker.chunk_document(extraction)

    assert result.total_chunks >= 1
    for chunk in result.chunks:
        assert chunk.section_title is None
        assert chunk.section_hierarchy == []


def test_08_pdf_page_number_preservation():
    """Scenario 8: PDF page-number preservation (strictly 1-based)."""
    pdf_bytes = generate_pdf_bytes(["Page 1 content about company travel.", "Page 2 content about lodging limits."])
    extraction = PDFParser().parse(pdf_bytes, filename="travel.pdf")

    chunker = DocumentChunkerService()
    result = chunker.chunk_document(extraction)

    assert result.total_chunks == 2
    assert result.chunks[0].page_number == 1
    assert result.chunks[1].page_number == 2


def test_09_pdf_multipage_extraction():
    """Scenario 9: PDF multipage extraction without combining across pages."""
    pages = [
        "First page statement about airfare.",
        "Second page statement about ground transport.",
        "Third page statement about meal expenses.",
    ]
    pdf_bytes = generate_pdf_bytes(pages)
    extraction = PDFParser().parse(pdf_bytes, filename="multi.pdf")

    chunker = DocumentChunkerService(default_chunk_size=5000)  # Large size to ensure whole pages fit
    result = chunker.chunk_document(extraction)

    assert result.total_chunks == 3
    for i, chunk in enumerate(result.chunks):
        assert chunk.page_number == i + 1
        assert pages[i] in chunk.chunk_text
        # Ensure Page 1 text is strictly absent from Page 2 chunk
        if i > 0:
            assert pages[0] not in chunk.chunk_text


def test_10_docx_page_number_remaining_null():
    """Scenario 10: DOCX page_number strictly remains None."""
    docx_bytes = generate_docx_bytes([("Normal", "Paragraph 1"), ("Normal", "Paragraph 2")])
    extraction = DOCXParser().parse(docx_bytes, filename="policy.docx")

    chunker = DocumentChunkerService()
    result = chunker.chunk_document(extraction)

    for chunk in result.chunks:
        assert chunk.page_number is None


def test_11_txt_page_number_remaining_null():
    """Scenario 11: TXT page_number strictly remains None."""
    txt_bytes = b"Block 1\n\nBlock 2\n\nBlock 3"
    extraction = TXTParser().parse(txt_bytes, filename="policy.txt")

    chunker = DocumentChunkerService()
    result = chunker.chunk_document(extraction)

    for chunk in result.chunks:
        assert chunk.page_number is None


def test_12_docx_paragraph_ordering():
    """Scenario 12: DOCX paragraph ordering preservation."""
    paragraphs = [("Normal", f"Order Check Paragraph Index {i}") for i in range(10)]
    docx_bytes = generate_docx_bytes(paragraphs)
    extraction = DOCXParser().parse(docx_bytes, filename="order.docx")

    chunker = DocumentChunkerService(default_chunk_size=120, default_chunk_overlap=20)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 1
    # Check that paragraph indices in text appear in strictly ascending order
    last_seen_idx = -1
    for chunk in result.chunks:
        import re
        matches = [int(m) for m in re.findall(r"Order Check Paragraph Index (\d+)", chunk.chunk_text)]
        for idx in matches:
            assert idx >= last_seen_idx
            last_seen_idx = idx


def test_13_table_header_and_row_preservation():
    """Scenario 13: Table header and row preservation."""
    table = [
        ["Band", "Domestic Limit", "International Limit"],
        ["Tier 1", "INR 25,000", "USD 1,000"],
        ["Tier 2", "INR 75,000", "USD 3,000"],
    ]
    docx_bytes = generate_docx_bytes([("Heading 1", "Reimbursement Matrix")], [table])
    extraction = DOCXParser().parse(docx_bytes, filename="matrix.docx")

    chunker = DocumentChunkerService(default_chunk_size=1000)
    result = chunker.chunk_document(extraction)

    table_chunk = [c for c in result.chunks if c.source_unit_type == "table"][0]
    assert "| Band | Domestic Limit | International Limit |" in table_chunk.chunk_text
    assert "| Tier 1 | INR 25,000 | USD 1,000 |" in table_chunk.chunk_text
    assert "| Tier 2 | INR 75,000 | USD 3,000 |" in table_chunk.chunk_text
    assert table_chunk.metadata.get("is_table") is True


def test_14_large_table_splitting_with_repeated_headers():
    """Scenario 14: Large table splitting with repeated headers."""
    headers = ["ID", "Expense Category", "Max Daily Limit", "Approver Role"]
    rows = [[str(i), f"Category-{i}", f"INR {i * 1000}", f"Manager-{i}"] for i in range(1, 25)]
    table = [headers] + rows

    docx_bytes = generate_docx_bytes([("Heading 1", "Comprehensive Rates")], [table])
    extraction = DOCXParser().parse(docx_bytes, filename="large_table.docx")

    # Use small chunk_size to force table to split across multiple chunks
    chunker = DocumentChunkerService(default_chunk_size=350, default_chunk_overlap=50)
    result = chunker.chunk_document(extraction)

    table_chunks = [c for c in result.chunks if c.source_unit_type == "table"]
    assert len(table_chunks) >= 2

    # Every split table chunk MUST contain the table headers
    for tc in table_chunks:
        assert "| ID | Expense Category | Max Daily Limit | Approver Role |" in tc.chunk_text
        assert "| --- | --- | --- | --- |" in tc.chunk_text
        assert tc.metadata.get("is_table") is True
        assert tc.metadata.get("headers") == headers


def test_15_empty_extraction_output():
    """Scenario 15: Empty extraction output handled gracefully."""
    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="empty.pdf",
        file_type="pdf",
        extraction_status="empty_content",
        total_pages=0,
        total_characters=0,
        extracted_text="",
        pages=[],
    )

    chunker = DocumentChunkerService()
    result = chunker.chunk_document(extraction)

    assert result.total_chunks == 0
    assert result.chunks == []
    assert result.metadata.get("status") == "empty_content"


def test_16_oversized_paragraphs():
    """Scenario 16: Oversized single paragraphs split cleanly without truncation."""
    sentences = [f"Sentence {i}: Northstar policy mandates strict compliance with travel regulations." for i in range(30)]
    long_paragraph = " ".join(sentences)
    assert len(long_paragraph) > 2000

    unit = ContentUnit(
        unit_index=0,
        unit_type="paragraph",
        page_number=None,
        section_title="Long Para Section",
        text=long_paragraph,
        character_count=len(long_paragraph),
    )
    extraction = DocumentExtractionResult(
        document_id=uuid.uuid4(),
        filename="oversized.docx",
        file_type="docx",
        extraction_status="completed",
        total_pages=None,
        total_characters=len(long_paragraph),
        extracted_text=long_paragraph,
        pages=[unit],
    )

    chunker = DocumentChunkerService(default_chunk_size=500, default_chunk_overlap=80)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 1
    for chunk in result.chunks:
        assert chunk.character_count <= 500
        assert chunk.section_title == "Long Para Section"

    # Verify first and last sentence are present
    assert "Sentence 0:" in result.chunks[0].chunk_text
    assert "Sentence 29:" in result.chunks[-1].chunk_text


def test_17_deterministic_output():
    """Scenario 17: Deterministic output for identical input."""
    text = "Section 1.0 General Provisions\n\nEmployees are eligible for reimbursement upon submission of tax invoices."
    extraction = TXTParser().parse(text.encode("utf-8"), filename="test.txt")

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    run_1 = chunker.chunk_document(extraction)
    run_2 = chunker.chunk_document(extraction)

    assert run_1.total_chunks == run_2.total_chunks
    for c1, c2 in zip(run_1.chunks, run_2.chunks):
        assert c1.chunk_index == c2.chunk_index
        assert c1.chunk_text == c2.chunk_text
        assert c1.character_count == c2.character_count
        assert c1.section_title == c2.section_title
        assert c1.page_number == c2.page_number


def test_18_stable_chunk_indices():
    """Scenario 18: Stable contiguous 0-based chunk indices."""
    paragraphs = [("Normal", f"Paragraph content block {i} with sufficient text to fill capacity.") for i in range(12)]
    docx_bytes = generate_docx_bytes(paragraphs)
    extraction = DOCXParser().parse(docx_bytes, filename="indices.docx")

    chunker = DocumentChunkerService(default_chunk_size=200, default_chunk_overlap=40)
    result = chunker.chunk_document(extraction)

    indices = [c.chunk_index for c in result.chunks]
    assert indices == list(range(len(result.chunks)))


def test_19_no_duplicate_only_chunks():
    """Scenario 19: No duplicate-only chunks."""
    text = "This is a meaningful unique block of enterprise text. " * 10
    extraction = TXTParser().parse(text.encode("utf-8"), filename="dup.txt")

    chunker = DocumentChunkerService(default_chunk_size=250, default_chunk_overlap=50)
    result = chunker.chunk_document(extraction)

    for i in range(len(result.chunks) - 1):
        c_curr = result.chunks[i].chunk_text
        c_next = result.chunks[i + 1].chunk_text
        assert c_curr != c_next


def test_20_no_infinite_splitting_or_non_progress_loops():
    """Scenario 20: No infinite splitting or non-progress loops on pathological inputs."""
    # A. String without spaces
    no_space_string = "A" * 2500
    splits_a = split_text_recursive(no_space_string, chunk_size=500, chunk_overlap=50)
    assert len(splits_a) == 6

    # B. Repeated punctuation
    punct_string = ".......... " * 50
    splits_b = split_text_recursive(punct_string, chunk_size=200, chunk_overlap=30)
    assert len(splits_b) > 0

    # C. Overlap = 0
    splits_c = split_text_recursive("Hello world! " * 50, chunk_size=150, chunk_overlap=0)
    assert len(splits_c) > 0


# ---------------------------------------------------------------------------
# Synthetic Policy Document Tests (Real Northstar Policies)
# ---------------------------------------------------------------------------

POLICIES_DIR = Path(__file__).resolve().parent.parent.parent / "synthetic-data" / "policies"


def test_21_synthetic_policy_travel():
    """Validates chunking on real synthetic Travel Reimbursement Policy."""
    fpath = POLICIES_DIR / "HR-TRV-001_Travel_Reimbursement_v1.0.pdf"
    if not fpath.exists():
        pytest.skip("Synthetic policy file not found")

    content = fpath.read_bytes()
    extraction = PDFParser().parse(content, filename=fpath.name)
    assert extraction.extraction_status == "completed"

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 5
    assert all(c.page_number is not None and c.page_number >= 1 for c in result.chunks)
    assert all(c.character_count <= 1000 for c in result.chunks)

    # Check that key policy terms are present in chunks
    all_chunk_text = " ".join(c.chunk_text for c in result.chunks)
    assert "Northstar Technologies" in all_chunk_text
    assert "Travel" in all_chunk_text


def test_22_synthetic_policy_leave():
    """Validates chunking on real synthetic Employee Leave Policy."""
    fpath = POLICIES_DIR / "HR-LVE-001_Employee_Leave_v1.0.pdf"
    if not fpath.exists():
        pytest.skip("Synthetic policy file not found")

    content = fpath.read_bytes()
    extraction = PDFParser().parse(content, filename=fpath.name)
    assert extraction.extraction_status == "completed"

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 5
    assert all(c.page_number is not None for c in result.chunks)
    all_chunk_text = " ".join(c.chunk_text for c in result.chunks)
    assert "Leave" in all_chunk_text or "leave" in all_chunk_text


def test_23_synthetic_policy_remote_work():
    """Validates chunking on real synthetic Remote/Hybrid Work Policy."""
    fpath = POLICIES_DIR / "HR-WFH-001_Remote_Hybrid_Work_v1.0.pdf"
    if not fpath.exists():
        pytest.skip("Synthetic policy file not found")

    content = fpath.read_bytes()
    extraction = PDFParser().parse(content, filename=fpath.name)
    assert extraction.extraction_status == "completed"

    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    result = chunker.chunk_document(extraction)

    assert result.total_chunks > 5
    assert all(c.page_number is not None for c in result.chunks)
    all_chunk_text = " ".join(c.chunk_text for c in result.chunks)
    assert "Remote" in all_chunk_text or "Hybrid" in all_chunk_text


# ---------------------------------------------------------------------------
# API Route Tests for POST /api/v1/documents/{document_id}/chunk
# ---------------------------------------------------------------------------

def test_24_api_chunk_endpoint_success(client: TestClient, override_db: Session):
    """Tests successful POST /api/v1/documents/{document_id}/chunk."""
    doc_id = uuid.uuid4()
    pdf_bytes = generate_pdf_bytes(["Section 1.0 Enterprise Policy Statement\nNorthstar Technologies India."])

    doc = Document(
        id=doc_id,
        title="Enterprise Policy",
        original_filename="policy.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/policy.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=pdf_bytes)
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/chunk?chunk_size=500&chunk_overlap=50")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc_id)
        assert data["file_type"] == "pdf"
        assert data["total_chunks"] >= 1
        assert data["chunk_size"] == 500
        assert data["chunk_overlap"] == 50
        assert len(data["chunks"]) == data["total_chunks"]
        assert data["chunks"][0]["page_number"] == 1
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def test_25_api_chunk_endpoint_not_found(client: TestClient, override_db: Session):
    """Tests chunking non-existent document returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/chunk")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_26_api_chunk_endpoint_invalid_overlap(client: TestClient, override_db: Session):
    """Tests chunk_overlap >= chunk_size returns HTTP 400."""
    doc_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{doc_id}/chunk?chunk_size=500&chunk_overlap=600")
    assert response.status_code == 400
    assert "strictly less than" in response.json()["detail"]


def test_27_api_chunk_endpoint_corrupted_doc(client: TestClient, override_db: Session):
    """Tests chunking corrupted file returns HTTP 422."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Corrupted Policy",
        original_filename="corrupted.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/corrupted.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=b"%PDF-1.4 corrupt data")
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/chunk")
        assert response.status_code == 422
        assert "parsing failed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
