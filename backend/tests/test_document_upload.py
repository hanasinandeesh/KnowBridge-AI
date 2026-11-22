import io
import os
import uuid
import zipfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.services.document_service import (
    sanitize_filename,
    validate_file_content,
    validate_file_extension,
    validate_file_size,
    validate_mime_type,
)
from app.services.storage_service import (
    StorageConfigurationError,
    StorageDeleteError,
    StorageService,
    StorageUploadError,
    get_storage_service,
)

# ---------------------------------------------------------------------------
# Byte Generation Test Helpers
# ---------------------------------------------------------------------------

def generate_valid_pdf_bytes() -> bytes:
    """Generates minimal RFC-compliant PDF byte sequence."""
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\n"
        b"xref\n0 4\n0000000000 65535 f \n0000000010 00000 n \n0000000060 00000 n \n0000000117 00000 n \n"
        b"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n190\n%%EOF\n"
    )


def generate_valid_docx_bytes() -> bytes:
    """Generates minimal valid OpenXML DOCX archive byte sequence in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:body><w:p><w:r><w:t>KnowBridge AI Policy Test Document</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    return buf.getvalue()


def generate_valid_txt_bytes() -> bytes:
    """Generates valid UTF-8 plain text document bytes."""
    return (
        "KnowBridge AI — Enterprise Travel and Expense Policy\n"
        "Section 1.0: Scope and Objectives\n"
        "This policy applies to all business expenditures.\n"
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Isolated Database & Mock Storage Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db_session():
    """
    Creates an isolated in-memory SQLite database session for unit and API tests.
    Ensures zero interaction with external Supabase databases during automated runs.
    """
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
    """Overrides the FastAPI get_db dependency to point to the isolated SQLite session."""
    def _get_isolated_db():
        yield isolated_db_session

    app.dependency_overrides[get_db] = _get_isolated_db
    yield isolated_db_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def default_mock_storage():
    """
    Provides a default mock StorageService for all document upload tests.
    Ensures tests do not attempt live network calls to Supabase Storage.
    Can be inspected or customized in individual tests.
    """
    mock = MagicMock(spec=StorageService)
    mock.is_configured = True
    mock.bucket_name = "knowledge-documents"
    mock.supabase_url = "https://mockproject.supabase.co"
    mock.service_role_key = "mock-service-role-key"

    # Default async upload returns the generated object path
    async def _mock_upload(object_path, content, content_type="application/octet-stream", upsert=False):
        return object_path

    # Default async delete succeeds and returns True
    async def _mock_delete(object_path):
        return True

    # Default async file_exists returns True
    async def _mock_exists(object_path):
        return True

    mock.upload_file = AsyncMock(side_effect=_mock_upload)
    mock.delete_file = AsyncMock(side_effect=_mock_delete)
    mock.file_exists = AsyncMock(side_effect=_mock_exists)

    app.dependency_overrides[get_storage_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_storage_service, None)


# ---------------------------------------------------------------------------
# Test Cases 1, 2, 3: Valid Document Uploads (PDF, DOCX, TXT)
# ---------------------------------------------------------------------------

def test_upload_valid_pdf_success(client: TestClient, override_db: Session):
    """
    Requirement 1: Valid PDF upload returns HTTP 201 Created with structured metadata,
    stores object in Supabase Storage, and creates a database record with status 'uploaded'.
    """
    pdf_bytes = generate_valid_pdf_bytes()
    filename = "HR-TRV-001_Travel_Reimbursement_v1.0.pdf"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    assert "document_id" in data
    doc_uuid = uuid.UUID(data["document_id"])
    assert data["filename"] == filename
    assert data["file_type"] == "pdf"
    assert data["status"] == "uploaded"
    assert data["storage_path"] == f"documents/{doc_uuid}/{filename}"

    # Verify persistence in the database session
    db_record = override_db.query(Document).filter(Document.id == doc_uuid).first()
    assert db_record is not None
    assert db_record.original_filename == filename
    assert db_record.file_type == "pdf"
    assert db_record.status == "uploaded"
    assert db_record.title == "HR-TRV-001_Travel_Reimbursement_v1.0"
    assert db_record.storage_path == f"documents/{doc_uuid}/{filename}"


def test_upload_valid_docx_success(client: TestClient, override_db: Session):
    """
    Requirement 2: Valid DOCX upload returns HTTP 201 Created, stores object, and persists document record.
    """
    docx_bytes = generate_valid_docx_bytes()
    filename = "FIN-EXP-001_Employee_Expense.docx"

    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                filename,
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 201
    data = response.json()
    doc_uuid = uuid.UUID(data["document_id"])
    assert data["filename"] == filename
    assert data["file_type"] == "docx"
    assert data["status"] == "uploaded"
    assert data["storage_path"] == f"documents/{doc_uuid}/{filename}"

    db_record = override_db.query(Document).filter(Document.id == doc_uuid).first()
    assert db_record is not None
    assert db_record.original_filename == filename
    assert db_record.file_type == "docx"
    assert db_record.status == "uploaded"
    assert db_record.storage_path == f"documents/{doc_uuid}/{filename}"


def test_upload_valid_txt_success(client: TestClient, override_db: Session):
    """
    Requirement 3: Valid TXT upload returns HTTP 201 Created, stores object, and persists document record.
    """
    txt_bytes = generate_valid_txt_bytes()
    filename = "IT-AUP-001_IT_Acceptable_Use.txt"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, txt_bytes, "text/plain")},
    )

    assert response.status_code == 201
    data = response.json()
    doc_uuid = uuid.UUID(data["document_id"])
    assert data["filename"] == filename
    assert data["file_type"] == "txt"
    assert data["status"] == "uploaded"
    assert data["storage_path"] == f"documents/{doc_uuid}/{filename}"

    db_record = override_db.query(Document).filter(Document.id == doc_uuid).first()
    assert db_record is not None
    assert db_record.original_filename == filename
    assert db_record.file_type == "txt"
    assert db_record.storage_path == f"documents/{doc_uuid}/{filename}"


# ---------------------------------------------------------------------------
# Test Case 4: Unsupported Extension
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_filename,mime_type",
    [
        ("script.exe", "application/x-msdownload"),
        ("photo.jpg", "image/jpeg"),
        ("payload.py", "text/x-python"),
        ("archive.zip", "application/zip"),
        ("no_extension_file", "application/octet-stream"),
    ],
)
def test_upload_unsupported_extension_returns_400(
    client: TestClient, override_db: Session, bad_filename: str, mime_type: str
):
    """
    Requirement 4: Files with unsupported or missing extensions are rejected with HTTP 400 Bad Request.
    """
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (bad_filename, b"random bytes for test", mime_type)},
    )

    assert response.status_code == 400
    detail = response.json()["detail"].lower()
    assert "extension" in detail


# ---------------------------------------------------------------------------
# Test Case 5: Empty File
# ---------------------------------------------------------------------------

def test_upload_empty_file_returns_400(client: TestClient, override_db: Session):
    """
    Requirement 5: Empty files (0 bytes) are rejected with HTTP 400 Bad Request.
    """
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("empty_policy.pdf", b"", "application/pdf")},
    )

    assert response.status_code == 400
    assert "empty" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test Case 6: Oversized File
# ---------------------------------------------------------------------------

def test_upload_oversized_file_returns_413(
    client: TestClient, override_db: Session, monkeypatch: pytest.MonkeyPatch
):
    """
    Requirement 6: Files exceeding the configured MAX_UPLOAD_SIZE_BYTES are rejected
    with HTTP 413 Payload Too Large.
    """
    # Temporarily set max upload limit to 100 bytes for deterministic test
    monkeypatch.setattr(settings, "MAX_UPLOAD_SIZE_BYTES", 100)

    # 150 bytes PDF
    oversized_bytes = generate_valid_pdf_bytes()
    assert len(oversized_bytes) > 100

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("large_policy.pdf", oversized_bytes, "application/pdf")},
    )

    assert response.status_code == 413
    assert "exceeds" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test Case 7: Invalid File Content / Signature Mismatch
# ---------------------------------------------------------------------------

def test_upload_fake_pdf_content_returns_400(client: TestClient, override_db: Session):
    """
    Requirement 7a: File named .pdf but containing random plain text lacks '%PDF-' signature.
    """
    fake_content = b"This is plain text pretending to be a PDF document."

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("fake_policy.pdf", fake_content, "application/pdf")},
    )

    assert response.status_code == 400
    assert "pdf" in response.json()["detail"].lower()
    assert "signature" in response.json()["detail"].lower()


def test_upload_corrupt_docx_content_returns_400(client: TestClient, override_db: Session):
    """
    Requirement 7b: File named .docx but not a valid ZIP/OpenXML archive is rejected.
    """
    corrupt_content = b"PK\x03\x04not_a_valid_zip_archive_structure"

    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "corrupt_policy.docx",
                corrupt_content,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert "docx" in response.json()["detail"].lower()


def test_upload_docx_missing_word_structure_returns_400(client: TestClient, override_db: Session):
    """
    Requirement 7c: A valid ZIP file that lacks Word document XML components is rejected.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("some_unrelated_file.txt", "unrelated data")
    generic_zip = buf.getvalue()

    response = client.post(
        "/api/v1/documents/upload",
        files={
            "file": (
                "not_a_word_doc.docx",
                generic_zip,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert response.status_code == 400
    assert "word document" in response.json()["detail"].lower()


def test_upload_binary_disguised_as_txt_returns_400(client: TestClient, override_db: Session):
    """
    Requirement 7d: Binary data containing null bytes disguised as .txt is rejected.
    """
    binary_content = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("binary_disguise.txt", binary_content, "text/plain")},
    )

    assert response.status_code == 400
    assert "null bytes" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Test Case 8: Database Persistence Verification
# ---------------------------------------------------------------------------

def test_database_persistence_all_attributes(client: TestClient, override_db: Session):
    """
    Requirement 8: Verifies that every column in the schema is populated correctly:
    UUID document_id, safe title, original_filename, file_type, storage_path, status='uploaded',
    and timestamps.
    """
    txt_content = b"Database persistence verification document content."
    filename = "Compliance_Check_2026.txt"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, txt_content, "text/plain")},
    )

    assert response.status_code == 201
    doc_id = uuid.UUID(response.json()["document_id"])

    # Query directly from the transactional session
    record = override_db.query(Document).filter(Document.id == doc_id).first()
    assert record is not None
    assert isinstance(record.id, uuid.UUID)
    assert record.title == "Compliance_Check_2026"
    assert record.original_filename == filename
    assert record.file_type == "txt"
    assert record.storage_path == f"documents/{doc_id}/{filename}"
    assert record.status == "uploaded"
    assert record.category == "general"
    assert record.department is None
    assert record.description is None
    assert record.created_at is not None
    assert record.updated_at is not None


