#!/usr/bin/env python3
"""Batch-add UTM parameters to all CTA URLs in Saverwell email templates.

Scans all .html files in data/saverwell/email_templates/ and appends UTM
parameters to saverwell.com CTA links that don't already have them.

UTM format:
  utm_source=saverwell&utm_medium=email&utm_campaign={campaign}&utm_content={slug}

Campaign and slug are derived from the filename:
  - welcome_1_discounts.html        -> campaign=welcome, content=discounts
  - drip_protection_01_safe-...html -> campaign=drip_protection, content=safe-...
  - drip_guide_03_cell-phone...html -> campaign=drip_guide, content=cell-phone...
  - medicare_guide_01_medicare..html -> campaign=medicare_guide, content=medicare...
  - reengagement_1_value_...html    -> campaign=reengagement, content=value_...
  - core_foundations_01_...html     -> campaign=core_foundations, content=...
  - charlie_migration_01_...html    -> campaign=charlie_migration, content=...

Layouts and snippets are skipped (they don't contain direct CTA links).

Usage:
  python scripts/add_utm_to_templates.py           # dry run (default)
  python scripts/add_utm_to_templates.py --apply    # write changes
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "data" / "saverwell" / "email_templates"

# Files to skip (layouts/snippets don't have CTA links to articles)
SKIP_PREFIXES = ("layout_", "snippet_")

# Only add UTMs to saverwell.com links
SAVERWELL_DOMAIN = "saverwell.com"

# Regex to find href="..." URLs in anchor tags
HREF_RE = re.compile(r'(href=")(https?://[^"]+)(")', re.IGNORECASE)


def derive_campaign_and_content(filename: str) -> tuple[str, str]:
    """Derive utm_campaign and utm_content from the template filename."""
    stem = Path(filename).stem  # e.g. "drip_protection_01_safe-online-shopping-tips"

    # Split on the first numeric segment to separate campaign from content
    # Pattern: {campaign}_{number}_{content-slug}
    match = re.match(r"^(.+?)_(\d+)_(.+)$", stem)
    if match:
        campaign = match.group(1)
        content = match.group(3)
    else:
        # Fallback: use the whole stem
        campaign = "saverwell"
        content = stem

    return campaign, content


def add_utm_to_url(url: str, campaign: str, content: str) -> str:
    """Add UTM parameters to a URL if not already present."""
    parsed = urlparse(url)

    # Only modify saverwell.com URLs
    if SAVERWELL_DOMAIN not in parsed.netloc:
        return url

    # Check if UTMs already exist
    existing_params = parse_qs(parsed.query)
    if "utm_source" in existing_params:
        return url

    utm_params = {
        "utm_source": "saverwell",
        "utm_medium": "email",
        "utm_campaign": campaign,
        "utm_content": content,
    }

    # Append to existing query string
    separator = "&" if parsed.query else ""
    new_query = parsed.query + separator + urlencode(utm_params)
    new_url = urlunparse(parsed._replace(query=new_query))
    return new_url


def process_file(filepath: Path, dry_run: bool = True) -> int:
    """Process a single template file. Returns number of URLs modified."""
    content = filepath.read_text(encoding="utf-8")
    campaign, slug = derive_campaign_and_content(filepath.name)

    modified_count = 0

    def replace_href(match: re.Match) -> str:
        nonlocal modified_count
        prefix = match.group(1)
        url = match.group(2)
        suffix = match.group(3)

        new_url = add_utm_to_url(url, campaign, slug)
        if new_url != url:
            modified_count += 1
        return prefix + new_url + suffix

    new_content = HREF_RE.sub(replace_href, content)

    if modified_count > 0:
        action = "Would update" if dry_run else "Updated"
        print(
            f"  {action} {modified_count} URL(s) in {filepath.name} "
            f"[campaign={campaign}, content={slug}]"
        )
        if not dry_run:
            filepath.write_text(new_content, encoding="utf-8")

    return modified_count


def main() -> None:
    dry_run = "--apply" not in sys.argv

    if dry_run:
        print("DRY RUN - no files will be modified. Use --apply to write changes.\n")
    else:
        print("APPLYING changes to template files.\n")

    if not TEMPLATES_DIR.exists():
        print(f"ERROR: Templates directory not found: {TEMPLATES_DIR}")
        sys.exit(1)

    html_files = sorted(TEMPLATES_DIR.glob("*.html"))
    total_modified = 0
    files_modified = 0

    for filepath in html_files:
        # Skip layouts and snippets
        if any(filepath.name.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue

        count = process_file(filepath, dry_run=dry_run)
        total_modified += count
        if count > 0:
            files_modified += 1

    print(
        f"\nTotal: {total_modified} URL(s) across {files_modified} file(s) "
        f"(of {len(html_files)} scanned)"
    )


if __name__ == "__main__":
    main()
