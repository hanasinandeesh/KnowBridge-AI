"""
Deterministic Unit Tests & Opt-in Integration Test for Task 05C —
Grounded LLM Answer Generation & Citation Validation.
"""

import json
import os
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.schemas.answer_generation import (
    AnswerGenerationRequest,
    AnswerStatus,
)
from app.schemas.evidence_assessment import (
    EvidenceAssessmentResult,
    EvidenceDecision,
    EvidenceReference,
    PolicyConflictItem,
    SupportLevel,
)
from app.schemas.query_understanding import (
    QueryIntent,
    QueryUnderstandingResult,
    RetrievalHints,
)
from app.schemas.retrieval import EvidenceItem, EvidencePackage
from app.services.answer_generation_service import (
    AnswerGenerationService,
    CitationValidationError,
    GenerationOutputValidationError,
    InvalidGenerationInputError,
)
from app.services.llm_client import GroqLLMClient


def _make_qu(
    query: str = "What is the domestic meal per diem?",
    intent: QueryIntent = QueryIntent.POLICY_LOOKUP,
    topic: str = "travel reimbursement",
    clarification_reason: str | None = None,
) -> QueryUnderstandingResult:
    return QueryUnderstandingResult(
        original_query=query,
        intent=intent,
        primary_topic=topic,
        rewritten_query=query,
        retrieval_hints=RetrievalHints(keywords=[topic]),
        needs_clarification=intent == QueryIntent.CLARIFICATION,
        clarification_reason=clarification_reason,
        model_used="openai/gpt-oss-20b",
    )


def _make_item(
    idx: int = 1,
    title: str = "Business Travel Policy",
    version: str = "2.0",
    text: str = "Domestic meal per diem is capped at $85 per day.",
    page: int | None = 4,
) -> EvidenceItem:
    tag = f"[{title} ({version}), p. {page}]" if page is not None else f"[{title} ({version})]"
    return EvidenceItem(
        citation_index=idx,
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        document_title=title,
        version_label=version,
        effective_from=date(2026, 4, 1),
        effective_until=date(2027, 3, 31),
        chunk_text=text,
        similarity_score=0.88,
        page_number=page,
        section_title="Meal Per Diem",
        citation_tag=tag,
    )


def _make_pkg(items: list[EvidenceItem]) -> EvidencePackage:
    return EvidencePackage(
        query="test query",
        total_evidence_count=len(items),
        items=items,
        formatted_context="\n".join(i.chunk_text for i in items) if items else "No evidence.",
        is_sufficient=len(items) > 0,
        applied_limit=5,
    )


def _make_mock_llm(payload: dict | str, model: str = "openai/gpt-oss-120b") -> MagicMock:
    mock_client = MagicMock()
    mock_client.default_model = model
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    mock_client.complete_json.return_value = (raw, model)
    return mock_client


# ---------------------------------------------------------------------------
# Grounded Synthesis & Provenance Tests
# ---------------------------------------------------------------------------


def test_sufficient_pdf_evidence_produces_grounded_answer_with_page() -> None:
    item1 = _make_item(idx=1, page=4)
    mock_llm = _make_mock_llm(
        {
            "answer": "Under the Business Travel Policy (v2.0), the domestic meal per diem is $85 per day [1].",
            "cited_indices": [1],
        }
    )
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="What is the domestic meal per diem?",
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([item1]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.SUFFICIENT,
                support_level=SupportLevel.FULL,
                is_relevant=True,
                reasoning="Direct match.",
                supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
                model_used="openai/gpt-oss-120b",
            ),
        )
    )

    assert res.status == AnswerStatus.ANSWERED
    assert res.original_query == "What is the domestic meal per diem?"
    assert len(res.citations) == 1
    assert res.citations[0].page_number == 4
    assert res.citations[0].chunk_id == item1.chunk_id
    assert res.model_used == "openai/gpt-oss-120b"


