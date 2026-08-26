"""
Comprehensive scan of Supabase discounts_v2 table for placeholder,
dummy, or suspicious values that shouldn't be in production.

Scans ONLY active rows (active=true) across discount_value, details,
and requirement fields.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx

# ── Supabase config ──────────────────────────────────────────────────
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://lmtrgkmgfermqatopkfp.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxtdHJna21nZmVybXFhdG9wa2ZwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk3NzA1NCwiZXhwIjoyMDgxNTUzMDU0fQ.R2zvCHiUgfwnp2Q096UPYNurTlPgMHcbAOyBGIS-ozQ",
)

TABLE = "discounts_v2"
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# ── Text fields to inspect ───────────────────────────────────────────
TEXT_FIELDS = ["discount_value", "details", "requirement"]

# ── Placeholder patterns ────────────────────────────────────────────
# Each entry: (label, compiled regex)
PLACEHOLDER_PATTERNS = [
    ("REPLACE", re.compile(r"\breplace\b", re.IGNORECASE)),
    ("TODO", re.compile(r"\btodo\b", re.IGNORECASE)),
    ("TBD", re.compile(r"\btbd\b", re.IGNORECASE)),
    ("placeholder", re.compile(r"\bplaceholder\b", re.IGNORECASE)),
    ("dummy", re.compile(r"\bdummy\b", re.IGNORECASE)),
    ("test", re.compile(r"\btest\b", re.IGNORECASE)),
    ("sample", re.compile(r"\bsample\b", re.IGNORECASE)),
    ("example", re.compile(r"\bexample\b", re.IGNORECASE)),
    ("N/A", re.compile(r"\bn/?a\b", re.IGNORECASE)),
    ("none (exact)", re.compile(r"^none$", re.IGNORECASE)),
    ("unknown", re.compile(r"\bunknown\b", re.IGNORECASE)),
    ("update (as in 'update this')", re.compile(r"\bupdate\s+this\b", re.IGNORECASE)),
    ("fill in", re.compile(r"\bfill\s+in\b", re.IGNORECASE)),
    ("insert", re.compile(r"\binsert\b", re.IGNORECASE)),
    ("pending", re.compile(r"\bpending\b", re.IGNORECASE)),
    ("coming soon", re.compile(r"\bcoming\s+soon\b", re.IGNORECASE)),
    ("TBA", re.compile(r"\btba\b", re.IGNORECASE)),
    ("XXX", re.compile(r"\bxxx\b", re.IGNORECASE)),
    ("??? or ??", re.compile(r"\?\?+", re.IGNORECASE)),
    ("just ellipsis", re.compile(r"^\.{2,}$")),
    ("empty string", re.compile(r"^$")),
    ("whitespace only", re.compile(r"^\s+$")),
]


def fetch_all_active_rows(client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch ALL active rows from discounts_v2, handling pagination."""
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000

    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/{TABLE}"
            f"?active=eq.true"
            f"&select=*"
            f"&limit={page_size}"
            f"&offset={offset}"
        )
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size

    return all_rows


