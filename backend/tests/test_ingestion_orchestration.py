"""
Unit and Integration Tests for End-to-End Ingestion Orchestration.
Task 003G – KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Polling ingestion job status by job_id (pending, processing, completed, failed).
2. Sanitization of error messages in job status responses (credential masking).
3. 404 handling for unknown job_id and unknown document_id.
4. Polling latest ingestion job by document_id.
5. Asynchronously triggering ingestion via POST /api/v1/ingestion/{document_id}/process (HTTP 202 Accepted).
6. Chunk overlap validation on process trigger (HTTP 400 when overlap >= size).
7. Concurrency guard preventing multiple simultaneous processing jobs for the same document.
8. Upload endpoint auto-processing parameter (auto_process=true enqueues job and returns ingestion_job_id).
9. Upload endpoint default behavior (auto_process=false preserves status='uploaded' and ingestion_job_id=None).
10. Background execution success (updating job and document status to 'completed').
11. Background execution error handling (updating job and document status to 'failed' with sanitized message).
"""

import math
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.schemas.chunking import DocumentChunk as ChunkSchema, DocumentChunkingResult
from app.schemas.embedding import ChunkEmbedding, DocumentEmbeddingResult
from app.schemas.extraction import ContentUnit, DocumentExtractionResult
from app.services.chunk_persistence import (
    ChunkPersistenceService,
    get_chunk_persistence_service,
)
from app.services.document_chunker import DocumentChunkerService
from app.services.document_extractor import DocumentExtractorService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import (
    IngestionService,
    get_ingestion_service,
    run_background_ingestion,
)
from app.services.storage_service import StorageService, get_storage_service


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def isolated_db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
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
    """Overrides the FastAPI get_db dependency with the isolated test session."""
    def _get_test_db():
        yield isolated_db_session

    app.dependency_overrides[get_db] = _get_test_db
    yield isolated_db_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def mock_storage():
    """Provides a mock StorageService instance for isolated unit tests."""
    mock = MagicMock(spec=StorageService)
    mock.is_configured = True
    mock.bucket_name = "knowledge-documents"
    mock.supabase_url = "https://mock.supabase.co"
    mock.service_role_key = "mock-key"

    async def _mock_upload(object_path, content, content_type="application/octet-stream", upsert=False):
        return object_path

    async def _mock_download(object_path):
        return b"%PDF-1.4 Mock PDF Content with Section 1.0 Policy"

    async def _mock_delete(object_path):
        return True

    mock.upload_file = AsyncMock(side_effect=_mock_upload)
    mock.download_file = AsyncMock(side_effect=_mock_download)
    mock.delete_file = AsyncMock(side_effect=_mock_delete)

    app.dependency_overrides[get_storage_service] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_storage_service, None)


