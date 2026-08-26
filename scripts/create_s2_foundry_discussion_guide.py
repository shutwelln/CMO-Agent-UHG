"""Create or update the S2 Foundry, LLC Co-Founder Discussion Guide as a Google Doc.

Constructs the full document structure and creates/updates it via the Google
Docs API. Bypasses LLM generation to ensure exact content fidelity.

Usage:
    python scripts/create_s2_foundry_discussion_guide.py              # create new
    python scripts/create_s2_foundry_discussion_guide.py --update ID  # update existing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the co-founder discussion guide document structure."""
    return {
        "title": "S2 Foundry, LLC - Co-Founder Discussion Guide",
        "sections": [
            # ── Section 1: Purpose ──────────────────────────────────────
            {
                "heading": "Purpose",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This is a working discussion guide, not a legal "
                            "document. It captures the key questions and "
                            "considerations that both co-founders need to align "
                            "on before engaging legal counsel to draft the "
                            "Operating Agreement for S2 Foundry, Limited "
                            "Liability Company (LLC)."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry is structured as a partnership that "
                            "allows both co-founders to collaborate on projects "
                            "while maintaining other professional commitments. "
                            "The business depends on both co-founders being "
                            "actively involved, and neither party alone can "
                            "operate the projects they build together. Each "
                            "section below includes a recommended position as "
                            "a starting point for discussion."
                        ),
                    },
                ],
            },
            # ── Section 2: IP Contribution & Ownership ──────────────────
            {
                "heading": (
                    "Intellectual Property (IP) Contribution & Ownership"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry will collaborate on multiple "
                            "products and client engagements over time. "
                            "Agent Tunnel is the first product and its IP "
                            "will be owned by S2 Foundry. As additional "
                            "products and engagements are created, those "
                            "will follow the same ownership model."
                        ),
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "What IP created within S2 Foundry "
                                    "belongs to the entity vs. the "
                                    "individual?"
                                ),
                                "rec": (
                                    "All products, code, and IP created "
                                    "by either co-founder in the course "
                                    "of S2 Foundry business belongs to "
                                    "the entity. Side projects and work "
                                    "done for other employers or clients "
                                    "remain individual property. Define "
                                    "\"S2 Foundry business\" clearly to "
                                    "avoid overlap with each co-founder's "
                                    "other professional work."
                                ),
                            },
                            {
                                "q": (
                                    "How do we handle IP for client "
                                    "engagements where S2 Foundry provides "
                                    "services to a third party?"
                                ),
                                "rec": (
                                    "Define this on a per-engagement basis "
                                    "in the client contract. The default "
                                    "should be that S2 Foundry retains "
                                    "ownership of any reusable tooling or "
                                    "platform IP, while client-specific "
                                    "deliverables are governed by the "
                                    "client agreement."
                                ),
                            },
                            {
                                "q": (
                                    "What happens to S2 Foundry's IP "
                                    "(including Agent Tunnel) if the LLC "
                                    "dissolves?"
                                ),
                                "rec": (
                                    "All entity-owned IP is either sold "
                                    "as part of dissolution with proceeds "
                                    "split 50/50, or licensed "
                                    "non-exclusively to both parties on "
                                    "a perpetual basis if neither party "
                                    "wants to buy."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 3: Roles, Responsibilities & Domain Authority ───
            {
                "heading": "Roles, Responsibilities & Domain Authority",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "A clear division of operational domains reduces "
                            "day-to-day friction. One co-founder leads "
                            "business strategy, marketing, go-to-market, "
                            "distribution, and partnerships. The other leads "
                            "technology, product architecture, engineering, "
                            "and technical infrastructure. Both co-founders "
                            "will maintain other professional commitments "
                            "alongside S2 Foundry."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Business & Commercial",
                            "Technology & Product",
                        ],
                        "rows": [
                            [
                                "Marketing & brand strategy",
                                "Product architecture & engineering",
                            ],
                            [
                                "Go-to-market & distribution",
                                "Technical infrastructure & DevOps",
                            ],
                            [
                                "Partnerships & BD",
                                "Data, security & compliance (technical)",
                            ],
                            [
                                "Sales & revenue operations",
                                "R&D and technical roadmap",
                            ],
                            [
                                "Finance & fundraising",
                                "Vendor selection (technical tools)",
                            ],
                        ],
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "Does the domain lead have final say "
                                    "within their area, or do certain "
                                    "decisions still require mutual agreement?"
                                ),
                                "rec": (
                                    "Domain lead has final say on day-to-day "
                                    "decisions. Strategic decisions that "
                                    "affect the revenue model, brand "
                                    "positioning, or technical architecture "
                                    "direction require both co-founders "
                                    "to agree."
                                ),
                            },
                            {
                                "q": (
                                    "What is the threshold (dollar amount, "
                                    "strategic impact) that triggers joint "
                                    "decision-making?"
                                ),
                                "rec": (
                                    "Any expenditure over $2,500, any "
                                    "commitment longer than 6 months, and "
                                    "any client commitment with revenue "
                                    "implications over $5,000/year."
                                ),
                            },
                            {
                                "q": (
                                    "How do we handle areas that span both "
                                    "domains (e.g., product pricing, client "
                                    "commitments)?"
                                ),
                                "rec": (
                                    "Product pricing is joint. Client "
                                    "commitments that involve technical "
                                    "delivery require both to sign off."
                                ),
                            },
                            {
                                "q": (
                                    "Who handles administrative and legal "
                                    "functions?"
                                ),
                                "rec": (
                                    "Business domain lead handles admin and "
                                    "legal coordination by default, with "
                                    "both co-founders involved in any "
                                    "decisions that create obligations for "
                                    "the LLC."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 4: Decision-Making & Deadlock Resolution ────────
            {
                "heading": "Decision-Making & Deadlock Resolution",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This is the most critical section for a 50/50 "
                            "structure. Without a majority owner, "
                            "disagreements need a defined resolution path "
                            "to prevent operational paralysis."
                        ),
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "What decisions can each co-founder make "
                                    "unilaterally within their domain?"
                                ),
                                "rec": (
                                    "Day-to-day operational decisions, "
                                    "spending under the agreed threshold, "
                                    "vendor choices within your domain, and "
                                    "tactical execution decisions."
                                ),
                            },
                            {
                                "q": (
                                    "What decisions require unanimous "
                                    "agreement?"
                                ),
                                "rec": (
                                    "Taking on debt, expenditures above the "
                                    "agreed threshold, entering new markets, "
                                    "any legal commitments binding the LLC, "
                                    "and winding down or dissolving the "
                                    "business."
                                ),
                            },
                            {
                                "q": (
                                    "What is the deadlock resolution process?"
                                ),
                                "rec": (
                                    "Three-step process: (1) 7-day "
                                    "cooling-off period with written position "
                                    "statements, (2) mediation by a mutually "
                                    "agreed advisor, (3) if still unresolved, "
                                    "domain authority applies and the "
                                    "co-founder whose domain the decision "
                                    "falls in gets the final call. Given the "
                                    "family relationship, preserving the "
                                    "personal relationship should take "
                                    "priority over any single business "
                                    "decision."
                                ),
                            },
                            {
                                "q": (
                                    "How do we handle urgency? Is there a "
                                    "\"time-sensitive decision\" exception "
                                    "where one party can act?"
                                ),
                                "rec": (
                                    "Either co-founder can make a "
                                    "time-sensitive decision unilaterally if "
                                    "the other is unreachable for 24 hours "
                                    "and there is a documented business "
                                    "reason for urgency. The acting party "
                                    "must notify the other within 24 hours."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 5: Financial Structure ──────────────────────────
            {
                "heading": "Financial Structure",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Covers how money flows in and out of the "
                            "partnership. Both co-founders maintain separate "
                            "income from other professional commitments, so "
                            "S2 Foundry does not need to support full-time "
                            "compensation."
                        ),
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "What are the initial capital "
                                    "contributions (cash, IP, or sweat "
                                    "equity)?"
                                ),
                                "rec": (
                                    "Document each party's contribution "
                                    "explicitly in the Operating Agreement. "
                                    "Agent Tunnel as the first product, "
                                    "any cash, and any sweat equity should "
                                    "be listed."
                                ),
                            },
                            {
                                "q": (
                                    "How are profits and losses distributed?"
                                ),
                                "rec": (
                                    "Straight 50/50. Keep it simple."
                                ),
                            },
                            {
                                "q": (
                                    "What is the process for approving "
                                    "project expenses or ongoing costs "
                                    "(hosting, tools, subscriptions)?"
                                ),
                                "rec": (
                                    "Either co-founder can approve recurring "
                                    "costs under the agreed threshold. "
                                    "Larger project investments require "
                                    "mutual agreement before spending."
                                ),
                            },
                            {
                                "q": (
                                    "If one party contributes more cash "
                                    "than the other, how is that accounted "
                                    "for?"
                                ),
                                "rec": (
                                    "Structure as a member loan with a "
                                    "defined repayment schedule rather than "
                                    "changing the equity split. Keeps "
                                    "ownership clean at 50/50."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 6: Commitment & Departure ───────────────────────
            {
                "heading": "Commitment & Departure",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry is designed to work alongside each "
                            "co-founder's other professional commitments. "
                            "The business depends on both co-founders being "
                            "actively involved. If either one steps away, "
                            "the projects they are collaborating on likely "
                            "cannot continue in their current form."
                        ),
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "What is the expected minimum time "
                                    "commitment from each co-founder?"
                                ),
                                "rec": (
                                    "Agree on a minimum number of hours per "
                                    "week or per month rather than requiring "
                                    "full-time. Document it so expectations "
                                    "are clear, but keep it flexible to "
                                    "accommodate each person's other "
                                    "commitments."
                                ),
                            },
                            {
                                "q": (
                                    "Are there any restrictions on what "
                                    "other work each co-founder can take on?"
                                ),
                                "rec": (
                                    "No general restrictions. Both "
                                    "co-founders are free to maintain other "
                                    "employment, clients, and side projects. "
                                    "The only restriction should be directly "
                                    "competing with an active S2 Foundry "
                                    "project in the same market while that "
                                    "project is ongoing."
                                ),
                            },
                            {
                                "q": (
                                    "What happens if one co-founder wants "
                                    "to step away or can no longer "
                                    "contribute?"
                                ),
                                "rec": (
                                    "60-day notice period. Since the "
                                    "business depends on both parties, the "
                                    "default outcome is a wind-down of "
                                    "active projects rather than a buyout. "
                                    "All entity-owned IP is handled per "
                                    "the dissolution terms."
                                ),
                            },
                            {
                                "q": (
                                    "Under what circumstances would one "
                                    "co-founder buy out the other's "
                                    "interest instead of winding down?"
                                ),
                                "rec": (
                                    "If the remaining co-founder wants to "
                                    "continue operating a specific project "
                                    "solo, they can buy out the departing "
                                    "member's interest at a mutually agreed "
                                    "price. If they cannot agree on price, "
                                    "use the shotgun clause from the Exit "
                                    "section."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 7: Exit, Sale & Dissolution ─────────────────────
            {
                "heading": "Exit, Sale & Dissolution",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Covers end-of-life scenarios for the "
                            "partnership."
                        ),
                    },
                    {
                        "type": "nested_bullets",
                        "items": [
                            {
                                "q": (
                                    "Right of First Refusal (ROFR): if one "
                                    "party wants to sell their interest, "
                                    "does the other get the first "
                                    "opportunity to buy?"
                                ),
                                "rec": (
                                    "Yes. 30 days to match any third-party "
                                    "offer before any outside sale can "
                                    "proceed."
                                ),
                            },
                            {
                                "q": (
                                    "Is there a shotgun clause (one party "
                                    "names a price, the other must buy at "
                                    "that price or sell at that price)?"
                                ),
                                "rec": (
                                    "Yes. One party names a price per unit; "
                                    "the other has 30 days to either buy at "
                                    "that price or sell at that price. "
                                    "Clean, fast, and fair because the "
                                    "person naming the price has to be "
                                    "willing to be on either side of the "
                                    "transaction."
                                ),
                            },
                            {
                                "q": (
                                    "What triggers dissolution of the LLC?"
                                ),
                                "rec": (
                                    "Mutual agreement, departure of either "
                                    "co-founder (unless the remaining party "
                                    "elects to buy out), or extended "
                                    "inactivity (e.g., no active projects "
                                    "for 12 months)."
                                ),
                            },
                            {
                                "q": (
                                    "How are assets handled on dissolution?"
                                ),
                                "rec": (
                                    "All entity-owned IP (including Agent "
                                    "Tunnel and any subsequent products) is "
                                    "either sold with proceeds split 50/50, "
                                    "or licensed non-exclusively to both "
                                    "parties. Cash and other assets split "
                                    "50/50 after all obligations are settled."
                                ),
                            },
                        ],
                    },
                ],
            },
            # ── Section 8: Next Steps ───────────────────────────────────
            {
                "heading": "Next Steps",
                "level": 1,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Walk through each section and document initial "
                            "alignment or disagreement",
                            "Revisit any areas of disagreement and negotiate "
                            "to a shared position",
                            "Engage legal counsel to draft the Operating "
                            "Agreement based on agreed positions",
                            "Formalize the IP contribution agreement as an "
                            "exhibit to the Operating Agreement",
                        ],
                    },
                ],
            },
        ],
    }


