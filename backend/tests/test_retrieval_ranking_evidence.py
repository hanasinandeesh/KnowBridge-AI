"""
Targeted Unit Tests for Retrieval Ranking and Evidence Formatting.
Task 04E — KnowBridge AI Enterprise RAG Knowledge Platform.

Validates:
1. Descending score ordering: Chunks are ordered strictly by descending similarity score.
2. Deterministic tie-breaking: Stable, deterministic ordering when scores are tied (current version first, title, page, UUID).
3. Duplicate chunk removal: Chunks with identical chunk_id are deduplicated.
4. Preservation of distinct similar chunks: Distinct chunks sharing similar or identical text are strictly preserved.
5. Configurable result limits: Enforces limit parameter and rejects invalid values (0, negative, non-int).
6. Preservation of citation metadata: Verifies all 9 provenance fields on EvidenceItem.
7. Missing optional provenance fields: Graceful handling when page_number, section_title, or version_label are None.
8. Empty result handling: Evidence package returns is_sufficient=False, total_evidence_count=0, and clean fallback text.
9. Version applicability in evidence package: Correct formatting of current vs historical versions in citation tags and context.
10. Direct invocation of format_evidence_package: Independent utility test for downstream pipeline nodes.
"""

import math
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult, RetrievedChunk
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import (
    InvalidRetrievalParameterError,
    RetrievalService,
)


# ---------------------------------------------------------------------------
# Test Helpers & Mock Fixtures
# ---------------------------------------------------------------------------

