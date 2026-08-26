"""Create the Agent Tunnel IP Assignment Agreement as a Google Doc.

Usage:
    python scripts/create_ip_assignment_agreement.py
    python scripts/create_ip_assignment_agreement.py --update ID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the IP Assignment Agreement document structure."""
    return {
        "title": "IP Assignment Agreement - Agent Tunnel to S2 Foundry LLC",
        "sections": [
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "INTELLECTUAL PROPERTY ASSIGNMENT AGREEMENT\n\n"
                            "This Intellectual Property Assignment Agreement "
                            "(\"Agreement\") is entered into as of [DATE] "
                            "(\"Effective Date\") by and between:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "jhaw ventures LLC, a Wyoming limited "
                                "liability company (\"Assignor\"), acting "
                                "through its sole member Justin Shaw"
                            ),
                            (
                                "S2 Foundry LLC (\"Assignee\" or \"Company\"), "
                                "a Wisconsin limited liability company"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "Recitals",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "WHEREAS, the Assignor (through its sole member "
                            "Justin Shaw) has developed certain software known "
                            "as \"Agent Tunnel,\" a macOS desktop application "
                            "for managing Cloudflare tunnels, including all "
                            "associated source code, object code, "
                            "documentation, designs, user interfaces, "
                            "graphics, and related materials (collectively, "
                            "the \"Assigned IP\");"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "WHEREAS, the Assignor is a Member of S2 Foundry "
                            "LLC (holding a 50% Membership Interest through "
                            "jhaw ventures LLC) and desires to assign the "
                            "Assigned IP to the Company as part of the "
                            "Assignor's capital contribution and in "
                            "furtherance of the Company's business purposes;"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "WHEREAS, Nick Shutwell (holding a 50% Membership "
                            "Interest) is the other Member of S2 Foundry LLC "
                            "and consents to this assignment;"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "NOW, THEREFORE, in consideration of the mutual "
                            "covenants set forth herein and the Assignor's "
                            "Membership Interest in the Company, the parties "
                            "agree as follows:"
                        ),
                    },
                ],
            },
            {
                "heading": "1. Assignment",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Assignor hereby irrevocably assigns, "
                            "transfers, and conveys to the Company all right, "
                            "title, and interest in and to the Assigned IP, "
                            "including but not limited to:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "All source code, object code, and related "
                                "documentation for Agent Tunnel"
                            ),
                            "The domain name agenttunnel.app and all associated subdomains",
                            (
                                "All trademarks, service marks, and trade "
                                "dress associated with Agent Tunnel"
                            ),
                            "All copyrights in the software and documentation",
                            "All trade secrets and know-how related to Agent Tunnel",
                            (
                                "All customer lists, subscription data, and "
                                "business records related to Agent Tunnel"
                            ),
                            (
                                "All rights to sue for past, present, and "
                                "future infringement of any of the foregoing"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "2. Consideration",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This assignment is made in consideration of the "
                            "Assignor's 50% Membership Interest in S2 Foundry "
                            "LLC, as set forth in the Company's Operating "
                            "Agreement. The parties agree that this "
                            "consideration is adequate and sufficient."
                        ),
                    },
                ],
            },
            {
                "heading": "3. Pre-Formation Revenue",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All revenue generated by Agent Tunnel prior to "
                            "the formation date of S2 Foundry LLC remains the "
                            "property of the Assignor (jhaw ventures LLC / "
                            "Justin Shaw). This assignment applies only to the "
                            "IP itself, not to historical revenue or accounts "
                            "receivable predating the Effective Date."
                        ),
                    },
                ],
            },
            {
                "heading": "4. Payment Processor Migration",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Assignor acknowledges that Agent Tunnel's "
                            "payment processing (currently via LemonSqueezy "
                            "under the Assignor's account) will be migrated "
                            "to an account owned by S2 Foundry LLC. The "
                            "Assignor agrees to cooperate in this migration, "
                            "including transferring or re-creating product "
                            "and subscription objects as needed."
                        ),
                    },
                ],
            },
            {
                "heading": "5. Further Assurances",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Assignor agrees to execute any additional "
                            "documents and take any further actions reasonably "
                            "necessary to evidence or perfect this assignment, "
                            "including but not limited to domain transfer "
                            "confirmations, trademark assignment filings, and "
                            "copyright registration updates."
                        ),
                    },
                ],
            },
            {
                "heading": "6. Representations and Warranties",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Assignor represents and warrants that:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "(a) The Assignor (through Justin Shaw) is "
                                "the sole owner of the Assigned IP and has "
                                "full authority to make this assignment"
                            ),
                            (
                                "(b) The Assigned IP is free and clear of "
                                "all liens, encumbrances, security interests, "
                                "and claims of any third party"
                            ),
                            (
                                "(c) The Assigned IP does not, to the best of "
                                "the Assignor's knowledge, infringe any third "
                                "party's intellectual property rights"
                            ),
                            (
                                "(d) There are no pending or threatened claims "
                                "against the Assignor related to the Assigned IP"
                            ),
                            (
                                "(e) No third party has any license, right, "
                                "or interest in the Assigned IP other than "
                                "end-user subscription licenses granted in "
                                "the ordinary course of business"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "7. Indemnification",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Assignor agrees to indemnify, defend, and "
                            "hold harmless the Company and its Members from "
                            "any claims, damages, losses, or expenses "
                            "(including reasonable attorney's fees) arising "
                            "from any breach of the representations and "
                            "warranties in Section 6."
                        ),
                    },
                ],
            },
            {
                "heading": "8. Governing Law",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This Agreement shall be governed by and construed "
                            "in accordance with the laws of the State of "
                            "Wisconsin, without regard to its conflicts of "
                            "law principles. Any disputes arising under this "
                            "Agreement shall be resolved in the state or "
                            "federal courts located in Dane County, Wisconsin."
                        ),
                    },
                ],
            },
            {
                "heading": "9. Entire Agreement",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This Agreement, together with the S2 Foundry LLC "
                            "Operating Agreement, constitutes the entire "
                            "agreement between the parties with respect to "
                            "the subject matter hereof and supersedes all "
                            "prior negotiations, representations, and "
                            "agreements relating thereto."
                        ),
                    },
                ],
            },
            {
                "heading": "Signatures",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "IN WITNESS WHEREOF, the parties have executed "
                            "this Agreement as of the Effective Date."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "ASSIGNOR:\n\n"
                            "jhaw ventures LLC\n\n\n"
                            "___________________________________\n"
                            "Justin Shaw, Sole Member of jhaw ventures LLC\n"
                            "Date: _______________"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "ASSIGNEE:\n\n"
                            "S2 Foundry LLC\n\n\n"
                            "___________________________________\n"
                            "Nick Shutwell, Member of S2 Foundry LLC\n"
                            "Date: _______________"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "ACKNOWLEDGED AND CONSENTED TO:\n\n\n"
                            "___________________________________\n"
                            "Nick Shutwell, Member of S2 Foundry LLC\n"
                            "(in his capacity as the other Member "
                            "consenting to the IP contribution)\n"
                            "Date: _______________"
                        ),
                    },
                ],
            },
            {
                "heading": "Exhibit A: Description of Assigned IP",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The following constitutes the Assigned IP "
                            "being transferred under this Agreement:"
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            (
                                "Agent Tunnel application: A macOS desktop "
                                "application for creating and managing "
                                "Cloudflare tunnels, including all source "
                                "code (Swift/SwiftUI), configuration files, "
                                "build scripts, and related tooling"
                            ),
                            (
                                "Domain: agenttunnel.app and all associated "
                                "DNS records and subdomains"
                            ),
                            (
                                "Website: The marketing website at "
                                "agenttunnel.app, including all content, "
                                "design assets, and code"
                            ),
                            (
                                "Brand assets: The Agent Tunnel name, logo, "
                                "icon, and all associated brand materials"
                            ),
                            (
                                "Documentation: All user documentation, "
                                "technical documentation, and internal "
                                "development notes"
                            ),
                            (
                                "Customer data: All subscriber records, "
                                "subscription data, and customer "
                                "communications related to Agent Tunnel"
                            ),
                            (
                                "Third-party accounts: LemonSqueezy merchant "
                                "account (to be migrated), Cloudflare "
                                "integration credentials, and any other "
                                "third-party service accounts used "
                                "exclusively for Agent Tunnel"
                            ),
                        ],
                    },
                ],
            },
        ],
    }


