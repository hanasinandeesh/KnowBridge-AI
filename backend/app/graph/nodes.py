"""
LangGraph node implementations for Task 05D — RAG Orchestration.

Each node is a thin, single-responsibility coordinator wrapping the existing
Task 05A, 04, 05B, and 05C services without duplicating domain logic.
"""

import logging
from typing import Any, Callable, Optional

from langchain_core.runnables import RunnableConfig

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.graph.state import AgentState
from app.schemas.answer_generation import AnswerGenerationRequest
from app.schemas.evidence_assessment import (
    EvidenceAssessmentRequest,
    EvidenceDecision,
)
from app.schemas.query_understanding import QueryUnderstandingRequest
from app.schemas.retrieval import EvidencePackage
from app.services.answer_generation_service import AnswerGenerationService
from app.services.evidence_assessment_service import EvidenceAssessmentService
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


def make_query_understanding_node(service: QueryUnderstandingService) -> NodeFn:
    """Creates the LangGraph node executing Task 05A QueryUnderstandingService."""

    def node_query_understanding(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
        logger.info("Executing node 'query_understanding'")
        try:
            req = QueryUnderstandingRequest(
                query=state["original_query"],
                conversation_history=state.get("conversation_history") or [],
                reference_date=state.get("reference_date"),
            )
            qu_result = service.understand_query(req)
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
    return _make_terminal_generation_node(
        stage_name="handle_clarification",
        expected_decision=EvidenceDecision.CLARIFICATION_REQUIRED,
        service=service,
    )


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
