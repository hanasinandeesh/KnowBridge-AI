"""
Deterministic Unit, Routing, Error-Handling, Checkpointing & Opt-in Integration
Tests for Task 05D — LangGraph RAG Orchestration.
"""

import os
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.graph.nodes import make_generate_answer_node
from app.graph.workflow import RAGOrchestrator
from app.schemas.answer_generation import (
    AnswerCitation,
    AnswerGenerationResult,
    AnswerStatus,
)
from app.schemas.evidence_assessment import (
    EvidenceAssessmentResult,
    EvidenceDecision,
    EvidenceReference,
    PolicyConflictItem,
    SupportLevel,
)
from app.schemas.orchestration import RAGWorkflowRequest
from app.schemas.query_understanding import (
    QueryIntent,
    QueryUnderstandingResult,
    RetrievalHints,
)
from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult
from app.services.answer_generation_service import (
    AnswerGenerationService,
    CitationValidationError,
)
from app.services.evidence_assessment_service import (
    AssessmentOutputValidationError,
    EvidenceAssessmentService,
)
from app.services.llm_client import LLMProviderError
from app.services.query_understanding_service import QueryUnderstandingService
from app.services.retrieval_service import RetrievalDatabaseError, RetrievalService


def _make_qu(
    query: str = "What is the domestic meal per diem?",
    intent: QueryIntent = QueryIntent.POLICY_LOOKUP,
    needs_clarification: bool = False,
    clarification_reason: str | None = None,
) -> QueryUnderstandingResult:
    return QueryUnderstandingResult(
        original_query=query,
        intent=intent,
        primary_topic="travel reimbursement" if not needs_clarification else "unknown",
        rewritten_query=query,
        retrieval_hints=RetrievalHints(keywords=["meal", "per diem"]),
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        model_used="openai/gpt-oss-20b",
    )


def _make_item(idx: int = 1, title: str = "Travel Policy", text: str = "$85/day meal cap.") -> EvidenceItem:
    return EvidenceItem(
        citation_index=idx,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        version_label="2.0",
        effective_from=date(2026, 4, 1),
        effective_until=date(2027, 3, 31),
        chunk_text=text,
        similarity_score=0.88,
        page_number=4,
        section_title="Meals",
        citation_tag=f"[{title} (2.0), p. 4]",
    )


def _make_retrieval_result(items: list[EvidenceItem]) -> RetrievalResult:
    pkg = EvidencePackage(
        query="test",
        total_evidence_count=len(items),
        items=items,
        formatted_context="\n".join(i.chunk_text for i in items) if items else "No evidence.",
        is_sufficient=len(items) > 0,
        applied_limit=5,
    )
    return RetrievalResult(
        query="test",
        total_retrieved=len(items),
        chunks=[],
        similarity_threshold=0.65,
        top_k=5,
        applied_limit=5,
        evidence_package=pkg,
    )


def _build_orchestrator(
    *,
    qu_result: QueryUnderstandingResult | Exception,
    ret_result: RetrievalResult | Exception | None = None,
    assess_result: EvidenceAssessmentResult | Exception | None = None,
    gen_result: AnswerGenerationResult | Exception | None = None,
) -> tuple[RAGOrchestrator, MagicMock, MagicMock, MagicMock, MagicMock]:
    qu_svc = MagicMock(spec=QueryUnderstandingService)
    if isinstance(qu_result, Exception):
        qu_svc.understand_query.side_effect = qu_result
    else:
        qu_svc.understand_query.return_value = qu_result

    ret_svc = MagicMock(spec=RetrievalService)
    if isinstance(ret_result, Exception):
        ret_svc.retrieve_chunks.side_effect = ret_result
    else:
        ret_svc.retrieve_chunks.return_value = ret_result

    assess_svc = MagicMock(spec=EvidenceAssessmentService)
    if isinstance(assess_result, Exception):
        assess_svc.assess_evidence.side_effect = assess_result
    else:
        assess_svc.assess_evidence.return_value = assess_result

    gen_svc = MagicMock(spec=AnswerGenerationService)
    if isinstance(gen_result, Exception):
        gen_svc.generate_answer.side_effect = gen_result
    else:
        gen_svc.generate_answer.return_value = gen_result

    orchestrator = RAGOrchestrator(
        query_understanding_service=qu_svc,
        retrieval_service=ret_svc,
        evidence_assessment_service=assess_svc,
        answer_generation_service=gen_svc,
    )
    return orchestrator, qu_svc, ret_svc, assess_svc, gen_svc