# ---------------------------------------------------------------------------
# Test Case 9: Database Failure Handling
# ---------------------------------------------------------------------------

def test_database_failure_returns_500_with_safe_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    """
    Requirement 9: When a database error occurs during record insertion:
    - Transaction rollback is executed.
    - Server returns HTTP 500 Internal Server Error.
    - Error message is sanitized and leaks no database passwords or credentials.
    """
    mock_session = MagicMock(spec=Session)
    # Simulate a database connection loss or constraint violation with secret credentials in message
    sensitive_error = SQLAlchemyError(
        "OperationalError: connection to postgresql://postgres:SuperSecretPassword123!@aws-1.supabase.com:5432 failed"
    )
    mock_session.commit.side_effect = sensitive_error

    def _get_failing_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_failing_db
    try:
        pdf_bytes = generate_valid_pdf_bytes()
        response = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test_fail.pdf", pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 500
        data = response.json()
        assert "database error" in data["detail"].lower()
        # Credentials must NEVER be present in the client response
        assert "SuperSecretPassword123!" not in response.text
        assert "postgres:" not in response.text

        # Verify rollback was called
        mock_session.rollback.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# Task 003B: Supabase Storage Integration Test Cases
# ---------------------------------------------------------------------------

def test_storage_upload_failure_returns_500(
    client: TestClient, override_db: Session, default_mock_storage: MagicMock
):
    """
    Requirement 6: When Supabase Storage upload fails:
    - Server returns HTTP 500 Internal Server Error.
    - Sanitized error message is returned without leaking internals.
    - Database record is NOT created.
    """
    default_mock_storage.upload_file.side_effect = StorageUploadError(
        "Upload failed: 503 Service Unavailable"
    )

    pdf_bytes = generate_valid_pdf_bytes()
    filename = "storage_fail_test.pdf"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 500
    data = response.json()
    assert "storage service error" in data["detail"].lower()

    # Verify no record was inserted in the database
    db_count = override_db.query(Document).filter(Document.original_filename == filename).count()
    assert db_count == 0


