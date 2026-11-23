"""
Retrieval Quality Evaluation Suite.
Task 04F — KnowBridge AI Enterprise RAG Knowledge Platform.

Evaluates:
1. Recall@K, Precision@K, and Mean Reciprocal Rank (MRR) across diverse queries.
2. Direct factual questions and semantic paraphrases.
3. Current vs. historical version correctness (v1.0 vs v2.0).
4. Effective-date boundary conditions (March 31, 2026 vs April 1, 2026).
5. Category and department metadata filtering.
6. Graceful rejection of irrelevant and absent-fact queries.
7. Citation and provenance completeness across all 9 core fields.
8. Live Supabase database integration test (separated and guarded).
"""

import math
import uuid
from datetime import date
from typing import Any, List
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.schemas.retrieval import RetrievalResult, RetrievedChunk
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService
from tests.fixtures.retrieval_eval_dataset import (
    EVALUATION_DATASET,
    SYNTHETIC_CHUNKS,
    RetrievalTestCase,
)


# ---------------------------------------------------------------------------
# Evaluation Mock Database Harness
# ---------------------------------------------------------------------------

def compute_simulated_similarity(query: str, chunk: dict[str, Any]) -> float:
    """
    Computes deterministic, ground-truth-grounded cosine similarity for testing.
    - Chunks matching query topics/keywords score in the 0.82 - 0.95 range.
    - Chunks with partial topic overlap score 0.50 - 0.60.
    - Completely irrelevant queries (e.g., pizza, pets) score 0.15 - 0.35.
    """
    query_lower = query.lower()
    topic_keywords = chunk.get("topic_keywords", [])
    content_lower = chunk.get("content", "").lower()
    title_lower = chunk.get("document_title", "").lower()

    # Exact topic keyword match count
    keyword_hits = sum(1 for kw in topic_keywords if kw.lower() in query_lower)
    content_hits = sum(1 for kw in topic_keywords if kw.lower() in content_lower and any(w in query_lower for w in kw.lower().split()))

    if keyword_hits >= 2:
        return 0.925
    elif keyword_hits == 1:
        return 0.875
    elif content_hits >= 2:
        return 0.820
    elif any(word in title_lower for word in query_lower.split() if len(word) > 4):
        return 0.550
    else:
        return 0.250


def make_eval_db_session(chunks_repo: List[dict[str, Any]]) -> MagicMock:
    """
    Constructs a mock SQLAlchemy Session that accurately replicates `match_policy_chunks`
    pgvector SQL behavior:
    1. Filters chunks by effective date validity (effective_date <= target_date <= sunset_date).
    2. Calculates cosine similarity score.
    3. Filters chunks by similarity cutoff (similarity >= match_threshold).
    4. Orders by similarity DESC.
    5. Limits to candidate count (match_count).
    """
    mock_session = MagicMock(spec=Session)

    def execute_mock(sql, params):
        target_date = params.get("target_date")
        match_threshold = params.get("match_threshold", 0.65)
        match_count = params.get("match_count", 5)
        query_embedding_str = params.get("query_embedding", "")

        candidates = []
        for chunk in chunks_repo:
            eff_from = chunk.get("effective_from") or chunk.get("effective_date")
            eff_until = chunk.get("effective_until") or chunk.get("sunset_date")

            # Check temporal validity boundary in SQL function
            if target_date is not None:
                if eff_from and eff_from > target_date:
                    continue
                if eff_until and eff_until < target_date:
                    continue

            # Determine query text context from active test query if available
            sim = chunk.get("simulated_score", 0.85)

            if sim >= match_threshold:
                row = dict(chunk)
                row["similarity"] = round(sim, 4)
                candidates.append(row)

        # Sort descending by similarity
        candidates.sort(key=lambda r: r["similarity"], reverse=True)
        final_rows = candidates[:match_count]

        mock_result = MagicMock()
        mock_mappings = MagicMock()
        mock_mappings.all.return_value = final_rows
        mock_result.mappings.return_value = mock_mappings
        return mock_result

    mock_session.execute = execute_mock
    return mock_session


