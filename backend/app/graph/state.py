"""
Typed LangGraph state definition for Task 05D — RAG Orchestration.

Reuses existing Task 04, 05A, 05B, and 05C Pydantic schemas directly and keeps
non-serializable dependencies (like SQLAlchemy Session) out of graph state.
"""

from datetime import date
from typing import Literal, Optional, TypedDict
import uuid

from app.schemas.answer_generation import AnswerGenerationResult
from app.schemas.evidence_assessment import EvidenceAssessmentResult
from app.schemas.memory import ActiveMemoryContext, ExtractedMemoryItem
from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingResult
from app.schemas.retrieval import EvidencePackage, RetrievalResult


class AgentState(TypedDict, total=False):
    """Centralized typed state passed across LangGraph RAG workflow nodes."""

    # Inputs & Session Scope
    original_query: str
    conversation_id: Optional[uuid.UUID]
    session_key: str
    conversation_history: list[ConversationTurn]
    reference_date: Optional[date]
    similarity_threshold: Optional[float]
    top_k: Optional[int]

    # Context Resolution & Memory Context (Tasks 06D & 06E)
    standalone_query: Optional[str]
    is_follow_up: bool
    requires_clarification: bool
    clarification_reason: Optional[str]
    active_memory_context: Optional[ActiveMemoryContext]

    # Intermediate outputs (Tasks 05A, 04, 05B)
    query_understanding: Optional[QueryUnderstandingResult]
    retrieval_result: Optional[RetrievalResult]
    evidence_package: Optional[EvidencePackage]
    evidence_assessment: Optional[EvidenceAssessmentResult]

    # Final output (Task 05C), persistence & workflow status
    generation_result: Optional[AnswerGenerationResult]
    persisted_user_message_id: Optional[uuid.UUID]
    persisted_assistant_message_id: Optional[uuid.UUID]
    new_memories_extracted: list[ExtractedMemoryItem]
    workflow_status: Literal["running", "completed", "failed"]
    error_stage: Optional[str]
    error_message: Optional[str]
