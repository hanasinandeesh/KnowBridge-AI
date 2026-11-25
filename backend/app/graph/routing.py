"""
Conditional routing functions for Task 05D — LangGraph RAG Orchestration.
"""

from app.graph.state import AgentState
from app.schemas.evidence_assessment import EvidenceDecision
from app.schemas.query_understanding import QueryIntent


def route_after_query_understanding(state: AgentState) -> str:
    """
    Routes after Task 05A:
    - Failures -> 'handle_error'
    - Clarification / out-of-scope -> skip retrieval and go straight to 'assess_evidence'
    - Searchable policy queries -> 'retrieve'
    """
    if state.get("workflow_status") == "failed":
        return "handle_error"

    qu = state.get("query_understanding")
    if qu is None:
        return "handle_error"

    if qu.needs_clarification or qu.intent in (
        QueryIntent.CLARIFICATION,
        QueryIntent.OUT_OF_SCOPE,
    ):
        return "assess_evidence"

    return "retrieve"


def route_after_retrieval(state: AgentState) -> str:
    """Routes after Task 04 retrieval to 'assess_evidence' or 'handle_error'."""
    if state.get("workflow_status") == "failed":
        return "handle_error"
    return "assess_evidence"


def route_after_assessment(state: AgentState) -> str:
    """
    Routes strictly based on Task 05B EvidenceDecision:
    - SUFFICIENT -> 'generate_answer'
    - CONFLICT -> 'handle_conflict'
    - CLARIFICATION_REQUIRED -> 'handle_clarification'
    - INSUFFICIENT (or missing assessment) -> 'abstain'
    """
    if state.get("workflow_status") == "failed":
        return "handle_error"

    assessment = state.get("evidence_assessment")
    if assessment is None:
        return "handle_error"

    if assessment.decision == EvidenceDecision.SUFFICIENT:
        return "generate_answer"
    if assessment.decision == EvidenceDecision.CONFLICT:
        return "handle_conflict"
    if assessment.decision == EvidenceDecision.CLARIFICATION_REQUIRED:
        return "handle_clarification"
    return "abstain"
