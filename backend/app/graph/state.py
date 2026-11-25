"""
Typed LangGraph state definition for Task 05D — RAG Orchestration.

Reuses existing Task 04, 05A, 05B, and 05C Pydantic schemas directly and keeps
non-serializable dependencies (like SQLAlchemy Session) out of graph state.
"""

from datetime import date
from typing import Literal, Optional, TypedDict

from app.schemas.answer_generation import AnswerGenerationResult
from app.schemas.evidence_assessment import EvidenceAssessmentResult
from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingResult
from app.schemas.retrieval import EvidencePackage, RetrievalResult


class AgentState(TypedDict, total=False):
    """Centralized typed state passed across LangGraph RAG workflow nodes."""

    # Inputs
    original_query: str
    conversation_history: list[ConversationTurn]
    reference_date: Optional[date]
    similarity_threshold: Optional[float]
    top_k: Optional[int]

    # Intermediate outputs (Tasks 05A, 04, 05B)
    query_understanding: Optional[QueryUnderstandingResult]
    retrieval_result: Optional[RetrievalResult]
    evidence_package: Optional[EvidencePackage]
    evidence_assessment: Optional[EvidenceAssessmentResult]

    # Final output (Task 05C) & workflow status
    generation_result: Optional[AnswerGenerationResult]
    workflow_status: Literal["running", "completed", "failed"]
    error_stage: Optional[str]
    error_message: Optional[str]
