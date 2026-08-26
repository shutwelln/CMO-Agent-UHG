#!/usr/bin/env python3
"""One-off script: Creates a Google Doc write-up of the DSDN Outreach System.

Uses the same Google auth + Docs API pattern as the Docs Agent.
Run:  python scripts/create_outreach_doc.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Google Auth (reuse project helper) ─────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

def get_services():
    """Return (docs_service, drive_service) using existing project credentials."""
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials, share_file_restricted

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=SCOPES,
    )
    if creds is None:
        raise RuntimeError("No Google credentials found. Set GOOGLE_OAUTH_TOKEN_PATH or GOOGLE_CREDENTIALS_PATH.")

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return docs, drive


# ── Inline formatting parser (from docs.py) ───────────────────────────
def parse_inline(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Parse **bold** and *italic* markers. Returns (plain_text, [(start,end,style),...])."""
    runs: List[Tuple[int, int, str]] = []
    chars: List[str] = []
    i, length = 0, len(text)
    while i < length:
        if i + 1 < length and text[i] == "*" and text[i + 1] == "*":
            end = text.find("**", i + 2)
            if end != -1:
                s = len(chars)
                inner = text[i + 2 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "bold"))
                i = end + 2
                continue
        if text[i] == "*" and (i + 1 >= length or text[i + 1] != "*"):
            end = text.find("*", i + 1)
            if end != -1:
                s = len(chars)
                inner = text[i + 1 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "italic"))
                i = end + 1
                continue
        chars.append(text[i])
        i += 1
    return "".join(chars), runs


# ── Document structure ─────────────────────────────────────────────────
TITLE = "DSDN Outreach Scanning & Response System — Technical Write-Up"

