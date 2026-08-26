#!/usr/bin/env python3
"""HOTFIX: Fix Insert Subscriber upsert by adding on_conflict=email to URL."""
from __future__ import annotations
import asyncio, os, sys, json
from dotenv import load_dotenv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
load_dotenv()

async def fix():
    import httpx
    base = os.environ["N8N_BASE_URL"]
    key = os.environ["N8N_API_KEY"]
    wf_id = "figz7MWe15HPc48z"
    headers = {"X-N8N-API-KEY": key, "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(f"{base}/api/v1/workflows/{wf_id}", headers=headers)
        wf = r.json()

        # Fix Insert Subscriber URL: add ?on_conflict=email for upsert
        changed = False
        for n in wf["nodes"]:
            if n["name"] == "Insert Subscriber":
                old_url = n["parameters"]["url"]
                print(f"Old URL: {old_url}")
                if "on_conflict" not in old_url:
                    n["parameters"]["url"] = old_url.rstrip("/") + "?on_conflict=email"
                    print(f"New URL: {n['parameters']['url']}")
                    changed = True
                else:
                    print("Already has on_conflict - no change needed")

                # Also restore onError: continueRegardlessOfError
                n["onError"] = "continueRegardlessOfError"
                print("Set onError: continueRegardlessOfError")
                break

        if not changed:
            print("No URL change needed")
            return

        payload = {
            "name": wf["name"],
            "nodes": wf["nodes"],
            "connections": wf["connections"],
            "settings": wf.get("settings", {}),
        }
        r2 = await c.put(f"{base}/api/v1/workflows/{wf_id}", headers=headers, json=payload)
        print(f"Update status: {r2.status_code}")
        if r2.status_code == 200:
            d = r2.json()
            print(f"FIXED: {d['name']} | active={d['active']}")
        else:
            print(r2.text[:500])

if __name__ == "__main__":
    asyncio.run(fix())
