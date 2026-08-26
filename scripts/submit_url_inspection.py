#!/usr/bin/env python3
"""Submit URLs to Google Search Console URL Inspection API for re-crawling.

Reads the live sitemap (or specific sub-sitemaps) and requests indexing
for each URL via the Search Console API.

Prerequisites:
  - Service account at data/saverwell-google-credentials.json
  - Service account email added as verified OWNER in GSC for sc-domain:saverwell.com
  - pip install google-api-python-client google-auth httpx

Usage:
    python scripts/submit_url_inspection.py --type dma           # DMA pages only
    python scripts/submit_url_inspection.py --type merchants     # retailer pages
    python scripts/submit_url_inspection.py --type guides        # guide articles
    python scripts/submit_url_inspection.py --type all           # all from sitemap
    python scripts/submit_url_inspection.py --type dma --limit 20
    python scripts/submit_url_inspection.py --type dma --dry-run
    python scripts/submit_url_inspection.py --type dma --method indexing  # Indexing API (JobPosting only)
"""

from __future__ import annotations

import argparse
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List

import httpx
from google.oauth2.service_account import Credentials

SITE_URL = "sc-domain:saverwell.com"
CREDENTIALS_PATH = Path(__file__).resolve().parents[1] / "data" / "saverwell-google-credentials.json"
SITEMAP_BASE = "https://saverwell.com"

# Rate limit: Google allows ~2000 inspection queries/day
# but recommends spacing requests
INSPECTION_DELAY = 1.5  # seconds between requests
INDEXING_DELAY = 0.5

LOG_FILE = Path(__file__).resolve().parents[1] / "data" / "url_inspection.log"

# Sub-sitemap URL mapping
TYPE_TO_SITEMAP = {
    "dma": f"{SITEMAP_BASE}/sitemap-dma.xml",
    "merchants": f"{SITEMAP_BASE}/sitemap-merchants.xml",
    "guides": f"{SITEMAP_BASE}/sitemap-guides.xml",
    "protect": f"{SITEMAP_BASE}/sitemap-protect.xml",
    "states": f"{SITEMAP_BASE}/sitemap-states.xml",
    "pages": f"{SITEMAP_BASE}/sitemap-pages.xml",
    "all": f"{SITEMAP_BASE}/sitemap.xml",
}


def log(msg: str) -> None:
    print(msg, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def fetch_urls_from_sitemap(sitemap_url: str) -> List[str]:
    """Parse a sitemap XML and return all <loc> URLs."""
    resp = httpx.get(sitemap_url, timeout=30.0, follow_redirects=True)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    urls: List[str] = []

    # Check if it's a sitemap index
    sitemaps = root.findall("sm:sitemap/sm:loc", ns)
    if sitemaps:
        # It's an index — recurse into each sub-sitemap
        for loc_el in sitemaps:
            sub_url = loc_el.text
            if sub_url:
                log(f"  Fetching sub-sitemap: {sub_url}")
                urls.extend(fetch_urls_from_sitemap(sub_url.strip()))
        return urls

    # Regular urlset
    for url_el in root.findall("sm:url/sm:loc", ns):
        if url_el.text:
            urls.append(url_el.text.strip())

    return urls


def get_credentials(scopes: List[str]) -> Credentials:
    if not CREDENTIALS_PATH.exists():
        print(f"ERROR: Credentials not found at {CREDENTIALS_PATH}")
        sys.exit(1)
    return Credentials.from_service_account_file(str(CREDENTIALS_PATH), scopes=scopes)


def inspect_urls(urls: List[str], dry_run: bool = False) -> None:
    """Use URL Inspection API to check and request indexing."""
    creds = get_credentials(["https://www.googleapis.com/auth/webmasters"])

    from googleapiclient.discovery import build
    service = build("searchconsole", "v1", credentials=creds)

    indexed = 0
    not_indexed = 0
    errors = 0

    for i, url in enumerate(urls):
        if dry_run:
            log(f"  [DRY RUN] Would inspect: {url}")
            continue

        try:
            result = service.urlInspection().index().inspect(
                body={
                    "inspectionUrl": url,
                    "siteUrl": SITE_URL,
                }
            ).execute()

            inspection = result.get("inspectionResult", {})
            index_status = inspection.get("indexStatusResult", {})
            verdict = index_status.get("verdict", "UNKNOWN")
            coverage = index_status.get("coverageState", "UNKNOWN")

            if verdict == "PASS":
                indexed += 1
                log(f"  [{i+1}/{len(urls)}] INDEXED: {url}")
            else:
                not_indexed += 1
                log(f"  [{i+1}/{len(urls)}] NOT INDEXED ({coverage}): {url}")

        except Exception as e:
            errors += 1
            err_str = str(e)[:200]
            log(f"  [{i+1}/{len(urls)}] ERROR: {url} - {err_str}")

            # If we hit quota, stop
            if "quota" in err_str.lower() or "rate" in err_str.lower():
                log(f"  Rate limited at URL {i+1}. Stopping.")
                break

        time.sleep(INSPECTION_DELAY)

    log(f"\nInspection complete: {indexed} indexed, {not_indexed} not indexed, {errors} errors")


def submit_indexing_api(urls: List[str], dry_run: bool = False) -> None:
    """Use Google Indexing API to request URL updates.

    Note: Officially for JobPosting/BroadcastEvent structured data only,
    but triggers crawling in practice.
    """
    creds = get_credentials(["https://www.googleapis.com/auth/indexing"])

    from googleapiclient.discovery import build
    service = build("indexing", "v3", credentials=creds)

    submitted = 0
    errors = 0

    for i, url in enumerate(urls):
        if dry_run:
            log(f"  [DRY RUN] Would submit: {url}")
            continue

        try:
            service.urlNotifications().publish(
                body={
                    "url": url,
                    "type": "URL_UPDATED",
                }
            ).execute()
            submitted += 1
            if submitted % 50 == 0:
                log(f"  Submitted {submitted}/{len(urls)}...")

        except Exception as e:
            errors += 1
            err_str = str(e)[:200]
            log(f"  [{i+1}/{len(urls)}] ERROR: {url} - {err_str}")

            if "quota" in err_str.lower() or "rate" in err_str.lower():
                log(f"  Rate limited at URL {i+1}. Stopping.")
                break

        time.sleep(INDEXING_DELAY)

    log(f"\nIndexing API: {submitted} submitted, {errors} errors")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Submit URLs to Google Search Console for re-indexing"
    )
    parser.add_argument(
        "--type",
        required=True,
        choices=list(TYPE_TO_SITEMAP.keys()),
        help="URL type to submit",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max URLs to process")
    parser.add_argument("--dry-run", action="store_true", help="Preview without submitting")
    parser.add_argument(
        "--method",
        choices=["inspection", "indexing"],
        default="inspection",
        help="API method: inspection (default, check+log) or indexing (submit URL_UPDATED)",
    )
    args = parser.parse_args()

    sitemap_url = TYPE_TO_SITEMAP[args.type]
    log(f"Fetching URLs from {sitemap_url}...")

    urls = fetch_urls_from_sitemap(sitemap_url)
    log(f"Found {len(urls)} URLs")

    if args.limit:
        urls = urls[: args.limit]
        log(f"Limited to {len(urls)} URLs")

    if not urls:
        log("No URLs to process")
        return

    if args.method == "indexing":
        submit_indexing_api(urls, dry_run=args.dry_run)
    else:
        inspect_urls(urls, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
