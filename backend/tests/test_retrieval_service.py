"""
Focused Unit Tests for Semantic Vector Search Retrieval Service.
Task 04C — KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Successful semantic retrieval with ranked candidate chunks.
2. Query embedding service integration and vector serialization.
3. Correct database function invocation (match_policy_chunks parameters).
4. Top-K parameter behavior and sensible default enforcement.
5. Graceful handling of empty search results.
6. Rejection of invalid inputs (empty query, bad top_k, out-of-range threshold).
7. Database error handling and credential sanitization.
8. Complete result structure and provenance preservation (title, version, page, section).
9. Embedding generation error propagation.
"""

import math
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.schemas.retrieval import RetrievalResult, RetrievedChunk
from app.services.embedding_service import (
    EmbeddingGenerationError,
    EmbeddingService,
    InvalidQueryError,
)
from app.services.retrieval_service import (
    InvalidRetrievalParameterError,
    RetrievalDatabaseError,
    RetrievalError,
    RetrievalService,
    get_retrieval_service,
)


# ---------------------------------------------------------------------------
# Test Fixtures & Mock Factories
# ---------------------------------------------------------------------------

def make_dummy_384_vector(seed: int = 42) -> list[float]:
    """Generates a deterministic 384-dimensional unit vector."""
    # Seed simple pseudo-vector
    raw = [(math.sin(seed + i)) for i in range(384)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def make_mock_embedding_service(vector: list[float] = None) -> MagicMock:
    """Creates a mock EmbeddingService returning a valid 384-dimensional vector."""
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.dimension = 384
    mock_service.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_service.normalize_embeddings = True
    dummy_vec = vector or make_dummy_384_vector()
    mock_service.embed_query.return_value = dummy_vec
    return mock_service


def make_mock_row(
    chunk_id: uuid.UUID = None,
    doc_id: uuid.UUID = None,
    title: str = "Enterprise Travel & Expense Policy",
    content: str = "Standard per diem meal allowance is $75 per day.",
    similarity: float = 0.852,
    page_number: int = 3,
    version_number: str = "1.0",
    metadata: dict = None,
) -> dict:
    """Creates a dict resembling a row returned by match_policy_chunks."""
    return {
        "chunk_id": chunk_id or uuid.uuid4(),
        "document_id": doc_id or uuid.uuid4(),
        "document_title": title,
        "version_id": uuid.uuid4(),
        "version_number": version_number,
        "effective_date": date(2025, 4, 1),
        "sunset_date": None,
        "page_number": page_number,
        "content": content,
        "similarity": similarity,
        "chunk_metadata": metadata or {
            "section_title": "2.1 Meal Per Diem",
            "section_hierarchy": ["2.0 Travel Allowances", "2.1 Meal Per Diem"],
        },
    }


def make_mock_db_session(rows: list[dict] = None) -> MagicMock:
    """Creates a mock SQLAlchemy Session that returns mappings for rows."""
    mock_session = MagicMock(spec=Session)
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows if rows is not None else []
    mock_result.mappings.return_value = mock_mappings
    mock_session.execute.return_value = mock_result
    return mock_session


# ---------------------------------------------------------------------------
# Unit Test Scenarios for Task 04C
# ---------------------------------------------------------------------------

def test_01_successful_semantic_retrieval():
    """
    Scenario 1: Validates successful semantic retrieval with ranked candidate chunks.
    """
    chunk_id_1 = uuid.uuid4()
    chunk_id_2 = uuid.uuid4()
    doc_id = uuid.uuid4()

    mock_rows = [
        make_mock_row(
            chunk_id=chunk_id_1,
            doc_id=doc_id,
            title="Travel Policy v1",
            content="Daily meal per diem is capped at $75 for domestic trips.",
            similarity=0.892,
            page_number=2,
            version_number="1.0",
        ),
        make_mock_row(
            chunk_id=chunk_id_2,
            doc_id=doc_id,
            title="Travel Policy v1",
            content="Incidentals and tips are covered up to $15 daily.",
            similarity=0.741,
            page_number=3,
            version_number="1.0",
        ),
    ]

    mock_db = make_mock_db_session(mock_rows)
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    query = "What is the daily meal allowance for travel?"
    result = service.retrieve_chunks(db=mock_db, query=query, top_k=5, similarity_threshold=0.65)

    assert isinstance(result, RetrievalResult)
    assert result.query == query
    assert result.total_retrieved == 2
    assert len(result.chunks) == 2
    assert result.top_k == 5
    assert result.similarity_threshold == 0.65

    # Provenance and values
    first = result.chunks[0]
    assert first.chunk_id == chunk_id_1
    assert first.document_id == doc_id
    assert first.document_title == "Travel Policy v1"
    assert "Daily meal per diem" in first.chunk_text
    assert first.similarity_score == 0.892
    assert first.page_number == 2
    assert first.section_title == "2.1 Meal Per Diem"
    assert first.document_version == "1.0"


def test_02_query_embedding_integration():
    """
    Scenario 2: Validates that query embedding service is invoked with the cleaned query.
    """
    mock_db = make_mock_db_session([])
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    raw_query = "   How do I submit expense receipts?   \n"
    service.retrieve_chunks(db=mock_db, query=raw_query)

    # Embedding service must be called with stripped query
    mock_embedder.embed_query.assert_called_once_with("How do I submit expense receipts?")


def test_03_correct_database_function_invocation():
    """
    Scenario 3: Validates that the existing match_policy_chunks SQL function is invoked
    with correct pgvector parameter bindings, target_date, match_threshold, and match_count.
    """
    mock_db = make_mock_db_session([])
    dummy_vec = make_dummy_384_vector(seed=10)
    mock_embedder = make_mock_embedding_service(vector=dummy_vec)
    service = RetrievalService(embedding_service=mock_embedder)

    target_d = date(2025, 6, 15)
    service.retrieve_chunks(
        db=mock_db,
        query="Remote work policy guidelines",
        top_k=8,
        similarity_threshold=0.70,
        target_date=target_d,
    )

    mock_db.execute.assert_called_once()
    call_args, _ = mock_db.execute.call_args
    sql_clause, params = call_args[0], call_args[1]

    # Verify SQL calls match_policy_chunks
    assert "match_policy_chunks" in str(sql_clause)
    assert "cast(:query_embedding as vector)" in str(sql_clause)

    # Verify parameter bindings
    assert params["match_count"] == 8
    assert params["match_threshold"] == 0.70
    assert params["target_date"] == target_d
    assert params["query_embedding"].startswith("[") and params["query_embedding"].endswith("]")
    assert len(params["query_embedding"].split(",")) == 384


def test_04_top_k_behavior_and_defaults():
    """
    Scenario 4: Validates default top_k=5, custom top_k, and rejection of invalid values.
    """
    mock_db = make_mock_db_session([])
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    # 1. Default top_k is 5
    res = service.retrieve_chunks(db=mock_db, query="Any question")
    assert res.top_k == 5

    # 2. Custom top_k is applied
    res2 = service.retrieve_chunks(db=mock_db, query="Any question", top_k=10)
    assert res2.top_k == 10

    # 3. Invalid top_k rejected (<= 0, non-int, boolean)
    with pytest.raises(InvalidRetrievalParameterError) as exc_zero:
        service.retrieve_chunks(db=mock_db, query="Valid query", top_k=0)
    assert "positive integer" in str(exc_zero.value).lower()

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="Valid query", top_k=-3)

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="Valid query", top_k=True)  # type: ignore

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="Valid query", top_k="five")  # type: ignore


