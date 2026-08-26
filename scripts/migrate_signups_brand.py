"""Migrate signups table: rename brand 'seniorsaver' -> 'saverwell'."""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.error

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://lmtrgkmgfermqatopkfp.supabase.co"
)
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxtdHJna21nZmVybXFhdG9wa2ZwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk3NzA1NCwiZXhwIjoyMDgxNTUzMDU0fQ.R2zvCHiUgfwnp2Q096UPYNurTlPgMHcbAOyBGIS-ozQ",
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


def api(method: str, path: str, body: dict | None = None) -> list | dict:
    url = f"{SUPABASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        err_body = e.read().decode()
        raise RuntimeError(f"HTTP {e.code}: {err_body}") from e


def main() -> None:
    # Step 1: fetch all rows to understand the schema
    print("=== Step 1: Fetching all signups rows ===")
    rows = api("GET", "/rest/v1/signups?select=*&limit=5")
    if not rows:
        print("Table is empty or does not exist.")
        return

    # Show columns so we can identify the brand field
    print(f"Columns: {list(rows[0].keys())}")
    print(f"Sample row: {json.dumps(rows[0], indent=2)}")

    # Identify the brand field - check common names
    brand_field = None
    for candidate in ["brand", "source", "workspace", "workspace_id"]:
        if candidate in rows[0]:
            brand_field = candidate
            break

    if brand_field is None:
        print("Could not find a brand/source field. Columns available:")
        print(list(rows[0].keys()))
        return

    print(f"\nUsing field: '{brand_field}'")

    # Step 2: Count current distribution
    print("\n=== Step 2: Current brand distribution ===")
    all_rows = api("GET", f"/rest/v1/signups?select=id,{brand_field}")
    total = len(all_rows)
    print(f"Total rows: {total}")

    from collections import Counter
    counts_before = Counter(r[brand_field] for r in all_rows)
    for val, count in counts_before.most_common():
        print(f"  {val!r}: {count}")

    seniorsaver_count = counts_before.get("seniorsaver", 0)
    if seniorsaver_count == 0:
        print("\nNo rows with 'seniorsaver' found. Nothing to migrate.")
        return

    print(f"\n{seniorsaver_count} rows to migrate: 'seniorsaver' -> 'saverwell'")

    # Step 3: PATCH all rows where brand == seniorsaver
    print("\n=== Step 3: Patching rows ===")
    patch_url = f"/rest/v1/signups?{brand_field}=eq.seniorsaver"
    result = api("PATCH", patch_url, {brand_field: "saverwell"})
    print(f"Patched {len(result)} rows")

    # Step 4: Verify no seniorsaver rows remain
    print("\n=== Step 4: Verification ===")
    remaining = api(
        "GET", f"/rest/v1/signups?{brand_field}=eq.seniorsaver&select=id"
    )
    print(f"Remaining 'seniorsaver' rows: {len(remaining)}")

    # Final distribution
    all_rows_after = api("GET", f"/rest/v1/signups?select=id,{brand_field}")
    counts_after = Counter(r[brand_field] for r in all_rows_after)
    print("\n=== Summary ===")
    print(f"Total rows: {len(all_rows_after)}")
    print("Before:")
    for val, count in counts_before.most_common():
        print(f"  {val!r}: {count}")
    print("After:")
    for val, count in counts_after.most_common():
        print(f"  {val!r}: {count}")

    if len(remaining) == 0:
        print("\nMigration complete. All 'seniorsaver' rows updated to 'saverwell'.")
    else:
        print(f"\nWARNING: {len(remaining)} rows still have 'seniorsaver'!")


if __name__ == "__main__":
    main()
