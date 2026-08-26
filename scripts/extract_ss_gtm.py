#!/usr/bin/env python3
"""Extract the full text content of the Saverwell GTM Strategy Google Doc.

Reads Google Doc ID 16jeXB5cK1C_ZSAax4HNbhBFGhHXE_oS7zT4w7iPI7Ro,
extracts ALL text including deep table cell traversal, and saves to
data/saverwell_gtm_strategy.md.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DOC_ID = "16jeXB5cK1C_ZSAax4HNbhBFGhHXE_oS7zT4w7iPI7Ro"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "saverwell_gtm_strategy.md"


def extract_text_from_paragraph(paragraph: Dict[str, Any]) -> str:
    """Extract text from a paragraph element."""
    text = ""
    for element in paragraph.get("elements", []):
        text_run = element.get("textRun")
        if text_run:
            text += text_run.get("content", "")
    return text


def get_paragraph_style(paragraph: Dict[str, Any]) -> str:
    """Return the named style type of a paragraph (e.g., HEADING_1)."""
    return paragraph.get("paragraphStyle", {}).get("namedStyleType", "NORMAL_TEXT")


def is_list_paragraph(paragraph: Dict[str, Any]) -> bool:
    """Check if a paragraph is a list item (has bullet)."""
    return "bullet" in paragraph.get("paragraphStyle", {}).get("bullet", {}) or \
           bool(paragraph.get("bullet"))


def extract_text_from_structural_elements(elements: List[Dict[str, Any]]) -> str:
    """Recursively extract all text from structural elements including tables.

    This handles the full traversal path for tables:
    table -> tableRows -> tableCells -> content -> paragraph -> elements -> textRun -> content
    """
    output_lines: List[str] = []

    for element in elements:
        # ── Paragraph ─────────────────────────────────────────────
        if "paragraph" in element:
            paragraph = element["paragraph"]
            style = get_paragraph_style(paragraph)
            text = extract_text_from_paragraph(paragraph)

            # Add markdown heading markers based on style
            if style == "TITLE":
                output_lines.append("# " + text.strip() + "\n\n")
            elif style == "HEADING_1":
                output_lines.append("## " + text.strip() + "\n\n")
            elif style == "HEADING_2":
                output_lines.append("### " + text.strip() + "\n\n")
            elif style == "HEADING_3":
                output_lines.append("#### " + text.strip() + "\n\n")
            elif style == "HEADING_4":
                output_lines.append("##### " + text.strip() + "\n\n")
            else:
                # Normal text — just append as-is (already has newline from Google)
                output_lines.append(text)

        # ── Table ─────────────────────────────────────────────────
        elif "table" in element:
            table = element["table"]
            table_rows = table.get("tableRows", [])

            all_rows: List[List[str]] = []

            for row in table_rows:
                row_cells: List[str] = []
                for cell in row.get("tableCells", []):
                    # Deep traversal: cell -> content -> paragraph -> elements -> textRun -> content
                    cell_text_parts: List[str] = []
                    cell_content = cell.get("content", [])
                    for content_element in cell_content:
                        if "paragraph" in content_element:
                            para = content_element["paragraph"]
                            para_text = extract_text_from_paragraph(para)
                            stripped = para_text.strip()
                            if stripped:
                                cell_text_parts.append(stripped)
                    row_cells.append(" / ".join(cell_text_parts) if cell_text_parts else "")
                all_rows.append(row_cells)

            # Convert to markdown table
            if all_rows:
                # Determine column count from widest row
                max_cols = max(len(r) for r in all_rows) if all_rows else 0
                # Normalize all rows to same column count
                for row in all_rows:
                    while len(row) < max_cols:
                        row.append("")

                # First row as header
                header = all_rows[0]
                output_lines.append("| " + " | ".join(header) + " |\n")
                output_lines.append("| " + " | ".join(["---"] * max_cols) + " |\n")
                for row in all_rows[1:]:
                    # Escape pipe characters within cell content
                    escaped = [c.replace("|", "\\|") for c in row]
                    output_lines.append("| " + " | ".join(escaped) + " |\n")
                output_lines.append("\n")

        # ── Table of Contents ─────────────────────────────────────
        elif "tableOfContents" in element:
            toc = element["tableOfContents"]
            toc_content = toc.get("content", [])
            output_lines.append("[Table of Contents]\n\n")
            # Extract TOC entries
            toc_text = extract_text_from_structural_elements(toc_content)
            output_lines.append(toc_text)
            output_lines.append("\n")

        # ── Section break ─────────────────────────────────────────
        elif "sectionBreak" in element:
            pass  # Skip section breaks

    return "".join(output_lines)


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    from googleapiclient.discovery import build

    from cmo_agent.config import Settings
    from cmo_agent.google_auth import get_google_credentials

    settings = Settings()
    creds = get_google_credentials(
        oauth_token_path=settings.google_oauth_token_path,
        service_account_path=settings.google_credentials_path,
        scopes=[
            "https://www.googleapis.com/auth/documents.readonly",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    )
    if not creds:
        print("ERROR: No Google credentials available. Check .env settings.")
        sys.exit(1)

    docs_service = build("docs", "v1", credentials=creds)

    # Fetch the full document
    print(f"Fetching Google Doc {DOC_ID}...")
    doc = docs_service.documents().get(documentId=DOC_ID).execute()

    title = doc.get("title", "Untitled")
    print(f"  Title: {title}")

    body = doc.get("body", {})
    content = body.get("content", [])
    print(f"  Structural elements: {len(content)}")

    # Extract all text
    print("Extracting text (including deep table traversal)...")
    extracted = extract_text_from_structural_elements(content)

    # Clean up excessive blank lines
    while "\n\n\n" in extracted:
        extracted = extracted.replace("\n\n\n", "\n\n")

    # Save to file
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(extracted)

    # Report stats
    lines = extracted.split("\n")
    non_empty = [l for l in lines if l.strip()]
    table_count = extracted.count("| ---")
    print(f"\nExtraction complete:")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  Total lines: {len(lines)}")
    print(f"  Non-empty lines: {len(non_empty)}")
    print(f"  Tables found: {table_count}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