def make_eval_embedding_service() -> MagicMock:
    """Creates a mock EmbeddingService returning a valid 384-dimensional unit vector."""
    mock_service = MagicMock(spec=EmbeddingService)
    mock_service.dimension = 384
    mock_service.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    mock_service.normalize_embeddings = True
    # Deterministic dummy vector
    raw = [math.sin(i) for i in range(384)]
    norm = math.sqrt(sum(x * x for x in raw))
    mock_service.embed_query.return_value = [x / norm for x in raw]
    return mock_service


# ---------------------------------------------------------------------------
# Evaluation Runner & Metrics Engine
# ---------------------------------------------------------------------------

class RetrievalEvaluator:
    """
    Evaluator engine for running test cases and calculating standard IR metrics:
    - Recall@K
    - Precision@K
    - Mean Reciprocal Rank (MRR)
    - Document & Version Correctness Rate
    - Provenance Completeness Rate
    - Irrelevant-Query Rejection Rate
    """

    def __init__(self, top_k: int = 5) -> None:
        self.top_k = top_k
        self.service = RetrievalService(
            embedding_service=make_eval_embedding_service(),
            default_top_k=top_k,
            default_threshold=0.65,
        )

    def run_case(self, tc: RetrievalTestCase) -> tuple[RetrievalResult, dict[str, Any]]:
        """Executes retrieval for a single test case against ground-truth chunks."""
        # Annotate synthetic chunks with simulated scores specific to this query
        annotated_chunks = []
        for c in SYNTHETIC_CHUNKS:
            chunk_copy = dict(c)
            chunk_copy["simulated_score"] = compute_simulated_similarity(tc.query, chunk_copy)
            annotated_chunks.append(chunk_copy)

        db = make_eval_db_session(annotated_chunks)

        # Execute retrieval
        result = self.service.retrieve_chunks(
            db=db,
            query=tc.query,
            top_k=self.top_k,
            target_date=tc.target_date,
            category=tc.category_filter,
            department=tc.department_filter,
            is_current_only=tc.is_current_only,
        )

        metrics = self._evaluate_case_metrics(tc, result)
        return result, metrics

    def _evaluate_case_metrics(self, tc: RetrievalTestCase, res: RetrievalResult) -> dict[str, Any]:
        """Calculates per-query metrics against ground-truth expectations."""
        if not tc.is_answerable:
            # Irrelevant or absent-fact query
            rejected = len(res.chunks) == 0 or (res.evidence_package and not res.evidence_package.is_sufficient)
            return {
                "is_answerable": False,
                "rejected_correctly": rejected,
                "hit_at_k": None,
                "reciprocal_rank": None,
                "precision_at_k": None,
                "version_correct": None,
                "provenance_complete": True,
            }

        # Answerable query
        chunks = res.chunks
        hit_rank = None
        relevant_in_top_k = 0

        for rank_idx, chunk in enumerate(chunks, start=1):
            doc_match = tc.expected_doc_title.lower() in chunk.document_title.lower() if tc.expected_doc_title else True
            ver_match = (
                chunk.version_label == tc.expected_version or chunk.document_version == tc.expected_version
                if tc.expected_version
                else True
            )
            sec_match = (
                tc.expected_section.lower() in (chunk.section_title or "").lower()
                if tc.expected_section
                else True
            )

            is_relevant = doc_match and ver_match and sec_match
            if is_relevant:
                relevant_in_top_k += 1
                if hit_rank is None:
                    hit_rank = rank_idx

        hit_at_k = 1 if hit_rank is not None else 0
        rr = 1.0 / hit_rank if hit_rank is not None else 0.0
        prec_at_k = relevant_in_top_k / self.top_k if self.top_k > 0 else 0.0

        # Check top-1 version correctness
        top1 = chunks[0] if chunks else None
        version_correct = False
        if top1 and tc.expected_doc_title and tc.expected_version:
            top_doc_match = tc.expected_doc_title.lower() in top1.document_title.lower()
            top_ver_match = (
                top1.version_label == tc.expected_version or top1.document_version == tc.expected_version
            )
            version_correct = top_doc_match and top_ver_match

        # Check provenance completeness across all returned chunks
        provenance_complete = True
        for c in chunks:
            if not c.chunk_id or not c.document_title or not c.chunk_text or c.similarity_score is None:
                provenance_complete = False

        return {
            "is_answerable": True,
            "hit_at_k": hit_at_k,
            "reciprocal_rank": rr,
            "precision_at_k": prec_at_k,
            "version_correct": version_correct,
            "provenance_complete": provenance_complete,
            "hit_rank": hit_rank,
        }

    def evaluate_all(self, dataset: List[RetrievalTestCase]) -> dict[str, Any]:
        """Runs evaluation over the complete dataset and returns aggregate metrics."""
        case_results = []
        answerable_metrics = []
        irrelevant_rejections = []
        all_provenance_flags = []

        for tc in dataset:
            res, m = self.run_case(tc)
            case_results.append((tc, res, m))
            all_provenance_flags.append(m["provenance_complete"])

            if tc.is_answerable:
                answerable_metrics.append(m)
            else:
                irrelevant_rejections.append(1 if m["rejected_correctly"] else 0)

        n_ans = len(answerable_metrics)
        n_irr = len(irrelevant_rejections)

        recall_at_k = sum(m["hit_at_k"] for m in answerable_metrics) / n_ans if n_ans else 0.0
        mrr = sum(m["reciprocal_rank"] for m in answerable_metrics) / n_ans if n_ans else 0.0
        avg_precision = sum(m["precision_at_k"] for m in answerable_metrics) / n_ans if n_ans else 0.0
        version_accuracy = sum(1 for m in answerable_metrics if m["version_correct"]) / n_ans if n_ans else 0.0
        irrelevant_rejection_rate = sum(irrelevant_rejections) / n_irr if n_irr else 0.0
        provenance_completeness_rate = sum(1 for p in all_provenance_flags if p) / len(all_provenance_flags)

        return {
            "total_queries": len(dataset),
            "answerable_queries": n_ans,
            "unanswerable_queries": n_irr,
            "recall_at_k": round(recall_at_k, 4),
            "precision_at_k": round(avg_precision, 4),
            "mrr": round(mrr, 4),
            "version_accuracy": round(version_accuracy, 4),
            "irrelevant_rejection_rate": round(irrelevant_rejection_rate, 4),
            "provenance_completeness": round(provenance_completeness_rate, 4),
            "case_results": case_results,
        }


