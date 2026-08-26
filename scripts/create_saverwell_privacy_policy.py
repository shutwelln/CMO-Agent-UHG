"""Create the Saverwell Holdings, LLC Privacy Policy as a Google Doc.

Usage:
    python scripts/create_saverwell_privacy_policy.py
    python scripts/create_saverwell_privacy_policy.py --update ID
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
        "title": "Saverwell Holdings, LLC - Privacy Policy",
        "sections": [
            {
                "heading": "",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Privacy Policy\n\n"
                            "Effective Date: January 1, 2026\n\n"
                            "Legal Entity: Saverwell Holdings, LLC"
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
                            'Saverwell Holdings, LLC ("we," "our," or "us") operates '
                            "the Saverwell website (the \"Service\"). This "
                            "Privacy Policy explains how we collect, use, "
                            "disclose, and safeguard your information when "
                            "you visit our website saverwell.com."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Please read this Privacy Policy carefully. By "
                            "using the Service, you agree to the collection "
                            "and use of information in accordance with this "
                            "policy."
                        ),
                    },
                ],
            },
            {
                "heading": "Information We Collect",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Personal Information",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "We may collect personal information that you "
                            "voluntarily provide to us, including:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Email address (when you create an account "
                                "or subscribe to our newsletter)"
                            ),
                            (
                                "ZIP code (to provide location-based "
                                "discount information)"
                            ),
                            "Account credentials (username and password)",
                            (
                                "Any other information you voluntarily "
                                "provide through forms or correspondence"
                            ),
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Automatically Collected Information",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "When you access our Service, we may "
                            "automatically collect certain information, "
                            "including:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "IP address and browser type",
                            "Pages viewed and time spent on pages",
                            "Device information and operating system",
                            "Referring website addresses",
                            (
                                "UTM parameters: campaign tracking data "
                                "from links you click to reach our site "
                                "(source, medium, campaign name)"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "Analytics and Marketing Tools",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We use the following third-party tools that "
                            "collect data on our behalf:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Google Analytics 4 (GA4): Collects page "
                                "views, session data, device information, "
                                "and approximate geographic location "
                                "(city/region level) to help us understand "
                                "how visitors use our site. See Google's "
                                "privacy policy at "
                                "https://policies.google.com/privacy"
                            ),
                            (
                                "Customer.io: Processes email delivery, "
                                "tracks email engagement (opens, clicks), "
                                "and records behavioral events for "
                                "personalized messaging. See Customer.io's "
                                "privacy policy at "
                                "https://customer.io/legal/privacy-policy"
                            ),
                            (
                                "Cloudflare: Provides security and "
                                "performance services. Cloudflare processes "
                                "visitor IP addresses, TLS fingerprints, "
                                "and bot scoring data before requests reach "
                                "our server. See Cloudflare's privacy "
                                "policy at "
                                "https://www.cloudflare.com/privacypolicy/"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "How We Use Your Information",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We use the information we collect to:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Provide, operate, and maintain our Service",
                            (
                                "Personalize your experience with "
                                "location-based discount information"
                            ),
                            (
                                "Send you newsletters and promotional "
                                "materials (with your consent)"
                            ),
                            (
                                "Respond to your comments, questions, and "
                                "requests"
                            ),
                            (
                                "Analyze usage patterns to improve our "
                                "Service"
                            ),
                            (
                                "Detect, prevent, and address technical "
                                "issues"
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "We Do Not Sell Your Personal Information",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We do not sell, rent, or trade your personal "
                            "information to third parties for their "
                            "marketing purposes."
                        ),
                    },
                ],
            },
            {
                "heading": "Sharing Your Information",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We may share your information in the following "
                            "situations:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Service Providers: We may share "
                                "information with third-party vendors who "
                                "perform services on our behalf, such as "
                                "email delivery, analytics, and hosting, "
                                "under contractual obligations to protect "
                                "your data."
                            ),
                            (
                                "Affiliate Partners: When you click through "
                                "to a third-party offer, the affiliate "
                                "partner receives only that you came from "
                                "Saverwell, not your personal information."
                            ),
                            (
                                "Legal Requirements: We may disclose "
                                "information if required by law or in "
                                "response to valid legal requests."
                            ),
                            (
                                "Business Transfers: In connection with a "
                                "merger, acquisition, or sale of assets, "
                                "your information may be transferred."
                            ),
                        ],
                    },
                ],
            },
            {
                "heading": "Cookies and Tracking Technologies",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We use cookies and similar tracking "
                            "technologies to track activity on our Service. "
                            "The types of cookies we use include:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Session cookies: Temporary cookies that "
                                "expire when you close your browser, used "
                                "for site functionality."
                            ),
                            (
                                "Persistent cookies: Remain on your device "
                                "for a set period, used to remember your "
                                "preferences."
                            ),
                            (
                                "Third-party cookies: Set by analytics and "
                                "marketing tools (such as Google Analytics) "
                                "to understand usage patterns."
                            ),
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "You can instruct your browser to refuse all "
                            "cookies or to indicate when a cookie is being "
                            "sent. You may also opt out of cookies through "
                            "our cookie consent banner."
                        ),
                    },
                ],
            },
            {
                "heading": "Data Retention",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We retain your personal information for as "
                            "long as your account is active or as needed "
                            "to provide you services. If you request "
                            "deletion of your data, we will process your "
                            "request within 30 days, except where we are "
                            "required by law to retain certain records."
                        ),
                    },
                ],
            },
            {
                "heading": "Third-Party Links",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Our Service may contain links to third-party "
                            "websites or services that are not operated by "
                            "us. We have no control over, and assume no "
                            "responsibility for, the content, privacy "
                            "policies, or practices of any third-party "
                            "sites or services."
                        ),
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
                            "We use administrative, technical, and physical "
                            "security measures to protect your personal "
                            "information, including HTTPS encryption, "
                            "secure hosting, and access controls. However, "
                            "no method of transmission over the Internet "
                            "is 100% secure, and we cannot guarantee "
                            "absolute security."
                        ),
                    },
                ],
            },
            {
                "heading": "Your Privacy Rights",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Depending on your location, you may have "
                            "certain rights regarding your personal "
                            "information:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Access your personal information",
                            "Correct inaccurate information",
                            "Request deletion of your information",
                            "Opt out of marketing communications",
                            "Withdraw consent where applicable",
                        ],
                    },
                ],
            },
            {
                "heading": "California Residents (CCPA)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "If you are a California resident, you have "
                            "additional rights under the California "
                            "Consumer Privacy Act (CCPA):"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            (
                                "Right to Know: You may request that we "
                                "disclose the categories and specific "
                                "pieces of personal information we have "
                                "collected about you."
                            ),
                            (
                                "Right to Delete: You may request that we "
                                "delete the personal information we have "
                                "collected about you."
                            ),
                            (
                                "Right to Opt Out of Sale: We do not sell "
                                "your personal information. If this changes "
                                "in the future, we will provide a \"Do Not "
                                "Sell My Personal Information\" link."
                            ),
                            (
                                "Right to Non-Discrimination: We will not "
                                "discriminate against you for exercising "
                                "any of your CCPA rights."
                            ),
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "To exercise any of these rights, please "
                            "contact us at info@saverwell.com."
                        ),
                    },
                ],
            },
            {
                "heading": "Children's Privacy",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Our Service is not intended for individuals "
                            "under the age of 18. We do not knowingly "
                            "collect personal information from children "
                            "under 18. If you become aware that a child "
                            "has provided us with personal information, "
                            "please contact us."
                        ),
                    },
                ],
            },
            {
                "heading": "Changes to This Privacy Policy",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "We may update our Privacy Policy from time to "
                            "time. We will notify you of any changes by "
                            "posting the new Privacy Policy on this page "
                            'and updating the "Effective Date" above.'
                        ),
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
                            "If you have any questions about this Privacy "
                            "Policy, please contact us at:\n\n"
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
