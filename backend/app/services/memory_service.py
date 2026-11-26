"""
Persistent Memory Service — Task 06E.

Provides business logic for:
1. Extracting reusable employee context and organizational facts from conversational dialogue.
2. Validating facts against durability, confidence, and sensitive PII policies.
3. Deduplicating and persisting memories with audit trails for superseded facts.
4. Bounded retrieval of unexpired memories.
5. Deletion, expiration purging, and formatting for downstream RAG consumption.
"""

from datetime import datetime, timedelta, timezone
import json
import logging
import re
from typing import Any, Optional, Union
import uuid

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.core.database import sanitize_error_message
from app.models.user_memory import UserMemory
from app.schemas.memory import (
    ActiveMemoryContext,
    ExtractedMemoryItem,
    MemoryCreate,
    MemoryResponse,
    MemoryType,
)
from app.schemas.query_understanding import ConversationTurn
from app.services.llm_client import LLMClient, LLMError, get_llm_client

logger = logging.getLogger("app.services.memory_service")

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)

# Sensitive PII regex patterns: Credit cards, SSNs, Passwords/tokens
_SENSITIVE_PII_PATTERNS = [
    re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"),  # 16-digit credit card
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),      # US SSN
    re.compile(r"\b(?:password|passwd|pwd|secret|api[_-]?key)\s*[:=]\s*\S+", re.IGNORECASE),
]

_MEMORY_EXTRACTOR_SYSTEM_PROMPT = """You are the Persistent Memory Extractor for KnowBridge AI, an enterprise policy-aware RAG platform.
Your task is to analyze conversation turns and extract durable, reusable facts about the user/employee that should persist across sessions.

CRITICAL EXTRACTION RULES:
1. ONLY USER PROFILE & CONSTRAINTS: Extract facts explicitly stated by the user about themselves or their organizational scope:
   - Department / business unit (e.g., Engineering, Human Resources, Finance)
   - Job role / seniority (e.g., Software Engineer, Director, Contractor, Intern)
   - Employment type (e.g., Full-Time, Part-Time, Contractor, Hourly)
   - Office / work location (e.g., London, Sydney, New York, Remote)
   - Policy-related preferences (e.g., Vegan meals for travel per diem, Prefers public transit)
   - User constraints (e.g., Works Tue-Thu only, Carries a company credit card)
2. NEVER EXTRACT POLICY FACTS: Do NOT extract general policy rules, numerical policy limits, or standard enterprise rules as user memories (e.g. "The annual leave limit is 20 days" or "Meal allowance is $75" are policy evidence, NEVER user memories).
3. DISTINGUISH DURABLE VS TRANSIENT:
   - Durable (is_durable: true): "I work in London", "I'm a contractor", "I work 4 days a week".
   - Transient (is_durable: false): "I'm taking leave next Tuesday", "I'm having coffee", "I am feeling sick today", "I'm looking at section 4".
4. SENSITIVE PII IDENTIFICATION:
   - Flag "is_sensitive_pii": true for Social Security Numbers, National IDs, credit card/bank details, medical conditions/diagnoses, private health data, passwords/API keys, home street addresses.
5. NO HALLUCINATION:
   - Only extract facts directly supported by the conversation. Never guess, assume, or fabricate employee context. If no user facts exist, return an empty list.

Return ONLY a single valid JSON object matching this exact structure:
{
  "memories": [
    {
      "memory_key": "department",
      "memory_value": "Engineering",
      "memory_text": "Employee works in the Engineering department.",
      "memory_type": "department",
      "confidence_score": 0.95,
      "is_durable": true,
      "is_sensitive_pii": false,
      "expires_in_days": null
    }
  ]
}"""


class MemoryServiceError(Exception):
    """Base exception for MemoryService operations."""
    pass


class MemoryDatabaseError(MemoryServiceError):
    """Raised when database operations fail."""
    pass


class MemoryValidationError(MemoryServiceError):
    """Raised when memory input fails validation."""
    pass


def _strip_markdown_fences(raw: str) -> str:
    """Removes surrounding markdown code fences from JSON LLM responses."""
    cleaned = raw.strip()
    lines = cleaned.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


