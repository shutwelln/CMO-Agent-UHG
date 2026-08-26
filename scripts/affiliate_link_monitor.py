"""Monitor affiliate link health for Saverwell.

Checks all active affiliate URLs in Supabase (merchants + guide comparison tables)
for broken links (404, 500, connection errors). Reports results to stdout and
optionally sends a Slack alert for any broken links.

Designed to run weekly via cron or manually.

Requires:
  SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

Optional:
  SLACK_BOT_TOKEN + a channel for alerts

Usage:
  python scripts/affiliate_link_monitor.py [--slack] [--fix-sheet]
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
SLACK_TOKEN = os.environ.get('SLACK_BOT_TOKEN', '')
SLACK_CHANNEL = os.environ.get('SLACK_NOTIFICATION_CHANNEL', '')

SEND_SLACK = '--slack' in sys.argv

SUPABASE_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

# HTTP client with generous timeout and redirect following
check_client = httpx.Client(
    timeout=15,
    follow_redirects=True,
    headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Saverwell Link Monitor',
    },
)
supabase_client = httpx.Client(timeout=30)


def check_url(url):
    """Check if a URL is healthy. Returns (status, message)."""
    if not url or not url.startswith('http'):
        return 'invalid', 'Not a valid URL'

    try:
        resp = check_client.head(url)
        # Some servers don't support HEAD, try GET
        if resp.status_code == 405:
            resp = check_client.get(url)

        if resp.status_code in (200, 301, 302, 307, 308):
            return 'ok', f'{resp.status_code}'
        elif resp.status_code == 403:
            # Many affiliate links return 403 to bots but work for humans
            return 'ok', '403 (likely bot-blocked, probably fine)'
        elif resp.status_code == 404:
            return 'broken', f'404 Not Found'
        elif resp.status_code >= 500:
            return 'broken', f'{resp.status_code} Server Error'
        else:
            return 'warning', f'{resp.status_code}'
    except httpx.ConnectTimeout:
        return 'broken', 'Connection timeout'
    except httpx.ConnectError as e:
        return 'broken', f'Connection error: {e}'
    except Exception as e:
        return 'warning', f'Error: {e}'


# ── Step 1: Fetch all active merchant affiliate URLs ───────────────────────────
print("Fetching active merchant affiliate URLs from Supabase...")

merchant_links = []
offset = 0
while True:
    resp = supabase_client.get(
        f'{SUPABASE_URL}/rest/v1/merchants',
        headers=SUPABASE_HEADERS,
        params={
            'select': 'id,name,affiliate_url,affiliate_network',
            'affiliate_status': 'eq.active',
            'affiliate_url': 'not.is.null',
            'limit': '500',
            'offset': str(offset),
        },
    )
    resp.raise_for_status()
    batch = resp.json()
    if not batch:
        break
    merchant_links.extend(batch)
    offset += 500

print(f"  Found {len(merchant_links)} active merchant affiliate links")


# ── Step 2: Fetch guide affiliate URLs from comparison tables ──────────────────
print("Fetching guide affiliate URLs from comparison tables...")

guide_links = []
resp = supabase_client.get(
    f'{SUPABASE_URL}/rest/v1/guide_articles',
    headers=SUPABASE_HEADERS,
    params={
        'select': 'slug,comparison_table',
        'comparison_table': 'not.is.null',
        'limit': '100',
    },
)
resp.raise_for_status()

for guide in resp.json():
    slug = guide.get('slug', '')
    table = guide.get('comparison_table', [])
    if not table or not isinstance(table, list):
        continue
    for row in table:
        url = row.get('affiliate_url', '')
        if url:
            # Find the provider name from the first non-url key
            provider = ''
            for key in ['provider', 'carrier', 'brand', 'company', 'name']:
                if key in row:
                    provider = row[key]
                    break
            guide_links.append({
                'slug': slug,
                'provider': provider,
                'affiliate_url': url,
            })

print(f"  Found {len(guide_links)} guide affiliate links")


# ── Step 3: Check all links ────────────────────────────────────────────────────
total = len(merchant_links) + len(guide_links)
print(f"\nChecking {total} affiliate links...")

broken = []
warnings = []
healthy = 0

# Check merchant links
for i, m in enumerate(merchant_links):
    name = m.get('name', 'Unknown')
    url = m.get('affiliate_url', '')
    network = m.get('affiliate_network', '')

    print(f"  [{i + 1}/{total}] {name}", end='', flush=True)
    status, msg = check_url(url)

    if status == 'ok':
        healthy += 1
        print(f" -> OK ({msg})")
    elif status == 'broken':
        broken.append({
            'type': 'merchant',
            'name': name,
            'url': url,
            'network': network,
            'error': msg,
        })
        print(f" -> BROKEN: {msg}")
    elif status == 'warning':
        warnings.append({
            'type': 'merchant',
            'name': name,
            'url': url,
            'network': network,
            'error': msg,
        })
        print(f" -> WARNING: {msg}")
    else:
        warnings.append({
            'type': 'merchant',
            'name': name,
            'url': url,
            'error': msg,
        })
        print(f" -> {status}: {msg}")

# Check guide links
for j, g in enumerate(guide_links):
    idx = len(merchant_links) + j + 1
    slug = g['slug']
    provider = g['provider']
    url = g['affiliate_url']

    print(f"  [{idx}/{total}] {slug}/{provider}", end='', flush=True)
    status, msg = check_url(url)

    if status == 'ok':
        healthy += 1
        print(f" -> OK ({msg})")
    elif status == 'broken':
        broken.append({
            'type': 'guide',
            'slug': slug,
            'provider': provider,
            'url': url,
            'error': msg,
        })
        print(f" -> BROKEN: {msg}")
    elif status == 'warning':
        warnings.append({
            'type': 'guide',
            'slug': slug,
            'provider': provider,
            'url': url,
            'error': msg,
        })
        print(f" -> WARNING: {msg}")
    else:
        print(f" -> {status}: {msg}")


# ── Step 4: Report results ─────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  AFFILIATE LINK HEALTH REPORT")
print(f"{'=' * 60}")
print(f"  Total checked: {total}")
print(f"  Healthy:       {healthy}")
print(f"  Broken:        {len(broken)}")
print(f"  Warnings:      {len(warnings)}")
print(f"{'=' * 60}")

if broken:
    print(f"\nBROKEN LINKS (need immediate attention):")
    for item in broken:
        if item['type'] == 'merchant':
            print(f"  Merchant: {item['name']} ({item.get('network', '')})")
        else:
            print(f"  Guide: {item['slug']} / {item['provider']}")
        print(f"    URL: {item['url']}")
        print(f"    Error: {item['error']}")

if warnings:
    print(f"\nWARNINGS (may need attention):")
    for item in warnings:
        if item['type'] == 'merchant':
            print(f"  Merchant: {item['name']}")
        else:
            print(f"  Guide: {item['slug']} / {item['provider']}")
        print(f"    URL: {item['url']}")
        print(f"    Issue: {item['error']}")


# ── Step 5: Send Slack alert if broken links found ─────────────────────────────
if SEND_SLACK and broken and SLACK_TOKEN and SLACK_CHANNEL:
    print(f"\nSending Slack alert...")

    slack_client = httpx.Client(timeout=15)

    lines = [f"*Affiliate Link Health Alert*\n{len(broken)} broken link(s) detected:\n"]
    for item in broken[:10]:  # Limit to 10 in Slack
        if item['type'] == 'merchant':
            lines.append(f"- *{item['name']}* ({item.get('network', '')}): {item['error']}")
        else:
            lines.append(f"- Guide `{item['slug']}` / {item['provider']}: {item['error']}")

    if len(broken) > 10:
        lines.append(f"\n... and {len(broken) - 10} more. Run the monitor script for full report.")

    resp = slack_client.post(
        'https://slack.com/api/chat.postMessage',
        headers={'Authorization': f'Bearer {SLACK_TOKEN}'},
        json={
            'channel': SLACK_CHANNEL,
            'text': '\n'.join(lines),
        },
    )

    if resp.status_code == 200 and resp.json().get('ok'):
        print(f"  Slack alert sent to {SLACK_CHANNEL}")
    else:
        print(f"  Slack alert failed: {resp.text[:200]}")

    slack_client.close()
elif SEND_SLACK and not broken:
    print("\nNo broken links - no Slack alert needed.")
elif SEND_SLACK and (not SLACK_TOKEN or not SLACK_CHANNEL):
    print("\nSlack alert requested but SLACK_BOT_TOKEN or SLACK_NOTIFICATION_CHANNEL not set.")

check_client.close()
supabase_client.close()

print("\nDone!")
if broken:
    sys.exit(1)  # Non-zero exit for CI/cron alerting
