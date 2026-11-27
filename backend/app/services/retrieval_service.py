"""
Semantic Vector Search Retrieval Service with Metadata Filtering & Version Awareness.
Tasks 04C & 04D — KnowBridge AI Enterprise RAG Knowledge Platform.

Provides policy-aware semantic document-chunk retrieval using pgvector
and the PostgreSQL stored procedure `match_policy_chunks`.
Supports:
1. Dense vector embedding generation via local MiniLM (384d, L2 normalized).
2. Optional category and department metadata filtering.
3. Document status filtering to exclude incomplete or failed documents.
4. Correct current-version selection for ordinary current-policy questions.
5. Historical version retrieval when a specific date or version is requested.
6. Effective-date applicability (effective_from <= date <= effective_until).
7. Preservation of full provenance (title, version, page, section, text, score).
8. Overlap and version ambiguity reporting without silent evidence loss.
"""

import json
import logging
import uuid
from datetime import date
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.database import sanitize_error_message
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.schemas.retrieval import EvidenceItem, EvidencePackage, RetrievalResult, RetrievedChunk
from app.services.embedding_service import (
    EmbeddingError,
    EmbeddingService,
    InvalidQueryError,
    get_embedding_service,
)

logger = logging.getLogger("app.services.retrieval")


# ============================================================================
# Custom Exceptions
# ============================================================================

class RetrievalError(Exception):
    """Base exception for retrieval engine operations."""
    pass


class InvalidRetrievalParameterError(RetrievalError):
    """Raised when query or search parameters (top_k, similarity_threshold) are invalid."""
    pass


class RetrievalDatabaseError(RetrievalError):
    """Raised when the database fails during vector search query execution."""
    pass


# ============================================================================
# Version & Text Normalization Helpers
# ============================================================================

def normalize_version(ver: Optional[str]) -> str:
    """Normalizes version strings by removing whitespace, lowering case, and stripping leading 'v'."""
    if not ver:
        return ""
    cleaned = str(ver).strip().lower()
    if cleaned.startswith("v") and len(cleaned) > 1 and cleaned[1].isdigit():
        return cleaned[1:]
    return cleaned


def versions_match(v1: Optional[str], v2: Optional[str]) -> bool:
    """Returns True if two version strings represent the same semantic release (e.g. 'v1.0' == '1.0')."""
    if not v1 or not v2:
        return False
    return normalize_version(v1) == normalize_version(v2)


# ============================================================================
# Retrieval Service Implementation
# ============================================================================

