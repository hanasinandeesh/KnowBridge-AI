"""
Employee Leave Policies (v1.0 SUPERSEDED and v2.0 CURRENT)
for Northstar Technologies India Pvt. Ltd.
"""

def get_leave_v1():
    return {
        "id": "HR-LVE-001",
        "title": "Employee Leave Policy",
        "category": "Human Resources & Benefits",
        "department": "Human Resources",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2026",
        "status": "SUPERSEDED",
        "owner": "Head – People Operations & Total Rewards",
        "approver": "Executive Committee & Chief Executive Officer (CEO)",
        "audience": "All permanent employees and probationers for leave periods prior to 01 April 2026",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Administration",
                "content": [
                    "This document defines the leave entitlements, accrual rules, and application procedures for all employees of Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: SUPERSEDED. This version (v1.0) governed employee leave from 01 April 2025 through 31 March 2026. Effective 01 April 2026, it was superseded by HR-LVE-001 Version 2.0.",
                    "Version Applicability Rule: All leave applications for absence periods commencing prior to 01 April 2026 are governed by this Version 1.0. Any leave commencing on or after 01 April 2026 is governed by Version 2.0."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Guiding Principles",
                "content": [
                    "Northstar recognizes the importance of work-life balance and rest. This policy provides paid time off for vacation, illness, personal responsibilities, and family commitments while ensuring business continuity and operational stability."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "This policy applies to all regular full-time employees, trainees, and probationers across all office locations (Bengaluru, Hyderabad, Pune, Chennai).",
                    "Independent contractors and external vendor consultants are not eligible for paid leave under this policy."
                ]
            },
            {
                "number": "4",
                "title": "Leave Categories and Entitlements (v1.0)",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Leave Type", "Annual Quota (v1.0)", "Accrual Frequency", "Max Carry-Forward", "Encashment Rule"],
                        "rows": [
                            ["Earned Leave (EL)", "18 working days", "1.5 days / month", "Up to 30 days", "Only at separation/resignation"],
                            ["Casual Leave (CL)", "10 working days", "Credited on Jan 1", "0 days (Lapses Dec 31)", "Non-encashable"],
                            ["Sick Leave (SL)", "8 working days", "Credited on Jan 1", "0 days (Lapses Dec 31)", "Non-encashable"],
                            ["Maternity Leave", "26 calendar weeks", "Event-based", "N/A", "Paid in full (Maternity Act)"],
                            ["Paternity Leave", "5 working days", "Event-based", "N/A", "Must use within 3 months"],
                            ["Bereavement Leave", "3 working days", "Event-based", "N/A", "Immediate family only"]
                        ],
                        "widths": [120, 95, 95, 95, 99]
                    }
                ]
            },
            {
                "number": "5",
                "title": "Earned Leave (EL) Rules and Accrual",
                "content": [
                    "- Accrual: Full-time employees accrue Earned Leave at the rate of 1.5 days per completed calendar month of active service, totaling 18 days per annum.",
                    "- Carry-Forward: A maximum of thirty (30) days of accrued EL may be carried forward into the subsequent calendar year. Any accumulated balance exceeding 30 days as of 31 December automatically lapses.",
                    "- Encashment: Under v1.0, EL encashment during active service is not permitted. Accumulated EL up to a maximum of 30 days is encashed only upon resignation, retirement, or termination.",
                    "- Advance Notice: Planned EL exceeding three (3) consecutive working days must be applied via the HRMS at least ten (10) calendar days in advance."
                ]
            },
            {
                "number": "6",
                "title": "Casual and Sick Leave Provisions",
                "content": [
                    {
                        "type": "subsection",
                        "number": "6.1",
                        "title": "Casual Leave (CL)",
                        "content": [
                            "CL is intended for unforeseen personal tasks or short emergencies. Employees receive 10 days per calendar year.",
                            "CL cannot be taken for more than three (3) consecutive working days at a time.",
                            "Unused CL cannot be carried forward to the next year and lapses on 31 December."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "6.2",
                        "title": "Sick Leave (SL)",
                        "content": [
                            "SL is provided for illness, injury, and medical consultations. Employees receive 8 days per calendar year.",
                            "Medical Certificate Requirement: A formal medical certificate issued by a registered medical practitioner (MBBS or higher) is mandatory for any sick leave exceeding three (3) consecutive working days.",
                            "Unused SL cannot be carried forward and cannot be encashed."
                        ]
                    }
                ]
            },
            {
                "number": "7",
                "title": "Special Leave Categories",
                "content": [
                    "- Maternity Leave: Female employees who have worked for at least 80 days in the 12 months preceding delivery are entitled to 26 weeks of paid maternity leave for up to two surviving children.",
                    "- Paternity Leave: Male employees are entitled to 5 working days of paid leave, which must be availed within three (3) months of childbirth.",
                    "- Bereavement Leave: 3 working days of paid leave upon the death of an immediate family member (spouse, child, parent, sibling, parent-in-law)."
                ]
            },
            {
                "number": "8",
                "title": "Leave During Notice Period",
                "content": [
                    "Employees serving their contractual notice period (upon resignation or termination) are not permitted to avail Casual Leave.",
                    "Earned Leave may only be approved during the notice period under exceptional medical circumstances with prior written approval from the Director of People Operations. Any unapproved absence will extend the notice period accordingly."
                ]
            },
            {
                "number": "9",
                "title": "Leave Approval Matrix",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Leave Type and Duration", "Primary Approver", "Secondary / Escalation Approver"],
                        "rows": [
                            ["Casual / Sick Leave (up to 3 days)", "Reporting Manager (Band L4+)", "Automated System Confirmation"],
                            ["Earned Leave (1 to 5 days)", "Reporting Manager (Band L4+)", "Department Lead"],
                            ["Earned Leave (6 to 15 days)", "Reporting Manager (Band L5+)", "Department Head / Director (Band L6)"],
                            ["Earned Leave (> 15 days)", "Director (Band L6)", "Head of People Operations"],
                            ["Maternity / Paternity / Bereavement", "Reporting Manager", "HR Shared Services (HRSS) Validation"]
                        ],
                        "widths": [180, 160, 164]
                    }
                ]
            },
            {
                "number": "10",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Employee: Responsible for planning leaves in advance, submitting leave requests via Darwinbox HRMS, ensuring project handover and out-of-office coverage, and submitting medical certificates within 48 hours of resuming duty after sick leave.",
                    "- Reporting Manager: Responsible for evaluating leave requests against project milestones and deliverables, ensuring equitable team holiday coverage, approving or rejecting applications within 48 hours, and tracking absenteeism patterns.",
                    "- People Operations & Benefits Desk: Responsible for maintaining accurate leave accrual records, configuring public holiday calendars across state centers (Karnataka, Telangana, Maharashtra, Tamil Nadu), and managing statutory compliance.",
                    "- Payroll & Total Rewards: Responsible for executing leave encashments at separation under v1.0 and computing Leave Without Pay (LWP) salary deductions in accordance with monthly attendance logs."
                ]
            },
            {
                "number": "11",
                "title": "Exceptions and Policy Deviations",
                "content": [
                    "- Special Leave Without Pay (LWP): In case of prolonged personal crisis or critical medical conditions where all EL and SL balances are exhausted, employees may request up to thirty (30) days of unpaid leave with written recommendation from the Department Head and approval from the Head of HR.",
                    "- Leave During Notice Period: Earned Leave may only be approved during the notice period under exceptional medical emergencies with prior written authorization from the Head of People Operations.",
                    "- Negative Leave Balance: Advance debit against future unaccrued leave is prohibited except under documented hospitalizations approved by the CPO.",
                    "- Exception Tracking: All statutory leave deviations and LWP dispensations must be documented in the employee's personnel file and audited semi-annually."
                ]
            },
            {
                "number": "12",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "How many days of Earned Leave can I carry forward under v1.0?",
                        "a": "Under v1.0, an employee can carry forward a maximum of 30 days of Earned Leave into the next calendar year. Any balance exceeding 30 days lapses on 31 December."
                    },
                    {
                        "type": "faq",
                        "q": "When is a medical certificate required for Sick Leave under v1.0?",
                        "a": "A registered medical certificate is mandatory if sick leave exceeds three (3) consecutive working days."
                    },
                    {
                        "type": "faq",
                        "q": "Can I encash my Earned Leave while still employed at Northstar under v1.0?",
                        "a": "No. Under v1.0, Earned Leave encashment is strictly permitted only upon separation (resignation, retirement, or termination)."
                    },
                    {
                        "type": "faq",
                        "q": "Which policy applies if I apply for leave on 15 March 2026 for dates between 20 March and 28 March 2026?",
                        "a": "Because the leave dates are prior to 01 April 2026, Version 1.0 governs the leave request and its carry-forward / encashment rules."
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
                            ["1.0", "01 April 2025", "SUPERSEDED", "Baseline leave policy. 18 days EL, 30-day carry-forward cap, 8 days SL."],
                            ["2.0", "01 April 2026", "CURRENT", "Superseded v1.0. Increased EL to 20 days, carry-forward to 45 days, SL to 12 days, introduced Wellness Leave."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }


def get_leave_v2():
    return {
        "id": "HR-LVE-001",
        "title": "Employee Leave Policy",
        "category": "Human Resources & Benefits",
        "department": "Human Resources",
        "version": "2.0",
        "effective_date": "01 April 2026",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Head – People Operations & Total Rewards",
        "approver": "Executive Committee & Chief Executive Officer (CEO)",
        "audience": "All permanent employees and probationers for leave periods on or after 01 April 2026",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Administration",
                "content": [
                    "This document defines the leave entitlements, accrual rules, and application procedures for all employees of Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. This version (v2.0) took effect on 01 April 2026 and supersedes HR-LVE-001 Version 1.0 in its entirety.",
                    "Version Applicability Rule: Any leave request for absence dates on or after 01 April 2026 is strictly governed by this Version 2.0. Leave periods commencing prior to 01 April 2026 remain governed by Version 1.0.",
                    "Primary Changes from Version 1.0: (a) Earned Leave quota increased from 18 to 20 days per annum; (b) Maximum EL carry-forward cap increased from 30 to 45 days; (c) Annual voluntary EL encashment introduced (up to 10 days); (d) Sick Leave increased from 8 to 12 days; (e) Medical certificate threshold tightened to >2 consecutive days; (f) Paternity Leave increased from 5 to 10 working days; (g) Bereavement Leave increased from 3 to 5 days; (h) New Wellness / Mental Health Leave introduced (2 days/year)."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Guiding Principles",
                "content": [
                    "Northstar is committed to an employee-centric wellness culture. Version 2.0 provides expanded rest periods, enhanced medical security, mental health support, and flexible annual leave encashment options."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "Applies to all regular full-time employees, trainees, and probationers across Northstar's Bengaluru HQ, Hyderabad, Pune, and Chennai facilities.",
                    "Contractors and external consultants are not eligible for paid leave under this policy."
                ]
            },
            {
                "number": "4",
                "title": "Leave Categories and Entitlements (v2.0)",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Leave Type", "Annual Quota (v2.0)", "Accrual Frequency", "Max Carry-Forward", "Encashment Rule"],
                        "rows": [
                            ["Earned Leave (EL)", "20 working days", "1.67 days / month", "Up to 45 days", "Annual encashment up to 10 days; balance at exit"],
                            ["Casual Leave (CL)", "8 working days", "Credited on Jan 1", "0 days (Lapses Dec 31)", "Non-encashable"],
                            ["Sick Leave (SL)", "12 working days", "Credited on Jan 1", "0 days (Lapses Dec 31)", "Non-encashable"],
                            ["Wellness Leave", "2 working days", "Credited on Jan 1", "0 days (Lapses Dec 31)", "Non-encashable"],
                            ["Maternity Leave", "26 calendar weeks", "Event-based", "N/A", "Paid in full (Maternity Act)"],
                            ["Paternity Leave", "10 working days", "Event-based", "N/A", "Must use within 6 months"],
                            ["Bereavement Leave", "5 working days", "Event-based", "N/A", "Immediate family"]
                        ],
                        "widths": [115, 95, 95, 95, 104]
                    }
                ]
            },
            {
                "number": "5",
                "title": "Earned Leave (EL) Rules, Accrual and Encashment",
                "content": [
                    "- Accrual: Full-time employees accrue 1.67 days per month, totaling 20 working days per calendar year.",
                    "- Carry-Forward: Up to forty-five (45) days of accrued EL may be carried forward into the next calendar year (increased from 30 days in v1.0). Balance beyond 45 days lapses on 31 December.",
                    "- Annual Voluntary Encashment: Under v2.0, employees with an accumulated balance of at least 25 days may encash up to ten (10) days of EL once annually during the November payroll window, provided a minimum balance of 15 days is retained.",
                    "- Separation Encashment: Accumulated EL up to a maximum of 45 days is encashed upon resignation, retirement, or separation based on the last drawn basic salary."
                ]
            },
            {
                "number": "6",
                "title": "Casual, Sick, and Wellness Leave Provisions",
                "content": [
                    {
                        "type": "subsection",
                        "number": "6.1",
                        "title": "Casual Leave (CL)",
                        "content": [
                            "CL quota is 8 working days per calendar year (adjusted from 10 days in v1.0 in exchange for Wellness Leave).",
                            "CL cannot exceed three (3) consecutive days. Unused CL lapses on 31 December."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "6.2",
                        "title": "Sick Leave (SL)",
                        "content": [
                            "SL quota is increased to 12 working days per calendar year (was 8 days in v1.0).",
                            "Medical Certificate Requirement: Under v2.0, a medical certificate is mandatory if sick leave exceeds two (2) consecutive working days (tightened from 3 days in v1.0)."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "6.3",
                        "title": "Wellness / Mental Health Leave (New in v2.0)",
                        "content": [
                            "Employees receive two (2) days of Wellness Leave per calendar year to prioritize mental rest, relaxation, or personal recharge.",
                            "No medical proof or detailed justification is required. Can be availed as individual days or paired with a weekend."
                        ]
                    }
                ]
            },
            {
                "number": "7",
                "title": "Special Leave Categories",
                "content": [
                    "- Maternity Leave: 26 weeks paid leave for up to two surviving children.",
                    "- Paternity Leave: 10 working days (increased from 5 days in v1.0), which can be availed within six (6) months of childbirth.",
                    "- Bereavement Leave: 5 working days (increased from 3 days in v1.0) for the bereavement of an immediate family member."
                ]
            },
            {
                "number": "8",
                "title": "Leave During Notice Period",
                "content": [
                    "Employees serving notice are prohibited from taking Casual Leave and Wellness Leave.",
                    "Earned Leave may only be approved under exceptional medical emergencies with prior written authorization from the Director of People Operations."
                ]
            },
            {
                "number": "9",
                "title": "Leave Approval Matrix",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Leave Type and Duration", "Primary Approver", "Secondary / Escalation Approver"],
                        "rows": [
                            ["Casual / Sick / Wellness (up to 3 days)", "Reporting Manager (Band L4+)", "Automated System Confirmation"],
                            ["Earned Leave (1 to 5 days)", "Reporting Manager (Band L4+)", "Department Lead"],
                            ["Earned Leave (6 to 15 days)", "Reporting Manager (Band L5+)", "Department Head / Director (Band L6)"],
                            ["Earned Leave (> 15 days)", "Director (Band L6)", "Head of People Operations"],
                            ["Annual EL Encashment Request", "Automated Payroll Validation", "Head of Total Rewards"]
                        ],
                        "widths": [180, 160, 164]
                    }
                ]
            },
            {
                "number": "10",
                "title": "Roles and Responsibilities",
                "content": [
                    "- Employee: Responsible for timely submission of leave requests via Darwinbox HRMS, planning EL requests at least two (2) weeks in advance, uploading mandatory medical certificates within two (2) days of returning from sick leave exceeding 2 days, and ensuring handover documentation.",
                    "- People Manager / Line Lead: Responsible for verifying project continuity, ensuring minimum on-call coverage, responding to leave applications within 48 hours, and monitoring team burnout and wellness leave utilization.",
                    "- People Operations & Total Rewards: Responsible for annual leave balance rollover audit on 31 December, administering the November annual EL encashment window, and managing maternity/paternity statutory leaves.",
                    "- Payroll Administration: Responsible for processing taxable encashment payouts in November payroll and calculating loss-of-pay deductions for unauthorized absences."
                ]
            },
            {
                "number": "11",
                "title": "Exceptions and Policy Deviations",
                "content": [
                    "- Critical Illness Balance Exemption: Employees requiring extended medical recovery beyond accrued SL and EL balances may apply for a Medical Grant of up to twenty (20) working days of advance sick leave, subject to approval from the Chief People Officer (CPO) and medical board review.",
                    "- Encashment Window Deviations: Out-of-cycle encashment requests outside the November window are strictly prohibited, except under documented critical family medical emergencies approved by the CFO.",
                    "- Notice Period Exceptions: Earned Leave during the contractual notice period is prohibited; exceptions may be granted exclusively by the Head of HR for terminal illness or immediate compassionate needs.",
                    "- Compliance Oversight: All policy exceptions are tracked in the HR Compliance Register and reviewed annually by the Executive Committee."
                ]
            },
            {
                "number": "12",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "What is the maximum Earned Leave carry-forward limit under Leave Policy v2.0?",
                        "a": "Under v2.0, employees can carry forward up to 45 days of Earned Leave into the subsequent calendar year, compared to 30 days under v1.0."
                    },
                    {
                        "type": "faq",
                        "q": "Can I encash Earned Leave while actively employed under v2.0?",
                        "a": "Yes. Version 2.0 introduced annual voluntary encashment of up to 10 days of EL during the November payroll window, provided a minimum balance of 15 days remains."
                    },
                    {
                        "type": "faq",
                        "q": "When is a medical certificate required for Sick Leave under v2.0?",
                        "a": "Under v2.0, a medical certificate is mandatory when Sick Leave exceeds two (2) consecutive working days. In v1.0, the threshold was three (3) consecutive days."
                    },
                    {
                        "type": "faq",
                        "q": "How many days of Paternity Leave are granted under v2.0?",
                        "a": "Fathers receive 10 working days of paid Paternity Leave under v2.0 (increased from 5 days in v1.0), usable within 6 months of childbirth."
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
                            ["1.0", "01 April 2025", "SUPERSEDED", "Baseline policy. 18 days EL, 30 days carry-forward, 8 days SL."],
                            ["2.0", "01 April 2026", "CURRENT", "Increased EL to 20 days, carry-forward to 45 days, SL to 12 days, paternity to 10 days; introduced annual EL encashment and Wellness Leave."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }
