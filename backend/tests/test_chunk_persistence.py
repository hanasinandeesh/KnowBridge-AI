"""
Unit and Integration Tests for Document Chunk and Embedding Database Persistence.
Task 003F – KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Successful persistence of multiple chunks.
2. Correct document version association.
3. Correct 384-dimensional vector storage.
4. PDF page-number preservation.
5. DOCX/TXT page_number remaining NULL.
6. Section-title preservation.
7. Metadata preservation.
8. Correct chunk ordering.
9. Empty chunk list.
10. Invalid embedding dimensions.
11. Non-finite vector values (NaN, Inf, -Inf).
12. Missing document handling (DocumentNotFoundError).
13. Missing document version resolution & safe creation.
14. Duplicate persistence (idempotency).
15. Reprocessing an existing document version (clean replacement).
16. Transaction rollback on failure.
17. No partial chunk records after a failed transaction.
18. Historical document versions remain untouched.
19. Ingestion job status handling (pending -> processing -> completed / failed).
20. API endpoint POST /api/v1/documents/{document_id}/persist success.
21. API endpoint 404 for missing document.
22. API endpoint 400 for invalid overlap.
"""

import math
import uuid
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError, SQLAlchemyError
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
    AlignmentError,
    ChunkPersistenceService,
    DocumentNotFoundError,
    DocumentVersionResolutionError,
    EmbeddingValidationError,
    PersistenceError,
    get_chunk_persistence_service,
)
from app.services.document_chunker import DocumentChunkerService
from app.services.document_extractor import DocumentExtractorService
from app.services.embedding_service import EmbeddingService
from app.services.storage_service import StorageService, get_storage_service


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def isolated_db_session():
    """
    Provides an in-memory SQLite database session isolated per test.
    Guarantees no modification of external or live Supabase databases.
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
    """Overrides the FastAPI get_db dependency with the isolated test session."""
    def _get_test_db():
        yield isolated_db_session

    app.dependency_overrides[get_db] = _get_test_db
    yield isolated_db_session
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def persistence_service():
    """Provides a fresh ChunkPersistenceService configured for 384 dimensions."""
    return ChunkPersistenceService(
        expected_dimension=384,
        expected_model="sentence-transformers/all-MiniLM-L6-v2",
    )


def make_dummy_vector(dim: int = 384, seed: float = 0.05) -> list[float]:
    """Generates a normalized dummy vector of given dimension."""
    raw = [(seed + (i * 0.001)) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def make_chunk_embedding(
    chunk_index: int = 0,
    text: str = "Test chunk content",
    page_number: int | None = 1,
    section_title: str | None = "Section 1.0",
    dim: int = 384,
    model: str = "sentence-transformers/all-MiniLM-L6-v2",
    metadata: dict | None = None,
) -> ChunkEmbedding:
    """Helper creating a valid ChunkEmbedding instance."""
    return ChunkEmbedding(
        chunk_id=uuid.uuid4(),
        chunk_index=chunk_index,
        chunk_text=text,
        section_title=section_title,
        page_number=page_number,
        embedding=make_dummy_vector(dim=dim, seed=0.01 * (chunk_index + 1)),
        embedding_model=model,
        dimension=dim,
        metadata=metadata or {"source_unit_type": "page", "section_hierarchy": [section_title or ""]},
    )


# ============================================================================
# Unit Tests (Scenarios 1-19)
# ============================================================================

def test_01_successful_persistence_multiple_chunks(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 1: Successful persistence of multiple chunks into document_chunks."""
    doc = Document(
        id=uuid.uuid4(),
        title="Leave Policy",
        original_filename="HR-LVE-001_Employee_Leave_v1.0.pdf",
        file_type="pdf",
        storage_path="documents/test/leave.pdf",
    )
    isolated_db_session.add(doc)
    isolated_db_session.commit()

    ver = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_label="1.0",
        is_current=True,
    )
    isolated_db_session.add(ver)
    isolated_db_session.commit()

    chunks = [
        make_chunk_embedding(i, f"Leave policy section text chunk {i}", page_number=i + 1)
        for i in range(5)
    ]

    count = persistence_service.persist_chunks_for_version(
        db=isolated_db_session,
        version=ver,
        chunk_embeddings=chunks,
        document_file_type="pdf",
    )
    isolated_db_session.commit()

    assert count == 5
    stored = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).all()
    assert len(stored) == 5
    assert [c.chunk_index for c in stored] == [0, 1, 2, 3, 4]


