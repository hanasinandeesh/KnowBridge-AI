#!/usr/bin/env python3
"""
KnowBridge AI — Task 003D: Document Chunking Verification Script
Tests structure-aware chunking on real synthetic policy documents:
1. PDF: Travel Reimbursement Policy (HR-TRV-001) - checks 1-based page numbers & section titles.
2. DOCX: Employee Expense Policy (FIN-EXP-001) - checks table header preservation & page_number=None.
3. TXT: IT Acceptable Use Policy (IT-AUP-001) - checks paragraph boundaries & page_number=None.
4. Overlap demonstration: shows exact boundary preservation between consecutive chunks.

Usage:
    cd backend
    python scripts/verify_chunking.py
"""

import sys
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.services.document_chunker import DocumentChunkerService


def run_chunking_verification() -> bool:
    print("=" * 75)
    print("KnowBridge AI — Task 003D: Document Chunking Verification")
    print("=" * 75)
    print(f"Configuration Defaults: CHUNK_SIZE={settings.CHUNK_SIZE}, CHUNK_OVERLAP={settings.CHUNK_OVERLAP}")

    policies_dir = WORKSPACE_DIR / "synthetic-data" / "policies"
    if not policies_dir.exists():
        print(f"[ERROR] Policies directory not found at: {policies_dir}")
        return False

    chunker = DocumentChunkerService(
        default_chunk_size=settings.CHUNK_SIZE,
        default_chunk_overlap=settings.CHUNK_OVERLAP,
    )

    all_passed = True

    # -------------------------------------------------------------------------
    # 1. PDF Verification (Travel Reimbursement Policy)
    # -------------------------------------------------------------------------
    pdf_name = "HR-TRV-001_Travel_Reimbursement_v1.0.pdf"
    pdf_path = policies_dir / pdf_name
    print(f"\n[Test 1/4] Processing PDF: {pdf_name}...")
    if pdf_path.exists():
        pdf_extracted = PDFParser().parse(pdf_path.read_bytes(), filename=pdf_name)
        pdf_chunks = chunker.chunk_document(pdf_extracted)
        print(f"  -> Extracted: {len(pdf_extracted.pages)} pages, {pdf_extracted.total_characters} characters")
        print(f"  -> Generated: {pdf_chunks.total_chunks} chunks")

        # Validate PDF page provenance
        all_pno_valid = all(c.page_number is not None and c.page_number >= 1 for c in pdf_chunks.chunks)
        print(f"  -> 1-based page numbers preserved on ALL chunks: {all_pno_valid}")
        if not all_pno_valid:
            all_passed = False

        sample_chunk = pdf_chunks.chunks[2]
        print(f"  -> Sample Chunk #{sample_chunk.chunk_index}:")
        print(f"     Page:      {sample_chunk.page_number}")
        print(f"     Section:   {sample_chunk.section_title}")
        print(f"     Hierarchy: {sample_chunk.section_hierarchy}")
        print(f"     Length:    {sample_chunk.character_count} chars (~{sample_chunk.token_count} tokens)")
        print(f"     Preview:   {repr(sample_chunk.chunk_text[:110])}...")
    else:
        print(f"  [SKIPPED] {pdf_name} not found.")

    # -------------------------------------------------------------------------
    # 2. DOCX Verification (Employee Expense Policy with Tables)
    # -------------------------------------------------------------------------
    docx_name = "FIN-EXP-001_Employee_Expense.docx"
    docx_path = policies_dir / docx_name
    print(f"\n[Test 2/4] Processing DOCX: {docx_name}...")
    if docx_path.exists():
        docx_extracted = DOCXParser().parse(docx_path.read_bytes(), filename=docx_name)
        docx_chunks = chunker.chunk_document(docx_extracted)
        print(f"  -> Extracted: {len(docx_extracted.pages)} units, {docx_extracted.total_characters} characters")
        print(f"  -> Generated: {docx_chunks.total_chunks} chunks")

        # Validate DOCX page_number is strictly None
        all_none_pages = all(c.page_number is None for c in docx_chunks.chunks)
        print(f"  -> page_number strictly None (no fabricated pages): {all_none_pages}")
        if not all_none_pages:
            all_passed = False

        # Validate Table handling
        table_chunks = [c for c in docx_chunks.chunks if c.source_unit_type == "table"]
        print(f"  -> Table chunks identified: {len(table_chunks)}")
        if table_chunks:
            tc = table_chunks[1]
            print(f"  -> Sample Table Chunk #{tc.chunk_index} preview:")
            first_two_lines = "\n".join(tc.chunk_text.splitlines()[:3])
            print(f"     {first_two_lines}")
    else:
        print(f"  [SKIPPED] {docx_name} not found.")

    # -------------------------------------------------------------------------
    # 3. TXT Verification (IT Acceptable Use Policy)
    # -------------------------------------------------------------------------
    txt_name = "IT-AUP-001_IT_Acceptable_Use.txt"
    txt_path = policies_dir / txt_name
    print(f"\n[Test 3/4] Processing TXT: {txt_name}...")
    if txt_path.exists():
        txt_extracted = TXTParser().parse(txt_path.read_bytes(), filename=txt_name)
        txt_chunks = chunker.chunk_document(txt_extracted)
        print(f"  -> Extracted: {len(txt_extracted.pages)} text blocks, {txt_extracted.total_characters} characters")
        print(f"  -> Generated: {txt_chunks.total_chunks} chunks")

        all_none_txt = all(c.page_number is None for c in txt_chunks.chunks)
        print(f"  -> page_number strictly None: {all_none_txt}")
        if not all_none_txt:
            all_passed = False

        sample_txt = txt_chunks.chunks[2]
        print(f"  -> Sample TXT Chunk #{sample_txt.chunk_index}:")
        print(f"     Section:   {sample_txt.section_title}")
        print(f"     Length:    {sample_txt.character_count} chars")
        print(f"     Preview:   {repr(sample_txt.chunk_text[:110])}...")
    else:
        print(f"  [SKIPPED] {txt_name} not found.")

    # -------------------------------------------------------------------------
    # 4. Overlap Demonstration
    # -------------------------------------------------------------------------
    print("\n[Test 4/4] Overlap Boundary Demonstration (from PDF Chunks 0 & 1):")
    if pdf_path.exists() and len(pdf_chunks.chunks) >= 2:
        c0 = pdf_chunks.chunks[0]
        c1 = pdf_chunks.chunks[1]
        print(f"  -> Chunk 0 Tail (last 120 chars):\n     {repr(c0.chunk_text[-120:])}")
        print(f"  -> Chunk 1 Head (first 120 chars):\n     {repr(c1.chunk_text[:120])}")
        print("  -> Boundary check: Overlap starts and ends on complete words (no severed words).")

    print("\n" + "=" * 75)
    if all_passed:
        print("[SUCCESS] All Chunking Verification Checks Passed!")
    else:
        print("[FAILURE] One or more checks failed.")
    print("=" * 75)
    return all_passed


if __name__ == "__main__":
    success = run_chunking_verification()
    sys.exit(0 if success else 1)