def test_sufficient_docx_evidence_preserves_none_page_number() -> None:
    docx_item = _make_item(
        idx=1,
        title="Employee Expense Policy",
        version="1.0",
        text="Receipts are required for expenses over $25.",
        page=None,
    )
    mock_llm = _make_mock_llm(
        {
            "answer": "Receipts are required for expenses exceeding $25 [1].",
            "cited_indices": [1],
        }
    )
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="When are receipts required?",
            query_understanding=_make_qu(query="When are receipts required?"),
            evidence_package=_make_pkg([docx_item]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.SUFFICIENT,
                support_level=SupportLevel.FULL,
                is_relevant=True,
                reasoning="Direct match.",
                supporting_evidence=[EvidenceReference.from_evidence_item(docx_item)],
            ),
        )
    )

    assert res.status == AnswerStatus.ANSWERED
    assert res.citations[0].page_number is None


# ---------------------------------------------------------------------------
# Safe Abstention, Partial Support, Conflict & Clarification Tests (No LLM)
# ---------------------------------------------------------------------------


def test_insufficient_none_abstains_without_calling_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="Does Northstar reimburse pet boarding?",
            query_understanding=_make_qu(query="Does Northstar reimburse pet boarding?"),
            evidence_package=_make_pkg([]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning="No policy clause addresses pet boarding.",
                missing_information=["Pet boarding reimbursement policy."],
            ),
        )
    )

    assert res.status == AnswerStatus.ABSTAINED
    assert res.citations == []
    assert "Pet boarding reimbursement policy." in res.answer
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


def test_partial_support_abstains_and_discloses_supported_and_missing() -> None:
    item1 = _make_item(
        idx=1,
        title="Employee Leave Policy",
        text="Full-time permanent employees receive 16 weeks of paid parental leave.",
        page=7,
    )
    mock_llm = _make_mock_llm({})
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="Are contractors eligible for parental leave?",
            query_understanding=_make_qu(
                query="Are contractors eligible for parental leave?",
                intent=QueryIntent.ELIGIBILITY,
            ),
            evidence_package=_make_pkg([item1]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.PARTIAL,
                is_relevant=True,
                reasoning="Contractor eligibility is missing.",
                missing_information=["Contractor eligibility for parental leave."],
                supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
            ),
        )
    )

    assert res.status == AnswerStatus.PARTIALLY_SUPPORTED_ABSTAINED
    assert len(res.citations) == 1
    assert "Employee Leave Policy" in res.answer
    assert "Contractor eligibility for parental leave." in res.answer
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


def test_conflict_decision_presents_both_sides_without_calling_llm() -> None:
    item1 = _make_item(idx=1, title="Remote Work Policy", text="$500 allowance.", page=3)
    item2 = _make_item(idx=2, title="Engineering Addendum", text="$1,000 stipend.", page=1)
    conflict = PolicyConflictItem(
        conflict_id="conflict-1",
        conflict_type="cross_document_contradiction",
        description="Conflicting home office equipment limits.",
        claim_a="$500 allowance.",
        source_a=EvidenceReference.from_evidence_item(item1),
        claim_b="$1,000 stipend.",
        source_b=EvidenceReference.from_evidence_item(item2),
    )
    mock_llm = _make_mock_llm({})
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="What is the home office equipment limit?",
            query_understanding=_make_qu(query="What is the home office equipment limit?"),
            evidence_package=_make_pkg([item1, item2]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.CONFLICT,
                support_level=SupportLevel.FULL,
                is_relevant=True,
                reasoning="Conflicting limits.",
                conflicts=[conflict],
            ),
        )
    )

    assert res.status == AnswerStatus.CONFLICT_DETECTED
    assert len(res.citations) == 2
    assert "$500 allowance." in res.answer
    assert "$1,000 stipend." in res.answer
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


def test_clarification_required_returns_question_without_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = AnswerGenerationService(llm_client=mock_llm)

    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="What is the limit?",
            query_understanding=_make_qu(
                query="What is the limit?",
                intent=QueryIntent.CLARIFICATION,
                clarification_reason="Please specify which policy (travel, expense, or remote work).",
            ),
            evidence_package=_make_pkg([]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.CLARIFICATION_REQUIRED,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning="Clarification needed.",
            ),
        )
    )

    assert res.status == AnswerStatus.CLARIFICATION_REQUIRED
    assert "Please specify which policy" in res.answer
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


# ---------------------------------------------------------------------------
# Citation & Grounding Validation Guardrails
# ---------------------------------------------------------------------------