def test_05_empty_search_results():
    """
    Scenario 5: Validates that when no chunks meet the threshold, an empty result
    list is returned gracefully without throwing errors.
    """
    mock_db = make_mock_db_session([])  # Zero rows returned
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    result = service.retrieve_chunks(db=mock_db, query="Obscure query returning no matches")

    assert isinstance(result, RetrievalResult)
    assert result.total_retrieved == 0
    assert result.chunks == []


def test_06_invalid_inputs_rejected():
    """
    Scenario 6: Validates rejection of empty queries, whitespace-only, and invalid thresholds.
    """
    mock_db = make_mock_db_session([])
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    # Empty and whitespace queries
    with pytest.raises(InvalidRetrievalParameterError) as exc_empty:
        service.retrieve_chunks(db=mock_db, query="")
    assert "cannot be empty" in str(exc_empty.value).lower()

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="   \t \n  ")

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query=None)  # type: ignore

    # Threshold validation (0.0 <= threshold <= 1.0)
    with pytest.raises(InvalidRetrievalParameterError) as exc_thresh:
        service.retrieve_chunks(db=mock_db, query="Valid query", similarity_threshold=1.5)
    assert "between 0.0 and 1.0" in str(exc_thresh.value)

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="Valid query", similarity_threshold=-0.1)

    with pytest.raises(InvalidRetrievalParameterError):
        service.retrieve_chunks(db=mock_db, query="Valid query", similarity_threshold="high")  # type: ignore


