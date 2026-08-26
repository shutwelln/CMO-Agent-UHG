#!/usr/bin/env python3
"""Update the Saverwell Revenue & Monetization Plan Google Doc.

Marks the Phase 1 Claude Code deliverables as complete and adds a session
summary note. Uses Google Docs API replaceAllText for surgical updates.

Usage:  python scripts/update_monetization_doc.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from googleapiclient.discovery import build  # noqa: E402

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

DOC_ID = "1SEd3e_tgjB-gFpqj7NPbOf9etNLRBBrtCMX-LW46Ork"
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def get_docs_service():
    """Build Google Docs API service using OAuth (service account can't access Docs)."""
    creds = get_google_credentials(
        oauth_token_path=os.environ.get(
            "GOOGLE_OAUTH_TOKEN_PATH", "data/google-token.json"
        ),
        service_account_path="",  # Force OAuth - service account fails for Docs API
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: No Google credentials. Run scripts/reauth_google_drive.py first.")
        sys.exit(1)
    return build("docs", "v1", credentials=creds)


def main():
    service = get_docs_service()

    # ── Text replacements ────────────────────────────────────────────
    # These replace specific unchecked items with checked versions in the doc.
    # The doc likely uses Unicode or plain text checkboxes.

    replacements = [
        # Phase 2 content expansion items
        (
            "[ ] 8 expansion guides (medical alerts, hearing aids, phones)",
            "[x] 8 expansion guides generated and upserted to Supabase (draft)",
        ),
        (
            "[ ] SEO audit and cross-linking",
            "[x] SEO audit complete: Article JSON-LD, Twitter Cards, keywords meta, related guides rendering, cross-link fixes",
        ),
        (
            "[ ] AHS and AARP email drip templates",
            "[x] AHS 3-email drip + AARP 2-email drip created (data/saverwell/email_campaigns/)",
        ),
    ]

    requests = []
    for old_text, new_text in replacements:
        requests.append(
            {
                "replaceAllText": {
                    "containsText": {"text": old_text, "matchCase": True},
                    "replaceText": new_text,
                }
            }
        )

    # ── Apply replacements ───────────────────────────────────────────
    if requests:
        result = (
            service.documents()
            .batchUpdate(documentId=DOC_ID, body={"requests": requests})
            .execute()
        )
        total_replaced = sum(
            r.get("replaceAllText", {}).get("occurrencesChanged", 0)
            for r in result.get("replies", [])
        )
        print(f"Applied {len(requests)} replacement rules, {total_replaced} total matches.")
    else:
        print("No replacements to apply.")

    # ── Append session summary at end of doc ─────────────────────────
    # Read current doc to get end index
    doc = service.documents().get(documentId=DOC_ID).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1

    session_note = (
        "\n\n---\n"
        "Session Update (March 16, 2026)\n\n"
        "Phase 2 - Content Expansion (8 guides):\n"
        "- Generated 8 new guide articles across 3 verticals:\n"
        "  - Medical Alerts (4): fall detection, watches/wearables, Medicare coverage, no-monthly-fee\n"
        "  - Hearing Aids (2): OTC under $500, Medicare coverage\n"
        "  - Phones (2): free government phones, best flip phones for seniors\n"
        "- All 8 inserted to Supabase as drafts (publish_web=false, pending review)\n"
        "- Each has comparison tables ready for affiliate URL population\n\n"
        "Phase 3 - SEO Audit + Cross-linking:\n"
        "- Cloudflare Worker SEO enhancements (cloudflare-worker/src/index.ts):\n"
        "  - Article JSON-LD schema (@type: Article, author, datePublished, dateModified)\n"
        "  - Twitter Card meta tags (twitter:card, twitter:title, twitter:description)\n"
        "  - Keywords meta tag from seo_keywords array\n"
        "  - article:published_time / article:modified_time from DB timestamps\n"
        "  - Related Guides section: fetches titles for related_slugs, renders linked list\n"
        "  - State page cross-links: resolves featured_guide_slugs + featured_protection_slugs\n"
        "- Fixed 7 guides with broken related_slugs (hallucinated slugs replaced with real ones)\n"
        "- Created scripts/fix_guide_cross_links.py for ongoing link hygiene\n"
        "- Sitemap already comprehensive (no changes needed)\n"
        "- Remaining gap: og:image (needs featured image URLs in DB schema)\n\n"
        "Phase 4 - Email Drips:\n"
        "- AHS (American Home Shield) 3-email drip:\n"
        "  Email 1: The $8,000 repair bill, Email 2: Warranty vs insurance, Email 3: 5 questions before buying\n"
        "  Emails 2-3 include AHS affiliate CTAs with disclosure\n"
        "- AARP 2-email drip:\n"
        "  Email 1: Is AARP worth $16/year, Email 2: 12 hidden discounts\n"
        "  Email 2 includes AARP join affiliate CTA with disclosure\n"
        "- Both in data/saverwell/email_campaigns/ ready for Customer.io deployment\n\n"
        "Next steps:\n"
        "- Human: Submit affiliate applications from prioritized checklist\n"
        "- Human: Review and publish 8 expansion guide drafts\n"
        "- Deploy Cloudflare Worker (npx wrangler deploy) for SEO enhancements\n"
        "- Run populate_affiliate_urls.py as partner approvals come in\n"
        "- Run populate_guide_affiliate_links.py after URLs are populated\n"
        "- Phase 5 optimization: A/B testing, Medicare AEP seasonal content\n"
    )

    append_requests = [
        {"insertText": {"location": {"index": end_index}, "text": session_note}}
    ]

    service.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": append_requests}
    ).execute()

    print(f"\nSession summary appended to doc.")
    print(f"Doc: https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
