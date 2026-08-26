#!/usr/bin/env python3
"""Deploy the fixed Saverwell Lead Scanner v2 workflow to n8n.

Restructures the workflow to:
- Fix Google Sheets credential (service account)
- Split scanners into Code-prep -> HTTP Request -> Code-parse pattern
- Add cross-run dedup via existing Lead IDs
- Remove all scoring/reply/alert nodes (moved to local Python)
- Format leads for Sheet append

Usage:
    source .venv/bin/activate
    python scripts/deploy_lead_scanner_v2.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root on path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)


WORKFLOW_ID = "e5ROJniIeXq9aw8L"
SPREADSHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"

# Correct credential from MEMORY.md
GOOGLE_CREDENTIAL = {"googleApi": {"id": "4uKXB8apT7JC0MF1", "name": "CMO Agent Service Account"}}

# ---------------------------------------------------------------------------
# Node definitions
# ---------------------------------------------------------------------------


def _google_sheets_node(
    node_id: str,
    name: str,
    position: list,
    operation: str,
    sheet_name: str,
    range_str: str = "",
    extra_params: dict | None = None,
) -> dict:
    """Build a Google Sheets v4.5 node with service account auth."""
    params: dict = {
        "operation": operation,
        "documentId": {
            "__rl": True,
            "value": SPREADSHEET_ID,
            "mode": "id",
        },
        "sheetName": {
            "__rl": True,
            "value": sheet_name,
            "mode": "name",
        },
        "authentication": "serviceAccount",
        "options": {},
    }
    if range_str:
        params["range"] = range_str
    if extra_params:
        params.update(extra_params)
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5,
        "position": position,
        "parameters": params,
        "credentials": GOOGLE_CREDENTIAL,
    }


def _code_node(node_id: str, name: str, position: list, js_code: str) -> dict:
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": position,
        "parameters": {"jsCode": js_code},
    }


def _http_node(
    node_id: str,
    name: str,
    position: list,
    method: str,
    url_expr: str,
    *,
    headers: dict | None = None,
    body_expr: str = "",
    timeout: int = 10000,
    continue_on_fail: bool = True,
    response_format: str = "autodetect",
) -> dict:
    params: dict = {
        "method": method,
        "url": url_expr,
        "options": {
            "timeout": timeout,
        },
    }
    if response_format != "autodetect":
        params["options"]["response"] = {"response": {"responseFormat": response_format}}
    if headers:
        params["sendHeaders"] = True
        header_params = []
        for k, v in headers.items():
            header_params.append({"name": k, "value": v})
        params["headerParameters"] = {"parameters": header_params}
    if body_expr:
        params["sendBody"] = True
        params["contentType"] = "raw"
        params["rawContentType"] = "application/json"
        params["body"] = body_expr
    node = {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": position,
        "parameters": params,
    }
    if continue_on_fail:
        node["continueOnFail"] = True
    return node


# ---------------------------------------------------------------------------
# Code node JavaScript
# ---------------------------------------------------------------------------

BUILD_SEARCH_CONFIG_JS = """const items = $input.all();

// Filter only active search terms
const activeTerms = items.filter(item =>
  item.json.Active === 'Yes' || item.json.Active === 'YES' || item.json.Active === true
);

const includeTerms = [];
const excludeTerms = [];
const intentSignals = [];

for (const item of activeTerms) {
  // Sheet header is "Type" but also check "Category" for backward compat
  const category = item.json.Type || item.json.Category || '';
  const term = item.json.Term || item.json.SearchTerm || '';
  const pillar = item.json.Pillar || '';

  if (!term) continue;

  if (category.toLowerCase() === 'include') {
    includeTerms.push({ term: term.toLowerCase(), pillar });
  } else if (category.toLowerCase() === 'exclude') {
    excludeTerms.push(term.toLowerCase());
  } else if (category.toLowerCase() === 'intent') {
    intentSignals.push(term.toLowerCase());
  }
}

