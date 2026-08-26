"""Create the Saverwell Holdings, LLC Operating Agreement as a Google Doc.

Usage:
    python scripts/create_saverwell_operating_agreement.py
    python scripts/create_saverwell_operating_agreement.py --update ID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the Saverwell Holdings Operating Agreement."""
    return {
        "title": (
            "Saverwell Holdings, LLC - Operating Agreement"
        ),
        "sections": [
            # Preamble
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "OPERATING AGREEMENT OF "
                            "SAVERWELL HOLDINGS, LLC"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "A Wisconsin Limited Liability Company"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This Operating Agreement (\"Agreement\") "
                            "of Saverwell Holdings, LLC (the "
                            "\"Company\") is entered into as of "
                            "[DATE] by the sole Member identified "
                            "below."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "IMPORTANT: This is a draft prepared as "
                            "a working starting point. Consider "
                            "having an attorney review before "
                            "signing, though a single-member "
                            "Operating Agreement is relatively low "
                            "risk."
                        ),
                    },
                ],
            },
            # Article I
            {
                "heading": "Article I: Formation",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "1.1 Formation. The Member has formed "
                            "Saverwell Holdings, LLC as a Wisconsin "
                            "limited liability company by filing "
                            "Articles of Organization with the "
                            "Wisconsin Department of Financial "
                            "Institutions."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.2 Name. The name of the Company is "
                            "Saverwell Holdings, LLC."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.3 Purpose. The Company is formed to "
                            "operate a consumer-facing content, "
                            "data, and affiliate platform, and to "
                            "engage in any other lawful business "
                            "activity."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.4 Term. The Company shall continue "
                            "until dissolved by the Member."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.5 Registered Agent. The registered "
                            "agent of the Company is Resident "
                            "Agents Inc. (Fict Name) / Registered "
                            "Agents Inc. (Corp Name), located at "
                            "2800 E. Enterprise Ave, STE 333, "
                            "Appleton, WI 54913."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "1.6 Principal Office. The principal "
                            "office of the Company is at 2800 E. "
                            "Enterprise Ave, STE 333, Appleton, "
                            "WI 54913, or such other location as "
                            "the Member may designate."
                        ),
                    },
                ],
            },
            # Article II
            {
                "heading": "Article II: Member",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "2.1 Sole Member. Nick Shutwell is the "
                            "sole Member of the Company, holding "
                            "100% of the Membership Interest."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "2.2 Management. The Company shall be "
                            "member-managed. The Member has full "
                            "authority to manage the business and "
                            "affairs of the Company."
                        ),
                    },
                ],
            },
            # Article III
            {
                "heading": "Article III: Capital Contributions",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "3.1 Initial Contribution. The Member "
                            "has contributed the following as the "
                            "initial capital contribution to the "
                            "Company:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "The Saverwell brand, including all "
                                "trademarks and trade dress"
                            ),
                            (
                                "The domain saverwell.com and all "
                                "associated subdomains"
                            ),
                            (
                                "The Saverwell website, codebase, "
                                "and all content"
                            ),
                            (
                                "The merchant discount database and "
                                "all associated data"
                            ),
                            (
                                "All email subscriber lists and "
                                "customer data"
                            ),
                            "[CASH AMOUNT, if any]",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "3.2 Additional Contributions. The "
                            "Member may make additional "
                            "contributions at any time at the "
                            "Member's sole discretion."
                        ),
                    },
                ],
            },
            # Article IV
            {
                "heading": (
                    "Article IV: Profits, Losses & Distributions"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "4.1 Allocation. All profits and losses "
                            "of the Company are allocated to the "
                            "sole Member."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "4.2 Distributions. The Member may take "
                            "distributions (owner draws) at any "
                            "time and in any amount, provided that "
                            "the Company maintains reasonable cash "
                            "reserves to meet its obligations and "
                            "foreseeable expenses."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "4.3 Tax Treatment. The Company shall "
                            "be treated as a disregarded entity for "
                            "federal and state income tax purposes. "
                            "All income, deductions, and credits "
                            "flow through to the Member's personal "
                            "tax return (Schedule C, Form 1040)."
                        ),
                    },
                ],
            },
            # Article V
            {
                "heading": "Article V: Intellectual Property",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "5.1 Company IP. The Company owns the "
                            "following intellectual property:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "The Saverwell brand name, logos, "
                                "and trade dress"
                            ),
                            (
                                "The domain saverwell.com and all "
                                "associated subdomains"
                            ),
                            (
                                "All website content, articles, "
                                "guides, and editorial material"
                            ),
                            (
                                "The merchant discount database "
                                "and all associated data "
                                "compilations"
                            ),
                            (
                                "All user data collected through "
                                "Saverwell services"
                            ),
                            (
                                "All software, tools, and "
                                "technology developed for "
                                "Saverwell operations"
                            ),
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "5.2 Excluded IP. The CMO Agent system "
                            "(the AI marketing automation codebase) "
                            "is the personal property of the Member "
                            "and is not assigned to the Company. "
                            "The Member may use the CMO Agent "
                            "system to operate Saverwell but "
                            "retains all rights to it."
                        ),
                    },
                ],
            },
            # Article VI
            {
                "heading": (
                    "Article VI: Liability & Indemnification"
                ),
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "6.1 Limited Liability. The Member "
                            "shall not be personally liable for the "
                            "debts, obligations, or liabilities of "
                            "the Company, except as required by law."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "6.2 Indemnification. The Company shall "
                            "indemnify the Member against any "
                            "losses arising from actions taken in "
                            "good faith on behalf of the Company "
                            "and within the scope of authority "
                            "granted by this Agreement."
                        ),
                    },
                ],
            },
            # Article VII
            {
                "heading": "Article VII: Dissolution",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "7.1 Dissolution. The Company shall be "
                            "dissolved upon: (a) the written "
                            "election of the Member, (b) the entry "
                            "of a decree of judicial dissolution, "
                            "or (c) any event that makes it "
                            "unlawful for the Company to continue."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "7.2 Winding Up. Upon dissolution, the "
                            "Company shall pay all debts and "
                            "obligations, and distribute remaining "
                            "assets to the Member."
                        ),
                    },
                ],
            },
            # Article VIII
            {
                "heading": "Article VIII: General Provisions",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "8.1 Amendments. This Agreement may be "
                            "amended at any time by the written "
                            "consent of the Member."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.2 Governing Law. This Agreement "
                            "shall be governed by the laws of the "
                            "State of Wisconsin."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.3 Severability. If any provision of "
                            "this Agreement is held invalid, the "
                            "remaining provisions remain in full "
                            "force."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "8.4 Entire Agreement. This Agreement "
                            "constitutes the entire agreement of "
                            "the Member with respect to the "
                            "Company."
                        ),
                    },
                ],
            },
            # Signature
            {
                "heading": "Signature",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "IN WITNESS WHEREOF, the sole Member "
                            "has executed this Operating Agreement "
                            "as of the date first written above."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "\n\n"
                            "___________________________________\n"
                            "Nick Shutwell, Sole Member\n"
                            "Date: _______________"
                        ),
                    },
                ],
            },
        ],
    }


