import math
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.models.document import Document
from app.schemas.chunking import DocumentChunk, DocumentChunkingResult
from app.schemas.embedding import ChunkEmbedding, DocumentEmbeddingResult
from app.schemas.extraction import ContentUnit, DocumentExtractionResult
from app.services.document_chunker import DocumentChunkerService, get_document_chunker
from app.services.document_extractor import (
    DocumentExtractorService,
    get_document_extractor,
)
from app.services.embedding_service import (
    EmbeddingDimensionMismatchError,
    EmbeddingError,
    EmbeddingGenerationError,
    EmbeddingService,
    InvalidChunkError,
    ModelInitializationError,
    NonFiniteVectorError,
    get_embedding_service,
)
from app.services.storage_service import (
    StorageService,
    get_storage_service,
)


# ---------------------------------------------------------------------------
# Test Helpers & Mock Model Factories
# ---------------------------------------------------------------------------

def create_mock_sentence_transformer(dim: int = 384, return_non_finite: bool = False, count_offset: int = 0):
    """Creates a mock SentenceTransformer instance producing deterministic normalized vectors."""
    mock_model = MagicMock()
    mock_model.get_sentence_embedding_dimension.return_value = dim
    mock_model.get_embedding_dimension.return_value = dim

    def _encode(sentences, batch_size=32, normalize_embeddings=True, show_progress_bar=False):
        n = len(sentences) + count_offset
        # Deterministic pseudo-vectors with L2 normalization
        vectors = []
        for i, s in enumerate(sentences):
            # Seed based on sentence hash for determinism
            rng = np.random.RandomState(abs(hash(s)) % (2**31))
            vec = rng.randn(dim).astype(np.float32)
            if return_non_finite and i == 0:
                vec[0] = np.nan
            elif normalize_embeddings:
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            vectors.append(vec)
        if count_offset != 0:
            if count_offset > 0:
                for _ in range(count_offset):
                    vectors.append(np.zeros(dim, dtype=np.float32))
            else:
                vectors = vectors[:n]
        return np.array(vectors)

    mock_model.encode.side_effect = _encode
    return mock_model


def make_test_chunk(
    index: int = 0,
    text: str = "Test policy text",
    doc_id: uuid.UUID = None,
    filename: str = "test_policy.pdf",
    page_number: int = 1,
    section_title: str = "1.0 Purpose",
    metadata: dict = None,
) -> DocumentChunk:
    """Creates a valid DocumentChunk for testing."""
    return DocumentChunk(
        chunk_id=uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        chunk_index=index,
        chunk_text=text,
        character_count=len(text),
        token_count=max(1, len(text) // 4),
        page_number=page_number,
        section_title=section_title,
        section_hierarchy=["1.0 Enterprise Policy", section_title],
        source_unit_indices=[index],
        source_unit_type="paragraph",
        filename=filename,
        file_type="pdf",
        metadata=metadata or {"source": "unit_test", "custom_key": f"val_{index}"},
    )


# ---------------------------------------------------------------------------
# Database Fixtures for API Tests
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
# Unit Tests (14 Required Scenarios)
# ---------------------------------------------------------------------------

def test_01_correct_384_dimensional_vector_output():
    """Scenario 1: Validates that generated vectors have strictly 384 dimensions."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    chunk = make_test_chunk(text="Enterprise Travel Reimbursement Policy standard rates.")
    results = service.embed_chunks([chunk])

    assert len(results) == 1
    emb = results[0]
    assert len(emb.embedding) == 384
    assert emb.dimension == 384
    assert all(isinstance(v, float) for v in emb.embedding)


def test_02_batch_embedding_generation():
    """Scenario 2: Validates batch embedding generation across chunks."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model, batch_size=4)

    chunks = [make_test_chunk(index=i, text=f"Policy statement number {i}") for i in range(10)]
    results = service.embed_chunks(chunks)

    assert len(results) == 10
    mock_model.encode.assert_called_once()
    _, kwargs = mock_model.encode.call_args
    assert kwargs.get("batch_size") == 4
    assert kwargs.get("normalize_embeddings") is True


def test_03_input_output_ordering_preservation():
    """Scenario 3: Validates that input ordering is strictly preserved in output."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    chunks = [
        make_test_chunk(index=0, text="First section: Scope and Applicability"),
        make_test_chunk(index=1, text="Second section: Travel Authorizations"),
        make_test_chunk(index=2, text="Third section: Per Diem Meal Rates"),
        make_test_chunk(index=3, text="Fourth section: Receipt Substantiation"),
    ]
    results = service.embed_chunks(chunks)

    assert len(results) == 4
    for i, res in enumerate(results):
        assert res.chunk_index == i
        assert res.chunk_text == chunks[i].chunk_text
        assert res.section_title == chunks[i].section_title


def test_04_metadata_preservation():
    """Scenario 4: Validates complete preservation of chunk metadata and provenance."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    doc_id = uuid.uuid4()
    chunk = make_test_chunk(
        index=7,
        text="Section 7.3 International Airfare Class Policy",
        doc_id=doc_id,
        filename="HR-TRV-001_v2.0.pdf",
        page_number=5,
        section_title="7.3 International Airfare",
        metadata={"cost_center": "Global_HR", "tier": "Executive"},
    )
    results = service.embed_chunks([chunk])

    assert len(results) == 1
    emb = results[0]
    assert emb.document_id == doc_id
    assert emb.filename == "HR-TRV-001_v2.0.pdf"
    assert emb.chunk_index == 7
    assert emb.chunk_text == "Section 7.3 International Airfare Class Policy"
    assert emb.section_title == "7.3 International Airfare"
    assert emb.page_number == 5
    assert emb.embedding_model == service.model_name
    assert emb.dimension == 384
    assert emb.metadata["cost_center"] == "Global_HR"
    assert emb.metadata["tier"] == "Executive"


def test_05_empty_input():
    """Scenario 5: Validates graceful handling of empty inputs."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    # Empty list of chunks
    assert service.embed_chunks([]) == []
    # Empty list of texts
    assert service.embed_texts([]) == []
    mock_model.encode.assert_not_called()

    # Empty DocumentChunkingResult
    empty_result = DocumentChunkingResult(
        document_id=uuid.uuid4(),
        filename="empty.pdf",
        file_type="pdf",
        total_chunks=0,
        chunk_size=1000,
        chunk_overlap=150,
        chunks=[],
    )
    doc_emb = service.embed_document_result(empty_result)
    assert doc_emb.total_chunks == 0
    assert doc_emb.embeddings == []
    assert doc_emb.embedding_dimension == 384


def test_06_empty_or_whitespace_only_text():
    """Scenario 6: Validates rejection of empty or whitespace-only chunk text."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    # Empty string chunk
    empty_chunk = make_test_chunk(text="")
    with pytest.raises(InvalidChunkError) as exc_empty:
        service.embed_chunks([empty_chunk])
    assert "cannot be empty" in str(exc_empty.value).lower()

    # Whitespace-only string chunk
    ws_chunk = make_test_chunk(text="   \n\t  \r  ")
    with pytest.raises(InvalidChunkError) as exc_ws:
        service.embed_chunks([ws_chunk])
    assert "cannot be empty" in str(exc_ws.value).lower()

    # Query embedding empty or whitespace
    with pytest.raises(InvalidChunkError):
        service.embed_query("")
    with pytest.raises(InvalidChunkError):
        service.embed_query("   \t  ")


def test_07_invalid_chunk_structure():
    """Scenario 7: Validates rejection of invalid chunk structures."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model)

    # None in list
    with pytest.raises(InvalidChunkError) as exc_none:
        service.embed_chunks([None])
    assert "cannot be none" in str(exc_none.value).lower()

    # Dictionary missing chunk_text
    with pytest.raises(InvalidChunkError) as exc_dict:
        service.embed_chunks([{"chunk_index": 0, "title": "Missing chunk_text"}])
    assert "chunk_text" in str(exc_dict.value).lower()

    # Unsupported object type
    with pytest.raises(InvalidChunkError) as exc_type:
        service.embed_chunks([12345])
    assert "expected documentchunk" in str(exc_type.value).lower()


def test_08_incorrect_embedding_dimensions():
    """Scenario 8: Validates rejection of vectors with unexpected dimension (not 384)."""
    # Mock model producing 512 dimensions instead of 384
    mock_model_512 = create_mock_sentence_transformer(dim=512)
    service = EmbeddingService(model_instance=mock_model_512, dimension=384)

    chunk = make_test_chunk(text="Policy text expecting 384 dimensions")
    with pytest.raises(EmbeddingDimensionMismatchError) as exc:
        service.embed_chunks([chunk])
    assert "384" in str(exc.value).lower() and "512" in str(exc.value).lower()


def test_09_non_finite_vector_values():
    """Scenario 9: Validates rejection of vectors containing NaN or Inf values."""
    mock_model_nan = create_mock_sentence_transformer(dim=384, return_non_finite=True)
    service = EmbeddingService(model_instance=mock_model_nan)

    chunk = make_test_chunk(text="Policy text that generates non-finite values")
    with pytest.raises(NonFiniteVectorError) as exc:
        service.embed_chunks([chunk])
    assert "non-finite" in str(exc.value).lower() or "nan" in str(exc.value).lower()


def test_10_model_initialization_failure():
    """Scenario 10: Validates error handling on model load or download failure."""
    EmbeddingService.reset_cached_model()
    service = EmbeddingService(model_instance=None)

    with patch("sentence_transformers.SentenceTransformer", side_effect=RuntimeError("Network unreachable / offline")):
        with pytest.raises(ModelInitializationError) as exc:
            service._get_model()
        assert "failed to initialize" in str(exc.value).lower()
        assert "network unreachable" in str(exc.value).lower()


def test_11_batch_processing_across_multiple_batches():
    """Scenario 11: Validates correct processing across multiple batches."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model, batch_size=16)

    # Create 50 chunks (3 full batches of 16 + 1 remainder batch of 2)
    chunks = [make_test_chunk(index=i, text=f"Document chunk passage {i}") for i in range(50)]
    results = service.embed_chunks(chunks, batch_size=16)

    assert len(results) == 50
    mock_model.encode.assert_called_once()
    call_args, call_kwargs = mock_model.encode.call_args
    assert len(call_args[0]) == 50
    assert call_kwargs.get("batch_size") == 16
    # Verify all 50 indices match
    for i, res in enumerate(results):
        assert res.chunk_index == i


def test_12_consistent_normalization():
    """Scenario 12: Validates consistent L2 vector normalization for chunks and queries."""
    mock_model = create_mock_sentence_transformer(dim=384)
    service = EmbeddingService(model_instance=mock_model, normalize_embeddings=True)

    # Document chunk embedding
    chunk = make_test_chunk(text="Sample policy clause on standard allowance.")
    chunk_results = service.embed_chunks([chunk])
    chunk_vec = np.array(chunk_results[0].embedding)
    chunk_norm = np.linalg.norm(chunk_vec)
    assert math.isclose(chunk_norm, 1.0, rel_tol=1e-4)

    # Search query embedding
    query_vec = np.array(service.embed_query("What is the meal allowance per diem?"))
    query_norm = np.linalg.norm(query_vec)
    assert math.isclose(query_norm, 1.0, rel_tol=1e-4)


def test_13_embedding_count_matching_chunk_count():
    """Scenario 13: Validates that embedding count strictly matches input count."""
    # Mock model returning fewer embeddings than inputs (e.g. dropped row)
    mock_dropped = create_mock_sentence_transformer(dim=384, count_offset=-1)
    service = EmbeddingService(model_instance=mock_dropped)

    chunks = [make_test_chunk(index=i, text=f"Chunk {i}") for i in range(4)]
    with pytest.raises(EmbeddingGenerationError) as exc:
        service.embed_chunks(chunks)
    assert "does not match" in str(exc.value).lower()


def test_14_no_accidental_model_reinitialization():
    """Scenario 14: Validates model caching and absence of per-chunk reinitialization."""
    EmbeddingService.reset_cached_model()

    mock_st_instance = create_mock_sentence_transformer(dim=384)

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_st_instance) as mock_st_cls:
        service1 = EmbeddingService()
        chunks_batch1 = [make_test_chunk(index=i, text=f"Batch 1 Chunk {i}") for i in range(3)]
        service1.embed_chunks(chunks_batch1)

        # Second call using same service
        chunks_batch2 = [make_test_chunk(index=i, text=f"Batch 2 Chunk {i}") for i in range(2)]
        service1.embed_chunks(chunks_batch2)

        # Third call using new service instance (should reuse shared cache)
        service2 = EmbeddingService()
        service2.embed_query("Test query")

        # SentenceTransformer constructor must be called exactly once
        assert mock_st_cls.call_count == 1

    EmbeddingService.reset_cached_model()


# ---------------------------------------------------------------------------
# API Route Tests for POST /api/v1/documents/{document_id}/embed
# ---------------------------------------------------------------------------

def test_15_api_embed_endpoint_success(client: TestClient, override_db: Session):
    """Scenario 15: Validates successful POST /api/v1/documents/{document_id}/embed."""
    doc_id = uuid.uuid4()
    pdf_bytes = b"%PDF-1.4\nMinimal test document content for embedding."

    doc = Document(
        id=doc_id,
        title="Enterprise Travel Policy",
        original_filename="travel.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/travel.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    # Mock storage
    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=pdf_bytes)

    # Mock extractor returning 1 page unit
    mock_extractor = MagicMock(spec=DocumentExtractorService)
    mock_extraction = DocumentExtractionResult(
        document_id=doc_id,
        filename="travel.pdf",
        file_type="pdf",
        extraction_status="completed",
        total_pages=1,
        total_characters=100,
        extracted_text="Section 1.0 Travel Reimbursement Policy Statement.",
        pages=[
            ContentUnit(
                unit_index=0,
                unit_type="page",
                text="Section 1.0 Travel Reimbursement Policy Statement.",
                page_number=1,
                section_title="1.0 Travel Reimbursement",
                character_count=50,
            )
        ],
    )
    mock_extractor.extract_from_bytes.return_value = mock_extraction

    # Mock embedder
    mock_embedder_model = create_mock_sentence_transformer(dim=384)
    test_embedder = EmbeddingService(model_instance=mock_embedder_model)

    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    app.dependency_overrides[get_document_extractor] = lambda: mock_extractor
    app.dependency_overrides[get_embedding_service] = lambda: test_embedder

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/embed?batch_size=16")
        assert response.status_code == 200
        data = response.json()
        assert data["document_id"] == str(doc_id)
        assert data["filename"] == "travel.pdf"
        assert data["total_chunks"] >= 1
        assert data["embedding_dimension"] == 384
        assert len(data["embeddings"]) == data["total_chunks"]
        first_emb = data["embeddings"][0]
        assert first_emb["chunk_index"] == 0
        assert len(first_emb["embedding"]) == 384
        assert first_emb["page_number"] == 1
        assert first_emb["dimension"] == 384
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
        app.dependency_overrides.pop(get_document_extractor, None)
        app.dependency_overrides.pop(get_embedding_service, None)