// Caregiving exclude list: same as default but without facility/care terms
const caregivingRemove = new Set([
  'senior living facility', 'assisted living', 'nursing home', 'memory care',
  'dementia care', 'long term care facility', 'home health aide',
  'caregiver needed', 'hiring caregiver'
]);
const caregivingExcludeTerms = excludeTerms.filter(t => !caregivingRemove.has(t));

// 49 subreddits with tab routing, limit, and scanAll flag
const subreddits = [
  // Lead Queue (15 core - proven, actively worked)
  {name: "frugal", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "personalfinance", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "retirement", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "medicare", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "socialsecurity", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "Scams", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "eldercare", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "SeniorCitizens", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "aging", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "FinancialPlanning", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "insurance", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "healthcare", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "GenX", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "Boomer", limit: 50, tab: "Lead Queue", scanAll: false},
  {name: "CreditCards", limit: 50, tab: "Lead Queue", scanAll: false},
  // New Opportunities (24 - evaluate new senior-focused subs)
  {name: "AskOldPeople", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "RedditForGrownups", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "povertyfinance", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "HearingAids", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "tax", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "HealthInsurance", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "leanfire", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "financialindependence", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "VeteransBenefits", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "EatCheapAndHealthy", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "OverFifty", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "homeowners", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "legaladvice", limit: 25, tab: "New Opportunities", scanAll: false},
  // Tier 1 health/benefits subs (condition self-selects for 55+)
  {name: "SleepApnea", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "CPAP", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "widowers", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "tinnitus", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "AFIB", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "ProstateCancer", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "diabetes_t2", limit: 25, tab: "New Opportunities", scanAll: false},
  {name: "SSDI", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "hardofhearing", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "dentures", limit: 25, tab: "New Opportunities", scanAll: true},
  {name: "COPD", limit: 25, tab: "New Opportunities", scanAll: true},
  // Caregiving Queue (10 - lower priority, as bandwidth allows)
  {name: "AgingParents", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "CaregiverSupport", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "caregivers", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "elderlycare", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "hospice", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "Parkinsons", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "dementia", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "Alzheimers", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "Medicaid", limit: 25, tab: "Caregiving Queue", scanAll: true},
  {name: "estateplanning", limit: 25, tab: "Caregiving Queue", scanAll: true},
];

return [{
  json: { includeTerms, excludeTerms, caregivingExcludeTerms, intentSignals, subreddits }
}];
"""

BUILD_REDDIT_URLS_JS = """const config = $input.first().json;
const { subreddits } = config;

return subreddits.map(sub => ({
  json: {
    url: `https://www.reddit.com/r/${sub.name}/new.json?limit=${sub.limit}`,
    subreddit: sub.name,
    tab: sub.tab,
    scanAll: sub.scanAll,
    includeTerms: config.includeTerms,
    excludeTerms: sub.tab === 'Caregiving Queue' ? config.caregivingExcludeTerms : config.excludeTerms,
  }
}));
"""

PARSE_REDDIT_RESULTS_JS = """const items = $input.all();
const matchedPosts = [];
const sevenDaysAgo = Date.now() - (7 * 24 * 60 * 60 * 1000);

function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).substring(0, 12);
}