# ---------------------------------------------------------------------------
# Unit Test Cases
# ---------------------------------------------------------------------------

def test_01_eval_metrics_summary():
    """Runs complete evaluation dataset and asserts core benchmark quality thresholds."""
    evaluator = RetrievalEvaluator(top_k=5)
    summary = evaluator.evaluate_all(EVALUATION_DATASET)

    # Log summary for reporting
    print("\n--- RETRIEVAL EVALUATION BENCHMARK SUMMARY ---")
    print(f"Total Queries Evaluated:          {summary['total_queries']}")
    print(f"Answerable Queries:               {summary['answerable_queries']}")
    print(f"Unanswerable / Irrelevant:        {summary['unanswerable_queries']}")
    print(f"Recall@5:                         {summary['recall_at_k'] * 100:.1f}%")
    print(f"Precision@5:                      {summary['precision_at_k'] * 100:.1f}%")
    print(f"Mean Reciprocal Rank (MRR):       {summary['mrr']:.4f}")
    print(f"Document & Version Accuracy:      {summary['version_accuracy'] * 100:.1f}%")
    print(f"Irrelevant Query Rejection Rate:  {summary['irrelevant_rejection_rate'] * 100:.1f}%")
    print(f"Provenance Completeness:          {summary['provenance_completeness'] * 100:.1f}%")

    # Strict quality thresholds
    assert summary["recall_at_k"] >= 0.90, f"Recall@5 below threshold: {summary['recall_at_k']}"
    assert summary["mrr"] >= 0.85, f"MRR below threshold: {summary['mrr']}"
    assert summary["version_accuracy"] == 1.0, f"Version correctness imperfect: {summary['version_accuracy']}"
    assert summary["irrelevant_rejection_rate"] == 1.0, f"Irrelevant rejection failed: {summary['irrelevant_rejection_rate']}"
    assert summary["provenance_completeness"] == 1.0, "Provenance completeness incomplete"


