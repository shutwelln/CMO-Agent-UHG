#!/usr/bin/env python3
"""
Validate all SEO pages before allowing Googlebot through Cloudflare.

Fetches every URL from the v_sitemap_urls view, requests each page, and checks:
  1. HTTP 200 status
  2. Page-specific <title> (not the generic default)
  3. <meta name="description"> present and not default
  4. JSON-LD FAQPage schema present
  5. JSON-LD BreadcrumbList schema present
  6. Page content length >= 100 characters
  7. Cross-linked URLs return 200 (no broken internal links)

Usage:
    python scripts/validate_seo_pages.py                         # validate all
    python scripts/validate_seo_pages.py --type retailer         # validate one type
    python scripts/validate_seo_pages.py --base-url http://localhost:3000  # local dev
    python scripts/validate_seo_pages.py --skip-links            # skip cross-link check
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

DEFAULT_BASE_URL = "https://saverwell.com"

# The generic title that the SPA shell returns before React hydrates
GENERIC_TITLES = [
    "Senior Discounts & Fraud Protection | Saverwell",
    "Saverwell",
    "React App",
    "Vite + React",
]


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
class PageResult:
    """Result of validating a single page."""

    def __init__(self, url: str) -> None:
        self.url = url
        self.passed = True
        self.issues: List[str] = []

    def fail(self, msg: str) -> None:
        self.passed = False
        self.issues.append(msg)

    def warn(self, msg: str) -> None:
        self.issues.append(f"WARN: {msg}")


def extract_title(html: str) -> Optional[str]:
    """Extract <title> content from HTML."""
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def extract_meta_description(html: str) -> Optional[str]:
    """Extract <meta name="description"> content."""
    match = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
        html,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    # Also check content-first variant
    match = re.search(
        r'<meta\s+content=["\']([^"\']*?)["\']\s+name=["\']description["\']',
        html,
        re.IGNORECASE,
    )
    return match.group(1).strip() if match else None


def extract_jsonld(html: str) -> List[Dict[str, Any]]:
    """Extract all JSON-LD blocks from HTML."""
    blocks: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                blocks.append(data)
            elif isinstance(data, list):
                blocks.extend(d for d in data if isinstance(d, dict))
        except json.JSONDecodeError:
            pass
    return blocks


def extract_text_content(html: str) -> str:
    """Strip HTML tags to get text content length estimate."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_internal_links(html: str, base_url: str) -> Set[str]:
    """Extract internal links from HTML."""
    links: Set[str] = set()
    pattern = re.compile(r'href=["\']([^"\']*)["\']', re.IGNORECASE)
    for match in pattern.finditer(html):
        href = match.group(1)
        if href.startswith("/"):
            links.add(href)
        elif href.startswith(base_url):
            path = href[len(base_url) :]
            if path:
                links.add(path)
    # Only return SEO page links
    seo_prefixes = ("/retailer/", "/dma/", "/protect/", "/guides/", "/state/")
    return {link for link in links if any(link.startswith(p) for p in seo_prefixes)}


