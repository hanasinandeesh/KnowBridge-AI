#!/usr/bin/env python3
"""
KnowBridge AI — Task 003D: Inspect Generated Document Chunks
Extracts and chunks synthetic enterprise policy documents and exports them
to a clean, formatted JSON file and formatted terminal view.

Usage:
    cd backend
    python scripts/inspect_chunks.py [--type pdf|docx|txt] [--limit N]
"""

import argparse
import json
import sys
from pathlib import Path

# Add backend directory to Python path
BACKEND_DIR = Path(__file__).resolve().parent.parent
WORKSPACE_DIR = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.parsers.docx_parser import DOCXParser
from app.parsers.pdf_parser import PDFParser
from app.parsers.txt_parser import TXTParser
from app.services.document_chunker import DocumentChunkerService


def inspect_chunks(doc_type: str = "pdf", limit: int = 5) -> None:
    policies_dir = WORKSPACE_DIR / "synthetic-data" / "policies"

    mapping = {
        "pdf": ("HR-TRV-001_Travel_Reimbursement_v1.0.pdf", PDFParser()),
        "docx": ("FIN-EXP-001_Employee_Expense.docx", DOCXParser()),
        "txt": ("IT-AUP-001_IT_Acceptable_Use.txt", TXTParser()),
    }

    if doc_type not in mapping:
        print(f"Unknown document type '{doc_type}'. Choose from: pdf, docx, txt.")
        return

    filename, parser = mapping[doc_type]
    file_path = policies_dir / filename

    if not file_path.exists():
        print(f"File not found: {file_path}")
        return

    print("=" * 80)
    print(f"KnowBridge AI — Chunk Inspector: {filename}")
    print("=" * 80)

    # 1. Extract
    extracted = parser.parse(file_path.read_bytes(), filename=filename)

    # 2. Chunk
    chunker = DocumentChunkerService(
        default_chunk_size=settings.CHUNK_SIZE,
        default_chunk_overlap=settings.CHUNK_OVERLAP,
    )
    result = chunker.chunk_document(extracted)

    # 3. Export to JSON file for easy reading
    output_file = BACKEND_DIR / "sample_chunks_output.json"
    result_dict = result.model_dump(mode="json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)

    print(f"\n[INFO] Total chunks generated: {result.total_chunks}")
    print(f"[INFO] Full chunks exported to: {output_file.resolve()}\n")
    print(f"Displaying first {min(limit, result.total_chunks)} chunks below:\n")

    for i in range(min(limit, result.total_chunks)):
        chunk = result.chunks[i]
        print(f"┌{'─' * 78}┐")
        print(f"│ CHUNK #{chunk.chunk_index:<3} | Page: {str(chunk.page_number):<5} | Type: {chunk.source_unit_type:<10} | Chars: {chunk.character_count:<4} | Tokens: ~{chunk.token_count:<4} │")
        print(f"├{'─' * 78}┤")
        print(f"│ Section Title:     {str(chunk.section_title):<57} │")
        hierarchy_str = " > ".join(chunk.section_hierarchy) if chunk.section_hierarchy else "None"
        if len(hierarchy_str) > 55:
            hierarchy_str = hierarchy_str[:52] + "..."
        print(f"│ Section Breadcrumb:{hierarchy_str:<57} │")
        print(f"├{'─' * 78}┤")
        print("│ TEXT CONTENT:")
        for line in chunk.chunk_text.splitlines():
            # Wrap long lines for clean terminal display
            while len(line) > 74:
                print(f"│   {line[:74]}")
                line = line[74:]
            print(f"│   {line}")
        print(f"└{'─' * 78}┘\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inspect generated document chunks")
    parser.add_argument("--type", choices=["pdf", "docx", "txt"], default="pdf", help="Document type to inspect")
    parser.add_argument("--limit", type=int, default=3, help="Number of chunks to print to terminal")
    args = parser.parse_args()

    inspect_chunks(doc_type=args.type, limit=args.limit)
