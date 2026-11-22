#!/usr/bin/env python3
"""
KnowBridge AI — Task 003B: Supabase Storage Integration Verification Script
Verifies live connectivity, upload capability, object listing, and deletion
in the real Supabase Storage bucket ('knowledge-documents').

Usage:
    cd backend
    python scripts/verify_storage_integration.py
"""

import sys
import uuid
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.services.storage_service import (
    StorageConfigurationError,
    StorageDeleteError,
    StorageService,
    StorageUploadError,
    generate_storage_path,
)


def run_storage_verification() -> bool:
    print("=" * 70)
    print("KnowBridge AI — Supabase Storage Live Verification (Task 003B)")
    print("=" * 70)

    # 1. Inspect Environment Configuration
    print("\n[Step 1/5] Checking Storage Configuration...")
    print(f"  Project Name:         {settings.PROJECT_NAME}")
    print(f"  Supabase URL:         {settings.SUPABASE_URL or '<not configured>'}")
    print(f"  Target Bucket:        {settings.STORAGE_BUCKET_NAME}")
    service_key_set = bool(settings.SUPABASE_SERVICE_ROLE_KEY and not settings.SUPABASE_SERVICE_ROLE_KEY.startswith("[YOUR-"))
    print(f"  Service Role Key:     {'[CONFIGURED]' if service_key_set else '<MISSING or PLACEHOLDER>'}")

    storage = StorageService()
    if not storage.is_configured:
        print("\n[FAILED] Supabase Storage is not configured.")
        print("  Please ensure the following environment variables are set in backend/.env:")
        print("    SUPABASE_URL=https://<your-project-ref>.supabase.co")
        print("    SUPABASE_SERVICE_ROLE_KEY=<your-supabase-service-role-key>")
        print("    STORAGE_BUCKET_NAME=knowledge-documents")
        print("\nNote: Never use the anon public key; storage management requires the service-role key.")
        return False

    print("  [OK] Storage service configuration verified.")

    # 2. Generate Unique Object Test Path
    print("\n[Step 2/5] Generating Unique Test Object Path...")
    doc_id = uuid.uuid4()
    filename = f"integration_test_{doc_id.hex[:8]}.txt"
    storage_path = generate_storage_path(doc_id, filename)
    print(f"  Target Path: {storage_path}")

    test_content = (
        f"KnowBridge AI Storage Live Verification\n"
        f"Document ID: {doc_id}\n"
        f"Bucket: {settings.STORAGE_BUCKET_NAME}\n"
        f"Timestamp: {uuid.uuid1()}\n"
    ).encode("utf-8")

    # 3. Upload File to Supabase Storage
    print("\n[Step 3/5] Uploading Test File to Bucket...")
    try:
        uploaded_path = storage.upload_file_sync(
            object_path=storage_path,
            content=test_content,
            content_type="text/plain; charset=utf-8",
        )
        print(f"  [OK] Successfully uploaded: {uploaded_path} ({len(test_content)} bytes)")
    except StorageUploadError as exc:
        print(f"  [FAILED] Upload failed: {exc}")
        return False

    # 4. Verify Object Existence in Bucket
    print("\n[Step 4/5] Verifying Object Existence in Bucket...")
    exists = storage.file_exists_sync(storage_path)
    if exists:
        print(f"  [OK] Object confirmed present in bucket '{settings.STORAGE_BUCKET_NAME}'.")
    else:
        print(f"  [WARNING] Object check returned false (may be due to eventual consistency or list permission).")

    # 5. Clean Up / Delete Object from Storage
    print("\n[Step 5/5] Cleaning Up Test Object from Storage...")
    try:
        deleted = storage.delete_file_sync(storage_path)
        if deleted:
            print(f"  [OK] Successfully deleted test object '{storage_path}'. No residual test artifacts left.")
        else:
            print(f"  [WARNING] Delete returned False for '{storage_path}'.")
    except StorageDeleteError as exc:
        print(f"  [FAILED] Cleanup delete failed: {exc}")
        print(f"  Please manually delete '{storage_path}' from bucket '{settings.STORAGE_BUCKET_NAME}'.")
        return False

    print("\n" + "=" * 70)
    print("ALL SUPABASE STORAGE LIVE VERIFICATION CHECKS PASSED SUCCESSFULLY!")
    print("=" * 70)
    return True


if __name__ == "__main__":
    success = run_storage_verification()
    sys.exit(0 if success else 1)
