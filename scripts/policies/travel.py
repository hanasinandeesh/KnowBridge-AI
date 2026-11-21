"""
Travel and Reimbursement Policies (v1.0 SUPERSEDED and v2.0 CURRENT)
for Northstar Technologies India Pvt. Ltd.
"""

def get_travel_v1():
    return {
        "id": "HR-TRV-001",
        "title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2026",
        "status": "SUPERSEDED",
        "owner": "Director – People Operations & Workplace Experience",
        "approver": "Executive Committee & Chief Financial Officer (CFO)",
        "audience": "All full-time and contract employees traveling on official business commencing before 01 April 2026",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Administration",
                "content": [
                    "This document establishes the official governance rules for official domestic and international business travel undertaken by employees of Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: SUPERSEDED. This version (v1.0) governed official business travel between 01 April 2025 and 31 March 2026. On 01 April 2026, it was formally superseded by HR-TRV-001 Version 2.0.",
                    "Version Applicability Rule: Any business trip commencing prior to 01 April 2026 is strictly governed by the provisions, expenditure limits, and submission deadlines of this Version 1.0. Trips commencing on or after 01 April 2026 must adhere to Version 2.0."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Strategic Intent",
                "content": [
                    "The purpose of this Policy is to define clear guidelines for official travel, ensuring employee physical safety, reasonable comfort, and operational productivity while enforcing fiscal discipline and transparent expenditure management across Northstar's Indian operations."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "This policy applies to all permanent full-time employees, fixed-term contract staff, and probationers across all Northstar facilities (Bengaluru HQ, Hyderabad, Pune, Chennai).",
                    "Official Travel is defined as any authorized travel exceeding fifty (50) kilometers from the employee's designated base office or residential address to conduct official company business.",
                    "Exclusions: Daily commuting between home and base office is strictly excluded. Personal side trips or vacation extensions taken alongside business trips are non-reimbursable."
                ]
            },
            {
                "number": "4",
                "title": "Definitions and Tier Classifications",
                "content": [
                    "- Base Location: The registered office city (Bengaluru, Hyderabad, Pune, or Chennai) where the employee is assigned in the HRMS.",
                    "- Band L1–L2: Associate Engineers, Software Engineers, Quality Analysts, Operations Associates.",
                    "- Band L3–L4: Senior Software Engineers, Technical Leads, Specialist Consultants, Senior Analysts.",
                    "- Band L5: Engineering Managers, Principal Engineers, Solutions Architects, Senior Practice Managers.",
                    "- Band L6+: Directors, Senior Directors, Vice Presidents, Senior Vice Presidents, and C-Suite.",
                    "- Tier 1 Cities: Bengaluru, Mumbai (including Navi Mumbai/Thane), Delhi-NCR (New Delhi, Gurugram, Noida), Hyderabad, Chennai, Pune, and Kolkata.",
                    "- Tier 2 Cities: Ahmedabad, Chandigarh, Kochi, Jaipur, Lucknow, Indore, Coimbatore, Vadodara, Bhubaneswar, and Nagpur.",
                    "- Tier 3 Cities: All other municipal corporations, district headquarters, and rural locations in India.",
                    "- Per Diem: Fixed daily allowance covering breakfast, lunch, dinner, and incidental out-of-pocket expenses without individual voucher submission."
                ]
            },
            {
                "number": "5",
                "title": "Travel Authorization and Booking Workflows",
                "content": [
                    {
                        "type": "subsection",
                        "number": "5.1",
                        "title": "Advance Booking Requirements",
                        "content": [
                            "All domestic travel must be booked at least seven (7) calendar days in advance of the travel date through the internal Corporate Travel Desk (CTD).",
                            "Emergency domestic travel (booked less than 48 hours prior) requires written email justification and approval from the Department Head (Band L6+).",
                            "International travel requires a minimum advance booking notice of twenty-one (21) calendar days."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "5.2",
                        "title": "Modes of Travel and Flight Entitlements",
                        "content": [
                            "Domestic Flights: All employees across all bands (L1 through L6+) must travel in Economy Class on domestic routes.",
                            "International Flights: Economy Class is mandatory for flights under eight (8) continuous hours. For international flights exceeding 8 continuous hours, Band L6+ may travel in Business Class, Band L5 in Premium Economy, and Bands L1–L4 in Economy Class.",
                            "Rail Travel: Bands L1–L2 may travel in AC 3-Tier; Bands L3–L4 in AC 2-Tier or AC Chair Car; Bands L5+ in AC First Class or Executive Chair Car."
                        ]
                    }
                ]
            },
            {
                "number": "6",
                "title": "Lodging and Accommodation Limits",
                "content": [
                    "Employees must book partner hotels via CTD. If unavailable, employees may book direct accommodations up to the nightly room caps below (excluding GST).",
                    {
                        "type": "table",
                        "headers": ["Employee Band", "Tier 1 Cities (INR/Night)", "Tier 2 Cities (INR/Night)", "Tier 3 Cities (INR/Night)"],
                        "rows": [
                            ["Band L1 – L2", "INR 4,000", "INR 2,800", "INR 2,000"],
                            ["Band L3 – L4", "INR 5,500", "INR 3,800", "INR 2,800"],
                            ["Band L5", "INR 7,500", "INR 5,000", "INR 3,800"],
                            ["Band L6+", "INR 11,000", "INR 7,500", "INR 5,000"]
                        ],
                        "widths": [140, 120, 120, 124]
                    },
                    "GST is reimbursable above these caps if the invoice reflects Northstar's valid state GSTIN.",
                    "Staying with Friends/Relatives: Employees may claim an Own Arrangement Allowance of INR 1,000 per night for Tier 1 and INR 750 per night for Tier 2/3 without submitting hotel bills."
                ]
            },
            {
                "number": "7",
                "title": "Daily Per Diem and Meal Allowances",
                "content": [
                    "A non-itemized daily per diem is provided to cover meals and transit incidentals:",
                    {
                        "type": "table",
                        "headers": ["Employee Band", "Tier 1 Cities (INR/Day)", "Tier 2 Cities (INR/Day)", "Tier 3 Cities (INR/Day)"],
                        "rows": [
                            ["Band L1 – L2", "INR 1,500", "INR 1,100", "INR 800"],
                            ["Band L3 – L4", "INR 2,000", "INR 1,500", "INR 1,100"],
                            ["Band L5", "INR 2,500", "INR 1,800", "INR 1,400"],
                            ["Band L6+", "INR 3,500", "INR 2,500", "INR 1,800"]
                        ],
                        "widths": [140, 120, 120, 124]
                    },
                    "If lunch or dinner is provided by the client or conference organizer, 40% per provided meal must be deducted from the per diem. Alcoholic beverages are strictly non-reimbursable."
                ]
            },
            {
                "number": "8",
                "title": "Local Conveyance and Mileage",
                "content": [
                    "- Personal Car: Reimbursed at INR 10.00 per kilometer (includes fuel, wear and tear). Tolls and parking reimbursable at actuals with receipts.",
                    "- Personal Two-Wheeler: Reimbursed at INR 4.50 per kilometer.",
                    "- Hired Cabs / Ride-Hailing: Ola/Uber actuals up to INR 1,500 per day in Tier 1 cities, INR 1,000 in Tier 2/3 cities."
                ]
            },
            {
                "number": "9",
                "title": "Travel Advances and Approvals",
                "content": [
                    "- Permanent employees traveling for over 5 days may request an advance up to INR 50,000 via ERP.",
                    "- Travel advances must be settled within the claim submission window.",
                    {
                        "type": "table",
                        "headers": ["Authorization Category", "Primary Approver", "Final Approving Authority"],
                        "rows": [
                            ["Domestic Travel Request (< 3 days)", "Line Manager (Band L4+)", "Automated CTD Ticketing"],
                            ["Domestic Travel Request (> 3 days)", "Line Manager (Band L4+)", "Director / Department Head (Band L6)"],
                            ["Expense Claim up to INR 25,000", "Line Manager (Band L5+)", "Finance Audit Team"],
                            ["Expense Claim INR 25,001 to 75,000", "Line Manager (Band L5+)", "Director / Department Head (Band L6)"],
                            ["Expense Claim above INR 75,000", "Director (Band L6)", "Chief Financial Officer (CFO)"]
                        ],
                        "widths": [200, 150, 154]
                    }
                ]
            },
            {
                "number": "10",
                "title": "Claim Submission Deadlines and Reimbursement Timelines",
                "content": [
                    "Mandatory Submission Window (v1.0): Travel expense claims must be submitted in the ERP within fifteen (15) calendar days after trip completion.",
                    "Claims submitted between 16 and 30 calendar days require written Department Head justification.",
                    "Claims submitted after thirty (30) calendar days are automatically forfeited and will not be reimbursed without CFO written approval.",
                    "Reimbursement Processing: Approved claims are disbursed on the 10th and 25th of each month via electronic bank transfer."
                ]
            },
            {
                "number": "11",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Traveling Employee (Claimant): Responsible for securing pre-travel authorization in the HRMS, adhering to accommodation and per diem ceilings, preserving valid GST tax invoices, and submitting claims within 15 calendar days of trip completion.",
                    "- Reporting Manager / Line Approver: Responsible for verifying genuine business purpose, confirming budget availability, checking flight and lodging compliance, and approving or rejecting travel requests within forty-eight (48) hours.",
                    "- Corporate Travel Desk: Responsible for corporate vendor tie-ups, ticketing through approved corporate booking tools, monitoring corporate hotel rates, and ensuring travel safety compliance.",
                    "- Corporate Finance & Accounts Payable: Responsible for auditing expense receipts against policy thresholds, recovering outstanding travel advances, processing disbursements on the 10th and 25th, and maintaining statutory audit records."
                ]
            },
            {
                "number": "12",
                "title": "Exceptions and Policy Deviations",
                "content": [
                    "- General Exception Rule: Any deviation from policy ceilings (e.g. hotel room exceeding tier cap due to city-wide conventions) requires prior written justification and approval from the Department Head (Band L6) and Corporate Finance before incurring the expense.",
                    "- Late Claim Submission Exception: Claims submitted between 16 and 30 calendar days require formal Department Head written justification. Submissions exceeding 30 calendar days are automatically forfeited and require exceptional CFO sign-off.",
                    "- Emergency Off-Portal Bookings: If the corporate travel portal is inaccessible during an emergency, employees may book directly up to approved tier limits, provided the Travel Desk is notified within twelve (12) hours of booking.",
                    "- Exception Tracking: All approved policy deviations must be logged by Finance Controllership in the Quarterly Policy Governance Audit Report."
                ]
            },
            {
                "number": "13",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "What is the claim submission deadline under Travel Policy v1.0?",
                        "a": "Under v1.0, travel expense claims must be submitted within 15 calendar days from the date of trip completion. Claims submitted after 30 days are automatically forfeited."
                    },
                    {
                        "type": "faq",
                        "q": "What policy governs a business trip that began on 25 March 2026 and ended on 02 April 2026?",
                        "a": "Trips commencing before 01 April 2026 are governed entirely by Version 1.0, including the 15-calendar-day claim submission deadline and v1.0 hotel caps."
                    },
                    {
                        "type": "faq",
                        "q": "Can a Senior Software Engineer (Band L3) travel in Business Class domestically?",
                        "a": "No. Under Section 5.2, all employees regardless of band must travel in Economy Class for all domestic flights."
                    },
                    {
                        "type": "faq",
                        "q": "Are laundry charges reimbursable for a 3-night business trip?",
                        "a": "No. Laundry expenses are reimbursable only for business trips exceeding four (4) consecutive nights."
                    }
                ]
            },
            {
                "number": "14",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "SUPERSEDED", "Baseline unified travel policy consolidating PAN-India operations. 15-day claim deadline."],
                            ["2.0", "01 April 2026", "CURRENT", "Superseded v1.0. Extended claim deadline to 30 days, increased hotel caps and per diem."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }


