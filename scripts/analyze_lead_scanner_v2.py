"""Deeper analysis: extract subreddit from Post URL, check content for audience signals."""

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
CREDS_PATH = Path(__file__).resolve().parent.parent / "data" / "saverwell-google-credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

COL = {
    "Date Found": 0, "Post Date": 1, "Lead ID": 2, "Platform": 3,
    "Pillar": 4, "Post Title/Summary": 5, "Full Content": 6, "Post URL": 7,
    "Score": 8, "Post Type": 9, "Monetization Signal": 10, "Draft Reply": 11,
    "Reviewer Notes": 12, "Status": 13,
}


def get_cell(row, col_idx, default=""):
    if col_idx < len(row):
        return str(row[col_idx]).strip()
    return default


def extract_subreddit(url):
    """Extract subreddit name from Reddit URL."""
    m = re.search(r"reddit\.com/r/([^/]+)", url)
    if m:
        return f"r/{m.group(1)}"
    return "(unknown)"


def main():
    creds = Credentials.from_service_account_file(str(CREDS_PATH), scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets().values()

    result = sheets.get(
        spreadsheetId=SHEET_ID,
        range="'Lead Queue'!A1:S5000",
    ).execute()
    all_rows = result.get("values", [])
    data_rows = all_rows[1:]

    print("=" * 90)
    print("LEAD SCANNER DEEP ANALYSIS - Subreddit-Level Breakdown")
    print("=" * 90)
    print(f"Total leads: {len(data_rows)}")
    print()

    # ── 1. Extract subreddit from URL ──
    sub_counts = Counter()
    sub_rows = defaultdict(list)
    sub_scores = defaultdict(list)

    for row in data_rows:
        url = get_cell(row, COL["Post URL"])
        subreddit = extract_subreddit(url)
        sub_counts[subreddit] += 1
        sub_rows[subreddit].append(row)
        score_str = get_cell(row, COL["Score"])
        if score_str:
            try:
                sub_scores[subreddit].append(float(score_str))
            except ValueError:
                pass

    print("-" * 90)
    print("SUBREDDIT BREAKDOWN")
    print("-" * 90)
    for sub, count in sub_counts.most_common():
        scores = sub_scores.get(sub, [])
        score_info = ""
        if scores:
            avg = sum(scores) / len(scores)
            score_info = f"  | Scores: min={min(scores):.0f} max={max(scores):.0f} avg={avg:.1f} (n={len(scores)})"
        print(f"  {sub}: {count} leads{score_info}")
    print()

    # ── 2. r/personalfinance deep dive ──
    pf_key = None
    for sub in sub_counts:
        if "personalfinance" in sub.lower():
            pf_key = sub
            break

    if pf_key:
        pf_leads = sub_rows[pf_key]
        print("=" * 90)
        print(f"{pf_key} DEEP DIVE ({len(pf_leads)} leads)")
        print("=" * 90)

        for i, row in enumerate(pf_leads, 1):
            title = get_cell(row, COL["Post Title/Summary"])
            score = get_cell(row, COL["Score"])
            pillar = get_cell(row, COL["Pillar"])
            status = get_cell(row, COL["Status"])
            notes = get_cell(row, COL["Reviewer Notes"])
            post_type = get_cell(row, COL["Post Type"])
            monet = get_cell(row, COL["Monetization Signal"])
            date = get_cell(row, COL["Date Found"])
            content = get_cell(row, COL["Full Content"])

            print(f"\n  [{i}] {title}")
            print(f"      Date: {date} | Score: {score} | Pillar: {pillar} | Status: {status}")
            print(f"      Post Type: {post_type} | Monetization: {monet}")
            if notes:
                print(f"      Reviewer Notes: {notes[:300]}")
            # Show first 200 chars of content for context
            if content:
                print(f"      Content preview: {content[:200]}...")
            print()

        # Pillar breakdown
        pf_pillars = Counter()
        for row in pf_leads:
            pillar = get_cell(row, COL["Pillar"], "(empty)")
            pf_pillars[pillar] += 1
        print(f"  Pillar breakdown: {dict(pf_pillars.most_common())}")
        print()
    else:
        print("No r/personalfinance leads found in Lead Queue.\n")

    # ── 3. Show all posts from non-senior-targeted subs ──
    # Subs that are clearly senior-focused
    SENIOR_SUBS = {"r/seniors", "r/retirement", "r/medicare", "r/eldercare",
                   "r/socialsecurity", "r/aging", "r/retirees"}
    offtarget_subs = {sub for sub in sub_counts if sub.lower() not in {s.lower() for s in SENIOR_SUBS}}

    if offtarget_subs:
        print("=" * 90)
        print("GENERAL-AUDIENCE SUBREDDITS (potential off-target sources)")
        print("=" * 90)
        for sub in sorted(offtarget_subs):
            leads = sub_rows[sub]
            if sub == pf_key:
                continue  # already shown above
            print(f"\n  --- {sub} ({len(leads)} leads) ---")
            # Show a sample of titles + notes
            for i, row in enumerate(leads[:15], 1):
                title = get_cell(row, COL["Post Title/Summary"])
                score = get_cell(row, COL["Score"])
                pillar = get_cell(row, COL["Pillar"])
                notes = get_cell(row, COL["Reviewer Notes"])
                status = get_cell(row, COL["Status"])
                print(f"    [{i}] {title[:80]}")
                print(f"        Score: {score} | Pillar: {pillar} | Status: {status}")
                if notes:
                    print(f"        Notes: {notes[:200]}")
            if len(leads) > 15:
                print(f"    ... and {len(leads) - 15} more")
            print()

    # ── 4. Analyze reviewer notes patterns ──
    print("=" * 90)
    print("REVIEWER NOTES ANALYSIS (all leads)")
    print("=" * 90)
    notes_counter = Counter()
    has_notes = 0
    no_notes = 0
    skip_flagged = 0
    for row in data_rows:
        notes = get_cell(row, COL["Reviewer Notes"])
        if notes:
            has_notes += 1
            # Extract key phrases
            notes_lower = notes.lower()
            if any(w in notes_lower for w in ["off-target", "off target", "not senior",
                                                "wrong audience", "young", "younger",
                                                "not a senior", "mismatch", "audience mismatch"]):
                skip_flagged += 1
        else:
            no_notes += 1

    print(f"  Leads with reviewer notes: {has_notes}")
    print(f"  Leads without reviewer notes: {no_notes}")
    print(f"  Leads flagged as off-target/audience-mismatch in notes: {skip_flagged}")
    print()

    # ── 5. Young/off-target keyword scan in titles ──
    print("=" * 90)
    print("OFF-TARGET SIGNAL SCAN (keywords in Post Titles suggesting younger audience)")
    print("=" * 90)
    young_signals = [
        "college", "student", "22", "23", "24", "25", "26", "27", "28", "29",
        "30", "first job", "entry level", "intern", "graduation", "graduated",
        "young adult", "early career", "starting out", "20s", "30s", "career change",
        "saving for house", "student loan", "newlywed", "new baby", "just married",
        "first apartment", "credit card first",
    ]
    flagged = []
    for row in data_rows:
        title = get_cell(row, COL["Post Title/Summary"]).lower()
        content_preview = get_cell(row, COL["Full Content"])[:300].lower()
        combined = title + " " + content_preview
        matches = [sig for sig in young_signals if sig in combined]
        if matches:
            url = get_cell(row, COL["Post URL"])
            subreddit = extract_subreddit(url)
            flagged.append((
                get_cell(row, COL["Post Title/Summary"]),
                subreddit,
                matches,
                get_cell(row, COL["Score"]),
                get_cell(row, COL["Status"]),
                get_cell(row, COL["Reviewer Notes"]),
            ))

    print(f"  Posts with younger-audience signals: {len(flagged)}")
    for title, sub, matches, score, status, notes in flagged:
        print(f"\n    Title: {title[:80]}")
        print(f"    Sub: {sub} | Score: {score} | Status: {status}")
        print(f"    Matched signals: {matches}")
        if notes:
            print(f"    Notes: {notes[:200]}")
    print()

    # ── 6. The real problem: pillar-less "catch-all" terms ──
    print("=" * 90)
    print("THE CORE ISSUE: PILLAR-LESS CATCH-ALL SEARCH TERMS")
    print("=" * 90)
    print()
    print("The Search Terms tab has 64 terms with NO pillar assigned (empty pillar).")
    print("These fall into several problematic categories:")
    print()
    print("  CATEGORY 1 - NEGATIVE FILTERS (should exclude, not match):")
    print('    These are EXCLUSION terms that should PREVENT matching, but they are')
    print('    stored as regular search terms and may be matching posts instead.')
    print('    Examples: "senior developer", "senior engineer", "dog senior", "cat senior"')
    print()
    print("  CATEGORY 2 - ULTRA-GENERIC PHRASES (match everything):")
    print('    These match ANY Reddit post asking for help, regardless of age/topic.')
    print('    "help me", "looking for", "does anyone know", "how do I",')
    print('    "any recommendations", "need advice", "what should I do",')
    print('    "feeling overwhelmed", "can\'t afford", "too expensive",')
    print('    "on a budget", "tight budget", "struggling to pay",')
    print('    "worried about", "scared of"')
    print()
    print("  CATEGORY 3 - INDUSTRY/FACILITY TERMS (not consumer leads):")
    print('    "insurance agent", "insurance broker", "caregiver needed",')
    print('    "hiring caregiver", "assisted living"')
    print()
    print("  ==> These 64 terms are almost certainly why off-target posts from")
    print('      r/personalfinance and other general subs are getting pulled in.')
    print('      A 25-year-old posting "struggling to pay rent, need advice" would')
    print('      match at least 3 of these catch-all terms.')
    print()

    # ── 7. Which pillar-less terms are likely matching our leads? ──
    pillar_empty_terms = [
        "help me", "looking for", "does anyone know", "where can I find",
        "how do I", "any recommendations", "has anyone tried", "is there a",
        "what's the best way", "anyone else", "am I eligible",
        "do they still offer", "is this legit", "is this real",
        "what should I do", "need advice", "feeling overwhelmed",
        "can't afford", "too expensive", "on a budget", "tight budget",
        "every penny counts", "pinching pennies", "making ends meet",
        "struggling to pay", "worried about", "scared of",
    ]

    print("-" * 90)
    print("CATCH-ALL TERM MATCHES FOUND IN LEAD QUEUE TITLES")
    print("-" * 90)
    term_match_counts = Counter()
    for row in data_rows:
        title = get_cell(row, COL["Post Title/Summary"]).lower()
        for term in pillar_empty_terms:
            if term in title:
                term_match_counts[term] += 1

    for term, count in term_match_counts.most_common():
        print(f"  \"{term}\": matches {count} lead titles")
    print()

    unmatched = [t for t in pillar_empty_terms if t not in term_match_counts]
    if unmatched:
        print(f"  ({len(unmatched)} catch-all terms didn't match any titles directly,")
        print(f"   but may match full post content which we didn't scan here)")

    print()
    print("=" * 90)
    print("RECOMMENDATIONS")
    print("=" * 90)
    print("""
  1. DEACTIVATE all 64 pillar-less terms. They are either:
     - Negative filters that should be in a separate exclusion list
     - Ultra-generic phrases that match any audience
     - Industry terms that attract professionals, not consumers

  2. The Savings (56), Protection (54), and Guides (25) pillar terms are
     well-targeted with senior/age qualifiers. Keep those.

  3. Some Protection terms lack age qualifiers but are still relevant
     (scam-related). Consider adding subreddit-level filtering instead
     of deactivating those. E.g., only scan r/Scams, r/personalfinance
     for scam terms, not all of Reddit.

  4. Add subreddit info to the Platform column (e.g., "Reddit/r/personalfinance")
     so reviewers can quickly spot off-target sources without clicking URLs.
""")


if __name__ == "__main__":
    main()
