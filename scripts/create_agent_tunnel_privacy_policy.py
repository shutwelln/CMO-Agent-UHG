"""Create the Agent Tunnel (S2 Foundry LLC) Privacy Policy as a Google Doc.

Usage:
    python scripts/create_agent_tunnel_privacy_policy.py
    python scripts/create_agent_tunnel_privacy_policy.py --update ID
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the Privacy Policy document structure."""
    return {
        "title": "Agent Tunnel (S2 Foundry LLC) - Privacy Policy",
        "sections": [
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Privacy Policy\n\n"
                            "Effective Date: [DATE]\n\n"
                            "Legal Entity: S2 Foundry LLC"
                        ),
                    },
                ],
            },
            {
                "heading": "Introduction",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry LLC (\"S2 Foundry,\" \"we,\" "
                            "\"us,\" or \"our\") operates Agent Tunnel, "
                            "a desktop application and related services "
                            "available at agenttunnel.app. This Privacy "
                            "Policy explains how we collect, use, and "
                            "protect your information."
                        ),
                    },
                ],
            },
            {
                "heading": "Information We Collect",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Account information: Email address, name, "
                                "and payment information (processed and "
                                "stored by LemonSqueezy; we do not store "
                                "credit card numbers)"
                            ),
                            (
                                "Usage analytics: Feature usage patterns, "
                                "app performance data, crash reports, and "
                                "error logs (collected in aggregate to "
                                "improve the product)"
                            ),
                            (
                                "Cloudflare tunnel data: When you create "
                                "and manage tunnels through our app, we "
                                "process tunnel configuration data. We do "
                                "not inspect, log, or store the content of "
                                "traffic flowing through your tunnels."
                            ),
                            (
                                "Device information: Operating system "
                                "version, app version, and device type (Mac)"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "Information We Do NOT Collect",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "The content of traffic flowing through "
                                "your Cloudflare tunnels"
                            ),
                            "Files on your local machine",
                            "Source code or project data",
                            "Browsing history outside of Agent Tunnel",
                        ],
                    },
                ],
            },
            {
                "heading": "How We Use Your Information",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "To provide and maintain the Agent Tunnel "
                                "service"
                            ),
                            (
                                "To process your subscription payments "
                                "via LemonSqueezy"
                            ),
                            (
                                "To send transactional emails (account "
                                "confirmations, billing receipts)"
                            ),
                            "To improve app performance and fix bugs",
                            "To provide customer support",
                        ],
                    },
                ],
            },
            {
                "heading": "Third-Party Services",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "LemonSqueezy: Payment processing (see "
                                "LemonSqueezy's privacy policy)"
                            ),
                            (
                                "Cloudflare: Tunnel infrastructure (see "
                                "Cloudflare's privacy policy)"
                            ),
                            (
                                "Anthropic: AI processing (see Anthropic's "
                                "privacy policy)"
                            ),
                            (
                                "Analytics: We may use privacy-respecting "
                                "analytics to understand aggregate usage "
                                "patterns"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "Data Security",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We use industry-standard security measures "
                            "to protect your data, including encryption "
                            "in transit (HTTPS/TLS), secure "
                            "authentication, and access controls."
                        ),
                    },
                ],
            },
            {
                "heading": "Data Retention and Deletion",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We retain account data for as long as your "
                            "subscription is active. When you cancel, we "
                            "retain billing records as required by law "
                            "(typically 7 years for tax purposes) and "
                            "delete other personal data within 30 days "
                            "of your request."
                        ),
                    },
                ],
            },
            {
                "heading": "Your Rights",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Request a copy of your personal data",
                            "Request deletion of your personal data",
                            "Cancel your subscription at any time",
                        ],
                    },
                ],
            },
            {
                "heading": "Contact Us",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "S2 Foundry LLC\n"
                            "Email: privacy@agenttunnel.app"
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
