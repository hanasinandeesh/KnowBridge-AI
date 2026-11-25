"""
Evidence Sufficiency & Conflict Detection Service — Task 05B.

Evaluates whether retrieved policy evidence (`EvidencePackage` / `RetrievalResult`
from Task 04) is relevant, complete, and consistent enough to support a grounded
answer for a structured `QueryUnderstandingResult` (Task 05A).
"""

import json
import logging
import re
import uuid
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings
from app.core.database import sanitize_error_message
from app.schemas.evidence_assessment import (
    EvidenceAssessmentRequest,
    EvidenceAssessmentResult,
    EvidenceDecision,
    EvidenceReference,
    PolicyConflictItem,
    SupportLevel,
)
from app.schemas.query_understanding import QueryIntent, QueryUnderstandingResult
from app.schemas.retrieval import EvidenceItem, RetrievalResult, RetrievedChunk
from app.services.llm_client import LLMClient, get_llm_client

logger = logging.getLogger("app.services.evidence_assessment")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

_ASSESSMENT_SYSTEM_PROMPT = """You are the Evidence Assessment & Conflict Detection engine for KnowBridge AI.
Evaluate whether the retrieved enterprise policy chunks answer the employee's question, identify missing details, and detect direct semantic contradictions between applicable chunks.

Rules:
1. Base your assessment STRICTLY on the provided numbered evidence items [1], [2], ...
2. NEVER invent facts, numbers, dates, or citations not present in the evidence.
3. "support_level":
   - "FULL": Every important part/condition of the question is directly answered by the evidence.
   - "PARTIAL": Some relevant information is present, but key conditions, roles, limits, or comparison targets are missing.
   - "NONE": The evidence does not address the question.
4. "is_relevant": true if at least one evidence item addresses the question's subject; otherwise false.
5. "supporting_indices": list of 1-based integer indices (e.g. [1, 2]) from the provided evidence that directly support the answer. Empty list if "NONE".
6. "missing_information": concise list of specific missing details if "PARTIAL" or "NONE"; empty list [] if "FULL".
7. "conflicts": list of direct semantic contradictions between TWO DIFFERENT applicable evidence items (e.g., mutually incompatible dollar limits or eligibility rules for the same scope/audience). Do NOT flag complementary details or version differences in a comparison query as conflicts.
   Each conflict item must use exact 1-based indices from the provided evidence:
   {
     "claim_a": "...",
     "source_a_index": 1,
     "claim_b": "...",
     "source_b_index": 2,
     "description": "..."
   }

Return ONLY valid JSON matching this exact structure:
{
  "is_relevant": true,
  "support_level": "FULL" | "PARTIAL" | "NONE",
  "reasoning": "...",
  "missing_information": [],
  "supporting_indices": [1],
  "conflicts": []
}"""


class EvidenceAssessmentError(Exception):
    """Base exception for evidence assessment operations."""


class InvalidAssessmentInputError(EvidenceAssessmentError):
    """Raised when the assessment request fails validation."""


class AssessmentOutputValidationError(EvidenceAssessmentError):
    """Raised when the LLM returns malformed JSON, invalid schema, or ungrounded citations."""


class _LLMConflictPayload(BaseModel):
    claim_a: str = Field(..., min_length=1, max_length=500)
    source_a_index: int = Field(..., ge=1)
    claim_b: str = Field(..., min_length=1, max_length=500)
    source_b_index: int = Field(..., ge=1)
    description: str = Field(..., min_length=1, max_length=500)


class _LLMAssessmentPayload(BaseModel):
    is_relevant: bool
    support_level: Literal["FULL", "PARTIAL", "NONE"]
    reasoning: str = Field(..., min_length=1, max_length=1000)
    missing_information: list[str] = Field(default_factory=list)
    supporting_indices: list[int] = Field(default_factory=list)
    conflicts: list[_LLMConflictPayload] = Field(default_factory=list)


def _strip_markdown_fences(raw_text: str) -> str:
    return _CODE_FENCE_RE.sub("", raw_text.strip()).strip()


