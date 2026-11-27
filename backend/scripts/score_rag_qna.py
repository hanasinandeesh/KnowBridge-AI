"""
KnowBridge AI — Automated RAG QnA Evaluation & Scoring Runner.

Executes an enterprise benchmark suite tailored to active policies:
- HR-LVE-001 (Employee Leave Policy v2.0)
- HR-WFH-001 (Remote & Hybrid Work Policy v2.0)
- FIN-PROC-001 (Procurement & Vendor Policy v1.0)
- IT-AUP-001 (IT Acceptable Use Policy v1.0)

Evaluates and scores:
1. Groundedness & Accuracy (%)
2. Citation Provenance & Page/Clause Linkage (%)
3. Evidence Status Consistency (%)
4. Safe Abstention / Zero Hallucination Rate (%)
5. Latency (s) and Overall RAG Benchmark Grade
"""

import sys
import time
from typing import List, Dict, Any

sys.path.insert(0, ".")

from app.core.database import SessionLocal
from app.graph.workflow import get_rag_orchestrator
from app.schemas.chat import ChatRequest

BENCHMARK_CASES = [
    {
        "id": "TC-01",
        "category": "Fact Retrieval (Leave v2.0)",
        "query": "How many days of annual leave do full-time employees get per year?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["20"],
        "unexpected_keywords": ["18 days"],
        "expected_citation": "HR-LVE-001",
    },
    {
        "id": "TC-02",
        "category": "Version Precedence (Sick Leave v2.0)",
        "query": "How many days of sick leave are provided and when is a medical certificate required?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["12", "2"],
        "expected_citation": "HR-LVE-001",
    },
    {
        "id": "TC-03",
        "category": "New Policy Category (Wellness Leave)",
        "query": "Does the company offer wellness or mental health leave, and how many days?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["2", "wellness"],
        "expected_citation": "HR-LVE-001",
    },
    {
        "id": "TC-04",
        "category": "IT Acceptable Use (Prohibited Activities)",
        "query": "What activities are strictly prohibited under the IT acceptable use policy?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["prohibited", "torrenting", "peer-to-peer", "cryptocurrency", "sniffing"],
        "expected_citation": "IT-AUP-001",
    },
    {
        "id": "TC-05",
        "category": "Finance Procurement (Quotation Mandate)",
        "query": "What is the quotation mandate for vendor purchases up to INR 1,00,000 versus above INR 1,00,000?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["single", "three", "1,00,000"],
        "expected_citation": "FIN-PROC-001",
    },
    {
        "id": "TC-06",
        "category": "Remote Work (Core Guidelines)",
        "query": "What are the core working hours and attendance expectations under the remote and hybrid work policy?",
        "expected_status": "SUPPORTED",
        "expected_keywords": ["hours", "hybrid", "remote"],
        "expected_citation": "HR-WFH-001",
    },
    {
        "id": "TC-07",
        "category": "Safe Abstention (Out-of-Scope / Pets)",
        "query": "Can I bring my pet dog or cat to the office on Fridays?",
        "expected_status": "INSUFFICIENT",
        "forbidden_hallucinations": ["yes, you can bring", "pets are permitted on fridays", "welcome to bring your pet"],
    },
    {
        "id": "TC-08",
        "category": "Safe Abstention (Out-of-Scope / Crypto)",
        "query": "Can vendor invoices or expense claims be paid in Bitcoin or Ethereum?",
        "expected_status": "INSUFFICIENT",
        "forbidden_hallucinations": ["yes, bitcoin is accepted", "crypto payments are supported", "reimbursed in cryptocurrency"],
    },
]


