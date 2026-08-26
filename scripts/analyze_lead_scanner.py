"""Analyze the Saverwell Lead Scanner Google Sheet to understand
why off-target / younger leads are appearing, especially from r/personalfinance.

Sheet ID: 1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
CREDS_PATH = Path(__file__).resolve().parent.parent / "data" / "saverwell-google-credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Column indices (0-based) from dashboard.py header definition
COL = {
    "Date Found": 0,      # A
    "Post Date": 1,        # B
    "Lead ID": 2,          # C
    "Platform": 3,         # D
    "Pillar": 4,           # E
    "Post Title/Summary": 5,  # F
    "Full Content": 6,     # G
    "Post URL": 7,         # H
    "Score": 8,            # I
    "Post Type": 9,        # J
    "Monetization Signal": 10,  # K
    "Draft Reply": 11,     # L
    "Reviewer Notes": 12,  # M
    "Status": 13,          # N
    "Claimed Date/Time": 14,  # O
    "Claimed By": 15,      # P
    "Response Notes": 16,  # Q
    "Response URL": 17,    # R
    "Outcome": 18,         # S
}


def get_cell(row, col_idx, default=""):
    """Safely get cell value from a row."""
    if col_idx < len(row):
        return str(row[col_idx]).strip()
    return default


def main():
    # ── Authenticate ──
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets().values()

    # ── 1. Read Lead Queue ──
    print("=" * 80)
    print("SAVERWELL LEAD SCANNER ANALYSIS")
    print("=" * 80)
    print()

    result = sheets.get(
        spreadsheetId=SHEET_ID,
        range="'Lead Queue'!A1:S5000",
    ).execute()
    all_rows = result.get("values", [])

    if not all_rows:
        print("ERROR: No data in Lead Queue tab")
        sys.exit(1)

    headers = all_rows[0]
    data_rows = all_rows[1:]  # skip header

    print(f"Total data rows in Lead Queue: {len(data_rows)}")
    print(f"Headers: {headers}")
    print()

    # ── 2. Platform breakdown ──
    print("-" * 80)
    print("PLATFORM BREAKDOWN (all leads)")
    print("-" * 80)
    platform_counts = Counter()
    for row in data_rows:
        platform = get_cell(row, COL["Platform"], "(empty)")
        platform_counts[platform] += 1

    for platform, count in platform_counts.most_common():
        print(f"  {platform}: {count} leads")
    print()

    # ── 3. Score distribution per platform ──
    print("-" * 80)
    print("SCORE DISTRIBUTION BY PLATFORM")
    print("-" * 80)
    platform_scores = defaultdict(list)
    for row in data_rows:
        platform = get_cell(row, COL["Platform"], "(empty)")
        score_str = get_cell(row, COL["Score"])
        if score_str:
            try:
                score = float(score_str)
                platform_scores[platform].append(score)
            except ValueError:
                pass

    for platform in sorted(platform_scores.keys()):
        scores = platform_scores[platform]
        if scores:
            avg = sum(scores) / len(scores)
            print(f"  {platform}:")
            print(f"    Count scored: {len(scores)}")
            print(f"    Min: {min(scores):.1f}  Max: {max(scores):.1f}  Avg: {avg:.1f}")
            # Score histogram
            buckets = Counter()
            for s in scores:
                bucket = int(s)
                buckets[bucket] += 1
            for bucket in sorted(buckets.keys()):
                bar = "#" * buckets[bucket]
                print(f"    Score {bucket}: {buckets[bucket]:3d} {bar}")
        print()

    # ── 4. Status breakdown per platform ──
    print("-" * 80)
    print("STATUS BREAKDOWN BY PLATFORM")
    print("-" * 80)
    platform_status = defaultdict(Counter)
    for row in data_rows:
        platform = get_cell(row, COL["Platform"], "(empty)")
        status = get_cell(row, COL["Status"], "(empty)")
        platform_status[platform][status] += 1

    for platform in sorted(platform_status.keys()):
        print(f"  {platform}:")
        for status, count in platform_status[platform].most_common():
            print(f"    {status}: {count}")
        print()

    # ── 5. r/personalfinance deep dive ──
    print("=" * 80)
    print("r/personalfinance DEEP DIVE")
    print("=" * 80)
    pf_rows = [
        row for row in data_rows
        if "personalfinance" in get_cell(row, COL["Platform"]).lower()
    ]
    print(f"Total r/personalfinance leads: {len(pf_rows)}")
    print()

    if pf_rows:
        print("-" * 80)
        print("ALL r/personalfinance leads (Post Title + Score + Pillar + Status + Reviewer Notes)")
        print("-" * 80)
        for i, row in enumerate(pf_rows, 1):
            title = get_cell(row, COL["Post Title/Summary"])
            score = get_cell(row, COL["Score"])
            pillar = get_cell(row, COL["Pillar"])
            status = get_cell(row, COL["Status"])
            notes = get_cell(row, COL["Reviewer Notes"])
            post_type = get_cell(row, COL["Post Type"])
            monet = get_cell(row, COL["Monetization Signal"])
            date = get_cell(row, COL["Date Found"])
            url = get_cell(row, COL["Post URL"])

            print(f"\n  [{i}] {title}")
            print(f"      Date: {date}  |  Score: {score}  |  Pillar: {pillar}")
            print(f"      Post Type: {post_type}  |  Monetization: {monet}")
            print(f"      Status: {status}")
            if notes:
                # Wrap long notes
                print(f"      Reviewer Notes: {notes[:300]}")
            if url:
                print(f"      URL: {url}")
        print()

        # Pillar breakdown for pf
        print("-" * 80)
        print("r/personalfinance - Pillar (search term category) breakdown")
        print("-" * 80)
        pf_pillars = Counter()
        for row in pf_rows:
            pillar = get_cell(row, COL["Pillar"], "(empty)")
            pf_pillars[pillar] += 1
        for pillar, count in pf_pillars.most_common():
            print(f"  {pillar}: {count}")
        print()

        # Status breakdown for pf
        print("-" * 80)
        print("r/personalfinance - Status breakdown")
        print("-" * 80)
        pf_statuses = Counter()
        for row in pf_rows:
            status = get_cell(row, COL["Status"], "(empty)")
            pf_statuses[status] += 1
        for status, count in pf_statuses.most_common():
            print(f"  {status}: {count}")
        print()

    # ── 6. Also check other potentially off-target subs ──
    print("=" * 80)
    print("POSTS WITH LOW SCORES (Score <= 3) BY PLATFORM")
    print("=" * 80)
    low_score_by_platform = defaultdict(list)
    for row in data_rows:
        score_str = get_cell(row, COL["Score"])
        if score_str:
            try:
                score = float(score_str)
                if score <= 3:
                    platform = get_cell(row, COL["Platform"])
                    title = get_cell(row, COL["Post Title/Summary"])
                    notes = get_cell(row, COL["Reviewer Notes"])
                    low_score_by_platform[platform].append((score, title, notes))
            except ValueError:
                pass

    for platform in sorted(low_score_by_platform.keys()):
        leads = low_score_by_platform[platform]
        print(f"\n  {platform} ({len(leads)} low-score leads):")
        for score, title, notes in sorted(leads, key=lambda x: x[0]):
            print(f"    Score {score:.0f}: {title[:80]}")
            if notes:
                print(f"           Notes: {notes[:150]}")
    print()

    # ── 7. Read Search Terms tab ──
    print("=" * 80)
    print("SEARCH TERMS ANALYSIS")
    print("=" * 80)
    try:
        st_result = sheets.get(
            spreadsheetId=SHEET_ID,
            range="'Search Terms'!A1:H500",
        ).execute()
        st_rows = st_result.get("values", [])
    except Exception as e:
        print(f"ERROR reading Search Terms tab: {e}")
        st_rows = []

    if st_rows:
        st_headers = st_rows[0]
        st_data = st_rows[1:]
        print(f"Search Terms headers: {st_headers}")
        print(f"Total search terms: {len(st_data)}")
        print()

        # Group by pillar and platform
        by_pillar = defaultdict(list)
        by_platform = defaultdict(list)
        active_terms = []
        for row in st_data:
            term = row[0] if len(row) > 0 else ""
            term_type = row[1] if len(row) > 1 else ""
            platform = row[2] if len(row) > 2 else ""
            pillar = row[3] if len(row) > 3 else ""
            active = row[4] if len(row) > 4 else ""
            by_pillar[pillar].append((term, platform, active))
            by_platform[platform].append((term, pillar, active))
            if active.upper() in ("TRUE", "YES", "1"):
                active_terms.append((term, pillar, platform))

        print(f"Active terms: {len(active_terms)}")
        print()

        print("-" * 80)
        print("SEARCH TERMS BY PILLAR")
        print("-" * 80)
        for pillar in sorted(by_pillar.keys()):
            terms = by_pillar[pillar]
            active = [t for t in terms if t[2].upper() in ("TRUE", "YES", "1")]
            print(f"\n  [{pillar}] ({len(terms)} total, {len(active)} active)")
            for term, platform, act in terms:
                marker = "ACTIVE" if act.upper() in ("TRUE", "YES", "1") else "inactive"
                print(f"    [{marker}] {term}  (platform: {platform})")

        print()
        print("-" * 80)
        print("POTENTIALLY BROAD TERMS (could match younger audiences)")
        print("-" * 80)
        print()
        # Flag terms that don't contain age/senior qualifiers
        senior_qualifiers = [
            "senior", "retiree", "retired", "65", "60", "70", "medicare",
            "social security", "aarp", "aging", "elderly", "older adult",
            "pension", "nursing home", "assisted living",
        ]
        broad_terms = []
        for term, pillar, platform in active_terms:
            term_lower = term.lower()
            has_qualifier = any(q in term_lower for q in senior_qualifiers)
            if not has_qualifier:
                broad_terms.append((term, pillar, platform))

        if broad_terms:
            print(f"  Found {len(broad_terms)} active terms WITHOUT senior/age qualifiers:")
            for term, pillar, platform in broad_terms:
                print(f"    - \"{term}\"  (pillar: {pillar}, platform: {platform})")
        else:
            print("  All active terms contain senior/age qualifiers.")
        print()

    # ── 8. Show which subreddits are configured in Search Terms ──
    print("-" * 80)
    print("PLATFORMS CONFIGURED IN SEARCH TERMS")
    print("-" * 80)
    for platform in sorted(by_platform.keys()):
        terms = by_platform[platform]
        active = [t for t in terms if t[2].upper() in ("TRUE", "YES", "1")]
        print(f"  {platform}: {len(terms)} terms ({len(active)} active)")
    print()

    # ── 9. Check Archive tab for more skipped r/personalfinance leads ──
    print("=" * 80)
    print("ARCHIVE TAB - SKIPPED LEADS CHECK")
    print("=" * 80)
    try:
        arch_result = sheets.get(
            spreadsheetId=SHEET_ID,
            range="'Archive'!A1:S5000",
        ).execute()
        arch_rows = arch_result.get("values", [])
    except Exception as e:
        print(f"ERROR reading Archive tab: {e}")
        arch_rows = []

    if arch_rows and len(arch_rows) > 1:
        arch_data = arch_rows[1:]
        print(f"Total archived rows: {len(arch_data)}")

        arch_platform_counts = Counter()
        arch_pf_rows = []
        for row in arch_data:
            platform = get_cell(row, COL["Platform"], "(empty)")
            arch_platform_counts[platform] += 1
            if "personalfinance" in platform.lower():
                arch_pf_rows.append(row)

        print("\nArchive platform breakdown:")
        for platform, count in arch_platform_counts.most_common():
            print(f"  {platform}: {count}")

        if arch_pf_rows:
            print(f"\nr/personalfinance in Archive: {len(arch_pf_rows)}")
            for i, row in enumerate(arch_pf_rows[:20], 1):
                title = get_cell(row, COL["Post Title/Summary"])
                score = get_cell(row, COL["Score"])
                notes = get_cell(row, COL["Reviewer Notes"])
                status = get_cell(row, COL["Status"])
                print(f"  [{i}] Score: {score} | Status: {status} | {title[:70]}")
                if notes:
                    print(f"       Notes: {notes[:150]}")
    else:
        print("Archive tab is empty or unreadable.")

    print()
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
