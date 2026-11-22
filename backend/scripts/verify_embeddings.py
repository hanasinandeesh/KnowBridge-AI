#!/usr/bin/env python3
"""
KnowBridge AI — Task 003E: Embedding Generation Verification Script

Loads 3 actual synthetic policy documents:
1. PDF: HR-TRV-001_Travel_Reimbursement_v1.0.pdf
2. DOCX: FIN-EXP-001_Employee_Expense.docx
3. TXT: IT-AUP-001_IT_Acceptable_Use.txt

For each document:
- Parses with Task 003C extractors.
- Chunks with Task 003D DocumentChunkerService.
- Generates 384-dimensional dense embeddings with Task 003E EmbeddingService.
- Validates 384 dimensions, finite numeric values, L2 normalization, order preservation.
- Prints representative chunk embedding previews.

Usage:
    cd backend
    python scripts/verify_embeddings.py
"""

import math
import sys
import uuid
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

import numpy as np

from app.core.config import settings
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.services.document_chunker import DocumentChunkerService
from app.services.embedding_service import EmbeddingService


def run_embedding_verification() -> bool:
    print("=" * 80)
    print("KnowBridge AI — Task 003E: Embedding Generation Verification")
    print("=" * 80)
    print(f"Model: {settings.EMBEDDING_MODEL_NAME}")
    print(f"Expected Dimension: {settings.EMBEDDING_DIMENSION}")
    print(f"Batch Size: {settings.EMBEDDING_BATCH_SIZE}")
    print(f"Normalize: {settings.EMBEDDING_NORMALIZE}")
    print("=" * 80)

    policies_dir = WORKSPACE_DIR / "synthetic-data" / "policies"
    if not policies_dir.exists():
        print(f"[ERROR] Policies directory not found at: {policies_dir}")
        return False

    chunker = DocumentChunkerService(
        default_chunk_size=settings.CHUNK_SIZE,
        default_chunk_overlap=settings.CHUNK_OVERLAP,
    )
    embedder = EmbeddingService(
        model_name=settings.EMBEDDING_MODEL_NAME,
        dimension=settings.EMBEDDING_DIMENSION,
        batch_size=settings.EMBEDDING_BATCH_SIZE,
        normalize_embeddings=settings.EMBEDDING_NORMALIZE,
    )

    documents_to_test = [
        ("PDF", "HR-TRV-001_Travel_Reimbursement_v1.0.pdf", PDFParser()),
        ("DOCX", "FIN-EXP-001_Employee_Expense.docx", DOCXParser()),
        ("TXT", "IT-AUP-001_IT_Acceptable_Use.txt", TXTParser()),
    ]

    all_passed = True
    representative_samples = []

    for doc_type, filename, parser in documents_to_test:
        fpath = policies_dir / filename
        print(f"\n--- Testing {doc_type}: {filename} ---")
        if not fpath.exists():
            print(f"[ERROR] File not found: {fpath}")
            all_passed = False
            continue

        raw_bytes = fpath.read_bytes()
        doc_id = uuid.uuid4()

        # Step 1: Extraction (Task 003C)
        extraction = parser.parse(raw_bytes, filename=filename, document_id=doc_id)
        print(f"  [1] Extracted: {len(extraction.pages)} content units, {extraction.total_characters} characters")

        # Step 2: Chunking (Task 003D)
        chunk_result = chunker.chunk_document(extraction)
        print(f"  [2] Chunked: {chunk_result.total_chunks} chunks produced")

        if chunk_result.total_chunks == 0:
            print("  [ERROR] Document produced 0 chunks!")
            all_passed = False
            continue

        # Step 3: Embedding Generation (Task 003E)
        embedding_result = embedder.embed_document_result(chunk_result)
        print(f"  [3] Embedded: {embedding_result.total_chunks} embeddings generated")

        # Step 4: Strict Validations
        # A. Count matching
        if len(embedding_result.embeddings) != chunk_result.total_chunks:
            print(f"  [FAIL] Embedding count ({len(embedding_result.embeddings)}) != Chunk count ({chunk_result.total_chunks})")
            all_passed = False

        # B. Dimension, finite values, normalization, order preservation
        all_dims_correct = True
        all_finite = True
        all_normalized = True
        order_preserved = True

        for idx, emb in enumerate(embedding_result.embeddings):
            # Check order
            if emb.chunk_index != idx:
                order_preserved = False
            if emb.chunk_text != chunk_result.chunks[idx].chunk_text:
                order_preserved = False

            # Check dimensions
            if len(emb.embedding) != 384 or emb.dimension != 384:
                all_dims_correct = False

            # Check finite values
            vec = np.array(emb.embedding, dtype=np.float32)
            if not np.all(np.isfinite(vec)):
                all_finite = False

            # Check L2 normalization (unit length)
            norm = np.linalg.norm(vec)
            if not math.isclose(norm, 1.0, rel_tol=1e-3):
                all_normalized = False

        print(f"  [Validation] 384 Dimensions: {'PASS' if all_dims_correct else 'FAIL'}")
        print(f"  [Validation] All Finite Values (no NaN/Inf): {'PASS' if all_finite else 'FAIL'}")
        print(f"  [Validation] L2 Normalization (norm ≈ 1.0): {'PASS' if all_normalized else 'FAIL'}")
        print(f"  [Validation] Exact Chunk Order Preserved: {'PASS' if order_preserved else 'FAIL'}")

        if not (all_dims_correct and all_finite and all_normalized and order_preserved):
            all_passed = False

        # Pick a representative chunk for reporting
        sample_chunk = embedding_result.embeddings[0]
        representative_samples.append({
            "doc_type": doc_type,
            "filename": filename,
            "chunk_index": sample_chunk.chunk_index,
            "section_title": sample_chunk.section_title or "N/A",
            "page_number": sample_chunk.page_number if sample_chunk.page_number is not None else "None (non-PDF)",
            "model_name": sample_chunk.embedding_model,
            "dimension": len(sample_chunk.embedding),
            "preview": [round(float(v), 5) for v in sample_chunk.embedding[:8]],
            "norm": round(float(np.linalg.norm(sample_chunk.embedding)), 5),
            "text_preview": sample_chunk.chunk_text[:120].replace("\n", " "),
        })

    # Step 5: Test query embedding
    print("\n--- Testing Search Query Embedding ---")
    query_text = "What is the maximum reimbursement for business meals and per diem?"
    query_vector = embedder.embed_query(query_text)
    query_norm = np.linalg.norm(query_vector)
    query_valid = len(query_vector) == 384 and np.all(np.isfinite(query_vector)) and math.isclose(query_norm, 1.0, rel_tol=1e-3)
    print(f"  Query: '{query_text}'")
    print(f"  Dimension: {len(query_vector)}")
    print(f"  Finite & Normalized: {'PASS' if query_valid else 'FAIL'} (norm={round(float(query_norm), 5)})")
    print(f"  Vector preview (first 8 dims): {[round(float(v), 5) for v in query_vector[:8]]}")

    if not query_valid:
        all_passed = False

    # Print representative summary
    print("\n" + "=" * 80)
    print("REPRESENTATIVE REAL-MODEL EMBEDDING RESULTS")
    print("=" * 80)
    for sample in representative_samples:
        print(f"\nDocument ({sample['doc_type']}): {sample['filename']}")
        print(f"  * Chunk Index:       {sample['chunk_index']}")
        print(f"  * Section Title:     {sample['section_title']}")
        print(f"  * Page Number:       {sample['page_number']}")
        print(f"  * Model Name:        {sample['model_name']}")
        print(f"  * Embedding Dim:     {sample['dimension']}")
        print(f"  * Vector L2 Norm:    {sample['norm']}")
        print(f"  * Vector Preview:    {sample['preview']}... (8 of 384)")
        print(f"  * Text Preview:      \"{sample['text_preview']}...\"")

    print("\n" + "=" * 80)
    if all_passed:
        print("ALL EMBEDDING GENERATION VERIFICATIONS PASSED SUCCESSFULLY!")
    else:
        print("ONE OR MORE VERIFICATION CHECKS FAILED.")
    print("=" * 80)
    return all_passed


if __name__ == "__main__":
    success = run_embedding_verification()
    sys.exit(0 if success else 1)
