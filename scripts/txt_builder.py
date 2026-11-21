"""
Plain Text (TXT) Generator module for KnowBridge AI Synthetic Enterprise Policies.
Produces clean, structured UTF-8 plain text documents with:
- Prominent synthetic sample disclaimer banner
- Standard ASCII document control headers
- Clean hierarchical section numbering (1.0, 1.1, etc.)
- Clear textual representations of tables and approval matrices
- Readable bullet points and FAQ structures (without raw markdown pipe tables)
"""

def format_table_as_text(headers, rows):
    """Formats a table into clean, indented plain text columns or key-value entries."""
    lines = []
    # Determine column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for idx, val in enumerate(row):
            if idx < len(col_widths):
                col_widths[idx] = max(col_widths[idx], len(str(val)))
            else:
                col_widths.append(len(str(val)))
    
    # Header line
    header_str = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    sep_str = "  ".join("-" * col_widths[i] for i in range(len(headers)))
    lines.append(header_str)
    lines.append(sep_str)
    
    # Rows
    for row in rows:
        row_str = "  ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
        lines.append(row_str)
        
    return "\n".join("    " + l for l in lines)


def build_txt_document(filepath, policy_data):
    """
    Constructs a complete, professional corporate TXT document from structured policy data.
    """
    lines = []
    
    # 1. Prominent Synthetic Sample Banner
    lines.append("=" * 80)
    lines.append("SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY")
    lines.append("This document is a synthetic artifact created solely for testing, evaluating,")
    lines.append("and benchmarking the KnowBridge AI enterprise RAG platform.")
    lines.append("All operational rules, numerical thresholds, names, and entities are fictional.")
    lines.append("=" * 80)
    lines.append("")

    # 2. Document Header Block
    lines.append("NORTHSTAR TECHNOLOGIES INDIA PVT. LTD.")
    lines.append(f"DOCUMENT ID:    {policy_data.get('id', '')}")
    lines.append(f"POLICY TITLE:   {policy_data.get('title', '').upper()}")
    lines.append(f"VERSION:        {policy_data.get('version', '1.0')}")
    lines.append(f"DOCUMENT STATUS:{policy_data.get('status', 'CURRENT').upper()}")
    lines.append(f"EFFECTIVE DATE: {policy_data.get('effective_date', '01 April 2025')}")
    lines.append(f"REVIEW DATE:    {policy_data.get('expiry_date', '31 March 2027')}")
    lines.append(f"POLICY OWNER:   {policy_data.get('owner', '')}")
    lines.append(f"APPROVING AUTH: {policy_data.get('approver', '')}")
    lines.append(f"CLASSIFICATION: Internal Corporate Policy — Restricted")
    lines.append(f"TARGET AUDIENCE:{policy_data.get('audience', 'All Employees')}")
    lines.append("-" * 80)
    lines.append("")

    # 3. Status Alert if Superseded
    status_str = policy_data.get("status", "CURRENT").upper()
    if "SUPERSEDED" in status_str:
        lines.append("[!] DOCUMENT STATUS NOTICE — SUPERSEDED:")
        lines.append(f"    This policy version ({policy_data.get('version', '1.0')}) was superseded on")
        lines.append(f"    {policy_data.get('expiry_date', '31 March 2026')} by Version 2.0.")
        lines.append(f"    Operations initiated prior to 01 April 2026 follow this version.")
        lines.append(f"    Operations initiated on or after 01 April 2026 follow Version 2.0.")
        lines.append("-" * 80)
        lines.append("")

    # 4. Render Document Sections
    for section in policy_data.get("sections", []):
        sec_num = section.get("number", "")
        sec_title = section.get("title", "")
        
        lines.append(f"{sec_num}.0 {sec_title.upper()}")
        lines.append("-" * (len(f"{sec_num}.0 {sec_title.upper()}")))
        lines.append("")

        for item in section.get("content", []):
            if isinstance(item, str):
                if item.startswith("- "):
                    lines.append(f"  * {item[2:]}")
                else:
                    lines.append(f"  {item}")
                lines.append("")
            elif isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type == "subsection":
                    sub_num = item.get("number", "")
                    sub_title = item.get("title", "")
                    lines.append(f"  {sub_num} {sub_title}")
                    lines.append(f"  {'~' * len(f'{sub_num} {sub_title}')}")
                    lines.append("")
                    for sub_text in item.get("content", []):
                        if sub_text.startswith("- "):
                            lines.append(f"    * {sub_text[2:]}")
                        else:
                            lines.append(f"    {sub_text}")
                        lines.append("")
                elif item_type == "table":
                    tbl_headers = item.get("headers", [])
                    tbl_rows = item.get("rows", [])
                    lines.append(format_table_as_text(tbl_headers, tbl_rows))
                    lines.append("")
                elif item_type == "faq":
                    q = item.get("q", "")
                    a = item.get("a", "")
                    lines.append(f"  Q: {q}")
                    lines.append(f"  A: {a}")
                    lines.append("")

        lines.append("")

    # 5. End of Document
    lines.append("=" * 80)
    lines.append("END OF POLICY DOCUMENT — NORTHSTAR TECHNOLOGIES INDIA PVT. LTD.")
    lines.append("SYNTHETIC SAMPLE — FICTIONAL COMPANY — NOT AN ACTUAL CORPORATE POLICY")
    lines.append("=" * 80)

    content = "\n".join(lines)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
        
    return filepath