def test_02_correct_document_version_association(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 2: Correct document version association (FK references version, not doc)."""
    doc = Document(
        id=uuid.uuid4(),
        title="Travel Policy",
        original_filename="travel.pdf",
        file_type="pdf",
        storage_path="documents/test/travel.pdf",
    )
    ver = DocumentVersion(
        id=uuid.uuid4(),
        document_id=doc.id,
        version_label="1.0",
        is_current=True,
    )
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    chunks = [make_chunk_embedding(0, "Travel rules")]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")
    isolated_db_session.commit()

    chunk_in_db = isolated_db_session.query(DocumentChunk).first()
    assert chunk_in_db.document_version_id == ver.id
    assert chunk_in_db.version.id == ver.id
    assert chunk_in_db.version.document.id == doc.id


def test_03_correct_384_dimensional_vector_storage(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 3: Correct 384-dimensional vector storage without precision loss."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    original_vec = make_dummy_vector(384)
    chunk = ChunkEmbedding(
        chunk_id=uuid.uuid4(),
        chunk_index=0,
        chunk_text="Precision text",
        embedding=original_vec,
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
    )

    persistence_service.persist_chunks_for_version(isolated_db_session, ver, [chunk], "pdf")
    isolated_db_session.commit()

    retrieved = isolated_db_session.query(DocumentChunk).first()
    assert len(retrieved.embedding) == 384
    # Check value matching
    for orig, stored in zip(original_vec[:10], retrieved.embedding[:10]):
        assert pytest.approx(orig, rel=1e-5) == stored


def test_04_pdf_page_number_preservation(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 4: PDF page numbers preserved as 1-based integers."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    chunks = [
        make_chunk_embedding(0, "Page 1 content", page_number=1),
        make_chunk_embedding(1, "Page 3 content", page_number=3),
    ]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")
    isolated_db_session.commit()

    stored = isolated_db_session.query(DocumentChunk).order_by(DocumentChunk.chunk_index).all()
    assert stored[0].page_number == 1
    assert stored[1].page_number == 3


def test_05_docx_txt_page_number_remaining_null(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 5: DOCX and TXT page_number strictly remains NULL."""
    for ftype in ["docx", "txt"]:
        doc = Document(id=uuid.uuid4(), title="Doc", original_filename=f"doc.{ftype}", file_type=ftype, storage_path=f"p_{ftype}")
        ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
        isolated_db_session.add_all([doc, ver])
        isolated_db_session.commit()

        # Even if chunk object had a page number set, the service enforces None for docx/txt
        chunk = make_chunk_embedding(0, f"Content for {ftype}", page_number=5)
        persistence_service.persist_chunks_for_version(isolated_db_session, ver, [chunk], document_file_type=ftype)
        isolated_db_session.commit()

        stored = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).first()
        assert stored.page_number is None


def test_06_section_title_preservation(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 6: Section-title preservation."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    chunk = make_chunk_embedding(0, "Text", section_title="Section 4.2 Reimbursement Limits")
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, [chunk], "pdf")
    isolated_db_session.commit()

    stored = isolated_db_session.query(DocumentChunk).first()
    assert stored.section_title == "Section 4.2 Reimbursement Limits"