class EvidenceAssessmentService:
    """
    Hybrid deterministic + LLM evidence sufficiency and conflict-detection service.
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        assessment_model: Optional[str] = None,
        default_min_similarity: Optional[float] = None,
    ) -> None:
        self._llm_client: LLMClient = llm_client or get_llm_client()
        self._assessment_model: str = (
            assessment_model if assessment_model is not None else settings.GROQ_ASSESSMENT_MODEL
        ).strip()
        self._default_min_similarity: float = (
            default_min_similarity
            if default_min_similarity is not None
            else settings.EVIDENCE_MIN_SIMILARITY
        )

    def assess_evidence(
        self,
        request: Union[EvidenceAssessmentRequest, dict[str, Any]],
    ) -> EvidenceAssessmentResult:
        """
        Assesses relevance, sufficiency, missing information, and policy conflicts
        for a given `QueryUnderstandingResult` and `EvidencePackage`.
        """
        req = self._validate_request(request)
        qu = req.query_understanding
        pkg = req.evidence_package
        min_sim = req.min_similarity_threshold

        # 1. Deterministic clarification & out-of-scope checks
        if qu.needs_clarification or qu.intent == QueryIntent.CLARIFICATION:
            return EvidenceAssessmentResult(
                decision=EvidenceDecision.CLARIFICATION_REQUIRED,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning=qu.clarification_reason
                or "The employee question requires clarification before evidence can be evaluated.",
                missing_information=["Clarification of the employee's specific policy question."],
                model_used=None,
            )

        if qu.intent == QueryIntent.OUT_OF_SCOPE:
            return EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning="The question is outside the scope of enterprise policy documents.",
                missing_information=["No enterprise policy applies to this out-of-scope inquiry."],
                model_used=None,
            )

        # 2. Deterministic emptiness check
        if not pkg.items or not pkg.is_sufficient:
            return EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning="No retrieved policy chunks met the retrieval criteria.",
                missing_information=[
                    f"No policy evidence found addressing '{qu.primary_topic}'."
                ],
                model_used=None,
            )

        # 3. Partition superseded vs. applicable evidence
        applicable_items, ignored_superseded = self._partition_superseded_items(
            items=pkg.items,
            retrieval_result=req.retrieval_result,
            query_understanding=qu,
        )

        if not applicable_items:
            return EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning="Only superseded/non-current policy versions were retrieved for a current-policy question.",
                missing_information=[
                    f"Current active policy evidence for '{qu.primary_topic}' is missing."
                ],
                ignored_superseded_sources=[
                    EvidenceReference.from_evidence_item(item) for item in ignored_superseded
                ],
                model_used=None,
            )

        # 4. Deterministic similarity cutoff check
        max_sim = max(item.similarity_score for item in applicable_items)
        if max_sim < min_sim:
            return EvidenceAssessmentResult(
                decision=EvidenceDecision.INSUFFICIENT,
                support_level=SupportLevel.NONE,
                is_relevant=False,
                reasoning=(
                    f"Highest evidence similarity ({max_sim:.4f}) is below the required "
                    f"threshold ({min_sim:.2f})."
                ),
                missing_information=[
                    f"Sufficiently relevant policy evidence for '{qu.primary_topic}'."
                ],
                ignored_superseded_sources=[
                    EvidenceReference.from_evidence_item(item) for item in ignored_superseded
                ],
                model_used=None,
            )

        # 5. Deterministic version-overlap conflict detection (reusing Task 04)
        overlap_conflicts = self._detect_version_overlap_conflicts(
            applicable_items=applicable_items,
            retrieval_result=req.retrieval_result,
            query_understanding=qu,
        )

        # 6. LLM semantic sufficiency & cross-document NLI conflict check
        messages = self._build_messages(qu, applicable_items)
        raw_content, model_used = self._llm_client.complete_json(
            messages=messages,
            model=self._assessment_model,
            temperature=0.0,
            max_tokens=2048,
        )
        llm_payload = self._parse_llm_payload(raw_content)

        # 7. Grounding validation & deterministic decision synthesis
        item_by_index = {item.citation_index: item for item in applicable_items}
        supporting_refs = self._resolve_supporting_refs(
            llm_payload.supporting_indices, item_by_index
        )
        nli_conflicts = self._resolve_nli_conflicts(
            llm_payload.conflicts, item_by_index, start_idx=len(overlap_conflicts) + 1
        )
        all_conflicts = overlap_conflicts + nli_conflicts

        support_level = SupportLevel(llm_payload.support_level)
        missing_info = [m.strip() for m in llm_payload.missing_information if m.strip()]
        reasoning = llm_payload.reasoning.strip()
        if ignored_superseded:
            reasoning += (
                f" Excluded {len(ignored_superseded)} superseded/non-current evidence item(s) "
                "from active policy evaluation."
            )

        decision = self._compute_decision(
            is_relevant=llm_payload.is_relevant,
            support_level=support_level,
            supporting_refs=supporting_refs,
            conflicts=all_conflicts,
        )

        logger.info(
            "Evidence assessed: decision=%s support=%s conflicts=%d model=%s",
            decision.value,
            support_level.value,
            len(all_conflicts),
            model_used,
        )

        return EvidenceAssessmentResult(
            decision=decision,
            support_level=support_level,
            is_relevant=llm_payload.is_relevant,
            reasoning=reasoning,
            missing_information=missing_info,
            supporting_evidence=supporting_refs,
            conflicts=all_conflicts,
            ignored_superseded_sources=[
                EvidenceReference.from_evidence_item(item) for item in ignored_superseded
            ],
            model_used=model_used,
        )

    def _validate_request(
        self,
        request: Union[EvidenceAssessmentRequest, dict[str, Any]],
    ) -> EvidenceAssessmentRequest:
        try:
            if isinstance(request, EvidenceAssessmentRequest):
                return request
            return EvidenceAssessmentRequest.model_validate(request)
        except ValidationError as exc:
            raise InvalidAssessmentInputError(
                f"Invalid evidence assessment request: {exc}"
            ) from exc

    @staticmethod
    def _partition_superseded_items(
        items: list[EvidenceItem],
        retrieval_result: Optional[RetrievalResult],
        query_understanding: QueryUnderstandingResult,
    ) -> tuple[list[EvidenceItem], list[EvidenceItem]]:
        """
        Separates superseded/non-current chunks when answering a current-policy
        question without explicit historical/comparison intent.
        """
        is_historical_or_compare = (
            query_understanding.intent == QueryIntent.COMPARISON
            or query_understanding.retrieval_hints.effective_date_hint is not None
            or query_understanding.retrieval_hints.version_hint is not None
            or (retrieval_result is not None and retrieval_result.is_current_only is False)
        )
        if is_historical_or_compare or retrieval_result is None:
            return list(items), []

        chunk_map: dict[uuid.UUID, RetrievedChunk] = {
            c.chunk_id: c for c in retrieval_result.chunks
        }
        applicable: list[EvidenceItem] = []
        superseded: list[EvidenceItem] = []

        for item in items:
            chunk = chunk_map.get(item.chunk_id)
            if chunk is not None and chunk.is_current is False:
                superseded.append(item)
            else:
                applicable.append(item)

        return applicable, superseded

    @staticmethod
    def _detect_version_overlap_conflicts(
        applicable_items: list[EvidenceItem],
        retrieval_result: Optional[RetrievalResult],
        query_understanding: QueryUnderstandingResult,
    ) -> list[PolicyConflictItem]:
        """Reuses Task 04 version-ambiguity detection to flag overlapping active versions."""
        if query_understanding.intent == QueryIntent.COMPARISON:
            return []
        if retrieval_result is None or not retrieval_result.has_version_ambiguity:
            return []

        by_doc: dict[str, list[EvidenceItem]] = {}
        for item in applicable_items:
            key = str(item.document_id) if item.document_id else item.document_title
            by_doc.setdefault(key, []).append(item)

        conflicts: list[PolicyConflictItem] = []
        counter = 1
        for doc_items in by_doc.values():
            seen_versions: dict[str, EvidenceItem] = {}
            for item in doc_items:
                ver = (item.version_label or "").strip()
                if ver and ver not in seen_versions:
                    seen_versions[ver] = item
            if len(seen_versions) > 1:
                ordered = list(seen_versions.values())
                first, second = ordered[0], ordered[1]
                conflicts.append(
                    PolicyConflictItem(
                        conflict_id=f"conflict-{counter}",
                        conflict_type="version_overlap_ambiguity",
                        description=(
                            f"Multiple overlapping active versions ({first.version_label} and "
                            f"{second.version_label}) detected for '{first.document_title}'."
                        ),
                        claim_a=first.chunk_text[:400],
                        source_a=EvidenceReference.from_evidence_item(first),
                        claim_b=second.chunk_text[:400],
                        source_b=EvidenceReference.from_evidence_item(second),
                    )
                )
                counter += 1

        return conflicts

    @staticmethod
    def _build_messages(
        qu: QueryUnderstandingResult,
        applicable_items: list[EvidenceItem],
    ) -> list[dict[str, str]]:
        evidence_blocks = []
        for item in applicable_items:
            ver_info = f" | version={item.version_label}" if item.version_label else ""
            date_info = (
                f" | effective={item.effective_from}..{item.effective_until}"
                if item.effective_from or item.effective_until
                else ""
            )
            evidence_blocks.append(
                f"[{item.citation_index}] {item.citation_tag} "
                f"(similarity={item.similarity_score:.4f}{ver_info}{date_info})\n"
                f"{item.chunk_text}"
            )

        user_prompt = (
            f"Original employee question: {qu.original_query}\n"
            f"Rewritten search query: {qu.rewritten_query}\n"
            f"Detected intent: {qu.intent.value}\n"
            f"Primary topic: {qu.primary_topic}\n\n"
            "Retrieved policy evidence:\n"
            + "\n\n".join(evidence_blocks)
        )
        return [
            {"role": "system", "content": _ASSESSMENT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _parse_llm_payload(raw_content: str) -> _LLMAssessmentPayload:
        cleaned = _strip_markdown_fences(raw_content)
        try:
            data: Any = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            sanitized = sanitize_error_message(str(exc))
            raise AssessmentOutputValidationError(
                f"Assessment LLM output is not valid JSON: {sanitized}"
            ) from exc

        if not isinstance(data, dict):
            raise AssessmentOutputValidationError(
                f"Assessment LLM output must be a JSON object, got {type(data).__name__}."
            )

        try:
            return _LLMAssessmentPayload.model_validate(data)
        except ValidationError as exc:
            sanitized = sanitize_error_message(str(exc))
            raise AssessmentOutputValidationError(
                f"Assessment LLM output failed schema validation: {sanitized}"
            ) from exc

    @staticmethod
    def _resolve_supporting_refs(
        indices: list[int],
        item_by_index: dict[int, EvidenceItem],
    ) -> list[EvidenceReference]:
        refs: list[EvidenceReference] = []
        seen: set[int] = set()
        for idx in indices:
            if idx not in item_by_index:
                raise AssessmentOutputValidationError(
                    f"LLM cited non-existent evidence index [{idx}]."
                )
            if idx not in seen:
                seen.add(idx)
                refs.append(EvidenceReference.from_evidence_item(item_by_index[idx]))
        return refs

    @staticmethod
    def _resolve_nli_conflicts(
        raw_conflicts: list[_LLMConflictPayload],
        item_by_index: dict[int, EvidenceItem],
        start_idx: int = 1,
    ) -> list[PolicyConflictItem]:
        resolved: list[PolicyConflictItem] = []
        for offset, c in enumerate(raw_conflicts):
            if c.source_a_index not in item_by_index or c.source_b_index not in item_by_index:
                raise AssessmentOutputValidationError(
                    f"LLM conflict referenced invalid evidence index "
                    f"({c.source_a_index}, {c.source_b_index})."
                )
            if c.source_a_index == c.source_b_index:
                raise AssessmentOutputValidationError(
                    "LLM flagged a conflict between an evidence item and itself."
                )
            resolved.append(
                PolicyConflictItem(
                    conflict_id=f"conflict-{start_idx + offset}",
                    conflict_type="cross_document_contradiction",
                    description=c.description.strip(),
                    claim_a=c.claim_a.strip(),
                    source_a=EvidenceReference.from_evidence_item(
                        item_by_index[c.source_a_index]
                    ),
                    claim_b=c.claim_b.strip(),
                    source_b=EvidenceReference.from_evidence_item(
                        item_by_index[c.source_b_index]
                    ),
                )
            )
        return resolved

    @staticmethod
    def _compute_decision(
        *,
        is_relevant: bool,
        support_level: SupportLevel,
        supporting_refs: list[EvidenceReference],
        conflicts: list[PolicyConflictItem],
    ) -> EvidenceDecision:
        if conflicts:
            return EvidenceDecision.CONFLICT
        if not is_relevant or support_level != SupportLevel.FULL or not supporting_refs:
            return EvidenceDecision.INSUFFICIENT
        return EvidenceDecision.SUFFICIENT


def get_evidence_assessment_service(
    llm_client: Optional[LLMClient] = None,
) -> EvidenceAssessmentService:
    """FastAPI/application dependency provider for EvidenceAssessmentService."""
    return EvidenceAssessmentService(llm_client=llm_client or get_llm_client())


__all__ = [
    "EvidenceAssessmentService",
    "EvidenceAssessmentError",
    "InvalidAssessmentInputError",
    "AssessmentOutputValidationError",
    "get_evidence_assessment_service",
]