def _render_content(docs_service, doc_id: str, sections: list) -> None:
    """Render sections into the Google Doc body."""
    requests: list = []
    cursor = 1

    def _heading_style(level: int) -> str:
        return {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3"}.get(
            level, "HEADING_1"
        )

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

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
                        "range": {"startIndex": h_start, "endIndex": h_end},
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
                            "range": {"startIndex": p_start, "endIndex": p_end},
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {"magnitude": 6, "unit": "PT"},
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor = p_end

            elif block_type == "bullets":
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

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


def main() -> None:
    """Create or update the Google Doc."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--update", metavar="DOC_ID",
        help="Update an existing Google Doc instead of creating a new one",
    )
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
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
        doc_id = args.update
        print(f"Updating existing Google Doc: {doc_id}")
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
        _render_content(docs_service, doc_id, sections)
        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc updated: {docs_url}")
    else:
        print(f"Building Google Doc: {title}")
        doc = (
            docs_service.documents()
            .create(body={"title": title})
            .execute()
        )
        doc_id = doc["documentId"]
        print(f"Document created: {doc_id}")
        _render_content(docs_service, doc_id, sections)
        try:
            drive_service.permissions().create(
                fileId=doc_id,
                body={"type": "anyone", "role": "writer"},
                fields="id",
            ).execute()
        except Exception as e:
            print(f"Warning: Could not share document: {e}")
        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc created: {docs_url}")


if __name__ == "__main__":
    main()