SECTIONS: List[Dict[str, Any]] = [
    # ── Executive Summary ──────────────────────────────────────────
    {
        "heading": "Executive Summary",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The DSDN Outreach Scanning & Response System is an automated pipeline "
                    "within the CMO Agent platform that helps the Down Syndrome Diagnosis "
                    "Network (DSDN) outreach team find and connect with families who have "
                    "recently received a Down syndrome diagnosis. It scans online platforms "
                    "(Reddit and Glowing.com), scores posts for outreach relevance, generates "
                    "AI-drafted replies with content safety checks, and provides a shared "
                    "Google Sheets dashboard for the 6+ person outreach team to claim posts, "
                    "track responses, and measure outcomes."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Every design decision reflects the sensitivity of the moment these "
                    "families are in. Replies are **always drafts** reviewed by a human team "
                    "member before sending. The system enforces person-first language, correct "
                    "domain usage (dsdiagnosisnetwork.org, never dsdn.org), and post-type-aware "
                    "tone (e.g., never saying \"congratulations\" on a prenatal diagnosis post)."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Automated scanning: Reddit (public JSON feeds) + Glowing.com (httpx scraper)",
                    "4-dimension outreach scoring: Diagnosis Relevance, Recency, Urgency, DSDN Fit (0-10 each, max 40)",
                    "AI-drafted replies with 9-point content safety checks (including assumption detection and savior/recruitment tone)",
                    "Google Sheets dashboard with 6 tabs: Outreach Queue, Search Terms, Canned Responses, Team Dashboard, Archive, Dropdowns",
                    "Dynamic dropdown validation: Status, Claimed By, and Outcome dropdowns populated from a central Dropdowns tab via ONE_OF_RANGE references",
                    "Engagement risk assessment: automatic detection of political, hostile, misinformation, and bait threads before drafting replies",
                    "Slack #dsdn-outreach alerts with Claim / Generate Reply / Skip buttons",
                    "Outcome tracking (connected / no response / declined / already connected / referred elsewhere) for measuring effectiveness",
                    "Cross-platform dedup via SHA-256 content hashing",
                    "Scheduled tasks: scan every 8 hours, search term sync every 15 minutes, dashboard sync every 30 minutes",
                ],
            },
        ],
    },

    # ── Architecture Overview ──────────────────────────────────────
    {
        "heading": "Architecture Overview",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The system is built as a new sub-agent (Outreach Scanner Agent) within the "
                    "existing CMO Agent multi-agent architecture. It follows the same BaseAgent "
                    "pattern used by all other agents — registered as a tool on the CMO Orchestrator, "
                    "invoked via natural language or scheduled tasks."
                ),
            },
        ],
    },
    {
        "heading": "System Components",
        "level": 2,
        "content": [
            {
                "type": "numbered_list",
                "items": [
                    "Outreach Scanner Agent (agents/outreach_scanner.py) — The core agent with 11 tools, Glowing.com scraper, engagement risk assessment, and outreach-specific scoring",
                    "Outreach Dashboard (outreach/dashboard.py) — Google Sheets API integration for the 6-tab team dashboard with dynamic dropdown validation",
                    "Search Terms Manager (outreach/search_terms.py) — Syncs include/exclude keywords between Google Sheet and DB",
                    "Reply Generator (outreach/replies.py) — LLM-powered draft reply generation with post-type awareness and canned response selection",
                    "Content Safety Checker (outreach/safety.py) — 7-point automatic quality gate for generated replies",
                    "Database Layer — 10 new columns on the opportunities table + 9 new repository methods",
                    "Scheduler Tasks — 3 automated task factories for scanning, syncing, and dashboard updates",
                    "Slack Integration — Block Kit notifications with interactive Claim/Generate Reply/Skip buttons",
                ],
            },
        ],
    },
    {
        "heading": "Data Flow",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The data flow follows this path: **Scan → Score → Store → Notify → Claim → "
                    "Draft → Respond → Track**. The database (SQLite) is the source of truth. "
                    "The Google Sheet is a synced view that the team interacts with. Slack provides "
                    "real-time alerts."
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "Scheduled scan runs every 8 hours (or on-demand via Slack /outreach-scan)",
                    "Scanner fetches posts from Reddit (general subreddits + r/DownSyndrome) and Glowing.com, applying keyword matching (include/exclude terms)",
                    "Each post is scored across 4 dimensions (max 40 points), classified by post type, and checked for duplicates",
                    "New opportunities are stored in the database with outreach_status='new'",
                    "Posts scoring above the threshold (default: 20) trigger Slack notifications to #dsdn-outreach",
                    "A team member clicks 'Claim' in Slack (or updates the Google Sheet) — status becomes 'claimed'",
                    "Team member clicks 'Generate Reply' — the AI drafts a reply, runs safety checks, posts in a Slack thread",
                    "Team member reviews, personalizes, and manually posts the reply on the original platform",
                    "Team member records the outcome (connected, no_response, declined, etc.) for effectiveness tracking",
                ],
            },
        ],
    },

    # ── Platform Scanning ──────────────────────────────────────────
    {
        "heading": "Platform Scanning",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The system currently scans two platforms. Reddit scanning leverages the existing "
                    "Reddit Ingest Agent (which uses public JSON feeds — no API key required). Glowing.com "
                    "scanning is a new Python httpx-based scraper built directly into the Outreach Scanner Agent."
                ),
            },
        ],
    },
    {
        "heading": "Reddit Scanning",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Reddit scanning is delegated to the existing Reddit Ingest Agent, which fetches posts "
                    "from configured subreddits (e.g., r/DownSyndrome, r/BabyBumps, r/pregnant) using "
                    "Reddit's public .json endpoints. Posts are filtered through the dynamic search term "
                    "list and scored using the outreach-specific 4-dimension scoring system."
                ),
            },
        ],
    },
    {
        "heading": "Glowing.com Scanning",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Glowing.com (formerly Glow Community) has a 272-member Down Syndrome group with "
                    "publicly accessible posts. The scraper uses Python httpx to fetch topic pages, "
                    "following the same pattern as the Reddit Ingest Agent."
                ),
            },
            {
                "type": "paragraph",
                "text": "**How the scraper works:**",
            },
            {
                "type": "numbered_list",
                "items": [
                    "Starts from seed topic IDs (known DS discussion threads on Glowing.com)",
                    "Fetches page HTML via httpx with a respectful User-Agent: 'DSDN-Outreach/1.0 (nonprofit family support; https://www.dsdiagnosisnetwork.org)'",
                    "Attempts to extract embedded JSON data from the page (window.__gl_page_init_data pattern)",
                    "Falls back to HTML meta tag extraction (og:title, og:description) if JSON is not available",
                    "Applies keyword matching (include/exclude from the dynamic search terms list)",
                    "Scores each post using the 4-dimension outreach scoring system",
                    "Checks for duplicates — both same-platform (source_id) and cross-platform (content_hash)",
                    "Stores qualifying posts in the opportunities table with source='glowing'",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Rate limiting and respect:**",
            },
            {
                "type": "bullets",
                "items": [
                    "3-second delay between requests (prevents server strain)",
                    "Maximum 20 pages per scan cycle (prevents excessive crawling)",
                    "Respectful User-Agent string identifying DSDN as a nonprofit",
                    "Read-only — the system never posts to Glowing.com",
                ],
            },
        ],
    },
    {
        "heading": "Google Alerts (Supplementary)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Google Alerts serves as a supplementary signal source, catching content that "
                    "keyword scanning might miss. This requires one-time manual setup of Google Alerts "
                    "configured to deliver to a Gmail label (dsdn-outreach-alerts). An n8n workflow "
                    "can then process these alert emails. Example alerts:"
                ),
            },
            {
                "type": "bullets",
                "items": [
                    '"down syndrome diagnosis" site:glowing.com',
                    '"trisomy 21" OR "NIPT positive" OR "down syndrome diagnosis"',
                    '"just found out" "down syndrome"',
                ],
            },
        ],
    },

    # ── Search Terms ───────────────────────────────────────────────
    {
        "heading": "Dynamic Search Terms",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The system uses a dynamic keyword list managed via the Google Sheet's "
                    "'Search Terms' tab. The outreach team can add, remove, or toggle terms "
                    "without touching code. Terms sync from the Sheet to the SQLite database "
                    "every 15 minutes (or on-demand via the sync_search_terms tool). During "
                    "each scan, the scanner reads keywords from the database (not directly "
                    "from the Sheet) for performance. If no terms are found in the database "
                    "(e.g., sync hasn't run yet), hardcoded defaults are used as a fallback."
                ),
            },
        ],
    },
    {
        "heading": "AND Combination Keywords",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The primary search strategy uses **AND combinations** — two phrases "
                    "joined by \"+\" that must both appear in the post. This dramatically "
                    "reduces false positives compared to single-term matching. The system "
                    "generates combinations from 4 primary synonyms crossed with 16 context "
                    "signals, producing 64 AND combinations."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Primary synonyms (4):**",
            },
            {
                "type": "bullets",
                "items": [
                    "down syndrome",
                    "trisomy 21",
                    "T21",
                    "DS",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Context signals (16):**",
            },
            {
                "type": "bullets",
                "items": [
                    "diagnosis, prenatal, baby, newborn, support group, genetic counselor",
                    "early intervention, just found out, NIPT, amniocentesis, prenatal testing",
                    "scared, terrified, resources, community, positive result",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Example AND combinations (64 total):**",
            },
            {
                "type": "bullets",
                "items": [
                    "down syndrome + diagnosis — matches 'we got a down syndrome diagnosis today'",
                    "T21 + prenatal — matches 'T21 came up in our prenatal testing'",
                    "DS + NIPT — matches 'DS flagged on NIPT results'",
                    "trisomy 21 + scared — matches 'scared after trisomy 21 results'",
                    "down syndrome + just found out — matches 'just found out about down syndrome'",
                    "DS + support group — matches 'looking for a DS support group'",
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "The \"+\" syntax means BOTH phrases must be present somewhere in the post "
                    "text (not necessarily adjacent). A post containing \"down syndrome\" without "
                    "any context signal will not match, significantly reducing noise from "
                    "casual mentions."
                ),
            },
        ],
    },
    {
        "heading": "Exclude Keywords (4 active)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "These terms filter out false positives. If any exclude term matches, "
                    "the post is rejected immediately (checked before include terms):"
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "download syndrome — prevents matching software/tech posts",
                    "shut down syndrome — prevents matching political/organizational shutdown posts",
                    "Nintendo DS — prevents matching gaming posts where 'DS' means Nintendo DS",
                    "DS game — same as above",
                ],
            },
        ],
    },
    {
        "heading": "Keyword Matching Logic",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Matching uses **word-boundary regex** to avoid partial matches. For example, "
                    "the include term \"down syndrome\" will match \"my child has down syndrome\" "
                    "but will NOT match \"sundown syndrome\" (blocked by exclude) or \"markdown\" "
                    "(word boundary prevents partial match). Matching is case-insensitive. Exclude "
                    "keywords are checked first for fast rejection."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "**AND combination matching**: When a term contains \"+\", the system splits "
                    "on \"+\" and requires ALL parts to be present as separate word-boundary "
                    "matches. For example, \"down syndrome + diagnosis\" matches any post "
                    "containing both \"down syndrome\" and \"diagnosis\" anywhere in the text, "
                    "even if they're paragraphs apart."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "**Search Terms tab columns**: Term, Type (Include/Exclude), Platform "
                    "(All/Reddit/Glowing), Active (Yes/No), Added By, Date Added, Notes. "
                    "Only rows with Active = 'Yes' are synced. The team can add new terms, "
                    "toggle existing ones off, or modify terms directly in the Sheet — changes "
                    "are picked up within 15 minutes."
                ),
            },
        ],
    },

    # ── Scoring ────────────────────────────────────────────────────
    {
        "heading": "Outreach Scoring System",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Every post is scored across 4 dimensions, each rated 0-10, for a maximum total "
                    "of 40. Posts scoring at or above the threshold (default: 20) trigger Slack "
                    "notifications. The scoring is intentionally tuned for outreach urgency — a "
                    "brand-new prenatal diagnosis post with emotional distress signals will score "
                    "near 40, while a casual mention of Down syndrome in a broader context will "
                    "score under 10."
                ),
            },
        ],
    },
    {
        "heading": "Dimension 1: Diagnosis Relevance (0-10)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Measures how specifically the post relates to a Down syndrome diagnosis event "
                    "(not just a general discussion about DS)."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Score 10: 'just found out', 'got the results today', 'NIPT came back positive', 'amnio results', 'diagnosed', 'prenatal diagnosis', 'T21 positive'",
                    "Score 7: 'diagnosis', 'testing', 'amniocentesis', 'CVS results', 'genetic counselor', 'NIPT', 'trisomy 21'",
                    "Score 4: general 'down syndrome' mention",
                    "Score 1: tangential mention",
                ],
            },
        ],
    },
    {
        "heading": "Dimension 2: Recency (0-10)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Aggressive time decay reflecting outreach urgency — the sooner the team "
                    "reaches out, the more impactful the connection. Currently defaults to "
                    "mid-range (5) for scraped content where exact timestamps may not be available. "
                    "When timestamps are available:"
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Score 10: less than 6 hours old",
                    "Score 8: less than 24 hours",
                    "Score 5: less than 48 hours",
                    "Score 2: less than 7 days",
                    "Score 0: older than 7 days",
                ],
            },
        ],
    },
    {
        "heading": "Dimension 3: Urgency / Emotional Need (0-10)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Detects signals of distress, isolation, or active information-seeking.",
            },
            {
                "type": "bullets",
                "items": [
                    "Score 9: 'scared', 'terrified', 'don't know what to do', 'feeling alone', 'need help', 'crying', 'devastated', 'heartbroken', 'shocked', 'overwhelmed', 'lost'",
                    "Score 6: 'worried', 'confused', 'what should I expect', 'any advice', 'nervous', 'anxious', 'uncertain'",
                    "Score 2: Baseline for general discussion posts",
                ],
            },
        ],
    },
    {
        "heading": "Dimension 4: DSDN Fit (0-10)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Assesses whether the poster is in DSDN's target demographic "
                    "(diagnosis through age 3)."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Score 10: 'expecting', 'pregnant', 'prenatal', 'newborn', 'just born', 'baby', 'NICU', 'born with'",
                    "Score 7: 'toddler', 'infant', '1 year', '2 year', 'early intervention'",
                    "Score 2: Baseline (older child, general audience)",
                ],
            },
        ],
    },
    {
        "heading": "Sensitivity Flag",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Posts are flagged as **[SENSITIVE]** when the post type is 'loss' or the "
                    "urgency score is 9 or higher. Sensitive posts get a visual indicator in both "
                    "the Google Sheet and Slack notification, so the team knows to handle with "
                    "extra care."
                ),
            },
        ],
    },

    # ── Post Type Classification ───────────────────────────────────
    {
        "heading": "Post Type Classification",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Each post is classified into one of 7 types using an LLM call. The "
                    "classification drives tone selection for draft replies — this is critical "
                    "because the appropriate response for a prenatal diagnosis post is very "
                    "different from a newborn diagnosis or loss post."
                ),
            },
            {
                "type": "table",
                "headers": ["Post Type", "Description", "Tone Guidance"],
                "rows": [
                    ["prenatal_diagnosis", "Parent received prenatal test results (NIPT, amnio, CVS) positive for T21", "Extreme empathy. Do NOT say 'congratulations'. Acknowledge fear/uncertainty."],
                    ["newborn_diagnosis", "Baby already born, diagnosed at birth or shortly after", "CAN say 'Congratulations on your baby!' Lead with warmth, introduce peer groups."],
                    ["seeking_community", "Looking for parent groups, communities, connections", "Be direct about what DSDN offers. Share the Rockin' Parents App."],
                    ["seeking_resources", "Looking for specific resources, therapies, early intervention info", "Resource-focused. Link to specific DSDN pages. Mention AAP recognition."],
                    ["medical_professional", "Doctor, nurse, genetic counselor, or other medical professional", "Informational, professional tone. Share provider resources."],
                    ["sharing_experience", "Parent sharing their ongoing journey, milestones, story", "Acknowledge their journey warmly. Mention DSDN only if natural."],
                    ["loss", "Post about pregnancy loss, TFMR, or infant loss related to DS", "EXTREME sensitivity. MINIMAL response. Express condolence. NEVER minimize grief."],
                ],
            },
        ],
    },

    # ── Draft Reply Generation ─────────────────────────────────────
    {
        "heading": "Draft Reply Generation",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "When a team member clicks 'Generate Reply' (or the tool is called directly), "
                    "the system generates a compassionate draft reply tailored to the post type, "
                    "platform, and DSDN's brand voice. **Replies are always drafts** — a human "
                    "team member reviews, personalizes, and manually posts them."
                ),
            },
        ],
    },
    {
        "heading": "Reply Generation Process",
        "level": 2,
        "content": [
            {
                "type": "numbered_list",
                "items": [
                    "Load the opportunity from the database (title, content, platform, post type)",
                    "If post type isn't set yet, classify it via LLM",
                    "Select the best-matching canned response template based on post type",
                    "Load DSDN brand voice and platform-specific guidelines",
                    "Build an LLM prompt combining: original post, canned template, brand voice, platform guidelines, and post-type-specific instructions",
                    "Generate the reply via Anthropic Claude (Sonnet model)",
                    "Run the 7-point content safety check",
                    "If critical safety checks fail, prepend [SAFETY WARNING] to the reply",
                    "Store the draft reply and which canned template was used in the database",
                    "Return the reply text, safety warnings, and template info to the team member",
                ],
            },
        ],
    },
    {
        "heading": "Canned Response Templates",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The system comes pre-seeded with 6 canned response templates that serve as "
                    "starting points for the LLM. These are stored in the Google Sheet's 'Canned "
                    "Responses' tab and can be edited by the team. Usage is tracked — the system "
                    "records which template was used for each reply, creating a learning loop "
                    "where the team can see which templates lead to the best outcomes."
                ),
            },
            {
                "type": "table",
                "headers": ["Scenario", "Template Summary", "Key Notes"],
                "rows": [
                    ["Prenatal Diagnosis (general)", "'So many parents have been right where you are, and you are not alone...'", "NO 'congratulations'. Lead with empathy."],
                    ["Newborn Diagnosis", "'Congratulations on your baby! Welcome to a community of incredible families...'", "CAN say congratulations. Warm, celebratory."],
                    ["Seeking Community", "'There's a wonderful community of parents who get it. DSDN has 22,000+ parents...'", "Direct about what DSDN offers."],
                    ["Seeking Resources", "'DSDN has some great resources — recognized by the American Academy of Pediatrics...'", "Resource-focused. AAP credibility."],
                    ["Medical Professional", "'Thank you for your dedication. DSDN partners with medical professionals...'", "Professional, informational tone."],
                    ["Loss / TFMR", "'I'm so sorry for your loss. Whatever your experience, you're welcome here...'", "EXTREME CARE. Minimal. Never minimize."],
                ],
            },
        ],
    },
    {
        "heading": "Platform-Specific Customization",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "**Reddit**: Conversational tone, no corporate-speak, match subreddit culture. Keep under 500 characters. Use markdown sparingly.",
                    "**Glowing.com**: Supportive, personal, warm community tone. Can be slightly longer than Reddit. Friendly and encouraging.",
                ],
            },
        ],
    },

    # ── Content Safety ─────────────────────────────────────────────
    {
        "heading": "Content Safety Checks",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Every generated reply passes through a 9-point automatic safety checker "
                    "before being shown to the team. Critical failures (checks 1, 2, 4, 7) block "
                    "the reply from being stored without a [SAFETY WARNING] prefix. Non-critical "
                    "warnings are informational."
                ),
            },
            {
                "type": "table",
                "headers": ["#", "Check", "Severity", "Description"],
                "rows": [
                    ["1", "Wrong Domain", "CRITICAL", "Rejects if reply contains 'dsdn.org' — must use 'dsdiagnosisnetwork.org' (DSDN does not own dsdn.org)"],
                    ["2", "Deficit Language", "CRITICAL", "Flags 'suffering from', 'afflicted', 'birth defect', 'special needs', 'retarded', 'mongolism', 'mongoloid'"],
                    ["3", "Person-First Violations", "Warning", "Flags 'Down syndrome child' instead of 'child with Down syndrome' (pattern: Down syndrome + noun without preposition)"],
                    ["4", "Inappropriate Congratulations", "CRITICAL", "Flags 'congratulations' in prenatal_diagnosis or loss posts"],
                    ["5", "PII Leak", "Warning", "Detects email addresses, SSNs, phone numbers accidentally included from the original post"],
                    ["6", "Length Check", "Warning", "Reddit: max 500 chars. All platforms: min 50 chars."],
                    ["7", "Link Validation", "CRITICAL", "Ensures all DSDN links use the correct domain (dsdiagnosisnetwork.org)"],
                    ["8", "Assumption Detection", "Warning", "Flags projected roles, beliefs, or emotions not stated in the original post (e.g., 'your husband', 'your church', 'your faith', 'you must be devastated', 'your insurance') — 18 assumption phrases checked"],
                    ["9", "Savior / Recruitment Tone", "Warning", "Flags inspiration framing and recruitment language ('we are the leading', 'sign up today', 'let us help you through this', 'everything happens for a reason', 'god only gives special children to special parents') — 24 savior phrases checked"],
                ],
            },
        ],
    },

    # ── Cross-Platform Dedup ───────────────────────────────────────
    {
        "heading": "Cross-Platform Deduplication",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Parents sometimes post the same content across multiple platforms. The system "
                    "uses two layers of deduplication to prevent the team from seeing the same "
                    "family's post twice:"
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "**Source-level dedup**: Each post has a unique source_id per platform (e.g., Reddit post ID, Glowing.com topic ID). If the same source_id already exists, the post is skipped.",
                    "**Cross-platform dedup via content hash**: A SHA-256 hash is computed from the normalized (lowercased, trimmed) title + content. If the same content_hash already exists from any platform, the post is skipped and logged.",
                ],
            },
        ],
    },

    # ── Google Sheet Dashboard ─────────────────────────────────────
    {
        "heading": "Google Sheets Dashboard",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The dashboard is the team's primary interface for managing outreach. Created "
                    "via the 'create_outreach_dashboard' tool (one-time setup), it's a Google "
                    "Spreadsheet with 6 tabs. The database is the source of truth — the Sheet is "
                    "a synced view updated every 30 minutes. Dropdown values (Status, Claimed By, "
                    "Outcome) are managed centrally in the Dropdowns tab and dynamically referenced "
                    "by all queue tabs via ONE_OF_RANGE data validation."
                ),
            },
        ],
    },
    {
        "heading": "Tab 1: Outreach Queue",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The main working tab. Contains all active outreach candidates with their "
                    "scores, post types, draft replies, claim status, and outcomes."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Columns (18 total):**",
            },
            {
                "type": "bullets",
                "items": [
                    "A: Post Date — When the original post was published",
                    "B: Date Found — When the post was first discovered by the scanner",
                    "C: Opportunity ID — Internal UUID for system reference",
                    "D: Platform — Reddit, Glowing, or RSS",
                    "E: Post Title/Summary — Truncated to 200 chars",
                    "F: Post URL — Direct link to the original post",
                    "G: Score — Total outreach score (0-40)",
                    "H: Post Type — prenatal_diagnosis, newborn_diagnosis, loss, etc.",
                    "I: Sensitivity? — [SENSITIVE] flag for loss posts or high-urgency",
                    "J: Engagement Risk? — Political, hostile, misinfo, bait, or none",
                    "K: Draft Reply — AI-generated reply text (if requested)",
                    "L: Reviewer Notes — Free-text notes from the reviewer (no dropdown — plain text)",
                    "M: Status — Dropdown (dynamically populated from Dropdowns tab): New / Claimed / Responded / Skipped",
                    "N: Claimed Date/Time — Timestamp of claim",
                    "O: Claimed By — Dropdown (dynamically populated from Dropdowns tab): team member names",
                    "P: Response Notes — Free-text notes from the responder",
                    "Q: Response URL — Link to the actual response posted",
                    "R: Outcome — Dropdown (dynamically populated from Dropdowns tab): Connected / No Response / Declined / Already Connected / Referred Elsewhere",
                ],
            },
        ],
    },
    {
        "heading": "Tab 2: Search Terms",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The team manages include/exclude keywords here. Changes sync to the database "
                    "every 15 minutes. Each term has a Type (Include/Exclude), Platform filter "
                    "(All/Reddit/Glowing), and Active toggle (Yes/No)."
                ),
            },
        ],
    },
    {
        "heading": "Tab 3: Canned Responses",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Stores the 6 canned response templates with scenario labels, full template "
                    "text, platform notes, usage count, and success rate. The team can edit "
                    "templates directly in the Sheet. Usage is tracked automatically — the system "
                    "records which template was used as a base for each generated reply."
                ),
            },
        ],
    },
    {
        "heading": "Tab 4: Team Dashboard",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Performance summary per team member: posts claimed, posts responded, average "
                    "response time, connected rate, weekly/monthly counts, and pending claims."
                ),
            },
        ],
    },
    {
        "heading": "Tab 5: Archive",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Same columns as the Outreach Queue. Rows are automatically moved here when "
                    "older than 30 days and status is Responded or Skipped. This prevents the "
                    "active Queue tab from growing unbounded."
                ),
            },
        ],
    },

    {
        "heading": "Tab 6: Dropdowns (Single Source of Truth)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The Dropdowns tab centralizes all dropdown values used across queue tabs. "
                    "When the team needs to add a new status, team member, or outcome, they edit "
                    "this tab once — all queue tabs (Outreach Queue, DS Subreddit Queue, Glowing "
                    "Queue, Archive, and any future queue tabs) automatically reflect the change."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Columns:**",
            },
            {
                "type": "bullets",
                "items": [
                    "A: Status — Default values: New, Claimed, Responded, Skipped",
                    "B: Claimed By — Team member names (seeded from OUTREACH_TEAM_MEMBERS env var during initial creation; managed here going forward)",
                    "C: Outcome — Default values: Connected, No Response, Declined, Already Connected, Referred Elsewhere",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Technical implementation:**",
            },
            {
                "type": "bullets",
                "items": [
                    "Dropdown validation uses ONE_OF_RANGE (not ONE_OF_LIST), referencing ranges like =Dropdowns!$A$2:$A$50",
                    "The apply_dropdown_validations tool detects column positions by reading header rows (not hardcoded), supporting different column layouts across tabs",
                    "Validation is applied with strict=False, so existing cell values are preserved even if they don't match the current dropdown list",
                    "Range references extend to row 50, allowing the team to add up to ~48 values per column without needing code changes",
                    "The OUTREACH_TEAM_MEMBERS environment variable is deprecated — the Dropdowns tab is now the single source of truth for Claimed By values",
                ],
            },
        ],
    },

    # ── Engagement Risk Assessment ────────────────────────────────
    {
        "heading": "Engagement Risk Assessment",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Before drafting a reply, the system automatically assesses whether the "
                    "thread is safe to engage with. This prevents the team from inadvertently "
                    "entering political debates, hostile threads, or misinformation discussions "
                    "where DSDN's response could be taken out of context."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Risk levels:**",
            },
            {
                "type": "bullets",
                "items": [
                    "**none** — Safe to engage. Thread is a genuine support request or discussion.",
                    "**political** — Thread is primarily about abortion politics or pro-life/pro-choice arguments. Engaging could position DSDN in a political context.",
                    "**hostile** — Thread is brigaded with hostile commenters or personal attacks. Engaging could expose DSDN to negativity.",
                    "**misinfo** — Thread contains medical misinformation (anti-vax, false cures, misleading statistics). Engaging could inadvertently amplify bad information.",
                    "**bait** — Post appears designed to provoke outrage; account history suggests trolling. Engaging would waste team time.",
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "The risk level is displayed in column J (Engagement Risk?) of the Outreach "
                    "Queue. Posts with non-none risk levels still appear in the queue for the team "
                    "to review, but the risk flag helps prioritize and avoid problematic threads."
                ),
            },
        ],
    },

    # ── Slack Integration ──────────────────────────────────────────
    {
        "heading": "Slack Integration",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Real-time notifications are sent to the #dsdn-outreach Slack channel whenever "
                    "a post scores at or above the threshold (default: 20). Notifications use Slack "
                    "Block Kit with interactive buttons."
                ),
            },
        ],
    },
    {
        "heading": "Notification Format",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Each notification includes:",
            },
            {
                "type": "bullets",
                "items": [
                    "Header: 'New Outreach Candidate' (with [SENSITIVE] flag if applicable)",
                    "Post title/summary (truncated)",
                    "Platform, score, and post type",
                    "Content preview (first ~200 characters of the original post)",
                    "Link to view the original post",
                    "Three action buttons: Claim, Generate Reply, Skip",
                ],
            },
        ],
    },
    {
        "heading": "Action Buttons",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "**Claim**: Sets claimed_by to the Slack user. Button changes to 'Claimed by @name'. Updates DB + Sheet.",
                    "**Generate Reply**: Calls the AI reply generator. Posts the draft reply in a thread under the notification, including safety warnings and which canned template was used.",
                    "**Skip**: Marks the post as skipped. Buttons replaced with 'Skipped by @name'.",
                ],
            },
        ],
    },
    {
        "heading": "On-Demand Scanning",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Team members can trigger an immediate scan by typing /outreach-scan in the "
                    "#dsdn-outreach channel. This bypasses the 4-hour schedule for situations "
                    "where urgency demands faster response."
                ),
            },
        ],
    },

    # ── Scheduled Tasks ────────────────────────────────────────────
    {
        "heading": "Scheduled Tasks",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Three automated tasks run on configurable intervals:",
            },
            {
                "type": "table",
                "headers": ["Task", "Interval", "What It Does"],
                "rows": [
                    ["Outreach Scan", "Every 8 hours", "Scans Reddit + Glowing.com, scores posts, sends Slack notifications for high-scoring candidates"],
                    ["Search Term Sync", "Every 15 minutes", "Reads Google Sheet 'Search Terms' tab and updates the DB config (lightweight — one Sheet read)"],
                    ["Dashboard Sync", "Every 30 minutes", "Syncs DB to Google Sheet (new rows, status updates) and archives old items (>30 days)"],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "All intervals are configurable via environment variables. A **dry run mode** "
                    "(OUTREACH_DRY_RUN=true) runs scans and logs results without posting to Slack "
                    "or writing to the Sheet — useful for tuning search terms."
                ),
            },
        ],
    },

    # ── Outreach Workflow Status Lifecycle ──────────────────────────
    {
        "heading": "Outreach Status Lifecycle",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Each outreach opportunity progresses through a defined status lifecycle:",
            },
            {
                "type": "paragraph",
                "text": "**new** → **claimed** → **draft_generated** → **responded** → (archive after 30 days)",
            },
            {
                "type": "paragraph",
                "text": "Posts can also be marked **skipped** at any point and will be archived.",
            },
            {
                "type": "paragraph",
                "text": (
                    "After responding, the team records an **outcome**: connected, no_response, "
                    "declined, already_connected, or referred_elsewhere. Outcomes feed the Team "
                    "Dashboard stats and the canned response learning loop (tracking which "
                    "templates lead to the best connection rates)."
                ),
            },
        ],
    },

    # ── Database Schema ────────────────────────────────────────────
    {
        "heading": "Database Schema Changes",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "10 new columns were added to the existing 'opportunities' table via an "
                    "idempotent migration (runs safely on every startup, skips if columns "
                    "already exist):"
                ),
            },
            {
                "type": "table",
                "headers": ["Column", "Type", "Purpose"],
                "rows": [
                    ["claimed_by", "TEXT", "Name of the team member who claimed the post"],
                    ["claimed_at", "TEXT", "ISO timestamp of when the claim was made"],
                    ["response_url", "TEXT", "Link to the actual response posted on the platform"],
                    ["response_notes", "TEXT", "Free-text notes from the responder"],
                    ["draft_reply", "TEXT", "AI-generated draft reply text"],
                    ["platform_post_type", "TEXT", "Classified post type (prenatal_diagnosis, loss, etc.)"],
                    ["outreach_status", "TEXT", "Workflow status (new, claimed, draft_generated, responded, skipped)"],
                    ["outreach_outcome", "TEXT", "Final outcome (connected, no_response, declined, etc.)"],
                    ["content_hash", "TEXT", "SHA-256 hash for cross-platform deduplication"],
                    ["canned_response_used", "TEXT", "Which canned template was used as the base for the reply"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**Indexes added:**",
            },
            {
                "type": "bullets",
                "items": [
                    "idx_opportunities_outreach — Composite index on (workspace_id, outreach_status, created_at DESC) for fast queue queries",
                    "idx_opportunities_content_hash — Partial index on content_hash (WHERE content_hash IS NOT NULL) for fast dedup lookups",
                ],
            },
        ],
    },

    # ── Configuration ──────────────────────────────────────────────
    {
        "heading": "Configuration",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "All settings are configured via environment variables:",
            },
            {
                "type": "table",
                "headers": ["Variable", "Default", "Description"],
                "rows": [
                    ["OUTREACH_ENABLED", "false", "Master toggle for the outreach system"],
                    ["OUTREACH_SPREADSHEET_ID", "(empty)", "Google Sheet ID for the dashboard (set automatically by create_outreach_dashboard)"],
                    ["SLACK_OUTREACH_CHANNEL", "#dsdn-outreach", "Slack channel for outreach notifications"],
                    ["OUTREACH_SCAN_INTERVAL_HOURS", "8", "How often automated scans run"],
                    ["OUTREACH_SCORE_THRESHOLD", "20", "Minimum score to trigger Slack notification"],
                    ["OUTREACH_TEAM_MEMBERS", "(empty)", "DEPRECATED — used only for initial Dropdowns tab seeding. Manage team members via the Dropdowns tab going forward."],
                    ["OUTREACH_DRY_RUN", "false", "Scan and log without posting to Slack/Sheet"],
                ],
            },
        ],
    },

    # ── Files Reference ────────────────────────────────────────────
    {
        "heading": "Files Reference",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "**New files created:**",
            },
            {
                "type": "table",
                "headers": ["File", "Purpose"],
                "rows": [
                    ["agents/outreach_scanner.py", "Core agent — 11 tools, Glowing.com scraper, engagement risk, scoring engine"],
                    ["outreach/__init__.py", "Package init, re-exports"],
                    ["outreach/dashboard.py", "Google Sheet dashboard — 6-tab create, dynamic dropdown validation (ONE_OF_RANGE), read, write, archive"],
                    ["outreach/search_terms.py", "Search terms sync (GSheet ↔ DB), keyword matching with word-boundary regex"],
                    ["outreach/replies.py", "Draft reply generator — post-type classification, engagement risk assessment, LLM prompting, canned response selection, reviewer notes parsing"],
                    ["outreach/safety.py", "Content safety checker — 9-point quality gate (including assumption detection and savior/recruitment tone)"],
                    ["scripts/fix_outreach_queue_alignment.py", "Diagnostic/fix script — remove misaligned rows, clear bad validation, add Dropdowns tab, apply validations"],
                    ["scripts/add_dropdowns_tab.py", "Migration script — idempotent Dropdowns tab creation + dropdown validation application"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**Modified files:**",
            },
            {
                "type": "table",
                "headers": ["File", "Changes"],
                "rows": [
                    ["db/schema.py", "10 new outreach columns + 2 indexes on opportunities table"],
                    ["db/database.py", "Idempotent migration execution"],
                    ["db/models.py", "OutreachStatus and OutreachOutcome enums, extended Opportunity model"],
                    ["db/repositories.py", "9 new methods on OpportunityRepo (claim, respond, outcome, stats, archive, etc.)"],
                    ["config.py", "7 new outreach configuration settings"],
                    ["agents/orchestrator.py", "Wired outreach scanner as tool #35"],
                    ["agents/factory.py", "Instantiate and register outreach scanner agent"],
                    ["runtime/session.py", "Action formatting for outreach scanner"],
                    ["scheduler/tasks.py", "3 automated task factories + Slack Block Kit notification builder"],
                ],
            },
        ],
    },

    # ── Further Tests & Hypotheses ───────────────────────────────
    {
        "heading": "Further Tests & Hypotheses",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The core Outreach Queue (Reddit + Glowing.com) is the production baseline. "
                    "The following tests and platform expansions are in various stages of planning "
                    "and prototyping. Each represents a hypothesis about where DSDN can find and "
                    "connect with newly diagnosed families. The system architecture supports "
                    "adding new platform queues as separate Google Sheet tabs without code changes "
                    "to the dashboard or dropdown validation layer."
                ),
            },
        ],
    },

    # ── Test 1: Cross-Reddit / DS Subreddit Queue ─────────────────
    {
        "heading": "Test 1: Cross-Reddit Expansion (DS Subreddit Queue)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Hypothesis:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "The current Outreach Queue scans general pregnancy and parenting subreddits "
                    "(r/BabyBumps, r/pregnant, etc.) where Down syndrome posts surface among broader "
                    "content. A dedicated scan of the r/DownSyndrome subreddit should yield a higher "
                    "density of relevant posts with stronger DSDN Fit scores, since posters in a "
                    "diagnosis-specific subreddit are more likely to be in the diagnosis-to-age-3 "
                    "window that DSDN serves."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Implementation:**",
            },
            {
                "type": "bullets",
                "items": [
                    "A separate 'DS Subreddit Queue' tab in the same Google Sheet, with the same 18-column layout as the Outreach Queue",
                    "Shares the same Dropdowns tab for Status, Claimed By, and Outcome values (dynamic ONE_OF_RANGE validation already applied)",
                    "Uses the same Reddit Ingest Agent (public JSON feeds) but configured for r/DownSyndrome specifically",
                    "Separate tab allows the team to evaluate signal quality independently — is r/DownSyndrome yielding higher-quality outreach candidates than general subreddits?",
                    "Same scoring system (4-dimension, max 40) but may warrant adjusted thresholds since the subreddit is diagnosis-specific",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Key metrics to track:**",
            },
            {
                "type": "bullets",
                "items": [
                    "Post volume: how many new posts per week in r/DownSyndrome vs general subreddits?",
                    "Score distribution: are r/DownSyndrome posts scoring higher on average?",
                    "Connection rate: what percentage of outreach attempts result in 'Connected' outcomes?",
                    "Post type mix: is the distribution of prenatal vs newborn vs seeking_community different?",
                    "Overlap rate: how many r/DownSyndrome posts are cross-posted to general subreddits and already captured?",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Status:** Tab created. Scanning active. Dropdown validations applied. Evaluating initial results.",
            },
        ],
    },

    # ── Test 2: Glowing Queue ─────────────────────────────────────
    {
        "heading": "Test 2: Glowing.com Dedicated Queue (Glowing Queue)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Hypothesis:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "Glowing.com (formerly Glow Community) hosts a 272-member Down Syndrome group "
                    "with publicly accessible posts. While the core Outreach Queue includes Glowing.com "
                    "posts alongside Reddit, a dedicated Glowing Queue tab would let the team evaluate "
                    "the platform's signal quality separately and track platform-specific engagement patterns."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Implementation:**",
            },
            {
                "type": "bullets",
                "items": [
                    "A separate 'Glowing Queue' tab in the same Google Sheet, same 18-column layout",
                    "Shares Dropdowns tab for all dropdown values (dynamic validation already applied)",
                    "Glowing.com posts routed to this dedicated tab instead of the main Outreach Queue",
                    "The httpx-based Glowing.com scraper extracts embedded JSON data (window.__gl_page_init_data) with fallback to HTML meta tag extraction",
                    "3-second delay between requests, max 20 pages per scan, respectful User-Agent identifying DSDN as a nonprofit",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Current observations:**",
            },
            {
                "type": "bullets",
                "items": [
                    "The Glowing.com DS-specific group has been largely inactive since January 2022 — new posts are rare",
                    "General pregnancy groups on Glowing.com occasionally surface relevant posts, but volume is low",
                    "The platform's value may be limited compared to Reddit, which has higher post volume and more active communities",
                    "Maintaining the scraper has minimal cost (read-only, lightweight), so keeping it running as a supplementary signal is reasonable",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Status:** Tab created. Scraper active but low volume. Dropdown validations applied. Monitoring for signal quality.",
            },
        ],
    },

    # ── Test 3: BabyCenter ────────────────────────────────────────
    {
        "heading": "Test 3: BabyCenter",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Hypothesis:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "BabyCenter is one of the largest pregnancy and parenting communities online, "
                    "with active birth month groups and condition-specific forums. Families receiving "
                    "a prenatal diagnosis frequently post to BabyCenter's community boards seeking "
                    "support, making it a potentially high-value source for outreach candidates."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Technical considerations:**",
            },
            {
                "type": "bullets",
                "items": [
                    "BabyCenter requires account creation to view community posts — unlike Reddit (public JSON) and Glowing.com (public HTML), this would need authenticated scraping",
                    "Terms of Service review required before implementing any scraping — BabyCenter may prohibit automated access",
                    "If TOS permits: credential-based httpx session with login flow, rate limiting, and respectful access patterns",
                    "If TOS prohibits scraping: Google Alerts can surface BabyCenter posts that are indexed by Google (see Test 5 below for details)",
                    "Could also be approached via manual monitoring with the team checking BabyCenter periodically — the system would just track and manage the workflow in a dedicated Sheet tab",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Expected signal quality:**",
            },
            {
                "type": "bullets",
                "items": [
                    "High — BabyCenter birth month groups contain active, emotionally candid conversations from expecting parents",
                    "Post volume likely higher than Glowing.com for prenatal diagnosis discussions",
                    "BabyCenter's community norms tend toward supportive, making outreach responses more likely to be well-received",
                    "Risk: BabyCenter has moderators who may flag or remove unsolicited organization mentions — reply tone must be peer-to-peer, not organizational promotion",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Status:** Not yet implemented. TOS review and feasibility assessment needed before building a scraper. Google Alerts is the low-risk path to surface BabyCenter content.",
            },
        ],
    },

    # ── Test 4: What To Expect ────────────────────────────────────
    {
        "heading": "Test 4: What To Expect",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Hypothesis:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "What To Expect (WhatToExpect.com) has large, active community forums organized "
                    "by birth month and topic. Families post about prenatal testing results, NIPT "
                    "positives, and Down syndrome diagnoses in these forums. Like BabyCenter, this "
                    "could be a high-volume source of outreach candidates."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Technical considerations:**",
            },
            {
                "type": "bullets",
                "items": [
                    "Similar to BabyCenter — requires account creation for full community access",
                    "Terms of Service review required before any automated scanning",
                    "If feasible: same authenticated httpx approach as BabyCenter would be used",
                    "Google Alerts fallback: WhatToExpect forum posts are often indexed by Google, so Google Alerts can surface them without scraping",
                    "What To Expect also has a mobile app with community features — app content may not be web-accessible",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Expected signal quality:**",
            },
            {
                "type": "bullets",
                "items": [
                    "High — What To Expect birth month groups are among the most active pregnancy communities",
                    "Prenatal testing discussions (NIPT, amnio, CVS results) are common, especially in first-trimester groups",
                    "Community tone is generally supportive, similar to BabyCenter",
                    "Risk: same as BabyCenter — moderators may restrict organizational mentions in peer support threads",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Status:** Not yet implemented. Same TOS review needed as BabyCenter. Google Alerts is the low-risk entry point.",
            },
        ],
    },

    # ── Test 5: Facebook Groups via Google Alerts ─────────────────
    {
        "heading": "Test 5: Facebook Groups via Google Alerts",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Hypothesis:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "Facebook hosts some of the largest Down syndrome parent communities (Lucky Few, "
                    "T21 Moms, Down syndrome parent groups with thousands of members). Direct "
                    "automation of Facebook is not viable (high ban risk for a nonprofit account), "
                    "but Google Alerts can surface Facebook posts that are publicly indexed by search "
                    "engines. This provides a low-risk signal without any direct Facebook interaction."
                ),
            },
            {
                "type": "paragraph",
                "text": "**How this would work:**",
            },
            {
                "type": "numbered_list",
                "items": [
                    "Set up Google Alerts for queries like: '\"down syndrome diagnosis\" site:facebook.com', '\"NIPT positive\" site:facebook.com', '\"trisomy 21\" site:facebook.com'",
                    "Google Alerts delivers matching results — NOT via email notifications, but via an n8n workflow that processes Google Alerts RSS feeds directly",
                    "The n8n workflow parses the alert data, extracts Facebook post URLs and snippet text, and passes them to the Outreach Scanner Agent",
                    "The agent scores the alert content using the standard 4-dimension system and adds qualifying items to a dedicated queue tab",
                    "Team members review the alerts, and if the post is in a public group, can respond directly on Facebook (manually — the system never automates Facebook posting)",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Important distinctions:**",
            },
            {
                "type": "bullets",
                "items": [
                    "This approach uses Google Alerts RSS feeds processed by an n8n workflow — NOT email notifications to an inbox",
                    "The system never logs into Facebook, never scrapes Facebook, and never posts to Facebook — it only processes what Google has already indexed",
                    "Coverage is limited to public posts that Google indexes — private group posts (the majority on Facebook) will not surface",
                    "This is a supplementary signal, not a primary scanning channel — volume will be low but any match is likely high-quality",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Status:** Not yet implemented. Requires setting up Google Alerts and building the n8n RSS processing workflow. Low effort, low risk.",
            },
        ],
    },

    # ── Test 6: Other Contemplated Platforms ──────────────────────
    {
        "heading": "Test 6: Other Contemplated Platforms",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Several other platforms have been discussed as potential scanning targets. "
                    "These are in the early consideration phase — no implementation work has started."
                ),
            },
            {
                "type": "paragraph",
                "text": "**The Bump (thebump.com):**",
            },
            {
                "type": "bullets",
                "items": [
                    "Active pregnancy community with forums and birth month groups",
                    "Similar TOS/access considerations as BabyCenter and What To Expect",
                    "Google Alerts can surface indexed content as a first step",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Instagram and TikTok (via Google Alerts):**",
            },
            {
                "type": "bullets",
                "items": [
                    "Parents share diagnosis stories on Instagram and TikTok with hashtags like #T21, #DownSyndromeDiagnosis, #NIPTPositive",
                    "Direct scraping is not viable (API restrictions, TOS), but Google Alerts can surface publicly indexed posts",
                    "These platforms are primarily visual/video — outreach response would be via comments, which has different dynamics than text forums",
                    "Lower priority: text-based forums are more natural for the kind of supportive conversation DSDN offers",
                ],
            },
            {
                "type": "paragraph",
                "text": "**HealthUnlocked and PatientsLikeMe:**",
            },
            {
                "type": "bullets",
                "items": [
                    "Health-focused community platforms where parents discuss medical conditions including Down syndrome",
                    "Smaller user bases than Reddit or BabyCenter, but higher signal-to-noise ratio for diagnosis-related content",
                    "Would require custom scraper or Google Alerts approach depending on access model",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Google Alerts as a universal fallback:**",
            },
            {
                "type": "paragraph",
                "text": (
                    "For any platform where direct scraping is infeasible (TOS restrictions, "
                    "authentication requirements, ban risk), Google Alerts serves as a universal "
                    "fallback. By setting up alerts like '\"down syndrome diagnosis\" site:babycenter.com' "
                    "or '\"NIPT positive\" site:whattoexpect.com', the system can surface publicly "
                    "indexed content from any platform without needing platform-specific scrapers. "
                    "The n8n workflow approach (RSS feed processing, not email) scales to any number "
                    "of alert queries."
                ),
            },
        ],
    },

    # ── Platform Prioritization Matrix ────────────────────────────
    {
        "heading": "Platform Prioritization",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The following matrix summarizes the expected value and feasibility of each "
                    "platform expansion:"
                ),
            },
            {
                "type": "table",
                "headers": ["Platform", "Expected Volume", "Signal Quality", "Implementation Effort", "Risk Level", "Status"],
                "rows": [
                    ["Reddit (general subs)", "High", "Medium", "Done", "Low", "Production"],
                    ["Reddit (r/DownSyndrome)", "Medium", "High", "Done", "Low", "Testing"],
                    ["Glowing.com", "Low", "Medium", "Done", "Low", "Active (low volume)"],
                    ["BabyCenter", "High", "High", "Medium (TOS review)", "Medium", "Planned"],
                    ["What To Expect", "High", "High", "Medium (TOS review)", "Medium", "Planned"],
                    ["Facebook (via Google Alerts)", "Low", "High", "Low (n8n workflow)", "Low", "Planned"],
                    ["The Bump", "Medium", "Medium", "Medium", "Medium", "Considered"],
                    ["Instagram/TikTok (via Alerts)", "Low", "Medium", "Low", "Low", "Considered"],
                    ["HealthUnlocked", "Low", "High", "Medium", "Low", "Considered"],
                ],
            },
        ],
    },

    # ── Not Planned ───────────────────────────────────────────────
    {
        "heading": "Not Planned",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "The following approaches have been explicitly ruled out:",
            },
            {
                "type": "bullets",
                "items": [
                    "**Direct Facebook automation** — Account ban risk is too high for a nonprofit. Facebook aggressively detects and bans automated activity. The Google Alerts approach captures publicly indexed content without this risk.",
                    "**Direct Instagram/TikTok scraping** — Same ban risk as Facebook, plus these platforms are primarily visual, making text-based outreach less natural.",
                    "**Automated posting/replying** — The system will NEVER automatically post responses on any platform. All replies are drafts reviewed and manually posted by human team members. This is a core design principle, not a future feature.",
                ],
            },
        ],
    },
]


