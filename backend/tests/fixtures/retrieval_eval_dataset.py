"""
Retrieval Quality Evaluation Dataset & Synthetic Policy Chunks.
Task 04F — KnowBridge AI Enterprise RAG Knowledge Platform.

Derived directly from Northstar Technologies India Pvt. Ltd. synthetic policies:
- HR-TRV-001 (Travel Policy v1.0 and v2.0)
- HR-LVE-001 (Leave Policy v1.0 and v2.0)
- HR-WFH-001 (Remote and Hybrid Work Policy v1.0 and v2.0)
- IT-SEC-001 (Information Security Policy v1.0)
- FIN-EXP-001 (Employee Expense Policy v1.0)
- HR-COC-001 (Code of Conduct v1.0)

Contains:
1. RetrievalTestCase dataclass defining ground truth for test queries.
2. 12 structured evaluation test cases covering all 9 required evaluation categories.
3. Realistic synthetic chunk database with verified provenance, versions, and validity dates.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any, List, Optional


@dataclass
class RetrievalTestCase:
    """
    Ground-truth test case for retrieval evaluation.
    """

    test_id: str
    query: str
    category: str
    expected_doc_title: Optional[str]
    expected_version: Optional[str]
    expected_section: Optional[str]
    target_date: Optional[date] = None
    category_filter: Optional[str] = None
    department_filter: Optional[str] = None
    is_current_only: Optional[bool] = None
    expected_relevant_keywords: List[str] = field(default_factory=list)
    is_answerable: bool = True
    description: str = ""


# ---------------------------------------------------------------------------
# Evaluation Dataset (12 Cases across 9 Categories)
# ---------------------------------------------------------------------------

EVALUATION_DATASET: List[RetrievalTestCase] = [
    # 1. Direct factual question (Travel v2.0)
    RetrievalTestCase(
        test_id="TC01_FACTUAL_TRAVEL_ADVANCE",
        query="What is the advance booking requirement for domestic flights?",
        category="factual",
        expected_doc_title="Business Travel and Reimbursement Policy",
        expected_version="2.0",
        expected_section="5.1 Advance Booking Requirements",
        expected_relevant_keywords=["domestic flights", "ten (10) calendar days", "Corporate Travel Desk"],
        is_answerable=True,
        description="Direct factual query on advance flight booking under current v2.0 policy.",
    ),
    # 2. Semantic question with different wording (Travel v2.0)
    RetrievalTestCase(
        test_id="TC02_SEMANTIC_TRAVEL_PER_DIEM",
        query="How much food allowance do software engineers get each day when visiting client sites in Bangalore or Mumbai?",
        category="semantic_paraphrase",
        expected_doc_title="Business Travel and Reimbursement Policy",
        expected_version="2.0",
        expected_section="7 Daily Per Diem and Meal Allowances",
        expected_relevant_keywords=["per diem", "Band L1 – L2", "Tier 1", "INR 1,800"],
        is_answerable=True,
        description="Paraphrased semantic query asking for food per diem for SEs in Tier 1 cities.",
    ),
    # 3. Current policy version retrieval (Leave v2.0)
    RetrievalTestCase(
        test_id="TC03_CURRENT_LEAVE_EL",
        query="What is the annual Earned Leave quota for permanent employees?",
        category="current_version",
        expected_doc_title="Employee Leave Policy",
        expected_version="2.0",
        expected_section="4 Leave Categories and Entitlements (v2.0)",
        expected_relevant_keywords=["Earned Leave (EL)", "20 working days"],
        is_answerable=True,
        description="Current policy query verifying retrieval of active v2.0 (20 days vs 18 in v1.0).",
    ),
    # 4. Historical policy version retrieval (Leave v1.0)
    RetrievalTestCase(
        test_id="TC04_HISTORICAL_LEAVE_2025",
        query="What was the annual Earned Leave quota for permanent employees in July 2025?",
        category="historical_version",
        expected_doc_title="Employee Leave Policy",
        expected_version="1.0",
        expected_section="4 Leave Categories and Entitlements (v1.0)",
        target_date=date(2025, 7, 15),
        expected_relevant_keywords=["Earned Leave (EL)", "18 working days"],
        is_answerable=True,
        description="Historical version retrieval targeting July 2025, when v1.0 was active.",
    ),
    # 5. Historical travel claim deadline (Travel v1.0)
    RetrievalTestCase(
        test_id="TC05_HISTORICAL_TRAVEL_DEADLINE",
        query="What was the expense claim submission deadline for business trips taken in October 2025?",
        category="historical_version",
        expected_doc_title="Business Travel and Reimbursement Policy",
        expected_version="1.0",
        expected_section="1 Document Control and Administration",
        target_date=date(2025, 10, 15),
        expected_relevant_keywords=["15 calendar days", "Version 1.0"],
        is_answerable=True,
        description="Historical travel query requiring v1.0 (15 days submission vs 30 days in v2.0).",
    ),
    # 6. Effective-date boundary: Sunset date of v1.0
    RetrievalTestCase(
        test_id="TC06_BOUNDARY_REMOTE_V1_SUNSET",
        query="How many mandatory days must employees work from the base office on March 31, 2026?",
        category="effective_date_boundary",
        expected_doc_title="Remote and Hybrid Work Policy",
        expected_version="1.0",
        expected_section="4 Office Attendance Expectations (v1.0)",
        target_date=date(2026, 3, 31),
        expected_relevant_keywords=["minimum of two (2) days per week"],
        is_answerable=True,
        description="Boundary test on final effective day of Remote v1.0 (2 days/week).",
    ),
    # 7. Effective-date boundary: Effective start date of v2.0
    RetrievalTestCase(
        test_id="TC07_BOUNDARY_REMOTE_V2_EFFECTIVE",
        query="How many mandatory days must employees work from the base office on April 1, 2026?",
        category="effective_date_boundary",
        expected_doc_title="Remote and Hybrid Work Policy",
        expected_version="2.0",
        expected_section="4 Office Attendance Expectations (v2.0)",
        target_date=date(2026, 4, 1),
        expected_relevant_keywords=["three (3) days per week", "Anchor Days"],
        is_answerable=True,
        description="Boundary test on first effective day of Remote v2.0 (3 days/week with Anchor Days).",
    ),
    # 8. Category & department filtering (IT Security)
    RetrievalTestCase(
        test_id="TC08_METADATA_FILTER_IT_PASSWORD",
        query="What are the password complexity requirements and expiration cycles?",
        category="metadata_filter",
        expected_doc_title="Information Security Policy",
        expected_version="1.0",
        expected_section="4.1 Password Complexity and Expiration",
        department_filter="IT",
        category_filter="Information Technology & Cyber Governance",
        expected_relevant_keywords=["fourteen (14) characters", "ninety (90) calendar days"],
        is_answerable=True,
        description="Metadata-filtered query restricted to IT department and Cyber Governance category.",
    ),
    # 9. Category & department filtering (Finance Expenses)
    RetrievalTestCase(
        test_id="TC09_METADATA_FILTER_FINANCE_SMARTPHONE",
        query="What is the maximum reimbursement for an executive smartphone handset?",
        category="metadata_filter",
        expected_doc_title="Employee Expense and Discretionary Spend Policy",
        expected_version="1.0",
        expected_section="4 Eligible Discretionary Expense Categories and Limits",
        department_filter="Finance",
        category_filter="Corporate Finance & Controllership",
        expected_relevant_keywords=["INR 30,000", "Band L5 and above"],
        is_answerable=True,
        description="Metadata-filtered query restricted to Finance department for smartphone entitlement.",
    ),
    # 10. Irrelevant / out-of-domain query
    RetrievalTestCase(
        test_id="TC10_IRRELEVANT_OUT_OF_DOMAIN",
        query="How do I bake authentic Italian sourdough pizza from scratch at home?",
        category="irrelevant",
        expected_doc_title=None,
        expected_version=None,
        expected_section=None,
        is_answerable=False,
        description="Out-of-domain recipe question completely unrelated to corporate enterprise policy.",
    ),
    # 11. Absent fact query (No pet policy exists in Northstar policies)
    RetrievalTestCase(
        test_id="TC11_ABSENT_PET_POLICY",
        query="Can employees bring pet dogs or golden retrievers to work at the Bengaluru campus?",
        category="absent_fact",
        expected_doc_title=None,
        expected_version=None,
        expected_section=None,
        is_answerable=False,
        description="Enterprise question whose fact is entirely absent from all corporate policies.",
    ),
    # 12. Citation and page provenance verification (Code of Conduct POSH)
    RetrievalTestCase(
        test_id="TC12_PROVENANCE_POSH_ICC",
        query="What is the email address and resolution timeframe for filing an Internal Complaints Committee report under POSH?",
        category="provenance",
        expected_doc_title="Corporate Code of Conduct and Workplace Ethics",
        expected_version="1.0",
        expected_section="4 Workplace Equality, Diversity, and Anti-Harassment",
        expected_relevant_keywords=["icc@northstar-tech.internal", "ninety (90) calendar days"],
        is_answerable=True,
        description="Provenance test checking page number, section, title, and citation tag for POSH report.",
    ),
]


# ---------------------------------------------------------------------------
# Synthetic Document Chunks Repository
# ---------------------------------------------------------------------------

DOC_IDS = {
    "travel": uuid.UUID("a0000000-0000-0000-0000-000000000001"),
    "leave": uuid.UUID("a0000000-0000-0000-0000-000000000002"),
    "remote": uuid.UUID("a0000000-0000-0000-0000-000000000003"),
    "security": uuid.UUID("a0000000-0000-0000-0000-000000000004"),
    "conduct": uuid.UUID("a0000000-0000-0000-0000-000000000005"),
    "expense": uuid.UUID("a0000000-0000-0000-0000-000000000006"),
}

VER_IDS = {
    "travel_v1": uuid.UUID("b0000000-0000-0000-0000-000000000001"),
    "travel_v2": uuid.UUID("b0000000-0000-0000-0000-000000000002"),
    "leave_v1": uuid.UUID("b0000000-0000-0000-0000-000000000003"),
    "leave_v2": uuid.UUID("b0000000-0000-0000-0000-000000000004"),
    "remote_v1": uuid.UUID("b0000000-0000-0000-0000-000000000005"),
    "remote_v2": uuid.UUID("b0000000-0000-0000-0000-000000000006"),
    "security_v1": uuid.UUID("b0000000-0000-0000-0000-000000000007"),
    "conduct_v1": uuid.UUID("b0000000-0000-0000-0000-000000000008"),
    "expense_v1": uuid.UUID("b0000000-0000-0000-0000-000000000009"),
}

SYNTHETIC_CHUNKS: List[dict[str, Any]] = [
    # 1. Travel v1.0 Section 5.1
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000001"),
        "document_id": DOC_IDS["travel"],
        "document_title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version_id": VER_IDS["travel_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": False,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2026, 3, 31),
        "effective_until": date(2026, 3, 31),
        "document_status": "completed",
        "page_number": 3,
        "section_title": "5.1 Advance Booking Requirements",
        "content": (
            "All domestic travel must be booked at least seven (7) calendar days in advance "
            "of the travel date through the Corporate Travel Desk (CTD). Emergency travel (<48 hours) "
            "requires written approval from Department Head. International travel requires 21 calendar days notice."
        ),
        "chunk_metadata": {"section_title": "5.1 Advance Booking Requirements"},
        "topic_keywords": ["advance booking", "domestic flights", "seven days", "flight", "booking notice"],
    },
    # 2. Travel v1.0 Section 1 (Claim deadline)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000002"),
        "document_id": DOC_IDS["travel"],
        "document_title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version_id": VER_IDS["travel_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": False,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2026, 3, 31),
        "effective_until": date(2026, 3, 31),
        "document_status": "completed",
        "page_number": 1,
        "section_title": "1 Document Control and Administration",
        "content": (
            "Status: SUPERSEDED. Version 1.0 governed business travel between 01 April 2025 and 31 March 2026. "
            "Expense claim submission deadline is strictly 15 calendar days from the completion of the business trip. "
            "Trips commencing prior to 01 April 2026 are governed by Version 1.0."
        ),
        "chunk_metadata": {"section_title": "1 Document Control and Administration"},
        "topic_keywords": ["expense claim", "submission deadline", "15 calendar days", "travel expense"],
    },
    # 3. Travel v2.0 Section 5.1 (Advance booking)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000003"),
        "document_id": DOC_IDS["travel"],
        "document_title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version_id": VER_IDS["travel_v2"],
        "version_number": "2.0",
        "version_label": "2.0",
        "is_current": True,
        "effective_date": date(2026, 4, 1),
        "effective_from": date(2026, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 3,
        "section_title": "5.1 Advance Booking Requirements",
        "content": (
            "Domestic flights must be booked at least ten (10) calendar days in advance via the "
            "Corporate Travel Desk (CTD) or the self-service travel portal. Emergency domestic travel "
            "(<48 hours) requires written approval from a Band L6+ Director. International travel requires 21 days."
        ),
        "chunk_metadata": {"section_title": "5.1 Advance Booking Requirements"},
        "topic_keywords": ["advance booking", "domestic flights", "ten days", "flight", "booking notice"],
    },
    # 4. Travel v2.0 Section 7 (Per Diem)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000004"),
        "document_id": DOC_IDS["travel"],
        "document_title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version_id": VER_IDS["travel_v2"],
        "version_number": "2.0",
        "version_label": "2.0",
        "is_current": True,
        "effective_date": date(2026, 4, 1),
        "effective_from": date(2026, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 4,
        "section_title": "7 Daily Per Diem and Meal Allowances",
        "content": (
            "A non-itemized daily per diem covers meals and transit incidentals: "
            "Band L1 – L2: INR 1,800 in Tier 1 cities (Bengaluru, Mumbai, Delhi-NCR, Hyderabad), "
            "INR 1,300 in Tier 2 cities, INR 1,000 in Tier 3 cities. Band L3-L4 receive INR 2,400 in Tier 1."
        ),
        "chunk_metadata": {"section_title": "7 Daily Per Diem and Meal Allowances"},
        "topic_keywords": ["per diem", "food allowance", "meal allowance", "Tier 1", "Band L1", "Bangalore", "Mumbai"],
    },
    # 5. Leave v1.0 Section 4 (Entitlements v1.0)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000005"),
        "document_id": DOC_IDS["leave"],
        "document_title": "Employee Leave Policy",
        "category": "Human Resources & Benefits",
        "department": "Human Resources",
        "version_id": VER_IDS["leave_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": False,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2026, 3, 31),
        "effective_until": date(2026, 3, 31),
        "document_status": "completed",
        "page_number": 2,
        "section_title": "4 Leave Categories and Entitlements (v1.0)",
        "content": (
            "Annual leave entitlements under Version 1.0: Earned Leave (EL): 18 working days accrued at 1.5 days/month. "
            "Maximum EL carry-forward cap is 30 days. Casual Leave (CL): 10 working days. Sick Leave (SL): 8 working days. "
            "Paternity Leave: 5 working days. Bereavement Leave: 3 working days."
        ),
        "chunk_metadata": {"section_title": "4 Leave Categories and Entitlements (v1.0)"},
        "topic_keywords": ["Earned Leave", "annual quota", "18 working days", "leave entitlement", "paternity"],
    },
    # 6. Leave v2.0 Section 4 (Entitlements v2.0)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000006"),
        "document_id": DOC_IDS["leave"],
        "document_title": "Employee Leave Policy",
        "category": "Human Resources & Benefits",
        "department": "Human Resources",
        "version_id": VER_IDS["leave_v2"],
        "version_number": "2.0",
        "version_label": "2.0",
        "is_current": True,
        "effective_date": date(2026, 4, 1),
        "effective_from": date(2026, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 2,
        "section_title": "4 Leave Categories and Entitlements (v2.0)",
        "content": (
            "Annual leave entitlements under Version 2.0: Earned Leave (EL): 20 working days accrued at 1.67 days/month. "
            "Maximum EL carry-forward cap is 45 days with annual voluntary encashment up to 10 days. "
            "Casual Leave: 8 days. Sick Leave: 12 days. Wellness Leave: 2 days. Paternity Leave: 10 working days."
        ),
        "chunk_metadata": {"section_title": "4 Leave Categories and Entitlements (v2.0)"},
        "topic_keywords": ["Earned Leave", "annual quota", "20 working days", "leave entitlement", "vacation"],
    },
    # 7. Remote v1.0 Section 4 (Attendance v1.0)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000007"),
        "document_id": DOC_IDS["remote"],
        "document_title": "Remote and Hybrid Work Policy",
        "category": "Human Resources & Workplace Operations",
        "department": "Human Resources",
        "version_id": VER_IDS["remote_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": False,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2026, 3, 31),
        "effective_until": date(2026, 3, 31),
        "document_status": "completed",
        "page_number": 2,
        "section_title": "4 Office Attendance Expectations (v1.0)",
        "content": (
            "Minimum Attendance Mandate: Employees must work from their registered Northstar base office for a "
            "minimum of two (2) days per week (or eight [8] days per calendar month). In-office days are determined "
            "flexibly by the employee in consultation with their immediate Line Manager."
        ),
        "chunk_metadata": {"section_title": "4 Office Attendance Expectations (v1.0)"},
        "topic_keywords": ["office attendance", "base office", "two days per week", "hybrid schedule", "in-office days"],
    },
    # 8. Remote v2.0 Section 4 (Attendance v2.0)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000008"),
        "document_id": DOC_IDS["remote"],
        "document_title": "Remote and Hybrid Work Policy",
        "category": "Human Resources & Workplace Operations",
        "department": "Human Resources",
        "version_id": VER_IDS["remote_v2"],
        "version_number": "2.0",
        "version_label": "2.0",
        "is_current": True,
        "effective_date": date(2026, 4, 1),
        "effective_from": date(2026, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 2,
        "section_title": "4 Office Attendance Expectations (v2.0)",
        "content": (
            "Minimum Attendance Mandate: Employees must work from their registered base office for a minimum of "
            "three (3) days per week (or twelve [12] days per month). Mandatory Anchor Days: Tuesday and Thursday "
            "are designated PAN-India corporate Anchor Days where campus attendance is compulsory."
        ),
        "chunk_metadata": {"section_title": "4 Office Attendance Expectations (v2.0)"},
        "topic_keywords": ["office attendance", "three days per week", "Anchor Days", "Tuesday and Thursday", "compulsory"],
    },
    # 9. Security v1.0 Section 4.1 (Password Complexity)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000009"),
        "document_id": DOC_IDS["security"],
        "document_title": "Information Security Policy",
        "category": "Information Technology & Cyber Governance",
        "department": "IT",
        "version_id": VER_IDS["security_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": True,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 3,
        "section_title": "4.1 Password Complexity and Expiration",
        "content": (
            "All user account passwords must contain a minimum of fourteen (14) characters, including at least "
            "one uppercase, one lowercase, one numeric digit, and one special character. Passwords expire "
            "automatically every ninety (90) calendar days. Password history remembers the last 12 passwords."
        ),
        "chunk_metadata": {"section_title": "4.1 Password Complexity and Expiration"},
        "topic_keywords": ["password complexity", "expiration", "fourteen characters", "ninety days", "special character"],
    },
    # 10. Finance Expense v1.0 Section 4 (Smartphone limit)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000010"),
        "document_id": DOC_IDS["expense"],
        "document_title": "Employee Expense and Discretionary Spend Policy",
        "category": "Corporate Finance & Controllership",
        "department": "Finance",
        "version_id": VER_IDS["expense_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": True,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 2,
        "section_title": "4 Eligible Discretionary Expense Categories and Limits",
        "content": (
            "Executive Smartphone Handset: Eligible for Band L5 and above, up to INR 30,000 once every 24 months. "
            "Team Engagement / Dinners: INR 1,200 per employee per quarter. Professional Certifications: "
            "Up to INR 50,000 per fiscal year."
        ),
        "chunk_metadata": {"section_title": "4 Eligible Discretionary Expense Categories and Limits"},
        "topic_keywords": ["smartphone handset", "reimbursement", "INR 30,000", "Band L5", "mobile handset"],
    },
    # 11. Code of Conduct v1.0 Section 4 (POSH ICC)
    {
        "chunk_id": uuid.UUID("c0000000-0000-0000-0000-000000000011"),
        "document_id": DOC_IDS["conduct"],
        "document_title": "Corporate Code of Conduct and Workplace Ethics",
        "category": "Human Resources & Legal Ethics",
        "department": "Human Resources",
        "version_id": VER_IDS["conduct_v1"],
        "version_number": "1.0",
        "version_label": "1.0",
        "is_current": True,
        "effective_date": date(2025, 4, 1),
        "effective_from": date(2025, 4, 1),
        "sunset_date": date(2027, 3, 31),
        "effective_until": date(2027, 3, 31),
        "document_status": "completed",
        "page_number": 4,
        "section_title": "4 Workplace Equality, Diversity, and Anti-Harassment",
        "content": (
            "Prevention of Sexual Harassment (POSH): Northstar maintains zero tolerance. Any aggrieved employee "
            "may file a confidential complaint directly with the Internal Complaints Committee (ICC) at "
            "icc@northstar-tech.internal. All formal inquiries are completed within ninety (90) calendar days."
        ),
        "chunk_metadata": {"section_title": "4 Workplace Equality, Diversity, and Anti-Harassment"},
        "topic_keywords": ["POSH", "Internal Complaints Committee", "ICC", "icc@northstar-tech.internal", "ninety days"],
    },
]