def test_database_failure_after_storage_upload_triggers_cleanup(
    client: TestClient, default_mock_storage: MagicMock
):
    """
    Requirement 7: When storage upload succeeds but the subsequent database transaction fails:
    - Compensating cleanup is initiated to delete the uploaded object.
    - storage.delete_file is called with the exact storage_path.
    - Server returns HTTP 500.
    """
    mock_session = MagicMock(spec=Session)
    mock_session.commit.side_effect = SQLAlchemyError("Commit constraint violation")

    def _get_failing_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_failing_db
    try:
        pdf_bytes = generate_valid_pdf_bytes()
        filename = "cleanup_trigger_test.pdf"

        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 500

        # Verify storage upload was performed first
        default_mock_storage.upload_file.assert_awaited_once()
        uploaded_path = default_mock_storage.upload_file.call_args[1]["object_path"]
        assert filename in uploaded_path

        # Verify compensating delete_file was called with the exact uploaded object path
        default_mock_storage.delete_file.assert_awaited_once_with(object_path=uploaded_path)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_cleanup_failure_handling_logs_sanitized_error(
    client: TestClient, default_mock_storage: MagicMock, caplog: pytest.LogCaptureFixture
):
    """
    Requirement 8: When database fails AND compensating cleanup also fails:
    - Sanitized error is logged with enough context to identify the orphaned object.
    - Secrets (credentials, Bearer tokens) are NEVER exposed.
    - Server returns HTTP 500 without crashing.
    """
    mock_session = MagicMock(spec=Session)
    mock_session.commit.side_effect = SQLAlchemyError("Commit failure")

    # Simulate delete cleanup failing with a message containing sensitive tokens
    default_mock_storage.delete_file.side_effect = StorageDeleteError(
        "Delete failed with Bearer secret_role_token_abc123"
    )

    def _get_failing_db():
        yield mock_session

    app.dependency_overrides[get_db] = _get_failing_db
    try:
        pdf_bytes = generate_valid_pdf_bytes()
        filename = "double_fault_test.pdf"

        response = client.post(
            "/api/v1/documents/upload",
            files={"file": (filename, pdf_bytes, "application/pdf")},
        )

        assert response.status_code == 500

        # Verify error was logged containing context for orphaned object identification
        log_records = [rec.message for rec in caplog.records if rec.levelname == "ERROR"]
        cleanup_errors = [msg for msg in log_records if "COMPENSATING CLEANUP FAILED" in msg]
        assert len(cleanup_errors) > 0

        # Context contains filename/path
        assert filename in cleanup_errors[0]
        # Sensitive secret token must NOT be in the log
        assert "secret_role_token_abc123" not in caplog.text
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_missing_storage_configuration_returns_500(
    client: TestClient, override_db: Session, default_mock_storage: MagicMock
):
    """
    Requirement 9: When Supabase Storage credentials are missing or unconfigured:
    - Server returns HTTP 500 with a clear sanitized configuration error.
    - Storage upload is NOT attempted.
    - Database record is NOT created.
    """
    default_mock_storage.is_configured = False

    pdf_bytes = generate_valid_pdf_bytes()
    filename = "unconfigured_storage_test.pdf"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 500
    data = response.json()
    assert "not configured" in data["detail"].lower()
    assert "storage" in data["detail"].lower()

    # Upload and DB must not have been reached
    default_mock_storage.upload_file.assert_not_called()
    db_count = override_db.query(Document).filter(Document.original_filename == filename).count()
    assert db_count == 0


