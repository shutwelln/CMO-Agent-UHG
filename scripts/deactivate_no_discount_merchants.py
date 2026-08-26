"""Deactivate merchants that have page content but no default_discount_* data.

These 17 merchants have LLM-generated page content with invented discount claims
that aren't backed by any verified data in the merchants table.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Merchants with page content but no default_discount_* data
MERCHANT_IDS = [
    899,   # Helzberg Diamonds
    3783,  # King Soopers
    982,   # Midas
    1153,  # Ashley Store
    791,   # Smoothie King
    807,   # Athleta
    966,   # Nothing Bundt Cakes
    951,   # Pep Boys
    146,   # Shoe Carnival
    406,   # Great American Cookies
    1232,  # Sunglass Hut at Macy's
    1265,  # BJ's Wholesale Club
    1315,  # Batteries Plus
    3763,  # Fry's Food And Drug
    3773,  # Ralphs
    3778,  # Harris Teeter
    3781,  # Smith's
]


def main() -> None:
    print(f"Deactivating {len(MERCHANT_IDS)} merchants with no discount data...\n")

    success = 0
    for mid in MERCHANT_IDS:
        resp = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/merchants?id=eq.{mid}",
            headers=HEADERS,
            json={"is_active": False},
            timeout=15,
        )
        if resp.status_code not in (200, 204):
            print(f"  FAILED [{mid}]: {resp.status_code} {resp.text[:200]}")
            continue

        rows = resp.json()
        if rows:
            print(f"  Deactivated [{mid}] {rows[0].get('name', '?')}")
            success += 1
        else:
            print(f"  No rows matched for id={mid}")

    print(f"\nDone. {success}/{len(MERCHANT_IDS)} merchants deactivated.")


if __name__ == "__main__":
    main()