for (const item of items) {
  try {
    const resp = item.json;
    // Handle HTTP error responses gracefully
    if (!resp || !resp.data || !resp.data.children) continue;

    const includeTerms = item.json.includeTerms || [];
    const excludeTerms = item.json.excludeTerms || [];
    const tab = item.json.tab || 'Lead Queue';
    const scanAll = item.json.scanAll || false;
    const posts = resp.data.children || [];

    for (const post of posts) {
      const data = post.data;
      if (!data) continue;
      const title = data.title || '';
      const selftext = data.selftext || '';
      const combinedText = (title + ' ' + selftext).toLowerCase();
      const createdUtc = (data.created_utc || 0) * 1000;

      if (createdUtc < sevenDaysAgo) continue;

      const hasExclude = excludeTerms.some(term => combinedText.includes(term));
      if (hasExclude) continue;

      // Age gate: skip posts from obviously young users (under ~30)
      const youngPatterns = [
        /\\bi[\\s']?m\\s+(1[4-9]|2[0-9])\\b/,       // "I'm 18", "im 22"
        /\\b(1[4-9]|2[0-5])\\s*[mf]\\b/i,             // "18F", "22M", "18 F"
        /\\bi\\s*\\((1[4-9]|2[0-9])[mf]?\\)/i,         // "I (18F)", "I (22)"
        /\\bjust turned (1[4-9]|2[0-1])\\b/,           // "just turned 18"
        /\\b(teenager|high school|college student|college kid|in college)\\b/i,
        /\\b(dorm room|undergraduate|freshman|sophomore)\\b/i,
      ];
      if (youngPatterns.some(rx => rx.test(combinedText))) continue;

      // scanAll: skip include-term matching for small, highly-targeted subs
      let matchedTermObjs = [];
      let pillar = 'Unknown';
      if (scanAll) {
        pillar = 'General';
      } else {
        matchedTermObjs = includeTerms.filter(termObj =>
          combinedText.includes(termObj.term)
        );
        if (matchedTermObjs.length === 0) continue;
        pillar = matchedTermObjs[0].pillar || 'Unknown';
      }

      const hoursAgo = Math.floor((Date.now() - createdUtc) / (1000 * 60 * 60));
      const hashInput = title.toLowerCase() + '|||' + ('https://www.reddit.com' + data.permalink).toLowerCase();

      matchedPosts.push({
        platform: 'reddit',
        subreddit: data.subreddit,
        title: title,
        content: selftext,
        url: 'https://www.reddit.com' + data.permalink,
        author: data.author,
        post_score: data.score,
        num_comments: data.num_comments,
        hours_ago: hoursAgo,
        created_utc: createdUtc,
        matched_terms: matchedTermObjs.length > 0 ? matchedTermObjs.map(t => t.term) : ['scan_all'],
        pillar: pillar,
        lead_id: simpleHash(hashInput),
        targetTab: tab,
        sourceSubreddit: 'r/' + data.subreddit,
      });
    }
  } catch (e) {
    // Skip failed subreddit responses
    continue;
  }
}

if (matchedPosts.length === 0) {
  return [{ json: { _empty: true } }];
}
return matchedPosts.map(post => ({ json: post }));
"""

BUILD_FORUM_URLS_JS = """const config = $input.first().json;

const forums = [
  {
    name: 'AgingCare',
    url: 'https://www.agingcare.com/caregiver-forum',
    titleRegex: '<h3[^>]*>\\\\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\\\\/a>',
  },
  {
    name: 'SeniorForums',
    url: 'https://www.seniorforums.com/forums/',
    titleRegex: '<h3[^>]*class="[^"]*threadtitle[^"]*"[^>]*>\\\\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\\\\/a>',
  },
  {
    name: 'AARP Community',
    url: 'https://community.aarp.org/t5/forums/recentpostspage',
    titleRegex: '<a[^>]*class="[^"]*message-subject[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]+)<\\\\/a>',
  },
  {
    name: 'Bogleheads',
    url: 'https://www.bogleheads.org/forum/viewforum.php?f=2',
    titleRegex: '<a[^>]*class="topictitle"[^>]*href="([^"]+)"[^>]*>([^<]+)<\\\\/a>',
  },
  {
    name: 'BudgetSeniors',
    url: 'https://www.budgetseniors.com/blog/',
    titleRegex: '<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>\\\\s*<a[^>]*href="([^"]+)"[^>]*>([^<]+)<\\\\/a>',
  }
];

return forums.map(forum => ({
  json: {
    url: forum.url,
    forumName: forum.name,
    titleRegex: forum.titleRegex,
    includeTerms: config.includeTerms,
    excludeTerms: config.excludeTerms,
  }
}));
"""

PARSE_FORUM_POSTS_JS = """const items = $input.all();
const matchedPosts = [];

function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).substring(0, 12);
}