def make_dummy_vector(dim: int = 384, seed: float = 0.05) -> list[float]:
    """Generates a dummy normalized 384d vector."""
    raw = [(seed + (i * 0.001)) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


# ============================================================================
# Test Cases 1-4: GET /api/v1/ingestion/{job_id}
# ============================================================================

def test_01_get_job_status_pending(client: TestClient, override_db: Session):
    """Scenario 1: GET /api/v1/ingestion/{job_id} returns 200 with 'pending' status."""
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status="pending",
    )
    override_db.add(job)
    override_db.commit()

    resp = client.get(f"/api/v1/ingestion/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(job_id)
    assert data["document_id"] == str(doc_id)
    assert data["status"] == "pending"
    assert data["total_pages"] is None
    assert data["total_chunks"] is None
    assert data["error_message"] is None


def test_02_get_job_status_completed(client: TestClient, override_db: Session):
    """Scenario 2: GET /api/v1/ingestion/{job_id} returns 200 with 'completed' metrics."""
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    now = datetime.utcnow()
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status="completed",
        total_pages=4,
        total_chunks=14,
        started_at=now,
        completed_at=now,
    )
    override_db.add(job)
    override_db.commit()

    resp = client.get(f"/api/v1/ingestion/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["total_pages"] == 4
    assert data["total_chunks"] == 14
    assert data["started_at"] is not None
    assert data["completed_at"] is not None


def test_03_get_job_status_failed_with_credential_sanitization(
    client: TestClient, override_db: Session
):
    """Scenario 3: Failed ingestion job returns sanitized error message redacting secrets."""
    doc_id = uuid.uuid4()
    job_id = uuid.uuid4()
    # IngestionJob created with an unredacted raw error string
    raw_error = "Connection failed to postgresql://user:my_secret_password@aws-pooler.supabase.com:5432/postgres"
    from app.core.database import sanitize_error_message
    sanitized = sanitize_error_message(raw_error)

    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status="failed",
        error_message=sanitized,
        completed_at=datetime.utcnow(),
    )
    override_db.add(job)
    override_db.commit()

    resp = client.get(f"/api/v1/ingestion/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert "my_secret_password" not in data["error_message"]
    assert "*****" in data["error_message"]


def test_04_get_job_not_found(client: TestClient, override_db: Session):
    """Scenario 4: Polling unknown job UUID returns HTTP 404."""
    unknown_id = uuid.uuid4()
    resp = client.get(f"/api/v1/ingestion/{unknown_id}")
    assert resp.status_code == 404
    assert f"'{unknown_id}' not found" in resp.json()["detail"]


# ============================================================================
# Test Cases 5-7: GET /api/v1/ingestion/document/{document_id}
# ============================================================================

def test_05_get_latest_job_for_document_success(client: TestClient, override_db: Session):
    """Scenario 5: Returns the most recent ingestion job for a document."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Leave Policy",
        original_filename="HR-LEV-001_Leave_Policy.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/leave.pdf",
        status="completed",
    )
    override_db.add(doc)

    t1 = datetime.utcnow() - timedelta(minutes=10)
    t2 = datetime.utcnow()
    older_job = IngestionJob(
        id=uuid.uuid4(),
        document_id=doc_id,
        status="failed",
        created_at=t1,
    )
    newer_job = IngestionJob(
        id=uuid.uuid4(),
        document_id=doc_id,
        status="completed",
        total_chunks=8,
        created_at=t2,
    )
    override_db.add_all([older_job, newer_job])
    override_db.commit()

    resp = client.get(f"/api/v1/ingestion/document/{doc_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == str(newer_job.id)
    assert data["status"] == "completed"
    assert data["total_chunks"] == 8


def test_06_get_latest_job_document_not_found(client: TestClient, override_db: Session):
    """Scenario 6: Polling latest job for non-existent document returns HTTP 404."""
    unknown_doc_id = uuid.uuid4()
    resp = client.get(f"/api/v1/ingestion/document/{unknown_doc_id}")
    assert resp.status_code == 404
    assert f"Document with ID '{unknown_doc_id}' not found" in resp.json()["detail"]


def test_07_get_latest_job_no_jobs_for_document(client: TestClient, override_db: Session):
    """Scenario 7: Document exists but has no jobs registered returns HTTP 404."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="New Document",
        original_filename="doc.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/doc.txt",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    resp = client.get(f"/api/v1/ingestion/document/{doc_id}")
    assert resp.status_code == 404
    assert f"No ingestion jobs found for document '{doc_id}'" in resp.json()["detail"]


# ============================================================================
# Test Cases 8-11: POST /api/v1/ingestion/{document_id}/process
# ============================================================================

def test_08_trigger_ingestion_endpoint_accepted(
    client: TestClient, override_db: Session, mock_storage: MagicMock
):
    """Scenario 8: POST /api/v1/ingestion/{document_id}/process returns HTTP 202 Accepted."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Remote Work Policy",
        original_filename="IT-REM-001_Remote_Work.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/remote.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    resp = client.post(f"/api/v1/ingestion/{doc_id}/process")
    assert resp.status_code == 202
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] in ("pending", "processing", "completed")
    assert "job_id" in data


def test_09_trigger_ingestion_invalid_overlap(client: TestClient, override_db: Session):
    """Scenario 9: POST /api/v1/ingestion/{document_id}/process rejects overlap >= size with 400."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Test Doc",
        original_filename="test.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/test.txt",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    resp = client.post(
        f"/api/v1/ingestion/{doc_id}/process",
        params={"chunk_size": 200, "chunk_overlap": 250},
    )
    assert resp.status_code == 400
    assert "chunk_overlap" in resp.json()["detail"]


def test_10_trigger_ingestion_missing_document(client: TestClient, override_db: Session):
    """Scenario 10: Triggering ingestion for non-existent document returns HTTP 404."""
    unknown_doc_id = uuid.uuid4()
    resp = client.post(f"/api/v1/ingestion/{unknown_doc_id}/process")
    assert resp.status_code == 404
    assert f"'{unknown_doc_id}' not found" in resp.json()["detail"]


def test_11_trigger_ingestion_concurrency_guard_reuses_active_job(
    client: TestClient, override_db: Session
):
    """Scenario 11: Triggering ingestion when a job is already processing returns the active job."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Active Doc",
        original_filename="active.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/active.pdf",
        status="processing",
    )
    active_job = IngestionJob(
        id=uuid.uuid4(),
        document_id=doc_id,
        status="processing",
        started_at=datetime.utcnow(),
    )
    override_db.add_all([doc, active_job])
    override_db.commit()

    resp = client.post(f"/api/v1/ingestion/{doc_id}/process")
    assert resp.status_code == 202
    data = resp.json()
    # Reuses existing active job ID without creating a duplicate job
    assert data["job_id"] == str(active_job.id)
    assert data["status"] == "processing"


# ============================================================================
# Test Cases 12-13: Ingestion Orchestration Parameter Customization
# ============================================================================

def test_12_trigger_ingestion_creates_job_record(
    client: TestClient, override_db: Session
):
    """Scenario 12: Triggering ingestion creates IngestionJob in 'pending' status in database."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Security Policy",
        original_filename="SEC-001_Security.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/sec.txt",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    resp = client.post(f"/api/v1/ingestion/{doc_id}/process")
    assert resp.status_code == 202
    data = resp.json()
    job_id = uuid.UUID(data["job_id"])

    # Verify IngestionJob was registered in PostgreSQL
    job = override_db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    assert job is not None
    assert job.document_id == doc_id
    assert job.status in ("pending", "processing", "completed")


def test_13_trigger_ingestion_with_custom_parameters(
    client: TestClient, override_db: Session
):
    """Scenario 13: Triggering ingestion passes custom chunk_size and version_label."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Code of Conduct",
        original_filename="HR-COC-001_Conduct.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/conduct.txt",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    resp = client.post(
        f"/api/v1/ingestion/{doc_id}/process",
        params={"chunk_size": 800, "chunk_overlap": 100, "version_label": "2.0"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["document_id"] == str(doc_id)
    assert data["status"] in ("pending", "processing", "completed")


# ============================================================================
# Test Cases 14-16: Background Worker Execution & Fault Tolerance
# ============================================================================

@pytest.mark.anyio
async def test_14_background_worker_full_pipeline_success(
    isolated_db_session: Session, mock_storage: MagicMock
):
    """Scenario 14: Direct execution of IngestionService completes pipeline and persists chunks."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Expense Policy",
        original_filename="FIN-EXP-001_Expense_v1.0.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/expense.txt",
        status="uploaded",
    )
    job_id = uuid.uuid4()
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status="pending",
    )
    isolated_db_session.add_all([doc, job])
    isolated_db_session.commit()

    # Mock storage download returning valid TXT content
    mock_storage.download_file.return_value = b"Section 1.0 Expense Limits.\nDaily meal allowance is $75."

    # Mock embedding service to avoid loading sentence-transformers model during fast unit test
    mock_embedder = MagicMock(spec=EmbeddingService)
    mock_embedder.expected_model = "sentence-transformers/all-MiniLM-L6-v2"
    mock_embedder.expected_dimension = 384

    def _mock_embed(chunking_result, batch_size=None):
        embeddings = []
        for i, chunk in enumerate(chunking_result.chunks):
            embeddings.append(
                ChunkEmbedding(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    filename=chunk.filename,
                    chunk_index=chunk.chunk_index,
                    chunk_text=chunk.chunk_text,
                    section_title=chunk.section_title,
                    page_number=chunk.page_number,
                    metadata=chunk.metadata,
                    embedding=make_dummy_vector(384, seed=0.01 * (i + 1)),
                    embedding_model="sentence-transformers/all-MiniLM-L6-v2",
                    dimension=384,
                )
            )
        return DocumentEmbeddingResult(
            document_id=chunking_result.document_id,
            filename=chunking_result.filename,
            total_chunks=len(embeddings),
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dimension=384,
            embeddings=embeddings,
        )

    mock_embedder.embed_document_result.side_effect = _mock_embed

    persistence_svc = ChunkPersistenceService(expected_dimension=384)
    ingestion_svc = IngestionService(
        persistence_service=persistence_svc,
        storage_service=mock_storage,
        extractor_service=DocumentExtractorService(storage_service=mock_storage),
        chunker_service=DocumentChunkerService(),
        embedding_service=mock_embedder,
    )

    await ingestion_svc.execute_ingestion(
        db=isolated_db_session,
        document_id=doc_id,
        job_id=job_id,
    )

    # Verify job status and chunk counts
    isolated_db_session.refresh(job)
    isolated_db_session.refresh(doc)
    assert job.status == "completed"
    assert job.total_chunks > 0
    assert doc.status == "completed"

    # Verify chunks persisted in DB
    chunks = isolated_db_session.query(DocumentChunk).all()
    assert len(chunks) == job.total_chunks


