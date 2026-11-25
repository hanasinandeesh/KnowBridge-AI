"""
Pydantic schemas for Task 05D — LangGraph RAG Orchestration.

Defines validated input (`RAGWorkflowRequest`) and output (`RAGWorkflowResult`)
contracts for running the end-to-end policy-aware RAG workflow.
"""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.answer_generation import AnswerGenerationResult
from app.schemas.evidence_assessment import EvidenceAssessmentResult
from app.schemas.query_understanding import ConversationTurn, QueryUnderstandingResult
from app.schemas.retrieval import RetrievalResult


class RAGWorkflowRequest(BaseModel):
    """Input payload for invoking the end-to-end LangGraph RAG workflow."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Employee's natural-language policy question",
    )
    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        max_length=10,
        description="Optional recent conversation turns for disambiguation",
    )
    reference_date: Optional[date] = Field(
        default=None,
        description="Optional reference date for resolving relative temporal expressions",
    )
    similarity_threshold: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Optional override for retrieval/assessment similarity threshold",
    )
    top_k: Optional[int] = Field(
        default=None,
        ge=1,
        le=20,
        description="Optional override for number of retrieved candidate chunks",
    )
    thread_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional LangGraph checkpoint thread identifier",
    )

    @field_validator("query")
    @classmethod
    def strip_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("query cannot be empty or whitespace-only.")
        return cleaned

    @field_validator("thread_id")
    @classmethod
    def strip_thread_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class RAGWorkflowResult(BaseModel):
    """Structured result returned by RAGOrchestrator after graph completion."""

    original_query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Original employee question preserved verbatim",
    )
    workflow_status: Literal["completed", "failed"] = Field(
        ...,
        description="Terminal execution status of the LangGraph workflow",
    )
    thread_id: Optional[str] = Field(
        default=None,
        description="LangGraph checkpoint thread_id used for execution, if any",
    )
    query_understanding: Optional[QueryUnderstandingResult] = Field(
        default=None,
        description="Structured output from Task 05A",
    )
    retrieval_result: Optional[RetrievalResult] = Field(
        default=None,
        description="Structured retrieval output from Task 04",
    )
    evidence_assessment: Optional[EvidenceAssessmentResult] = Field(
        default=None,
        description="Structured evidence assessment from Task 05B",
    )
    generation_result: Optional[AnswerGenerationResult] = Field(
        default=None,
        description="Final grounded answer or safe abstention/conflict result from Task 05C",
    )
    error_stage: Optional[str] = Field(
        default=None,
        description="Node/stage name where failure occurred when workflow_status == 'failed'",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Sanitized error message when workflow_status == 'failed'",
    )

    model_config = ConfigDict(from_attributes=True)
