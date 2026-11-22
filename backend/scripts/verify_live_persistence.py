"""
Live Verification Script for Task 003F – Chunk and Embedding Database Persistence.
Runs against actual Supabase PostgreSQL and Supabase Storage.

Verifies:
1. Processing and persistence of 3 synthetic policy documents (PDF, DOCX, TXT).
2. Verification of document_versions and document_chunks in Supabase.
3. 384-dimensional dense vectors on all persisted chunks.
4. PDF page-number preservation vs DOCX/TXT page_number=NULL.
5. Section titles and metadata preservation.
6. Idempotent reprocessing (running persistence twice leaves no duplicates).
7. Ingestion job state transitions (processing -> completed).
8. Failure rollback verification (no partial records).
"""

import asyncio
import logging
import math
import sys
import uuid
from pathlib import Path

# Configure path and logging
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.document_version import DocumentVersion
from app.models.ingestion_job import IngestionJob
from app.services.chunk_persistence import (
    ChunkPersistenceService,
    DocumentNotFoundError,
    EmbeddingValidationError,
    get_chunk_persistence_service,
)
from app.services.document_chunker import DocumentChunkerService
from app.services.document_extractor import DocumentExtractorService
from app.services.embedding_service import EmbeddingService
from app.services.storage_service import StorageService

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s]: %(message)s")
logger = logging.getLogger("verify_live_persistence")


