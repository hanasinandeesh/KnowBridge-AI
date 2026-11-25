"""
Deterministic Unit Tests & Opt-in Integration Test for Task 05B —
Evidence Sufficiency & Conflict Detection.
"""

import json
import os
import uuid
from datetime import date
from unittest.mock import MagicMock

import pytest

from app.schemas.evidence_assessment import (
    EvidenceAssessmentRequest,
    EvidenceDecision,
    SupportLevel,
)
from app.schemas.query_understanding import (
    QueryIntent,
    QueryUnderstandingResult,
    RetrievalHints,
)
from app.schemas.retrieval import (
    EvidenceItem,
    EvidencePackage,
    RetrievalResult,
    RetrievedChunk,
)
from app.services.evidence_assessment_service import (
    AssessmentOutputValidationError,
    EvidenceAssessmentService,
    InvalidAssessmentInputError,
)
from app.services.llm_client import GroqLLMClient


def _make_qu(
    query: str = "What is the meal per diem?",
    intent: QueryIntent = QueryIntent.POLICY_LOOKUP,
    topic: str = "travel reimbursement",
    needs_clarification: bool = False,
    clarification_reason: str | None = None,
) -> QueryUnderstandingResult:
    return QueryUnderstandingResult(
        original_query=query,
        intent=intent,
        primary_topic=topic,
        rewritten_query=query,
        retrieval_hints=RetrievalHints(keywords=[topic]),
        needs_clarification=needs_clarification,
        clarification_reason=clarification_reason,
        model_used="openai/gpt-oss-20b",
    )


def _make_item(
    idx: int = 1,
    title: str = "Business Travel Policy",
    version: str = "2.0",
    text: str = "Domestic meal per diem is capped at $85 per day.",
    similarity: float = 0.85,
    page: int | None = 4,
    doc_id: uuid.UUID | None = None,
) -> EvidenceItem:
    return EvidenceItem(
        citation_index=idx,
        chunk_id=uuid.uuid4(),
        document_id=doc_id or uuid.uuid4(),
        document_title=title,
        version_label=version,
        effective_from=date(2026, 4, 1),
        effective_until=date(2027, 3, 31),
        chunk_text=text,
        similarity_score=similarity,
        page_number=page,
        section_title="Meal Per Diem",
        citation_tag=f"[{title} ({version}), p. {page}]",
    )


def _make_pkg(items: list[EvidenceItem], has_conflicts: bool = False) -> EvidencePackage:
    return EvidencePackage(
        query="test query",
        total_evidence_count=len(items),
        items=items,
        formatted_context="\n".join(i.chunk_text for i in items) if items else "No evidence.",
        has_conflicts=has_conflicts,
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
# Deterministic Pre-Check Tests (Zero LLM Calls)
# ---------------------------------------------------------------------------


def test_empty_evidence_returns_insufficient_without_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([]),
        )
    )

    assert res.decision == EvidenceDecision.INSUFFICIENT
    assert res.support_level == SupportLevel.NONE
    assert res.is_relevant is False
    assert res.model_used is None
    assert res.missing_information
    mock_llm.complete_json.assert_not_called()


def test_low_similarity_evidence_returns_insufficient_without_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    low_item = _make_item(similarity=0.52)
    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([low_item]),
            min_similarity_threshold=0.65,
        )
    )

    assert res.decision == EvidenceDecision.INSUFFICIENT
    assert res.support_level == SupportLevel.NONE
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


def test_clarification_required_short_circuits_without_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(
                query="What is the limit?",
                intent=QueryIntent.CLARIFICATION,
                topic="unknown",
                needs_clarification=True,
                clarification_reason="Policy subject is unspecified.",
            ),
            evidence_package=_make_pkg([_make_item()]),
        )
    )

    assert res.decision == EvidenceDecision.CLARIFICATION_REQUIRED
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


def test_out_of_scope_returns_insufficient_without_llm() -> None:
    mock_llm = _make_mock_llm({})
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(
                query="What is the weather in London?",
                intent=QueryIntent.OUT_OF_SCOPE,
                topic="unknown",
            ),
            evidence_package=_make_pkg([_make_item()]),
        )
    )

    assert res.decision == EvidenceDecision.INSUFFICIENT
    assert res.is_relevant is False
    assert res.model_used is None
    mock_llm.complete_json.assert_not_called()


# ---------------------------------------------------------------------------
# Semantic Sufficiency, Partial Support, Conflict & Superseded Policy Tests
# ---------------------------------------------------------------------------