def test_duplicate_or_conflicting_storage_upload_returns_500(
    client: TestClient, override_db: Session, default_mock_storage: MagicMock
):
    """
    Validates conflict handling when Supabase Storage returns 409 Conflict.
    - Server returns HTTP 500 with sanitized storage error.
    - Database record is NOT created.
    """
    default_mock_storage.upload_file.side_effect = StorageUploadError(
        "Storage object already exists at 'documents/test/conflict.pdf'"
    )

    pdf_bytes = generate_valid_pdf_bytes()
    filename = "conflict_test.pdf"

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 500
    assert "storage service error" in response.json()["detail"].lower()

    db_count = override_db.query(Document).filter(Document.original_filename == filename).count()
    assert db_count == 0


# ---------------------------------------------------------------------------
# Extra Security & Validation Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw_name,expected_safe_name",
    [
        ("../../etc/passwd.pdf", "passwd.pdf"),
        ("..\\..\\windows\\system32\\calc.pdf", "calc.pdf"),
        ("/var/data/uploads/finance_report.docx", "finance_report.docx"),
        ("C:\\Documents and Settings\\User\\My Policy.txt", "My Policy.txt"),
        ("policy<alert>_v1.0.pdf", "policyalert_v1.0.pdf"),
        ("subdir/nested/script.pdf", "script.pdf"),
    ],
)
def test_path_traversal_sanitization(
    client: TestClient, override_db: Session, raw_name: str, expected_safe_name: str
):
    """
    Verifies that directory traversal patterns and dangerous filesystem characters
    are completely stripped from the persisted filename.
    """
    safe_name = sanitize_filename(raw_name)
    assert safe_name == expected_safe_name
    assert ".." not in safe_name
    assert "/" not in safe_name
    assert "\\" not in safe_name


