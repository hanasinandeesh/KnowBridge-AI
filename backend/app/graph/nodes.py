"""
LangGraph node implementations for Tasks 05D & 06F — Policy-Aware RAG & Memory Orchestration.

Each node is a thin, single-responsibility coordinator wrapping the existing
services (Tasks 04, 05A, 05B, 05C, 06C, 06D, 06E) without duplicating domain logic.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Optional
import uuid

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.graph.state import AgentState
from app.schemas.answer_generation import (
    AnswerCitation,
    AnswerGenerationRequest,
    AnswerGenerationResult,
    AnswerStatus,
)
from app.schemas.context_builder import ContextBuilderRequest
from app.schemas.evidence_assessment import (
    EvidenceAssessmentRequest,
    EvidenceDecision,
)
from app.schemas.memory import ActiveMemoryContext, ExtractedMemoryItem, MemoryCreate
from app.schemas.message import CitationItem, EvidenceStatusEnum, MessageCreate, MessageRole
from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingRequest
from app.schemas.retrieval import EvidencePackage
from app.services.answer_generation_service import AnswerGenerationService
from app.services.context_builder_service import ContextBuilderService
from app.services.evidence_assessment_service import EvidenceAssessmentService
from app.services.memory_service import MemoryService
from app.services.message_service import MessageService
from app.services.query_understanding_service import QueryUnderstandingService
from app.services.retrieval_service import RetrievalService

logger = logging.getLogger("app.graph.nodes")

NodeFn = Callable[[AgentState, RunnableConfig], dict[str, Any]]


def _fail_state(stage: str, exc: Exception) -> dict[str, Any]:
    sanitized = sanitize_error_message(str(exc)) or type(exc).__name__
    logger.error("Workflow node '%s' failed: %s", stage, sanitized)
    return {
        "workflow_status": "failed",
        "error_stage": stage,
        "error_message": sanitized,
        "generation_result": None,
    }


def make_load_context_and_memory_node(
    context_builder_service: Optional[ContextBuilderService] = None,
    memory_service: Optional[MemoryService] = None,
) -> NodeFn:
    """
    Creates the LangGraph node executing context history resolution (Task 06D)
    and active user memory loading (Task 06E).
    """

    def node_load_context_and_memory(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'load_context_and_memory'")
        try:
            db = (config.get("configurable") or {}).get("db")
            conv_id = state.get("conversation_id")
            session_key = state.get("session_key") or "default"
            original_query = state["original_query"]
            in_memory_hist = state.get("conversation_history")

            standalone_query = original_query
            is_follow_up = False
            requires_clarification = False
            clarification_reason = None
            resolved_history: list[ConversationTurn] = in_memory_hist or []

            # 1. Resolve conversation history & follow-up references
            if context_builder_service is not None:
                if conv_id is not None and db is not None:
                    cb_req = ContextBuilderRequest(
                        query=original_query,
                        conversation_id=conv_id,
                    )
                    cb_res = context_builder_service.build_context(
                        request=cb_req,
                        in_memory_history=in_memory_hist,
                    )
                    standalone_query = cb_res.standalone_query
                    is_follow_up = cb_res.is_follow_up
                    requires_clarification = cb_res.requires_clarification
                    clarification_reason = cb_res.clarification_reason
                    resolved_history = cb_res.conversation_history
                elif in_memory_hist:
                    cb_res = context_builder_service.build_context(
                        request=ContextBuilderRequest(query=original_query),
                        in_memory_history=in_memory_hist,
                    )
                    standalone_query = cb_res.standalone_query
                    is_follow_up = cb_res.is_follow_up
                    requires_clarification = cb_res.requires_clarification
                    clarification_reason = cb_res.clarification_reason
                    resolved_history = cb_res.conversation_history

            # 2. Retrieve persistent user memory context
            active_memory_ctx: Optional[ActiveMemoryContext] = None
            if memory_service is not None and db is not None:
                try:
                    active_memory_ctx = memory_service.get_active_memory_context(session_key=session_key)
                except Exception as mem_err:
                    logger.warning("Failed to load active memory context: %s", mem_err)

            return {
                "standalone_query": standalone_query,
                "is_follow_up": is_follow_up,
                "requires_clarification": requires_clarification,
                "clarification_reason": clarification_reason,
                "conversation_history": resolved_history,
                "active_memory_context": active_memory_ctx,
                "workflow_status": "running",
            }
        except Exception as exc:
            return _fail_state("load_context_and_memory", exc)

    return node_load_context_and_memory


def make_query_understanding_node(service: QueryUnderstandingService) -> NodeFn:
    """Creates the LangGraph node executing Task 05A QueryUnderstandingService."""

    def node_query_understanding(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'query_understanding'")
        try:
            # Use standalone resolved query if available, falling back to original query
            effective_query = state.get("standalone_query") or state["original_query"]

            req = QueryUnderstandingRequest(
                query=effective_query,
                conversation_history=state.get("conversation_history") or [],
                reference_date=state.get("reference_date"),
            )
            qu_result = service.understand_query(req)

            # Advisory memory enhancement: if no explicit department in user query, supply memory department hint
            mem_ctx = state.get("active_memory_context")
            if mem_ctx and mem_ctx.department and not qu_result.retrieval_hints.department_hint:
                qu_result.retrieval_hints.department_hint = mem_ctx.department

            return {
                "query_understanding": qu_result,
                "retrieval_result": None,
                "evidence_package": None,
                "evidence_assessment": None,
                "generation_result": None,
                "error_stage": None,
                "error_message": None,
                "workflow_status": "running",
            }
        except Exception as exc:
            return _fail_state("query_understanding", exc)

    return node_query_understanding


def make_retrieve_node(service: RetrievalService) -> NodeFn:
    """Creates the LangGraph node executing Task 04 RetrievalService."""

    def node_retrieve(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'retrieve'")
        try:
            qu = state.get("query_understanding")
            if qu is None:
                raise ValueError("Missing query_understanding in state before retrieval.")

            db = (config.get("configurable") or {}).get("db")
            if db is None:
                raise ValueError(
                    "Missing SQLAlchemy Session in RunnableConfig['configurable']['db']."
                )

            retrieval_result = service.retrieve_chunks(
                db=db,
                query=qu.rewritten_query,
                top_k=state.get("top_k"),
                similarity_threshold=state.get("similarity_threshold"),
                target_date=qu.retrieval_hints.effective_date_hint,
                version=qu.retrieval_hints.version_hint,
            )
            return {
                "retrieval_result": retrieval_result,
                "evidence_package": retrieval_result.evidence_package,
            }
        except Exception as exc:
            return _fail_state("retrieve", exc)

    return node_retrieve


def make_assess_evidence_node(service: EvidenceAssessmentService) -> NodeFn:
    """Creates the LangGraph node executing Task 05B EvidenceAssessmentService."""

    def node_assess_evidence(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'assess_evidence'")
        try:
            qu = state.get("query_understanding")
            if qu is None:
                raise ValueError("Missing query_understanding in state before assessment.")

            evidence_pkg = state.get("evidence_package")
            if evidence_pkg is None:
                evidence_pkg = EvidencePackage(
                    query=qu.rewritten_query,
                    total_evidence_count=0,
                    items=[],
                    formatted_context="No evidence retrieved.",
                    has_conflicts=False,
                    is_sufficient=False,
                    applied_limit=state.get("top_k") or 5,
                )

            min_sim = state.get("similarity_threshold")
            if min_sim is None:
                min_sim = settings.EVIDENCE_MIN_SIMILARITY

            assessment = service.assess_evidence(
                EvidenceAssessmentRequest(
                    query_understanding=qu,
                    evidence_package=evidence_pkg,
                    retrieval_result=state.get("retrieval_result"),
                    min_similarity_threshold=min_sim,
                )
            )
            return {
                "evidence_package": evidence_pkg,
                "evidence_assessment": assessment,
            }
        except Exception as exc:
            return _fail_state("assess_evidence", exc)

    return node_assess_evidence


def _make_terminal_generation_node(
    *,
    stage_name: str,
    expected_decision: EvidenceDecision,
    service: AnswerGenerationService,
) -> NodeFn:
    """Factory for guarded terminal nodes delegating to Task 05C AnswerGenerationService."""

    def terminal_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node '%s'", stage_name)
        try:
            qu = state.get("query_understanding")
            pkg = state.get("evidence_package")
            assessment = state.get("evidence_assessment")
            if qu is None or pkg is None or assessment is None:
                raise ValueError(f"Incomplete state entering '{stage_name}'.")

            if assessment.decision != expected_decision:
                raise ValueError(
                    f"Routing guard violation in '{stage_name}': expected decision "
                    f"'{expected_decision.value}', got '{assessment.decision.value}'."
                )

            gen_result = service.generate_answer(
                AnswerGenerationRequest(
                    original_query=state["original_query"],
                    query_understanding=qu,
                    evidence_package=pkg,
                    evidence_assessment=assessment,
                )
            )
            return {
                "generation_result": gen_result,
                "workflow_status": "completed",
            }
        except Exception as exc:
            return _fail_state(stage_name, exc)

    return terminal_node


def make_generate_answer_node(service: AnswerGenerationService) -> NodeFn:
    """Guarded node for SUFFICIENT evidence -> Task 05C grounded generation."""
    return _make_terminal_generation_node(
        stage_name="generate_answer",
        expected_decision=EvidenceDecision.SUFFICIENT,
        service=service,
    )


def make_abstain_node(service: AnswerGenerationService) -> NodeFn:
    """Guarded node for INSUFFICIENT evidence -> Task 05C safe abstention."""
    return _make_terminal_generation_node(
        stage_name="abstain",
        expected_decision=EvidenceDecision.INSUFFICIENT,
        service=service,
    )


def make_handle_conflict_node(service: AnswerGenerationService) -> NodeFn:
    """Guarded node for CONFLICT evidence -> Task 05C conflict disclosure."""
    return _make_terminal_generation_node(
        stage_name="handle_conflict",
        expected_decision=EvidenceDecision.CONFLICT,
        service=service,
    )


def make_handle_clarification_node(service: AnswerGenerationService) -> NodeFn:
    """Guarded node for CLARIFICATION_REQUIRED -> Task 05C clarification prompt."""

    def node_handle_clarification(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'handle_clarification'")
        try:
            qu = state.get("query_understanding")
            assessment = state.get("evidence_assessment")

            # Direct clarification from context resolution (or missing assessment)
            if assessment is None or qu is None:
                reason = (
                    state.get("clarification_reason")
                    or "Your question requires additional context or is ambiguous."
                )
                gen_result = AnswerGenerationResult(
                    original_query=state["original_query"],
                    answer=f"Could you please clarify your question? {reason}",
                    status=AnswerStatus.CLARIFICATION_REQUIRED,
                    citations=[],
                    supporting_evidence=[],
                    missing_information=[reason],
                    conflicts=[],
                    model_used=None,
                )
                return {
                    "generation_result": gen_result,
                    "workflow_status": "completed",
                }

            # Assessment-driven clarification
            gen_result = service.generate_answer(
                AnswerGenerationRequest(
                    original_query=state["original_query"],
                    query_understanding=qu,
                    evidence_package=state.get("evidence_package")
                    or EvidencePackage(
                        query=qu.rewritten_query,
                        total_evidence_count=0,
                        items=[],
                        formatted_context="No evidence.",
                        has_conflicts=False,
                        is_sufficient=False,
                        applied_limit=5,
                    ),
                    evidence_assessment=assessment,
                )
            )
            return {
                "generation_result": gen_result,
                "workflow_status": "completed",
            }
        except Exception as exc:
            return _fail_state("handle_clarification", exc)

    return node_handle_clarification


def make_persist_interaction_node(
    message_service: Optional[MessageService] = None,
    memory_service: Optional[MemoryService] = None,
) -> NodeFn:
    """
    Creates the LangGraph node persisting interaction turns (Task 06C)
    and synchronizing extracted persistent user memories (Task 06E).
    """

    def node_persist_interaction(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'persist_interaction'")
        db = (config.get("configurable") or {}).get("db")
        conv_id = state.get("conversation_id")
        gen_result = state.get("generation_result")

        persisted_user_id: Optional[uuid.UUID] = None
        persisted_assistant_id: Optional[uuid.UUID] = None
        extracted_memories: list[ExtractedMemoryItem] = []

        if db is not None and conv_id is not None and message_service is not None:
            try:
                # 1. Persist user prompt
                user_msg = message_service.create_message(
                    conversation_id=conv_id,
                    payload=MessageCreate(
                        role=MessageRole.USER,
                        content=state["original_query"],
                        citations=[],
                        evidence_status=None,
                    ),
                )
                persisted_user_id = user_msg.id

                # 2. Persist assistant response
                if gen_result is not None:
                    citations_payload = [
                        CitationItem(
                            citation_index=idx,
                            chunk_id=c.chunk_id,
                            document_title=c.document_title,
                            version_label=c.version_label,
                            page_number=c.page_number,
                            snippet=c.snippet,
                        )
                        for idx, c in enumerate(gen_result.citations, start=1)
                    ]
                    raw_status = (
                        gen_result.status.value
                        if hasattr(gen_result.status, "value")
                        else str(gen_result.status)
                    ).upper()

                    if "ANSWER" in raw_status or raw_status == "SUPPORTED":
                        evidence_status = EvidenceStatusEnum.SUPPORTED
                    elif "CONFLICT" in raw_status:
                        evidence_status = EvidenceStatusEnum.CONFLICTING
                    else:
                        evidence_status = EvidenceStatusEnum.INSUFFICIENT

                    asst_msg = message_service.create_message(
                        conversation_id=conv_id,
                        payload=MessageCreate(
                            role=MessageRole.ASSISTANT,
                            content=gen_result.answer,
                            citations=citations_payload,
                            evidence_status=evidence_status,
                        ),
                    )
                    persisted_assistant_id = asst_msg.id

                # 3. Synchronize durable memories in safe, non-blocking block
                if memory_service is not None:
                    try:
                        session_key = state.get("session_key") or "default"
                        turns = [
                            ConversationTurn(role="user", content=state["original_query"]),
                        ]
                        if gen_result is not None:
                            turns.append(
                                ConversationTurn(
                                    role="assistant",
                                    content=gen_result.answer[:300],
                                )
                            )
                        # Extract candidates and store
                        items = memory_service.extract_memories_from_turns(turns)
                        extracted_memories = items
                        for item in items:
                            memory_service.store_memory(
                                payload=MemoryCreate(
                                    session_key=session_key,
                                    memory_key=item.memory_key,
                                    memory_value=item.memory_value,
                                    memory_text=item.memory_text,
                                    memory_type=item.memory_type,
                                    confidence_score=item.confidence_score,
                                    source_conversation_id=conv_id,
                                )
                            )
                    except Exception as mem_err:
                        logger.warning("Background memory sync failed (non-fatal): %s", mem_err)

            except Exception as exc:
                sanitized = sanitize_error_message(str(exc))
                logger.error("Failed to persist interaction turns for conversation %s: %s", conv_id, sanitized)

        return {
            "persisted_user_message_id": persisted_user_id,
            "persisted_assistant_message_id": persisted_assistant_id,
            "new_memories_extracted": extracted_memories,
        }

    return node_persist_interaction


def node_handle_error(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """Terminal error node preserving sanitized failure diagnostics without fabricating answers."""
    stage = state.get("error_stage") or "unknown"
    message = sanitize_error_message(state.get("error_message") or "Workflow execution failed.")
    logger.warning("Terminating RAG workflow in 'handle_error' (stage=%s): %s", stage, message)
    return {
        "workflow_status": "failed",
        "error_stage": stage,
        "error_message": message,
        "generation_result": None,
    }