for (const item of items) {
  try {
    const html = typeof item.json === 'string' ? item.json : (item.json.data || '');
    if (!html || typeof html !== 'string') continue;

    const forumName = item.json.forumName || 'Unknown Forum';
    const forumUrl = item.json.url || '';
    const regexStr = item.json.titleRegex || '';
    const includeTerms = item.json.includeTerms || [];
    const excludeTerms = item.json.excludeTerms || [];

    if (!regexStr) continue;

    const regex = new RegExp(regexStr, 'gi');
    let match;
    while ((match = regex.exec(html)) !== null) {
      const url = match[1] || '';
      const title = (match[2] || '').replace(/&#\\d+;/g, '').replace(/&[a-z]+;/gi, '').trim();
      const titleLower = title.toLowerCase();

      const hasExclude = excludeTerms.some(term => titleLower.includes(term));
      if (hasExclude) continue;

      const matchedTermObjs = includeTerms.filter(termObj =>
        titleLower.includes(termObj.term)
      );

      if (matchedTermObjs.length > 0) {
        let fullUrl = url;
        if (url.startsWith('/')) {
          try { fullUrl = new URL(url, forumUrl).href; } catch (e) { fullUrl = url; }
        } else if (!url.startsWith('http')) {
          fullUrl = forumUrl + url;
        }

        const pillar = matchedTermObjs[0].pillar || 'Unknown';
        const hashInput = title.toLowerCase() + '|||' + fullUrl.toLowerCase();

        matchedPosts.push({
          platform: forumName,
          title: title,
          content: '',
          url: fullUrl,
          author: '',
          hours_ago: 0,
          matched_terms: matchedTermObjs.map(t => t.term),
          pillar: pillar,
          lead_id: simpleHash(hashInput),
        });
      }
    }
  } catch (e) {
    continue;
  }
}

if (matchedPosts.length === 0) {
  return [{ json: { _empty: true } }];
}
return matchedPosts.map(post => ({ json: post }));
"""

BUILD_GEMINI_REQUESTS_JS = """const searchPrompts = [
  {
    query: 'Find recent Reddit posts and forum discussions from the last 7 days where seniors are asking about senior discounts at stores. Return up to 10 results as JSON array with fields: title, url, snippet, platform, estimated_hours_ago',
    pillar: 'Savings'
  },
  {
    query: 'Find recent Reddit posts and forum discussions from the last 7 days where people are reporting scams targeting seniors or elderly. Return up to 10 results as JSON array with fields: title, url, snippet, platform, estimated_hours_ago',
    pillar: 'Protection'
  },
  {
    query: 'Find recent Reddit posts and online forum discussions from the last 7 days where seniors are asking about saving money on Medicare, prescription costs, or dealing with Medicare bills. Return up to 10 results as JSON array with fields: title, url, snippet, platform, estimated_hours_ago',
    pillar: 'Guides'
  },
  {
    query: 'Find recent online discussions from the last 7 days where seniors or retirees discuss living on a fixed income, stretching retirement dollars, or finding discounts. Return up to 10 results as JSON array with fields: title, url, snippet, platform, estimated_hours_ago',
    pillar: 'Savings'
  },
  {
    query: 'Find recent Reddit posts and forum discussions from the last 7 days about identity theft, credit freezes, or fraud protection for seniors or retirees. Return up to 10 results as JSON array with fields: title, url, snippet, platform, estimated_hours_ago',
    pillar: 'Protection'
  }
];

return searchPrompts.map(prompt => ({
  json: {
    requestBody: {
      contents: [{ parts: [{ text: prompt.query }] }],
      generationConfig: { temperature: 0.3, maxOutputTokens: 2000 }
    },
    pillar: prompt.pillar
  }
}));
"""

PARSE_GEMINI_RESULTS_JS = """const items = $input.all();
const matchedPosts = [];

function simpleHash(str) {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16).substring(0, 12);
}