def test_07_metadata_preservation(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 7: Full metadata preservation in JSONB without discarding."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    custom_meta = {
        "section_hierarchy": ["1.0 HR Policies", "1.3 Remote Work"],
        "source_unit_indices": [0, 1],
        "source_unit_type": "paragraph",
        "author": "People Ops",
        "audit_tag": "v1-approved",
    }
    chunk = make_chunk_embedding(0, "Remote work guidelines", metadata=custom_meta)
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, [chunk], "pdf")
    isolated_db_session.commit()

    stored = isolated_db_session.query(DocumentChunk).first()
    assert stored.metadata_["author"] == "People Ops"
    assert stored.metadata_["audit_tag"] == "v1-approved"
    assert stored.metadata_["section_hierarchy"] == ["1.0 HR Policies", "1.3 Remote Work"]
    assert stored.metadata_["source_unit_indices"] == [0, 1]


def test_08_correct_chunk_ordering(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 8: Correct sequential chunk ordering preserved."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    chunks = [make_chunk_embedding(i, f"Chunk {i}") for i in range(10)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")
    isolated_db_session.commit()

    stored = isolated_db_session.query(DocumentChunk).order_by(DocumentChunk.chunk_index).all()
    for idx, c in enumerate(stored):
        assert c.chunk_index == idx
        assert c.chunk_text == f"Chunk {idx}"


def test_09_empty_chunk_list(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 9: Empty chunk list cleanly clears existing and returns 0."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    # Seed one chunk
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, [make_chunk_embedding(0, "Seed")], "pdf")
    isolated_db_session.commit()
    assert isolated_db_session.query(DocumentChunk).count() == 1

    # Now pass empty list
    count = persistence_service.persist_chunks_for_version(isolated_db_session, ver, [], "pdf")
    isolated_db_session.commit()
    assert count == 0
    assert isolated_db_session.query(DocumentChunk).count() == 0