def scan_for_placeholders(
    rows: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Scan text fields for placeholder patterns. Returns {pattern_label: [matches]}."""
    matches: Dict[str, List[Dict[str, Any]]] = {}

    for label, regex in PLACEHOLDER_PATTERNS:
        hits: List[Dict[str, Any]] = []
        for row in rows:
            for field in TEXT_FIELDS:
                val = row.get(field)
                if val is None:
                    # NULL handling done separately
                    continue
                val_str = str(val).strip()
                if regex.search(val_str):
                    hits.append(
                        {
                            "id": row.get("id"),
                            "merchant_name": row.get("merchant_name", ""),
                            "field": field,
                            "value": val_str[:120],
                        }
                    )
        if hits:
            matches[label] = hits

    return matches


def find_nulls_and_empties(
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Find active rows where text fields are NULL or empty."""
    issues: List[Dict[str, Any]] = []
    for row in rows:
        for field in TEXT_FIELDS:
            val = row.get(field)
            if val is None:
                issues.append(
                    {
                        "id": row.get("id"),
                        "merchant_name": row.get("merchant_name", ""),
                        "field": field,
                        "issue": "NULL",
                    }
                )
            elif isinstance(val, str) and val.strip() == "":
                issues.append(
                    {
                        "id": row.get("id"),
                        "merchant_name": row.get("merchant_name", ""),
                        "field": field,
                        "issue": "empty string",
                    }
                )
    return issues


def aggregate_values(
    rows: List[Dict[str, Any]], field: str
) -> Counter:
    """Count unique values for a field."""
    return Counter(str(row.get(field, "")) for row in rows)


def print_separator(char: str = "=", width: int = 80) -> None:
    print(char * width)


def print_section(title: str) -> None:
    print()
    print_separator()
    print(f"  {title}")
    print_separator()


def main() -> None:
    print_separator("#")
    print("  DISCOUNTS_V2 PLACEHOLDER & ANOMALY SCAN")
    print("  Scanning ONLY active rows")
    print_separator("#")

    with httpx.Client(timeout=30) as client:
        print("\nFetching all active rows from discounts_v2...")
        rows = fetch_all_active_rows(client)
        print(f"Total active rows: {len(rows)}")

        if not rows:
            print("No active rows found. Nothing to scan.")
            return

        # ── 1. Placeholder pattern matches ───────────────────────────
        print_section("1. PLACEHOLDER PATTERN MATCHES")
        matches = scan_for_placeholders(rows)
        if not matches:
            print("\n  No placeholder patterns found in any active rows.")
        else:
            total_hits = sum(len(v) for v in matches.values())
            print(f"\n  Found {total_hits} total matches across {len(matches)} patterns:\n")
            for label, hits in matches.items():
                print(f"  --- Pattern: '{label}' ({len(hits)} match(es)) ---")
                for h in hits[:20]:  # cap display at 20 per pattern
                    print(
                        f"    ID={h['id']}  merchant={h['merchant_name']!r}"
                        f"  field={h['field']}  value={h['value']!r}"
                    )
                if len(hits) > 20:
                    print(f"    ... and {len(hits) - 20} more")
                print()

        # ── 2. NULL and empty fields ─────────────────────────────────
        print_section("2. NULL OR EMPTY FIELDS ON ACTIVE ROWS")
        null_empties = find_nulls_and_empties(rows)
        if not null_empties:
            print("\n  No NULL or empty text fields on active rows.")
        else:
            print(f"\n  Found {len(null_empties)} NULL/empty fields:\n")
            for ne in null_empties[:50]:
                print(
                    f"    ID={ne['id']}  merchant={ne['merchant_name']!r}"
                    f"  field={ne['field']}  issue={ne['issue']}"
                )
            if len(null_empties) > 50:
                print(f"    ... and {len(null_empties) - 50} more")

        # ── 3. Unique discount_value values ──────────────────────────
        print_section("3. UNIQUE discount_value VALUES (with counts)")
        dv_counts = aggregate_values(rows, "discount_value")
        print(f"\n  {len(dv_counts)} unique values:\n")
        for val, count in dv_counts.most_common():
            flag = ""
            # Flag suspicious values
            if val.strip() == "" or val == "None":
                flag = "  <-- SUSPICIOUS"
            elif len(val) > 80:
                flag = "  <-- UNUSUALLY LONG"
            elif re.match(r"^[\d.]+$", val):
                flag = "  <-- BARE NUMBER (no % or $)"
            print(f"    [{count:>4}x]  {val!r}{flag}")

        # ── 4. Unique requirement values ─────────────────────────────
        print_section("4. UNIQUE requirement VALUES (with counts)")
        req_counts = aggregate_values(rows, "requirement")
        print(f"\n  {len(req_counts)} unique values:\n")
        for val, count in req_counts.most_common():
            flag = ""
            if val.strip() == "" or val == "None":
                flag = "  <-- SUSPICIOUS"
            print(f"    [{count:>4}x]  {val!r}{flag}")

        # ── 5. Unique details values (sample) ────────────────────────
        print_section("5. UNIQUE details VALUES (with counts)")
        det_counts = aggregate_values(rows, "details")
        print(f"\n  {len(det_counts)} unique values:\n")
        for val, count in det_counts.most_common():
            flag = ""
            if val.strip() == "" or val == "None":
                flag = "  <-- SUSPICIOUS"
            # Truncate long details for readability
            display = val[:100] + ("..." if len(val) > 100 else "")
            print(f"    [{count:>4}x]  {display!r}{flag}")

        # ── 6. Additional anomaly checks ─────────────────────────────
        print_section("6. ADDITIONAL ANOMALY CHECKS")

        # 6a. Rows with identical discount_value + details + requirement
        print("\n  6a. Fully duplicate rows (same discount_value + details + requirement):")
        combo_counter: Counter = Counter()
        combo_rows: Dict[str, List[int]] = {}
        for row in rows:
            key = (
                str(row.get("discount_value", "")),
                str(row.get("details", "")),
                str(row.get("requirement", "")),
            )
            combo_counter[key] += 1
            combo_rows.setdefault(str(key), []).append(row.get("id", 0))

        dupes_found = False
        for key_tuple, count in combo_counter.most_common():
            if count > 1:
                dupes_found = True
                dv, det, req = key_tuple
                ids = combo_rows[str(key_tuple)][:10]
                print(
                    f"    [{count}x] discount_value={dv!r}  details={det[:60]!r}  "
                    f"requirement={req[:60]!r}"
                )
                print(f"          IDs: {ids}")
        if not dupes_found:
            print("    No fully duplicate active rows found.")

        # 6b. Very short or suspicious discount_value patterns
        print("\n  6b. Unusually short discount_value (1-2 chars, not '$' or '%'):")
        short_found = False
        for row in rows:
            val = str(row.get("discount_value", ""))
            if 0 < len(val.strip()) <= 2 and val.strip() not in ("$", "%"):
                short_found = True
                print(
                    f"    ID={row.get('id')}  merchant={row.get('merchant_name', '')!r}"
                    f"  discount_value={val!r}"
                )
        if not short_found:
            print("    None found.")

        # 6c. discount_value with no digits (not a real discount?)
        print("\n  6c. discount_value with NO digits (possibly not a real discount):")
        no_digit_found = False
        for row in rows:
            val = str(row.get("discount_value", "")).strip()
            if val and not any(c.isdigit() for c in val):
                no_digit_found = True
                print(
                    f"    ID={row.get('id')}  merchant={row.get('merchant_name', '')!r}"
                    f"  discount_value={val!r}"
                )
        if not no_digit_found:
            print("    None found.")

        # 6d. Check for columns we might not know about
        print("\n  6d. All columns present in the data:")
        if rows:
            cols = sorted(rows[0].keys())
            print(f"    {cols}")

        # ── Summary ──────────────────────────────────────────────────
        print_section("SUMMARY")
        total_issues = 0
        if matches:
            total_issues += sum(len(v) for v in matches.values())
        total_issues += len(null_empties)
        print(f"\n  Total active rows scanned: {len(rows)}")
        print(f"  Placeholder pattern matches: {sum(len(v) for v in matches.values()) if matches else 0}")
        print(f"  NULL/empty field issues: {len(null_empties)}")
        print(f"  Unique discount_value values: {len(dv_counts)}")
        print(f"  Unique requirement values: {len(req_counts)}")
        print(f"  Unique details values: {len(det_counts)}")
        if total_issues == 0:
            print("\n  RESULT: No placeholder or suspicious values detected in active rows.")
        else:
            print(f"\n  RESULT: {total_issues} potential issue(s) found. Review matches above.")
        print()


if __name__ == "__main__":
    main()