# ── Build Google Doc ───────────────────────────────────────────────
def heading_style(level: int) -> str:
    return f"HEADING_{min(level, 6)}"


def build_doc(docs_service: Any, drive_service: Any) -> str:
    """Create the Google Doc, populate it, share it. Returns the URL."""

    # 1. Create empty doc
    doc = docs_service.documents().create(body={"title": TITLE}).execute()
    doc_id = doc["documentId"]
    print(f"Created document: {doc_id}")

    # 2. Build requests
    requests: List[Dict[str, Any]] = []
    cursor = 1

    for section in SECTIONS:
        h = section.get("heading", "")
        lvl = section.get("level", 1)
        blocks = section.get("content", [])

        # Insert heading
        if h:
            htxt = h + "\n"
            requests.append({"insertText": {"location": {"index": cursor}, "text": htxt}})
            h_start, h_end = cursor, cursor + len(htxt)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": h_start, "endIndex": h_end},
                    "paragraphStyle": {
                        "namedStyleType": heading_style(lvl),
                        "spaceAbove": {"magnitude": 14 if lvl == 1 else 10, "unit": "PT"},
                        "spaceBelow": {"magnitude": 4, "unit": "PT"},
                    },
                    "fields": "namedStyleType,spaceAbove,spaceBelow",
                }
            })
            cursor = h_end

        # Content blocks
        for block in blocks:
            btype = block.get("type", "paragraph")

            if btype == "paragraph":
                text = block["text"]
                para_text = text + "\n"
                plain, runs = parse_inline(para_text)
                requests.append({"insertText": {"location": {"index": cursor}, "text": plain}})
                p_start, p_end = cursor, cursor + len(plain)
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": p_start, "endIndex": p_end},
                        "paragraphStyle": {"namedStyleType": "NORMAL_TEXT", "spaceBelow": {"magnitude": 6, "unit": "PT"}},
                        "fields": "namedStyleType,spaceBelow",
                    }
                })
                for rs, re_, style in runs:
                    abs_s, abs_e = cursor + rs, cursor + re_
                    if style == "bold":
                        requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"bold": True}, "fields": "bold"}})
                    elif style == "italic":
                        requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"italic": True}, "fields": "italic"}})
                cursor = p_end

            elif btype == "bullets":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append({"insertText": {"location": {"index": cursor}, "text": plain_item}})
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"bold": True}, "fields": "bold"}})
                        elif style == "italic":
                            requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"italic": True}, "fields": "italic"}})
                    cursor += len(plain_item)
                requests.append({"createParagraphBullets": {"range": {"startIndex": list_start, "endIndex": cursor}, "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"}})

            elif btype == "numbered_list":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append({"insertText": {"location": {"index": cursor}, "text": plain_item}})
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"bold": True}, "fields": "bold"}})
                        elif style == "italic":
                            requests.append({"updateTextStyle": {"range": {"startIndex": abs_s, "endIndex": abs_e}, "textStyle": {"italic": True}, "fields": "italic"}})
                    cursor += len(plain_item)
                requests.append({"createParagraphBullets": {"range": {"startIndex": list_start, "endIndex": cursor}, "bulletPreset": "NUMBERED_DECIMAL_NESTED"}})

            elif btype == "table":
                # Flush pending requests BEFORE inserting table (cursor must be accurate)
                if requests:
                    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
                    requests = []
                    time.sleep(0.3)
                    # Re-read to get accurate cursor
                    _ds = docs_service.documents().get(documentId=doc_id).execute()
                    _bc = _ds.get("body", {}).get("content", [])
                    if _bc:
                        cursor = _bc[-1].get("endIndex", cursor + 1) - 1

                headers = block["headers"]
                rows = block["rows"]
                num_cols = len(headers)
                num_rows = 1 + len(rows)

                # Insert table
                requests.append({"insertTable": {"rows": num_rows, "columns": num_cols, "location": {"index": cursor}}})

                # Batch execute to materialize the table
                if requests:
                    docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
                    requests = []
                    time.sleep(0.5)

                # Re-read to get table cell indices
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                table_elem = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_elem = elem  # take the last table (just inserted)

                if table_elem:
                    table = table_elem["table"]
                    all_rows = [headers] + rows
                    cell_inserts: List[Tuple[int, str]] = []
                    for ri, row_data in enumerate(all_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(table_row.get("tableCells", [])):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get("startIndex", 0)
                                cell_inserts.append((cell_idx, str(cell_val)))

                    # Sort descending (insert from end to avoid index shifts)
                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cidx, ctext in cell_inserts:
                        requests.append({"insertText": {"location": {"index": cidx}, "text": ctext}})

                    if requests:
                        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()
                        requests = []
                        time.sleep(0.5)

                    # Bold header row
                    doc_state2 = docs_service.documents().get(documentId=doc_id).execute()
                    bold_requests = []
                    for elem2 in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem2:
                            t2 = elem2["table"]
                            if len(t2.get("tableRows", [])) > 0:
                                header_row = t2["tableRows"][0]
                                for hcell in header_row.get("tableCells", []):
                                    for para in hcell.get("content", []):
                                        for el in para.get("paragraph", {}).get("elements", []):
                                            si = el.get("startIndex", 0)
                                            ei = el.get("endIndex", 0)
                                            if ei > si:
                                                bold_requests.append({"updateTextStyle": {"range": {"startIndex": si, "endIndex": ei}, "textStyle": {"bold": True}, "fields": "bold"}})
                    if bold_requests:
                        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": bold_requests}).execute()
                        time.sleep(0.5)

                # Update cursor — re-read doc to get accurate end position
                doc_state3 = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state3.get("body", {}).get("content", [])
                if body_content:
                    last = body_content[-1]
                    # endIndex of the last body element is the insertion point
                    cursor = last.get("endIndex", cursor + 1) - 1

    # Final batch
    if requests:
        docs_service.documents().batchUpdate(documentId=doc_id, body={"requests": requests}).execute()

    # 3. Share (restricted access)
    share_file_restricted(drive_service, doc_id)

    # 4. Move to CMO Agent folder
    try:
        from cmo_agent.google_auth import ensure_drive_folder, move_file_to_folder, share_file_restricted
        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
    except Exception as e:
        print(f"Warning: could not move to folder: {e}")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return url


# ── Main ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Initializing Google services...")
    docs_svc, drive_svc = get_services()

    print("Building document...")
    doc_url = build_doc(docs_svc, drive_svc)

    print(f"\nDone! Document created:")
    print(doc_url)
