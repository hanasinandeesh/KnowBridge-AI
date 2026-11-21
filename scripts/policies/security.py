"""
Information Security Policy (IT-SEC-001) and IT Acceptable Use Policy (IT-AUP-001)
for Northstar Technologies India Pvt. Ltd.
"""

def get_infosec_v1():
    return {
        "id": "IT-SEC-001",
        "title": "Information Security Policy",
        "category": "Information Technology & Cyber Governance",
        "department": "IT",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Chief Information Security Officer (CISO)",
        "approver": "Executive Committee & Chief Technology Officer (CTO)",
        "audience": "All employees, contractors, consultants, and third-party vendors accessing Northstar IT assets",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Administration",
                "content": [
                    "This document defines the overarching Information Security framework, access control mandates, incident response protocols, and data classification schemas for Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. Effective 01 April 2025, reviewed annually."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Objectives",
                "content": [
                    "To safeguard Northstar's intellectual property, proprietary software source code, customer enterprise data, and operational systems from unauthorized access, cyber threats, data exfiltration, and regulatory non-compliance."
                ]
            },
            {
                "number": "3",
                "title": "Scope and Applicability",
                "content": [
                    "Applies to all information systems, cloud infrastructure (AWS, Azure, GCP), corporate endpoints (laptops, mobile devices), networks, and data repositories owned or leased by Northstar.",
                    "Covers all full-time employees, contractors, interns, and vendors across Bengaluru, Hyderabad, Pune, and Chennai."
                ]
            },
            {
                "number": "4",
                "title": "Identity and Access Management (IAM)",
                "content": [
                    {
                        "type": "subsection",
                        "number": "4.1",
                        "title": "Password Complexity and Expiration",
                        "content": [
                            "All user account passwords must contain a minimum of fourteen (14) characters.",
                            "Must contain at least one uppercase letter, one lowercase letter, one numeric digit, and one special symbol (!@#$%^&*).",
                            "Passwords expire automatically every ninety (90) calendar days.",
                            "Password history remembers the last twelve (12) passwords; reuse of previous passwords is prevented by system policy."
                        ]
                    },
                    {
                        "type": "subsection",
                        "number": "4.2",
                        "title": "Multi-Factor Authentication (MFA)",
                        "content": [
                            "MFA is mandatory for all employee accounts accessing corporate email, VPN, ERP, source code repositories (GitLab/GitHub Enterprise), and cloud consoles.",
                            "Approved MFA methods include Okta Verify, Microsoft Authenticator push notifications, and FIDO2 hardware security keys. SMS-based OTP is prohibited as a primary factor."
                        ]
                    }
                ]
            },
            {
                "number": "5",
                "title": "Data Classification and Handling Framework",
                "content": [
                    "All organizational data must be categorized into one of four classification levels:",
                    {
                        "type": "table",
                        "headers": ["Classification Level", "Definition & Examples", "Access Control Mandate", "Storage & Transmission Rules"],
                        "rows": [
                            ["Public", "Information approved for public release (marketing brochures, whitepapers)", "Unrestricted access", "Standard corporate web hosting"],
                            ["Internal", "Routine business communications, employee directory, internal wikis", "Northstar employees and authenticated contractors", "Requires corporate login credentials"],
                            ["Confidential", "Financial statements, client contracts, architectural designs, pricing models", "Role-based need-to-know access", "Encrypted in transit (TLS 1.3) and at rest (AES-256)"],
                            ["Restricted", "Source code, customer production databases, PII, cryptographic keys", "Explicit CISO / VP approval required", "Strict encryption, DLP monitoring, zero USB download"]
                        ],
                        "widths": [90, 150, 130, 134]
                    }
                ]
            },
            {
                "number": "6",
                "title": "Endpoint Security and Clean Desk Mandates",
                "content": [
                    "- Disk Encryption: Full-disk encryption (BitLocker for Windows, FileVault for macOS) must be active at all times with corporate key escrow.",
                    "- Screen Auto-Lock: All workstations must automatically lock screens after five (5) minutes of user inactivity. Users must not disable screensavers or auto-lock timers.",
                    "- Removable Storage (USB): USB mass storage devices and flash drives are disabled by default across all laptops via Endpoint Privilege Management (EPM). Temporary USB write access requires formal business justification approved by the CISO.",
                    "- Clean Desk Policy: Sensitive documents, access badges, and confidential printouts must be locked in personal desk pedestals when leaving the workstation."
                ]
            },
            {
                "number": "7",
                "title": "Security Incident Reporting Procedures and SLAs",
                "content": [
                    "Employees must immediately report suspected security incidents (e.g., lost laptop, phishing click, malware alert, unauthorized data transfer) following standard incident response procedures to the Security Operations Center (SOC) at soc@northstar-tech.internal.",
                    {
                        "type": "table",
                        "headers": ["Severity Level", "Incident Example", "Reporting Deadline (SLA)", "Response SLA"],
                        "rows": [
                            ["Critical / Sev-1", "Ransomware detection, customer database leak, lost laptop with unencrypted data", "Within 1 hour of discovery", "Immediate (under 15 mins) SOC mobilization"],
                            ["High / Sev-2", "Targeted spear-phishing attack, compromised user credentials", "Within 2 hours of discovery", "Within 1 hour investigation"],
                            ["Medium / Sev-3", "Malware quarantined by EDR, suspicious port scan", "Within 4 hours of discovery", "Within 4 hours analysis"],
                            ["Low / Sev-4", "Minor spam campaign, misconfigured share without sensitive data", "Within 24 hours of discovery", "Next business day"]
                        ],
                        "widths": [100, 160, 120, 124]
                    }
                ]
            },
            {
                "number": "8",
                "title": "Phishing Simulations and Mandatory Training",
                "content": [
                    "- The InfoSec team conducts unannounced monthly simulated phishing campaigns across all departments.",
                    "- Employees who click on a simulated phishing link are automatically enrolled in a 15-minute micro-learning module.",
                    "- Employees who fail two (2) consecutive quarterly phishing simulations are required to attend a mandatory 2-hour instructor-led security remediation workshop within five (5) business days."
                ]
            },
            {
                "number": "9",
                "title": "Roles and Responsibilities",
                "content": [
                    "- All Users (Employees & Contractors): Responsible for safeguarding corporate authentication credentials, operating with MFA enabled, locking workstations upon leaving desks, maintaining clean desk hygiene, and promptly reporting suspicious emails or security anomalies.",
                    "- System Administrators & DevOps Engineers: Responsible for applying mandatory security patches within documented SLAs, enforcing role-based least-privilege access, configuring automated secret rotation, and maintaining encrypted backup archives.",
                    "- Security Operations Center (SOC) & Incident Responders: Responsible for 24/7 SIEM monitoring, threat hunting, executing containment protocols during Sev-1/Sev-2 incidents, conducting forensic root-cause analysis, and notifying regulatory bodies under CERT-In timelines.",
                    "- Chief Information Security Officer (CISO) & Corporate Governance: Responsible for establishing information security architecture, commissioning external penetration tests, overseeing ISO 27001/SOC 2 audits, and reporting cyber risk metrics to the Board."
                ]
            },
            {
                "number": "10",
                "title": "Information Security Exceptions and Risk Waivers",
                "content": [
                    "- Formal Risk Waiver Protocol: Deviations from security baselines (e.g. temporary port opening, legacy protocol usage, delay in patch deployment) require an electronic Risk Waiver Request logged in the GRC Portal.",
                    "- Risk Assessment & Compensating Controls: Every waiver must document an identified technical justification, business impact analysis, compensating security controls (e.g., enhanced logging, network isolation), and a rollback plan.",
                    "- Approval Matrix: Low/Medium risk waivers require CISO approval. High/Critical risk waivers require joint sign-off by the CISO and Chief Technology Officer (CTO).",
                    "- Maximum Validity & Expiration: Security waivers are granted for a maximum duration of ninety (90) calendar days. Unrenewed waivers expire automatically, triggering automated firewall rule revocation."
                ]
            },
            {
                "number": "11",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "What is the password requirement under Northstar Information Security Policy?",
                        "a": "Passwords must have a minimum of 14 characters, combine uppercase, lowercase, numbers, and symbols, expire every 90 days, and remember the previous 12 passwords."
                    },
                    {
                        "type": "faq",
                        "q": "What is the reporting deadline if an employee's corporate laptop is stolen or lost?",
                        "a": "Under Section 7, a lost or stolen laptop is classified as a Critical (Sev-1) incident and must be reported to the SOC (soc@northstar-tech.internal) within one (1) hour of discovery to trigger remote cryptographic wipe."
                    },
                    {
                        "type": "faq",
                        "q": "Can I connect my personal USB thumb drive to copy code or presentation slides?",
                        "a": "No. USB storage devices are blocked by default. Copying corporate data or source code to personal USB drives is strictly prohibited and constitutes a gross security violation."
                    },
                    {
                        "type": "faq",
                        "q": "What happens if I fail two consecutive simulated phishing tests?",
                        "a": "You must complete a mandatory 2-hour instructor-led security remediation workshop within 5 business days, and your manager will be formally notified."
                    }
                ]
            },
            {
                "number": "12",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "CURRENT", "Comprehensive enterprise Information Security policy establishing 14-character passwords, MFA, 4-tier data classification, and 1-hour critical incident SLA."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }


