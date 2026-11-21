# KnowBridge AI — Synthetic Enterprise Policy Dataset

> **SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY**  
> *This entire dataset is synthetic and was created exclusively for benchmarking, evaluating, and testing the KnowBridge AI enterprise Retrieval-Augmented Generation (RAG) platform. All entities, dates, financial amounts, procedures, and rules are entirely fictional.*

---

## 1. Company Profile

- **Legal Entity:** Northstar Technologies India Pvt. Ltd.
- **Corporate Headquarters:** Northstar Tech Park, Tower B, Floors 4–8, Outer Ring Road, Bellandur, Bengaluru, Karnataka 560103, India
- **Regional Development Centers:** Hyderabad, Pune, and Chennai
- **Workforce:** ~2,500 full-time employees
- **Industry Sector:** Enterprise IT and Software Services
- **Functional Departments:** Engineering, Human Resources, Finance, IT, Sales, and Workplace Operations
- **Operating Currency:** Indian Rupee (INR / ₹)
- **Corporate Language:** Professional Indian corporate English

---

## 2. Dataset Objective & RAG Benchmarking Scope

This synthetic dataset addresses critical challenges in enterprise knowledge management and RAG systems:

1. **Temporal & Version-Aware Retrieval:** Old superseded policies exist alongside current policies. RAG systems must retrieve the current policy by default or correctly answer historical questions based on trip or leave occurrence dates.
2. **Conflicting Policy & Evidence Detection:** Changes between versions (e.g., 15-day vs. 30-day claim submission deadlines) test whether the RAG orchestrator detects contradictions or hallucinates hybrid rules.
3. **Multi-Format Ingestion:** Tests document parsers across PDF (layout-aware, tables, headers, footers), DOCX (hierarchical styles, tables, callouts), and TXT (unstructured, clean text headers).
4. **Exact Numerical & Threshold Retrieval:** Tests extraction of specific currency limits (e.g., hotel caps, per diems, car mileage rates, certification caps).
5. **Workflow & Approval Matrix Reasoning:** Tests multi-step decision logic (e.g., whether an expense requires Line Manager, Director, or CFO authorization).
6. **Safe Abstention & Boundary Verification:** Tests whether the model safely abstains and defers to escalation contacts when a specific query falls outside documented policy provisions.

---

## 3. Dataset Inventory (13 Policy Documents)

```
synthetic-data/
    policies/
        ├── HR-TRV-001_Travel_Reimbursement_v1.0.pdf  (PDF, Superseded)
        ├── HR-TRV-001_Travel_Reimbursement_v2.0.pdf  (PDF, Current)
        ├── HR-LVE-001_Employee_Leave_v1.0.pdf        (PDF, Superseded)
        ├── HR-LVE-001_Employee_Leave_v2.0.pdf        (PDF, Current)
        ├── HR-WFH-001_Remote_Hybrid_Work_v1.0.pdf    (PDF, Superseded)
        ├── HR-WFH-001_Remote_Hybrid_Work_v2.0.pdf    (PDF, Current)
        ├── IT-SEC-001_Information_Security.pdf       (PDF, Current)
        ├── HR-COC-001_Code_of_Conduct.pdf            (PDF, Current)
        ├── FIN-EXP-001_Employee_Expense.docx         (DOCX, Current)
        ├── HR-ONB-001_Employee_Onboarding.docx       (DOCX, Current)
        ├── FIN-PROC-001_Procurement_Vendor.docx      (DOCX, Current)
        ├── HR-PER-001_Performance_Appraisal.txt      (TXT, Current)
        └── IT-AUP-001_IT_Acceptable_Use.txt          (TXT, Current)
    metadata/
        └── manifest.csv                              (Metadata Catalog)
    └── README.md                                     (Dataset Guide)
```

### Document Matrix

| Policy ID | Title | Format | Version | Status | Effective Date | Expiry / Review | Department |
|---|---|---|---|---|---|---|---|
| `HR-TRV-001` | Travel and Reimbursement | PDF | 1.0 | SUPERSEDED | 01-Apr-2025 | 31-Mar-2026 | Human Resources |
| `HR-TRV-001` | Travel and Reimbursement | PDF | 2.0 | CURRENT | 01-Apr-2026 | 31-Mar-2027 | Human Resources |
| `HR-LVE-001` | Employee Leave Policy | PDF | 1.0 | SUPERSEDED | 01-Apr-2025 | 31-Mar-2026 | Human Resources |
| `HR-LVE-001` | Employee Leave Policy | PDF | 2.0 | CURRENT | 01-Apr-2026 | 31-Mar-2027 | Human Resources |
| `HR-WFH-001` | Remote and Hybrid Work | PDF | 1.0 | SUPERSEDED | 01-Apr-2025 | 31-Mar-2026 | Human Resources |
| `HR-WFH-001` | Remote and Hybrid Work | PDF | 2.0 | CURRENT | 01-Apr-2026 | 31-Mar-2027 | Human Resources |
| `IT-SEC-001` | Information Security | PDF | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | IT |
| `HR-COC-001` | Code of Conduct | PDF | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | Human Resources |
| `FIN-EXP-001` | Employee Expense Policy | DOCX | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | Finance |
| `HR-ONB-001` | Employee Onboarding | DOCX | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | Human Resources |
| `FIN-PROC-001` | Procurement and Vendor | DOCX | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | Finance |
| `HR-PER-001` | Performance Appraisal | TXT | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | Human Resources |
| `IT-AUP-001` | IT Acceptable Use | TXT | 1.0 | CURRENT | 01-Apr-2025 | 31-Mar-2027 | IT |