def test_07_database_errors_handled_and_sanitized():
    """
    Scenario 7: Validates that database failures raise RetrievalDatabaseError and
    credentials/secrets in connection strings are sanitized.
    """
    mock_db = MagicMock(spec=Session)
    mock_db.execute.side_effect = OperationalError(
        statement="SELECT * FROM match_policy_chunks(...)",
        params={},
        orig=Exception("connection to postgresql://postgres:super_secret_pg_pwd_99@aws.pooler.supabase.com:5432 failed"),
    )
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    with pytest.raises(RetrievalDatabaseError) as exc_info:
        service.retrieve_chunks(db=mock_db, query="Sample question")

    err_text = str(exc_info.value)
    # Ensure sensitive credentials are redacted
    assert "super_secret_pg_pwd_99" not in err_text
    assert "*****" in err_text
    assert "Database error during semantic retrieval" in err_text


def test_08_result_structure_and_provenance_preservation():
    """
    Scenario 8: Validates full provenance preservation: document title, version label,
    1-based page number for PDF, None page number for non-PDF, section title from hierarchy,
    and metadata JSON.
    """
    chunk_pdf_id = uuid.uuid4()
    chunk_docx_id = uuid.uuid4()

    mock_rows = [
        # PDF chunk with page_number and section_title in metadata
        {
            "chunk_id": str(chunk_pdf_id),
            "document_id": str(uuid.uuid4()),
            "document_title": "IT Security Policy.pdf",
            "version_number": "v2.0",
            "effective_date": date(2025, 1, 1),
            "sunset_date": None,
            "page_number": 5,
            "content": "Multi-factor authentication is mandatory for all SSO accounts.",
            "similarity": 0.915,
            "chunk_metadata": {
                "section_hierarchy": ["1.0 Authentication", "1.2 MFA Policy"],
            },
        },
        # DOCX chunk with NULL page_number and chunk_text column fallback
        {
            "chunk_id": str(chunk_docx_id),
            "document_id": None,
            "document_title": "HR Handbook.docx",
            "version_label": "1.0",
            "effective_date": date(2025, 1, 1),
            "sunset_date": None,
            "page_number": None,
            "chunk_text": "Core working hours are 10:00 AM to 4:00 PM local time.",
            "similarity": 0.824,
            "section_title": "Core Hours",
            "chunk_metadata": {"file_type": "docx"},
        },
    ]

    mock_db = make_mock_db_session(mock_rows)
    mock_embedder = make_mock_embedding_service()
    service = RetrievalService(embedding_service=mock_embedder)

    result = service.retrieve_chunks(db=mock_db, query="Working hours and security policies")
    assert result.total_retrieved == 2

    # Chunk 1 (PDF)
    c1 = result.chunks[0]
    assert c1.chunk_id == chunk_pdf_id
    assert c1.document_title == "IT Security Policy.pdf"
    assert c1.page_number == 5
    assert c1.section_title == "1.2 MFA Policy"  # Resolved from last element of hierarchy
    assert c1.document_version == "v2.0"
    assert c1.similarity_score == 0.915

    # Chunk 2 (DOCX)
    c2 = result.chunks[1]
    assert c2.chunk_id == chunk_docx_id
    assert c2.document_id is None
    assert c2.page_number is None  # Strictly None for DOCX
    assert c2.section_title == "Core Hours"
    assert c2.document_version == "1.0"
    assert c2.similarity_score == 0.824
    assert c2.chunk_text == "Core working hours are 10:00 AM to 4:00 PM local time."


def test_09_embedding_error_propagation():
    """
    Scenario 9: Validates that when embedding service fails, RetrievalError is raised cleanly.
    """
    mock_db = make_mock_db_session([])
    mock_embedder = MagicMock(spec=EmbeddingService)
    mock_embedder.embed_query.side_effect = EmbeddingGenerationError("Model inference device out of memory")
    service = RetrievalService(embedding_service=mock_embedder)

    with pytest.raises(RetrievalError) as exc_info:
        service.retrieve_chunks(db=mock_db, query="Any valid question")
    assert "Query embedding generation failed" in str(exc_info.value)
    assert "out of memory" in str(exc_info.value)


def test_10_fastapi_dependency_provider():
    """
    Scenario 10: Validates that get_retrieval_service dependency returns a working service.
    """
    mock_embedder = make_mock_embedding_service()
    service = get_retrieval_service(embedding_service=mock_embedder)
    assert isinstance(service, RetrievalService)
    assert service.default_top_k == 5
    assert service.default_threshold == 0.65