def get_acceptable_use_v1():
    return {
        "id": "IT-AUP-001",
        "title": "IT Acceptable Use Policy",
        "category": "Information Technology & Infrastructure",
        "department": "IT",
        "version": "1.0",
        "effective_date": "01 April 2025",
        "expiry_date": "31 March 2027",
        "status": "CURRENT",
        "owner": "Head of IT Infrastructure & Cloud Services",
        "approver": "Chief Technology Officer (CTO) & CISO",
        "audience": "All users of Northstar digital hardware, networks, cloud workspaces, and email systems",
        "sections": [
            {
                "number": "1",
                "title": "Document Control and Introduction",
                "content": [
                    "This policy defines the acceptable, responsible, and secure use of all Information Technology (IT) assets, computer equipment, network resources, internet access, and communication channels provided by Northstar Technologies India Pvt. Ltd. ('Northstar').",
                    "Status: CURRENT. Effective 01 April 2025, reviewed every two years."
                ]
            },
            {
                "number": "2",
                "title": "Purpose and Scope",
                "content": [
                    "- Policy Purpose: To ensure corporate computing assets and digital resources are used productively, ethically, and securely, preventing cybersecurity breaches, data theft, and legal liability while providing a reliable digital workplace.",
                    "- Scope and Applicability: Applies to all permanent full-time employees, contractors, consultants, interns, and third-party vendor personnel accessing Northstar networks, cloud systems, and company-issued hardware across Bengaluru, Hyderabad, Pune, and Chennai.",
                    "- Systems Covered: All enterprise laptops, workstations, mobile devices, corporate email, Slack/Teams workspaces, VPNs, internal code repositories (GitLab/GitHub Enterprise), and cloud services."
                ]
            },
            {
                "number": "3",
                "title": "Ownership of Computing Resources and Data",
                "content": [
                    "All computing equipment (laptops, desktops, monitors, peripherals), software licenses, network bandwidth, corporate email accounts (name@northstar-tech.internal), collaboration channels (Slack, Microsoft Teams), and data stored thereon remain the exclusive property of Northstar.",
                    "Employees have no expectation of personal privacy regarding any communications, files, or internet traffic transmitted across or stored on corporate assets."
                ]
            },
            {
                "number": "4",
                "title": "Acceptable Personal Use Clause",
                "content": [
                    "Northstar recognizes that employees may occasionally need to attend to urgent personal matters during business hours.",
                    "Incidental, reasonable personal use of company laptops and internet (e.g., brief personal email checking, reading news, online banking) is permitted provided it:",
                    "- Occurs during designated rest breaks or outside core working hours.",
                    "- Does not consume excessive network bandwidth (e.g., video streaming, gaming).",
                    "- Does not interfere with job productivity or team obligations.",
                    "- Does not involve commercial side ventures, freelancing, or secondary employment.",
                    "- Does not violate any provisions of the Code of Conduct or InfoSec Policy."
                ]
            },
            {
                "number": "5",
                "title": "Strictly Prohibited Activities",
                "content": [
                    "Users are strictly prohibited from engaging in the following actions using Northstar assets or networks:",
                    "- Accessing, downloading, storing, or transmitting pornographic, sexually explicit, obscene, racist, or defamatory material.",
                    "- Peer-to-peer (P2P) file sharing, torrenting, or downloading pirated software, movies, music, or media.",
                    "- Engaging in unauthorized cryptocurrency mining or distributed ledger computation.",
                    "- Running network sniffing, port scanning, password cracking, or penetration testing tools without written CISO authorization.",
                    "- Jailbreaking, rooting, or disabling operating system security controls, antivirus, or Mobile Device Management (MDM) agents.",
                    "- Disclosing company intellectual property, customer data, or internal source code on public forums, pastebins, or unapproved AI platforms."
                ]
            },
            {
                "number": "6",
                "title": "Software Installation and Administrative Privileges",
                "content": [
                    "- Standard User Rights: By default, standard employee accounts do not possess local administrative privileges on corporate laptops.",
                    "- Software Requests: Employees requiring specific engineering tools, libraries, or development software not available in the Northstar Software Center must submit an IT Jira Service Management request.",
                    "- Unauthorized Software: Downloading or installing unlicensed, open-source with restrictive licenses (e.g., AGPL in proprietary client code), or unauthorized freeware is strictly forbidden."
                ]
            },
            {
                "number": "7",
                "title": "Network and Activity Monitoring Disclosure",
                "content": [
                    "To ensure regulatory compliance, protect intellectual property, and defend against cyber attacks, Northstar actively monitors and logs:",
                    "- Web browsing activity, URLs visited, and categorized web filtering blocks.",
                    "- Inbound and outbound email communications, attachments, and data transfer volumes.",
                    "- Endpoint telemetry, installed processes, CPU utilization, and software installations.",
                    "- Authentication attempts, VPN connections, and geo-location access points.",
                    "Monitoring is conducted in compliance with applicable Indian laws (Information Technology Act, 2000, and SPDI Rules)."
                ]
            },
            {
                "number": "8",
                "title": "Procedures and Hardware Lifecycle Workflows",
                "content": [
                    "- Hardware Requisition: Requisitions for replacement laptops, additional monitors, or specialized peripherals must be initiated via Jira Service Management with Line Manager approval.",
                    "- Lost or Damaged Hardware Protocol: In the event of lost, stolen, or damaged assets, the user must notify it-helpdesk@northstar-tech.internal within two (2) hours to trigger remote locking. For stolen devices, a police First Information Report (FIR) must be filed within 24 hours.",
                    "- Mandatory Asset Return on Separation: On the employee's final working day, all issued hardware, chargers, security keys, and access badges must be surrendered to the IT Facility Desk before final exit clearance is signed off."
                ]
            },
            {
                "number": "9",
                "title": "Roles and Responsibilities",
                "content": [
                    "- End-User / Employee: Responsible for exercising due care with assigned digital hardware, adhering to software installation restrictions, operating under secure VPN when remote, and maintaining workstation confidentiality.",
                    "- Reporting Manager / Supervisor: Responsible for reviewing software entitlement requests, monitoring employee adherence to acceptable use standards, and validating equipment requirements during onboarding and offboarding.",
                    "- IT Service Desk & Infrastructure Operations: Responsible for provisioning standardized system images, managing automated software patch distribution, executing timely hardware repairs within 48 hours, and maintaining asset inventory.",
                    "- CISO & Corporate Security: Responsible for defining network access rules, conducting audit telemetry reviews, and investigating acceptable use policy violations."
                ]
            },
            {
                "number": "10",
                "title": "Policy Exceptions and Access Waivers",
                "content": [
                    "- Temporary Local Admin Exemption: Developers requiring temporary local administrative access for kernel debugging or system tool builds may request a Time-Bound Admin Waiver (maximum 30 days) via Jira Service Management, subject to approval from the Engineering Director and CISO.",
                    "- USB Read/Write Access Waiver: Permanent USB port blocking may only be bypassed for specialized testing labs through a written sole-purpose waiver signed by the IT Infrastructure Head.",
                    "- AI Tool Usage Exception: Utilizing commercial generative AI platforms with corporate source code requires a Formal Enterprise AI License and written authorization from the CISO.",
                    "- Exception Log & Revocation: All granted exceptions are logged in the Central Access Register and subject to immediate revocation upon security advisory."
                ]
            },
            {
                "number": "11",
                "title": "Frequently Asked Questions",
                "content": [
                    {
                        "type": "faq",
                        "q": "Can I install personal software or games on my Northstar laptop?",
                        "a": "No. Employees do not have local administrative privileges, and installing personal games, torrent clients, or unauthorized applications is strictly prohibited."
                    },
                    {
                        "type": "faq",
                        "q": "Does Northstar monitor my internet browsing on company laptops?",
                        "a": "Yes. Corporate laptops route traffic through corporate proxies and endpoint monitoring tools. All web activity and data transfers are logged for cybersecurity compliance."
                    },
                    {
                        "type": "faq",
                        "q": "How quickly must I report a lost company laptop?",
                        "a": "You must report a lost or stolen laptop to it-helpdesk@northstar-tech.internal within two (2) hours of discovering the loss."
                    },
                    {
                        "type": "faq",
                        "q": "Can I use my company laptop to do freelance software projects in the evening?",
                        "a": "No. Using corporate equipment for commercial side ventures or freelancing is strictly prohibited and constitutes grounds for termination under the Code of Conduct."
                    }
                ]
            },
            {
                "number": "12",
                "title": "Revision History",
                "content": [
                    {
                        "type": "table",
                        "headers": ["Version", "Effective Date", "Status", "Summary of Primary Changes"],
                        "rows": [
                            ["1.0", "01 April 2025", "CURRENT", "Baseline IT Acceptable Use Policy covering hardware ownership, prohibited activities, software installation, and monitoring disclosure."]
                        ],
                        "widths": [60, 90, 90, 264]
                    }
                ]
            }
        ]
    }
