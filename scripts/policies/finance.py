"""
Employee Expense Policy (FIN-EXP-001) and Procurement & Vendor Policy (FIN-PROC-001)
for Northstar Technologies India Pvt. Ltd.
"""

def get_expense_v1():
    return {
        "id": "FIN-EXP-001",
        "title": "Employee Expense and Discretionary Spend Policy",
        "category": "Corporate Finance & Controllership",
        "department": "Finance",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Head of Financial Planning & Analysis (FP&A)",
        "approver": "Chief Financial Officer (CFO)",
        "audience": "All employees incurring reimbursable business expenses or discretionary team budgets",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Introduction",
                "content": [
                    "This document defines the policies, monetary thresholds, eligibility criteria, and reimbursement workflows governing operational, discretionary, and non-travel business expenditures incurred by employees of Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. Effective 01 April 2025."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Core Fiduciary Principles",
                "content": [
                    "To establish transparent, auditable, and fiscally prudent guidelines for reimbursing legitimate business expenses incurred on behalf of Northstar, preventing financial irregularities while empowering teams with necessary operational resources."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Exclusions",
                "content": [
                    "Applies to all permanent full-time employees across Bengaluru, Hyderabad, Pune, and Chennai facilities.",
                    "Exclusions: Travel-related expenses (airfare, outstation lodging, per diem) are governed exclusively under HR-TRV-001. Capital asset procurements and vendor contracts are governed under FIN-PROC-001."
                ]
            },
            {
                "number": "4",
                "title": "Eligible Discretionary Expense Categories and Limits",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Expense Category", "Eligible Audience", "Monetary Limit (INR)", "Frequency / Conditions"],
                        "rows": [
                            ["Team Engagement / Dinners", "All Team Members", "INR 1,200 per employee", "Quarterly allotment; cannot be carried over across quarters"],
                            ["Professional Certifications", "Engineers & Consultants", "Up to INR 50,000 per fiscal year", "Pre-approval required; 12-month service bond if > INR 25,000"],
                            ["Executive Smartphone Handset", "Band L5 and above", "Up to INR 30,000", "Once every twenty-four (24) months"],
                            ["Mobile Voice & Data Plan", "Client-facing / On-call staff", "Up to INR 1,000 per month", "Against monthly GST telephone invoice"],
                            ["Client Entertainment Meals", "Band L6+ Directors & VPs", "Up to INR 5,000 per occasion", "Requires attendee names, client organization, and agenda"]
                        ],
                        "widths": [130, 110, 110, 154]
                    }
                ]
            },
            {
                "number": "5",
                "title": "Professional Certifications and Training Reimbursement",
                "content": [
                    "- Covered Certifications: Industry-recognized accreditations directly relevant to employee job responsibilities (e.g., AWS Certified Solutions Architect, Google Cloud Professional, Azure Solutions Architect, Kubernetes CKA, CISSP, PMP).",
                    "- Pre-Approval Mandate: Employees must secure prior written approval in the ERP from their Department Head (Band L6) before purchasing exam vouchers or course materials.",
                    "- Passing Requirement: Reimbursement is disbursed only upon submission of the official passing score certificate and original tax invoice.",
                    "- Service Commitment Agreement (Bond): Any certification reimbursement exceeding INR 25,000 requires the employee to execute a 12-month Service Commitment Agreement. If the employee voluntarily resigns within 12 months of reimbursement, the prorated amount is recovered from their final settlement."
                ]
            },
            {
                "number": "6",
                "title": "Ineligible and Non-Reimbursable Expenses",
                "content": [
                    "The following expenditures are strictly personal liabilities and will be rejected by Finance Audit:",
                    "- Traffic violation fines, parking penalties, speeding tickets, or towing charges.",
                    "- Alcoholic beverages (unless explicitly part of a pre-approved Band L6+ client entertainment dinner).",
                    "- Personal grooming, haircuts, clothing, luggage, or personal electronics accessories.",
                    "- Late fees, interest charges, or finance charges on personal credit cards.",
                    "- Subscriptions to personal entertainment streaming platforms (Netflix, Spotify, Amazon Prime)."
                ]
            },
            {
                "number": "7",
                "title": "Submission Deadlines and Approval Hierarchy",
                "content": [
                    "- Submission Deadline: All expense claims must be logged in the ERP with attached digital GST invoices within thirty (30) calendar days from the date the expense was incurred. Claims older than 30 days are forfeited.",
                    "- Tax Invoice Requirement: Invoices must reflect Northstar Technologies India Pvt. Ltd. and our state GSTIN for any item exceeding INR 1,000.",
                    {
                        "type": "table",
                        "headers": ["Expense Amount (INR)", "Primary Approver", "Final Approving Authority"],
                        "rows": [
                            ["Up to INR 15,000", "Reporting Manager (Band L4+)", "Finance Audit Desk"],
                            ["INR 15,001 to INR 50,000", "Reporting Manager (Band L5+)", "Department Head / Director (Band L6)"],
                            ["Above INR 50,000", "Director (Band L6)", "Chief Financial Officer (CFO)"]
                        ],
                        "widths": [180, 160, 164]
                    }
                ]
            },
            {
                "number": "8",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Claimant Employee: Responsible for incurring expenses solely for justifiable business purposes, securing pre-approvals for certifications and executive purchases, collecting valid GST invoices, and submitting claims within 30 calendar days.",
                    "- Reporting Manager / Approver: Responsible for reviewing expense legitimacy, checking receipt authenticity, verifying cost-center allocation, and approving or rejecting claims within three (3) business days.",
                    "- Department Head / Director (Band L6+): Responsible for monitoring quarterly discretionary spend burn-rates against budgeted allotments and endorsing high-value training/certification applications.",
                    "- Finance Controllership & Accounts Payable: Responsible for auditing claims against tax compliance and statutory GSTIN validity, performing random sample audits, and processing reimbursement payments on the 10th and 25th of each month."
                ]
            },
            {
                "number": "9",
                "title": "Exceptions and Non-Standard Expense Approvals",
                "content": [
                    "- Late Claim Exceptions: Claims submitted between thirty-one (31) and sixty (60) calendar days from the invoice date require formal written justification and authorization from the Department Head and VP of Finance. Claims older than 60 days are permanently forfeited.",
                    "- Budget Cap Deviations: Discretionary team spend exceeding the quarterly allocation (INR 1,200/employee) by up to 10% due to team expansion requires prior written approval from the Head of FP&A.",
                    "- Non-Standard Client Entertainment: Client entertainment exceeding the standard INR 5,000 per head cap requires prior written authorization from the Chief Financial Officer (CFO).",
                    "- Non-Waivable Exclusions: Under no circumstances may exceptions be granted for traffic fines, personal credit card interest, alcohol on personal dining, or unauthorized personal electronics."
                ]
            },
            {
                "number": "10",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "What is the quarterly team dinner allowance per employee?",
                        "a": "Under Section 4, teams receive an engagement allowance of INR 1,200 per employee per calendar quarter. Unused balances do not carry over to the next quarter."
                    },
                    {
                        "type": "faq",
                        "q": "Is there a service commitment bond for expensive technical certifications?",
                        "a": "Yes. Any certification reimbursement exceeding INR 25,000 requires signing a 12-month Service Commitment Agreement. If you voluntarily leave within 12 months, the prorated cost is recovered."
                    },
                    {
                        "type": "faq",
                        "q": "Can a Senior Software Engineer (Band L3) claim the smartphone purchase reimbursement?",
                        "a": "No. Under Section 4, mobile handset purchase reimbursement (up to INR 30,000 once every 24 months) is restricted to Band L5 (Managers/Principals) and above."
                    },
                    {
                        "type": "faq",
                        "q": "What is the deadline for submitting general business expense claims?",
                        "a": "All expense claims must be submitted in the ERP within thirty (30) calendar days from the date the expense was incurred."
                    }
                ]
            },
            {
                "number": "11",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "CURRENT", "Baseline employee expense policy defining team dinner caps, certification reimbursement, executive mobile allowances, and 30-day claim deadline."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }


def get_procurement_v1():
    return {
        "id": "FIN-PROC-001",
        "title": "Procurement and Vendor Management Policy",
        "category": "Finance & Supply Chain Operations",
        "department": "Finance",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Head of Strategic Sourcing & Procurement",
        "approver": "Executive Committee & Chief Financial Officer (CFO)",
        "audience": "All department heads, project managers, and budget holders procuring goods or third-party services",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Overview",
                "content": [
                    "This document defines the corporate policy, competitive bidding mandates, vendor evaluation standards, and approval authorities for procuring goods, hardware, software licenses, and third-party professional services for Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. Effective 01 April 2025."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Governance Objectives",
                "content": [
                    "To ensure that Northstar acquires high-quality goods and services at optimal total cost of ownership (TCO), through ethical, competitive, auditable, and transparent sourcing processes that minimize supply chain and commercial risk."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "- Covered Procurement Categories: Applies to all enterprise expenditures including computing hardware, data center infrastructure, cloud services, commercial off-the-shelf software licenses, SaaS subscriptions, facility management, and external technical consulting across all Northstar entities.",
                    "- Geographic Reach: Enforced across corporate headquarters in Bengaluru and regional centers in Hyderabad, Pune, and Chennai.",
                    "- Scope Exclusions: Employee travel reimbursements are governed exclusively by HR-TRV-001; internal employee expense claims are governed by FIN-EXP-001; statutory payroll and benefits are governed by People Operations."
                ]
            },
            {
                "number": "4",
                "title": "Purchase Requisition (PR) to Purchase Order (PO) Lifecycle",
                "content": [
                    "- Mandatory Purchase Order Rule: No employee has the authority to commit Northstar to any commercial contract, purchase order, or expenditure without an approved electronic Purchase Order (PO) generated through Oracle Fusion ERP.",
                    "- No Retrospective POs: Issuing purchase orders after goods have been delivered or services commenced ('after-the-fact POs') is strictly prohibited, except under documented emergency procurement circumstances."
                ]
            },
            {
                "number": "5",
                "title": "Competitive Quotation Rules and Bidding Thresholds",
                "content": [
                    "All purchases must strictly adhere to the competitive procurement rules and quotation thresholds outlined below:",
                    {
                        "type": "table",
                        "headers": ["Procurement Value (INR)", "Quotation Mandate", "Procurement Method", "Evaluation Criteria"],
                        "rows": [
                            ["Up to INR 1,00,000", "Single verified commercial quotation", "Direct Purchase / Catalogs", "Price reasonability, brand reliability"],
                            ["INR 1,00,001 to INR 10,00,000", "Minimum three (3) independent competitive written quotes", "Formal Request for Quotation (RFQ)", "Commercial evaluation matrix, delivery SLA"],
                            ["INR 10,00,001 to INR 50,00,000", "Formal sealed tender / RFP", "Managed by Central Sourcing", "Techno-commercial scoring, financial stability"],
                            ["Above INR 50,00,000", "Open competitive tender / Executive Board review", "Executive Procurement Committee", "Comprehensive TCO, risk audit, security assessment"]
                        ],
                        "widths": [120, 130, 120, 134]
                    },
                    "Sole-Source Procurement: Sourcing without competitive quotes is permitted only when goods/services are proprietary or available from a sole monopoly provider. Requires a formal Sole-Source Justification Certificate approved in writing by the CFO."
                ]
            },
            {
                "number": "6",
                "title": "Vendor Due Diligence and Onboarding (KYC)",
                "content": [
                    "Before any vendor can be issued a PO or receive payment, Central Procurement must complete the following onboarding verification:",
                    "- Legal Identification: Valid Certificate of Incorporation, GSTIN registration certificate, PAN card copy.",
                    "- MSME Classification: Submission of Udyam Registration Certificate (if registered under the MSMED Act, 2006) to ensure priority statutory payment.",
                    "- Financial Health: Audited financial statements (Balance Sheet and Profit & Loss) for the preceding two (2) fiscal years.",
                    "- Anti-Bribery & Ethics: Signed adherence to the Northstar Supplier Code of Conduct and Anti-Bribery Declaration.",
                    "- Banking Details: Cancelled business cheque or bank confirmation letter for automated NEFT/RTGS payment setups."
                ]
            },
            {
                "number": "7",
                "title": "Financial Approval Matrix for Procurement",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Spend Limit (INR)", "Primary Recommender", "Final Approving Authority"],
                        "rows": [
                            ["Up to INR 50,000", "Project / Technical Lead (Band L4)", "Department Manager (Band L5)"],
                            ["INR 50,001 to INR 2,50,000", "Department Manager (Band L5)", "Practice Head / Director (Band L6)"],
                            ["INR 2,50,001 to INR 10,00,000", "Director (Band L6)", "Vice President (Band L7)"],
                            ["Above INR 10,00,000", "Vice President (Band L7)", "Executive Procurement Committee (CFO & CEO)"]
                        ],
                        "widths": [180, 160, 164]
                    }
                ]
            },
            {
                "number": "8",
                "title": "Payment Terms and MSME Statutory Compliance",
                "content": [
                    "- Standard Corporate Payment Terms: Net forty-five (45) calendar days from receipt of a verified, GST-compliant tax invoice accompanied by a signed Goods Receipt Note (GRN) or Service Sign-off.",
                    "- MSMED Act 2006 Compliance: For registered Micro and Small enterprises, payments must be settled within the statutory deadline of forty-five (45) calendar days from acceptance. Central Finance flags MSME vendor invoices for prioritized automated payment processing.",
                    "- Advance Payments: Commercial advance payments exceeding 20% of contract value are prohibited without an irrevocable Bank Guarantee (BG) from a scheduled commercial bank."
                ]
            },
            {
                "number": "9",
                "title": "Emergency Procurement Protocol",
                "content": [
                    "- Scope: Applies exclusively to sudden, critical operational emergencies (e.g., core data center cooling failure, production server hardware outage) where standard procurement lead times would cause catastrophic client disruption.",
                    "- Financial Cap: Up to INR 2,00,000 may be committed immediately upon verbal/email authorization from a Band L6+ Director.",
                    "- Retrospective Ratification: A formal emergency Purchase Requisition and retrospective PO must be submitted in the ERP within forty-eight (48) hours of the incident."
                ]
            },
            {
                "number": "10",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Requisitioner / Project Lead: Responsible for defining accurate technical specifications, estimating required quantities, avoiding contract splitting, and verifying initial budget availability.",
                    "- Strategic Sourcing & Procurement Desk: Responsible for commercial negotiations, floating RFQs, evaluating competitive bids, onboarding vendors through KYC, and issuing approved Purchase Orders.",
                    "- Department Head / Budget Owner: Responsible for validating business ROI, verifying spend alignment with annual operational budgets, and enforcing procurement threshold compliance.",
                    "- Finance & Accounts Payable: Responsible for three-way matching (PO, Invoice, GRN), executing statutory tax deductions (TDS, GST-TDS), and ensuring payment settlement within Net 45 days.",
                    "- Legal & Information Security: Responsible for reviewing Master Services Agreements (MSAs), intellectual property indemnities, and vendor SOC 2 / ISO 27001 data protection compliance."
                ]
            },
            {
                "number": "11",
                "title": "Procurement Exceptions and Single-Source Waivers",
                "content": [
                    "- Sole-Source Exemption Protocol: When technical compatibility or proprietary IP precludes multi-vendor bidding, the requisitioner must submit a Sole-Source Justification Form endorsed by the Practice Head (Band L6) and approved in writing by the CFO.",
                    "- Retrospective PO Exception: Any emergency purchase undertaken without a prior PO must complete formal retrospective ratification within 48 hours; unauthorized retroactive POs will result in cost disallowance and disciplinary audit.",
                    "- Payment Term Deviations: Requests to shorten payment terms below Net 45 days or provide advance deposits require written authorization from the Corporate Controller and CFO.",
                    "- Governance Audit Log: All procurement deviations and single-source waivers are logged in the Central Procurement Audit Log and reviewed bi-annually by Internal Audit."
                ]
            },
            {
                "number": "12",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "When are three competitive quotes mandatory for a purchase?",
                        "a": "Under Section 5, any procurement with a value between INR 1,00,001 and INR 10,00,000 strictly requires a minimum of three (3) independent competitive written quotes."
                    },
                    {
                        "type": "faq",
                        "q": "What are the standard payment terms for vendor invoices?",
                        "a": "Standard payment terms are Net 45 calendar days from receipt of a verified tax invoice and signed Goods Receipt Note (GRN). MSME vendors are guaranteed payment within 45 days pursuant to the MSMED Act."
                    },
                    {
                        "type": "faq",
                        "q": "Who must approve a procurement contract valued at INR 15,00,000?",
                        "a": "Under Section 7, any procurement exceeding INR 10,00,000 must be approved by the Executive Procurement Committee comprising the Chief Financial Officer (CFO) and Chief Executive Officer (CEO)."
                    },
                    {
                        "type": "faq",
                        "q": "What is the procedure for emergency hardware procurement?",
                        "a": "Emergency procurement up to INR 2,00,000 is authorized for critical system outages upon Director approval, provided a retrospective PO is submitted within 48 hours."
                    }
                ]
            },
            {
                "number": "13",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "CURRENT", "Unified procurement governance establishing PR-to-PO workflows, 3-quote thresholds, vendor KYC, MSMED Act compliance, and emergency procurement limits."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }
