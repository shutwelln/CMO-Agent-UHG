#!/usr/bin/env python3
"""Update the Agent Tunnel GTM Strategy Google Doc with latest markdown content.

Reads the updated markdown from data/agent_tunnel_gtm_strategy.md, converts it
to the Google Docs structured format, and replaces the doc content via the API.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

DOC_ID = "1zegIuI3M98H2ZkqAHI5E8O9hZGrXHiOBqnUUQvH1NyA"
MD_PATH = Path(__file__).resolve().parent.parent / "data" / "agent_tunnel_gtm_strategy.md"


# ── Reuse helpers from docs agent ─────────────────────────────────────────

def _heading_style(level: int) -> str:
    return {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3"}.get(level, "HEADING_1")


def _parse_inline_formatting(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Parse **bold** and *italic* markers, return (plain_text, runs)."""
    runs: List[Tuple[int, int, str]] = []
    result_chars: List[str] = []
    i = 0
    length = len(text)
    while i < length:
        if i + 1 < length and text[i] == "*" and text[i + 1] == "*":
            end_marker = text.find("**", i + 2)
            if end_marker != -1:
                start_pos = len(result_chars)
                inner = text[i + 2 : end_marker]
                result_chars.extend(inner)
                runs.append((start_pos, start_pos + len(inner), "bold"))
                i = end_marker + 2
                continue
        if text[i] == "*" and (i + 1 >= length or text[i + 1] != "*"):
            end_marker = text.find("*", i + 1)
            if end_marker != -1 and (end_marker + 1 >= length or text[end_marker + 1] != "*"):
                start_pos = len(result_chars)
                inner = text[i + 1 : end_marker]
                result_chars.extend(inner)
                runs.append((start_pos, start_pos + len(inner), "italic"))
                i = end_marker + 1
                continue
        result_chars.append(text[i])
        i += 1
    return ("".join(result_chars), runs)


# ── Markdown parser ───────────────────────────────────────────────────────

def parse_markdown(md_text: str) -> Dict[str, Any]:
    """Convert markdown to document structure format for the Google Docs API."""
    lines = md_text.split("\n")
    title = ""
    sections: List[Dict[str, Any]] = []
    current_section: Dict[str, Any] | None = None
    current_content: List[Dict[str, Any]] = []
    bullet_items: List[str] = []
    table_headers: List[str] = []
    table_rows: List[List[str]] = []

    def flush_bullets() -> None:
        nonlocal bullet_items
        if bullet_items:
            current_content.append({"type": "bullets", "items": bullet_items[:]})
            bullet_items = []

    def flush_table() -> None:
        nonlocal table_headers, table_rows
        if table_headers:
            current_content.append({
                "type": "table",
                "headers": table_headers[:],
                "rows": [r[:] for r in table_rows],
            })
            table_headers = []
            table_rows = []

    def flush_section() -> None:
        nonlocal current_section, current_content
        flush_bullets()
        flush_table()
        if current_section is not None:
            current_section["content"] = current_content[:]
            sections.append(current_section)
        current_section = None
        current_content = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        i += 1

        # Skip horizontal rules
        if stripped == "---":
            flush_bullets()
            flush_table()
            continue

        # Title (# heading)
        if re.match(r"^# (?!#)", stripped):
            title = stripped[2:].strip()
            continue

        # Heading level 1 (## heading)
        if re.match(r"^## (?!#)", stripped):
            flush_section()
            current_section = {"heading": stripped[3:].strip(), "level": 1}
            current_content = []
            continue

        # Heading level 2 (### heading)
        if re.match(r"^### (?!#)", stripped):
            flush_section()
            current_section = {"heading": stripped[4:].strip(), "level": 2}
            current_content = []
            continue

        # Heading level 3 (#### heading) → treat as level 2 subheading
        if re.match(r"^#### ", stripped):
            flush_section()
            current_section = {"heading": stripped[5:].strip(), "level": 2}
            current_content = []
            continue

        # Table row
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_bullets()
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator rows (|---|---|)
            if all(re.match(r"^[-:]+$", c) for c in cells):
                continue
            if not table_headers:
                table_headers = cells
            else:
                table_rows.append(cells)
            continue
        elif table_headers:
            flush_table()

        # Bullet point
        if stripped.startswith("- "):
            bullet_items.append(stripped[2:])
            continue
        elif bullet_items:
            flush_bullets()

        # Empty line — skip
        if not stripped:
            continue

        # Regular paragraph
        if current_section is not None:
            current_content.append({"type": "paragraph", "text": stripped})

    flush_section()
    return {"title": title, "include_toc": True, "sections": sections}


# ── Table of Contents ─────────────────────────────────────────────────────