def _render_content(docs_service, doc_id: str, sections: list) -> None:
    """Render sections into the Google Doc body."""
    requests = []
    cursor = 1

    def _heading_style(level: int) -> str:
        mapping = {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
        }
        return mapping.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        # Insert heading
        if heading:
            heading_text = heading + "\n"
            requests.append(
                {
                    "insertText": {
                        "location": {"index": cursor},
                        "text": heading_text,
                    }
                }
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": h_start,
                            "endIndex": h_end,
                        },
                        "paragraphStyle": {
                            "namedStyleType": _heading_style(level),
                            "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        # Insert content blocks
        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text:
                    continue
                para_text = text + "\n"
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": para_text,
                        }
                    }
                )
                p_start = cursor
                p_end = cursor + len(para_text)
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": p_start,
                                "endIndex": p_end,
                            },
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {
                                    "magnitude": 6,
                                    "unit": "PT",
                                },
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": item_text,
                            }
                        }
                    )
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "nested_bullets":
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                sub_ranges = []
                for item in items:
                    q_text = item["q"] + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": q_text,
                            }
                        }
                    )
                    cursor += len(q_text)
                    rec_text = item["rec"] + "\n"
                    rec_start = cursor
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": rec_text,
                            }
                        }
                    )
                    cursor += len(rec_text)
                    rec_end = cursor
                    sub_ranges.append((rec_start, rec_end))
                list_end = cursor
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                        }
                    }
                )
                for rec_start, rec_end in sub_ranges:
                    requests.append(
                        {
                            "updateParagraphStyle": {
                                "range": {
                                    "startIndex": rec_start,
                                    "endIndex": rec_end,
                                },
                                "paragraphStyle": {
                                    "indentStart": {
                                        "magnitude": 72,
                                        "unit": "PT",
                                    },
                                    "indentFirstLine": {
                                        "magnitude": 54,
                                        "unit": "PT",
                                    },
                                },
                                "fields": "indentStart,indentFirstLine",
                            }
                        }
                    )

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)

                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                doc_state = (
                    docs_service.documents().get(documentId=doc_id).execute()
                )
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts = []
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
                                cell_idx = cell_content[0].get(
                                    "startIndex", 0
                                )
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append(
                                        (cell_idx, cell_text)
                                    )

                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cell_idx},
                                    "text": cell_text,
                                }
                            }
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                    doc_state2 = (
                        docs_service.documents()
                        .get(documentId=doc_id)
                        .execute()
                    )
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get("tableRows"):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si,
                                                    "endIndex": ei,
                                                },
                                                "textStyle": {"bold": True},
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                doc_state = (
                    docs_service.documents().get(documentId=doc_id).execute()
                )
                body_content = doc_state.get("body", {}).get("content", [])
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": "\n",
                        }
                    }
                )
                cursor += 1

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