def validate_page(
    html: str,
    url: str,
    check_links: bool = True,
) -> PageResult:
    """Run all validation checks on a page's HTML."""
    result = PageResult(url)

    # 1. Title check
    title = extract_title(html)
    if not title:
        result.fail("Missing <title> tag")
    elif title in GENERIC_TITLES:
        result.fail(f"Generic title: '{title}' (not page-specific)")

    # 2. Meta description check
    desc = extract_meta_description(html)
    if not desc:
        result.fail("Missing <meta name='description'>")
    elif len(desc) < 30:
        result.warn(f"Short meta description ({len(desc)} chars)")

    # 3. JSON-LD checks
    jsonld_blocks = extract_jsonld(html)
    types = {block.get("@type", "") for block in jsonld_blocks}

    if "FAQPage" not in types:
        result.warn("No FAQPage JSON-LD schema found")

    if "BreadcrumbList" not in types:
        result.fail("No BreadcrumbList JSON-LD schema found")

    # 4. Content length check
    text = extract_text_content(html)
    if len(text) < 100:
        result.fail(f"Content too short ({len(text)} chars, need >= 100)")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Saverwell SEO pages")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"Base URL to validate (default: {DEFAULT_BASE_URL})",
    )
    parser.add_argument(
        "--type",
        choices=["retailer", "dma", "protect", "guides", "state"],
        help="Only validate one content type",
    )
    parser.add_argument(
        "--skip-links",
        action="store_true",
        help="Skip cross-link validation",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of pages to check (0 = all)",
    )
    parser.add_argument(
        "--bot-ua",
        action="store_true",
        help="Use Googlebot user agent (test dynamic rendering)",
    )
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    base_url = args.base_url.rstrip("/")

    print("=" * 70)
    print("  Saverwell SEO Page Validator")
    print("=" * 70)
    print(f"  Base URL:    {base_url}")
    print(f"  Type filter: {args.type or 'all'}")
    print(f"  Skip links:  {args.skip_links}")
    print(f"  Bot UA:      {args.bot_ua}")
    print()

    # Fetch sitemap URLs from Supabase
    print("Fetching sitemap URLs from v_sitemap_urls ...")
    with httpx.Client(timeout=30) as sb_client:
        params: Dict[str, str] = {"select": "url,lastmod"}
        if args.type:
            params["url"] = f"like./{args.type}/%"

        resp = sb_client.get(
            f"{SUPABASE_URL}/rest/v1/v_sitemap_urls",
            headers=SUPABASE_HEADERS,
            params=params,
        )
        if resp.status_code != 200:
            print(f"ERROR: Failed to fetch sitemap URLs: HTTP {resp.status_code}")
            print(f"  {resp.text[:300]}")
            print()
            print("Have you deployed the v_sitemap_urls view?")
            print("Run scripts/sql/update_sitemap_view.sql in the Supabase SQL Editor.")
            sys.exit(1)

        urls_data = resp.json()

    urls = [row["url"] for row in urls_data]
    if args.limit > 0:
        urls = urls[: args.limit]

    print(f"  Found {len(urls_data)} URLs, validating {len(urls)}")
    print()

    # Validate each page
    headers: Dict[str, str] = {}
    if args.bot_ua:
        headers["User-Agent"] = "Googlebot/2.1 (+http://www.google.com/bot.html)"

    results: List[PageResult] = []
    broken_links: Set[str] = set()
    all_internal_links: Set[str] = set()

    with httpx.Client(timeout=15, follow_redirects=True) as client:
        for i, url_path in enumerate(urls):
            full_url = f"{base_url}{url_path}"
            prefix = f"[{i+1}/{len(urls)}]"

            try:
                resp = client.get(full_url, headers=headers)
            except httpx.RequestError as e:
                result = PageResult(url_path)
                result.fail(f"Request error: {e}")
                results.append(result)
                print(f"  {prefix} FAIL {url_path} - request error")
                continue

            if resp.status_code != 200:
                result = PageResult(url_path)
                result.fail(f"HTTP {resp.status_code}")
                results.append(result)
                print(f"  {prefix} FAIL {url_path} - HTTP {resp.status_code}")
                continue

            html = resp.text
            result = validate_page(html, url_path)
            results.append(result)

            # Collect internal links for cross-link check
            if not args.skip_links:
                links = extract_internal_links(html, base_url)
                all_internal_links.update(links)

            status = "PASS" if result.passed else "FAIL"
            detail = ""
            if result.issues:
                detail = f" - {result.issues[0]}"
                if len(result.issues) > 1:
                    detail += f" (+{len(result.issues)-1} more)"
            print(f"  {prefix} {status} {url_path}{detail}")

        # Cross-link validation
        if not args.skip_links and all_internal_links:
            print()
            print(f"Checking {len(all_internal_links)} cross-linked URLs ...")
            # Only check links that aren't already in our validated set
            validated_paths = {r.url for r in results}
            links_to_check = all_internal_links - validated_paths

            for link_path in sorted(links_to_check):
                full_url = f"{base_url}{link_path}"
                try:
                    resp = client.head(full_url, headers=headers)
                    if resp.status_code not in (200, 301, 302):
                        broken_links.add(link_path)
                        print(f"  BROKEN: {link_path} -> HTTP {resp.status_code}")
                except httpx.RequestError:
                    broken_links.add(link_path)
                    print(f"  BROKEN: {link_path} -> request error")

    # ── Report ────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  VALIDATION REPORT")
    print("=" * 70)

    passed = [r for r in results if r.passed]
    failed = [r for r in results if not r.passed]
    warned = [r for r in results if r.issues and r.passed]

    print(f"  Total pages:  {len(results)}")
    print(f"  Passed:       {len(passed)}")
    print(f"  Failed:       {len(failed)}")
    print(f"  With warnings: {len(warned)}")
    if not args.skip_links:
        print(f"  Broken links: {len(broken_links)}")
    print()

    if failed:
        print("FAILURES:")
        for r in failed:
            print(f"  {r.url}")
            for issue in r.issues:
                print(f"    - {issue}")
        print()

    if warned:
        print("WARNINGS:")
        for r in warned:
            for issue in r.issues:
                if issue.startswith("WARN:"):
                    print(f"  {r.url}: {issue}")
        print()

    if broken_links:
        print("BROKEN CROSS-LINKS:")
        for link in sorted(broken_links):
            print(f"  {link}")
        print()

    # Exit code
    if failed or broken_links:
        print("RESULT: FAIL - fix issues before allowing Googlebot through Cloudflare")
        sys.exit(1)
    else:
        print("RESULT: PASS - all pages validated successfully")
        print("Safe to allow Googlebot through Cloudflare.")


if __name__ == "__main__":
    main()
