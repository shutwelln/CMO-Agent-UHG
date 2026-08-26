#!/usr/bin/env python3
"""Populate the Saverwell Content Queue Google Sheet with all ~100 articles.

Reads:
  - 91 guide JSONs from data/saverwell/guide_drafts/
  - 28 protection articles from data/saverwell/protection_article_archive.txt
  - Existing 33 rows from the Content Queue sheet (preserves them)

Adds missing articles with expanded columns. Creates a new Subscriber Timeline tab.

Usage:
  python scripts/populate_content_queue.py           # dry run
  python scripts/populate_content_queue.py --apply    # write to sheet
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

SHEET_ID = "1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE"
GUIDE_DRAFTS_DIR = project_root / "data" / "saverwell" / "guide_drafts"
PROTECTION_ARCHIVE = project_root / "data" / "saverwell" / "protection_article_archive.txt"
TEMPLATES_DIR = project_root / "data" / "saverwell" / "email_templates"

# --- Vertical to content_vertical mapping ---
VERTICAL_MAP = {
    "1A-medicare": "Medicare & Health",
    "1B-insurance": "Insurance",
    "2A-medical-alerts": "Medical Alerts",
    "2B-phones": "Phones & Telecom",
    "2C-hearing-aids": "Hearing Aids",
    "3A-finance": "Finance & Retirement",
    "5-protection": "Fraud & Protection",
    "6-discounts": "Discounts & Shopping",
    "7-caregiving": "Family Caregiving",
    "SEO-finance": "Finance & Retirement",
    "SEO-medicare": "Medicare & Health",
    "SEO2-finance": "Finance & Retirement",
    "SEO2-insurance": "Insurance",
    "SEO3-finance": "Finance & Retirement",
    "SEO4-finance": "Finance & Retirement",
    "SEO4-medicare": "Medicare & Health",
}

# --- New category URL mapping (vertical code → URL category slug) ---
# Updated to match regrouped guide categories (Mar 2026)
CATEGORY_URL_MAP: Dict[str, str] = {
    "1A-medicare": "medicare",
    "1B-insurance": "insurance",
    "2A-medical-alerts": "senior-products",
    "2B-phones": "senior-products",
    "2C-hearing-aids": "senior-products",
    "3A-finance": "retirement-taxes",  # default for finance; overridden below
    "5-protection": "protection",  # uses /protection/article/ path, not /guides/
    "6-discounts": "saving-money",
    "7-caregiving": "caregiving",
    "SEO-finance": "retirement-taxes",
    "SEO-medicare": "medicare",
    "SEO2-finance": "retirement-taxes",
    "SEO2-insurance": "insurance",
    "SEO3-finance": "retirement-taxes",
    "SEO4-finance": "retirement-taxes",
    "SEO4-medicare": "medicare",
}

# Finance articles that belong in /guides/saving-money/ instead of /guides/retirement-taxes/
SAVING_MONEY_SLUGS: Set[str] = {
    "beginner-saver-guide-retirees",
    "free-budgeting-tools-retirees",
    "monthly-subscription-audit-retirees",
    "hidden-monthly-drains-retirees",
    "what-seniors-actually-cut-first",
    "why-retirees-quit-budgeting-apps",
    "permission-to-spend-in-retirement",
    "dont-pay-it-back-yet-checklist",
    "unexpected-cost-survival-playbook",
    "late-life-marriage-benefits-guide",
}


def _compute_article_url(slug: str, vertical: str) -> str:
    """Compute the canonical article URL using the new category structure."""
    if vertical == "5-protection":
        return f"/protection/article/{slug}"

    category = CATEGORY_URL_MAP.get(vertical, "")
    if not category:
        return f"/guides/{slug}"

    # Override finance articles that belong in saving-money
    if category == "retirement-taxes" and slug in SAVING_MONEY_SLUGS:
        category = "saving-money"

    return f"/guides/{category}/{slug}"


# --- Partner slug mapping (by vertical or specific slug) ---
PARTNER_SLUG_MAP: Dict[str, str] = {
    # By slug (specific articles with known partner matches)
}

PARTNER_BY_VERTICAL: Dict[str, str] = {
    "2A-medical-alerts": "adt",
    "2C-hearing-aids": "hear_com",
}

# --- Drip assignment mapping ---
DRIP_ASSIGNMENTS: Dict[str, str] = {
    # Core Foundations
    "safe-online-shopping-tips": "core_foundations_01",
    "password-safety-guide": "core_foundations_02",
    "senior-scam-protection-complete-guide": "core_foundations_03",
    "cell-phone-plans-seniors": "core_foundations_04",
    "medical-alert-systems-guide": "core_foundations_05",
    "when-to-claim-social-security": "core_foundations_06",
}

# --- Email template file mapping ---
TEMPLATE_FILE_MAP: Dict[str, str] = {}


def _scan_templates() -> None:
    """Build template file map from existing email template files."""
    if not TEMPLATES_DIR.exists():
        return
    for f in TEMPLATES_DIR.glob("*.html"):
        if f.name.startswith("layout_") or f.name.startswith("snippet_"):
            continue
        # Extract slug from filename: drip_protection_01_safe-online-shopping-tips.html
        match = re.match(r"^.+?_\d+_(.+)\.html$", f.name)
        if match:
            slug = match.group(1)
            TEMPLATE_FILE_MAP[slug] = f.name


def _parse_protection_articles() -> List[Dict[str, Any]]:
    """Parse protection articles from the archive text file."""
    if not PROTECTION_ARCHIVE.exists():
        print(f"  Warning: {PROTECTION_ARCHIVE} not found, skipping protection articles")
        return []

    text = PROTECTION_ARCHIVE.read_text(encoding="utf-8")
    articles = []
    # Split on ### slug-name pattern
    blocks = re.split(r"\n### ", text)
    for block in blocks[1:]:  # skip header
        lines = block.strip().split("\n")
        slug = lines[0].strip()
        title = ""
        for line in lines[1:10]:
            if line.startswith("Title: "):
                title = line[7:].strip()

        articles.append(
            {
                "slug": slug,
                "title": title,
                "content_type": "protection",
                "vertical": "5-protection",
                "content_vertical": "Fraud & Protection",
                "monetization_type": "informational",
                "affiliate_disclosure": False,
                "article_url": f"/protection/article/{slug}",
                "base_priority": 5,
                "send_day": "tuesday",
            }
        )

    return articles


def _parse_guide_articles() -> List[Dict[str, Any]]:
    """Parse guide articles from JSON draft files."""
    if not GUIDE_DRAFTS_DIR.exists():
        print(f"  Warning: {GUIDE_DRAFTS_DIR} not found, skipping guide articles")
        return []

    articles = []
    for f in sorted(GUIDE_DRAFTS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            print(f"  Warning: Could not parse {f.name}: {exc}")
            continue

        slug = data.get("slug", f.stem)
        vertical = data.get("vertical", "")
        content_vertical = VERTICAL_MAP.get(vertical, "Other")
        monetization_type = data.get("monetization_type", "informational")
        affiliate = data.get("affiliate_disclosure", False)
        email_url = _compute_article_url(slug, vertical)

        # Determine base priority from vertical and monetization
        base_priority = 5
        if vertical.startswith("1A"):  # Medicare
            base_priority = 7
        elif vertical.startswith("1B"):  # Insurance
            base_priority = 6
        elif vertical.startswith("2A"):  # Medical alerts
            base_priority = 6
        elif vertical.startswith("2B"):  # Phones
            base_priority = 6
        elif vertical.startswith("2C"):  # Hearing aids
            base_priority = 5
        elif vertical.startswith("3A"):  # Finance
            base_priority = 6
        elif vertical.startswith("5"):  # Protection (guides)
            base_priority = 5
        elif vertical.startswith("6"):  # Discounts
            base_priority = 5
        elif vertical.startswith("7"):  # Caregiving
            base_priority = 4

        # Affiliate articles get a small priority bump
        if monetization_type == "affiliate":
            base_priority = min(base_priority + 1, 10)

        articles.append(
            {
                "slug": slug,
                "title": data.get("title", slug),
                "content_type": "guide",
                "vertical": vertical,
                "content_vertical": content_vertical,
                "monetization_type": monetization_type,
                "affiliate_disclosure": affiliate,
                "article_url": email_url,
                "base_priority": base_priority,
                "send_day": "tuesday" if vertical == "5-protection" else "thursday",
            }
        )

    return articles


def _determine_partner_slug(slug: str, vertical: str) -> str:
    """Determine the partner slug for an article."""
    if slug in PARTNER_SLUG_MAP:
        return PARTNER_SLUG_MAP[slug]
    return PARTNER_BY_VERTICAL.get(vertical, "")


def _determine_monetization_tier(monetization_type: str, affiliate: bool) -> str:
    """Determine monetization tier: none, low, medium, high."""
    if monetization_type == "affiliate" and affiliate:
        return "high"
    elif monetization_type == "lead_gen":
        return "medium"
    elif monetization_type == "informational":
        return "none"
    return "low"


def build_article_rows(
    existing_slugs: Set[str],
) -> Tuple[List[List[str]], List[Dict[str, Any]]]:
    """Build rows for all articles, preserving existing entries."""
    _scan_templates()

    all_articles: List[Dict[str, Any]] = []
    seen_slugs: Set[str] = set()

    # Protection articles
    for art in _parse_protection_articles():
        if art["slug"] not in seen_slugs:
            all_articles.append(art)
            seen_slugs.add(art["slug"])

    # Guide articles
    for art in _parse_guide_articles():
        if art["slug"] not in seen_slugs:
            all_articles.append(art)
            seen_slugs.add(art["slug"])

    # Build rows
    rows = []
    new_articles = []
    for art in all_articles:
        slug = art["slug"]
        partner = _determine_partner_slug(slug, art["vertical"])
        tier = _determine_monetization_tier(art["monetization_type"], art["affiliate_disclosure"])
        drip = DRIP_ASSIGNMENTS.get(slug, "broadcast_pool")
        template = TEMPLATE_FILE_MAP.get(slug, "")
        is_new = slug not in existing_slugs

        row = [
            slug,
            art["title"],
            art["content_type"],
            art["vertical"],
            art["content_vertical"],
            str(art["base_priority"]),
            art["send_day"],
            "",  # seasonal_boost_start
            "",  # seasonal_boost_end
            "",  # seasonal_boost_amount
            tier,
            str(art["affiliate_disclosure"]).upper(),
            partner,
            art["article_url"],
            drip,
            template,
            "TRUE",  # email_ready
            "0",  # total_sends
            "",  # notes
        ]
        rows.append(row)
        if is_new:
            new_articles.append(art)

    return rows, new_articles


def build_subscriber_timeline() -> List[List[str]]:
    """Build the Subscriber Timeline tab data."""
    headers = ["Week", "Day", "Type", "Content", "Seasonal"]
    rows = [headers]

    # Welcome Flow (Weeks 1-2)
    rows.append(["1", "Day 0", "Welcome", "Welcome to Saverwell - Savings and Protection", ""])
    rows.append(["1", "Day 3", "Welcome", "3 Discounts Most Seniors Don't Know About", ""])
    rows.append(["1", "Day 6", "Welcome", "Shop Online Safely: Protect Your Money", ""])
    rows.append(["2", "Day 10", "Welcome", "7 Ways to Cut Your Medicare Premiums", ""])
    rows.append(["2", "Day 14", "Welcome", "Your First Weekly Digest Is Ready", ""])

    # Core Foundations (Weeks 3-8) + Digest
    foundations = [
        ("3", "Safe Online Shopping Tips"),
        ("4", "Password Safety Guide"),
        ("5", "Senior Scam Protection Complete Guide"),
        ("6", "Cell Phone Plans for Seniors"),
        ("7", "Medical Alert Systems Guide"),
        ("8", "When to Claim Social Security"),
    ]
    for week, article in foundations:
        rows.append([week, "Mon", "Digest", f"Weekly Digest #{int(week) - 2}", ""])
        rows.append([week, "Tue", "Foundations", article, ""])

    # Broadcast (Weeks 9+) - show sample pattern
    rows.append(["", "", "", "", ""])
    rows.append(["", "", "", "--- PERSONALIZED BROADCAST ENGINE ---", ""])
    rows.append(["", "", "", "", ""])

    sample_broadcasts = [
        ("9", "Bank Impostor Calls", "Medicare Explained: A Simple Guide"),
        ("10", "Subscription Traps", "Medicare Parts A, B, C, D"),
        ("11", "Email Account Hacked", "Save Money on Medicare Premiums"),
        ("12", "Tax Identity Theft", "Medicare Enrollment Deadlines"),
    ]
    for week, tue_article, thu_article in sample_broadcasts:
        rows.append([week, "Mon", "Digest", f"Weekly Digest #{int(week) - 2}", ""])
        rows.append([week, "Tue", "Broadcast", f"[Personalized] e.g. {tue_article}", ""])
        rows.append([week, "Thu", "Broadcast", f"[Personalized] e.g. {thu_article}", ""])

    # Medicare AEP overlay
    rows.append(["", "", "", "", ""])
    rows.append(["", "", "", "--- MEDICARE AEP OVERLAY (Sep-Dec) ---", ""])
    rows.append(["", "", "", "", ""])

    rows.append(["30", "Mon", "Digest", "Weekly Digest", ""])
    rows.append(["30", "Tue", "Broadcast", "[Personalized]", "AEP (Oct-Dec)"])
    rows.append(["30", "Wed", "Medicare", "Medicare AEP Guide #1", "AEP (Oct-Dec)"])
    rows.append(["30", "Thu", "Broadcast", "[Personalized]", "AEP (Oct-Dec)"])

    # Re-engagement
    rows.append(["", "", "", "", ""])
    rows.append(["", "", "", "--- RE-ENGAGEMENT (fires on 30 days inactive) ---", ""])
    rows.append(["", "", "", "", ""])
    rows.append(["--", "Day 0", "Re-engage", "Still Finding Savings Near You?", ""])
    rows.append(["--", "Day 7", "Re-engage", "A Quick Fraud Protection Update", ""])
    rows.append(["--", "Day 14", "Re-engage", "Should We Keep Your Updates Coming?", ""])
    rows.append(["--", "+30 days", "Sunset", "No engagement = suppress subscriber", ""])

    return rows


def read_existing_slugs(sheets_service: Any) -> Set[str]:
    """Read existing article slugs from the Content Queue sheet."""
    try:
        result = (
            sheets_service.spreadsheets()
            .values()
            .get(
                spreadsheetId=SHEET_ID,
                range="'Article Library'!A2:A200",
            )
            .execute()
        )
        values = result.get("values", [])
        return {row[0] for row in values if row}
    except Exception as exc:
        print(f"  Warning: Could not read existing slugs: {exc}")
        return set()


def main() -> None:
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN - no changes will be written. Use --apply to write.\n")
    else:
        print("APPLYING changes to Content Queue Google Sheet.\n")

    # Build article data (no Google auth needed for dry run)
    print("Scanning content sources...")
    existing_slugs: Set[str] = set()

    if not dry_run:
        from googleapiclient.discovery import build

        from cmo_agent.google_auth import get_google_credentials

        oauth_path = str(project_root / "data" / "google-token.json")
        sa_path = str(project_root / "data" / "saverwell-google-credentials.json")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        # Use service account for Sheets (per memory: SA works for Sheets API)
        credentials = get_google_credentials(
            oauth_token_path=oauth_path,
            service_account_path=sa_path,
            scopes=scopes,
        )
        if credentials is None:
            print("ERROR: Could not load Google credentials.")
            sys.exit(1)

        sheets_service = build("sheets", "v4", credentials=credentials)
        existing_slugs = read_existing_slugs(sheets_service)
        print(f"  Found {len(existing_slugs)} existing articles in sheet")

    rows, new_articles = build_article_rows(existing_slugs)
    timeline_rows = build_subscriber_timeline()

    print("\nArticle inventory:")
    print(f"  Total articles: {len(rows)}")
    print(f"  New articles (not in sheet): {len(new_articles)}")
    print(f"  Existing articles (preserved): {len(rows) - len(new_articles)}")

    # Count by vertical
    vertical_counts: Dict[str, int] = {}
    affiliate_count = 0
    for row in rows:
        v = row[4]  # content_vertical column
        vertical_counts[v] = vertical_counts.get(v, 0) + 1
        if row[11] == "TRUE":  # affiliate_disclosure
            affiliate_count += 1

    print("\nBy vertical:")
    for v in sorted(vertical_counts):
        print(f"  {v}: {vertical_counts[v]}")
    print(f"\nAffiliate-enabled: {affiliate_count}")
    print(f"Subscriber Timeline rows: {len(timeline_rows)}")

    if dry_run:
        print("\nDry run complete. Use --apply to write to Google Sheets.")
        return

    # Write to Google Sheets
    print("\nWriting to Google Sheets...")

    # Headers for Article Library (expanded)
    headers = [
        "slug",
        "title",
        "content_type",
        "vertical",
        "content_vertical",
        "base_priority",
        "send_day",
        "seasonal_boost_start",
        "seasonal_boost_end",
        "seasonal_boost_amount",
        "monetization_tier",
        "affiliate_disclosure",
        "partner_slug",
        "article_url",
        "drip_assignment",
        "email_template_file",
        "email_ready",
        "total_sends",
        "notes",
    ]

    # Clear and rewrite Article Library
    sheets_service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="'Article Library'!A:Z",
    ).execute()

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range="'Article Library'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers] + rows},
    ).execute()
    print(f"  Article Library: {len(rows)} articles written ({len(headers)} columns)")

    # Add Subscriber Timeline tab
    # First check if tab exists
    spreadsheet = (
        sheets_service.spreadsheets()
        .get(
            spreadsheetId=SHEET_ID,
        )
        .execute()
    )
    existing_tabs = {s["properties"]["title"] for s in spreadsheet["sheets"]}

    if "Subscriber Timeline" not in existing_tabs:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={
                "requests": [
                    {
                        "addSheet": {
                            "properties": {
                                "title": "Subscriber Timeline",
                                "index": 3,
                            }
                        }
                    }
                ]
            },
        ).execute()
        print("  Subscriber Timeline tab created")

    sheets_service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="'Subscriber Timeline'!A:Z",
    ).execute()

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range="'Subscriber Timeline'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": timeline_rows},
    ).execute()
    print(f"  Subscriber Timeline: {len(timeline_rows)} rows written")

    # Update Seasonal Calendar with new windows
    seasonal_headers = [
        "season",
        "start_date",
        "end_date",
        "boost_verticals",
        "boost_amount",
        "notes",
    ]
    seasonal_rows = [
        [
            "Medicare AEP",
            "2026-10-01",
            "2026-12-07",
            "medicare",
            "+5",
            "Biggest monetization window. Broker referral CTAs.",
        ],
        [
            "Medicare OEP",
            "2027-01-01",
            "2027-03-31",
            "medicare",
            "+3",
            "Medicare Advantage switching.",
        ],
        [
            "Tax Season",
            "2027-01-15",
            "2027-04-15",
            "fraud, finance",
            "+3",
            "Tax identity theft, tax deduction guides.",
        ],
        [
            "Holiday Shopping",
            "2026-11-01",
            "2026-12-31",
            "fraud",
            "+2",
            "Online shopping scams, gift card fraud.",
        ],
        [
            "New Year Reset",
            "2027-01-01",
            "2027-01-31",
            "finance",
            "+2",
            "Budgeting, subscription audits, financial fresh start.",
        ],
        [
            "Cybersecurity Month",
            "2026-10-01",
            "2026-10-31",
            "fraud",
            "+2",
            "National Cybersecurity Awareness Month.",
        ],
        [
            "Data Breach (Reactive)",
            "",
            "",
            "fraud",
            "+4",
            "Manually set dates when major breaches announced.",
        ],
    ]

    sheets_service.spreadsheets().values().clear(
        spreadsheetId=SHEET_ID,
        range="'Seasonal Calendar'!A:Z",
    ).execute()

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range="'Seasonal Calendar'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [seasonal_headers] + seasonal_rows},
    ).execute()
    print(
        f"  Seasonal Calendar: {len(seasonal_rows)} seasons written "
        "(added New Year Reset + Cybersecurity Month)"
    )

    print(f"\nDone. Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit")


# ── Importable API for weekly_content_factory ────────────────────────────────


def append_new_articles(
    articles: List[Dict[str, Any]],
    sheets_service: Any = None,
    sheet_id: str = SHEET_ID,
) -> int:
    """Append new articles to the Article Library tab in the Content Queue sheet.

    This is the importable entry point used by ``weekly_content_factory.py``.
    Only appends articles whose slugs aren't already in the sheet.

    Args:
        articles: List of article dicts with keys: slug, title, vertical,
            category_slug, monetization_type, affiliate_disclosure, base_priority.
        sheets_service: Authenticated Google Sheets service. If None, creates one.
        sheet_id: Google Sheets spreadsheet ID.

    Returns:
        Number of articles appended.
    """
    _scan_templates()

    if sheets_service is None:
        from googleapiclient.discovery import build

        from cmo_agent.google_auth import get_google_credentials

        oauth_path = str(project_root / "data" / "google-token.json")
        sa_path = str(project_root / "data" / "saverwell-google-credentials.json")
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]

        credentials = get_google_credentials(
            oauth_token_path=oauth_path,
            service_account_path=sa_path,
            scopes=scopes,
        )
        if credentials is None:
            print("ERROR: Could not load Google credentials for append_new_articles")
            return 0

        sheets_service = build("sheets", "v4", credentials=credentials)

    existing_slugs = read_existing_slugs(sheets_service)

    rows_to_append = []
    send_day_cycle = ["tuesday", "thursday"]

    for i, art in enumerate(articles):
        slug = art.get("slug", "")
        if not slug or slug in existing_slugs:
            continue

        vertical = art.get("vertical", "6-discounts")
        content_vertical = VERTICAL_MAP.get(vertical, "General")
        article_url = _compute_article_url(slug, vertical)
        partner = _determine_partner_slug(slug, vertical)
        tier = _determine_monetization_tier(
            art.get("monetization_type", "informational"),
            art.get("affiliate_disclosure", False),
        )
        drip = "broadcast_pool"
        template = TEMPLATE_FILE_MAP.get(slug, "")
        send_day = send_day_cycle[i % len(send_day_cycle)]
        base_priority = str(art.get("base_priority", 5))

        row = [
            slug,
            art.get("title", slug),
            "guide",
            vertical,
            content_vertical,
            base_priority,
            send_day,
            "",  # seasonal_boost_start
            "",  # seasonal_boost_end
            "",  # seasonal_boost_amount
            tier,
            str(art.get("affiliate_disclosure", False)).upper(),
            partner,
            article_url,
            drip,
            template,
            "TRUE",  # email_ready
            "0",  # total_sends
            "auto-generated by content factory",  # notes
        ]
        rows_to_append.append(row)

    if not rows_to_append:
        print("  No new articles to append to Content Queue")
        return 0

    # Append rows (don't clear/rewrite — just append)
    sheets_service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="'Article Library'!A:S",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows_to_append},
    ).execute()

    print(f"  Appended {len(rows_to_append)} new articles to Article Library")
    return len(rows_to_append)


if __name__ == "__main__":
    main()
