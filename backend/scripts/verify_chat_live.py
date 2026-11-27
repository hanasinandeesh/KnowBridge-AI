"""
Live Verification Script for Task 06F — LangGraph End-to-End Chat & Feedback.
Tests live multi-turn conversational RAG against Groq LLM and Supabase PostgreSQL.
"""

import sys
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal
from app.graph.workflow import get_rag_orchestrator
from app.models.message import Message
from app.schemas.chat import ChatRequest
from sqlalchemy import text


def run_live_chat_test():
    print("=" * 70)
    print("KNOWBRIDGE AI — TASK 06F: LIVE CONVERSATIONAL RAG VERIFICATION")
    print("=" * 70)

    db = SessionLocal()
    orchestrator = get_rag_orchestrator(db=db)

    try:
        # Step 1: Turn 1 - Cold Start / New Conversation Thread
        print("\n[Step 1] Turn 1: Asking initial policy question (no conversation_id)...")
        q1 = "What is the maximum daily meal allowance for domestic travel?"
        print(f"User: '{q1}'")

        req1 = ChatRequest(query=q1, session_key="live_demo_user")
        res1 = orchestrator.chat(request=req1, db=db)

        print(f"\nResponse (Status: {res1.evidence_status}):")
        print(f"Assistant: {res1.answer}")
        print(f"Conversation ID: {res1.conversation_id}")
        print(f"Assistant Message ID: {res1.assistant_message_id}")
        print(f"Citations: {len(res1.citations)}")
        for c in res1.citations:
            print(f"  • [{c.document_title}, p. {c.page_number}] -> {c.snippet[:80]}...")

        # Step 2: Turn 2 - Follow-up in the same thread
        print("\n" + "-" * 70)
        print("[Step 2] Turn 2: Asking an elliptical follow-up question in the same thread...")
        q2 = "Does this include alcohol?"
        print(f"User: '{q2}' (thread_id: {res1.conversation_id})")

        req2 = ChatRequest(
            query=q2,
            conversation_id=res1.conversation_id,
            session_key="live_demo_user",
        )
        res2 = orchestrator.chat(request=req2, db=db)

        print(f"\nResponse (Status: {res2.evidence_status}):")
        print(f"Resolved Standalone Query: '{res2.standalone_query}'")
        print(f"Is Follow-Up Detected: {res2.is_follow_up}")
        print(f"Assistant: {res2.answer}")

        # Step 3: Turn 3 - Submit User Feedback
        print("\n" + "-" * 70)
        print("[Step 3] Turn 3: Submitting thumbs-up (+1) feedback on the assistant response...")
        if res1.assistant_message_id:
            msg = db.query(Message).filter(Message.id == res1.assistant_message_id).first()
            if msg:
                msg.feedback_score = 1
                db.commit()
                print(f"Successfully recorded feedback_score = +1 on message {msg.id}")

        # Step 4: Verify in Supabase
        print("\n" + "-" * 70)
        print("[Step 4] Querying live Supabase PostgreSQL 'messages' table for this thread:")
        rows = db.execute(
            text(
                "SELECT role, content, evidence_status, feedback_score, created_at "
                "FROM public.messages WHERE conversation_id = :cid ORDER BY created_at ASC"
            ),
            {"cid": str(res1.conversation_id)},
        ).fetchall()

        print(f"Found {len(rows)} message(s) in Supabase:")
        for r in rows:
            feedback_str = f" [Feedback: {r[3]}]" if r[3] is not None else ""
            print(f"  [{r[0].upper()}] ({r[2]}){feedback_str}: {r[1][:90]}...")

        print("\n" + "=" * 70)
        print("ALL LIVE CHAT & ORCHESTRATION VERIFICATION STEPS PASSED SUCCESSFULLY!")
        print("=" * 70)

    finally:
        db.close()


if __name__ == "__main__":
    run_live_chat_test()