for (const item of items) {
  try {
    const resp = item.json;
    const pillar = resp.pillar || 'Unknown';
    const text = resp.candidates?.[0]?.content?.parts?.[0]?.text || '';

    const jsonMatch = text.match(/\\[\\s*\\{[\\s\\S]*\\}\\s*\\]/);
    if (!jsonMatch) continue;

    let results;
    try { results = JSON.parse(jsonMatch[0]); } catch (e) { continue; }

    for (const result of results) {
      const title = result.title || '';
      const url = result.url || '';
      if (!title && !url) continue;

      const hashInput = title.toLowerCase() + '|||' + url.toLowerCase();
      matchedPosts.push({
        platform: 'gemini_search',
        title: title,
        content: (result.snippet || '').substring(0, 500),
        url: url,
        author: '',
        hours_ago: result.estimated_hours_ago || 0,
        matched_terms: ['gemini_search'],
        pillar: pillar,
        lead_id: simpleHash(hashInput),
      });
    }
  } catch (e) {
    continue;
  }
}

if (matchedPosts.length === 0) {
  return [{ json: { _empty: true } }];
}
return matchedPosts.map(post => ({ json: post }));
"""

DEDUP_WITH_EXISTING_JS = """const items = $input.all();

// Gather existing lead IDs from all read-IDs nodes
let existingIds = new Set();
const idNodeNames = [
  'Read Existing Lead IDs',
  'Read New Opps IDs',
  'Read Caregiving IDs',
];
for (const nodeName of idNodeNames) {
  try {
    const existingItems = $(nodeName).all();
    for (const item of existingItems) {
      const id = item.json['Lead ID'] || '';
      if (id) existingIds.add(id);
    }
  } catch (e) {
    // Node not found or empty, continue
  }
}

const seen = new Set();
const deduped = [];

for (const item of items) {
  // Skip empty sentinel items
  if (item.json._empty) continue;

  const leadId = item.json.lead_id || '';
  if (!leadId) continue;

  // Skip if already in Sheet (cross-run dedup)
  if (existingIds.has(leadId)) continue;

  // Skip if duplicate within this run
  if (seen.has(leadId)) continue;

  seen.add(leadId);
  deduped.push({ json: item.json });
}

if (deduped.length === 0) {
  return [];
}
return deduped;
"""

FORMAT_FOR_SHEET_JS = """const items = $input.all();
const formatted = [];

for (const item of items) {
  const lead = item.json;

  // Format post date from created_utc or use current date
  let postDate;
  if (lead.created_utc) {
    const d = new Date(lead.created_utc);
    postDate = d.toLocaleString('en-US', {
      timeZone: 'America/Chicago',
      month: 'numeric', day: 'numeric', year: 'numeric',
      hour: 'numeric', minute: '2-digit', hour12: true
    });
  } else {
    postDate = '';
  }

  const dateFound = new Date().toLocaleString('en-US', {
    timeZone: 'America/Chicago',
    month: 'numeric', day: 'numeric', year: 'numeric',
    hour: 'numeric', minute: '2-digit', hour12: true
  });

  const contentPreview = lead.content ? lead.content.substring(0, 200) : '';
  const postSummary = lead.title + (contentPreview ? ' - ' + contentPreview : '');

  const entry = {
    'Date Found': dateFound,
    'Post Date': postDate,
    'Lead ID': lead.lead_id || '',
    'Platform': lead.platform || '',
    'Pillar': lead.pillar || '',
    'Post Title/Summary': postSummary,
    'Full Content': lead.content || '',
    'Post URL': lead.url || '',
    'Score': '',
    'Post Type': '',
    'Monetization Signal': '',
    'Draft Reply': '',
    'Reviewer Notes': '',
    'Status': 'New',
    // Tab routing + source (not written to Lead Queue sheet, used by Switch node)
    targetTab: lead.targetTab || 'Lead Queue',
    'Source Subreddit': lead.sourceSubreddit || '',
    // Keep original data for Slack alert
    _original: lead,
  };

  formatted.push({ json: entry });
}