def insert_toc(docs_service: Any, doc_id: str, batch_fn: Any) -> None:
    """Insert a formatted, linked Table of Contents at the top of the document."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])

    headings: List[Dict[str, Any]] = []
    for elem in body_content:
        if "paragraph" not in elem:
            continue
        para = elem["paragraph"]
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        heading_id = style.get("headingId", "")
        if not named_style.startswith("HEADING_") or not heading_id:
            continue
        level = int(named_style.replace("HEADING_", ""))
        if level > 3:
            continue
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()
        if text:
            headings.append({"text": text, "level": level, "heading_id": heading_id})

    if not headings:
        return

    toc_title = "Table of Contents\n"
    toc_tip = (
        "For page numbers: select this TOC, delete it, then "
        "Insert \u2192 Table of contents \u2192 With page numbers.\n"
    )
    entry_lines: List[str] = []
    for h in headings:
        entry_lines.append(h["text"] + "\n")
    separator = "\n"

    toc_text = toc_title + toc_tip + "".join(entry_lines) + separator

    requests: List[Dict[str, Any]] = [
        {"insertText": {"location": {"index": 1}, "text": toc_text}},
    ]

    # Style title: bold 16pt
    title_start = 1
    title_end = title_start + len(toc_title)
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": title_start, "endIndex": title_end},
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "spaceBelow": {"magnitude": 4, "unit": "PT"},
            },
            "fields": "namedStyleType,spaceBelow",
        }
    })
    requests.append({
        "updateTextStyle": {
            "range": {"startIndex": title_start, "endIndex": title_end - 1},
            "textStyle": {
                "bold": True,
                "fontSize": {"magnitude": 16, "unit": "PT"},
            },
            "fields": "bold,fontSize",
        }
    })

    # Style tip: italic 9pt grey
    tip_start = title_end
    tip_end = tip_start + len(toc_tip)
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": tip_start, "endIndex": tip_end},
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "spaceBelow": {"magnitude": 6, "unit": "PT"},
            },
            "fields": "namedStyleType,spaceBelow",
        }
    })
    requests.append({
        "updateTextStyle": {
            "range": {"startIndex": tip_start, "endIndex": tip_end - 1},
            "textStyle": {
                "italic": True,
                "fontSize": {"magnitude": 9, "unit": "PT"},
                "foregroundColor": {
                    "color": {
                        "rgbColor": {"red": 0.6, "green": 0.6, "blue": 0.6}
                    }
                },
            },
            "fields": "italic,fontSize,foregroundColor",
        }
    })

    # Style each entry: 11pt, linked, indented by level
    cursor = tip_end
    for h in headings:
        entry_text = h["text"] + "\n"
        entry_start = cursor
        entry_end = cursor + len(entry_text) - 1

        if entry_end > entry_start:
            requests.append({
                "updateParagraphStyle": {
                    "range": {
                        "startIndex": entry_start,
                        "endIndex": entry_start + len(entry_text),
                    },
                    "paragraphStyle": {
                        "namedStyleType": "NORMAL_TEXT",
                        "spaceAbove": {"magnitude": 2, "unit": "PT"},
                        "spaceBelow": {"magnitude": 2, "unit": "PT"},
                        "indentStart": {
                            "magnitude": 18 * (h["level"] - 1),
                            "unit": "PT",
                        },
                    },
                    "fields": "namedStyleType,spaceAbove,spaceBelow,indentStart",
                }
            })
            text_style: Dict[str, Any] = {
                "fontSize": {"magnitude": 11, "unit": "PT"},
                "link": {"headingId": h["heading_id"]},
            }
            style_fields = "fontSize,link"
            if h["level"] == 1:
                text_style["bold"] = True
                style_fields += ",bold"
            requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": entry_start, "endIndex": entry_end},
                    "textStyle": text_style,
                    "fields": style_fields,
                }
            })

        cursor += len(entry_text)

    batch_fn(requests)


# ── Google Doc update ─────────────────────────────────────────────────────

def update_doc(docs_service: Any, doc_id: str, structure: Dict[str, Any]) -> None:
    """Clear the Google Doc and rebuild it from the structure."""
    write_timestamps: List[float] = []

    def batch(requests_payload: List[Dict[str, Any]]) -> Any:
        """Execute batchUpdate with rate limiting."""
        now = time.time()
        while write_timestamps and now - write_timestamps[0] > 60:
            write_timestamps.pop(0)
        if len(write_timestamps) >= 55:
            sleep_time = 61 - (now - write_timestamps[0])
            if sleep_time > 0:
                print(f"  Rate limit pause: {sleep_time:.1f}s")
                time.sleep(sleep_time)
        result = docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests_payload}
        ).execute()
        write_timestamps.append(time.time())
        return result

    # 1. Read existing doc to find content length
    print("  Reading existing doc...")
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])
    end_index = body_content[-1].get("endIndex", 1) if body_content else 1

    # 2. Delete all existing content
    if end_index > 2:
        print("  Clearing existing content...")
        batch([{
            "deleteContentRange": {
                "range": {"startIndex": 1, "endIndex": end_index - 1}
            }
        }])

    # 3. Build content
    sections = structure.get("sections", [])
    # Normalize: convert body→content if needed
    for s in sections:
        if "content" not in s:
            body = s.pop("body", "")
            s["content"] = [{"type": "paragraph", "text": body}] if body else []

    requests: List[Dict[str, Any]] = []
    cursor = 1

    print(f"  Inserting {len(sections)} sections...")

    for sec_idx, section in enumerate(sections):
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        # Insert heading
        if heading:
            heading_text = heading + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": heading_text}}
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": h_start, "endIndex": h_end},
                    "paragraphStyle": {
                        "namedStyleType": _heading_style(level),
                        "spaceAbove": {"magnitude": 12, "unit": "PT"},
                        "spaceBelow": {"magnitude": 4, "unit": "PT"},
                    },
                    "fields": "namedStyleType,spaceAbove,spaceBelow",
                }
            })
            cursor = h_end

        # Insert content blocks
        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text:
                    continue
                para_text = text + "\n"
                plain, formatting_runs = _parse_inline_formatting(para_text)
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": plain}}
                )
                p_start = cursor
                p_end = cursor + len(plain)
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": p_start, "endIndex": p_end},
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "spaceBelow": {"magnitude": 6, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceBelow",
                    }
                })
                for run_start, run_end, style in formatting_runs:
                    abs_start = cursor + run_start
                    abs_end = cursor + run_end
                    if style == "bold":
                        requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": abs_start, "endIndex": abs_end},
                                "textStyle": {"bold": True},
                                "fields": "bold",
                            }
                        })
                    elif style == "italic":
                        requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": abs_start, "endIndex": abs_end},
                                "textStyle": {"italic": True},
                                "fields": "italic",
                            }
                        })
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append({
                        "insertText": {"location": {"index": cursor}, "text": item_text}
                    })
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append({
                    "createParagraphBullets": {
                        "range": {"startIndex": list_start, "endIndex": list_end},
                        "bulletPreset": preset,
                    }
                })

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)
                requests.append({
                    "insertTable": {
                        "rows": num_rows,
                        "columns": num_cols,
                        "location": {"index": cursor},
                    }
                })
                # Execute pending requests before populating table
                if requests:
                    batch(requests)
                    requests = []

                # Re-read doc to find table cell positions (nearest to cursor)
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        elem_start = elem.get("startIndex", 0)
                        if elem_start >= cursor - 2:
                            table_element = elem
                            break
                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts: List[Tuple[int, str]] = []
                    for ri, row_data in enumerate(all_table_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(table_row.get("tableCells", [])):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get("startIndex", 0)
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append((cell_idx, cell_text))
                    # Insert in reverse order so indices stay valid
                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cell_idx, cell_text in cell_inserts:
                        requests.append({
                            "insertText": {
                                "location": {"index": cell_idx},
                                "text": cell_text,
                            }
                        })
                    if requests:
                        batch(requests)
                        requests = []

                    # Bold header row — find the same table by startIndex
                    doc_state2 = docs_service.documents().get(documentId=doc_id).execute()
                    table_elem2 = None
                    tbl_start = table_element.get("startIndex", 0)
                    for elem in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem and elem.get("startIndex", 0) >= tbl_start:
                            table_elem2 = elem
                            break
                    if table_elem2 and table_elem2["table"].get("tableRows"):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append({
                                        "updateTextStyle": {
                                            "range": {"startIndex": si, "endIndex": ei},
                                            "textStyle": {"bold": True},
                                            "fields": "bold",
                                        }
                                    })
                    if requests:
                        batch(requests)
                        requests = []

                # Update cursor position after table
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                if body_content:
                    cursor = body_content[-1].get("endIndex", cursor) - 1
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": "\n"}}
                )
                cursor += 1

    # 4. Execute remaining requests
    if requests:
        batch(requests)

    print("  Content inserted successfully.")

    # 5. Insert Table of Contents if requested
    if structure.get("include_toc"):
        print("  Inserting Table of Contents...")
        insert_toc(docs_service, doc_id, batch)
        print("  TOC inserted.")


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
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    if not creds:
        print("ERROR: No Google credentials available. Check .env settings.")
        sys.exit(1)

    docs_service = build("docs", "v1", credentials=creds)

    # Parse markdown
    print(f"Reading {MD_PATH.name}...")
    md_text = MD_PATH.read_text()
    structure = parse_markdown(md_text)
    print(f"  Title: {structure['title']}")
    print(f"  Sections: {len(structure['sections'])}")

    # Update the doc
    print(f"\nUpdating Google Doc {DOC_ID}...")
    update_doc(docs_service, DOC_ID, structure)

    print(f"\nDone! View at: https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
