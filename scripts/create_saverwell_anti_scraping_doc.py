"""Create the Saverwell Anti-Scraping & Site Protection Plan as a Google Doc.

Constructs the full document structure and creates it via the Docs Agent's
Google Docs API builder. Bypasses LLM generation to ensure exact content
fidelity.

Usage:
    python scripts/create_saverwell_anti_scraping_doc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the full anti-scraping plan document structure."""
    return {
        "title": "Saverwell - Anti-Scraping & Site Protection Plan",
        "include_toc": True,
        "sections": [
            # ── Overview ──────────────────────────────────────────────
            {
                "heading": "Overview",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This document is the implementation plan for protecting "
                            "Saverwell's merchant discount database (1,418 merchants, "
                            "8,762 discount records, 56,778 store locations) from "
                            "automated scraping. It preserves full access for "
                            "legitimate users and verified search engine crawlers."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Cloudflare plan requirement: Most rules work on Free/Pro. "
                            "Rate limiting custom rules require Pro ($20/mo). Bot "
                            "Management ML requires Business ($200/mo) - recommended "
                            "but not required."
                        ),
                    },
                ],
            },
            # ── 1. Bot Fight Mode ─────────────────────────────────────
            {
                "heading": "1. Bot Fight Mode",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Location: Settings > Security > Bots",
                    },
                ],
            },
            {
                "heading": "Configuration",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Bot Fight Mode: ON (Free plan)",
                            "Super Bot Fight Mode (Pro plan - recommended):",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Super Bot Fight Mode settings:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Definitely automated: Block",
                            "Likely automated: Managed Challenge",
                            "Verified bots: Allow",
                            "Static resource protection: ON",
                            "JavaScript detections: ON",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This is the single most impactful setting. Cloudflare "
                            "verifies that crawlers claiming to be Googlebot actually "
                            "originate from Google's published IP ranges. Scrapers "
                            "spoofing user agents get blocked; real search engines "
                            "pass through."
                        ),
                    },
                ],
            },
            # ── 2. Block AI Scrapers ──────────────────────────────────
            {
                "heading": "2. Block AI Scrapers and Crawlers",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Location: Settings > Security > Bots",
                    },
                ],
            },
            {
                "heading": "Configuration",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": ["AI Scrapers and Crawlers: Blocked"],
                    },
                    {
                        "type": "paragraph",
                        "text": "This blocks known AI training crawlers:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "GPTBot (OpenAI)",
                            "CCBot (Common Crawl)",
                            "Google-Extended (Gemini training)",
                            "Anthropic web crawler",
                            "Bytespider (ByteDance)",
                            "And others",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "These crawlers would ingest your structured discount data "
                            "into their training sets. Blocking them has zero SEO "
                            "impact - they are separate from Googlebot/Bingbot search "
                            "indexing crawlers, which remain allowed."
                        ),
                    },
                ],
            },
            # ── 3. WAF Custom Rules ───────────────────────────────────
            {
                "heading": "3. WAF Custom Rules",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Location: Security > WAF > Custom Rules",
                    },
                ],
            },
            # Rule 1
            {
                "heading": "Rule 1: Rate Limit - Aggressive Page Requests",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: Block scrapers hitting pages rapidly. A real "
                            "senior views 5-15 pages per session. A scraper hits "
                            "hundreds per minute."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Rate Limit - Page Requests"],
                            [
                                "When",
                                'URI path != "/api/" AND not contains "/static/" '
                                'AND not contains "/_next/" AND not contains "/assets/"',
                            ],
                            ["Action", "Managed Challenge"],
                            ["Rate", "30 requests per 1 minute per IP"],
                            ["Mitigation timeout", "60 seconds"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Why 30/min: That is one page every 2 seconds - faster "
                            "than any real user browses but catches scrapers quickly. "
                            "If a real user somehow triggers this (unlikely), they "
                            "just solve a Turnstile challenge and continue."
                        ),
                    },
                ],
            },
            # Rule 2
            {
                "heading": "Rule 2: Rate Limit - Supabase API Proxy",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: If your app proxies Supabase through a "
                            "server-side route (e.g., /api/), rate limit those "
                            "separately."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Rate Limit - API Requests"],
                            [
                                "When",
                                'URI path contains "/api/" OR contains "/rest/"',
                            ],
                            ["Action", "Block"],
                            ["Rate", "60 requests per 1 minute per IP"],
                            ["Mitigation timeout", "300 seconds (5 min block)"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Why stricter on API: API endpoints return structured "
                            "JSON - much easier to parse than HTML. A scraper "
                            "targeting your API is more dangerous than one scraping "
                            "pages."
                        ),
                    },
                ],
            },
            # Rule 3
            {
                "heading": "Rule 3: Block Known Scraping Tools",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: Block requests from common scraping frameworks "
                            "that identify themselves in user agent strings."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": "Block user agents containing any of:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Scrapy, python-requests, Go-http-client, Java/, libwww-perl",
                            "wget, curl, HTTPie, node-fetch, axios",
                            "puppeteer, PhantomJS, HeadlessChrome, Selenium, webdriver",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Action: Block",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Note: Sophisticated scrapers will spoof user agents. "
                            "This catches lazy scrapers and automated tools. More "
                            "advanced scrapers are caught by Bot Fight Mode's "
                            "JavaScript detection and behavioral analysis."
                        ),
                    },
                ],
            },
            # Rule 4
            {
                "heading": "Rule 4: Block Empty or Missing User Agents",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: Legitimate browsers always send a user agent. "
                            "Missing or empty user agents are almost always bots."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Block Empty User Agent"],
                            ["When", 'user_agent eq "" OR not user_agent'],
                            ["Action", "Block"],
                        ],
                    },
                ],
            },
            # Rule 5
            {
                "heading": "Rule 5: Challenge High-Volume Sessions",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: Catch scrapers that stay under the per-minute "
                            "rate limit but accumulate many requests over a session."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Rate Limit - Session Volume"],
                            [
                                "When",
                                'URI path != "/api/" AND not contains "/static/"',
                            ],
                            ["Action", "Block"],
                            ["Rate", "200 requests per 1 hour per IP"],
                            ["Mitigation timeout", "3600 seconds (1 hour block)"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Why 200/hour: Even an extremely active user would not "
                            "view 200 merchant pages in an hour. At this volume, "
                            "it is systematic scraping."
                        ),
                    },
                ],
            },
            # Rule 6
            {
                "heading": "Rule 6: Protect Merchant Directory Listing",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: The Store Directory / merchant listing pages "
                            "are the highest-value scraping target because they "
                            "aggregate multiple merchants on one page."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Rate Limit - Directory Pages"],
                            [
                                "When",
                                'URI path contains "/store-directory" OR '
                                '"/discounts" OR "/merchants"',
                            ],
                            ["Action", "Managed Challenge"],
                            ["Rate", "15 requests per 1 minute per IP"],
                            ["Mitigation timeout", "120 seconds"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Why tighter: Directory/listing pages contain multiple "
                            "merchants per page. A scraper hitting these pages can "
                            "extract data faster than hitting individual merchant "
                            "pages. Tighter limits here."
                        ),
                    },
                ],
            },
            # Rule 7
            {
                "heading": "Rule 7: Geographic Restriction (Optional)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Purpose: If Saverwell only serves US customers (senior "
                            "discounts at US merchants), block traffic from countries "
                            "commonly associated with scraping farms."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Setting", "Value"],
                        "rows": [
                            ["Name", "Geo Block - Non-US Traffic (Challenge)"],
                            [
                                "When",
                                'Country NOT in {"US", "CA", "GB", "AU"}',
                            ],
                            ["Action", "Managed Challenge"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            'Note: Use "Managed Challenge" not "Block" - this '
                            "allows legitimate users (e.g., a senior traveling "
                            "abroad) to pass through while stopping automated "
                            "traffic from scraping-heavy regions. Include CA/GB/AU "
                            "for snowbirds and English-speaking expats."
                        ),
                    },
                ],
            },
            # ── 4. Page Rules ─────────────────────────────────────────
            {
                "heading": "4. Cloudflare Page Rules",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Location: Rules > Page Rules",
                    },
                ],
            },
            {
                "heading": "Cache Static Content Aggressively",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["URL Pattern", "Setting"],
                        "rows": [
                            [
                                "saverwell.ai/static/*",
                                "Cache Level = Cache Everything, Edge Cache TTL = 1 month",
                            ],
                            [
                                "saverwell.ai/assets/*",
                                "Cache Level = Cache Everything, Edge Cache TTL = 1 month",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This reduces origin load and makes it harder for "
                            "scrapers to detect they are being rate-limited (cached "
                            "responses return faster, masking the throttling)."
                        ),
                    },
                ],
            },
            # ── 5. Transform Rules ────────────────────────────────────
            {
                "heading": "5. Cloudflare Transform Rules - Security Headers",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Location: Rules > Transform Rules. Add these response headers to all pages:",
                    },
                    {
                        "type": "table",
                        "headers": ["Header", "Value", "Purpose"],
                        "rows": [
                            [
                                "X-Content-Type-Options",
                                "nosniff",
                                "Prevents MIME type sniffing",
                            ],
                            [
                                "X-Frame-Options",
                                "DENY",
                                "Prevents iframe embedding (scraping vector)",
                            ],
                            [
                                "Referrer-Policy",
                                "strict-origin-when-cross-origin",
                                "Prevents leaking full URLs to third parties",
                            ],
                        ],
                    },
                ],
            },
            # ── 6. robots.txt ─────────────────────────────────────────
            {
                "heading": "6. robots.txt Recommendations",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Update your robots.txt file to block known scrapers "
                            "that respect it. This is a polite request - not "
                            "enforcement. Cloudflare WAF handles enforcement."
                        ),
                    },
                ],
            },
            {
                "heading": "Allow search engines",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "User-agent: Googlebot - Allow: /",
                            "User-agent: Bingbot - Allow: /",
                            "User-agent: Slurp - Allow: /",
                        ],
                    },
                ],
            },
            {
                "heading": "Block AI training crawlers",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "User-agent: GPTBot - Disallow: /",
                            "User-agent: Google-Extended - Disallow: /",
                            "User-agent: CCBot - Disallow: /",
                            "User-agent: anthropic-ai - Disallow: /",
                            "User-agent: Bytespider - Disallow: /",
                            "User-agent: ClaudeBot - Disallow: /",
                        ],
                    },
                ],
            },
            {
                "heading": "Block common scrapers",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "User-agent: Scrapy - Disallow: /",
                            "User-agent: AhrefsBot - Disallow: /",
                            "User-agent: SemrushBot - Disallow: /",
                            "User-agent: DotBot - Disallow: /",
                            "User-agent: MJ12bot - Disallow: /",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Default: User-agent: * - Allow: /",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "IMPORTANT: Do NOT include a public sitemap URL in "
                            "robots.txt. Submit your sitemap directly to Google "
                            "Search Console and Bing Webmaster Tools. A public "
                            "sitemap is a roadmap for scrapers - it lists every "
                            "URL they need to hit."
                        ),
                    },
                ],
            },
            # ── 7. Honeypot Pages ─────────────────────────────────────
            {
                "heading": "7. Honeypot Pages",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Create 5-10 fake merchant pages with plausible but "
                            "verifiably fake data. These serve as canaries - if a "
                            "competitor's site shows this fake data, you have proof "
                            "of scraping."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Fake Merchant",
                            "Fake Discount",
                            "Fake Requirement",
                        ],
                        "rows": [
                            ["GreenLeaf Market", "15% off Thursdays", "Ages 62+"],
                            ["Patriot Home Supply", "12% off Mondays", "Ages 58+"],
                            [
                                "SilverBridge Pharmacy",
                                "20% off Wednesdays",
                                "Ages 65+, AARP required",
                            ],
                            ["Cornerstone Grocers", "8% off daily", "Ages 60+"],
                            ["BrightPath Hardware", "10% off Fridays", "Ages 55+"],
                        ],
                    },
                ],
            },
            {
                "heading": "Implementation notes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Create these pages with real-looking URLs "
                            "(e.g., /store-directory/greenleaf-market)",
                            "Do NOT link them from navigation, sitemap, or any "
                            "visible page",
                            "Only a scraper crawling exhaustively or brute-forcing "
                            "URL patterns would find them",
                            'If a competitor\'s site shows "GreenLeaf Market 15% '
                            'off Thursdays for 62+" - you have proof of scraping',
                            "Document the fake data with timestamps for legal evidence",
                        ],
                    },
                ],
            },
            # ── 7b. Honeypot Detection System ────────────────────────
            {
                "heading": "Honeypot Detection System",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Four detection methods work together to catch anyone "
                            "who copies Saverwell's data. Each layer covers a "
                            "different type of scraping."
                        ),
                    },
                ],
            },
            {
                "heading": "Method 1: Canary Redirect URLs",
                "level": 3,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Each fake merchant's 'website' field in Supabase contains "
                            "a tracking redirect URL (e.g., https://saverwell.ai/r/glm "
                            "for GreenLeaf Market). These are NOT real websites. They "
                            "are Next.js API routes that log every hit (referrer, IP, "
                            "user agent, timestamp) to a honeypot_hits Supabase table, "
                            "then redirect to the Saverwell homepage."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "If a competitor copies your merchant database and includes "
                            "the website links, any click from their site is logged "
                            "with their domain as the referrer. This is the strongest "
                            "detection method because it produces an automatic alert "
                            "the moment someone uses your data."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Canary Code", "Merchant", "Redirect URL"],
                        "rows": [
                            ["glm", "GreenLeaf Market", "https://saverwell.ai/r/glm"],
                            ["phs", "Patriot Home Supply", "https://saverwell.ai/r/phs"],
                            [
                                "sbp",
                                "SilverBridge Pharmacy",
                                "https://saverwell.ai/r/sbp",
                            ],
                            ["cg", "Cornerstone Grocers", "https://saverwell.ai/r/cg"],
                            ["bph", "BrightPath Hardware", "https://saverwell.ai/r/bph"],
                        ],
                    },
                ],
            },
            {
                "heading": "Method 2: Tracking Beacons",
                "level": 3,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Each honeypot merchant page includes a hidden 1x1 "
                            "transparent tracking pixel loaded from a unique URL "
                            "(e.g., https://saverwell.ai/beacon/greenleaf-market.gif). "
                            "If someone scrapes your page HTML and serves it on their "
                            "site, the beacon fires on every page load, logging their "
                            "domain."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This catches scrapers who copy raw HTML but strip visible "
                            "content. Most scrapers do not clean hidden images or "
                            "CSS-referenced resources."
                        ),
                    },
                ],
            },
            {
                "heading": "Method 3: Automated Web Search Scanner",
                "level": 3,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "An n8n workflow (Saverwell Honeypot Scanner - Weekly) runs "
                            "every Monday at 7:00 AM CST, searching via Serper.dev API "
                            "for the exact fake merchant names. Since these merchants "
                            "do not exist, any search result is proof of scraping. "
                            "Alerts are sent as a direct Slack message."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": "Search queries:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            '"GreenLeaf Market" "15% off Thursdays"',
                            '"Patriot Home Supply" "12% off Mondays"',
                            '"SilverBridge Pharmacy" "20% off Wednesdays"',
                            '"Cornerstone Grocers" "8% off daily"',
                            '"BrightPath Hardware" "10% off Fridays"',
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The workflow sends a direct Slack message with the "
                            "matching URL, domain, and snippet as evidence. Hits "
                            "are also logged to the Supabase honeypot_hits table."
                        ),
                    },
                ],
            },
            {
                "heading": "Method 4: Google Alerts (backup)",
                "level": 3,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Set up a free Google Alert for each fake merchant name. "
                            "Google emails you whenever new content matching these "
                            "names is indexed. This is a zero-maintenance backup that "
                            "catches publicly indexed copies, though it can be slow "
                            "(days to detect)."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Create alert: GreenLeaf Market senior discount",
                            "Create alert: Patriot Home Supply senior discount",
                            "Create alert: SilverBridge Pharmacy senior discount",
                            "Create alert: Cornerstone Grocers senior discount",
                            "Create alert: BrightPath Hardware senior discount",
                        ],
                    },
                ],
            },
            # ── 7c. Honeypot Database Records ────────────────────────
            {
                "heading": "Honeypot Database Records",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The 5 fake merchants are inserted into the Supabase "
                            "merchants table as national retailers (is_national = "
                            "true, is_active = true, no store locations). The honeypot "
                            "marker is embedded in default_discount_details as a "
                            "[HONEYPOT canary:xxx] suffix. affiliate_priority_score "
                            "is set to 0. Merchant IDs: 3804-3808."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Each merchant has a matching discounts_v2 record. The "
                            "website_url field contains the canary redirect URL "
                            "(https://saverwell.ai/r/[code]). Merchants are filtered "
                            "from the frontend via a .not() filter on website_url "
                            "so real users never see them, but database scrapers do."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": "A honeypot_hits table tracks all canary detections:",
                    },
                    {
                        "type": "table",
                        "headers": ["Column", "Type", "Purpose"],
                        "rows": [
                            ["id", "bigint (auto)", "Primary key"],
                            ["created_at", "timestamptz", "When the hit occurred"],
                            [
                                "canary_code",
                                "text",
                                "Which merchant was hit (glm, phs, etc.)",
                            ],
                            ["hit_type", "text", "redirect or beacon"],
                            ["referrer", "text", "The referring domain (competitor site)"],
                            ["ip_address", "text", "IP address of the request"],
                            ["user_agent", "text", "Browser/bot user agent string"],
                            ["merchant_slug", "text", "Full merchant slug"],
                        ],
                    },
                ],
            },
            # ── 8. Monitoring ─────────────────────────────────────────
            {
                "heading": "8. Monitoring & Alerts",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Cloudflare Analytics to watch:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Security > Overview: Monitor challenged/blocked "
                            "requests daily for the first week",
                            'Security > Bots: Check "automated" vs "likely '
                            'automated" traffic ratios',
                            "Security > Events: Look for rate limit triggers - "
                            "if legitimate users are hitting them, adjust "
                            "thresholds up",
                        ],
                    },
                ],
            },
            {
                "heading": "Alert thresholds",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Set Cloudflare notifications for:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Rate limit triggers exceeding 100/day (possible "
                            "scraping attempt)",
                            "Bot score anomalies (sudden spike in automated traffic)",
                            "Origin error rate spike (could indicate scraper "
                            "overwhelming origin)",
                        ],
                    },
                ],
            },
            # ── 9. Terms of Service ───────────────────────────────────
            {
                "heading": "9. Terms of Service - Anti-Scraping Language",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Add the following provisions to Saverwell's Terms of "
                            "Service to create a legal basis for enforcement against "
                            "scrapers. This gives you grounds for a cease-and-desist "
                            "or Computer Fraud and Abuse Act (CFAA) claim if someone "
                            "scrapes your data despite technical protections."
                        ),
                    },
                ],
            },
            {
                "heading": "Prohibited Activities clause",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Add to your Prohibited Activities section (or create "
                            "one if it does not exist):"
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            '"You agree not to: (a) use any automated system, '
                            "including without limitation robots, spiders, scrapers, "
                            "data mining tools, or similar data gathering or "
                            "extraction methods, to access the Service for any "
                            "purpose; (b) collect, harvest, or compile information "
                            "or data from the Service, including but not limited to "
                            "merchant names, discount details, store locations, "
                            "eligibility requirements, or any database content; "
                            "(c) use the Service's data to build or augment a "
                            "competing product, service, or database; (d) circumvent "
                            "or attempt to circumvent any access restrictions, rate "
                            "limits, bot detection, or security measures implemented "
                            'on the Service."'
                        ),
                    },
                ],
            },
            {
                "heading": "Data ownership clause",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Add a clear data ownership statement:",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            '"All content on the Service, including but not limited '
                            "to merchant discount data, store locations, eligibility "
                            "information, database compilations, and the selection "
                            "and arrangement thereof, is the proprietary property of "
                            "Saverwell and is protected by copyright, trade secret, "
                            "and other intellectual property laws. The compilation "
                            "and organization of this data represents significant "
                            "investment and constitutes a protectable database under "
                            'applicable law."'
                        ),
                    },
                ],
            },
            {
                "heading": "Remedies clause",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Establish your right to take action:",
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            '"Any unauthorized use of automated means to access the '
                            "Service or collect data constitutes a violation of these "
                            "Terms and may violate applicable laws including the "
                            "Computer Fraud and Abuse Act (18 U.S.C. 1030). Saverwell "
                            "reserves the right to: (a) immediately terminate access "
                            "for any user or IP address engaging in prohibited "
                            "activities; (b) pursue injunctive relief and monetary "
                            "damages; (c) report violations to appropriate law "
                            "enforcement authorities; (d) cooperate with other "
                            "companies and industry groups to identify and prevent "
                            'scraping activities."'
                        ),
                    },
                ],
            },
            {
                "heading": "Acceptance mechanism",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "For maximum enforceability, ensure your ToS acceptance "
                            "is clear:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Display a footer link on every page: "
                            '"By using this site, you agree to our Terms of Service"',
                            "Link prominently in the site footer to the full ToS",
                            "If you have user accounts, require ToS checkbox at "
                            "signup",
                            "Keep a change log with dates on the ToS page itself",
                        ],
                    },
                ],
            },
            # ── Implementation Checklist ──────────────────────────────
            {
                "heading": "Implementation Checklist",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Implementation status as of March 2, 2026. "
                            "Cloudflare Pro plan active on saverwell.com."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Status", "Step", "Details"],
                        "rows": [
                            [
                                "DONE",
                                "Super Bot Fight Mode",
                                "Pro plan: definitely automated = Block, verified bots = Allow, JS detections ON, static resource protection ON",
                            ],
                            [
                                "DONE",
                                "Block AI Scrapers toggle",
                                "AI Scrapers and Crawlers: Blocked",
                            ],
                            [
                                "DONE",
                                "WAF: Block scraping tools",
                                "16 user agent patterns blocked (Scrapy, puppeteer, Selenium, etc.) - deployed via API",
                            ],
                            [
                                "DONE",
                                "WAF: Block empty user agents",
                                "Deployed via Cloudflare API",
                            ],
                            [
                                "DONE",
                                "Rate limit: Page requests (30/min)",
                                "Managed Challenge, per IP, configured manually in Cloudflare",
                            ],
                            [
                                "DONE",
                                "Rate limit: API requests (60/min)",
                                "Block action, 5 min timeout, deployed via API",
                            ],
                            [
                                "DONE",
                                "Security headers (Managed Transforms)",
                                "Remove X-Powered-By + Add security headers toggles enabled",
                            ],
                            [
                                "DONE",
                                "Page caching rules",
                                "Cache Everything + 1 month Edge TTL for /static/* and /assets/*",
                            ],
                            [
                                "DONE",
                                "Update robots.txt",
                                "AI crawlers + scraper bots blocked, no sitemap URL",
                            ],
                            [
                                "DONE",
                                "Update Terms of Service",
                                "Sections 6-8: IP protection, prohibited uses (scraping), remedies (CFAA). Sections 9-10 reformatted to normal case.",
                            ],
                            [
                                "DONE",
                                "Honeypot merchants in Supabase",
                                "5 merchants (IDs 3804-3808) + discounts_v2 records. Filtered from frontend, visible to DB scrapers.",
                            ],
                            [
                                "DONE",
                                "honeypot_hits Supabase table",
                                "Created with canary_code, hit_type, referrer, ip_address, user_agent, merchant_slug columns",
                            ],
                            [
                                "DONE",
                                "Canary redirect routes (/r/[code])",
                                "5 routes log to honeypot_hits then 302 redirect to homepage",
                            ],
                            [
                                "DONE",
                                "Tracking beacon routes (/beacon/[slug].gif)",
                                "5 routes log to honeypot_hits then return 1x1 transparent GIF",
                            ],
                            [
                                "DONE",
                                "Google Alerts for fake merchants",
                                "5 alerts, as-it-happens, all results",
                            ],
                            [
                                "DONE",
                                "n8n honeypot scanner workflow",
                                "Serper.dev API, weekly Monday 7am CST, Slack DM alerts, Supabase logging. Workflow ID: Z7wCL0VuIbhXl1h5",
                            ],
                            [
                                "NOT DONE",
                                "Rate limit: Directory pages (15/min)",
                                "Pro plan limited to 2 rate limit rules (both slots used). Requires upgrade or replacing existing rule.",
                            ],
                            [
                                "NOT DONE",
                                "Rate limit: Session volume (200/hr)",
                                "Pro plan limited to 2 rate limit rules. Same constraint as above.",
                            ],
                            [
                                "NOT DONE",
                                "Geo restriction (optional)",
                                "Challenge non-US/CA/GB/AU traffic. Can be added as a custom WAF rule if needed.",
                            ],
                            [
                                "ONGOING",
                                "Monitor Cloudflare analytics",
                                "Check Security > Overview daily for first week, adjust thresholds as needed",
                            ],
                        ],
                    },
                ],
            },
        ],
    }