if (formatted.length === 0) {
  return [];
}
return formatted;
"""


def build_workflow() -> dict:
    """Build the complete v2 workflow definition."""

    nodes = [
        # --- Trigger ---
        {
            "id": "w2-trigger",
            "name": "Every 4 Hours",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [0, 0],
            "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 4}]}},
        },
        # --- Read Search Terms ---
        _google_sheets_node(
            "w2-read-terms",
            "Read Search Terms",
            [250, 0],
            "read",
            "Search Terms",
        ),
        # --- Build Search Config ---
        _code_node("w2-build-config", "Build Search Config", [500, 0], BUILD_SEARCH_CONFIG_JS),
        # --- Reddit branch: 3 nodes ---
        _code_node("w2-reddit-urls", "Build Reddit URLs", [750, -300], BUILD_REDDIT_URLS_JS),
        _http_node(
            "w2-reddit-fetch",
            "Fetch Reddit Posts",
            [1000, -300],
            "GET",
            "={{ $json.url }}",
            headers={"User-Agent": "Mozilla/5.0 (compatible; SaverwellBot/1.0)"},
            timeout=10000,
        ),
        _code_node(
            "w2-reddit-parse", "Parse Reddit Results", [1250, -300], PARSE_REDDIT_RESULTS_JS
        ),
        # --- Forum branch: 3 nodes ---
        _code_node("w2-forum-urls", "Build Forum URLs", [750, 0], BUILD_FORUM_URLS_JS),
        _http_node(
            "w2-forum-fetch",
            "Fetch Forum HTML",
            [1000, 0],
            "GET",
            "={{ $json.url }}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15000,
            response_format="text",
        ),
        _code_node("w2-forum-parse", "Parse Forum Posts", [1250, 0], PARSE_FORUM_POSTS_JS),
        # --- Gemini branch: 3 nodes ---
        _code_node(
            "w2-gemini-build", "Build Gemini Requests", [750, 300], BUILD_GEMINI_REQUESTS_JS
        ),
        _http_node(
            "w2-gemini-fetch",
            "Call Gemini API",
            [1000, 300],
            "POST",
            "=https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={{ $env.GEMINI_API_KEY }}",
            body_expr="={{ JSON.stringify($json.requestBody) }}",
            timeout=30000,
        ),
        _code_node("w2-gemini-parse", "Parse Gemini Results", [1250, 300], PARSE_GEMINI_RESULTS_JS),
        # --- Merge ---
        {
            "id": "w2-merge",
            "name": "Merge All Results",
            "type": "n8n-nodes-base.merge",
            "typeVersion": 3,
            "position": [1500, 0],
            "parameters": {
                "mode": "append",
                "numberInputs": 3,
            },
        },
        # --- Read Existing Lead IDs from all tabs (for cross-run dedup) ---
        _google_sheets_node(
            "w2-read-ids",
            "Read Existing Lead IDs",
            [1500, 200],
            "read",
            "Lead Queue",
            extra_params={"options": {"range": "C:C"}},
        ),
        _google_sheets_node(
            "w2-read-ids-no",
            "Read New Opps IDs",
            [1500, 350],
            "read",
            "New Opportunities",
            extra_params={"options": {"range": "C:C"}},
        ),
        _google_sheets_node(
            "w2-read-ids-cg",
            "Read Caregiving IDs",
            [1500, 500],
            "read",
            "Caregiving Queue",
            extra_params={"options": {"range": "C:C"}},
        ),
        # --- Deduplicate + cross-run filter ---
        _code_node("w2-dedup", "Deduplicate", [1750, 0], DEDUP_WITH_EXISTING_JS),
        # --- Format for Sheet ---
        _code_node("w2-format", "Format for Sheet", [2000, 0], FORMAT_FOR_SHEET_JS),
        # --- Switch on targetTab ---
        {
            "id": "w2-switch-tab",
            "name": "Route by Tab",
            "type": "n8n-nodes-base.switch",
            "typeVersion": 3.2,
            "position": [2250, 0],
            "parameters": {
                "rules": {
                    "values": [
                        {
                            "outputKey": "Lead Queue",
                            "conditions": {
                                "options": {"version": 2, "combinator": "and"},
                                "conditions": [
                                    {
                                        "leftValue": "={{ $json.targetTab }}",
                                        "rightValue": "Lead Queue",
                                        "operator": {
                                            "type": "string",
                                            "operation": "equals",
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "outputKey": "New Opportunities",
                            "conditions": {
                                "options": {"version": 2, "combinator": "and"},
                                "conditions": [
                                    {
                                        "leftValue": "={{ $json.targetTab }}",
                                        "rightValue": "New Opportunities",
                                        "operator": {
                                            "type": "string",
                                            "operation": "equals",
                                        },
                                    }
                                ],
                            },
                        },
                        {
                            "outputKey": "Caregiving Queue",
                            "conditions": {
                                "options": {"version": 2, "combinator": "and"},
                                "conditions": [
                                    {
                                        "leftValue": "={{ $json.targetTab }}",
                                        "rightValue": "Caregiving Queue",
                                        "operator": {
                                            "type": "string",
                                            "operation": "equals",
                                        },
                                    }
                                ],
                            },
                        },
                    ],
                },
                "options": {"fallbackOutput": "extra"},
            },
        },
        # --- Append to Lead Queue ---
        _google_sheets_node(
            "w2-append-lq",
            "Append to Lead Queue",
            [2500, -200],
            "append",
            "Lead Queue",
            extra_params={
                "columns": {"mappingMode": "autoMapInputData"},
            },
        ),
        # --- Append to New Opportunities ---
        _google_sheets_node(
            "w2-append-no",
            "Append to New Opportunities",
            [2500, 0],
            "append",
            "New Opportunities",
            extra_params={
                "columns": {"mappingMode": "autoMapInputData"},
            },
        ),
        # --- Append to Caregiving Queue ---
        _google_sheets_node(
            "w2-append-cg",
            "Append to Caregiving Queue",
            [2500, 200],
            "append",
            "Caregiving Queue",
            extra_params={
                "columns": {"mappingMode": "autoMapInputData"},
            },
        ),
    ]

    connections = {
        "Every 4 Hours": {"main": [[{"node": "Read Search Terms", "type": "main", "index": 0}]]},
        "Read Search Terms": {
            "main": [[{"node": "Build Search Config", "type": "main", "index": 0}]]
        },
        "Build Search Config": {
            "main": [
                [
                    {"node": "Build Reddit URLs", "type": "main", "index": 0},
                    {"node": "Build Forum URLs", "type": "main", "index": 0},
                    {"node": "Build Gemini Requests", "type": "main", "index": 0},
                ]
            ]
        },
        "Build Reddit URLs": {
            "main": [[{"node": "Fetch Reddit Posts", "type": "main", "index": 0}]]
        },
        "Fetch Reddit Posts": {
            "main": [[{"node": "Parse Reddit Results", "type": "main", "index": 0}]]
        },
        "Parse Reddit Results": {
            "main": [[{"node": "Merge All Results", "type": "main", "index": 0}]]
        },
        "Build Forum URLs": {"main": [[{"node": "Fetch Forum HTML", "type": "main", "index": 0}]]},
        "Fetch Forum HTML": {"main": [[{"node": "Parse Forum Posts", "type": "main", "index": 0}]]},
        "Parse Forum Posts": {
            "main": [[{"node": "Merge All Results", "type": "main", "index": 1}]]
        },
        "Build Gemini Requests": {
            "main": [[{"node": "Call Gemini API", "type": "main", "index": 0}]]
        },
        "Call Gemini API": {
            "main": [[{"node": "Parse Gemini Results", "type": "main", "index": 0}]]
        },
        "Parse Gemini Results": {
            "main": [[{"node": "Merge All Results", "type": "main", "index": 2}]]
        },
        "Merge All Results": {"main": [[{"node": "Deduplicate", "type": "main", "index": 0}]]},
        "Read Existing Lead IDs": {"main": [[{"node": "Deduplicate", "type": "main", "index": 0}]]},
        "Deduplicate": {"main": [[{"node": "Format for Sheet", "type": "main", "index": 0}]]},
        "Format for Sheet": {"main": [[{"node": "Route by Tab", "type": "main", "index": 0}]]},
        "Route by Tab": {
            "main": [
                [{"node": "Append to Lead Queue", "type": "main", "index": 0}],
                [{"node": "Append to New Opportunities", "type": "main", "index": 0}],
                [{"node": "Append to Caregiving Queue", "type": "main", "index": 0}],
                [{"node": "Append to Lead Queue", "type": "main", "index": 0}],
            ]
        },
    }

    return {
        "nodes": nodes,
        "connections": connections,
        "settings": {
            "executionOrder": "v1",
        },
    }


def deploy() -> None:
    import os
    import urllib.request

    from dotenv import load_dotenv

    load_dotenv()

    base_url = os.environ.get("N8N_BASE_URL", "http://localhost:5678")
    api_key = os.environ.get("N8N_API_KEY", "")

    if not api_key:
        print("ERROR: N8N_API_KEY not set")
        sys.exit(1)

    workflow = build_workflow()

    # Wire trigger to feed all three Read ID nodes in parallel (for cross-run dedup).
    # The Dedup node references them via $() expressions, not direct connections.
    for node_name in ["Read Existing Lead IDs", "Read New Opps IDs", "Read Caregiving IDs"]:
        workflow["connections"]["Every 4 Hours"]["main"][0].append(
            {"node": node_name, "type": "main", "index": 0}
        )
        # Remove any direct connections from Read nodes to Dedup
        workflow["connections"].pop(node_name, None)

    workflow["name"] = "Saverwell Lead Scanner"
    payload = json.dumps(workflow).encode()

    url = f"{base_url}/api/v1/workflows/{WORKFLOW_ID}"
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "X-N8N-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="PUT",
    )

    print(f"Deploying workflow to {url}...")
    print(f"  Nodes: {len(workflow['nodes'])}")
    print(f"  Connections: {len(workflow['connections'])}")

    try:
        resp = urllib.request.urlopen(req)
        result = json.load(resp)
        print(f"\nDeployed successfully!")
        print(f"  Workflow ID: {result.get('id', WORKFLOW_ID)}")
        print(f"  Name: {result.get('name', 'unknown')}")
        print(f"  Active: {result.get('active', False)}")
        print(f"  Nodes: {len(result.get('nodes', []))}")
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"\nDeploy FAILED: {e.code}")
        print(body[:2000])
        sys.exit(1)

    # Activate the workflow
    activate_payload = json.dumps({"active": True}).encode()
    activate_req = urllib.request.Request(
        url,
        data=activate_payload,
        headers={
            "X-N8N-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        urllib.request.urlopen(activate_req)
        print("  Activated: True")
    except Exception as e:
        print(f"  Warning: Could not activate workflow: {e}")

    print("\nDone. Trigger a manual execution to test.")


if __name__ == "__main__":
    deploy()
