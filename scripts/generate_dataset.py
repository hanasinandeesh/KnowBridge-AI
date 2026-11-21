"""
Master Orchestration Script for KnowBridge AI Synthetic Enterprise Policy Dataset.
Generates:
- 8 PDF policy files
- 3 DOCX policy files
- 2 TXT policy files
- 1 manifest.csv (in synthetic-data/metadata/)
- 1 comprehensive README.md (in synthetic-data/)

Performs automated validation and reports full generation metrics.
"""

import os
import sys
import csv
from pathlib import Path

# Add parent directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pdf_builder import build_pdf_document
from docx_builder import build_docx_document
from txt_builder import build_txt_document

from policies.travel import get_travel_v1, get_travel_v2
from policies.leave import get_leave_v1, get_leave_v2
from policies.remote import get_remote_v1, get_remote_v2
from policies.security import get_infosec_v1, get_acceptable_use_v1
from policies.conduct_onboard import (
    get_code_of_conduct_v1, get_onboarding_v1, get_performance_v1
)
from policies.finance import get_expense_v1, get_procurement_v1

# Target Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "synthetic-data"
POLICIES_DIR = OUTPUT_DIR / "policies"
METADATA_DIR = OUTPUT_DIR / "metadata"
MANIFEST_PATH = METADATA_DIR / "manifest.csv"
README_PATH = OUTPUT_DIR / "README.md"


def get_dataset_catalog():
    """Returns the master list of 13 document definitions and generator mappings."""
    return [
        {
            "filename": "HR-TRV-001_Travel_Reimbursement_v1.0.pdf",
            "format": "PDF",
            "data_getter": get_travel_v1,
            "department": "Human Resources"
        },
        {
            "filename": "HR-TRV-001_Travel_Reimbursement_v2.0.pdf",
            "format": "PDF",
            "data_getter": get_travel_v2,
            "department": "Human Resources"
        },
        {
            "filename": "HR-LVE-001_Employee_Leave_v1.0.pdf",
            "format": "PDF",
            "data_getter": get_leave_v1,
            "department": "Human Resources"
        },
        {
            "filename": "HR-LVE-001_Employee_Leave_v2.0.pdf",
            "format": "PDF",
            "data_getter": get_leave_v2,
            "department": "Human Resources"
        },
        {
            "filename": "HR-WFH-001_Remote_Hybrid_Work_v1.0.pdf",
            "format": "PDF",
            "data_getter": get_remote_v1,
            "department": "Human Resources"
        },
        {
            "filename": "HR-WFH-001_Remote_Hybrid_Work_v2.0.pdf",
            "format": "PDF",
            "data_getter": get_remote_v2,
            "department": "Human Resources"
        },
        {
            "filename": "IT-SEC-001_Information_Security.pdf",
            "format": "PDF",
            "data_getter": get_infosec_v1,
            "department": "IT"
        },
        {
            "filename": "HR-COC-001_Code_of_Conduct.pdf",
            "format": "PDF",
            "data_getter": get_code_of_conduct_v1,
            "department": "Human Resources"
        },
        {
            "filename": "FIN-EXP-001_Employee_Expense.docx",
            "format": "DOCX",
            "data_getter": get_expense_v1,
            "department": "Finance"
        },
        {
            "filename": "HR-ONB-001_Employee_Onboarding.docx",
            "format": "DOCX",
            "data_getter": get_onboarding_v1,
            "department": "Human Resources"
        },
        {
            "filename": "FIN-PROC-001_Procurement_Vendor.docx",
            "format": "DOCX",
            "data_getter": get_procurement_v1,
            "department": "Finance"
        },
        {
            "filename": "HR-PER-001_Performance_Appraisal.txt",
            "format": "TXT",
            "data_getter": get_performance_v1,
            "department": "Human Resources"
        },
        {
            "filename": "IT-AUP-001_IT_Acceptable_Use.txt",
            "format": "TXT",
            "data_getter": get_acceptable_use_v1,
            "department": "IT"
        },
    ]


