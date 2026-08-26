#!/usr/bin/env python3
"""Deploy the Saverwell Honeypot Scanner workflow to n8n.

Creates a weekly workflow that searches Google for the 5 fake honeypot
merchant names. Any match = proof of scraping. Sends Slack alert +
logs to Supabase honeypot_hits table.

Usage:
    python scripts/deploy_honeypot_scanner_workflow.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

N8N_URL = os.environ.get("N8N_BASE_URL", "")
N8N_KEY = os.environ.get("N8N_API_KEY", "")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")

if not all([N8N_URL, N8N_KEY]):
    print("ERROR: N8N_BASE_URL and N8N_API_KEY must be set in .env")
    sys.exit(1)

# ── Code node scripts ─────────────────────────────────────────────────────

GENERATE_QUERIES_JS = r"""
// ============================================================
// Honeypot merchant search queries
// ============================================================
// UPDATE THESE TWO VALUES with your Google Custom Search credentials:
const GOOGLE_API_KEY = 'YOUR_API_KEY';   // Google Cloud Console > APIs > Credentials
const GOOGLE_CSE_ID  = 'YOUR_CSE_ID';   // programmablesearchengine.google.com > Search Engine ID
// ============================================================

const merchants = [
  { code: 'glm', name: 'GreenLeaf Market',      query: '"GreenLeaf Market" "15% off Thursdays"',    slug: 'greenleaf-market' },
  { code: 'phs', name: 'Patriot Home Supply',    query: '"Patriot Home Supply" "12% off Mondays"',   slug: 'patriot-home-supply' },
  { code: 'sbp', name: 'SilverBridge Pharmacy',  query: '"SilverBridge Pharmacy" "20% off Wednesdays"', slug: 'silverbridge-pharmacy' },
  { code: 'cg',  name: 'Cornerstone Grocers',    query: '"Cornerstone Grocers" "8% off daily"',      slug: 'cornerstone-grocers' },
  { code: 'bph', name: 'BrightPath Hardware',    query: '"BrightPath Hardware" "10% off Fridays"',   slug: 'brightpath-hardware' },
];

return merchants.map(m => ({
  json: {
    ...m,
    apiKey: GOOGLE_API_KEY,
    cseId: GOOGLE_CSE_ID,
  }
}));
""".strip()

AGGREGATE_RESULTS_JS = r"""
// Aggregate all 5 search responses, filter out our own domains
const searchResults = $input.all();
const queries = $('Generate Queries').all();

const ownDomains = ['saverwell.ai', 'saverwell.com', 'seniorsaver-protection.lovable.app'];
const matches = [];

for (let i = 0; i < searchResults.length; i++) {
  const response = searchResults[i].json;
  const merchant = queries[i].json;

  // Google CSE returns items array; missing = no results
  const items = response.items || [];

  for (const item of items) {
    const domain = item.displayLink || '';
    if (ownDomains.some(d => domain.includes(d))) continue;

    matches.push({
      merchantName: merchant.name,
      canaryCode: merchant.code,
      merchantSlug: merchant.slug,
      foundUrl: item.link,
      foundDomain: domain,
      foundTitle: item.title || '',
      foundSnippet: (item.snippet || '').substring(0, 200),
    });
  }
}

return [{ json: { matchCount: matches.length, matches } }];
""".strip()

FORMAT_SLACK_JS = r"""
// Format a single Slack alert with all matches
const { matchCount, matches } = $json;

let text = `*Honeypot Scraping Detected*\n\nFound ${matchCount} match(es) across the web:\n\n`;

for (const m of matches) {
  text += `*${m.merchantName}* (canary: ${m.canaryCode}) found on *${m.foundDomain}*\n`;
  text += `  URL: ${m.foundUrl}\n`;
  if (m.foundSnippet) {
    text += `  Snippet: "${m.foundSnippet}"\n`;
  }
  text += `\n`;
}

text += `_Action: Verify each URL manually. If confirmed, screenshot for evidence and consider a cease-and-desist._`;

return [{ json: { text, channel: '#saverwell-opportunities' } }];
""".strip()

EXPAND_SUPABASE_JS = r"""
// Expand matches into individual Supabase honeypot_hits records
const { matches } = $('Aggregate & Filter').item.json;

