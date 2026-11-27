"""
LangGraph StateGraph builder & RAGOrchestrator runner — Tasks 05D & 06F.

Connects:
- Task 06D: ContextBuilderService (conversation history & follow-up resolution)
- Task 06E: MemoryService (persistent user memory retrieval & synchronization)
- Task 05A: QueryUnderstandingService (intent & search query rewrite)
- Task 04: RetrievalService (policy-aware vector search)
- Task 05B: EvidenceAssessmentService (sufficiency & conflict detection)
- Task 05C: AnswerGenerationService (grounded answer, abstention, conflict disclosure)
- Task 06C: MessageService (interaction persistence in PostgreSQL/Supabase)
"""

from datetime import datetime
import logging
from typing import Any, Optional
import uuid

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
    make_load_context_and_memory_node,
    make_persist_interaction_node,
    make_query_understanding_node,
    make_retrieve_node,
    node_handle_error,
)
from app.graph.routing import (
    route_after_assessment,
    route_after_context_and_memory,
    route_after_query_understanding,
    route_after_retrieval,
)
from app.graph.state import AgentState
from app.schemas.answer_generation import (
    AnswerCitation,
    AnswerGenerationResult,
    AnswerStatus,
)
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.evidence_assessment import (
    EvidenceAssessmentResult,
    EvidenceDecision,
    EvidenceReference,
    PolicyConflictItem,
    SupportLevel,
)
from app.schemas.memory import ActiveMemoryContext, ExtractedMemoryItem
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
from app.services.context_builder_service import (
    ContextBuilderService,
    get_context_builder_service,
)
from app.services.evidence_assessment_service import (
    EvidenceAssessmentService,
    get_evidence_assessment_service,
)
from app.services.memory_service import (
    MemoryService,
    get_memory_service,
)
from app.services.message_service import (
    MessageService,
    get_message_service,
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
    ActiveMemoryContext,
    ExtractedMemoryItem,
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
    Constructs and compiles the core Task 05D policy-aware RAG `StateGraph`.
    (START -> query_understanding -> retrieve -> assess_evidence -> terminal nodes -> END)
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


def build_chat_graph(
    *,
    context_builder_service: Optional[ContextBuilderService] = None,
    memory_service: Optional[MemoryService] = None,
    message_service: Optional[MessageService] = None,
    query_understanding_service: Optional[QueryUnderstandingService] = None,
    retrieval_service: Optional[RetrievalService] = None,
    evidence_assessment_service: Optional[EvidenceAssessmentService] = None,
    answer_generation_service: Optional[AnswerGenerationService] = None,
    checkpointer: Optional[BaseCheckpointSaver] = None,
) -> CompiledStateGraph:
    """
    Constructs and compiles the Task 06F End-to-End Conversational RAG `StateGraph`.
    (START -> load_context_and_memory -> query_understanding -> retrieve -> assess_evidence -> generation -> persist_interaction -> END)
    """
    qu_svc = query_understanding_service or get_query_understanding_service()
    ret_svc = retrieval_service or get_retrieval_service()
    assess_svc = evidence_assessment_service or get_evidence_assessment_service()
    gen_svc = answer_generation_service or get_answer_generation_service()

    builder = StateGraph(AgentState)

    # Register all workflow nodes
    builder.add_node(
        "load_context_and_memory",
        make_load_context_and_memory_node(
            context_builder_service=context_builder_service,
            memory_service=memory_service,
        ),
    )
    builder.add_node("query_understanding", make_query_understanding_node(qu_svc))
    builder.add_node("retrieve", make_retrieve_node(ret_svc))
    builder.add_node("assess_evidence", make_assess_evidence_node(assess_svc))
    builder.add_node("generate_answer", make_generate_answer_node(gen_svc))
    builder.add_node("abstain", make_abstain_node(gen_svc))
    builder.add_node("handle_conflict", make_handle_conflict_node(gen_svc))
    builder.add_node("handle_clarification", make_handle_clarification_node(gen_svc))
    builder.add_node("handle_error", node_handle_error)
    builder.add_node(
        "persist_interaction",
        make_persist_interaction_node(
            message_service=message_service,
            memory_service=memory_service,
        ),
    )

    # Wire edges
    builder.add_edge(START, "load_context_and_memory")
    builder.add_conditional_edges(
        "load_context_and_memory",
        route_after_context_and_memory,
        {
            "query_understanding": "query_understanding",
            "handle_clarification": "handle_clarification",
            "handle_error": "handle_error",
        },
    )
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

    # All terminal outcomes transition to persistence before ending
    builder.add_edge("generate_answer", "persist_interaction")
    builder.add_edge("abstain", "persist_interaction")
    builder.add_edge("handle_conflict", "persist_interaction")
    builder.add_edge("handle_clarification", "persist_interaction")
    builder.add_edge("handle_error", "persist_interaction")
    builder.add_edge("persist_interaction", END)

    return builder.compile(checkpointer=checkpointer)


class RAGOrchestrator:
    """
    High-level coordinator executing LangGraph RAG workflows,
    managing conversation threads, context history, and persistent memory.
    """

    def __init__(
        self,
        *,
        context_builder_service: Optional[ContextBuilderService] = None,
        memory_service: Optional[MemoryService] = None,
        message_service: Optional[MessageService] = None,
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
        self.context_builder_service = context_builder_service
        self.memory_service = memory_service
        self.message_service = message_service
        self.query_understanding_service = query_understanding_service
        self.retrieval_service = retrieval_service
        self.evidence_assessment_service = evidence_assessment_service
        self.answer_generation_service = answer_generation_service

        # Core Task 05D RAG graph (for standalone queries)
        self.graph: CompiledStateGraph = build_rag_graph(
            query_understanding_service=query_understanding_service,
            retrieval_service=retrieval_service,
            evidence_assessment_service=evidence_assessment_service,
            answer_generation_service=answer_generation_service,
            checkpointer=resolved_checkpointer,
        )

        # End-to-End Task 06F Chat graph (with context resolution, memory, persistence)
        self.chat_graph: CompiledStateGraph = build_chat_graph(
            context_builder_service=context_builder_service,
            memory_service=memory_service,
            message_service=message_service,
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
        Executes the standalone RAG workflow for a user question (Task 05D).
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

    def chat(
        self,
        request: ChatRequest,
        *,
        db: Session,
    ) -> ChatResponse:
        """
        Executes end-to-end conversational chat (Task 06F) with automatic thread creation,
        follow-up context resolution, persistent memory injection, and message persistence.
        """
        from app.models.conversation import Conversation

        # 1. Ensure conversation thread exists (auto-create if conversation_id is None)
        conv_id = request.conversation_id
        if conv_id is None:
            clean_title = request.query[:60].strip()
            if len(request.query) > 60:
                clean_title += "..."
            new_conv = Conversation(id=uuid.uuid4(), title=clean_title)
            db.add(new_conv)
            db.commit()
            db.refresh(new_conv)
            conv_id = new_conv.id
            logger.info("Auto-created conversation %s ('%s')", conv_id, clean_title)

        # 2. Prepare initial graph state
        initial_state: AgentState = {
            "original_query": request.query,
            "conversation_id": conv_id,
            "session_key": request.session_key,
            "conversation_history": [],
            "reference_date": request.reference_date,
            "similarity_threshold": request.similarity_threshold,
            "top_k": request.top_k,
            "workflow_status": "running",
        }

        configurable: dict = {"db": db}
        if self.checkpointer is not None:
            configurable["thread_id"] = str(conv_id)

        config = {"configurable": configurable}

        try:
            final_state = self.chat_graph.invoke(initial_state, config=config)
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc)) or type(exc).__name__
            logger.error("Unhandled chat graph invocation failure: %s", sanitized)
            return ChatResponse(
                conversation_id=conv_id,
                user_message_id=None,
                assistant_message_id=None,
                original_query=request.query,
                standalone_query=request.query,
                is_follow_up=False,
                answer="An unexpected error occurred while processing your request. Please try again.",
                citations=[],
                evidence_status="INSUFFICIENT",
                workflow_status="failed",
                error_stage="chat_invoke",
                error_message=sanitized,
            )

        gen_res = final_state.get("generation_result")
        answer_text = (
            gen_res.answer
            if gen_res is not None
            else "I was unable to determine an answer based on available enterprise policies."
        )
        citations_list = gen_res.citations if gen_res is not None else []
        raw_status = (
            gen_res.status.value
            if gen_res is not None and hasattr(gen_res.status, "value")
            else str(gen_res.status) if gen_res is not None else "INSUFFICIENT"
        ).upper()
        if "ANSWER" in raw_status or raw_status == "SUPPORTED":
            evidence_status_str = "SUPPORTED"
        elif "CONFLICT" in raw_status:
            evidence_status_str = "CONFLICTING"
        else:
            evidence_status_str = "INSUFFICIENT"

        active_mem = final_state.get("active_memory_context")
        active_mem_dict = (
            active_mem.model_dump(mode="json")
            if active_mem and hasattr(active_mem, "model_dump")
            else None
        )

        wf_status = final_state.get("workflow_status", "completed")
        if wf_status not in ("completed", "failed"):
            wf_status = "completed"

        return ChatResponse(
            conversation_id=conv_id,
            user_message_id=final_state.get("persisted_user_message_id"),
            assistant_message_id=final_state.get("persisted_assistant_message_id"),
            original_query=request.query,
            standalone_query=final_state.get("standalone_query") or request.query,
            is_follow_up=bool(final_state.get("is_follow_up", False)),
            answer=answer_text,
            citations=citations_list,
            evidence_status=evidence_status_str,
            active_memory_used=active_mem_dict,
            workflow_status=wf_status,
            error_stage=final_state.get("error_stage"),
            error_message=final_state.get("error_message"),
        )


def get_rag_orchestrator(db: Optional[Session] = None) -> RAGOrchestrator:
    """FastAPI/application dependency provider returning configured RAGOrchestrator."""
    cb_svc = get_context_builder_service(db=db) if db is not None else None
    mem_svc = get_memory_service(db=db) if db is not None else None
    msg_svc = get_message_service(db=db) if db is not None else None

    return RAGOrchestrator(
        context_builder_service=cb_svc,
        memory_service=mem_svc,
        message_service=msg_svc,
    )