def generate_manifest(manifest_rows):
    """Generates manifest.csv with the exact required schema."""
    fieldnames = [
        "filename",
        "policy_id",
        "title",
        "category",
        "department",
        "version",
        "effective_date",
        "expiry_date",
        "status",
        "file_type",
        "applicable_audience"
    ]
    with open(MANIFEST_PATH, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(row)
    print(f"[OK] Generated manifest.csv with {len(manifest_rows)} rows at {MANIFEST_PATH}")


def generate_readme():
    """Generates comprehensive documentation for the synthetic dataset."""
    readme_content = """# KnowBridge AI — Synthetic Enterprise Policy Dataset

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
"""
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(f"[OK] Generated README.md at {README_PATH}")


def validate_generated_files(catalog):
    """
    Validates that:
    1. Output directory contains exactly 13 files in policies/
    2. Exactly 8 PDFs, 3 DOCXs, 2 TXTs
    3. All files exist, are readable, and have non-zero size
    4. Manifest exists and has exactly 13 rows
    5. README.md exists and has non-zero size
    """
    print("\n" + "=" * 70)
    print("RUNNING AUTOMATED DATASET VALIDATION SUITE")
    print("=" * 70)

    policy_files = list(POLICIES_DIR.iterdir())
    print(f"Total files in policies/ directory: {len(policy_files)} (Expected: 13)")
    
    pdf_count = len([f for f in policy_files if f.suffix.lower() == ".pdf"])
    docx_count = len([f for f in policy_files if f.suffix.lower() == ".docx"])
    txt_count = len([f for f in policy_files if f.suffix.lower() == ".txt"])
    
    print(f"  - PDF files:  {pdf_count} (Expected: 8)")
    print(f"  - DOCX files: {docx_count} (Expected: 3)")
    print(f"  - TXT files:  {txt_count} (Expected: 2)")
    
    assert len(policy_files) == 13, f"Expected 13 files, found {len(policy_files)}"
    assert pdf_count == 8, f"Expected 8 PDFs, found {pdf_count}"
    assert docx_count == 3, f"Expected 3 DOCXs, found {docx_count}"
    assert txt_count == 2, f"Expected 2 TXTs, found {txt_count}"

    # Detailed file inspection
    validation_results = []
    for item in catalog:
        filepath = POLICIES_DIR / item["filename"]
        assert filepath.exists(), f"Missing file: {filepath}"
        size = filepath.stat().st_size
        assert size > 0, f"File {filepath} is empty (0 bytes)!"
        
        # Verify content readability
        if item["format"] == "PDF":
            # Check PDF header
            with open(filepath, "rb") as f:
                header = f.read(5)
                assert header == b"%PDF-", f"Invalid PDF header in {filepath}"
            validation_results.append((item["filename"], item["format"], f"{size / 1024:.1f} KB", "Valid PDF"))
            
        elif item["format"] == "DOCX":
            import docx
            doc = docx.Document(filepath)
            p_count = len(doc.paragraphs)
            t_count = len(doc.tables)
            assert p_count > 10, f"DOCX {filepath} has insufficient paragraphs ({p_count})"
            validation_results.append((item["filename"], item["format"], f"{size / 1024:.1f} KB", f"{p_count} paras, {t_count} tables"))
            
        elif item["format"] == "TXT":
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            assert len(lines) > 50, f"TXT {filepath} has insufficient lines ({len(lines)})"
            validation_results.append((item["filename"], item["format"], f"{size / 1024:.1f} KB", f"{len(lines)} lines"))

    # Validate manifest.csv
    assert MANIFEST_PATH.exists(), f"Missing manifest at {MANIFEST_PATH}"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        reader = list(csv.DictReader(f))
        assert len(reader) == 13, f"Expected 13 manifest rows, found {len(reader)}"
    print(f"[OK] Manifest validated: 13 rows with complete metadata fields.")

    # Validate README.md
    assert README_PATH.exists(), f"Missing README at {README_PATH}"
    readme_size = README_PATH.stat().st_size
    assert readme_size > 1000, f"README.md too small ({readme_size} bytes)"
    print(f"[OK] README.md validated: {readme_size} bytes.")

    print("\n" + "-" * 70)
    print("DETAILED FILE VALIDATION TABLE:")
    print("-" * 70)
    print(f"{'Filename':<42} {'Format':<6} {'Size':<10} {'Details'}")
    print("-" * 70)
    for fn, fmt, sz, details in validation_results:
        print(f"{fn:<42} {fmt:<6} {sz:<10} {details}")
    print("-" * 70)
    print("ALL VALIDATION CHECKS PASSED SUCCESSFULLY!\n")


def main():
    print("=" * 70)
    print("KNOWBRIDGE AI — SYNTHETIC ENTERPRISE POLICY DATASET GENERATOR")
    print("=" * 70)
    
    POLICIES_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    catalog = get_dataset_catalog()
    manifest_rows = []

    for item in catalog:
        filename = item["filename"]
        fmt = item["format"]
        data = item["data_getter"]()
        filepath = POLICIES_DIR / filename
        
        print(f"Generating [{fmt}] {filename}...")
        
        if fmt == "PDF":
            build_pdf_document(str(filepath), data)
        elif fmt == "DOCX":
            build_docx_document(str(filepath), data)
        elif fmt == "TXT":
            build_txt_document(str(filepath), data)
            
        manifest_rows.append({
            "filename": filename,
            "policy_id": data.get("id", ""),
            "title": data.get("title", ""),
            "category": data.get("category", ""),
            "department": item.get("department", "Human Resources"),
            "version": data.get("version", "1.0"),
            "effective_date": data.get("effective_date", "2025-04-01"),
            "expiry_date": data.get("expiry_date", "2027-03-31"),
            "status": data.get("status", "CURRENT"),
            "file_type": fmt,
            "applicable_audience": data.get("audience", "All Northstar Employees")
        })

    # Generate Manifest & README
    generate_manifest(manifest_rows)
    generate_readme()

    # Run Automated Validation
    validate_generated_files(catalog)


if __name__ == "__main__":
    main()
