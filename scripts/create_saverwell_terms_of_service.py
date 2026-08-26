"""Create the Saverwell Holdings, LLC Terms of Service as a Google Doc.

Usage:
    python scripts/create_saverwell_terms_of_service.py
    python scripts/create_saverwell_terms_of_service.py --update ID
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
        "title": "Saverwell Holdings, LLC - Terms of Service",
        "sections": [
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Terms of Service\n\n"
                            "Effective Date: January 1, 2026\n\n"
                            "Legal Entity: Saverwell Holdings, LLC"
                        ),
                    },
                ],
            },
            {
                "heading": "1. Acceptance of Terms",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "By accessing or using the Saverwell website "
                            "(the \"Service\") operated by Saverwell Holdings, LLC "
                            "(\"we,\" \"us,\" or \"our\"), you agree to be "
                            "bound by these Terms and Conditions. If you "
                            "do not agree to these terms, please do not "
                            "use our Service."
                        ),
                    },
                ],
            },
            {
                "heading": "2. Description of Service",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Saverwell provides educational content, "
                            "discount directories, product and service "
                            "comparisons, guides, newsletters, and "
                            "related resources for adults, with a focus "
                            "on seniors. Our services include a website, "
                            "email communications, and related digital "
                            "properties."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The selection, arrangement, verification, and "
                            "presentation of all content on this Service, "
                            "including discount information, editorial "
                            "content, and data compilations, is proprietary "
                            "to Saverwell Holdings, LLC."
                        ),
                    },
                ],
            },
            {
                "heading": "3. Informational Purposes Only",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The information provided through this Service "
                            "is for general informational and educational "
                            "purposes only. It does not constitute "
                            "professional financial, medical, legal, or "
                            "insurance advice. Discount details, Medicare "
                            "information, fraud protection guidance, and "
                            "all other content on this Service should not "
                            "be relied upon as a substitute for "
                            "consultation with qualified professionals. "
                            "Always consult with appropriate professionals "
                            "regarding your specific situation before "
                            "making financial, medical, or legal decisions."
                        ),
                    },
                ],
            },
            {
                "heading": "4. User Accounts",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "To access certain features of the Service, "
                            "you may need to create an account. You are "
                            "responsible for:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Providing accurate and complete information "
                                "during registration"
                            ),
                            (
                                "Maintaining the security of your account "
                                "credentials"
                            ),
                            "All activities that occur under your account",
                            (
                                "Notifying us immediately of any "
                                "unauthorized use of your account"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "5. Accuracy of Information",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "While we strive to provide accurate and "
                            "up-to-date information about senior discounts, "
                            "we cannot guarantee the accuracy, "
                            "completeness, or reliability of any discount "
                            "information displayed on our Service. Discount "
                            "offers are subject to change at the discretion "
                            "of individual retailers without notice."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "You should always verify discount terms "
                            "directly with the retailer before making "
                            "purchasing decisions."
                        ),
                    },
                ],
            },
            {
                "heading": "6. Third-Party Content and Links",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Our Service may contain links to third-party "
                            "websites or services. We are not responsible "
                            "for:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "The content, accuracy, or opinions "
                                "expressed on third-party sites"
                            ),
                            "The privacy practices of third-party sites",
                            "Products or services offered by third parties",
                        ],
                    },
                ],
            },
            {
                "heading": "7. Intellectual Property",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Service and its original content, "
                            "features, and functionality are owned by "
                            "Saverwell Holdings, LLC and are protected by "
                            "international copyright, trademark, and other "
                            "intellectual property laws."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The compilation, organization, and arrangement "
                            "of all content on the Service, including but "
                            "not limited to merchant discount data, store "
                            "locations, eligibility requirements, and "
                            "database records, represents significant "
                            "investment by Saverwell Holdings, LLC and constitutes a "
                            "protectable database under applicable law, "
                            "including copyright protection for "
                            "compilations under 17 U.S.C. \u00a7 103."
                        ),
                    },
                ],
            },
            {
                "heading": "8. Prohibited Uses",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "You agree not to use the Service:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "For any unlawful purpose or in violation "
                                "of any laws"
                            ),
                            "To harass, abuse, or harm another person",
                            "To impersonate any person or entity",
                            (
                                "To interfere with or disrupt the Service "
                                "or servers"
                            ),
                            (
                                "To transmit any viruses, malware, or "
                                "malicious code"
                            ),
                            (
                                "To use any automated system, including "
                                "without limitation robots, spiders, "
                                "scrapers, data mining tools, browser "
                                "extensions, AI agents, or similar data "
                                "gathering or extraction methods, to access "
                                "the Service for any purpose"
                            ),
                            (
                                "To collect, harvest, compile, or copy "
                                "information or data from the Service, "
                                "including but not limited to merchant "
                                "names, discount details, discount values, "
                                "eligibility requirements, store locations, "
                                "or any database content, whether manually "
                                "or through automated means"
                            ),
                            (
                                "To use data obtained from the Service to "
                                "build, augment, train, or contribute to a "
                                "competing product, service, database, or "
                                "machine learning model"
                            ),
                            (
                                "To circumvent or attempt to circumvent "
                                "any access restrictions, rate limits, bot "
                                "detection, CAPTCHAs, or security measures "
                                "implemented on the Service"
                            ),
                            (
                                "To access the Service through any "
                                "interface other than the standard web "
                                "browser interface provided by us"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "9. Remedies for Prohibited Use",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Any unauthorized use of automated means to "
                            "access the Service or collect data constitutes "
                            "a violation of these Terms and may violate "
                            "applicable laws, including the Computer Fraud "
                            "and Abuse Act (18 U.S.C. \u00a7 1030) and "
                            "state computer fraud statutes. Saverwell Holdings, LLC "
                            "reserves the right to: (a) immediately "
                            "terminate access for any user or IP address "
                            "engaging in prohibited activities without "
                            "prior notice; (b) pursue injunctive relief "
                            "and monetary damages, including statutory "
                            "damages where available; (c) report violations "
                            "to appropriate law enforcement authorities; "
                            "(d) cooperate with other companies and "
                            "industry groups to identify and prevent "
                            "scraping activities; and (e) use technical "
                            "measures, including but not limited to rate "
                            "limiting, bot detection, and access blocking, "
                            "to enforce these Terms."
                        ),
                    },
                ],
            },
            {
                "heading": "10. Affiliate Disclosure",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This website may include promotions, "
                            "referrals, or links to products or services "
                            "offered by third-party providers. Saverwell "
                            "LLC may receive compensation from these "
                            "providers when you make purchases through our "
                            "links. Affiliate relationships do not "
                            "influence our editorial content."
                        ),
                    },
                ],
            },
            {
                "heading": "11. Disclaimer of Warranties",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Service is provided \"as is\" and \"as "
                            "available\" without warranties of any kind, "
                            "either express or implied, including implied "
                            "warranties of merchantability, fitness for a "
                            "particular purpose, and non-infringement. We "
                            "do not warrant that the Service will be "
                            "uninterrupted, secure, or error-free."
                        ),
                    },
                ],
            },
            {
                "heading": "12. Limitation of Liability",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "To the maximum extent permitted by law, "
                            "Saverwell Holdings, LLC shall not be liable for any "
                            "indirect, incidental, special, consequential, "
                            "or punitive damages arising from your use of "
                            "the Service. Our total aggregate liability "
                            "for any claim related to the Service shall "
                            "not exceed the total amount paid by you to us "
                            "in the 12 months preceding the claim, or one "
                            "hundred dollars ($100), whichever is greater."
                        ),
                    },
                ],
            },
            {
                "heading": "13. Indemnification",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "You agree to defend, indemnify, and hold "
                            "harmless Saverwell Holdings, LLC from any claims, "
                            "damages, obligations, losses, or expenses "
                            "arising from your use of the Service or "
                            "violation of these Terms."
                        ),
                    },
                ],
            },
            {
                "heading": "14. Class Action Waiver",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "You agree that any claims arising out of or "
                            "related to these Terms or the Service will be "
                            "brought in your individual capacity only, and "
                            "not as a plaintiff or class member in any "
                            "purported class, collective, or "
                            "representative proceeding."
                        ),
                    },
                ],
            },
            {
                "heading": "15. Modifications to Terms",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We reserve the right to modify these Terms "
                            "at any time. We will notify users of "
                            "significant changes by posting a notice on "
                            "our Service. Your continued use of the "
                            "Service after changes constitutes acceptance "
                            "of the new Terms."
                        ),
                    },
                ],
            },
            {
                "heading": "16. Termination",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We may terminate or suspend your account and "
                            "access to the Service immediately, without "
                            "prior notice, for any reason, including "
                            "breach of these Terms."
                        ),
                    },
                ],
            },
            {
                "heading": "17. Governing Law and Dispute Resolution",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "These Terms shall be governed by and construed "
                            "in accordance with the laws of the State of "
                            "Wisconsin, without regard to conflict of law "
                            "principles. Any disputes arising under or in "
                            "connection with these Terms shall be resolved "
                            "exclusively in the state or federal courts "
                            "located in Dane County, Wisconsin. You "
                            "consent to the personal jurisdiction and "
                            "venue of such courts."
                        ),
                    },
                ],
            },
            {
                "heading": "18. Contact Information",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "If you have any questions about these Terms, "
                            "please contact us at:\n\n"
                            "Saverwell Holdings, LLC\n"
                            "Email: info@saverwell.com"
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
        share_file_restricted(drive_service, doc_id)
        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print(f"\nGoogle Doc created: {docs_url}")


if __name__ == "__main__":
    main()