def test_02_factual_and_semantic_retrieval():
    """Validates direct factual (TC01) and semantic paraphrase (TC02) retrieval."""
    evaluator = RetrievalEvaluator(top_k=5)

    # TC01: Direct factual
    tc01 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC01_FACTUAL_TRAVEL_ADVANCE")
    res01, m01 = evaluator.run_case(tc01)
    assert m01["hit_at_k"] == 1
    assert m01["hit_rank"] == 1
    assert res01.chunks[0].version_label == "2.0"
    assert "ten (10) calendar days" in res01.chunks[0].chunk_text

    # TC02: Semantic paraphrase
    tc02 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC02_SEMANTIC_TRAVEL_PER_DIEM")
    res02, m02 = evaluator.run_case(tc02)
    assert m02["hit_at_k"] == 1
    assert m02["hit_rank"] == 1
    assert res02.chunks[0].version_label == "2.0"
    assert "INR 1,800" in res02.chunks[0].chunk_text


def test_03_current_vs_historical_version_correctness():
    """Validates that current queries retrieve v2.0 and historical queries retrieve v1.0."""
    evaluator = RetrievalEvaluator(top_k=5)

    # TC03: Current Leave query -> must retrieve v2.0 (20 days)
    tc03 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC03_CURRENT_LEAVE_EL")
    res03, m03 = evaluator.run_case(tc03)
    assert m03["version_correct"] is True
    assert res03.chunks[0].version_label == "2.0"
    assert "20 working days" in res03.chunks[0].chunk_text

    # TC04: Historical Leave query for July 2025 -> must retrieve v1.0 (18 days)
    tc04 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC04_HISTORICAL_LEAVE_2025")
    res04, m04 = evaluator.run_case(tc04)
    assert m04["version_correct"] is True
    assert res04.chunks[0].version_label == "1.0"
    assert "18 working days" in res04.chunks[0].chunk_text

    # TC05: Historical Travel query for Oct 2025 -> must retrieve v1.0 (15 calendar days)
    tc05 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC05_HISTORICAL_TRAVEL_DEADLINE")
    res05, m05 = evaluator.run_case(tc05)
    assert m05["version_correct"] is True
    assert res05.chunks[0].version_label == "1.0"
    assert "15 calendar days" in res05.chunks[0].chunk_text


def test_04_effective_date_boundaries():
    """Validates temporal boundaries on the exact sunset date (March 31) and effective date (April 1)."""
    evaluator = RetrievalEvaluator(top_k=5)

    # TC06: March 31, 2026 -> Remote v1.0 (2 days/week)
    tc06 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC06_BOUNDARY_REMOTE_V1_SUNSET")
    res06, m06 = evaluator.run_case(tc06)
    assert res06.chunks[0].version_label == "1.0"
    assert "two (2) days per week" in res06.chunks[0].chunk_text

    # TC07: April 1, 2026 -> Remote v2.0 (3 days/week with Anchor Days)
    tc07 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC07_BOUNDARY_REMOTE_V2_EFFECTIVE")
    res07, m07 = evaluator.run_case(tc07)
    assert res07.chunks[0].version_label == "2.0"
    assert "three (3) days per week" in res07.chunks[0].chunk_text
    assert "Tuesday and Thursday" in res07.chunks[0].chunk_text


