#!/usr/bin/env python3
"""HOTFIX: Fix Build CIO Payload to read from Insert Signup instead of Insert Subscriber.

Insert Subscriber returns empty {} (Prefer: return=minimal). Build CIO Payload uses
$input.item.json which gets {}, losing all subscriber data. Fix: change the code to
read from $('Insert Signup') which has the full data.
"""
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

        for n in wf["nodes"]:
            if n["name"] == "Build CIO Payload":
                old_code = n["parameters"]["jsCode"]
                # Replace $input.item.json with $('Insert Signup').item.json
                # so it reads the full subscriber data, not Insert Subscriber's empty response
                new_code = old_code.replace(
                    "const item = $input.item.json;",
                    "const item = $('Insert Signup').item.json;"
                )
                if new_code == old_code:
                    print("WARNING: Could not find the line to replace!")
                    print(f"First 200 chars: {old_code[:200]}")
                    return
                n["parameters"]["jsCode"] = new_code
                print("Fixed Build CIO Payload: $input.item.json -> $('Insert Signup').item.json")
                break

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