def _executed_nodes(orchestrator: RAGOrchestrator, query: str, db: Session, thread_id: str) -> list[str]:
    nodes: list[str] = []
    for chunk in orchestrator.graph.stream(
        {"original_query": query, "workflow_status": "running"},
        config={"configurable": {"db": db, "thread_id": thread_id}},
    ):
        nodes.extend(chunk.keys())
    return nodes


# ---------------------------------------------------------------------------
# Happy Path & Conditional Routing Tests
# ---------------------------------------------------------------------------


def test_sufficient_evidence_routes_through_generate_answer() -> None:
    item = _make_item()
    qu = _make_qu()
    ret = _make_retrieval_result([item])
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.SUFFICIENT,
        support_level=SupportLevel.FULL,
        is_relevant=True,
        reasoning="Directly supported.",
        supporting_evidence=[EvidenceReference.from_evidence_item(item)],
        model_used="openai/gpt-oss-120b",
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="Domestic meal per diem is $85/day [1].",
        status=AnswerStatus.ANSWERED,
        citations=[AnswerCitation.from_evidence_item(item)],
        model_used="openai/gpt-oss-120b",
    )

    orchestrator, qu_svc, ret_svc, assess_svc, gen_svc = _build_orchestrator(
        qu_result=qu,
        ret_result=ret,
        assess_result=assess,
        gen_result=gen,
    )
    mock_db = MagicMock(spec=Session)

    visited = _executed_nodes(orchestrator, qu.original_query, mock_db, "t-sufficient")
    assert visited == ["query_understanding", "retrieve", "assess_evidence", "generate_answer"]

    result = orchestrator.run(RAGWorkflowRequest(query=qu.original_query, thread_id="t-run"), db=mock_db)
    assert result.workflow_status == "completed"
    assert result.generation_result is not None
    assert result.generation_result.status == AnswerStatus.ANSWERED
    assert len(result.generation_result.citations) == 1
    qu_svc.understand_query.assert_called()
    ret_svc.retrieve_chunks.assert_called()
    assess_svc.assess_evidence.assert_called()
    gen_svc.generate_answer.assert_called()


def test_insufficient_evidence_routes_to_abstain_never_generate_answer() -> None:
    qu = _make_qu(query="Does Northstar reimburse pet boarding?")
    ret = _make_retrieval_result([])
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.INSUFFICIENT,
        support_level=SupportLevel.NONE,
        is_relevant=False,
        reasoning="No pet boarding clause found.",
        missing_information=["Pet boarding policy"],
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="I cannot answer this question due to insufficient evidence.",
        status=AnswerStatus.ABSTAINED,
        citations=[],
        missing_information=["Pet boarding policy"],
    )

    orchestrator, _, _, _, _ = _build_orchestrator(
        qu_result=qu, ret_result=ret, assess_result=assess, gen_result=gen
    )
    mock_db = MagicMock(spec=Session)

    visited = _executed_nodes(orchestrator, qu.original_query, mock_db, "t-abstain")
    assert visited == ["query_understanding", "retrieve", "assess_evidence", "abstain"]
    assert "generate_answer" not in visited

    res = orchestrator.run(qu.original_query, db=mock_db)
    assert res.workflow_status == "completed"
    assert res.generation_result.status == AnswerStatus.ABSTAINED


