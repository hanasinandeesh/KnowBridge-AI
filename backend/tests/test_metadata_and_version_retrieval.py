"""
Targeted Unit Tests for Metadata Filtering and Version-Aware Retrieval.
Task 04D — KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Category metadata filtering (case-insensitive).
2. Department metadata filtering (case-insensitive).
3. Excluding failed, processing, and incomplete documents.
4. Correct current-version retrieval (excluding obsolete historical revisions).
5. Historical date retrieval (retrieving the version active on the requested past date).
6. Effective-date boundary conditions (inclusive on effective_from and effective_until).
7. Specific version label retrieval (e.g. '1.0' vs 'v1.0').
8. Detection and reporting of version ambiguity and overlaps without evidence loss.
9. Combined metadata filters with semantic similarity ranking.
10. Full provenance preservation across document, version, section, and page fields.
"""

import math
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.schemas.retrieval import RetrievalResult, RetrievedChunk
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService


# ---------------------------------------------------------------------------
# Test Helpers & Mock Fixtures
# ---------------------------------------------------------------------------

def make_dummy_vector(seed: int = 1) -> list[float]:
    """Generates a normalized 384-dimensional unit vector."""
    raw = [math.sin(seed + i) for i in range(384)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def make_mock_embedding_service() -> MagicMock:
    """Creates a mock EmbeddingService returning valid 384-dimensional vector."""
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.dimension = 384
    mock_service.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_service.normalize_embeddings = True
    mock_service.embed_query.return_value = make_dummy_vector()
    return mock_service


def make_retrieval_row(
    chunk_id: uuid.UUID = None,
    doc_id: uuid.UUID = None,
    title: str = "Enterprise Policy",
    category: str = "general",
    department: str = "Corporate",
    doc_status: str = "completed",
    version_label: str = "1.0",
    is_current: bool = True,
    effective_from: date = date(2025, 1, 1),
    effective_until: date = None,
    content: str = "Policy clause text",
    similarity: float = 0.85,
    page_number: int = 1,
    section_title: str = "1.0 Purpose",
) -> dict:
    """Creates a comprehensive row simulating match_policy_chunks + document join."""
    return {
        "chunk_id": chunk_id or uuid.uuid4(),
        "document_id": doc_id or uuid.uuid4(),
        "document_title": title,
        "category": category,
        "department": department,
        "document_status": doc_status,
        "version_id": uuid.uuid4(),
        "version_number": version_label,
        "version_label": version_label,
        "is_current": is_current,
        "effective_date": effective_from,
        "effective_from": effective_from,
        "sunset_date": effective_until,
        "effective_until": effective_until,
        "page_number": page_number,
        "content": content,
        "similarity": similarity,
        "section_title": section_title,
        "chunk_metadata": {
            "category": category,
            "department": department,
            "document_status": doc_status,
            "version_label": version_label,
            "is_current": is_current,
            "effective_from": effective_from,
            "effective_until": effective_until,
            "section_title": section_title,
            "section_hierarchy": ["Enterprise Policies", section_title],
        },
    }


def make_mock_session(rows: list[dict]) -> MagicMock:
    """Creates a mock Session returning specified row mappings."""
    mock_session = MagicMock(spec=Session)
    mock_result = MagicMock()
    mock_mappings = MagicMock()
    mock_mappings.all.return_value = rows
    mock_result.mappings.return_value = mock_mappings
    mock_session.execute.return_value = mock_result
    return mock_session


# ---------------------------------------------------------------------------
# Unit Test Scenarios for Task 04D
# ---------------------------------------------------------------------------

def test_01_category_filtering():
    """
    Scenario 1: Validates that category filtering restricts retrieval to the requested
    category (case-insensitively) and excludes other categories.
    """
    rows = [
        make_retrieval_row(title="HR Leave Policy", category="HR", content="Annual leave is 20 days."),
        make_retrieval_row(title="IT Access Policy", category="IT", content="SSH keys must be rotated."),
        make_retrieval_row(title="Finance Expense Policy", category="Finance", content="Per diem meal allowance $75."),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Filter for Finance (case-insensitive)
    result = service.retrieve_chunks(db=mock_db, query="What are the expense rules?", category="finance")

    assert result.total_retrieved == 1
    assert result.chunks[0].category == "Finance"
    assert "Per diem meal allowance" in result.chunks[0].chunk_text
    assert result.category_filter == "finance"


def test_02_department_filtering():
    """
    Scenario 2: Validates that department filtering isolates chunks from the requested department.
    """
    rows = [
        make_retrieval_row(title="Travel Policy", department="People Operations", content="Travel reimbursement SOP."),
        make_retrieval_row(title="Procurement Guide", department="Finance & Accounting", content="Vendor PO approval."),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    result = service.retrieve_chunks(
        db=mock_db,
        query="PO approval rules",
        department="finance & accounting",
    )

    assert result.total_retrieved == 1
    assert result.chunks[0].department == "Finance & Accounting"
    assert "Vendor PO approval" in result.chunks[0].chunk_text
    assert result.department_filter == "finance & accounting"


def test_03_excluding_failed_and_incomplete_documents():
    """
    Scenario 3: Validates that chunks belonging to documents with status 'failed', 'processing',
    or 'corrupted' are excluded from retrieval results.
    """
    rows = [
        make_retrieval_row(title="Good Doc", doc_status="completed", content="Valid active clause."),
        make_retrieval_row(title="Failed Doc", doc_status="failed", content="Partial extraction junk."),
        make_retrieval_row(title="Pending Doc", doc_status="processing", content="In-flight extraction."),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    result = service.retrieve_chunks(db=mock_db, query="Valid clauses")

    assert result.total_retrieved == 1
    assert result.chunks[0].document_title == "Good Doc"


def test_04_current_version_retrieval_excludes_historical():
    """
    Scenario 4: For ordinary current questions, validates that obsolete historical
    versions (is_current=False) are excluded in favor of current active versions (is_current=True).
    """
    doc_id = uuid.uuid4()
    rows = [
        # Obsolete v1.0
        make_retrieval_row(
            doc_id=doc_id,
            title="Travel Policy",
            version_label="1.0",
            is_current=False,
            effective_from=date(2022, 1, 1),
            effective_until=date(2023, 12, 31),
            content="Old policy: meal per diem is $50.",
            similarity=0.92,
        ),
        # Current active v2.0
        make_retrieval_row(
            doc_id=doc_id,
            title="Travel Policy",
            version_label="2.0",
            is_current=True,
            effective_from=date(2024, 1, 1),
            effective_until=None,
            content="Current policy: meal per diem is $75.",
            similarity=0.88,
        ),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Default current query
    result = service.retrieve_chunks(db=mock_db, query="What is the meal allowance per diem?")

    assert result.total_retrieved == 1
    assert result.chunks[0].document_version == "2.0"
    assert "Current policy: meal per diem is $75" in result.chunks[0].chunk_text
    assert result.is_current_only is True


def test_05_historical_date_retrieval():
    """
    Scenario 5: When a historical date is requested, retrieves the version that was active
    on that date, even though it is not current today.
    """
    doc_id = uuid.uuid4()
    rows = [
        # v1.0 was active in 2023
        make_retrieval_row(
            doc_id=doc_id,
            title="Health Benefits",
            version_label="1.0",
            is_current=False,
            effective_from=date(2022, 1, 1),
            effective_until=date(2023, 12, 31),
            content="2023 benefits: Dental coverage is $1,000 annually.",
        ),
        # v2.0 was active from 2024 onwards
        make_retrieval_row(
            doc_id=doc_id,
            title="Health Benefits",
            version_label="2.0",
            is_current=True,
            effective_from=date(2024, 1, 1),
            effective_until=None,
            content="2024 benefits: Dental coverage increased to $1,500 annually.",
        ),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Query asking about policy as of June 2023
    historical_date = date(2023, 6, 15)
    result = service.retrieve_chunks(
        db=mock_db,
        query="What was the dental benefit allowance?",
        target_date=historical_date,
    )

    assert result.total_retrieved == 1
    assert result.chunks[0].document_version == "1.0"
    assert "$1,000 annually" in result.chunks[0].chunk_text
    assert result.is_current_only is False
    assert result.target_date == historical_date


def test_06_effective_date_boundary_conditions():
    """
    Scenario 6: Validates boundary conditions for effective_from and effective_until:
    - Inclusive on start date (effective_from == target_date)
    - Inclusive on end date (effective_until == target_date)
    - Excluded before start date
    - Excluded after sunset date
    """
    v_start = date(2025, 1, 1)
    v_end = date(2025, 12, 31)

    row = make_retrieval_row(
        title="Leave Policy",
        effective_from=v_start,
        effective_until=v_end,
        is_current=False,
        content="2025 Annual Leave Schedule",
    )
    mock_db = make_mock_session([row])
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # 1. Exact start date boundary -> INCLUDED
    res_start = service.retrieve_chunks(db=mock_db, query="Leave", target_date=v_start, is_current_only=False)
    assert res_start.total_retrieved == 1

    # 2. Exact end date boundary -> INCLUDED
    res_end = service.retrieve_chunks(db=mock_db, query="Leave", target_date=v_end, is_current_only=False)
    assert res_end.total_retrieved == 1

    # 3. One day before start -> EXCLUDED
    res_pre = service.retrieve_chunks(db=mock_db, query="Leave", target_date=date(2024, 12, 31), is_current_only=False)
    assert res_pre.total_retrieved == 0

    # 4. One day after end -> EXCLUDED
    res_post = service.retrieve_chunks(db=mock_db, query="Leave", target_date=date(2026, 1, 1), is_current_only=False)
    assert res_post.total_retrieved == 0


def test_07_specific_version_label_retrieval():
    """
    Scenario 7: Validates explicit version retrieval (e.g. version='1.0' or 'v1.0')
    retrieves that version regardless of current active status.
    """
    doc_id = uuid.uuid4()
    rows = [
        make_retrieval_row(doc_id=doc_id, version_label="1.0", is_current=False, content="Version 1.0 guidelines"),
        make_retrieval_row(doc_id=doc_id, version_label="2.0", is_current=True, content="Version 2.0 guidelines"),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Request version='v1.0' (tests semantic 'v' prefix normalization)
    result = service.retrieve_chunks(db=mock_db, query="Guidelines", version="v1.0")

    assert result.total_retrieved == 1
    assert result.chunks[0].document_version == "1.0"
    assert "Version 1.0 guidelines" in result.chunks[0].chunk_text
    assert result.version_filter == "v1.0"


def test_08_overlapping_and_ambiguous_version_reporting():
    """
    Scenario 8: If multiple versions overlap or applicability cannot be established,
    preserves all candidate evidence and reports the ambiguity in audit notes.
    """
    doc_id = uuid.uuid4()
    rows = [
        # Two versions overlapping for the same document on target date
        make_retrieval_row(
            doc_id=doc_id,
            title="Security SOP",
            version_label="1.5",
            effective_from=date(2025, 1, 1),
            effective_until=date(2025, 12, 31),
            is_current=True,
            content="Version 1.5 SOP clause",
        ),
        make_retrieval_row(
            doc_id=doc_id,
            title="Security SOP",
            version_label="2.0",
            effective_from=date(2025, 6, 1),
            effective_until=date(2026, 6, 1),
            is_current=True,
            content="Version 2.0 SOP clause",
        ),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Query for date where both versions claim applicability
    result = service.retrieve_chunks(
        db=mock_db,
        query="SOP clause",
        target_date=date(2025, 8, 1),
    )

    # Both chunks are preserved (no evidence lost)
    assert result.total_retrieved == 2
    # Ambiguity is reported
    assert result.has_version_ambiguity is True
    assert len(result.ambiguity_notes) == 1
    assert "overlapping versions (1.5, 2.0)" in result.ambiguity_notes[0]
    # Each chunk carries ambiguity flag
    assert all(c.is_ambiguous is True for c in result.chunks)


def test_09_combining_metadata_filters_with_semantic_search():
    """
    Scenario 9: Combines category, department, version, and threshold filters simultaneously.
    """
    rows = [
        # Match all filters
        make_retrieval_row(
            category="IT",
            department="Cybersecurity",
            version_label="3.0",
            is_current=True,
            content="Zero-trust access policy requirement.",
            similarity=0.88,
        ),
        # Wrong category
        make_retrieval_row(
            category="HR",
            department="Cybersecurity",
            version_label="3.0",
            is_current=True,
            content="Wrong category clause.",
            similarity=0.89,
        ),
        # Wrong department
        make_retrieval_row(
            category="IT",
            department="Helpdesk",
            version_label="3.0",
            is_current=True,
            content="Wrong department clause.",
            similarity=0.87,
        ),
    ]
    mock_db = make_mock_session(rows)
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    result = service.retrieve_chunks(
        db=mock_db,
        query="Zero trust requirements",
        category="it",
        department="cybersecurity",
        version="3.0",
        similarity_threshold=0.80,
    )

    assert result.total_retrieved == 1
    assert result.chunks[0].chunk_text == "Zero-trust access policy requirement."
    assert result.chunks[0].category == "IT"
    assert result.chunks[0].department == "Cybersecurity"


def test_10_provenance_preservation():
    """
    Scenario 10: Validates that all provenance attributes (title, version, page,
    section, text, score, effective dates) are preserved accurately.
    """
    c_id = uuid.uuid4()
    d_id = uuid.uuid4()

    row = make_retrieval_row(
        chunk_id=c_id,
        doc_id=d_id,
        title="Enterprise Conduct Code",
        category="Compliance",
        department="Legal",
        version_label="v4.2",
        is_current=True,
        effective_from=date(2025, 3, 1),
        effective_until=date(2027, 3, 1),
        content="Conflict of interest disclosure is mandatory.",
        similarity=0.876543,
        page_number=14,
        section_title="4.2 Conflict of Interest",
    )
    mock_db = make_mock_session([row])
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    result = service.retrieve_chunks(db=mock_db, query="Conflict of interest")

    assert result.total_retrieved == 1
    chunk = result.chunks[0]
    assert chunk.chunk_id == c_id
    assert chunk.document_id == d_id
    assert chunk.document_title == "Enterprise Conduct Code"
    assert chunk.category == "Compliance"
    assert chunk.department == "Legal"
    assert chunk.document_version == "v4.2"
    assert chunk.is_current is True
    assert chunk.effective_from == date(2025, 3, 1)
    assert chunk.effective_until == date(2027, 3, 1)
    assert chunk.page_number == 14
    assert chunk.section_title == "4.2 Conflict of Interest"
    assert chunk.chunk_text == "Conflict of interest disclosure is mandatory."
    assert chunk.similarity_score == 0.876543
    assert chunk.is_ambiguous is False