class RetrievalService:
    """
    Policy-aware semantic retrieval service coordinating:
    1. Query embedding generation via SentenceTransformers.
    2. Candidate vector retrieval via PostgreSQL `match_policy_chunks`.
    3. Metadata filtering: category, department, document processing status.
    4. Version-aware selection: current active policy vs historical date/version.
    5. Ambiguity and version-overlap detection with full evidence preservation.
    """

    def __init__(
        self,
        embedding_service: Optional[EmbeddingService] = None,
        default_top_k: int = 5,
        default_threshold: float = 0.35,
    ) -> None:
        """
        Initializes the retrieval service.

        Args:
            embedding_service: EmbeddingService instance. Defaults to application singleton.
            default_top_k: Default candidate count matching SQL function match_count parameter (5).
            default_threshold: Default similarity threshold matching SQL function match_threshold (0.65).
        """
        self.embedding_service = embedding_service or get_embedding_service()
        self.default_top_k = default_top_k
        self.default_threshold = default_threshold

    def retrieve_chunks(
        self,
        db: Session,
        query: str,
        top_k: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
        target_date: Optional[date] = None,
        category: Optional[str] = None,
        department: Optional[str] = None,
        document_status: Optional[str] = "completed",
        version: Optional[str] = None,
        is_current_only: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> RetrievalResult:
        """
        Executes policy-aware semantic vector search with metadata and version filtering.

        Args:
            db: Active SQLAlchemy transactional session.
            query: User natural-language question or search query.
            top_k: Maximum candidate chunks to return (defaults to 5; must be positive integer).
            similarity_threshold: Cosine similarity cutoff (defaults to 0.65; must be 0.0 <= x <= 1.0).
            target_date: Temporal validity date for policy applicability (defaults to date.today()).
            category: Optional category filter (e.g. 'HR', 'Finance', 'IT').
            department: Optional originating department filter (e.g. 'Human Resources').
            document_status: Document status to require (defaults to 'completed'; set None to disable).
            version: Specific version label to retrieve (e.g. '1.0' or 'v2.0').
            is_current_only: If True, restricts strictly to active current revisions. Defaults to True
                             unless an explicit version or historical date is requested.
            limit: Configurable final result limit applied to returned evidence items (defaults to top_k).

        Returns:
            RetrievalResult containing ranked candidate chunks with full provenance and ambiguity audit.

        Raises:
            InvalidRetrievalParameterError: If question or parameters are invalid.
            RetrievalDatabaseError: If database query fails.
            RetrievalError: If embedding generation or unexpected error occurs.
        """
        # 1. Validate query input
        if not isinstance(query, str) or not query.strip():
            raise InvalidRetrievalParameterError("Query cannot be empty or whitespace-only.")

        cleaned_query = query.strip()

        # 2. Validate top_k parameter
        if top_k is not None:
            if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k <= 0:
                raise InvalidRetrievalParameterError(f"top_k must be a positive integer, got: {top_k}")
            eff_top_k = top_k
        else:
            eff_top_k = self.default_top_k

        # 3. Validate limit parameter
        if limit is not None:
            if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
                raise InvalidRetrievalParameterError(f"limit must be a positive integer, got: {limit}")
            eff_limit = limit
        else:
            eff_limit = eff_top_k

        # 4. Validate similarity_threshold parameter
        if similarity_threshold is not None:
            if not isinstance(similarity_threshold, (int, float)) or isinstance(similarity_threshold, bool):
                raise InvalidRetrievalParameterError(
                    f"similarity_threshold must be a numerical float, got: {type(similarity_threshold).__name__}"
                )
            if not (0.0 <= similarity_threshold <= 1.0):
                raise InvalidRetrievalParameterError(
                    f"similarity_threshold must be between 0.0 and 1.0, got: {similarity_threshold}"
                )
            eff_threshold = float(similarity_threshold)
        else:
            eff_threshold = self.default_threshold

        # 5. Resolve target_date and version intent
        today = date.today()
        eff_date = target_date if target_date is not None else today

        # Determine effective current-only mode:
        # If caller specified version, disable current-only (they want that specific version).
        # If caller specified a historical target_date in the past, disable current-only (they want historical applicability).
        # Otherwise, default to True (ordinary current-policy inquiry).
        if is_current_only is not None:
            effective_current_only = is_current_only
        elif version is not None:
            effective_current_only = False
        elif target_date is not None and target_date < today:
            effective_current_only = False
        else:
            effective_current_only = True

        # 6. Generate 384-dimensional normalized query embedding
        try:
            query_vector = self.embedding_service.embed_query(cleaned_query)
        except InvalidQueryError as exc:
            raise InvalidRetrievalParameterError(str(exc)) from exc
        except EmbeddingError as exc:
            raise RetrievalError(f"Query embedding generation failed: {exc}") from exc

        # Format vector for pgvector string representation: '[x1,x2,...]'
        vector_str = f"[{','.join(str(x) for x in query_vector)}]"

        # When metadata filters are explicitly active, request sufficient candidate depth from SQL
        eff_fetch_k = max(eff_top_k, eff_limit)
        has_metadata_filters = bool(
            category or department or version or (is_current_only is False)
        )
        candidate_count = max(eff_fetch_k * 4, 20) if has_metadata_filters else eff_fetch_k

        # 7. Execute match_policy_chunks via SQLAlchemy text query
        sql = text("""
            SELECT
                chunk_id,
                document_id,
                document_title,
                version_id,
                version_number,
                effective_date,
                sunset_date,
                page_number,
                content,
                similarity,
                chunk_metadata
            FROM match_policy_chunks(
                cast(:query_embedding as vector),
                :target_date,
                :match_threshold,
                :match_count
            )
        """)

        params = {
            "query_embedding": vector_str,
            "target_date": eff_date,
            "match_threshold": eff_threshold,
            "match_count": candidate_count,
        }

        try:
            result = db.execute(sql, params)
            rows = result.mappings().all()
        except SQLAlchemyError as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error(
                "Database error executing match_policy_chunks for query '%s': %s",
                cleaned_query,
                sanitized,
            )
            raise RetrievalDatabaseError(f"Database error during semantic retrieval: {sanitized}") from exc
        except Exception as exc:
            sanitized = sanitize_error_message(str(exc))
            logger.error("Unexpected error during semantic retrieval: %s", sanitized)
            raise RetrievalError(f"Semantic retrieval failed: {sanitized}") from exc

        # 7. Metadata Resolution & Filtering
        filtered_candidates: list[RetrievedChunk] = []

        # Local caches for document and version lookups to minimize DB roundtrips
        doc_cache: dict[uuid.UUID, Optional[Document]] = {}
        ver_cache: dict[uuid.UUID, Optional[DocumentVersion]] = {}

        for row in rows:
            # Parse chunk metadata
            meta = row.get("chunk_metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            elif not isinstance(meta, dict):
                meta = {}

            # Parse UUIDs
            raw_chunk_id = row.get("chunk_id")
            chunk_uuid = raw_chunk_id if isinstance(raw_chunk_id, uuid.UUID) else uuid.UUID(str(raw_chunk_id))

            raw_doc_id = row.get("document_id")
            doc_uuid = None
            if raw_doc_id:
                doc_uuid = raw_doc_id if isinstance(raw_doc_id, uuid.UUID) else uuid.UUID(str(raw_doc_id))

            raw_ver_id = row.get("version_id")
            ver_uuid = None
            if raw_ver_id:
                ver_uuid = raw_ver_id if isinstance(raw_ver_id, uuid.UUID) else uuid.UUID(str(raw_ver_id))

            # --- A. Resolve Document Attributes ---
            chunk_category = row.get("category") or meta.get("category")
            chunk_department = row.get("department") or meta.get("department")
            chunk_doc_status = row.get("document_status") or row.get("status") or meta.get("document_status")

            if doc_uuid and (chunk_category is None or chunk_department is None or chunk_doc_status is None):
                if doc_uuid not in doc_cache:
                    try:
                        query_fn = getattr(db, "query", None)
                        if callable(query_fn):
                            res = query_fn(Document).filter(Document.id == doc_uuid).first()
                            doc_cache[doc_uuid] = res if isinstance(res, Document) else None
                        else:
                            doc_cache[doc_uuid] = None
                    except Exception:
                        doc_cache[doc_uuid] = None
                doc_obj = doc_cache[doc_uuid]
                if doc_obj:
                    if chunk_category is None:
                        chunk_category = doc_obj.category
                    if chunk_department is None:
                        chunk_department = doc_obj.department
                    if chunk_doc_status is None:
                        chunk_doc_status = doc_obj.status

            # --- B. Resolve Version Attributes ---
            version_str = row.get("version_number") or row.get("version_label") or meta.get("version_label")
            chunk_is_current = row.get("is_current")
            if chunk_is_current is None and "is_current" in meta:
                chunk_is_current = meta["is_current"]

            chunk_eff_from = row.get("effective_from") or row.get("effective_date") or meta.get("effective_from")
            chunk_eff_until = row.get("effective_until") or row.get("sunset_date") or meta.get("effective_until")

            if ver_uuid and (chunk_is_current is None or chunk_eff_from is None):
                if ver_uuid not in ver_cache:
                    try:
                        query_fn = getattr(db, "query", None)
                        if callable(query_fn):
                            res = query_fn(DocumentVersion).filter(DocumentVersion.id == ver_uuid).first()
                            ver_cache[ver_uuid] = res if isinstance(res, DocumentVersion) else None
                        else:
                            ver_cache[ver_uuid] = None
                    except Exception:
                        ver_cache[ver_uuid] = None
                ver_obj = ver_cache[ver_uuid]
                if ver_obj:
                    if chunk_is_current is None:
                        chunk_is_current = ver_obj.is_current
                    if chunk_eff_from is None:
                        chunk_eff_from = ver_obj.effective_from
                    if chunk_eff_until is None:
                        chunk_eff_until = ver_obj.effective_until
                    if not version_str:
                        version_str = ver_obj.version_label

            # --- C. Apply Filters ---

            # 1. Document Status Filter (exclude failed, processing, incomplete documents)
            if document_status is not None and isinstance(chunk_doc_status, str):
                # Exclude incomplete or failed statuses
                if chunk_doc_status.lower() in ("failed", "processing", "incomplete", "error", "corrupted"):
                    continue
                if document_status and chunk_doc_status.lower() != document_status.lower():
                    continue

            # 2. Category Filter
            if category:
                if not isinstance(chunk_category, str) or chunk_category.strip().lower() != category.strip().lower():
                    continue

            # 3. Department Filter
            if department:
                if not isinstance(chunk_department, str) or chunk_department.strip().lower() != department.strip().lower():
                    continue

            # 4. Version & Temporal Applicability Filtering
            if version:
                # Specific version requested: must match version string
                if not versions_match(version, version_str):
                    continue
            elif effective_current_only:
                # Ordinary current question: strictly exclude historical versions
                if chunk_is_current is False:
                    continue
                # Date applicability boundary check
                if chunk_eff_from and chunk_eff_from > eff_date:
                    continue
                if chunk_eff_until and chunk_eff_until < eff_date:
                    continue
            else:
                # Historical date query: check date boundaries
                if chunk_eff_from and chunk_eff_from > eff_date:
                    continue
                if chunk_eff_until and chunk_eff_until < eff_date:
                    continue

            # --- D. Resolve Section and Text Content ---
            sec_title = (
                row.get("section_title")
                or meta.get("section_title")
                or (meta.get("section_hierarchy")[-1] if meta.get("section_hierarchy") else None)
            )
            content_text = row.get("content") or row.get("chunk_text") or ""

            # Similarity bounded to [0.0, 1.0]
            raw_sim = float(row.get("similarity", 0.0))
            sim_score = max(0.0, min(1.0, round(raw_sim, 6)))

            candidate = RetrievedChunk(
                chunk_id=chunk_uuid,
                document_id=doc_uuid,
                document_title=str(row.get("document_title") or "Untitled Document"),
                chunk_text=str(content_text),
                similarity_score=sim_score,
                page_number=row.get("page_number"),
                section_title=sec_title,
                document_version=str(version_str) if version_str is not None else None,
                version_label=str(version_str) if version_str is not None else None,
                category=str(chunk_category) if chunk_category is not None else None,
                department=str(chunk_department) if chunk_department is not None else None,
                is_current=chunk_is_current,
                effective_from=chunk_eff_from,
                effective_until=chunk_eff_until,
                is_ambiguous=False,
                chunk_metadata=meta,
            )
            filtered_candidates.append(candidate)

        # 8. Ambiguity & Version Overlap Detection
        # If multiple versions of the same document match the requested date, preserve all
        # evidence and report ambiguity rather than guessing.
        has_version_ambiguity = False
        ambiguity_notes: list[str] = []

        # Group candidates by document
        doc_versions_map: dict[str, set[str]] = {}
        for c in filtered_candidates:
            key = str(c.document_id) if c.document_id else c.document_title
            if c.document_version:
                doc_versions_map.setdefault(key, set()).add(c.document_version)

        # Flag overlapping versions
        for key, vers in doc_versions_map.items():
            if len(vers) > 1:
                has_version_ambiguity = True
                ver_list = ", ".join(sorted(vers))
                note = f"Multiple overlapping versions ({ver_list}) detected for document '{key}' on {eff_date}. Preserved evidence."
                ambiguity_notes.append(note)
                logger.warning(note)
                # Mark all chunks belonging to this document as ambiguous
                for c in filtered_candidates:
                    c_key = str(c.document_id) if c.document_id else c.document_title
                    if c_key == key:
                        c.is_ambiguous = True

        # 9. Deterministic Ranking & Tie-Breaking
        # Primary: similarity score descending (-c.similarity_score)
        # Secondary: current revisions prioritized over historical/unspecified (0=True, 1=None, 2=False)
        # Tertiary: alphabetical document title (c.document_title or "")
        # Quaternary: page number (c.page_number if not None else 999999)
        # Quinary: chunk UUID string for deterministic stability across platforms
        def ranking_key(c: RetrievedChunk):
            current_order = 0 if c.is_current is True else (1 if c.is_current is None else 2)
            page_order = c.page_number if c.page_number is not None else 999999
            return (
                -c.similarity_score,
                current_order,
                c.document_title or "",
                page_order,
                str(c.chunk_id),
            )

        sorted_candidates = sorted(filtered_candidates, key=ranking_key)

        # 10. Deduplication by chunk_id
        # Discard duplicate chunks if the exact same chunk_id appears multiple times.
        # Distinct chunks with identical or similar text MUST be preserved.
        seen_chunk_ids: set[uuid.UUID] = set()
        deduped_candidates: list[RetrievedChunk] = []
        for c in sorted_candidates:
            if c.chunk_id not in seen_chunk_ids:
                seen_chunk_ids.add(c.chunk_id)
                deduped_candidates.append(c)

        # 11. Final Limit Slicing
        final_chunks = deduped_candidates[:eff_limit]

        # 12. Structured Evidence Package Formatting
        evidence_pkg = self.format_evidence_package(
            query=cleaned_query,
            chunks=final_chunks,
            limit=eff_limit,
            has_conflicts=has_version_ambiguity,
        )

        logger.info(
            "Retrieval completed for query '%s': returned %d chunks (limit=%d, filters: cat=%s, dept=%s, ver=%s, current_only=%s)",
            cleaned_query,
            len(final_chunks),
            eff_limit,
            category,
            department,
            version,
            effective_current_only,
        )

        return RetrievalResult(
            query=cleaned_query,
            total_retrieved=len(final_chunks),
            chunks=final_chunks,
            similarity_threshold=eff_threshold,
            top_k=eff_top_k,
            applied_limit=eff_limit,
            target_date=eff_date,
            category_filter=category,
            department_filter=department,
            version_filter=version,
            is_current_only=effective_current_only,
            has_version_ambiguity=has_version_ambiguity,
            ambiguity_notes=ambiguity_notes,
            evidence_package=evidence_pkg,
        )

    def format_evidence_package(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        limit: int,
        has_conflicts: bool = False,
    ) -> EvidencePackage:
        """
        Builds a deterministic, clean structured evidence package suitable for downstream LLM synthesis.

        Args:
            query: User's search query or question.
            chunks: Ranked, deduplicated list of retrieved chunks.
            limit: Final result limit applied.
            has_conflicts: True if version ambiguity or conflicting revisions were detected.

        Returns:
            EvidencePackage containing indexed EvidenceItem models and a formatted context text block.
        """
        if not chunks:
            return EvidencePackage(
                query=query,
                total_evidence_count=0,
                items=[],
                formatted_context="No relevant policy documents or evidence were found matching the query.",
                has_conflicts=has_conflicts,
                is_sufficient=False,
                applied_limit=limit,
            )

        items: list[EvidenceItem] = []
        context_blocks: list[str] = []

        for idx, chunk in enumerate(chunks, start=1):
            tag_parts: list[str] = [chunk.document_title]
            ver = chunk.version_label or chunk.document_version
            if ver:
                tag_parts[0] += f" ({ver})"
            if chunk.page_number is not None:
                tag_parts.append(f"p. {chunk.page_number}")
            if chunk.section_title:
                tag_parts.append(f"Section: {chunk.section_title}")
            citation_tag = f"[{', '.join(tag_parts)}]"

            item = EvidenceItem(
                citation_index=idx,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_title=chunk.document_title,
                version_label=ver,
                effective_from=chunk.effective_from,
                effective_until=chunk.effective_until,
                chunk_text=chunk.chunk_text,
                similarity_score=chunk.similarity_score,
                page_number=chunk.page_number,
                section_title=chunk.section_title,
                citation_tag=citation_tag,
            )
            items.append(item)

            header = f"[{idx}] {citation_tag} (Similarity: {chunk.similarity_score:.4f})"
            block = f"{header}\n{chunk.chunk_text}"
            context_blocks.append(block)

        formatted_context = "\n\n".join(context_blocks)

        return EvidencePackage(
            query=query,
            total_evidence_count=len(items),
            items=items,
            formatted_context=formatted_context,
            has_conflicts=has_conflicts,
            is_sufficient=True,
            applied_limit=limit,
        )


# ============================================================================
# FastAPI Dependency Provider
# ============================================================================

def get_retrieval_service(
    embedding_service: EmbeddingService = None,
) -> RetrievalService:
    """FastAPI dependency provider returning configured RetrievalService."""
    return RetrievalService(embedding_service=embedding_service or get_embedding_service())
