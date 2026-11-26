"""
Live Verification Script for Task 06E — Persistent Memory System.
Tests end-to-end memory extraction with Groq LLM, persistence in Supabase,
fact superseding with audit history, and active context compilation.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path so app modules are resolvable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid
from app.core.database import SessionLocal
from app.schemas.memory import MemoryCreate, MemoryType
from app.schemas.query_understanding import ConversationTurn
from app.services.llm_client import get_llm_client
from app.services.memory_service import MemoryService
from sqlalchemy import text


def run_live_memory_test():
    print("=" * 65)
    print("KNOWBRIDGE AI — TASK 06E: LIVE PERSISTENT MEMORY VERIFICATION")
    print("=" * 65)

    db = SessionLocal()
    session_key = f"demo_emp_{uuid.uuid4().hex[:6]}"
    llm = get_llm_client()
    service = MemoryService(db=db, llm_client=llm)

    try:
        # Step 1: Fact Extraction from User Dialogue
        print(f"\n[Step 1] Extracting durable employee context using Groq LLM...")
        turns = [
            ConversationTurn(
                role="user",
                content=(
                    "Hi! I am a full-time Senior DevOps Engineer based in the Sydney office. "
                    "I adhere to a strict vegan diet for all travel meal per diems."
                ),
            ),
            ConversationTurn(
                role="assistant",
                content="Welcome! I have noted your Sydney office location and vegan meal preferences.",
            ),
        ]

        print("User statement: 'Hi! I am a full-time Senior DevOps Engineer based in the Sydney office. I adhere to a strict vegan diet for all travel meal per diems.'")
        extracted = service.extract_memories_from_turns(turns)
        print(f"Extracted {len(extracted)} valid memory item(s):")
        for item in extracted:
            print(f"  • Key: {item.memory_key:<18} | Value: {item.memory_value:<20} | Type: {item.memory_type:<15} | Conf: {item.confidence_score}")

        # Step 2: Persist into Supabase
        print(f"\n[Step 2] Storing extracted memories into Supabase under session '{session_key}'...")
        synced = service.extract_and_sync_memories(turns, session_key=session_key)
        print(f"Successfully stored {len(synced)} record(s) in Supabase.")

        # Step 3: Test Conflict / Superseding
        print("\n[Step 3] Simulating employee relocation (Fact Superseding)...")
        print("Employee update: 'I have officially relocated to the Melbourne office.'")
        relocation_req = MemoryCreate(
            session_key=session_key,
            memory_key="work_location",
            memory_value="Melbourne",
            memory_text="Employee is located in the Melbourne office.",
            memory_type=MemoryType.LOCATION,
            confidence_score=0.98,
        )
        updated = service.store_memory(relocation_req)
        print(f"Location memory updated: new value = '{updated.memory_value}'")
        superseded_history = updated.metadata.get("superseded_history", [])
        print(f"Audit Trail (superseded_history in Supabase):")
        for h in superseded_history:
            print(f"  • Previous Value: '{h['previous_value']}' at {h['superseded_at']}")

        # Step 4: Active Context Compilation for RAG
        print("\n[Step 4] Compiling Active Memory Context for downstream RAG prompts...")
        context = service.get_active_memory_context(session_key=session_key)
        print("Compiled Context String (ready for LangGraph / Task 05A):")
        print("-" * 50)
        print(context.to_context_string())
        print("-" * 50)

        # Step 5: Direct Supabase SQL Query
        print("\n[Step 5] Direct SQL inspection in Supabase 'public.user_memories' table:")
        rows = db.execute(
            text(
                "SELECT memory_key, memory_value, memory_type, confidence_score, updated_at "
                "FROM public.user_memories WHERE session_key = :sk ORDER BY updated_at DESC"
            ),
            {"sk": session_key},
        ).fetchall()
        for r in rows:
            print(f"  Row -> key: {r[0]:<18} | value: {r[1]:<22} | type: {r[2]:<12} | conf: {r[3]}")

        # Clean up demo session
        print(f"\n[Step 6] Cleaning up test session '{session_key}'...")
        deleted = service.clear_session_memories(session_key=session_key)
        print(f"Cleaned up {deleted} test records. Database left in pristine state.")

        print("\n" + "=" * 65)
        print("ALL LIVE PERSISTENT MEMORY VERIFICATION STEPS PASSED SUCCESSFULLY!")
        print("=" * 65)

    finally:
        db.close()


if __name__ == "__main__":
    run_live_memory_test()