def test_10_invalid_embedding_dimensions(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 10: Vector dimension not equal to 384 raises EmbeddingValidationError."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    # 128 dimensions instead of 384
    bad_chunk = make_chunk_embedding(0, "Bad vector", dim=128)
    with pytest.raises(EmbeddingValidationError) as exc_info:
        persistence_service.persist_chunks_for_version(isolated_db_session, ver, [bad_chunk], "pdf")
    assert "dimension mismatch" in str(exc_info.value).lower()


def test_11_non_finite_vector_values(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 11: Non-finite values (NaN, Inf, -Inf) raise EmbeddingValidationError."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    for bad_val in [float("nan"), float("inf"), float("-inf")]:
        vec = make_dummy_vector(384)
        vec[42] = bad_val
        chunk = ChunkEmbedding(
            chunk_index=0,
            chunk_text="Bad val chunk",
            embedding=vec,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            dimension=384,
        )
        with pytest.raises(EmbeddingValidationError) as exc_info:
            persistence_service.persist_chunks_for_version(isolated_db_session, ver, [chunk], "pdf")
        assert "non-finite" in str(exc_info.value).lower()


@pytest.mark.anyio
async def test_12_missing_document(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 12: Missing document raises DocumentNotFoundError."""
    random_id = uuid.uuid4()
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    extractor = DocumentExtractorService()
    chunker = DocumentChunkerService()
    embedder = MagicMock(spec=EmbeddingService)

    with pytest.raises(DocumentNotFoundError):
        await persistence_service.persist_document(
            db=isolated_db_session,
            document_id=random_id,
            storage=mock_storage,
            extractor=extractor,
            chunker=chunker,
            embedder=embedder,
        )


def test_13_missing_document_version_resolution(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 13: Missing document version is safely resolved and created without inventing dates."""
    doc = Document(
        id=uuid.uuid4(),
        title="Remote Work",
        original_filename="HR-WFH-001_Remote_Hybrid_Work_v2.0.pdf",
        file_type="pdf",
        storage_path="documents/test/remote.pdf",
    )
    isolated_db_session.add(doc)
    isolated_db_session.commit()

    # Extract version from filename (_v2.0) and date from text
    sample_text = "VERSION: 2.0\nEFFECTIVE DATE: 01 April 2026\nRemote work policy content."
    ver = persistence_service.resolve_or_create_version(
        db=isolated_db_session,
        document=doc,
        extracted_text=sample_text,
    )
    isolated_db_session.commit()

    assert ver.version_label == "2.0"
    assert ver.effective_from == date(2026, 4, 1)
    assert ver.effective_until is None  # Not invented!
    assert ver.is_current is True


def test_14_duplicate_persistence_and_idempotency(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 14: Duplicate persistence runs produce exact same count and no unique constraint violation."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    chunks = [make_chunk_embedding(i, f"Text {i}") for i in range(4)]

    # Run 1
    count1 = persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")
    isolated_db_session.commit()
    assert count1 == 4

    # Run 2 (exact same version)
    count2 = persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")
    isolated_db_session.commit()
    assert count2 == 4

    # DB total chunks must remain 4, not 8!
    total = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).count()
    assert total == 4


def test_15_reprocessing_existing_document_version(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 15: Reprocessing existing version replaces chunks cleanly even when chunk count changes."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    # Initial 5 chunks
    chunks_v1 = [make_chunk_embedding(i, f"Initial chunk {i}") for i in range(5)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks_v1, "pdf")
    isolated_db_session.commit()
    assert isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).count() == 5

    # Reprocess with 3 revised chunks
    chunks_v2 = [make_chunk_embedding(i, f"Revised chunk {i}") for i in range(3)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks_v2, "pdf")
    isolated_db_session.commit()

    stored = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).all()
    assert len(stored) == 3
    assert [c.chunk_text for c in stored] == ["Revised chunk 0", "Revised chunk 1", "Revised chunk 2"]


def test_16_transaction_rollback_on_failure(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 16: Transaction rollback on failure."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    # Seed 2 chunks
    persistence_service.persist_chunks_for_version(
        isolated_db_session, ver, [make_chunk_embedding(0, "A"), make_chunk_embedding(1, "B")], "pdf"
    )
    isolated_db_session.commit()
    assert isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).count() == 2

    # Attempt to persist with a simulated flush error
    with patch.object(isolated_db_session, "flush", side_effect=SQLAlchemyError("Simulated write failure")):
        with pytest.raises(PersistenceError):
            persistence_service.persist_chunks_for_version(
                isolated_db_session, ver, [make_chunk_embedding(0, "New")], "pdf"
            )

    # After rollback, the original 2 chunks remain intact
    assert isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).count() == 2


def test_17_no_partial_chunk_records_after_failed_transaction(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 17: No partial chunk records after a failed transaction."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=True)
    isolated_db_session.add_all([doc, ver])
    isolated_db_session.commit()

    # Validate fail before persist: invalid vector in middle of batch
    chunks = [
        make_chunk_embedding(0, "Valid chunk 0"),
        make_chunk_embedding(1, "Invalid chunk 1", dim=200),  # Bad dimension
        make_chunk_embedding(2, "Valid chunk 2"),
    ]

    with pytest.raises(EmbeddingValidationError):
        persistence_service.persist_chunks_for_version(isolated_db_session, ver, chunks, "pdf")

    # Zero chunks persisted
    assert isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver.id).count() == 0


def test_18_historical_document_versions_remain_untouched(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 18: Historical document versions remain untouched during newer version persistence."""
    doc = Document(id=uuid.uuid4(), title="Doc", original_filename="doc.pdf", file_type="pdf", storage_path="p")
    ver_v1 = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="1.0", is_current=False)
    ver_v2 = DocumentVersion(id=uuid.uuid4(), document_id=doc.id, version_label="2.0", is_current=True)
    isolated_db_session.add_all([doc, ver_v1, ver_v2])
    isolated_db_session.commit()

    # Persist chunks for v1.0
    chunks_v1 = [make_chunk_embedding(i, f"v1.0 chunk {i}") for i in range(3)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver_v1, chunks_v1, "pdf")
    isolated_db_session.commit()

    # Persist chunks for v2.0
    chunks_v2 = [make_chunk_embedding(i, f"v2.0 chunk {i}") for i in range(5)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver_v2, chunks_v2, "pdf")
    isolated_db_session.commit()

    # Re-persist v2.0
    chunks_v2_updated = [make_chunk_embedding(i, f"v2.0 updated {i}") for i in range(4)]
    persistence_service.persist_chunks_for_version(isolated_db_session, ver_v2, chunks_v2_updated, "pdf")
    isolated_db_session.commit()

    # Verify v1.0 chunks are completely untouched!
    v1_chunks = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver_v1.id).all()
    assert len(v1_chunks) == 3
    assert [c.chunk_text for c in v1_chunks] == ["v1.0 chunk 0", "v1.0 chunk 1", "v1.0 chunk 2"]

    # Verify v2.0 has its new 4 chunks
    v2_chunks = isolated_db_session.query(DocumentChunk).filter_by(document_version_id=ver_v2.id).all()
    assert len(v2_chunks) == 4


def test_19_correct_ingestion_job_status_handling(isolated_db_session: Session, persistence_service: ChunkPersistenceService):
    """Scenario 19: Ingestion job status lifecycle (pending -> processing -> completed / failed)."""
    doc_id = uuid.uuid4()
    job = persistence_service.get_or_create_ingestion_job(isolated_db_session, doc_id)
    assert job.status == "pending"

    # Mark processing
    persistence_service.mark_job_processing(isolated_db_session, job)
    assert job.status == "processing"
    assert job.started_at is not None

    # Mark completed
    persistence_service.mark_job_completed(isolated_db_session, job, total_chunks=12, total_pages=3)
    assert job.status == "completed"
    assert job.total_chunks == 12
    assert job.total_pages == 3
    assert job.completed_at is not None

    # Mark failed on another job
    job2 = IngestionJob(id=uuid.uuid4(), document_id=doc_id, status="processing")
    isolated_db_session.add(job2)
    isolated_db_session.commit()

    persistence_service.mark_job_failed(isolated_db_session, job2, "Simulated network failure password='secret'")
    assert job2.status == "failed"
    assert "secret" not in job2.error_message  # Error message is sanitized!
    assert "*****" in job2.error_message


# ============================================================================
# API Route Tests (POST /api/v1/documents/{document_id}/persist)
# ============================================================================

def test_20_api_persist_endpoint_success(client: TestClient, override_db: Session):
    """Scenario 20: POST /api/v1/documents/{document_id}/persist returns 200 and DocumentPersistenceResponse."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Expense Policy",
        original_filename="FIN-EXP-001_Employee_Expense.txt",
        file_type="txt",
        storage_path=f"documents/{doc_id}/expense.txt",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    # Mock storage download
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    txt_content = (
        "VERSION: 1.0\n"
        "EFFECTIVE DATE: 01 April 2025\n"
        "Section 1.0 Travel and Meals Reimbursement Policy.\n"
        "All expenses must be submitted within 30 days."
    ).encode("utf-8")
    mock_storage.download_file = AsyncMock(return_value=txt_content)

    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    try:
        response = client.post(f"/api/v1/documents/{doc_id}/persist?chunk_size=500&chunk_overlap=50")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc_id)
        assert data["persistence_status"] == "completed"
        assert data["persisted_chunk_count"] >= 1
        assert data["embedding_dimension"] == 384
        assert data["embedding_model"] == "sentence-transformers/all-MiniLM-L6-v2"
        assert data["version_label"] == "1.0"

        # Verify DB records
        chunks_in_db = override_db.query(DocumentChunk).all()
        assert len(chunks_in_db) == data["persisted_chunk_count"]
        # TXT document must have page_number=None
        assert all(c.page_number is None for c in chunks_in_db)
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def test_21_api_persist_endpoint_not_found(client: TestClient, override_db: Session):
    """Scenario 21: POST /api/v1/documents/{document_id}/persist with non-existent ID returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/persist")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_22_api_persist_endpoint_invalid_overlap(client: TestClient, override_db: Session):
    """Scenario 22: chunk_overlap >= chunk_size returns HTTP 400 Bad Request."""
    doc_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{doc_id}/persist?chunk_size=200&chunk_overlap=250")
    assert response.status_code == 400
    assert "strictly less than" in response.json()["detail"]