def test_fabricated_citation_index_raises_citation_validation_error() -> None:
    item1 = _make_item(idx=1)
    mock_llm = _make_mock_llm(
        {
            "answer": "The meal per diem is $85 [99].",
            "cited_indices": [99],
        }
    )
    svc = AnswerGenerationService(llm_client=mock_llm)

    with pytest.raises(CitationValidationError):
        svc.generate_answer(
            AnswerGenerationRequest(
                original_query="What is the meal per diem?",
                query_understanding=_make_qu(),
                evidence_package=_make_pkg([item1]),
                evidence_assessment=EvidenceAssessmentResult(
                    decision=EvidenceDecision.SUFFICIENT,
                    support_level=SupportLevel.FULL,
                    is_relevant=True,
                    reasoning="OK",
                    supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
                ),
            )
        )


def test_fabricated_page_number_in_answer_raises_citation_validation_error() -> None:
    item1 = _make_item(idx=1, title="Business Travel Policy", page=4)
    mock_llm = _make_mock_llm(
        {
            "answer": "Meal per diem is $85 [Business Travel Policy, Page 99] [1].",
            "cited_indices": [1],
        }
    )
    svc = AnswerGenerationService(llm_client=mock_llm)

    with pytest.raises(CitationValidationError):
        svc.generate_answer(
            AnswerGenerationRequest(
                original_query="What is the meal per diem?",
                query_understanding=_make_qu(),
                evidence_package=_make_pkg([item1]),
                evidence_assessment=EvidenceAssessmentResult(
                    decision=EvidenceDecision.SUFFICIENT,
                    support_level=SupportLevel.FULL,
                    is_relevant=True,
                    reasoning="OK",
                    supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
                ),
            )
        )


def test_missing_citations_for_sufficient_answer_raises_error() -> None:
    item1 = _make_item(idx=1)
    mock_llm = _make_mock_llm(
        {
            "answer": "The meal per diem is $85 per day.",
            "cited_indices": [],
        }
    )
    svc = AnswerGenerationService(llm_client=mock_llm)

    with pytest.raises(CitationValidationError):
        svc.generate_answer(
            AnswerGenerationRequest(
                original_query="What is the meal per diem?",
                query_understanding=_make_qu(),
                evidence_package=_make_pkg([item1]),
                evidence_assessment=EvidenceAssessmentResult(
                    decision=EvidenceDecision.SUFFICIENT,
                    support_level=SupportLevel.FULL,
                    is_relevant=True,
                    reasoning="OK",
                    supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
                ),
            )
        )


def test_malformed_llm_json_raises_generation_output_validation_error() -> None:
    item1 = _make_item(idx=1)
    svc = AnswerGenerationService(llm_client=_make_mock_llm("not valid json"))

    with pytest.raises(GenerationOutputValidationError):
        svc.generate_answer(
            AnswerGenerationRequest(
                original_query="What is the meal per diem?",
                query_understanding=_make_qu(),
                evidence_package=_make_pkg([item1]),
                evidence_assessment=EvidenceAssessmentResult(
                    decision=EvidenceDecision.SUFFICIENT,
                    support_level=SupportLevel.FULL,
                    is_relevant=True,
                    reasoning="OK",
                    supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
                ),
            )
        )


def test_invalid_request_raises_input_error() -> None:
    svc = AnswerGenerationService(llm_client=_make_mock_llm({}))
    with pytest.raises(InvalidGenerationInputError):
        svc.generate_answer({"bad": "payload"})


# ---------------------------------------------------------------------------
# Opt-in Live Groq Integration Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_groq_answer_generation() -> None:
    """Opt-in live integration test calling Groq API when RUN_LIVE_LLM_TESTS=1."""
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_LLM_TESTS=1 to run live Groq integration test.")

    item1 = _make_item(idx=1, page=4)
    svc = AnswerGenerationService(llm_client=GroqLLMClient())
    res = svc.generate_answer(
        AnswerGenerationRequest(
            original_query="What is the domestic meal per diem?",
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([item1]),
            evidence_assessment=EvidenceAssessmentResult(
                decision=EvidenceDecision.SUFFICIENT,
                support_level=SupportLevel.FULL,
                is_relevant=True,
                reasoning="Direct match.",
                supporting_evidence=[EvidenceReference.from_evidence_item(item1)],
            ),
        )
    )
    assert res.status == AnswerStatus.ANSWERED
    assert "85" in res.answer
    assert len(res.citations) == 1
