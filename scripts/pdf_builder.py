"""
PDF Generator module for KnowBridge AI Synthetic Enterprise Policies.
Uses ReportLab to produce professional corporate policy PDFs with:
- Multi-page NumberedCanvas ('Page X of Y')
- Running headers and footers with company name, policy ID, version
- Prominent synthetic sample disclaimer banner
- Styled document metadata control tables
- Professional typography, callouts, section hierarchy, and approval matrices
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.pdfgen import canvas

# Corporate Color Palette
NAVY_PRIMARY = colors.HexColor("#0F2942")     # Deep Corporate Navy
BLUE_SECONDARY = colors.HexColor("#1E5F8A")   # Steel Blue Accent
SLATE_DARK = colors.HexColor("#2D3748")       # Body Text Slate
SLATE_LIGHT = colors.HexColor("#718096")      # Muted Subtext
BORDER_COLOR = colors.HexColor("#CBD5E0")     # Subtle Table/Line Borders
BG_LIGHT = colors.HexColor("#F7FAFC")         # Table Row Tint
HEADER_BG = colors.HexColor("#EBF8FF")        # Table Header Tint
BANNER_BG = colors.HexColor("#FFF5F5")        # Disclaimer Banner Light Red
BANNER_BORDER = colors.HexColor("#FEB2B2")    # Disclaimer Border
BANNER_TEXT = colors.HexColor("#9B2C2C")      # Disclaimer Deep Crimson
SUPERSEDED_BG = colors.HexColor("#FFF0EB")    # Amber/Orange warning background
SUPERSEDED_BORDER = colors.HexColor("#FBD38D")
SUPERSEDED_TEXT = colors.HexColor("#C05621")


class PolicyNumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas that writes dynamic total page count ('Page X of Y')
    and running headers and footers across all pages.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self.doc_id = "POL-000"
        self.doc_version = "1.0"
        self.doc_title = "Enterprise Policy"
        self.doc_status = "CURRENT"

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        
        # 1. Running Header (on all pages)
        self.setFont("Helvetica-Bold", 7.5)
        self.setFillColor(NAVY_PRIMARY)
        self.drawString(54, 755, "Northstar Technologies India Pvt. Ltd. | Enterprise Policy Repository")
        
        self.setFont("Helvetica", 7.5)
        self.setFillColor(SLATE_LIGHT)
        status_suffix = " [SUPERSEDED]" if "SUPERSEDED" in self.doc_status.upper() else ""
        self.drawRightString(612 - 54, 755, f"{self.doc_id} v{self.doc_version}{status_suffix}")
        
        self.setStrokeColor(BORDER_COLOR)
        self.setLineWidth(0.6)
        self.line(54, 747, 612 - 54, 747)

        # 2. Running Footer (on all pages)
        self.line(54, 45, 612 - 54, 45)
        self.setFont("Helvetica-Bold", 6.5)
        self.setFillColor(BANNER_TEXT)
        self.drawString(54, 33, "SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY")
        
        self.setFont("Helvetica", 7.5)
        self.setFillColor(SLATE_LIGHT)
        self.drawRightString(612 - 54, 33, f"Page {self._pageNumber} of {page_count}")
        
        self.restoreState()


def get_policy_styles():
    """Build and return custom typography styles for policy documents."""
    base_styles = getSampleStyleSheet()
    
    styles = {
        'DocTitle': ParagraphStyle(
            'PolicyDocTitle',
            parent=base_styles['Title'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=22,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
            spaceAfter=4,
        ),
        'DocSubtitle': ParagraphStyle(
            'PolicyDocSubtitle',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=SLATE_LIGHT,
            alignment=TA_LEFT,
            spaceAfter=10,
        ),
        'DisclaimerBanner': ParagraphStyle(
            'PolicyDisclaimerBanner',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=11,
            textColor=BANNER_TEXT,
            alignment=TA_CENTER,
        ),
        'StatusAlert': ParagraphStyle(
            'PolicyStatusAlert',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=SUPERSEDED_TEXT,
            alignment=TA_LEFT,
        ),
        'Heading1': ParagraphStyle(
            'PolicyHeading1',
            parent=base_styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=NAVY_PRIMARY,
            spaceBefore=12,
            spaceAfter=6,
            keepWithNext=True,
        ),
        'Heading2': ParagraphStyle(
            'PolicyHeading2',
            parent=base_styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=BLUE_SECONDARY,
            spaceBefore=9,
            spaceAfter=4,
            keepWithNext=True,
        ),
        'Heading3': ParagraphStyle(
            'PolicyHeading3',
            parent=base_styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=9,
            leading=13,
            textColor=SLATE_DARK,
            spaceBefore=6,
            spaceAfter=3,
            keepWithNext=True,
        ),
        'Body': ParagraphStyle(
            'PolicyBody',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=SLATE_DARK,
            alignment=TA_JUSTIFY,
            spaceAfter=5,
        ),
        'Bullet': ParagraphStyle(
            'PolicyBullet',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=SLATE_DARK,
            leftIndent=14,
            spaceAfter=3,
        ),
        'TableHeader': ParagraphStyle(
            'PolicyTableHeader',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8,
            leading=10,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
        ),
        'TableCell': ParagraphStyle(
            'PolicyTableCell',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=7.5,
            leading=10,
            textColor=SLATE_DARK,
            alignment=TA_LEFT,
        ),
        'TableCellBold': ParagraphStyle(
            'PolicyTableCellBold',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=10,
            textColor=NAVY_PRIMARY,
            alignment=TA_LEFT,
        ),
        'FAQQuestion': ParagraphStyle(
            'PolicyFAQQuestion',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=8.5,
            leading=12,
            textColor=BLUE_SECONDARY,
            spaceBefore=6,
            spaceAfter=2,
            keepWithNext=True,
        ),
        'FAQAnswer': ParagraphStyle(
            'PolicyFAQAnswer',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=8.5,
            leading=12,
            textColor=SLATE_DARK,
            leftIndent=10,
            spaceAfter=6,
        ),
    }
    return styles


def build_pdf_document(filepath, policy_data):
    """
    Constructs a complete, professional corporate PDF document from structured policy data.
    """
    doc = SimpleDocTemplate(
        filepath,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )
    
    styles = get_policy_styles()
    story = []
    
    # Custom Canvas Class closure to bind metadata
    class ConfiguredCanvas(PolicyNumberedCanvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.doc_id = policy_data.get("id", "HR-POL-001")
            self.doc_version = policy_data.get("version", "1.0")
            self.doc_title = policy_data.get("title", "Corporate Policy")
            self.doc_status = policy_data.get("status", "CURRENT")

    # 1. Prominent Synthetic Sample Banner at top of page 1
    banner_text = (
        "<b>SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY</b><br/>"
        "<i>Created exclusively for benchmarking and evaluating KnowBridge AI enterprise RAG. "
        "All parameters, amounts, and rules are synthetic.</i>"
    )
    banner_table = Table(
        [[Paragraph(banner_text, styles['DisclaimerBanner'])]],
        colWidths=[504]
    )
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BANNER_BG),
        ('BOX', (0, 0), (-1, -1), 0.8, BANNER_BORDER),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    story.append(banner_table)
    story.append(Spacer(1, 10))

    # 2. Company & Document Title Header Block
    story.append(Paragraph("Northstar Technologies India Pvt. Ltd.", styles['DocSubtitle']))
    story.append(Paragraph(f"{policy_data['id']}: {policy_data['title']}", styles['DocTitle']))
    
    status_str = policy_data.get("status", "CURRENT").upper()
    subtitle_meta = (
        f"<b>Category:</b> {policy_data.get('category', 'Corporate Policy')} &nbsp;|&nbsp; "
        f"<b>Version:</b> {policy_data.get('version', '1.0')} &nbsp;|&nbsp; "
        f"<b>Status:</b> {status_str} &nbsp;|&nbsp; "
        f"<b>Effective Date:</b> {policy_data.get('effective_date', '01 April 2025')}"
    )
    story.append(Paragraph(subtitle_meta, styles['DocSubtitle']))
    story.append(Spacer(1, 4))

    # 3. Status Alert Callout Box (if Superseded)
    if "SUPERSEDED" in status_str:
        doc_id = policy_data.get("id", "")
        if "TRV" in doc_id:
            domain_activity = "Official business travel bookings, travel advances, and expense reimbursement claims"
        elif "LVE" in doc_id:
            domain_activity = "Leave applications, absence records, and leave accrual balances"
        elif "WFH" in doc_id:
            domain_activity = "Remote and hybrid work schedules, equipment reimbursements, and broadband allowances"
        else:
            domain_activity = "Operational activities, expense claims, or employee requests"

        alert_text = (
            f"<b>DOCUMENT STATUS NOTICE — SUPERSEDED:</b> This version ({policy_data.get('version', '1.0')}) "
            f"was superseded on <b>{policy_data.get('expiry_date', '31 March 2026')}</b> by Version 2.0. "
            f"{domain_activity} initiated prior to 01 April 2026 remain auditable under this document. "
            f"For activities on or after 01 April 2026, refer strictly to Version 2.0."
        )
        alert_table = Table(
            [[Paragraph(alert_text, styles['StatusAlert'])]],
            colWidths=[504]
        )
        alert_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), SUPERSEDED_BG),
            ('BOX', (0, 0), (-1, -1), 0.8, SUPERSEDED_BORDER),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(alert_table)
        story.append(Spacer(1, 8))

    # 4. Document Control Block (Metadata Table)
    meta_rows = [
        [
            Paragraph("<b>Document ID:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("id", ""), styles['TableCell']),
            Paragraph("<b>Version:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("version", ""), styles['TableCell']),
        ],
        [
            Paragraph("<b>Document Owner:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("owner", ""), styles['TableCell']),
            Paragraph("<b>Approving Authority:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("approver", ""), styles['TableCell']),
        ],
        [
            Paragraph("<b>Effective Date:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("effective_date", ""), styles['TableCell']),
            Paragraph("<b>Review / Expiry:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("expiry_date", "31 March 2027"), styles['TableCell']),
        ],
        [
            Paragraph("<b>Jurisdiction:</b>", styles['TableCellBold']),
            Paragraph("India (Bengaluru HQ, Hyderabad, Pune, Chennai)", styles['TableCell']),
            Paragraph("<b>Classification:</b>", styles['TableCellBold']),
            Paragraph("Internal Corporate Policy — Enterprise Restricted", styles['TableCell']),
        ],
        [
            Paragraph("<b>Applicable Audience:</b>", styles['TableCellBold']),
            Paragraph(policy_data.get("audience", "All Northstar Employees"), styles['TableCell']),
            Paragraph("<b>Status:</b>", styles['TableCellBold']),
            Paragraph(f"<b>{status_str}</b>", styles['TableCellBold']),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[100, 152, 110, 142])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), BG_LIGHT),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 5. Render All Document Sections
    for section in policy_data.get("sections", []):
        sec_num = section.get("number", "")
        sec_title = section.get("title", "")
        story.append(Paragraph(f"{sec_num}. {sec_title}", styles['Heading1']))
        
        # Render Paragraphs / Content Elements
        for item in section.get("content", []):
            if isinstance(item, str):
                if item.startswith("- "):
                    story.append(Paragraph(f"&bull; {item[2:]}", styles['Bullet']))
                else:
                    story.append(Paragraph(item, styles['Body']))
            elif isinstance(item, dict):
                # Subsections, Tables, or FAQs
                item_type = item.get("type", "")
                if item_type == "subsection":
                    sub_num = item.get("number", "")
                    sub_title = item.get("title", "")
                    story.append(Paragraph(f"{sub_num} {sub_title}", styles['Heading2']))
                    for sub_text in item.get("content", []):
                        if sub_text.startswith("- "):
                            story.append(Paragraph(f"&bull; {sub_text[2:]}", styles['Bullet']))
                        else:
                            story.append(Paragraph(sub_text, styles['Body']))
                elif item_type == "table":
                    tbl_headers = item.get("headers", [])
                    tbl_rows = item.get("rows", [])
                    col_widths = item.get("widths", None)
                    
                    # Convert headers and rows to Paragraphs
                    formatted_data = [[Paragraph(h, styles['TableHeader']) for h in tbl_headers]]
                    for row in tbl_rows:
                        formatted_data.append([Paragraph(cell, styles['TableCell']) for cell in row])
                    
                    t = Table(formatted_data, colWidths=col_widths)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), HEADER_BG),
                        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (-1, -1), 5),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ]))
                    story.append(Spacer(1, 3))
                    story.append(t)
                    story.append(Spacer(1, 5))
                elif item_type == "faq":
                    q = item.get("q", "")
                    a = item.get("a", "")
                    story.append(Paragraph(f"<b>Q: {q}</b>", styles['FAQQuestion']))
                    story.append(Paragraph(f"A: {a}", styles['FAQAnswer']))

        story.append(Spacer(1, 4))

    # Build Document
    doc.build(story, canvasmaker=ConfiguredCanvas)
    return filepath