return matches.map(m => ({
  json: {
    canary_code: m.canaryCode,
    hit_type: 'web_search',
    referrer: m.foundUrl,
    ip_address: null,
    user_agent: 'n8n-honeypot-scanner',
    merchant_slug: m.merchantSlug,
  }
}));
""".strip()

# ── Workflow definition ────────────────────────────────────────────────────

workflow = {
    "name": "Saverwell Honeypot Scanner - Weekly",
    "nodes": [
        # 1. Schedule Trigger - Monday 12:00 UTC (7:00 AM CST)
        {
            "parameters": {
                "rule": {
                    "interval": [
                        {
                            "field": "weeks",
                            "triggerAtDay": [1],
                            "triggerAtHour": 12,
                        }
                    ]
                }
            },
            "name": "Weekly Monday 7am CST",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [220, 300],
        },
        # 2. Code: Generate search queries
        {
            "parameters": {"jsCode": GENERATE_QUERIES_JS},
            "name": "Generate Queries",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [440, 300],
        },
        # 3. HTTP Request: Google Custom Search API
        {
            "parameters": {
                "method": "GET",
                "url": "https://www.googleapis.com/customsearch/v1",
                "sendQuery": True,
                "queryParameters": {
                    "parameters": [
                        {"name": "key", "value": "={{ $json.apiKey }}"},
                        {"name": "cx", "value": "={{ $json.cseId }}"},
                        {"name": "q", "value": "={{ $json.query }}"},
                    ]
                },
                "options": {
                    "response": {"response": {"fullResponse": True}},
                },
            },
            "name": "Google Search",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [660, 300],
            "onError": "continueRegularOutput",
        },
        # 4. Code: Aggregate & filter results
        {
            "parameters": {"jsCode": AGGREGATE_RESULTS_JS},
            "name": "Aggregate & Filter",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [880, 300],
        },
        # 5. IF: Any matches found?
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": ""},
                    "conditions": [
                        {
                            "id": "match-check",
                            "leftValue": "={{ $json.matchCount }}",
                            "rightValue": "0",
                            "operator": {
                                "type": "number",
                                "operation": "gt",
                            },
                        }
                    ],
                    "combinator": "and",
                }
            },
            "name": "Any Matches?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1100, 300],
        },
        # 6. Code: Format Slack message
        {
            "parameters": {"jsCode": FORMAT_SLACK_JS},
            "name": "Format Slack Alert",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1320, 200],
        },
        # 7. HTTP Request: Post to Slack
        {
            "parameters": {
                "method": "POST",
                "url": "https://slack.com/api/chat.postMessage",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {
                            "name": "Authorization",
                            "value": f"Bearer {SLACK_TOKEN}",
                        },
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": '={{ JSON.stringify({ channel: $json.channel, text: $json.text, unfurl_links: false }) }}',
                "options": {},
            },
            "name": "Slack Alert",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1540, 200],
        },
        # 8. Code: Expand matches for Supabase
        {
            "parameters": {"jsCode": EXPAND_SUPABASE_JS},
            "name": "Expand Supabase Hits",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1320, 400],
        },
        # 9. HTTP Request: Log to Supabase honeypot_hits
        {
            "parameters": {
                "method": "POST",
                "url": f"{SUPABASE_URL}/rest/v1/honeypot_hits",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": f"Bearer {SUPABASE_KEY}"},
                        {"name": "apikey", "value": SUPABASE_KEY},
                        {"name": "Content-Type", "value": "application/json"},
                        {"name": "Prefer", "value": "return=minimal"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ canary_code: $json.canary_code, hit_type: $json.hit_type, referrer: $json.referrer, ip_address: $json.ip_address, user_agent: $json.user_agent, merchant_slug: $json.merchant_slug }) }}",
                "options": {},
            },
            "name": "Log to Supabase",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1540, 400],
            "onError": "continueRegularOutput",
        },
        # 10. NoOp: No matches (clean end)
        {
            "parameters": {},
            "name": "No Matches",
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [1320, 500],
        },
    ],
    "connections": {
        "Weekly Monday 7am CST": {
            "main": [[{"node": "Generate Queries", "type": "main", "index": 0}]]
        },
        "Generate Queries": {
            "main": [[{"node": "Google Search", "type": "main", "index": 0}]]
        },
        "Google Search": {
            "main": [[{"node": "Aggregate & Filter", "type": "main", "index": 0}]]
        },
        "Aggregate & Filter": {
            "main": [[{"node": "Any Matches?", "type": "main", "index": 0}]]
        },
        "Any Matches?": {
            "main": [
                # True branch -> Slack + Supabase
                [
                    {"node": "Format Slack Alert", "type": "main", "index": 0},
                    {"node": "Expand Supabase Hits", "type": "main", "index": 0},
                ],
                # False branch -> NoOp
                [{"node": "No Matches", "type": "main", "index": 0}],
            ]
        },
        "Format Slack Alert": {
            "main": [[{"node": "Slack Alert", "type": "main", "index": 0}]]
        },
        "Expand Supabase Hits": {
            "main": [[{"node": "Log to Supabase", "type": "main", "index": 0}]]
        },
    },
    "settings": {"executionOrder": "v1"},
}

# ── Deploy ─────────────────────────────────────────────────────────────────


def main() -> None:
    print(f"Deploying to: {N8N_URL}")

    headers = {"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"}

    resp = httpx.post(
        f"{N8N_URL}/api/v1/workflows",
        headers=headers,
        json=workflow,
        timeout=30,
    )

    if resp.status_code not in (200, 201):
        print(f"ERROR: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    wf_id = data.get("id", "unknown")
    wf_name = data.get("name", "unknown")

    print(f"\nWorkflow created successfully!")
    print(f"  Name: {wf_name}")
    print(f"  ID:   {wf_id}")
    print(f"  URL:  {N8N_URL}/workflow/{wf_id}")
    print()
    print("NEXT STEPS:")
    print("  1. Open the workflow in n8n")
    print('  2. Click the "Generate Queries" Code node')
    print("  3. Replace YOUR_API_KEY with your Google Custom Search API key")
    print("  4. Replace YOUR_CSE_ID with your Programmable Search Engine ID")
    print("  5. Save and activate the workflow")
    print("  6. Run it manually once to test")


if __name__ == "__main__":
    main()
