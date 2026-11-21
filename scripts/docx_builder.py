"""
DOCX Generator module for KnowBridge AI Synthetic Enterprise Policies.
Uses python-docx to produce professional editable Word documents with:
- Standard corporate document hierarchy and metadata tables
- Prominent synthetic sample disclaimer banner
- Styled tables with shaded headers and subtle grid borders
- Professional typography, numbered sections, bullets, and FAQs
"""

import docx
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml

# Colors
NAVY = RGBColor(15, 41, 66)        # #0F2942
BLUE = RGBColor(30, 95, 138)       # #1E5F8A
SLATE = RGBColor(45, 55, 72)       # #2D3748
MUTED = RGBColor(113, 128, 150)    # #718096
CRIMSON = RGBColor(155, 44, 44)    # #9B2C2C


def set_cell_background(cell, hex_color):
    """Sets background shading of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{hex_color}"/>')
    tcPr.append(shd)


def set_cell_margins(cell, top=80, bottom=80, left=120, right=120):
    """Sets internal margins (padding) of a table cell."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)


def build_docx_document(filepath, policy_data):
    """
    Constructs a complete, professional corporate DOCX document from structured policy data.
    """
    doc = Document()
    
    # 1. Page Margins (1 inch all around)
    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)
        
        # Header & Footer
        header = section.header
        hp = header.paragraphs[0]
        hp.text = f"Northstar Technologies India Pvt. Ltd. | {policy_data.get('id', '')} v{policy_data.get('version', '')}"
        hp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        hp.runs[0].font.size = Pt(8)
        hp.runs[0].font.color.rgb = MUTED
        
        footer = section.footer
        fp = footer.paragraphs[0]
        fp.text = "SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY"
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        fp.runs[0].font.size = Pt(7.5)
        fp.runs[0].font.bold = True
        fp.runs[0].font.color.rgb = CRIMSON

    # 2. Prominent Disclaimer Callout Box
    disclaimer_table = doc.add_table(rows=1, cols=1)
    disclaimer_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    d_cell = disclaimer_table.cell(0, 0)
    set_cell_background(d_cell, "FFF5F5")
    set_cell_margins(d_cell, top=100, bottom=100, left=150, right=150)
    
    dp = d_cell.paragraphs[0]
    dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d_run = dp.add_run("SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY\n")
    d_run.bold = True
    d_run.font.size = Pt(8.5)
    d_run.font.color.rgb = CRIMSON
    
    d_sub = dp.add_run(
        "This document is a synthetic artifact created solely for testing, evaluating, and demonstrating "
        "the KnowBridge AI enterprise RAG platform. All operational parameters, limits, and entities are fictional."
    )
    d_sub.italic = True
    d_sub.font.size = Pt(7.5)
    d_sub.font.color.rgb = CRIMSON

    doc.add_paragraph()  # Spacing

    # 3. Document Title & Subtitle
    p_comp = doc.add_paragraph()
    r_comp = p_comp.add_run("Northstar Technologies India Pvt. Ltd.")
    r_comp.font.size = Pt(11)
    r_comp.font.color.rgb = MUTED
    p_comp.paragraph_format.space_after = Pt(2)

    p_title = doc.add_paragraph()
    r_title = p_title.add_run(f"{policy_data['id']}: {policy_data['title']}")
    r_title.bold = True
    r_title.font.size = Pt(18)
    r_title.font.color.rgb = NAVY
    p_title.paragraph_format.space_after = Pt(4)

    p_meta = doc.add_paragraph()
    r_meta = p_meta.add_run(
        f"Category: {policy_data.get('category', 'Corporate Policy')}  |  "
        f"Version: {policy_data.get('version', '1.0')}  |  "
        f"Status: {policy_data.get('status', 'CURRENT')}  |  "
        f"Effective Date: {policy_data.get('effective_date', '01 April 2025')}"
    )
    r_meta.font.size = Pt(9.5)
    r_meta.font.color.rgb = MUTED
    p_meta.paragraph_format.space_after = Pt(10)

    # 4. Status Warning if Superseded
    status_str = policy_data.get("status", "CURRENT").upper()
    if "SUPERSEDED" in status_str:
        s_table = doc.add_table(rows=1, cols=1)
        s_table.alignment = WD_TABLE_ALIGNMENT.CENTER
        s_cell = s_table.cell(0, 0)
        set_cell_background(s_cell, "FFF0EB")
        set_cell_margins(s_cell, top=80, bottom=80, left=140, right=140)
        sp = s_cell.paragraphs[0]
        s_run = sp.add_run(
            f"DOCUMENT STATUS NOTICE — SUPERSEDED: This policy version was superseded on "
            f"{policy_data.get('expiry_date', '31 March 2026')} by Version 2.0. "
            f"Prior business operations remain auditable under this document; active guidelines require Version 2.0."
        )
        s_run.bold = True
        s_run.font.size = Pt(8.5)
        s_run.font.color.rgb = RGBColor(192, 86, 33)
        doc.add_paragraph()

    # 5. Document Control Metadata Table
    meta_rows = [
        ("Document ID", policy_data.get("id", ""), "Version", policy_data.get("version", "")),
        ("Document Owner", policy_data.get("owner", ""), "Approving Authority", policy_data.get("approver", "")),
        ("Effective Date", policy_data.get("effective_date", ""), "Review / Expiry", policy_data.get("expiry_date", "31 March 2027")),
        ("Jurisdiction", "India (Bengaluru, Hyderabad, Pune, Chennai)", "Classification", "Internal Corporate Policy — Restricted"),
        ("Applicable Audience", policy_data.get("audience", "All Employees"), "Document Status", status_str),
    ]
    
    tbl = doc.add_table(rows=len(meta_rows), cols=4)
    tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
    for r_idx, (k1, v1, k2, v2) in enumerate(meta_rows):
        row = tbl.rows[r_idx]
        
        c0, c1, c2, c3 = row.cells[0], row.cells[1], row.cells[2], row.cells[3]
        set_cell_background(c0, "F7FAFC")
        set_cell_background(c2, "F7FAFC")
        for c in (c0, c1, c2, c3):
            set_cell_margins(c, top=50, bottom=50, left=80, right=80)
            
        p = c0.paragraphs[0]
        r = p.add_run(k1)
        r.bold = True
        r.font.size = Pt(8)
        r.font.color.rgb = NAVY
        
        p = c1.paragraphs[0]
        r = p.add_run(v1)
        r.font.size = Pt(8)
        r.font.color.rgb = SLATE
        
        p = c2.paragraphs[0]
        r = p.add_run(k2)
        r.bold = True
        r.font.size = Pt(8)
        r.font.color.rgb = NAVY
        
        p = c3.paragraphs[0]
        r = p.add_run(v2)
        r.font.size = Pt(8)
        r.font.color.rgb = SLATE

    doc.add_paragraph()  # Spacing

    # 6. Render Document Sections
    for section in policy_data.get("sections", []):
        sec_num = section.get("number", "")
        sec_title = section.get("title", "")
        
        # Heading 1
        h1 = doc.add_paragraph()
        r_h1 = h1.add_run(f"{sec_num}. {sec_title}")
        r_h1.bold = True
        r_h1.font.size = Pt(13)
        r_h1.font.color.rgb = NAVY
        h1.paragraph_format.space_before = Pt(12)
        h1.paragraph_format.space_after = Pt(4)
        h1.paragraph_format.keep_with_next = True

        for item in section.get("content", []):
            if isinstance(item, str):
                p = doc.add_paragraph()
                if item.startswith("- "):
                    p.paragraph_format.left_indent = Inches(0.25)
                    r = p.add_run(f"• {item[2:]}")
                else:
                    r = p.add_run(item)
                r.font.size = Pt(9.5)
                r.font.color.rgb = SLATE
                p.paragraph_format.space_after = Pt(4)
                
            elif isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "subsection":
                    sub_num = item.get("number", "")
                    sub_title = item.get("title", "")
                    h2 = doc.add_paragraph()
                    r_h2 = h2.add_run(f"{sub_num} {sub_title}")
                    r_h2.bold = True
                    r_h2.font.size = Pt(11)
                    r_h2.font.color.rgb = BLUE
                    h2.paragraph_format.space_before = Pt(8)
                    h2.paragraph_format.space_after = Pt(3)
                    h2.paragraph_format.keep_with_next = True
                    
                    for sub_text in item.get("content", []):
                        p = doc.add_paragraph()
                        if sub_text.startswith("- "):
                            p.paragraph_format.left_indent = Inches(0.25)
                            r = p.add_run(f"• {sub_text[2:]}")
                        else:
                            r = p.add_run(sub_text)
                        r.font.size = Pt(9.5)
                        r.font.color.rgb = SLATE
                        p.paragraph_format.space_after = Pt(3)
                        
                elif item_type == "table":
                    tbl_headers = item.get("headers", [])
                    tbl_rows = item.get("rows", [])
                    t = doc.add_table(rows=len(tbl_rows) + 1, cols=len(tbl_headers))
                    t.alignment = WD_TABLE_ALIGNMENT.CENTER
                    
                    # Header row
                    hdr_cells = t.rows[0].cells
                    for idx, header_text in enumerate(tbl_headers):
                        cell = hdr_cells[idx]
                        set_cell_background(cell, "EBF8FF")
                        set_cell_margins(cell, top=60, bottom=60, left=80, right=80)
                        p = cell.paragraphs[0]
                        r = p.add_run(header_text)
                        r.bold = True
                        r.font.size = Pt(8.5)
                        r.font.color.rgb = NAVY
                        
                    # Body rows
                    for r_idx, row_data in enumerate(tbl_rows):
                        row_cells = t.rows[r_idx + 1].cells
                        for c_idx, cell_value in enumerate(row_data):
                            cell = row_cells[c_idx]
                            set_cell_margins(cell, top=50, bottom=50, left=80, right=80)
                            p = cell.paragraphs[0]
                            r = p.add_run(cell_value)
                            r.font.size = Pt(8)
                            r.font.color.rgb = SLATE
                    doc.add_paragraph()  # Spacing
                    
                elif item_type == "faq":
                    q = item.get("q", "")
                    a = item.get("a", "")
                    p_q = doc.add_paragraph()
                    r_q = p_q.add_run(f"Q: {q}")
                    r_q.bold = True
                    r_q.font.size = Pt(9.5)
                    r_q.font.color.rgb = BLUE
                    p_q.paragraph_format.space_before = Pt(6)
                    p_q.paragraph_format.space_after = Pt(2)
                    p_q.paragraph_format.keep_with_next = True
                    
                    p_a = doc.add_paragraph()
                    p_a.paragraph_format.left_indent = Inches(0.2)
                    r_a = p_a.add_run(f"A: {a}")
                    r_a.font.size = Pt(9)
                    r_a.font.color.rgb = SLATE
                    p_a.paragraph_format.space_after = Pt(5)

    doc.save(filepath)
    return filepath