def main() -> None:
    """Create the Google Doc."""
    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    # --- Load credentials -----------------------------------------------
    oauth_path = str(project_root / "data" / "google-token.json")

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

    # --- Build document structure ---------------------------------------
    structure = build_document_structure()
    title = structure["title"]
    include_toc = structure.get("include_toc", False)
    sections = _normalize_sections(structure, skip_toc=include_toc)

    print(f"Building Google Doc: {title}")
    print(f"Sections: {len(sections)}")

    # --- Create doc and populate ----------------------------------------
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    print(f"Document created: {doc_id}")

    requests = []
    cursor = 1

    def _heading_style(level: int) -> str:
        mapping = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3", 4: "HEADING_4"}
        return mapping.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        if heading:
            heading_text = heading + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": heading_text}}
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
                    {"insertText": {"location": {"index": cursor}, "text": para_text}}
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

            elif block_type in ("bullets", "numbered_list"):
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
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)

                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts = []
                    for ri, row_data in enumerate(all_table_rows):
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
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append((cell_idx, cell_text))

                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cell_idx},
                                    "text": cell_text,
                                }
                            }
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                    # Bold header row
                    doc_state2 = docs_service.documents().get(documentId=doc_id).execute()
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get("tableRows"):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si,
                                                    "endIndex": ei,
                                                },
                                                "textStyle": {"bold": True},
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": "\n"}}
                )
                cursor += 1

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    # Insert TOC
    if include_toc:
        _insert_toc(docs_service, doc_id)

    # Share document (restricted access)
    share_file_restricted(drive_service, doc_id)

    # Move to CMO Agent folder
    folder_id = ensure_drive_folder(drive_service)
    if folder_id:
        move_file_to_folder(drive_service, doc_id, folder_id)

    docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"\nGoogle Doc created successfully!")
    print(f"URL: {docs_url}")