def test_sufficient_evidence_decision() -> None:
    item1 = _make_item(idx=1)
    mock_llm = _make_mock_llm(
        {
            "is_relevant": True,
            "support_level": "FULL",
            "reasoning": "The active travel policy explicitly states the $85/day domestic meal per diem.",
            "missing_information": [],
            "supporting_indices": [1],
            "conflicts": [],
        }
    )
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([item1]),
        )
    )

    assert res.decision == EvidenceDecision.SUFFICIENT
    assert res.support_level == SupportLevel.FULL
    assert res.is_relevant is True
    assert len(res.supporting_evidence) == 1
    assert res.supporting_evidence[0].chunk_id == item1.chunk_id
    assert res.conflicts == []
    assert res.model_used == "openai/gpt-oss-120b"


def test_partial_support_maps_to_insufficient_with_missing_info() -> None:
    item1 = _make_item(
        idx=1,
        title="Employee Leave Policy",
        text="Full-time permanent employees receive 16 weeks of paid parental leave.",
    )
    mock_llm = _make_mock_llm(
        {
            "is_relevant": True,
            "support_level": "PARTIAL",
            "reasoning": "Evidence covers permanent employees but does not address contractor eligibility.",
            "missing_information": ["Parental leave eligibility rules for contractors."],
            "supporting_indices": [1],
            "conflicts": [],
        }
    )
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(
                query="Are contractors eligible for parental leave?",
                intent=QueryIntent.ELIGIBILITY,
                topic="parental leave",
            ),
            evidence_package=_make_pkg([item1]),
        )
    )

    assert res.decision == EvidenceDecision.INSUFFICIENT
    assert res.support_level == SupportLevel.PARTIAL
    assert res.is_relevant is True
    assert res.missing_information == ["Parental leave eligibility rules for contractors."]
    assert len(res.supporting_evidence) == 1


def test_cross_document_nli_conflict_detection() -> None:
    item1 = _make_item(
        idx=1,
        title="Remote & Hybrid Work Policy",
        text="Employees receive a $500 home office equipment allowance.",
    )
    item2 = _make_item(
        idx=2,
        title="Engineering Equipment Addendum",
        text="Employees receive a $1,000 home office equipment stipend.",
    )
    mock_llm = _make_mock_llm(
        {
            "is_relevant": True,
            "support_level": "FULL",
            "reasoning": "Two active policies specify different home office equipment caps.",
            "missing_information": [],
            "supporting_indices": [1, 2],
            "conflicts": [
                {
                    "claim_a": "$500 home office equipment allowance.",
                    "source_a_index": 1,
                    "claim_b": "$1,000 home office equipment stipend.",
                    "source_b_index": 2,
                    "description": "Conflicting home office equipment reimbursement limits.",
                }
            ],
        }
    )
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(
                query="What is the home office equipment reimbursement limit?",
                topic="remote work equipment",
            ),
            evidence_package=_make_pkg([item1, item2]),
        )
    )

    assert res.decision == EvidenceDecision.CONFLICT
    assert len(res.conflicts) == 1
    c = res.conflicts[0]
    assert c.conflict_type == "cross_document_contradiction"
    assert c.source_a.chunk_id == item1.chunk_id
    assert c.source_b.chunk_id == item2.chunk_id


def test_superseded_policy_excluded_from_active_conflict_check() -> None:
    doc_id = uuid.uuid4()
    old_item = _make_item(
        idx=1,
        title="Business Travel Policy",
        version="1.0",
        text="Meal per diem is $50/day.",
        doc_id=doc_id,
    )
    current_item = _make_item(
        idx=2,
        title="Business Travel Policy",
        version="2.0",
        text="Meal per diem is $85/day.",
        doc_id=doc_id,
    )
    retrieval = RetrievalResult(
        query="What is the meal per diem?",
        total_retrieved=2,
        chunks=[
            RetrievedChunk(
                chunk_id=old_item.chunk_id,
                document_id=doc_id,
                document_title="Business Travel Policy",
                chunk_text=old_item.chunk_text,
                similarity_score=0.80,
                version_label="1.0",
                is_current=False,
            ),
            RetrievedChunk(
                chunk_id=current_item.chunk_id,
                document_id=doc_id,
                document_title="Business Travel Policy",
                chunk_text=current_item.chunk_text,
                similarity_score=0.88,
                version_label="2.0",
                is_current=True,
            ),
        ],
        similarity_threshold=0.65,
        top_k=5,
        is_current_only=True,
    )
    mock_llm = _make_mock_llm(
        {
            "is_relevant": True,
            "support_level": "FULL",
            "reasoning": "Active v2.0 policy specifies $85/day.",
            "missing_information": [],
            "supporting_indices": [2],
            "conflicts": [],
        }
    )
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([old_item, current_item]),
            retrieval_result=retrieval,
        )
    )

    assert res.decision == EvidenceDecision.SUFFICIENT
    assert res.conflicts == []
    assert len(res.ignored_superseded_sources) == 1
    assert res.ignored_superseded_sources[0].chunk_id == old_item.chunk_id

    # Confirm superseded item [1] was not sent to the LLM
    sent_prompt = mock_llm.complete_json.call_args.kwargs["messages"][1]["content"]
    assert "$50/day" not in sent_prompt
    assert "$85/day" in sent_prompt