def test_conflict_routes_to_handle_conflict_never_generate_answer() -> None:
    item1 = _make_item(idx=1, title="Remote Work Policy", text="$500 allowance.")
    item2 = _make_item(idx=2, title="Engineering Addendum", text="$1,000 stipend.")
    qu = _make_qu(query="What is the home office equipment limit?")
    ret = _make_retrieval_result([item1, item2])
    conflict = PolicyConflictItem(
        conflict_id="conflict-1",
        conflict_type="cross_document_contradiction",
        description="Conflicting equipment caps.",
        claim_a="$500 allowance.",
        source_a=EvidenceReference.from_evidence_item(item1),
        claim_b="$1,000 stipend.",
        source_b=EvidenceReference.from_evidence_item(item2),
    )
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.CONFLICT,
        support_level=SupportLevel.FULL,
        is_relevant=True,
        reasoning="Conflicting active policies.",
        conflicts=[conflict],
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="Conflicting active policy guidance was found...",
        status=AnswerStatus.CONFLICT_DETECTED,
        conflicts=[conflict],
    )

    orchestrator, _, _, _, _ = _build_orchestrator(
        qu_result=qu, ret_result=ret, assess_result=assess, gen_result=gen
    )
    mock_db = MagicMock(spec=Session)

    visited = _executed_nodes(orchestrator, qu.original_query, mock_db, "t-conflict")
    assert visited == ["query_understanding", "retrieve", "assess_evidence", "handle_conflict"]
    assert "generate_answer" not in visited


def test_clarification_skips_retrieval_and_routes_to_handle_clarification() -> None:
    qu = _make_qu(
        query="What is the limit?",
        intent=QueryIntent.CLARIFICATION,
        needs_clarification=True,
        clarification_reason="Please specify which policy.",
    )
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.CLARIFICATION_REQUIRED,
        support_level=SupportLevel.NONE,
        is_relevant=False,
        reasoning="Clarification needed.",
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="Could you please clarify your question? Please specify which policy.",
        status=AnswerStatus.CLARIFICATION_REQUIRED,
    )

    orchestrator, _, ret_svc, _, _ = _build_orchestrator(
        qu_result=qu, ret_result=None, assess_result=assess, gen_result=gen
    )
    mock_db = MagicMock(spec=Session)

    visited = _executed_nodes(orchestrator, qu.original_query, mock_db, "t-clarify")
    assert visited == ["query_understanding", "assess_evidence", "handle_clarification"]
    ret_svc.retrieve_chunks.assert_not_called()


def test_out_of_scope_skips_retrieval_and_abstains() -> None:
    qu = _make_qu(query="Who won the match?", intent=QueryIntent.OUT_OF_SCOPE)
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.INSUFFICIENT,
        support_level=SupportLevel.NONE,
        is_relevant=False,
        reasoning="Out of scope.",
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="I cannot answer out-of-scope questions.",
        status=AnswerStatus.ABSTAINED,
    )

    orchestrator, _, ret_svc, _, _ = _build_orchestrator(
        qu_result=qu, ret_result=None, assess_result=assess, gen_result=gen
    )
    mock_db = MagicMock(spec=Session)

    visited = _executed_nodes(orchestrator, qu.original_query, mock_db, "t-oos")
    assert visited == ["query_understanding", "assess_evidence", "abstain"]
    ret_svc.retrieve_chunks.assert_not_called()


# ---------------------------------------------------------------------------
# Error Handling, Guard & Checkpointing Tests
# ---------------------------------------------------------------------------


def test_query_understanding_llm_failure_routes_to_handle_error_and_sanitizes() -> None:
    orchestrator, _, ret_svc, _, _ = _build_orchestrator(
        qu_result=LLMProviderError("Groq failed with key gsk_secret12345")
    )
    mock_db = MagicMock(spec=Session)

    res = orchestrator.run("What is the leave policy?", db=mock_db)

    assert res.workflow_status == "failed"
    assert res.error_stage == "query_understanding"
    assert res.generation_result is None
    assert "gsk_secret12345" not in (res.error_message or "")
    ret_svc.retrieve_chunks.assert_not_called()


def test_retrieval_failure_routes_to_handle_error() -> None:
    orchestrator, _, _, assess_svc, _ = _build_orchestrator(
        qu_result=_make_qu(),
        ret_result=RetrievalDatabaseError("DB connection failed"),
    )
    mock_db = MagicMock(spec=Session)

    res = orchestrator.run("What is the meal per diem?", db=mock_db)

    assert res.workflow_status == "failed"
    assert res.error_stage == "retrieve"
    assert res.generation_result is None
    assess_svc.assess_evidence.assert_not_called()