def _insert_toc(docs_service, doc_id: str) -> None:
    """Insert a linked table of contents at the beginning of the document."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])

    headings = []
    for elem in body_content:
        if "paragraph" not in elem:
            continue
        para = elem["paragraph"]
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        heading_id = style.get("headingId", "")
        if not named_style.startswith("HEADING_") or not heading_id:
            continue
        level = int(named_style.replace("HEADING_", ""))
        if level > 3:
            continue
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()
        if text:
            headings.append({"text": text, "level": level, "heading_id": heading_id})

    if not headings:
        return

    toc_title = "Table of Contents\n"
    toc_tip = (
        "For page numbers: select this TOC, delete it, then "
        "Insert > Table of contents > With page numbers.\n"
    )
    entry_lines = [h["text"] + "\n" for h in headings]
    separator = "\n"
    toc_text = toc_title + toc_tip + "".join(entry_lines) + separator

    requests = [
        {"insertText": {"location": {"index": 1}, "text": toc_text}},
    ]

    title_start = 1
    title_end = title_start + len(toc_title)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end - 1},
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 16, "unit": "PT"},
                },
                "fields": "bold,fontSize",
            }
        }
    )

    tip_start = title_end
    tip_end = tip_start + len(toc_tip)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 6, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end - 1},
                "textStyle": {
                    "italic": True,
                    "fontSize": {"magnitude": 9, "unit": "PT"},
                    "foregroundColor": {
                        "color": {
                            "rgbColor": {"red": 0.6, "green": 0.6, "blue": 0.6}
                        }
                    },
                },
                "fields": "italic,fontSize,foregroundColor",
            }
        }
    )

    entry_cursor = tip_end
    for h in headings:
        entry_text = h["text"] + "\n"
        entry_start = entry_cursor
        entry_end = entry_cursor + len(entry_text) - 1

        if entry_end > entry_start:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": entry_start,
                            "endIndex": entry_start + len(entry_text),
                        },
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "spaceAbove": {"magnitude": 2, "unit": "PT"},
                            "spaceBelow": {"magnitude": 2, "unit": "PT"},
                            "indentStart": {
                                "magnitude": 18 * (h["level"] - 1),
                                "unit": "PT",
                            },
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow,indentStart",
                    }
                }
            )

            style_fields = "fontSize,link"
            text_style = {
                "fontSize": {"magnitude": 11, "unit": "PT"},
                "link": {"headingId": h["heading_id"]},
            }
            if h["level"] == 1:
                text_style["bold"] = True
                style_fields += ",bold"

            requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": entry_start,
                            "endIndex": entry_end,
                        },
                        "textStyle": text_style,
                        "fields": style_fields,
                    }
                }
            )

        entry_cursor += len(entry_text)

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    print(f"TOC inserted with {len(headings)} entries")


if __name__ == "__main__":
    main()