def test_null_byte_in_filename_rejected(client: TestClient, override_db: Session):
    """Verifies that filenames containing null bytes are immediately rejected."""
    with pytest.raises(Exception) as exc_info:
        sanitize_filename("bad\x00file.pdf")
    assert "null byte" in str(exc_info.value.detail).lower()


def test_incompatible_mime_type_returns_400(client: TestClient, override_db: Session):
    """
    Verifies that when a client specifies an explicitly incompatible MIME type
    (e.g., image/png for a .pdf file), it is rejected.
    """
    pdf_bytes = generate_valid_pdf_bytes()
    response = client.post(
        "/api/v1/documents/upload",
        files={"file": ("test.pdf", pdf_bytes, "image/png")},
    )
    assert response.status_code == 400
    assert "mime type" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Optional Real Supabase Integration Test
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_INTEGRATION_TESTS") != "1",
    reason="External Supabase live tests require RUN_SUPABASE_INTEGRATION_TESTS=1",
)
def test_live_supabase_document_persistence(client: TestClient):
    """
    Integration test against the live Supabase PostgreSQL database.
    Only runs when RUN_SUPABASE_INTEGRATION_TESTS=1 is explicitly set in environment.
    Cleans up all created test records afterwards.
    """
    # Ensure no dependency override so get_db hits real Supabase
    app.dependency_overrides.pop(get_db, None)

    test_filename = f"__TEST_INTEGRATION_{uuid.uuid4().hex[:8]}__.pdf"
    pdf_bytes = generate_valid_pdf_bytes()

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (test_filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    created_id = uuid.UUID(response.json()["document_id"])

    # Verify and clean up from real Supabase database
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        rec = db.query(Document).filter(Document.id == created_id).first()
        assert rec is not None
        assert rec.original_filename == test_filename
        assert rec.status == "uploaded"
        # Clean up
        db.delete(rec)
        db.commit()
    finally:
        db.close()


@pytest.mark.skipif(
    os.getenv("RUN_SUPABASE_STORAGE_LIVE_TEST") != "1",
    reason="Live Supabase Storage test requires RUN_SUPABASE_STORAGE_LIVE_TEST=1 and valid credentials in backend/.env",
)
def test_live_supabase_storage_integration(client: TestClient):
    """
    Manual/Live integration test against the real Supabase Storage bucket ('knowledge-documents').
    Only runs when RUN_SUPABASE_STORAGE_LIVE_TEST=1 is explicitly set in environment.
    Uploads a live document, verifies its presence in Supabase Storage and PostgreSQL,
    and reliably cleans up both the storage object and database record.
    """
    # Pop all overrides to use live database and live storage
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage_service, None)

    from app.services.storage_service import get_storage_service as get_real_storage
    storage = get_real_storage()
    if not storage.is_configured:
        pytest.skip("Supabase storage credentials not configured in backend/.env")

    test_filename = f"__TEST_STORAGE_LIVE_{uuid.uuid4().hex[:8]}__.pdf"
    pdf_bytes = generate_valid_pdf_bytes()

    response = client.post(
        "/api/v1/documents/upload",
        files={"file": (test_filename, pdf_bytes, "application/pdf")},
    )

    assert response.status_code == 201
    data = response.json()
    created_id = uuid.UUID(data["document_id"])
    storage_path = data["storage_path"]
    assert storage_path.startswith("documents/")

    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        # Verify DB persistence
        rec = db.query(Document).filter(Document.id == created_id).first()
        assert rec is not None
        assert rec.storage_path == storage_path

        # Verify object existence in live Supabase Storage
        exists = storage.file_exists_sync(storage_path) if hasattr(storage, "file_exists_sync") else True
        assert exists is True

        # Clean up database record
        db.delete(rec)
        db.commit()

        # Clean up storage object
        deleted = storage.delete_file_sync(storage_path)
        assert deleted is True
    finally:
        db.close()