def get_travel_v2():
    return {
        "id": "HR-TRV-001",
        "title": "Business Travel and Reimbursement Policy",
        "category": "Human Resources & Corporate Travel",
        "department": "Human Resources",
        "version": "2.0",
        "effective_date": "01 April 2026",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Director – People Operations & Workplace Experience",
        "approver": "Executive Committee & Chief Financial Officer (CFO)",
        "audience": "All full-time and contract employees traveling on official business commencing on or after 01 April 2026",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Administration",
                "content": [
                    "This document establishes the official governance rules for official domestic and international business travel undertaken by employees of Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. This version (v2.0) took effect on 01 April 2026 and supersedes HR-TRV-001 Version 1.0 in its entirety.",
                    "Version Applicability Rule: Any business trip commencing on or after 01 April 2026 is strictly governed by this Version 2.0. Trips that commenced before 01 April 2026 remain auditable under Version 1.0.",
                    "Primary Changes from Version 1.0: (a) Expense claim submission deadline extended from 15 calendar days to 30 calendar days; (b) Upward revision of hotel accommodation caps across all city tiers; (c) Increased daily per diem and car mileage rates; (d) Increased travel advance ceiling to INR 75,000; (e) Introduction of Green Travel sustainability initiatives."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Strategic Intent",
                "content": [
                    "This Policy provides an equitable, modern, and employee-centric framework for corporate travel. It aligns corporate travel practices with inflation trends, enhances employee wellbeing, supports sustainability, and maintains rigorous fiscal auditability."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "Applies to all permanent full-time employees, fixed-term contract staff, and probationers across Northstar's Bengaluru HQ, Hyderabad, Pune, and Chennai facilities.",
                    "Official Travel is defined as authorized travel exceeding fifty (50) kilometers from the employee's base location to conduct company business.",
                    "Exclusions: Regular commuting and personal vacation extensions are strictly excluded."
                ]
            },
            {
                "number": "4",
                "title": "Definitions and Tier Classifications",
                "content": [
                    "- Base Location: The registered office city (Bengaluru, Hyderabad, Pune, or Chennai) where the employee is assigned in HRMS.",
                    "- Band L1–L2: Associate Engineers, Software Engineers, Quality Analysts, Operations Associates.",
                    "- Band L3–L4: Senior Software Engineers, Technical Leads, Specialist Consultants, Senior Analysts.",
                    "- Band L5: Engineering Managers, Principal Engineers, Solutions Architects, Senior Practice Managers.",
                    "- Band L6+: Directors, Senior Directors, Vice Presidents, Senior Vice Presidents, and C-Suite.",
                    "- Tier 1 Cities: Bengaluru, Mumbai (including Navi Mumbai/Thane), Delhi-NCR (New Delhi, Gurugram, Noida), Hyderabad, Chennai, Pune, and Kolkata.",
                    "- Tier 2 Cities: Ahmedabad, Chandigarh, Kochi, Jaipur, Lucknow, Indore, Coimbatore, Vadodara, Bhubaneswar, and Nagpur.",
                    "- Tier 3 Cities: All other municipal corporations, district centers, and rural locations in India.",
                    "- Green Travel: Corporate initiative prioritizing rail travel over short flights for routes under 6 hours (e.g., Vande Bharat Express)."
                ]
            },
            {
                "number": "5",
                "title": "Travel Authorization and Booking Workflows",
                "content": [
                    {
                        "type": "subsection",
                        "number": "5.1",
                        "title": "Advance Booking Requirements",
                        "content": [
                            "Domestic flights must be booked at least ten (10) calendar days in advance via the Corporate Travel Desk (CTD) or the self-service travel portal.",
                            "Emergency domestic travel (<48 hours) requires written approval from a Band L6+ Director.",
                            "International travel requires a minimum advance booking notice of twenty-one (21) calendar days."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "5.2",
                        "title": "Flight and Rail Entitlements",
                        "content": [
                            "Domestic Flights: All employees across all bands (L1 to L6+) must travel in Economy Class for domestic flights.",
                            "International Flights: Flights exceeding five (5) continuous flying hours allow Band L5 to travel in Premium Economy, and Band L6+ in Business Class. Flights under 5 hours are Economy Class for all bands.",
                            "Rail Travel: Bands L1–L2 in AC 3-Tier or AC Chair Car; Bands L3–L4 in AC 2-Tier or Executive Chair Car; Bands L5+ in AC First Class or Vande Bharat Executive Class."
                        ]
                    }
                ]
            },
            {
                "number": "6",
                "title": "Lodging and Accommodation Limits",
                "content": [
                    "Employees must book partner hotels via CTD. The revised nightly room caps (excluding GST) under v2.0 are:",
                    {
                        "type": "table",
                        "headers": ["Employee Band", "Tier 1 Cities (INR/Night)", "Tier 2 Cities (INR/Night)", "Tier 3 Cities (INR/Night)"],
                        "rows": [
                            ["Band L1 – L2", "INR 5,000", "INR 3,500", "INR 2,500"],
                            ["Band L3 – L4", "INR 7,500", "INR 5,000", "INR 3,500"],
                            ["Band L5", "INR 9,500", "INR 6,500", "INR 4,500"],
                            ["Band L6+", "INR 13,500", "INR 9,500", "INR 6,500"]
                        ],
                        "widths": [140, 120, 120, 124]
                    },
                    "GST is reimbursable above these caps if the invoice reflects Northstar's valid state GSTIN.",
                    "Staying with Friends/Relatives: Own Arrangement Allowance is revised to INR 1,500 per night for Tier 1 and INR 1,000 per night for Tier 2/3."
                ]
            },
            {
                "number": "7",
                "title": "Daily Per Diem and Meal Allowances",
                "content": [
                    "Revised non-itemized daily per diem rates under v2.0:",
                    {
                        "type": "table",
                        "headers": ["Employee Band", "Tier 1 Cities (INR/Day)", "Tier 2 Cities (INR/Day)", "Tier 3 Cities (INR/Day)"],
                        "rows": [
                            ["Band L1 – L2", "INR 2,000", "INR 1,400", "INR 1,000"],
                            ["Band L3 – L4", "INR 2,500", "INR 1,800", "INR 1,300"],
                            ["Band L5", "INR 3,200", "INR 2,200", "INR 1,600"],
                            ["Band L6+", "INR 4,500", "INR 3,200", "INR 2,200"]
                        ],
                        "widths": [140, 120, 120, 124]
                    },
                    "Deductions apply if meals are provided by client/organizer: 20% for breakfast, 40% for lunch, 40% for dinner. Alcohol is strictly non-reimbursable."
                ]
            },
            {
                "number": "8",
                "title": "Local Conveyance and Mileage",
                "content": [
                    "- Personal Car: Reimbursed at INR 12.00 per kilometer (increased from INR 10.00 in v1.0). Tolls must be evidenced by FASTag transaction statements.",
                    "- Personal Two-Wheeler: Reimbursed at INR 6.00 per kilometer (increased from INR 4.50 in v1.0).",
                    "- Hired Cabs / Ride-Hailing: Employees should use Uber for Business or Ola Corporate linked to Northstar corporate billing. Daily cap on actuals is INR 2,000 in Tier 1 and INR 1,400 in Tier 2/3."
                ]
            },
            {
                "number": "9",
                "title": "Travel Advances and Approvals",
                "content": [
                    "- Permanent employees traveling for over 5 days may request an advance up to INR 75,000 via ERP (increased from INR 50,000).",
                    {
                        "type": "table",
                        "headers": ["Authorization Category", "Primary Approver", "Final Approving Authority"],
                        "rows": [
                            ["Domestic Travel Request (< 3 days)", "Line Manager (Band L4+)", "Automated CTD Ticketing"],
                            ["Domestic Travel Request (> 3 days)", "Line Manager (Band L4+)", "Director / Department Head (Band L6)"],
                            ["Expense Claim up to INR 40,000", "Line Manager (Band L5+)", "Finance Audit Team"],
                            ["Expense Claim INR 40,001 to 1,00,000", "Line Manager (Band L5+)", "Director / Department Head (Band L6)"],
                            ["Expense Claim above INR 1,00,000", "Director (Band L6)", "Chief Financial Officer (CFO)"]
                        ],
                        "widths": [200, 150, 154]
                    }
                ]
            },
            {
                "number": "10",
                "title": "Claim Submission Deadlines and Reimbursement Timelines",
                "content": [
                    "Mandatory Submission Window (v2.0): Travel expense claims must be submitted in the ERP within thirty (30) calendar days after trip completion (extended from 15 calendar days in v1.0).",
                    "Claims submitted between 31 and 45 calendar days require Line Manager and Department Head justification.",
                    "Claims submitted after forty-five (45) calendar days will be rejected and require CFO exception approval.",
                    "Reimbursement Processing: Approved claims are processed bi-weekly (10th and 25th) via direct bank transfer."
                ]
            },
            {
                "number": "11",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Traveling Employee (Claimant): Responsible for completing pre-travel workflows, securing approvals before departure, ensuring compliance with revised hotel caps and per diem rates, compiling GST-compliant hotel and transport receipts, and submitting claims within 30 calendar days of trip completion.",
                    "- Reporting Manager / Line Approver: Responsible for evaluating travel necessity, checking budget allocations, ensuring compliance with travel classes and hotel limits, and approving or escalating claims within 48 hours.",
                    "- Corporate Travel Desk & Travel Partner: Responsible for maintaining competitive corporate rates, managing emergency rebooking hotlines, enforcing green travel options, and auditing lodging vouchers.",
                    "- Corporate Finance & Controllership: Responsible for verifying GST compliance, monitoring travel advance reconciliations, processing bi-weekly disbursements (10th and 25th), and auditing late claim exception approvals."
                ]
            },
            {
                "number": "12",
                "title": "Exceptions and Policy Deviations",
                "content": [
                    "- General Threshold Exceptions: Accommodations exceeding Tier caps due to seasonal peak demand or high-density international summits must be pre-approved in writing by the Practice Head / Director (Band L6) and Corporate Finance before booking.",
                    "- Late Claim Exceptions (v2.0): Claims submitted between 31 and 45 calendar days require documented Line Manager and Department Head justification. Claims beyond forty-five (45) calendar days will be rejected and require formal written CFO exception approval.",
                    "- Non-Standard Conveyance Exceptions: Use of self-driven personal vehicles for trips exceeding 300 kilometers requires prior written approval from the Department Head citing business necessity.",
                    "- Exception Governance: All exceptions are audited quarterly by the Corporate Governance and Risk Committee to detect chronic policy leakage."
                ]
            },
            {
                "number": "13",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "What is the claim submission deadline under Travel Policy v2.0?",
                        "a": "Under v2.0, travel expense claims must be submitted within 30 calendar days from the date of trip completion. This is an extension from the 15-day deadline in v1.0."
                    },
                    {
                        "type": "faq",
                        "q": "If an employee took a business trip commencing 10 April 2026, which policy version applies?",
                        "a": "Because the trip commenced on or after 01 April 2026, it is governed by Version 2.0. The employee has 30 calendar days to submit claims and can avail of the higher hotel caps (e.g., INR 7,500 for Band L3–L4 in Tier 1)."
                    },
                    {
                        "type": "faq",
                        "q": "Can I claim FASTag toll receipts for personal car business travel?",
                        "a": "Yes. Under v2.0, FASTag monthly or transaction statements clearly indicating vehicle registration and toll plaza timestamps are mandatory for toll reimbursements."
                    },
                    {
                        "type": "faq",
                        "q": "Are domestic flight upgrades to Business Class reimbursable in v2.0?",
                        "a": "No. Under Section 5.2 of v2.0, all employees across all bands must travel in Economy Class for domestic flights without exception."
                    }
                ]
            },
            {
                "number": "14",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "SUPERSEDED", "Baseline unified travel policy. 15-day claim submission deadline."],
                            ["2.0", "01 April 2026", "CURRENT", "Extended claim deadline to 30 days. Revised hotel caps, per diem rates, mileage rates, and advance limits."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }
