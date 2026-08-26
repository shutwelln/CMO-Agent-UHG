#!/usr/bin/env python3
"""HOTFIX: Remove broken Compute Email Hash node, restore subscribe workflow."""
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

        # 1. Remove Compute Email Hash node
        nodes = [n for n in wf["nodes"] if n["name"] != "Compute Email Hash"]
        removed = len(wf["nodes"]) - len(nodes)
        print(f"Removed {removed} node(s) ({len(wf['nodes'])} -> {len(nodes)})")
        if removed == 0:
            print("Compute Email Hash not found - already removed?")
            return

        # 2. Fix connections
        conns = wf["connections"]
        conns.pop("Compute Email Hash", None)

        signup_main = conns.get("Insert Signup", {}).get("main", [[]])
        new_main = []
        for output in signup_main:
            fixed = []
            for conn in output:
                if conn.get("node") == "Compute Email Hash":
                    fixed.append({"node": "Insert Subscriber", "type": "main", "index": 0})
                else:
                    fixed.append(conn)
            new_main.append(fixed)
        conns["Insert Signup"]["main"] = new_main
        print("Rewired: Insert Signup -> Insert Subscriber")

        # 3. Revert Insert Subscriber jsonBody (remove email_hash reference)
        for n in nodes:
            if n["name"] == "Insert Subscriber":
                n["parameters"]["jsonBody"] = (
                    "={{ JSON.stringify({"
                    " email: $json.email,"
                    " content_interest: $json.content_interest || 'all',"
                    " brand: $json.brand || 'saverwell'"
                    " }) }}"
                )
                print("Reverted Insert Subscriber jsonBody")
                break

        # 4. PUT the fix
        payload = {
            "name": wf["name"],
            "nodes": nodes,
            "connections": conns,
            "settings": wf.get("settings", {}),
        }
        r2 = await c.put(f"{base}/api/v1/workflows/{wf_id}", headers=headers, json=payload)
        print(f"Update status: {r2.status_code}")
        if r2.status_code == 200:
            d = r2.json()
            print(f"FIXED: {d['name']} | active={d['active']} | nodes={len(d['nodes'])}")
        else:
            print(r2.text[:500])

if __name__ == "__main__":
    asyncio.run(fix())