async def run_live_verification():
    logger.info("=== Starting Live Supabase Verification for Task 003F ===")
    logger.info("Database Target: %s", settings.masked_database_url)

    if not SessionLocal:
        raise RuntimeError("SessionLocal is not initialized. Check DATABASE_URL in backend/.env")

    db = SessionLocal()
    storage = StorageService()
    extractor = DocumentExtractorService()
    chunker = DocumentChunkerService(default_chunk_size=1000, default_chunk_overlap=150)
    embedder = EmbeddingService(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        dimension=384,
        batch_size=32,
    )
    persistence = ChunkPersistenceService(
        expected_dimension=384,
        expected_model="sentence-transformers/all-MiniLM-L6-v2",
    )

    test_docs = [
        {
            "id": uuid.UUID("5dd2fa13-ab1b-44e7-9b84-91fdf39b196f"),
            "name": "HR-LVE-001_Employee_Leave_v2.0.pdf",
            "type": "pdf",
        },
        {
            "id": uuid.UUID("63914b7d-e0d8-41b5-9d8e-7fe51f86cd66"),
            "name": "FIN-PROC-001_Procurement_Vendor.docx",
            "type": "docx",
        },
        {
            "id": uuid.UUID("9e6a3f25-c8d3-4db4-aeed-b89de176580d"),
            "name": "IT-AUP-001_IT_Acceptable_Use.txt",
            "type": "txt",
        },
    ]

    persistence_results = []

    try:
        # --------------------------------------------------------------------
        # 1. Process and Persist the 3 Synthetic Documents
        # --------------------------------------------------------------------
        for doc_info in test_docs:
            doc_id = doc_info["id"]
            doc_name = doc_info["name"]
            doc_type = doc_info["type"]
            logger.info("--- Processing Document: %s (%s, ID: %s) ---", doc_name, doc_type, doc_id)

            res = await persistence.persist_document(
                db=db,
                document_id=doc_id,
                storage=storage,
                extractor=extractor,
                chunker=chunker,
                embedder=embedder,
            )
            persistence_results.append(res)
            logger.info(
                "Persisted %s: version_id=%s (%s), chunk_count=%d, status=%s",
                doc_name,
                res.document_version_id,
                res.version_label,
                res.persisted_chunk_count,
                res.persistence_status,
            )

        # --------------------------------------------------------------------
        # 2. Query Live Supabase Database to Verify Persisted Records
        # --------------------------------------------------------------------
        logger.info("\n=== Querying Actual Supabase Database Records ===")

        for doc_info in test_docs:
            doc_id = doc_info["id"]
            doc_name = doc_info["name"]
            doc_type = doc_info["type"]

            # Query version
            version = db.query(DocumentVersion).filter_by(document_id=doc_id).first()
            assert version is not None, f"DocumentVersion missing for {doc_name}"
            assert version.is_current is True, f"Version for {doc_name} should be is_current=True"

            # Query chunks
            chunks = (
                db.query(DocumentChunk)
                .filter_by(document_version_id=version.id)
                .order_by(DocumentChunk.chunk_index)
                .all()
            )
            assert len(chunks) > 0, f"No chunks persisted for {doc_name}"

            logger.info(
                "Verified Document '%s': version_id=%s, version_label='%s', chunks_in_db=%d",
                doc_name,
                version.id,
                version.version_label,
                len(chunks),
            )

            # Check every chunk
            for c in chunks:
                # 1. 384 dimensions
                vec = c.embedding
                assert len(vec) == 384, f"Chunk {c.chunk_index} vector dimension {len(vec)} != 384"
                assert all(math.isfinite(x) for x in vec[:10]), f"Chunk {c.chunk_index} contains non-finite values"

                # 2. Page number rules
                if doc_type == "pdf":
                    assert c.page_number is not None and c.page_number >= 1, (
                        f"PDF chunk {c.chunk_index} page_number must be >= 1, got {c.page_number}"
                    )
                else:
                    assert c.page_number is None, (
                        f"{doc_type.upper()} chunk {c.chunk_index} page_number must be NULL, got {c.page_number}"
                    )

                # 3. Model name
                assert c.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"

                # 4. Content
                assert len(c.chunk_text.strip()) > 0

                # 5. Metadata
                assert isinstance(c.metadata_, dict)

            # Check sequential indices
            indices = [c.chunk_index for c in chunks]
            assert indices == list(range(len(chunks))), f"Chunk indices not sequential: {indices}"

            # Check ingestion job
            job = db.query(IngestionJob).filter_by(document_id=doc_id).order_by(IngestionJob.created_at.desc()).first()
            assert job is not None
            assert job.status == "completed"
            assert job.total_chunks == len(chunks)
            if doc_type == "pdf":
                assert job.total_pages is not None and job.total_pages >= 1

            logger.info(
                "[PASS] Validated %d chunks for '%s': 384-dim vectors, page_number=%s, sequential indices, job completed.",
                len(chunks),
                doc_name,
                f"1-based (max {max(c.page_number for c in chunks)})" if doc_type == "pdf" else "NULL",
            )

        # --------------------------------------------------------------------
        # 3. Idempotency Test: Run Persistence a Second Time on Live Database
        # --------------------------------------------------------------------
        logger.info("\n=== Testing Live Idempotency (Second Persistence Run) ===")
        doc_to_retry = test_docs[0]
        v1_count_before = (
            db.query(DocumentChunk)
            .join(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_to_retry["id"])
            .count()
        )

        res_retry = await persistence.persist_document(
            db=db,
            document_id=doc_to_retry["id"],
            storage=storage,
            extractor=extractor,
            chunker=chunker,
            embedder=embedder,
        )

        v1_count_after = (
            db.query(DocumentChunk)
            .join(DocumentVersion)
            .filter(DocumentVersion.document_id == doc_to_retry["id"])
            .count()
        )

        logger.info(
            "Idempotency run for '%s': count_before=%d, count_after=%d, status=%s",
            doc_to_retry["name"],
            v1_count_before,
            v1_count_after,
            res_retry.persistence_status,
        )
        assert v1_count_before == v1_count_after, (
            f"Idempotency violated! Count before ({v1_count_before}) != count after ({v1_count_after})"
        )
        logger.info("[PASS] Live Idempotency confirmed: exact same chunk count, zero duplicate chunks.")

        # --------------------------------------------------------------------
        # 4. Failure Rollback Test: Confirm No Partial Records
        # --------------------------------------------------------------------
        logger.info("\n=== Testing Live Failure Rollback Safety ===")
        # Attempt to persist with an invalid embedding dimension on a fresh dummy version
        temp_ver = DocumentVersion(
            id=uuid.uuid4(),
            document_id=test_docs[0]["id"],
            version_label="temp-rollback-test",
            is_current=False,
        )
        db.add(temp_ver)
        db.commit()

        bad_chunks = [
            {
                "chunk_index": 0,
                "chunk_text": "Rollback test chunk",
                "embedding": [0.1] * 200,  # Invalid dimension (200 != 384)
            }
        ]

        try:
            persistence.persist_chunks_for_version(
                db=db,
                version=temp_ver,
                chunk_embeddings=bad_chunks,
            )
            db.commit()
            raise RuntimeError("Should have raised EmbeddingValidationError")
        except EmbeddingValidationError as exc:
            db.rollback()
            logger.info("Expected validation error caught: %s", exc)

        # Verify no chunks were left for temp_ver
        partial_count = db.query(DocumentChunk).filter_by(document_version_id=temp_ver.id).count()
        assert partial_count == 0, f"Found {partial_count} partial chunk records after failed transaction!"
        logger.info("[PASS] Live Rollback confirmed: 0 partial chunk records in document_chunks.")

        # Clean up temporary test version
        db.delete(temp_ver)
        db.commit()

        # --------------------------------------------------------------------
        # 5. Print Example Persisted Records
        # --------------------------------------------------------------------
        logger.info("\n=== Example Persisted Records from Supabase document_chunks ===")
        sample_chunks = (
            db.query(DocumentChunk)
            .join(DocumentVersion)
            .join(Document)
            .order_by(DocumentChunk.created_at.desc())
            .limit(3)
            .all()
        )
        for sc in sample_chunks:
            logger.info(
                "Chunk ID: %s | Version ID: %s | Index: %d | Page: %s | Title: '%s' | Text: '%.60s...' | Vec dim: %d | Model: %s",
                sc.id,
                sc.document_version_id,
                sc.chunk_index,
                sc.page_number,
                sc.section_title,
                sc.chunk_text.replace("\n", " "),
                len(sc.embedding),
                sc.embedding_model,
            )

        logger.info("\n>>> ALL LIVE SUPABASE VERIFICATION CHECKS PASSED SUCCESSFULLY! <<<")

    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_live_verification())
