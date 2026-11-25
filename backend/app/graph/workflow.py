"""
LangGraph StateGraph builder & RAGOrchestrator runner — Task 05D.

Connects Task 05A (Query Understanding), Task 04 (Retrieval), Task 05B
(Evidence Assessment), and Task 05C (Grounded Answer Generation) into a single
validated workflow with optional checkpointing.
"""

import logging
from typing import Optional

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.orm import Session

from app.core.database import sanitize_error_message
from app.graph.nodes import (
    make_abstain_node,
    make_assess_evidence_node,
    make_generate_answer_node,
    make_handle_clarification_node,
    make_handle_conflict_node,
    make_query_understanding_node,
    make_retrieve_node,
    node_handle_error,
)
from app.graph.routing import (
    route_after_assessment,
    route_after_query_understanding,
    route_after_retrieval,
)
from app.graph.state import AgentState
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
from app.schemas.orchestration import RAGWorkflowRequest, RAGWorkflowResult
from app.schemas.query_understanding import (
    ConversationTurn,
    QueryIntent,
    QueryUnderstandingResult,
    RetrievalHints,
)
from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult, RetrievedChunk
from app.services.answer_generation_service import (
    AnswerGenerationService,
    get_answer_generation_service,
)
from app.services.evidence_assessment_service import (
    EvidenceAssessmentService,
    get_evidence_assessment_service,
)
from app.services.query_understanding_service import (
    QueryUnderstandingService,
    get_query_understanding_service,
)
from app.services.retrieval_service import RetrievalService, get_retrieval_service

logger = logging.getLogger("app.graph.workflow")

ALLOWED_CHECKPOINT_TYPES = [
    QueryIntent,
    ConversationTurn,
    RetrievalHints,
    QueryUnderstandingResult,
    RetrievedChunk,
    EvidenceItem,
    EvidencePackage,
    RetrievalResult,
    EvidenceDecision,
    SupportLevel,
    EvidenceReference,
    PolicyConflictItem,
    EvidenceAssessmentResult,
    AnswerStatus,
    AnswerCitation,
    AnswerGenerationResult,
]


def build_rag_graph(
    *,
    query_understanding_service: Optional[QueryUnderstandingService] = None,
    retrieval_service: Optional[RetrievalService] = None,
    evidence_assessment_service: Optional[EvidenceAssessmentService] = None,
    answer_generation_service: Optional[AnswerGenerationService] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """
    Constructs and compiles the KnowBridge AI policy-aware RAG `StateGraph`.
    """
    qu_svc = query_understanding_service or get_query_understanding_service()
    ret_svc = retrieval_service or get_retrieval_service()
    assess_svc = evidence_assessment_service or get_evidence_assessment_service()
    gen_svc = answer_generation_service or get_answer_generation_service()

    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("query_understanding", make_query_understanding_node(qu_svc))
    builder.add_node("retrieve", make_retrieve_node(ret_svc))
    builder.add_node("assess_evidence", make_assess_evidence_node(assess_svc))
    builder.add_node("generate_answer", make_generate_answer_node(gen_svc))
    builder.add_node("abstain", make_abstain_node(gen_svc))
    builder.add_node("handle_conflict", make_handle_conflict_node(gen_svc))
    builder.add_node("handle_clarification", make_handle_clarification_node(gen_svc))
    builder.add_node("handle_error", node_handle_error)

    # Wire edges & conditional routing
    builder.add_edge(START, "query_understanding")
    builder.add_conditional_edges(
        "query_understanding",
        route_after_query_understanding,
        {
            "retrieve": "retrieve",
            "assess_evidence": "assess_evidence",
            "handle_error": "handle_error",
        },
    )
    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieval,
        {
            "assess_evidence": "assess_evidence",
            "handle_error": "handle_error",
        },
    )
    builder.add_conditional_edges(
        "assess_evidence",
        route_after_assessment,
        {
            "generate_answer": "generate_answer",
            "abstain": "abstain",
            "handle_conflict": "handle_conflict",
            "handle_clarification": "handle_clarification",
            "handle_error": "handle_error",
        },
    )

    builder.add_edge("generate_answer", END)
    builder.add_edge("abstain", END)
    builder.add_edge("handle_conflict", END)
    builder.add_edge("handle_clarification", END)
    builder.add_edge("handle_error", END)

    return builder.compile(checkpointer=checkpointer)


class RAGOrchestrator:
    """
    High-level coordinator executing the compiled LangGraph RAG workflow and
    returning a validated `RAGWorkflowResult`.
    """

    def __init__(
        self,
        *,
        query_understanding_service: Optional[QueryUnderstandingService] = None,
        retrieval_service: Optional[RetrievalService] = None,
        evidence_assessment_service: Optional[EvidenceAssessmentService] = None,
        answer_generation_service: Optional[AnswerGenerationService] = None,
        checkpointer: Optional[BaseCheckpointSaver] = None,
        use_memory_checkpointer: bool = True,
    ) -> None:
        resolved_checkpointer: Optional[BaseCheckpointSaver]
        if checkpointer is not None:
            resolved_checkpointer = checkpointer
        elif use_memory_checkpointer:
            resolved_checkpointer = MemorySaver(
                serde=JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES)
            )
        else:
            resolved_checkpointer = None

        self.checkpointer = resolved_checkpointer
        self.graph: CompiledStateGraph = build_rag_graph(
            query_understanding_service=query_understanding_service,
            retrieval_service=retrieval_service,
            evidence_assessment_service=evidence_assessment_service,
            answer_generation_service=answer_generation_service,
            checkpointer=resolved_checkpointer,
        )

    def run(
        self,
        request: RAGWorkflowRequest | str,
        *,
        db: Session,
    ) -> RAGWorkflowResult:
        """
        Executes the end-to-end RAG workflow for a user question.

        Args:
            request: Validated `RAGWorkflowRequest` or raw question string.
            db: Active SQLAlchemy session passed via RunnableConfig (not stored in state).
        """
        req = (
            RAGWorkflowRequest(query=request)
            if isinstance(request, str)
            else request
        )

        initial_state: AgentState = {
            "original_query": req.query,
            "conversation_history": req.conversation_history,
            "reference_date": req.reference_date,
            "similarity_threshold": req.similarity_threshold,
            "top_k": req.top_k,
            "workflow_status": "running",
        }

        configurable: dict = {"db": db}
        if self.checkpointer is not None:
            configurable["thread_id"] = req.thread_id or "default"

        config = {"configurable": configurable}

        try:
            final_state = self.graph.invoke(initial_state, config=config)
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc)) or type(exc).__name__
            logger.error("Unhandled graph invocation failure: %s", sanitized)
            return RAGWorkflowResult(
                original_query=req.query,
                workflow_status="failed",
                thread_id=configurable.get("thread_id"),
                error_stage="graph_invoke",
                error_message=sanitized,
            )

        status = final_state.get("workflow_status", "failed")
        if status not in ("completed", "failed"):
            status = "failed"

        return RAGWorkflowResult(
            original_query=req.query,
            workflow_status=status,
            thread_id=configurable.get("thread_id"),
            query_understanding=final_state.get("query_understanding"),
            retrieval_result=final_state.get("retrieval_result"),
            evidence_assessment=final_state.get("evidence_assessment"),
            generation_result=final_state.get("generation_result"),
            error_stage=final_state.get("error_stage"),
            error_message=final_state.get("error_message"),
        )


def get_rag_orchestrator() -> RAGOrchestrator:
    """FastAPI/application dependency provider returning configured RAGOrchestrator."""
    return RAGOrchestrator()