def _render_content(docs_service, doc_id: str, sections: list) -> None:
    requests: list = []
    cursor = 1

    def _hs(level):
        return {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3"}.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        blocks = (
            [{"type": "heading", "text": heading, "level": level}] if heading else []
        ) + section.get("content", [])
        for block in blocks:
            bt = block.get("type", "paragraph")
            if bt == "heading":
                ht = block["text"] + "\n"
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": ht}}
                )
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": cursor,
                                "endIndex": cursor + len(ht),
                            },
                            "paragraphStyle": {
                                "namedStyleType": _hs(block["level"]),
                                "spaceAbove": {"magnitude": 12, "unit": "PT"},
                                "spaceBelow": {"magnitude": 4, "unit": "PT"},
                            },
                            "fields": "namedStyleType,spaceAbove,spaceBelow",
                        }
                    }
                )
                cursor += len(ht)
            elif bt == "paragraph":
                t = block.get("text", "")
                if not t:
                    continue
                pt = t + "\n"
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": pt}}
                )
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": cursor,
                                "endIndex": cursor + len(pt),
                            },
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {"magnitude": 6, "unit": "PT"},
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor += len(pt)
            elif bt == "bullets":
                items = block.get("items", [])
                if not items:
                    continue
                ls = cursor
                for item in items:
                    it = str(item) + "\n"
                    requests.append(
                        {"insertText": {"location": {"index": cursor}, "text": it}}
                    )
                    cursor += len(it)
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {"startIndex": ls, "endIndex": cursor},
                            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                        }
                    }
                )
            elif bt == "numbered_list":
                items = block.get("items", [])
                if not items:
                    continue
                ls = cursor
                for item in items:
                    it = str(item) + "\n"
                    requests.append(
                        {"insertText": {"location": {"index": cursor}, "text": it}}
                    )
                    cursor += len(it)
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {"startIndex": ls, "endIndex": cursor},
                            "bulletPreset": "NUMBERED_DECIMAL_NESTED",
                        }
                    }
                )

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", metavar="DOC_ID")
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
    )

    creds = get_google_credentials(
        oauth_token_path="/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json",
        service_account_path="",
        scopes=[
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)
    structure = build_document_structure()
    title = structure["title"]
    sections = _normalize_sections(structure, skip_toc=False)

    if args.update:
        doc_id = args.update
        print(f"Updating: {doc_id}")
        doc = docs_service.documents().get(documentId=doc_id).execute()
        bc = doc.get("body", {}).get("content", [])
        if bc:
            ei = bc[-1].get("endIndex", 2) - 1
            if ei > 1:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "deleteContentRange": {
                                    "range": {"startIndex": 1, "endIndex": ei}
                                }
                            }
                        ]
                    },
                ).execute()
        _render_content(docs_service, doc_id, sections)
        print(f"\nUpdated: https://docs.google.com/document/d/{doc_id}/edit")
    else:
        print(f"Building: {title}")
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        _render_content(docs_service, doc_id, sections)
        try:
            drive_service.permissions().create(
                fileId=doc_id,
                body={"type": "anyone", "role": "writer"},
                fields="id",
            ).execute()
        except Exception as e:
            print(f"Warning: {e}")
        fid = ensure_drive_folder(drive_service)
        if fid:
            move_file_to_folder(drive_service, doc_id, fid)
        print(f"\nCreated: https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()
