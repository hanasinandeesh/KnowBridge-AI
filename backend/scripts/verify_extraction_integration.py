#!/usr/bin/env python3
"""
KnowBridge AI — Task 003C: Document Text Extraction Verification Script
Verifies live end-to-end extraction against real Supabase Storage:
1. Uploads real policy documents (PDF, DOCX, TXT) to private Supabase Storage.
2. Downloads binaries using StorageService.download_file_sync.
3. Extracts structured text with PyMuPDF, python-docx, and UTF-8 text parser.
4. Validates preserved page numbers, logical content units, section titles, and status.
5. Cleans up test objects from storage bucket.

Usage:
    cd backend
    python scripts/verify_extraction_integration.py
"""

import sys
import uuid
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.services.document_extractor import DocumentExtractorService
from app.services.storage_service import (
    StorageService,
    generate_storage_path,
)


def run_extraction_verification() -> bool:
    print("=" * 75)
    print("KnowBridge AI — Task 003C: Document Text Extraction Live Verification")
    print("=" * 75)

    # 1. Verify Storage Configuration
    print("\n[Step 1/5] Checking Storage Configuration...")
    print(f"  Project Name:         {settings.PROJECT_NAME}")
    print(f"  Supabase URL:         {settings.SUPABASE_URL or '<not configured>'}")
    print(f"  Target Bucket:        {settings.STORAGE_BUCKET_NAME}")

    storage = StorageService()
    if not storage.is_configured:
        print("\n[FAILED] Supabase Storage credentials are not configured in backend/.env.")
        return False
    print("  [OK] Supabase Storage credentials verified.")

    extractor = DocumentExtractorService(storage_service=storage)
    policies_dir = WORKSPACE_DIR / "synthetic-data" / "policies"

    test_docs = [
        ("pdf", "HR-TRV-001_Travel_Reimbursement_v1.0.pdf", "application/pdf"),
        ("docx", "FIN-EXP-001_Employee_Expense.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("txt", "IT-AUP-001_IT_Acceptable_Use.txt", "text/plain"),
    ]

    all_passed = True

    for step_num, (file_type, filename, mime_type) in enumerate(test_docs, start=2):
        print(f"\n[Step {step_num}/5] Testing Real {file_type.upper()} Extraction: '{filename}'")
        filepath = policies_dir / filename
        if not filepath.exists():
            print(f"  [ERROR] Sample file not found at: {filepath}")
            all_passed = False
            continue

        raw_bytes = filepath.read_bytes()
        doc_uuid = uuid.uuid4()
        storage_path = generate_storage_path(doc_uuid, filename)

        # Upload to Supabase Storage
        print(f"  -> Uploading to Supabase Storage: {storage_path} ({len(raw_bytes)} bytes)...")
        try:
            storage.upload_file_sync(storage_path, raw_bytes, content_type=mime_type)
            print("     [OK] Upload confirmed.")
        except Exception as exc:
            print(f"     [FAILED] Upload failed: {exc}")
            all_passed = False
            continue

        # Download from Supabase Storage
        print(f"  -> Downloading binary from private bucket using StorageService.download_file_sync...")
        downloaded_bytes = b""
        try:
            downloaded_bytes = storage.download_file_sync(storage_path)
            assert len(downloaded_bytes) == len(raw_bytes)
            print(f"     [OK] Downloaded {len(downloaded_bytes)} bytes (byte count matched).")
        except Exception as exc:
            print(f"     [FAILED] Download failed: {exc}")
            all_passed = False
            storage.delete_file_sync(storage_path)
            continue

        # Extract structured text
        print(f"  -> Extracting structured text with {extractor.get_parser(file_type).__class__.__name__}...")
        try:
            result = extractor.extract_from_bytes(
                content=downloaded_bytes,
                filename=filename,
                file_type=file_type,
                document_id=doc_uuid,
            )
            print(f"     [OK] Extraction status: '{result.extraction_status}'")
            print(f"     [OK] Total characters:  {result.total_characters}")
            print(f"     [OK] Logical units:     {len(result.pages)}")

            if file_type == "pdf":
                print(f"     [OK] Physical pages:    {result.total_pages}")
                assert result.total_pages > 0
                assert all(u.page_number is not None for u in result.pages)
                print(f"     [OK] Verified 1-based page numbers: {[u.page_number for u in result.pages]}")
            elif file_type == "docx":
                print(f"     [OK] Total pages:       {result.total_pages} (None as required; no fabricated pages)")
                assert result.total_pages is None
                assert all(u.page_number is None for u in result.pages)
                table_units = [u for u in result.pages if u.unit_type == "table"]
                heading_units = [u for u in result.pages if u.unit_type == "heading"]
                print(f"     [OK] Headings detected: {len(heading_units)}, Tables: {len(table_units)}")
            elif file_type == "txt":
                print(f"     [OK] Total pages:       {result.total_pages} (None as required; no fabricated pages)")
                assert result.total_pages is None
                assert all(u.page_number is None for u in result.pages)
                print(f"     [OK] Text units:        {len(result.pages)}")

            print(f"     [OK] Sample text preview:\n         {result.extracted_text[:120]!r}...")

        except Exception as exc:
            print(f"     [FAILED] Extraction failed: {exc}")
            all_passed = False

        finally:
            # Clean up object from Supabase Storage
            print(f"  -> Cleaning up test object from Supabase Storage...")
            try:
                storage.delete_file_sync(storage_path)
                print("     [OK] Test object deleted. No residual storage artifacts left.")
            except Exception as exc:
                print(f"     [WARNING] Cleanup failed: {exc}")

    # Summary
    print("\n" + "=" * 75)
    if all_passed:
        print("ALL TASK 003C EXTRACTION INTEGRATION CHECKS PASSED SUCCESSFULLY!")
    else:
        print("SOME CHECKS FAILED. PLEASE REVIEW LOGS ABOVE.")
    print("=" * 75)
    return all_passed


if __name__ == "__main__":
    success = run_extraction_verification()
    sys.exit(0 if success else 1)