---

## 4. Controlled Version Differences for Temporal & Conflict Testing

The dataset deliberately includes three dual-version policies to test temporal reasoning and conflicting evidence handling:

### 4.1 Travel and Reimbursement (`HR-TRV-001`)
- **Claim Submission Deadline:**
  - *Version 1.0:* Must be submitted within **15 calendar days** after trip completion.
  - *Version 2.0:* Must be submitted within **30 calendar days** after trip completion.
- **Version Applicability Rule:** Trips commencing **before 01 April 2026** follow v1.0. Trips commencing **on or after 01 April 2026** follow v2.0.
- **Hotel Caps (Tier 1, Band L3–L4):** v1.0 = INR 5,500/night vs. v2.0 = INR 7,500/night.
- **Car Mileage Reimbursement:** v1.0 = INR 10.00/km vs. v2.0 = INR 12.00/km (requires FASTag statement).
- **Travel Cash Advance Limit:** v1.0 = INR 50,000 vs. v2.0 = INR 75,000.

### 4.2 Employee Leave (`HR-LVE-001`)
- **Annual / Earned Leave (EL):**
  - *Version 1.0:* 18 days/year; max carry-forward 30 days; encashment permitted only at separation.
  - *Version 2.0:* 20 days/year; max carry-forward 45 days; annual voluntary encashment up to 10 days in November.
- **Sick Leave & Medical Certificate:**
  - *Version 1.0:* 8 days/year; medical certificate required for > 3 consecutive days.
  - *Version 2.0:* 12 days/year; medical certificate required for > 2 consecutive days.
- **Paternity Leave:** v1.0 = 5 working days vs. v2.0 = 10 working days.
- **New Category in v2.0:** Wellness / Mental Health Leave (2 days/year, non-cumulative).

### 4.3 Remote and Hybrid Work (`HR-WFH-001`)
- **Office Attendance:**
  - *Version 1.0:* Minimum 2 days/week (8 days/month); flexible schedule chosen with manager.
  - *Version 2.0:* Minimum 3 days/week (12 days/month); Tuesday and Thursday are mandatory corporate Anchor Days.
- **Home Equipment Setup:**
  - *Version 1.0:* One-time reimbursement up to INR 15,000 against submitted furniture/monitor invoices.
  - *Version 2.0:* Direct corporate hardware dispatch (dual monitors, docking station, keyboard/mouse); cash reimbursement discontinued.
- **Broadband Allowance:**
  - *Version 1.0:* INR 1,000/month against uploaded monthly ISP bills.
  - *Version 2.0:* INR 1,500/month disbursed automatically via payroll without bill upload.
- **Domestic Work from Anywhere:** v1.0 = 15 calendar days vs. v2.0 = 30 calendar days per fiscal year.

---

## 5. File Format Distribution

- **PDF Files (8 files):** Built with ReportLab 5.1.0 using a two-pass `NumberedCanvas` ('Page X of Y'), corporate headers/footers, metadata tables, section headers, and disclaimer banners.
- **DOCX Files (3 files):** Built with `python-docx` 1.2.0 featuring custom corporate styles, shaded table headers, callout boxes, and structured section numbering.
- **TXT Files (2 files):** Built as UTF-8 plain text with ASCII borders, hierarchical numbering (1.0, 1.1), text-based tabular columns, and clean FAQ blocks.

---

## 6. How to Use for RAG Evaluation

| Evaluation Angle | Example Query | Expected RAG Behavior |
|---|---|---|
| **Current vs. Superseded** | "What is the claim submission deadline for business travel?" | Retrieves v2.0 (30 days); clarifies v1.0 was 15 days for trips before 01-Apr-2026. |
| **Historical Temporal Query** | "I took a business trip on 10 March 2026. How many days do I have to submit my claim?" | Recognizes trip commenced before 01 April 2026; applies v1.0 deadline of 15 days. |
| **Threshold Extraction** | "What is the hotel allowance for a Senior Engineer in Mumbai?" | Surfaces Tier 1 cap (INR 7,500/night in v2.0, INR 5,500 in v1.0) with Band L3–L4 citation. |
| **Cross-Policy Reasoning** | "Can I combine earned leave with a business trip to Goa?" | Cross-references `HR-TRV-001` (personal extensions non-reimbursable) and `HR-LVE-001` (prior EL approval). |
| **Safe Abstention** | "Does Northstar reimburse pet sitting while on business travel?" | Policy does not define pet care; system must abstain safely and cite Travel Desk escalation. |

---

## 7. Synthetic Data Disclaimer

All company names, employee titles, email domains (`@northstar-tech.internal`), phone numbers, addresses, and monetary caps in this repository are purely synthetic and designed for software benchmarking. They do not reflect actual employment policies of any legal corporation.