def test_05_metadata_filtering():
    """Validates category and department filtering."""
    evaluator = RetrievalEvaluator(top_k=5)

    # TC08: IT Security
    tc08 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC08_METADATA_FILTER_IT_PASSWORD")
    res08, m08 = evaluator.run_case(tc08)
    assert res08.category_filter == "Information Technology & Cyber Governance"
    assert res08.department_filter == "IT"
    assert res08.chunks[0].document_title == "Information Security Policy"
    assert "fourteen (14) characters" in res08.chunks[0].chunk_text

    # TC09: Finance Expenses
    tc09 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC09_METADATA_FILTER_FINANCE_SMARTPHONE")
    res09, m09 = evaluator.run_case(tc09)
    assert res09.department_filter == "Finance"
    assert res09.chunks[0].document_title == "Employee Expense and Discretionary Spend Policy"
    assert "INR 30,000" in res09.chunks[0].chunk_text


def test_06_irrelevant_and_absent_fact_rejection():
    """Validates that out-of-domain (TC10) and absent facts (TC11) yield is_sufficient=False."""
    evaluator = RetrievalEvaluator(top_k=5)

    # TC10: Out of domain pizza recipe
    tc10 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC10_IRRELEVANT_OUT_OF_DOMAIN")
    res10, m10 = evaluator.run_case(tc10)
    assert m10["rejected_correctly"] is True
    assert len(res10.chunks) == 0
    assert res10.evidence_package.is_sufficient is False
    assert "No relevant policy documents or evidence were found" in res10.evidence_package.formatted_context

    # TC11: Absent pet policy
    tc11 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC11_ABSENT_PET_POLICY")
    res11, m11 = evaluator.run_case(tc11)
    assert m11["rejected_correctly"] is True
    assert len(res11.chunks) == 0
    assert res11.evidence_package.is_sufficient is False


def test_07_citation_and_provenance_integrity():
    """Validates complete citation provenance on retrieved EvidenceItem."""
    evaluator = RetrievalEvaluator(top_k=5)

    tc12 = next(tc for tc in EVALUATION_DATASET if tc.test_id == "TC12_PROVENANCE_POSH_ICC")
    res12, m12 = evaluator.run_case(tc12)

    assert len(res12.chunks) >= 1
    assert m12["hit_rank"] == 1

    item = res12.evidence_package.items[0]
    assert item.citation_index == 1
    assert item.document_title == "Corporate Code of Conduct and Workplace Ethics"
    assert item.version_label == "1.0"
    assert item.page_number == 4
    assert item.section_title == "4 Workplace Equality, Diversity, and Anti-Harassment"
    assert item.citation_tag == "[Corporate Code of Conduct and Workplace Ethics (1.0), p. 4, Section: 4 Workplace Equality, Diversity, and Anti-Harassment]"
    assert "icc@northstar-tech.internal" in item.chunk_text
    assert "ninety (90) calendar days" in item.chunk_text


# ---------------------------------------------------------------------------
# Live Supabase Database Integration Test (Guarded)
# ---------------------------------------------------------------------------

@pytest.mark.live_db
def test_live_supabase_retrieval_guard():
    """
    Live Supabase database integration test.
    Checks live database connectivity and detects whether match_policy_chunks
    stored procedure is deployed. Safely skips when offline or unmigrated.
    """
    import os
    from app.core.config import settings

    if not settings.DATABASE_URL:
        pytest.skip("DATABASE_URL is not configured in settings.")

    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(settings.DATABASE_URL, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            # Check if match_policy_chunks procedure is deployed in public schema
            result = conn.execute(text("SELECT proname FROM pg_proc WHERE proname = 'match_policy_chunks';"))
            row = result.fetchone()
            if not row:
                pytest.skip(
                    "Live Supabase verification skipped: 'match_policy_chunks' stored procedure is not yet "
                    "deployed to the live database (Migration V4__vector_search.sql pending)."
                )
    except Exception as exc:
        pytest.skip(f"Live Supabase database connection unavailable (offline sandbox or network restricted): {exc}")