class MemoryService:
    """
    Service responsible for extraction, validation, storage, deduplication,
    retrieval, and purging of persistent user memories.
    """

    def __init__(
        self,
        db: Session,
        llm_client: Optional[LLMClient] = None,
    ) -> None:
        self._db = db
        self._llm_client = llm_client or get_llm_client()

    # -------------------------------------------------------------------------
    # Subtask 06E.2: Memory Extraction & Validation
    # -------------------------------------------------------------------------

    def extract_memories_from_turns(
        self,
        turns: list[ConversationTurn],
    ) -> list[ExtractedMemoryItem]:
        """
        Analyzes conversation turns with Groq LLM to extract user facts.
        Applies PII filters, durability checks, and confidence thresholding (>= 0.75).
        """
        if not turns:
            return []

        # Optimization: Check if there are any user messages
        user_turns = [t for t in turns if t.role == "user"]
        if not user_turns:
            return []

        # Format conversation dialogue for extractor
        formatted_dialogue = "\n".join(
            f"[{t.role.upper()}]: {t.content}" for t in turns[-6:]
        )
        user_content = f"Analyze the following conversation and extract durable user facts:\n\n{formatted_dialogue}"

        messages = [
            {"role": "system", "content": _MEMORY_EXTRACTOR_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        try:
            raw_content, model_used = self._llm_client.complete_json(
                messages=messages,
                temperature=0.0,
                max_tokens=768,
            )
            cleaned = _strip_markdown_fences(raw_content)
            data = json.loads(cleaned)
            memories_raw = data.get("memories", [])
            if not isinstance(memories_raw, list):
                logger.warning("LLM returned non-list for memories key: %s", type(memories_raw))
                return []

            extracted: list[ExtractedMemoryItem] = []
            for item in memories_raw:
                try:
                    parsed = ExtractedMemoryItem.model_validate(item)
                    if self._validate_extracted_item(parsed):
                        extracted.append(parsed)
                except ValidationError as val_err:
                    logger.debug("Skipping invalid extracted memory candidate: %s", val_err)
                    continue

            logger.info(
                "Extracted %d valid user memories from %d turns using model %s",
                len(extracted),
                len(turns),
                model_used,
            )
            return extracted

        except (LLMError, json.JSONDecodeError) as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.warning("LLM memory extraction failed (%s). Continuing safely.", sanitized)
            return []

    def _validate_extracted_item(self, item: ExtractedMemoryItem) -> bool:
        """
        Validates extracted candidate against durability, PII, and confidence rules.
        """
        # 1. Reject transient context
        if not item.is_durable:
            logger.debug("Rejected memory '%s': not durable", item.memory_key)
            return False

        # 2. Reject low-confidence items (< 0.75)
        if item.confidence_score < 0.75:
            logger.debug(
                "Rejected memory '%s': confidence %.2f < 0.75",
                item.memory_key,
                item.confidence_score,
            )
            return False

        # 3. Reject sensitive PII
        if item.is_sensitive_pii:
            logger.warning("Rejected memory '%s': flagged as sensitive PII by extractor", item.memory_key)
            return False

        combined_text = f"{item.memory_key} {item.memory_value} {item.memory_text}"
        for pattern in _SENSITIVE_PII_PATTERNS:
            if pattern.search(combined_text):
                logger.warning(
                    "Rejected memory '%s': matched sensitive PII regex pattern",
                    item.memory_key,
                )
                return False

        return True

    # -------------------------------------------------------------------------
    # Subtask 06E.3 & 06E.4: Memory Storage, Deduplication & Superseding
    # -------------------------------------------------------------------------

    def store_memory(self, payload: MemoryCreate) -> MemoryResponse:
        """
        Persists or updates a user memory record.
        - Exact duplicate: Reaffirms timestamp, updates confidence if higher, preserves record.
        - Superseded value: Safely updates value and appends previous value to audit history.
        - New: Creates and inserts record.
        """
        try:
            stmt = select(UserMemory).where(
                UserMemory.session_key == payload.session_key,
                UserMemory.memory_key == payload.memory_key,
            )
            existing = self._db.execute(stmt).scalars().first()

            if existing:
                existing_val_norm = existing.memory_value.strip().lower()
                new_val_norm = payload.memory_value.strip().lower()

                if existing_val_norm == new_val_norm:
                    # Exact reaffirmation: update timestamp, bump confidence if higher
                    if payload.confidence_score > existing.confidence_score:
                        existing.confidence_score = payload.confidence_score
                    if payload.expires_at is not None:
                        existing.expires_at = payload.expires_at
                    if payload.source_conversation_id is not None:
                        existing.source_conversation_id = payload.source_conversation_id
                    existing.updated_at = datetime.now(timezone.utc)
                    self._db.commit()
                    self._db.refresh(existing)
                    logger.info(
                        "Reaffirmed existing memory id=%s key='%s' session='%s'",
                        existing.id,
                        existing.memory_key,
                        existing.session_key,
                    )
                    return MemoryResponse.model_validate(existing)
                else:
                    # Superseded memory: record previous value in audit trail
                    meta = dict(existing.metadata_json or {})
                    history = list(meta.get("superseded_history", []))
                    history.append({
                        "previous_value": existing.memory_value,
                        "previous_text": existing.memory_text,
                        "previous_confidence": existing.confidence_score,
                        "superseded_at": datetime.now(timezone.utc).isoformat(),
                        "superseded_by_conversation": str(payload.source_conversation_id) if payload.source_conversation_id else None,
                    })
                    meta["superseded_history"] = history
                    if payload.metadata:
                        for k, v in payload.metadata.items():
                            if k != "superseded_history":
                                meta[k] = v

                    existing.metadata_json = meta
                    flag_modified(existing, "metadata_json")

                    existing.memory_value = payload.memory_value
                    existing.memory_text = payload.memory_text or f"User's {payload.memory_key} is {payload.memory_value}."
                    existing.memory_type = (
                        payload.memory_type.value
                        if hasattr(payload.memory_type, "value")
                        else str(payload.memory_type)
                    )
                    existing.confidence_score = payload.confidence_score
                    existing.source_conversation_id = payload.source_conversation_id
                    existing.expires_at = payload.expires_at
                    existing.updated_at = datetime.now(timezone.utc)

                    self._db.commit()
                    self._db.refresh(existing)
                    logger.info(
                        "Superseded memory id=%s key='%s' session='%s' with new value='%s'",
                        existing.id,
                        existing.memory_key,
                        existing.session_key,
                        existing.memory_value,
                    )
                    return MemoryResponse.model_validate(existing)

            # Insert new memory record
            new_record = UserMemory(
                id=uuid.uuid4(),
                session_key=payload.session_key,
                memory_key=payload.memory_key,
                memory_value=payload.memory_value,
                memory_text=payload.memory_text or f"User's {payload.memory_key} is {payload.memory_value}.",
                memory_type=(
                    payload.memory_type.value
                    if hasattr(payload.memory_type, "value")
                    else str(payload.memory_type)
                ),
                confidence_score=payload.confidence_score,
                source_conversation_id=payload.source_conversation_id,
                expires_at=payload.expires_at,
                metadata_json=payload.metadata or {},
            )
            self._db.add(new_record)
            self._db.commit()
            self._db.refresh(new_record)
            logger.info(
                "Created memory id=%s key='%s' value='%s' session='%s'",
                new_record.id,
                new_record.memory_key,
                new_record.memory_value,
                new_record.session_key,
            )
            return MemoryResponse.model_validate(new_record)

        except SQLAlchemyError as exc:
            self._db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to store memory for key='%s': %s", payload.memory_key, sanitized)
            raise MemoryDatabaseError(f"Database error storing memory: {sanitized}") from exc

    def extract_and_sync_memories(
        self,
        turns: list[ConversationTurn],
        session_key: str = "default",
        conversation_id: Optional[uuid.UUID] = None,
    ) -> list[MemoryResponse]:
        """
        End-to-end extraction and storage pipeline for a set of conversation turns.
        """
        extracted_items = self.extract_memories_from_turns(turns)
        persisted: list[MemoryResponse] = []

        now = datetime.now(timezone.utc)
        for item in extracted_items:
            expires_at = None
            if item.expires_in_days:
                expires_at = now + timedelta(days=item.expires_in_days)

            create_payload = MemoryCreate(
                session_key=session_key,
                memory_key=item.memory_key,
                memory_value=item.memory_value,
                memory_text=item.memory_text,
                memory_type=item.memory_type,
                confidence_score=item.confidence_score,
                source_conversation_id=conversation_id,
                expires_at=expires_at,
                metadata={"source_turn_count": len(turns)},
            )
            stored = self.store_memory(create_payload)
            persisted.append(stored)

        return persisted

    # -------------------------------------------------------------------------
    # Subtask 06E.5: Memory Retrieval
    # -------------------------------------------------------------------------

    def get_active_memories(
        self,
        session_key: str = "default",
        limit: int = 10,
        include_expired: bool = False,
    ) -> list[MemoryResponse]:
        """
        Retrieves active unexpired memories for a given session, ordered by
        confidence score descending, then recency descending.
        """
        try:
            stmt = select(UserMemory).where(UserMemory.session_key == session_key)
            if not include_expired:
                now = datetime.now(timezone.utc)
                stmt = stmt.where(
                    (UserMemory.expires_at.is_(None)) | (UserMemory.expires_at > now)
                )

            stmt = stmt.order_by(
                UserMemory.confidence_score.desc(),
                UserMemory.updated_at.desc(),
            ).limit(limit)

            rows = self._db.execute(stmt).scalars().all()
            return [MemoryResponse.model_validate(r) for r in rows]

        except SQLAlchemyError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to retrieve memories for session='%s': %s", session_key, sanitized)
            raise MemoryDatabaseError(f"Database error retrieving memories: {sanitized}") from exc

    def get_active_memory_context(
        self,
        session_key: str = "default",
    ) -> ActiveMemoryContext:
        """
        Retrieves active memories and maps them into a structured ActiveMemoryContext
        suitable for feeding into Query Understanding (Task 05A) and Orchestration.
        """
        memories = self.get_active_memories(session_key=session_key, limit=20)

        context = ActiveMemoryContext(session_key=session_key, raw_memories=memories)

        for mem in memories:
            key = mem.memory_key.lower()
            mtype = mem.memory_type.lower()

            if (key == "department" or mtype == "department") and not context.department:
                context.department = mem.memory_value
            elif (key == "role" or mtype == "role") and not context.role:
                context.role = mem.memory_value
            elif (key in ("employment_type", "employment_status") or mtype == "employment_type") and not context.employment_type:
                context.employment_type = mem.memory_value
            elif (key in ("location", "work_location", "office_location") or mtype == "location") and not context.location:
                context.location = mem.memory_value
            elif mtype == "user_constraint" or key.endswith("_constraint"):
                context.constraints.append(mem.memory_text)
            elif mtype == "policy_preference" or key.endswith("_preference"):
                context.preferences.append(mem.memory_text)

        return context

    # -------------------------------------------------------------------------
    # Subtask 06E.6: Memory Deletion & Expiration Purging
    # -------------------------------------------------------------------------

    def delete_memory(self, memory_id: uuid.UUID) -> bool:
        """
        Deletes a specific user memory record by UUID.
        Returns True if deleted, False if record was not found.
        """
        try:
            stmt = select(UserMemory).where(UserMemory.id == memory_id)
            record = self._db.execute(stmt).scalars().first()
            if not record:
                return False

            self._db.delete(record)
            self._db.commit()
            logger.info("Deleted memory id=%s", memory_id)
            return True

        except SQLAlchemyError as exc:
            self._db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to delete memory id=%s: %s", memory_id, sanitized)
            raise MemoryDatabaseError(f"Database error deleting memory: {sanitized}") from exc

    def clear_session_memories(self, session_key: str) -> int:
        """
        Purges all persistent memories for a given session key.
        Returns the number of deleted records.
        """
        try:
            stmt = delete(UserMemory).where(UserMemory.session_key == session_key)
            result = self._db.execute(stmt)
            self._db.commit()
            deleted_count = result.rowcount or 0
            logger.info("Cleared %d memories for session='%s'", deleted_count, session_key)
            return deleted_count

        except SQLAlchemyError as exc:
            self._db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to clear memories for session='%s': %s", session_key, sanitized)
            raise MemoryDatabaseError(f"Database error clearing session memories: {sanitized}") from exc

    def purge_expired_memories(self) -> int:
        """
        Purges all expired memory records across all sessions.
        Returns the count of purged rows.
        """
        try:
            now = datetime.now(timezone.utc)
            stmt = delete(UserMemory).where(
                UserMemory.expires_at.is_not(None),
                UserMemory.expires_at < now,
            )
            result = self._db.execute(stmt)
            self._db.commit()
            purged = result.rowcount or 0
            logger.info("Purged %d expired memory records", purged)
            return purged

        except SQLAlchemyError as exc:
            self._db.rollback()
            sanitized = sanitize_error_message(str(exc))
            logger.error("Failed to purge expired memories: %s", sanitized)
            raise MemoryDatabaseError(f"Database error purging expired memories: {sanitized}") from exc


def get_memory_service(
    db: Session,
    llm_client: Optional[LLMClient] = None,
) -> MemoryService:
    """Dependency injection provider for MemoryService."""
    return MemoryService(db=db, llm_client=llm_client)