def make_dummy_vector(seed: int = 42) -> list[float]:
    """Generates a deterministic 384-dimensional unit vector."""
    raw = [math.sin(seed + i) for i in range(384)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


def make_mock_embedding_service() -> MagicMock:
    """Creates a mock EmbeddingService returning a valid 384-dimensional vector."""
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.dimension = 384
    mock_service.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_service.normalize_embeddings = True
    mock_service.embed_query.return_value = make_dummy_vector()
    return mock_service


def make_chunk_row(
    chunk_id: uuid.UUID = None,
    doc_id: uuid.UUID = None,
    title: str = "Enterprise Travel & Expense Policy",
    content: str = "Standard per diem meal allowance is $75 per day.",
    similarity: float = 0.852,
    page_number: int = 3,
    version_number: str = "1.0",
    is_current: bool = True,
    effective_from: date = date(2025, 1, 1),
    effective_until: date = None,
    section_title: str = "2.1 Meal Per Diem",
    doc_status: str = "completed",
    category: str = "Finance",
    department: str = "Corporate Travel",
) -> dict:
    """Creates a mock DB row matching match_policy_chunks return signature."""
    return {
        "chunk_id": chunk_id or uuid.uuid4(),
        "document_id": doc_id or uuid.uuid4(),
        "document_title": title,
        "version_id": uuid.uuid4(),
        "version_number": version_number,
        "version_label": version_number,
        "effective_date": effective_from,
        "effective_from": effective_from,
        "effective_until": effective_until,
        "sunset_date": effective_until,
        "page_number": page_number,
        "content": content,
        "chunk_text": content,
        "similarity": similarity,
        "is_current": is_current,
        "document_status": doc_status,
        "category": category,
        "department": department,
        "chunk_metadata": {
            "section_title": section_title,
            "section_hierarchy": [section_title] if section_title else [],
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
# Test Cases
# ---------------------------------------------------------------------------

def test_01_descending_score_ordering():
    """Retrieved chunks and evidence items must be ordered strictly by descending similarity score."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Rows with unsorted similarity scores
    rows = [
        make_chunk_row(content="Lowest score passage", similarity=0.710),
        make_chunk_row(content="Highest score passage", similarity=0.945),
        make_chunk_row(content="Medium score passage", similarity=0.830),
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(db, "What is the policy?", top_k=5)

    assert len(result.chunks) == 3
    scores = [c.similarity_score for c in result.chunks]
    assert scores == [0.945, 0.830, 0.710]
    assert result.chunks[0].chunk_text == "Highest score passage"
    assert result.chunks[2].chunk_text == "Lowest score passage"

    # Verify evidence package mirrors descending score order
    assert result.evidence_package is not None
    assert result.evidence_package.total_evidence_count == 3
    evidence_scores = [item.similarity_score for item in result.evidence_package.items]
    assert evidence_scores == [0.945, 0.830, 0.710]
    assert result.evidence_package.items[0].citation_index == 1
    assert result.evidence_package.items[0].chunk_text == "Highest score passage"


def test_02_deterministic_tie_breaking():
    """Equal similarity scores must be broken deterministically using version status, title, page, and chunk_id."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    id_a = uuid.UUID("11111111-1111-1111-1111-111111111111")
    id_b = uuid.UUID("22222222-2222-2222-2222-222222222222")
    id_c = uuid.UUID("33333333-3333-3333-3333-333333333333")

    # Three chunks with identical similarity (0.850):
    # - Chunk 1: Historical version (is_current=False), Title "Alpha Policy", page 1
    # - Chunk 2: Current version (is_current=True), Title "Beta Policy", page 5
    # - Chunk 3: Current version (is_current=True), Title "Alpha Policy", page 2
    # Expected ordering:
    # 1. Chunk 3: is_current=True, Title "Alpha Policy", page 2
    # 2. Chunk 2: is_current=True, Title "Beta Policy", page 5
    # 3. Chunk 1: is_current=False (ranked after current versions)
    rows = [
        make_chunk_row(
            chunk_id=id_a,
            title="Alpha Policy",
            content="Historical alpha",
            similarity=0.850,
            page_number=1,
            is_current=False,
            version_number="v1.0",
        ),
        make_chunk_row(
            chunk_id=id_b,
            title="Beta Policy",
            content="Current beta",
            similarity=0.850,
            page_number=5,
            is_current=True,
            version_number="v2.0",
        ),
        make_chunk_row(
            chunk_id=id_c,
            title="Alpha Policy",
            content="Current alpha",
            similarity=0.850,
            page_number=2,
            is_current=True,
            version_number="v2.0",
        ),
    ]
    db = make_mock_db_session(rows)

    # Use is_current_only=False so historical version is not filtered out prior to ranking
    result = service.retrieve_chunks(db, "policy terms", is_current_only=False, top_k=5)

    assert len(result.chunks) == 3
    assert result.chunks[0].chunk_id == id_c  # Current Alpha, p.2
    assert result.chunks[1].chunk_id == id_b  # Current Beta, p.5
    assert result.chunks[2].chunk_id == id_a  # Historical Alpha, p.1


def test_03_duplicate_chunk_removal():
    """Duplicate occurrences of the exact same chunk_id must be deduplicated to a single result."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    shared_chunk_id = uuid.UUID("44444444-4444-4444-4444-444444444444")
    other_chunk_id = uuid.UUID("55555555-5555-5555-5555-555555555555")

    # DB returns duplicate chunk_id twice (e.g. from version join overlap)
    rows = [
        make_chunk_row(chunk_id=shared_chunk_id, content="Duplicate passage", similarity=0.900),
        make_chunk_row(chunk_id=shared_chunk_id, content="Duplicate passage", similarity=0.900),
        make_chunk_row(chunk_id=other_chunk_id, content="Unique passage", similarity=0.800),
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(db, "deduplication test", top_k=5)

    assert len(result.chunks) == 2
    assert result.chunks[0].chunk_id == shared_chunk_id
    assert result.chunks[1].chunk_id == other_chunk_id
    assert result.evidence_package.total_evidence_count == 2
    assert [item.chunk_id for item in result.evidence_package.items] == [shared_chunk_id, other_chunk_id]


def test_04_preservation_of_distinct_similar_chunks():
    """Distinct chunks with different chunk_ids but identical or similar text must NOT be discarded."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # Two distinct chunks from different pages/sections sharing the same boilerplate notice
    shared_boilerplate = "Confidential & Proprietary. All rights reserved by Acme Corporation."
    chunk_1_id = uuid.uuid4()
    chunk_2_id = uuid.uuid4()

    rows = [
        make_chunk_row(
            chunk_id=chunk_1_id,
            content=shared_boilerplate,
            similarity=0.880,
            page_number=1,
            section_title="Disclaimer",
        ),
        make_chunk_row(
            chunk_id=chunk_2_id,
            content=shared_boilerplate,
            similarity=0.875,
            page_number=14,
            section_title="Appendix B",
        ),
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(db, "proprietary notice", top_k=5)

    assert len(result.chunks) == 2
    assert result.chunks[0].chunk_id == chunk_1_id
    assert result.chunks[1].chunk_id == chunk_2_id
    assert result.chunks[0].page_number == 1
    assert result.chunks[1].page_number == 14
    assert result.evidence_package.total_evidence_count == 2


def test_05_configurable_result_limits():
    """Enforces configurable limit parameter and rejects invalid inputs."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    # 5 available chunks
    rows = [
        make_chunk_row(content=f"Clause {i}", similarity=0.90 - (i * 0.05))
        for i in range(5)
    ]
    db = make_mock_db_session(rows)

    # 1. Specifying limit=2 should return exactly 2 items
    res_limited = service.retrieve_chunks(db, "test query", top_k=5, limit=2)
    assert len(res_limited.chunks) == 2
    assert res_limited.applied_limit == 2
    assert res_limited.total_retrieved == 2
    assert res_limited.evidence_package.total_evidence_count == 2
    assert len(res_limited.evidence_package.items) == 2

    # 2. Rejection of invalid limit values
    with pytest.raises(InvalidRetrievalParameterError, match="limit must be a positive integer"):
        service.retrieve_chunks(db, "test query", limit=0)

    with pytest.raises(InvalidRetrievalParameterError, match="limit must be a positive integer"):
        service.retrieve_chunks(db, "test query", limit=-3)

    with pytest.raises(InvalidRetrievalParameterError, match="limit must be a positive integer"):
        service.retrieve_chunks(db, "test query", limit="five")  # type: ignore


def test_06_preservation_of_all_citation_metadata():
    """All 9 core provenance fields must be preserved on EvidenceItem and RetrievedChunk."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    expected_chunk_id = uuid.uuid4()
    expected_doc_id = uuid.uuid4()
    eff_start = date(2025, 4, 1)
    eff_end = date(2027, 3, 31)

    rows = [
        make_chunk_row(
            chunk_id=expected_chunk_id,
            doc_id=expected_doc_id,
            title="Global Anti-Corruption & Bribery Policy",
            content="Employees must report any gift valued over $100.",
            similarity=0.8875,
            page_number=7,
            version_number="3.2",
            is_current=True,
            effective_from=eff_start,
            effective_until=eff_end,
            section_title="4.1 Gift Thresholds",
        )
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(db, "gift limit threshold", top_k=5)

    assert len(result.chunks) == 1
    chunk = result.chunks[0]

    # Verify all 9 provenance fields on RetrievedChunk
    assert chunk.chunk_id == expected_chunk_id
    assert chunk.document_id == expected_doc_id
    assert chunk.document_title == "Global Anti-Corruption & Bribery Policy"
    assert chunk.version_label == "3.2"
    assert chunk.document_version == "3.2"
    assert chunk.effective_from == eff_start
    assert chunk.effective_until == eff_end
    assert chunk.chunk_text == "Employees must report any gift valued over $100."
    assert chunk.similarity_score == 0.8875
    assert chunk.page_number == 7
    assert chunk.section_title == "4.1 Gift Thresholds"

    # Verify all 9 provenance fields on EvidenceItem
    evidence = result.evidence_package.items[0]
    assert evidence.citation_index == 1
    assert evidence.chunk_id == expected_chunk_id
    assert evidence.document_id == expected_doc_id
    assert evidence.document_title == "Global Anti-Corruption & Bribery Policy"
    assert evidence.version_label == "3.2"
    assert evidence.effective_from == eff_start
    assert evidence.effective_until == eff_end
    assert evidence.chunk_text == "Employees must report any gift valued over $100."
    assert evidence.similarity_score == 0.8875
    assert evidence.page_number == 7
    assert evidence.section_title == "4.1 Gift Thresholds"
    assert evidence.citation_tag == "[Global Anti-Corruption & Bribery Policy (3.2), p. 7, Section: 4.1 Gift Thresholds]"

    # Verify formatted context contains citation and score
    assert "[1] [Global Anti-Corruption & Bribery Policy (3.2), p. 7, Section: 4.1 Gift Thresholds]" in result.evidence_package.formatted_context
    assert "Employees must report any gift valued over $100." in result.evidence_package.formatted_context


def test_07_missing_optional_provenance_fields():
    """Handles missing optional provenance fields (DOCX without page numbers, missing sections) gracefully."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    chunk_id = uuid.uuid4()
    doc_id = uuid.uuid4()

    # Document without page_number (DOCX/TXT), section_title, or version_label
    rows = [
        {
            "chunk_id": chunk_id,
            "document_id": doc_id,
            "document_title": "Remote Work Guidelines",
            "version_id": None,
            "version_number": None,
            "version_label": None,
            "effective_date": None,
            "sunset_date": None,
            "page_number": None,  # No page for DOCX
            "content": "Eligible employees may work remotely up to two days per week.",
            "similarity": 0.795,
            "is_current": True,
            "document_status": "completed",
            "chunk_metadata": {},  # No section info
        }
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(db, "work from home frequency", top_k=5)

    assert len(result.chunks) == 1
    chunk = result.chunks[0]
    assert chunk.page_number is None
    assert chunk.section_title is None
    assert chunk.version_label is None

    evidence = result.evidence_package.items[0]
    assert evidence.page_number is None
    assert evidence.section_title is None
    assert evidence.version_label is None
    # Citation tag does not invent pages or sections
    assert evidence.citation_tag == "[Remote Work Guidelines]"
    assert "[1] [Remote Work Guidelines] (Similarity: 0.7950)" in result.evidence_package.formatted_context


def test_08_empty_retrieval_results():
    """Empty search results return a structured, safe evidence package with is_sufficient=False."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())
    db = make_mock_db_session([])

    result = service.retrieve_chunks(db, "unmatched obscure query", top_k=5)

    assert len(result.chunks) == 0
    assert result.total_retrieved == 0
    assert result.evidence_package is not None
    assert result.evidence_package.total_evidence_count == 0
    assert result.evidence_package.items == []
    assert result.evidence_package.is_sufficient is False
    assert "No relevant policy documents or evidence were found" in result.evidence_package.formatted_context


def test_09_historical_and_ambiguous_version_handling():
    """Evidence package correctly flags version ambiguity and preserves conflicting versions."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    doc_id = uuid.uuid4()
    # Overlapping versions for the same document on target date
    rows = [
        make_chunk_row(
            doc_id=doc_id,
            title="Parental Leave Policy",
            content="Version 1.0 provides 12 weeks of paid leave.",
            similarity=0.910,
            version_number="1.0",
            is_current=False,
            effective_from=date(2023, 1, 1),
            effective_until=date(2025, 12, 31),
        ),
        make_chunk_row(
            doc_id=doc_id,
            title="Parental Leave Policy",
            content="Version 2.0 provides 16 weeks of paid leave.",
            similarity=0.905,
            version_number="2.0",
            is_current=True,
            effective_from=date(2025, 1, 1),
            effective_until=None,
        ),
    ]
    db = make_mock_db_session(rows)

    result = service.retrieve_chunks(
        db,
        "How many weeks of parental leave?",
        target_date=date(2025, 6, 1),
        is_current_only=False,
        top_k=5,
    )

    assert len(result.chunks) == 2
    assert result.has_version_ambiguity is True
    assert result.evidence_package.has_conflicts is True
    assert result.evidence_package.total_evidence_count == 2
    # Verify version labels are distinctly preserved in evidence items
    versions = [item.version_label for item in result.evidence_package.items]
    assert "1.0" in versions
    assert "2.0" in versions


def test_10_format_evidence_package_direct_invocation():
    """format_evidence_package can be invoked directly as a modular evidence compilation helper."""
    service = RetrievalService(embedding_service=make_mock_embedding_service())

    chunk = RetrievedChunk(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title="Cybersecurity Incident Management",
        chunk_text="All severe data breaches must be reported within 24 hours.",
        similarity_score=0.9234,
        page_number=4,
        section_title="Incident Escalation",
        document_version="v1.1",
        version_label="v1.1",
        is_current=True,
    )

    pkg = service.format_evidence_package(
        query="breach reporting SLA",
        chunks=[chunk],
        limit=5,
        has_conflicts=False,
    )

    assert isinstance(pkg, EvidencePackage)
    assert pkg.total_evidence_count == 1
    assert pkg.is_sufficient is True
    assert pkg.has_conflicts is False
    assert pkg.applied_limit == 5
    assert len(pkg.items) == 1
    assert pkg.items[0].citation_index == 1
    assert pkg.items[0].citation_tag == "[Cybersecurity Incident Management (v1.1), p. 4, Section: Incident Escalation]"
    assert "[1] [Cybersecurity Incident Management (v1.1), p. 4, Section: Incident Escalation] (Similarity: 0.9234)" in pkg.formatted_context
    assert "All severe data breaches must be reported within 24 hours." in pkg.formatted_context