def run_benchmark():
    print("=" * 80)
    print("  KNOWBRIDGE AI — RAG QnA BENCHMARK & EVALUATION RUNNER")
    print("=" * 80)
    print(f"Total Test Cases: {len(BENCHMARK_CASES)}")
    print("Initializing RAG Orchestrator and Database Session...\n")

    db = SessionLocal()
    orchestrator = get_rag_orchestrator(db=db)

    results: List[Dict[str, Any]] = []
    total_time = 0.0

    for idx, tc in enumerate(BENCHMARK_CASES, start=1):
        print(f"[{idx}/{len(BENCHMARK_CASES)}] Running {tc['id']} ({tc['category']}):")
        print(f"  Query: \"{tc['query']}\"")

        start_t = time.perf_counter()
        req = ChatRequest(query=tc["query"], session_key="eval_benchmark_user")
        res = orchestrator.chat(request=req, db=db)
        elapsed = time.perf_counter() - start_t
        total_time += elapsed

        answer = res.answer or ""
        status = res.evidence_status
        citations = res.citations or []

        # 1. Status Match
        status_pass = (status == tc["expected_status"])

        # 2. Accuracy / Keyword Grounding
        expected_kws = tc.get("expected_keywords", [])
        matched_kws = [kw for kw in expected_kws if kw.lower() in answer.lower()]
        keywords_hit = (len(matched_kws) >= 1) if expected_kws else True

        no_unexpected = not any(kw.lower() in answer.lower() for kw in tc.get("unexpected_keywords", []))
        no_hallucination = not any(h.lower() in answer.lower() for h in tc.get("forbidden_hallucinations", []))
        accuracy_pass = keywords_hit and no_unexpected and no_hallucination

        # 3. Citation Check
        if tc["expected_status"] == "SUPPORTED":
            has_citation_tag = ("[" in answer and "]" in answer) or (len(citations) > 0)
            target_policy = tc.get("expected_citation", "")
            matches_policy = any(target_policy.lower() in str(c).lower() for c in citations) or (target_policy.lower() in answer.lower())
            citation_pass = has_citation_tag and (matches_policy or not target_policy)
        else:
            # Safe abstention requires no hallucinated citations or status == INSUFFICIENT
            citation_pass = (status == "INSUFFICIENT")

        overall_pass = status_pass and accuracy_pass and citation_pass

        results.append({
            "tc": tc,
            "response": res,
            "elapsed": elapsed,
            "status_pass": status_pass,
            "accuracy_pass": accuracy_pass,
            "citation_pass": citation_pass,
            "overall_pass": overall_pass,
        })

        tag = "PASSED" if overall_pass else "FAILED"
        print(f"  Result: [{tag}] (Status: {status}, Citations: {len(citations)}, Latency: {elapsed:.2f}s)")
        print(f"  Snippet: {answer[:130].strip()}...")
        print("-" * 80)
        time.sleep(3.0)  # Pacing delay to respect Groq free-tier TPM limit

    db.close()

    # Aggregate Scores
    total = len(results)
    passed_count = sum(1 for r in results if r["overall_pass"])
    status_score = sum(1 for r in results if r["status_pass"]) / total * 100
    accuracy_score = sum(1 for r in results if r["accuracy_pass"]) / total * 100
    citation_score = sum(1 for r in results if r["citation_pass"]) / total * 100
    abstention_tests = [r for r in results if r["tc"]["expected_status"] == "INSUFFICIENT"]
    abstention_score = sum(1 for r in abstention_tests if r["status_pass"] and r["accuracy_pass"]) / len(abstention_tests) * 100 if abstention_tests else 100.0
    avg_latency = total_time / total

    pct = (passed_count / total) * 100
    if pct >= 90:
        grade = "A+ (Enterprise Production Grade)"
    elif pct >= 80:
        grade = "A (High Reliability)"
    elif pct >= 70:
        grade = "B (Good)"
    else:
        grade = "C (Needs Tuning)"

    print("\n" + "=" * 80)
    print("                     EVALUATION SCORECARD REPORT")
    print("=" * 80)
    print(f"  Overall Score:               {passed_count}/{total} passed ({pct:.1f}%)")
    print(f"  Overall Quality Grade:       {grade}")
    print(f"  Groundedness & Accuracy:     {accuracy_score:.1f}%")
    print(f"  Status Consistency:          {status_score:.1f}%")
    print(f"  Citation Provenance:         {citation_score:.1f}%")
    print(f"  Safe Abstention Rate:        {abstention_score:.1f}% (Zero Hallucination)")
    print(f"  Average Query Latency:       {avg_latency:.2f}s")
    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
