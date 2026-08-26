"""Create the Agent Tunnel (S2 Foundry LLC) Terms of Service as a Google Doc.

Usage:
    python scripts/create_agent_tunnel_terms_of_service.py
    python scripts/create_agent_tunnel_terms_of_service.py --update ID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the Terms of Service document structure."""
    return {
        "title": "Agent Tunnel (S2 Foundry LLC) - Terms of Service",
        "sections": [
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Terms of Service\n\n"
                            "Effective Date: [DATE]\n\n"
                            "Legal Entity: S2 Foundry LLC"
                        ),
                    },
                ],
            },
            {
                "heading": "1. Description of Service",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Agent Tunnel is a macOS desktop application "
                            "that simplifies the creation and management "
                            "of Cloudflare tunnels. It provides a "
                            "graphical interface for tunnel configuration, "
                            "monitoring, and management."
                        ),
                    },
                ],
            },
            {
                "heading": "2. Subscription and Payment",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Agent Tunnel is offered as a subscription "
                                "service at $15 per month."
                            ),
                            (
                                "Payment is processed by LemonSqueezy. By "
                                "subscribing, you authorize recurring "
                                "monthly charges."
                            ),
                            (
                                "You may cancel your subscription at any "
                                "time. Cancellation takes effect at the "
                                "end of the current billing period. No "
                                "refunds for partial months."
                            ),
                            (
                                "We may change pricing with 30 days' "
                                "notice. Existing subscribers will be "
                                "notified by email."
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "3. Acceptable Use",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "You agree to use Agent Tunnel only for "
                            "lawful purposes. You may not:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Use the service to facilitate any "
                                "illegal activity"
                            ),
                            (
                                "Attempt to reverse engineer, decompile, "
                                "or disassemble the application"
                            ),
                            "Share your account credentials with others",
                            (
                                "Use the service to circumvent security "
                                "measures of any system"
                            ),
                            (
                                "Use the service in a way that violates "
                                "Cloudflare's Terms of Service"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "4. Intellectual Property",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Agent Tunnel, including its code, design, "
                            "and documentation, is the property of S2 "
                            "Foundry LLC. Your subscription grants you a "
                            "limited, non-exclusive, non-transferable "
                            "license to use the application for its "
                            "intended purpose."
                        ),
                    },
                ],
            },
            {
                "heading": "5. Limitation of Liability",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "To the fullest extent permitted by law, S2 "
                            "Foundry LLC shall not be liable for any "
                            "indirect, incidental, special, consequential, "
                            "or punitive damages arising from your use of "
                            "Agent Tunnel. This includes, without "
                            "limitation, damages for loss of data, loss "
                            "of profits, business interruption, or any "
                            "other commercial damages."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Our total aggregate liability for any claim "
                            "related to Agent Tunnel shall not exceed the "
                            "total amount you paid for the service in the "
                            "12 months preceding the claim, or one hundred "
                            "dollars ($100), whichever is greater."
                        ),
                    },
                ],
            },
            {
                "heading": "6. Disclaimer of Warranties",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Agent Tunnel is provided \"as is\" and \"as "
                            "available.\" We make no warranties, express "
                            "or implied, regarding the reliability, "
                            "availability, or suitability of the service. "
                            "We do not guarantee uninterrupted or "
                            "error-free operation."
                        ),
                    },
                ],
            },
            {
                "heading": "7. Service Availability",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Agent Tunnel depends on Cloudflare's "
                            "infrastructure. We are not responsible for "
                            "Cloudflare outages, changes to Cloudflare's "
                            "API, or changes to Cloudflare's terms that "
                            "may affect Agent Tunnel's functionality."
                        ),
                    },
                ],
            },
            {
                "heading": "8. Indemnification",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "You agree to indemnify, defend, and hold "
                            "harmless S2 Foundry LLC and its members, "
                            "officers, and agents from any claims, "
                            "damages, losses, or expenses (including "
                            "reasonable attorney's fees) arising from "
                            "your use of Agent Tunnel, your violation "
                            "of these Terms, or your violation of any "
                            "third party's rights."
                        ),
                    },
                ],
            },
            {
                "heading": "9. Termination",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We may terminate or suspend your access to "
                            "Agent Tunnel at any time for violation of "
                            "these Terms, with notice where practical. "
                            "You may terminate your subscription at any "
                            "time by canceling through your account "
                            "settings."
                        ),
                    },
                ],
            },
            {
                "heading": "10. Governing Law",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "These Terms are governed by the laws of the "
                            "State of Wisconsin. Any disputes shall be "
                            "resolved in the state or federal courts "
                            "located in Dane County, Wisconsin."
                        ),
                    },
                ],
            },
            {
                "heading": "11. Contact",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry LLC\n"
                            "Email: support@agenttunnel.app"
                        ),
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
        for block in ([{"type": "heading", "text": heading, "level": level}] if heading else []) + section.get("content", []):
            bt = block.get("type", "paragraph")
            if bt == "heading":
                ht = block["text"] + "\n"
                requests.append({"insertText": {"location": {"index": cursor}, "text": ht}})
                requests.append({"updateParagraphStyle": {"range": {"startIndex": cursor, "endIndex": cursor + len(ht)}, "paragraphStyle": {"namedStyleType": _hs(block["level"]), "spaceAbove": {"magnitude": 12, "unit": "PT"}, "spaceBelow": {"magnitude": 4, "unit": "PT"}}, "fields": "namedStyleType,spaceAbove,spaceBelow"}})
                cursor += len(ht)
            elif bt == "paragraph":
                t = block.get("text", "")
                if not t:
                    continue
                pt = t + "\n"
                requests.append({"insertText": {"location": {"index": cursor}, "text": pt}})
                requests.append({"updateParagraphStyle": {"range": {"startIndex": cursor, "endIndex": cursor + len(pt)}, "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "spaceBelow": {"magnitude": 6, "unit": "PT"}}, "fields": "namedStyleType,spaceBelow"}})
                cursor += len(pt)
            elif bt == "bullets":
                items = block.get("items", [])
                if not items:
                    continue
                ls = cursor
                for item in items:
                    it = str(item) + "\n"
                    requests.append({"insertText": {"location": {"index": cursor}, "text": it}})
                    cursor += len(it)
                requests.append({"createParagraphBullets": {"range": {"startIndex": ls, "endIndex": cursor}, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})

    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", metavar="DOC_ID")
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import ensure_drive_folder, get_google_credentials, move_file_to_folder

    creds = get_google_credentials(oauth_token_path="/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json", service_account_path="", scopes=["https://www.googleapis.com/auth/documents", "https://www.googleapis.com/auth/drive.file"])
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
                docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": ei}}}]}).execute()
        _render_content(docs_service, doc_id, sections)
        print(f"\nUpdated: https://docs.google.com/document/d/{doc_id}/edit")
    else:
        print(f"Building: {title}")
        doc = docs_service.documents().create(body={"title": title}).execute()
        doc_id = doc["documentId"]
        _render_content(docs_service, doc_id, sections)
        try:
            drive_service.permissions().create(fileId=doc_id, body={"type": "anyone", "role": "writer"}, fields="id").execute()
        except Exception as e:
            print(f"Warning: {e}")
        fid = ensure_drive_folder(drive_service)
        if fid:
            move_file_to_folder(drive_service, doc_id, fid)
        print(f"\nCreated: https://docs.google.com/document/d/{doc_id}/edit")


if __name__ == "__main__":
    main()
