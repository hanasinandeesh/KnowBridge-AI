import codecs
import io
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import docx
import pytest
import pymupdf
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.parsers.base import (
    CorruptedDocumentError,
    EncryptedDocumentError,
    UnsupportedDocumentError,
)
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.schemas.extraction import DocumentExtractionResult
from app.services.document_extractor import (
    DocumentExtractorService,
    DocumentNotFoundError,
    get_document_extractor,
)
from app.services.storage_service import (
    StorageConfigurationError,
    StorageDownloadError,
    StorageService,
    get_storage_service,
)


# ---------------------------------------------------------------------------
# Synthetic Document Byte Generators
# ---------------------------------------------------------------------------

def generate_multipage_pdf_bytes(page_texts: list[str]) -> bytes:
    """Generates an in-memory RFC-compliant multi-page PDF using PyMuPDF."""
    doc = pymupdf.open()
    for text in page_texts:
        page = doc.new_page()
        page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def generate_scanned_pdf_bytes(page_count: int = 2) -> bytes:
    """Generates a valid PDF with blank pages (no digital text layer, simulating scanned images)."""
    doc = pymupdf.open()
    for _ in range(page_count):
        doc.new_page()
    data = doc.tobytes()
    doc.close()
    return data


def generate_encrypted_pdf_bytes(password: str = "secret123") -> bytes:
    """Generates a password-protected PDF using PyMuPDF."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 72), "Confidential corporate policy statement.")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw=password)
    doc.close()
    return data


def generate_docx_bytes(paragraphs: list[tuple[str, str]], tables: list[list[list[str]]] = None) -> bytes:
    """
    Generates a valid OpenXML DOCX archive with structured paragraphs and tables.
    paragraphs: list of (style_name, text)
    tables: list of 2D grids (rows of cells)
    """
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


def generate_txt_bytes(text: str) -> bytes:
    """Generates standard UTF-8 text bytes."""
    return text.encode("utf-8")


def generate_txt_with_bom_bytes(text: str) -> bytes:
    """Generates UTF-8 text bytes prefixed with UTF-8 BOM."""
    return codecs.BOM_UTF8 + text.encode("utf-8")


# ---------------------------------------------------------------------------
# Test Database Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db_session():
    """Isolated SQLite in-memory database session."""
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
def override_db(isolated_db_session: Session):
    """FastAPI get_db override fixture."""
    def _get_isolated_db():
        yield isolated_db_session

    app.dependency_overrides[get_db] = _get_isolated_db
    yield isolated_db_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_storage():
    """Mock StorageService configured for isolated extraction testing."""
    mock = MagicMock(spec=StorageService)
    mock.is_configured = True
    mock.bucket_name = "knowledge-documents"
    mock.supabase_url = "https://mockproject.supabase.co"
    mock.service_role_key = "mock-service-role-key"

    # Default download raises not found unless customized
    async def _mock_download(object_path):
        return b"%PDF-1.4 mock content"

    def _mock_download_sync(object_path):
        return b"%PDF-1.4 mock content"

    mock.download_file = AsyncMock(side_effect=_mock_download)
    mock.download_file_sync = MagicMock(side_effect=_mock_download_sync)

    app.dependency_overrides[get_storage_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_storage_service, None)


# ---------------------------------------------------------------------------
# Requirement 8 Tests: Scenarios 1 - 12
# ---------------------------------------------------------------------------

def test_01_multipage_pdf_extraction():
    """
    Scenario 1: Multi-page PDF extraction.
    Validates page-by-page extraction, 1-based page numbering,
    page boundaries, and character counting.
    """
    page_texts = [
        "1. Document Control and Purpose\nThis section defines corporate travel standards.",
        "5.0 Airfare Booking Requirements\nEconomy class mandatory for all flights under 6 hours.",
        "7.0 Daily Meal Per Diem\nMaximum INR 1,500 daily reimbursement for domestic travel.",
    ]
    pdf_bytes = generate_multipage_pdf_bytes(page_texts)
    parser = PDFParser()

    result = parser.parse(pdf_bytes, filename="Travel_Policy.pdf")

    assert result.extraction_status == "completed"
    assert result.total_pages == 3
    assert result.file_type == "pdf"
    assert len(result.pages) == 3

    # Validate exact 1-based page numbering
    for i, unit in enumerate(result.pages):
        assert unit.page_number == i + 1
        assert unit.unit_type == "page"
        assert unit.is_empty is False
        assert unit.character_count > 0
        assert page_texts[i] in unit.text

    # Validate page boundaries in full extracted text
    assert "--- [Page 1] ---" in result.extracted_text
    assert "--- [Page 2] ---" in result.extracted_text
    assert "--- [Page 3] ---" in result.extracted_text
    assert result.total_characters == sum(len(u.text) for u in result.pages)


def test_02_docx_paragraph_extraction():
    """
    Scenario 2: DOCX paragraph extraction.
    Validates paragraphs extracted in document order, headings preserved,
    and page numbers strictly None.
    """
    paragraphs = [
        ("Heading 1", "1.0 Enterprise Information Security Policy"),
        ("Normal", "This policy outlines access controls and data protection protocols."),
        ("Heading 2", "1.1 Password Complexity Standards"),
        ("Normal", "All passwords must be at least 14 characters with mixed character sets."),
    ]
    docx_bytes = generate_docx_bytes(paragraphs)
    parser = DOCXParser()

    result = parser.parse(docx_bytes, filename="Security_Policy.docx")

    assert result.extraction_status == "completed"
    assert result.file_type == "docx"
    assert result.total_pages is None  # DOCX pagination is rendering-dependent
    assert len(result.pages) == 4

    # Verify all page_number values are strictly None
    for unit in result.pages:
        assert unit.page_number is None

    # Check headings and section assignments
    assert result.pages[0].unit_type == "heading"
    assert result.pages[0].section_title == "1.0 Enterprise Information Security Policy"

    assert result.pages[1].unit_type == "paragraph"
    assert result.pages[1].section_title == "1.0 Enterprise Information Security Policy"

    assert result.pages[2].unit_type == "heading"
    assert result.pages[2].section_title == "1.1 Password Complexity Standards"

    assert result.pages[3].unit_type == "paragraph"
    assert result.pages[3].section_title == "1.1 Password Complexity Standards"


def test_03_docx_table_extraction():
    """
    Scenario 3: DOCX table extraction.
    Validates structured table extraction in exact document order with Markdown formatting.
    """
    paragraphs = [
        ("Heading 1", "Approval Matrix"),
        ("Normal", "Below are the required approval tiers for expenditure."),
    ]
    tables = [
        [
            ["Band", "Monetary Limit", "Approver Role"],
            ["Tier 1", "<= INR 25,000", "Direct Manager"],
            ["Tier 2", "<= INR 1,00,000", "Department Head"],
            ["Tier 3", "> INR 1,00,000", "VP and Finance Controller"],
        ]
    ]
    docx_bytes = generate_docx_bytes(paragraphs, tables)
    parser = DOCXParser()

    result = parser.parse(docx_bytes, filename="Expense_Matrix.docx")

    assert result.extraction_status == "completed"
    assert result.total_pages is None
    # 2 paragraphs + 1 table
    assert len(result.pages) == 3

    table_unit = result.pages[2]
    assert table_unit.unit_type == "table"
    assert table_unit.page_number is None
    assert "| Band | Monetary Limit | Approver Role |" in table_unit.text
    assert "| Tier 1 | <= INR 25,000 | Direct Manager |" in table_unit.text
    assert table_unit.metadata["num_rows"] == 4
    assert table_unit.metadata["num_columns"] == 3
    assert table_unit.metadata["headers"] == ["Band", "Monetary Limit", "Approver Role"]


def test_04_txt_extraction():
    """
    Scenario 4: TXT extraction.
    Validates UTF-8 text extraction, line break preservation,
    paragraph boundary detection, and page numbers strictly None.
    """
    text_content = (
        "1.0 CODE OF BUSINESS CONDUCT\n"
        "----------------------------\n\n"
        "All employees are expected to uphold the highest ethical standards.\n"
        "Violations will result in disciplinary proceedings.\n\n"
        "2.0 CONFLICTS OF INTEREST\n"
        "-------------------------\n\n"
        "Employees must disclose any external business interests annually."
    )
    txt_bytes = generate_txt_bytes(text_content)
    parser = TXTParser()

    result = parser.parse(txt_bytes, filename="Code_of_Conduct.txt")

    assert result.extraction_status == "completed"
    assert result.file_type == "txt"
    assert result.total_pages is None  # Plain text has no pages
    assert len(result.pages) > 0

    for unit in result.pages:
        assert unit.page_number is None

    # Verify line breaks within paragraphs are preserved
    assert "\n" in result.pages[1].text
    assert "Violations will result in disciplinary proceedings." in result.pages[1].text


def test_05_utf8_bom_handling():
    """
    Scenario 5: UTF-8 BOM handling.
    Validates that UTF-8 files with Byte Order Mark (0xEF, 0xBB, 0xBF)
    are decoded cleanly without leaving BOM artifacts in extracted text.
    """
    raw_text = "KnowBridge AI — Enterprise Travel and Expense Policy\nSection 1: Scope"
    bom_bytes = generate_txt_with_bom_bytes(raw_text)
    parser = TXTParser()

    result = parser.parse(bom_bytes, filename="Policy_BOM.txt")

    assert result.extraction_status == "completed"
    assert result.metadata["has_bom"] is True
    assert result.metadata["encoding"] == "utf-8-sig"
    assert not result.extracted_text.startswith("\ufeff")
    assert result.extracted_text.startswith("KnowBridge AI")


def test_06_empty_pdf():
    """
    Scenario 6: Empty PDF handling.
    0-byte PDF raises CorruptedDocumentError;
    0-page PDF returns extraction_status='empty_content'.
    """
    parser = PDFParser()

    # 0-byte PDF
    with pytest.raises(CorruptedDocumentError) as exc_info:
        parser.parse(b"", filename="empty_file.pdf")
    assert "empty" in str(exc_info.value).lower()

    # Valid RFC PDF container with 0 pages in catalog
    zero_page_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
        b"xref\n0 3\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n"
        b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n110\n%%EOF\n"
    )

    result = parser.parse(zero_page_pdf, filename="zero_pages.pdf")
    assert result.extraction_status == "empty_content"
    assert result.total_pages == 0
    assert result.total_characters == 0
    assert len(result.pages) == 0


def test_07_scanned_pdf_no_text_layer():
    """
    Scenario 7: Scanned PDF with no text layer.
    Validates detection of blank/scanned pages without claiming OCR support.
    """
    scanned_bytes = generate_scanned_pdf_bytes(page_count=3)
    parser = PDFParser()

    result = parser.parse(scanned_bytes, filename="Scanned_Invoice.pdf")

    assert result.extraction_status == "empty_content"
    assert result.total_pages == 3
    assert result.total_characters == 0
    assert result.metadata["scanned_only"] is True
    assert result.metadata["ocr_supported"] is False
    assert "OCR is not supported" in result.metadata["note"]

    # Each page unit is marked is_empty=True with correct 1-based page number
    for i, unit in enumerate(result.pages):
        assert unit.page_number == i + 1
        assert unit.is_empty is True
        assert unit.character_count == 0


def test_08_corrupt_pdf():
    """
    Scenario 8: Corrupt PDF.
    Validates that truncated or random binary bytes raise CorruptedDocumentError.
    """
    corrupt_bytes = b"%PDF-1.4\nCorrupt truncated binary junk\x00\x01\x02"
    parser = PDFParser()

    with pytest.raises(CorruptedDocumentError) as exc_info:
        parser.parse(corrupt_bytes, filename="corrupt.pdf")
    assert "corrupted" in str(exc_info.value).lower() or "invalid" in str(exc_info.value).lower()


def test_09_malformed_docx():
    """
    Scenario 9: Malformed DOCX.
    Validates that invalid ZIP archives or missing XML structures raise CorruptedDocumentError.
    """
    malformed_bytes = b"PK\x03\x04corrupted_payload_that_is_not_a_valid_zip"
    parser = DOCXParser()

    with pytest.raises(CorruptedDocumentError) as exc_info:
        parser.parse(malformed_bytes, filename="broken.docx")
    assert "corrupted" in str(exc_info.value).lower() or "malformed" in str(exc_info.value).lower()


def test_10_invalid_txt_encoding():
    """
    Scenario 10: Invalid TXT encoding.
    Validates that binary data or invalid byte sequences raise CorruptedDocumentError.
    """
    # Null bytes in plain text (binary masquerading as txt)
    null_bytes_txt = b"Valid ASCII prefix\x00Binary payload\x01\x02"
    parser = TXTParser()

    with pytest.raises(CorruptedDocumentError) as exc_info:
        parser.parse(null_bytes_txt, filename="binary.txt")
    assert "null bytes" in str(exc_info.value).lower()

    # Non-decodable byte sequence
    undecodable = b"\xff\xfe\x99\xaa\xbb\xcc"
    with pytest.raises(CorruptedDocumentError) as exc_info:
        parser.parse(undecodable, filename="invalid_charset.txt")
    assert "invalid text encoding" in str(exc_info.value).lower()


def test_11_supabase_storage_download_failure(override_db: Session):
    """
    Scenario 11: Supabase Storage download failure.
    Validates that storage download errors are caught and surfaced as StorageDownloadError.
    """
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Test Document",
        original_filename="test.pdf",
        file_type="pdf",
        storage_path="documents/test/test.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    mock_storage_service = MagicMock(spec=StorageService)
    mock_storage_service.download_file = AsyncMock(
        side_effect=StorageDownloadError("Storage connection timed out.")
    )

    extractor = DocumentExtractorService(storage_service=mock_storage_service)

    with pytest.raises(StorageDownloadError) as exc_info:
        import anyio
        anyio.run(extractor.extract_document, doc_id, override_db, mock_storage_service)

    assert "timed out" in str(exc_info.value).lower()


def test_12_preservation_of_page_numbers_and_logical_boundaries():
    """
    Scenario 12: Preservation of page numbers and logical content boundaries.
    - PDF: strictly 1-based page numbers (1, 2, 3...)
    - DOCX: page_number is strictly None, logical units (paragraph, heading, table) preserved
    - TXT: page_number is strictly None, logical text blocks and line breaks preserved
    """
    # PDF
    pdf_bytes = generate_multipage_pdf_bytes(["First page", "Second page"])
    pdf_res = PDFParser().parse(pdf_bytes, "test.pdf")
    assert pdf_res.total_pages == 2
    assert [u.page_number for u in pdf_res.pages] == [1, 2]

    # DOCX
    docx_bytes = generate_docx_bytes([("Normal", "Para 1"), ("Normal", "Para 2")])
    docx_res = DOCXParser().parse(docx_bytes, "test.docx")
    assert docx_res.total_pages is None
    assert all(u.page_number is None for u in docx_res.pages)

    # TXT
    txt_bytes = generate_txt_bytes("Block 1\nLine 2\n\nBlock 2\nLine 4")
    txt_res = TXTParser().parse(txt_bytes, "test.txt")
    assert txt_res.total_pages is None
    assert all(u.page_number is None for u in txt_res.pages)


def test_13_password_protected_pdf_raises_encrypted_document_error():
    """
    Validates that password-protected PDFs raise EncryptedDocumentError.
    """
    enc_pdf = generate_encrypted_pdf_bytes("strong_password")
    parser = PDFParser()

    with pytest.raises(EncryptedDocumentError) as exc_info:
        parser.parse(enc_pdf, filename="secret.pdf")
    assert "password-protected" in str(exc_info.value).lower()


def test_14_unsupported_document_format_raises_error():
    """
    Validates that unsupported formats raise UnsupportedDocumentError.
    """
    extractor = DocumentExtractorService()
    with pytest.raises(UnsupportedDocumentError) as exc_info:
        extractor.extract_from_bytes(b"some content", filename="archive.zip", file_type="zip")
    assert "unsupported" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# API Route Tests for POST /api/v1/documents/{document_id}/extract
# ---------------------------------------------------------------------------

def test_api_extract_document_pdf_success(client: TestClient, override_db: Session):
    """
    Tests successful API text extraction for an uploaded PDF document.
    """
    doc_id = uuid.uuid4()
    pdf_bytes = generate_multipage_pdf_bytes(["KnowBridge AI Policy Text on Page 1"])
    storage_path = f"documents/{doc_id}/policy.pdf"

    doc = Document(
        id=doc_id,
        title="Travel Policy",
        original_filename="policy.pdf",
        file_type="pdf",
        storage_path=storage_path,
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    # Mock storage download returning valid PDF bytes
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=pdf_bytes)
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/extract")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc_id)
        assert data["file_type"] == "pdf"
        assert data["extraction_status"] == "completed"
        assert data["total_pages"] == 1
        assert len(data["pages"]) == 1
        assert data["pages"][0]["page_number"] == 1
        assert "KnowBridge AI Policy Text on Page 1" in data["extracted_text"]
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def test_api_extract_document_not_found(client: TestClient, override_db: Session):
    """
    Tests that extracting a non-existent document UUID returns HTTP 404 Not Found.
    """
    random_uuid = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_uuid}/extract")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_api_extract_document_corrupted_file(client: TestClient, override_db: Session):
    """
    Tests that extracting a corrupted document returns HTTP 422 Unprocessable Entity.
    """
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
        response = client.post(f"/api/v1/documents/{doc_id}/extract")
        assert response.status_code == 422
        assert "parsing failed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