def test_assessment_failure_routes_to_handle_error() -> None:
    item = _make_item()
    orchestrator, _, _, _, gen_svc = _build_orchestrator(
        qu_result=_make_qu(),
        ret_result=_make_retrieval_result([item]),
        assess_result=AssessmentOutputValidationError("Bad assessment JSON"),
    )
    mock_db = MagicMock(spec=Session)

    res = orchestrator.run("What is the meal per diem?", db=mock_db)

    assert res.workflow_status == "failed"
    assert res.error_stage == "assess_evidence"
    assert res.generation_result is None
    gen_svc.generate_answer.assert_not_called()


def test_generation_citation_failure_routes_to_handle_error() -> None:
    item = _make_item()
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.SUFFICIENT,
        support_level=SupportLevel.FULL,
        is_relevant=True,
        reasoning="OK",
        supporting_evidence=[EvidenceReference.from_evidence_item(item)],
    )
    orchestrator, _, _, _, _ = _build_orchestrator(
        qu_result=_make_qu(),
        ret_result=_make_retrieval_result([item]),
        assess_result=assess,
        gen_result=CitationValidationError("Invalid page number"),
    )
    mock_db = MagicMock(spec=Session)

    res = orchestrator.run("What is the meal per diem?", db=mock_db)

    assert res.workflow_status == "failed"
    assert res.error_stage == "generate_answer"
    assert res.generation_result is None


def test_generate_answer_node_guard_rejects_insufficient_decision() -> None:
    gen_svc = MagicMock(spec=AnswerGenerationService)
    node = make_generate_answer_node(gen_svc)
    state = {
        "original_query": "test",
        "query_understanding": _make_qu(),
        "evidence_package": _make_retrieval_result([]).evidence_package,
        "evidence_assessment": EvidenceAssessmentResult(
            decision=EvidenceDecision.INSUFFICIENT,
            support_level=SupportLevel.NONE,
            is_relevant=False,
            reasoning="Insufficient",
        ),
    }
    update = node(state, {"configurable": {}})
    assert update["workflow_status"] == "failed"
    assert update["error_stage"] == "generate_answer"
    gen_svc.generate_answer.assert_not_called()


def test_memory_checkpointer_persists_state_snapshot() -> None:
    item = _make_item()
    qu = _make_qu()
    ret = _make_retrieval_result([item])
    assess = EvidenceAssessmentResult(
        decision=EvidenceDecision.SUFFICIENT,
        support_level=SupportLevel.FULL,
        is_relevant=True,
        reasoning="OK",
        supporting_evidence=[EvidenceReference.from_evidence_item(item)],
    )
    gen = AnswerGenerationResult(
        original_query=qu.original_query,
        answer="Meal per diem is $85/day [1].",
        status=AnswerStatus.ANSWERED,
        citations=[AnswerCitation.from_evidence_item(item)],
    )
    orchestrator, _, _, _, _ = _build_orchestrator(
        qu_result=qu, ret_result=ret, assess_result=assess, gen_result=gen
    )
    mock_db = MagicMock(spec=Session)

    res = orchestrator.run(
        RAGWorkflowRequest(query=qu.original_query, thread_id="thread-42"),
        db=mock_db,
    )
    assert res.thread_id == "thread-42"

    snapshot = orchestrator.graph.get_state({"configurable": {"thread_id": "thread-42"}})
    assert snapshot.values["workflow_status"] == "completed"
    assert snapshot.values["generation_result"].status == AnswerStatus.ANSWERED


# ---------------------------------------------------------------------------
# Opt-in Live End-to-End Integration Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_langgraph_orchestrator_end_to_end() -> None:
    """Opt-in live test hitting Groq + Supabase when RUN_LIVE_RAG_TESTS=1."""
    if os.getenv("RUN_LIVE_RAG_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_RAG_TESTS=1 to run live LangGraph E2E test.")

    from app.core.database import SessionLocal
    from app.graph.workflow import get_rag_orchestrator

    orchestrator = get_rag_orchestrator()
    with SessionLocal() as db:
        res = orchestrator.run(
            RAGWorkflowRequest(
                query="What are the remote work rules for employees?",
                similarity_threshold=0.4,
                thread_id="live-e2e-check",
            ),
            db=db,
        )
    assert res.workflow_status == "completed"
    assert res.generation_result is not None