def test_overlapping_active_versions_raise_version_overlap_conflict() -> None:
    doc_id = uuid.uuid4()
    item_a = _make_item(idx=1, version="1.0", text="Cap is $50.", doc_id=doc_id)
    item_b = _make_item(idx=2, version="2.0", text="Cap is $85.", doc_id=doc_id)
    retrieval = RetrievalResult(
        query="What is the meal per diem?",
        total_retrieved=2,
        chunks=[
            RetrievedChunk(
                chunk_id=item_a.chunk_id,
                document_id=doc_id,
                document_title="Business Travel Policy",
                chunk_text=item_a.chunk_text,
                similarity_score=0.82,
                version_label="1.0",
                is_current=True,
                is_ambiguous=True,
            ),
            RetrievedChunk(
                chunk_id=item_b.chunk_id,
                document_id=doc_id,
                document_title="Business Travel Policy",
                chunk_text=item_b.chunk_text,
                similarity_score=0.85,
                version_label="2.0",
                is_current=True,
                is_ambiguous=True,
            ),
        ],
        similarity_threshold=0.65,
        top_k=5,
        is_current_only=True,
        has_version_ambiguity=True,
        ambiguity_notes=["Overlapping active versions 1.0 and 2.0"],
    )
    mock_llm = _make_mock_llm(
        {
            "is_relevant": True,
            "support_level": "FULL",
            "reasoning": "Both versions appear active.",
            "missing_information": [],
            "supporting_indices": [1, 2],
            "conflicts": [],
        }
    )
    svc = EvidenceAssessmentService(llm_client=mock_llm)

    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(),
            evidence_package=_make_pkg([item_a, item_b], has_conflicts=True),
            retrieval_result=retrieval,
        )
    )

    assert res.decision == EvidenceDecision.CONFLICT
    assert any(c.conflict_type == "version_overlap_ambiguity" for c in res.conflicts)


# ---------------------------------------------------------------------------
# Output Grounding & Validation Guardrails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_llm_output",
    [
        "not valid json",
        json.dumps({"is_relevant": True, "support_level": "MAYBE", "reasoning": "bad"}),
        json.dumps(
            {
                "is_relevant": True,
                "support_level": "FULL",
                "reasoning": "Fabricated index",
                "missing_information": [],
                "supporting_indices": [99],  # does not exist
                "conflicts": [],
            }
        ),
        json.dumps(
            {
                "is_relevant": True,
                "support_level": "FULL",
                "reasoning": "Self-conflict",
                "missing_information": [],
                "supporting_indices": [1],
                "conflicts": [
                    {
                        "claim_a": "A",
                        "source_a_index": 1,
                        "claim_b": "B",
                        "source_b_index": 1,  # same index
                        "description": "Invalid self-conflict",
                    }
                ],
            }
        ),
    ],
)
def test_invalid_or_ungrounded_llm_output_raises_validation_error(bad_llm_output: str) -> None:
    svc = EvidenceAssessmentService(llm_client=_make_mock_llm(bad_llm_output))

    with pytest.raises(AssessmentOutputValidationError):
        svc.assess_evidence(
            EvidenceAssessmentRequest(
                query_understanding=_make_qu(),
                evidence_package=_make_pkg([_make_item(idx=1)]),
            )
        )


def test_invalid_request_raises_input_error() -> None:
    svc = EvidenceAssessmentService(llm_client=_make_mock_llm({}))
    with pytest.raises(InvalidAssessmentInputError):
        svc.assess_evidence({"bad": "payload"})


# ---------------------------------------------------------------------------
# Opt-in Live Groq Integration Test
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_live_groq_evidence_assessment() -> None:
    """Opt-in live integration test calling Groq API when RUN_LIVE_LLM_TESTS=1."""
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_LLM_TESTS=1 to run live Groq integration test.")

    svc = EvidenceAssessmentService(llm_client=GroqLLMClient())
    res = svc.assess_evidence(
        EvidenceAssessmentRequest(
            query_understanding=_make_qu(query="What is the domestic meal per diem?"),
            evidence_package=_make_pkg([_make_item(idx=1)]),
        )
    )
    assert res.decision == EvidenceDecision.SUFFICIENT
    assert res.support_level == SupportLevel.FULL