def test_16_api_embed_endpoint_not_found(client: TestClient, override_db: Session):
    """Scenario 16: Validates that embedding a non-existent document returns HTTP 404."""
    random_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{random_id}/embed")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_17_api_embed_endpoint_invalid_overlap(client: TestClient, override_db: Session):
    """Scenario 17: Validates that chunk_overlap >= chunk_size returns HTTP 400."""
    doc_id = uuid.uuid4()
    response = client.post(f"/api/v1/documents/{doc_id}/embed?chunk_size=500&chunk_overlap=600")
    assert response.status_code == 400
    assert "strictly less than" in response.json()["detail"]


def test_18_api_embed_endpoint_corrupted_doc(client: TestClient, override_db: Session):
    """Scenario 18: Validates that corrupted document returns HTTP 422."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Corrupt File",
        original_filename="broken.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/broken.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=b"%PDF-1.4 corrupt junk")
    app.dependency_overrides[get_storage_service] = lambda: mock_storage

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/embed")
        assert response.status_code == 422
        assert "parsing failed" in response.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_storage_service, None)


def test_19_api_embed_endpoint_empty_chunks(client: TestClient, override_db: Session):
    """Scenario 19: Validates document producing zero chunks returns HTTP 200 with 0 embeddings."""
    doc_id = uuid.uuid4()
    doc = Document(
        id=doc_id,
        title="Scanned Blank Doc",
        original_filename="blank.pdf",
        file_type="pdf",
        storage_path=f"documents/{doc_id}/blank.pdf",
        status="uploaded",
    )
    override_db.add(doc)
    override_db.commit()

    mock_storage = MagicMock(spec=StorageService)
    mock_storage.is_configured = True
    mock_storage.download_file = AsyncMock(return_value=b"%PDF-1.4 blank")

    mock_extractor = MagicMock(spec=DocumentExtractorService)
    mock_extraction = DocumentExtractionResult(
        document_id=doc_id,
        filename="blank.pdf",
        file_type="pdf",
        extraction_status="empty_content",
        total_pages=1,
        total_characters=0,
        extracted_text="",
        pages=[],
    )
    mock_extractor.extract_from_bytes.return_value = mock_extraction

    mock_embedder_model = create_mock_sentence_transformer(dim=384)
    test_embedder = EmbeddingService(model_instance=mock_embedder_model)

    app.dependency_overrides[get_storage_service] = lambda: mock_storage
    app.dependency_overrides[get_document_extractor] = lambda: mock_extractor
    app.dependency_overrides[get_embedding_service] = lambda: test_embedder

    try:
        response = client.post(f"/api/v1/documents/{doc_id}/embed")
        assert response.status_code == 200
        data = response.json()
        assert data["total_chunks"] == 0
        assert data["embeddings"] == []
    finally:
        app.dependency_overrides.pop(get_storage_service, None)
        app.dependency_overrides.pop(get_document_extractor, None)
        app.dependency_overrides.pop(get_embedding_service, None)