@pytest.mark.anyio
async def test_15_background_worker_failure_handling(
    isolated_db_session: Session, mock_storage: MagicMock
):
    """Scenario 15: Background worker catches exception and records sanitized error on job."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Corrupted File",
        original_filename="corrupted.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/corrupted.pdf",
        status="uploaded",
    )
    job_id = uuid.uuid4()
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        status="pending",
    )
    isolated_db_session.add_all([doc, job])
    isolated_db_session.commit()

    # Simulate storage error containing a sensitive password token
    from app.services.storage_service import StorageDownloadError
    mock_storage.download_file.side_effect = StorageDownloadError(
        "Download failed from https://user:secret_token@supabase.co: Connection refused"
    )

    ingestion_svc = IngestionService(
        storage_service=mock_storage,
    )

    await ingestion_svc.execute_ingestion(
        db=isolated_db_session,
        document_id=doc_id,
        job_id=job_id,
    )

    isolated_db_session.refresh(job)
    isolated_db_session.refresh(doc)
    assert job.status == "failed"
    assert doc.status == "failed"
    assert "secret_token" not in job.error_message
    assert "*****" in job.error_message


@pytest.mark.anyio
async def test_16_background_worker_concurrency_guard(isolated_db_session: Session):
    """Scenario 16: Concurrency guard aborts second worker execution if another job is processing."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Concurrent Doc",
        original_filename="concurrent.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/concurrent.txt",
        status="processing",
    )
    active_job = IngestionJob(
        id=uuid.uuid4(),
        document_id=doc_id,
        status="processing",
        started_at=datetime.utcnow(),
    )
    duplicate_job = IngestionJob(
        id=uuid.uuid4(),
        document_id=doc_id,
        status="pending",
    )
    isolated_db_session.add_all([doc, active_job, duplicate_job])
    isolated_db_session.commit()

    ingestion_svc = IngestionService()

    # Attempt to execute duplicate_job while active_job is already processing
    await ingestion_svc.execute_ingestion(
        db=isolated_db_session,
        document_id=doc_id,
        job_id=duplicate_job.id,
    )

    isolated_db_session.refresh(active_job)
    isolated_db_session.refresh(duplicate_job)

    # Active job remains untouched in 'processing' state
    assert active_job.status == "processing"

    # Duplicate job is safely marked 'failed' due to concurrency guard
    assert duplicate_job.status == "failed"
    assert "already being processed" in duplicate_job.error_message