def main() -> None:
    """Create or update the Google Doc."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update",
        metavar="DOC_ID",
        help="Update an existing Google Doc instead of creating a new one",
    )
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    oauth_path = (
        "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
    )
    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=SCOPES,
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    structure = build_document_structure()
    title = structure["title"]
    sections = _normalize_sections(structure, skip_toc=False)

    if args.update:
        # ── Update existing document ────────────────────────────────
        doc_id = args.update
        print(f"Updating existing Google Doc: {doc_id}")
        print(f"Sections: {len(sections)}")

        # Clear existing body content
        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get("body", {}).get("content", [])
        if body_content:
            end_index = body_content[-1].get("endIndex", 2) - 1
            if end_index > 1:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "deleteContentRange": {
                                    "range": {
                                        "startIndex": 1,
                                        "endIndex": end_index,
                                    }
                                }
                            }
                        ]
                    },
                ).execute()
                print("Cleared existing content")

        _render_content(docs_service, doc_id, sections)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc updated successfully!")
        print(f"URL: {docs_url}")

    else:
        # ── Create new document ─────────────────────────────────────
        print(f"Building Google Doc: {title}")
        print(f"Sections: {len(sections)}")

        doc = (
            docs_service.documents()
            .create(body={"title": title})
            .execute()
        )
        doc_id = doc["documentId"]
        print(f"Document created: {doc_id}")

        _render_content(docs_service, doc_id, sections)

        share_file_restricted(drive_service, doc_id)

        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc created successfully!")
        print(f"URL: {docs_url}")


if __name__ == "__main__":
    main()
