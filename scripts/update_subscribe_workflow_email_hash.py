#!/usr/bin/env python3
"""
Update the Saverwell Subscribe Workflow to compute and store email_hash.

Adds a "Compute Email Hash" Code node between "Insert Signup" and "Insert Subscriber"
that computes SHA-256 of the subscriber's email and passes it through. Then updates
the "Insert Subscriber" node's JSON body to include email_hash.

This enables matching website reads (sw_user_id in localStorage) back to subscribers
for digest personalization.

Usage:
  source .venv/bin/activate
  python scripts/update_subscribe_workflow_email_hash.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
load_dotenv()


async def main() -> None:
    from cmo_agent.n8n.client import N8NClient

    workflow_id = "figz7MWe15HPc48z"

    client = N8NClient(
        base_url=os.environ.get("N8N_BASE_URL", "http://localhost:5678"),
        api_key=os.environ.get("N8N_API_KEY", ""),
    )

    try:
        wf = await client.get_workflow(workflow_id)
    except Exception as e:
        print(f"ERROR: Could not fetch workflow {workflow_id}: {e}")
        sys.exit(1)

    # Convert to dicts for manipulation
    nodes_dicts = [n.model_dump(by_alias=True) for n in wf.nodes]
    for nd in nodes_dicts:
        if nd.get("credentials") is None:
            del nd["credentials"]
    connections = dict(wf.connections)

    # ── Verify expected nodes exist ──────────────────────────────────────
    node_names = {n["name"] for n in nodes_dicts}
    required = {"Insert Signup", "Insert Subscriber"}
    missing = required - node_names
    if missing:
        print(f"ERROR: Missing expected nodes: {missing}")
        print("  Run update_subscribe_workflow_insert_subscriber.py first.")
        sys.exit(1)

    # Idempotency check
    if "Compute Email Hash" in node_names:
        print("Compute Email Hash node already exists. Skipping.")
        await client.close()
        sys.exit(0)

    # ── Find Insert Signup position to place new node after it ─────────
    insert_signup_pos = None
    for nd in nodes_dicts:
        if nd["name"] == "Insert Signup":
            insert_signup_pos = nd["position"]
            break

    if not insert_signup_pos:
        print("ERROR: Could not find Insert Signup position")
        sys.exit(1)

    # Place Compute Email Hash between Insert Signup and Insert Subscriber
    # Shift Insert Subscriber (and everything downstream) 224px right
    new_x = insert_signup_pos[0] + 224
    new_y = insert_signup_pos[1]

    # ── Define new Code node ─────────────────────────────────────────────
    hash_code = (
        "const crypto = require('crypto');\n"
        "const items = $input.all();\n"
        "for (const item of items) {\n"
        "  const email = (item.json.email || '').toLowerCase().trim();\n"
        "  item.json.email_hash = crypto.createHash('sha256')"
        ".update(email).digest('hex');\n"
        "}\n"
        "return items;"
    )

    new_node = {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": hash_code,
        },
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [new_x, new_y],
        "id": "compute-email-hash-node",
        "name": "Compute Email Hash",
    }

    # ── Shift Insert Subscriber and downstream nodes ─────────────────────
    shift_after = set()
    to_visit = ["Insert Subscriber"]
    while to_visit:
        current = to_visit.pop(0)
        if current in shift_after:
            continue
        shift_after.add(current)
        node_conns = connections.get(current, {}).get("main", [])
        for output in node_conns:
            for conn in output:
                if conn.get("node"):
                    to_visit.append(conn["node"])

    for nd in nodes_dicts:
        if nd["name"] in shift_after:
            x, y = nd["position"]
            nd["position"] = [x + 224, y]
            print(f"  Shifted '{nd['name']}' to [{x + 224}, {y}]")

    # ── Add new node ───────────────────────────────────────────────────
    nodes_dicts.append(new_node)

    # ── Update connections ─────────────────────────────────────────────
    # Rewire: Insert Signup -> Compute Email Hash -> Insert Subscriber
    # (was: Insert Signup -> Insert Subscriber)

    signup_conns = connections.get("Insert Signup", {}).get("main", [[]])
    new_signup_main = []
    for output_conns in signup_conns:
        filtered = [c for c in output_conns if c.get("node") != "Insert Subscriber"]
        filtered.append(
            {"node": "Compute Email Hash", "type": "main", "index": 0}
        )
        new_signup_main.append(filtered)
    connections["Insert Signup"]["main"] = new_signup_main

    # Compute Email Hash -> Insert Subscriber
    connections["Compute Email Hash"] = {
        "main": [[{"node": "Insert Subscriber", "type": "main", "index": 0}]]
    }

    # ── Update Insert Subscriber jsonBody to include email_hash ──────────
    for nd in nodes_dicts:
        if nd["name"] == "Insert Subscriber":
            nd["parameters"]["jsonBody"] = (
                "={{ JSON.stringify({"
                " email: $json.email,"
                " email_hash: $json.email_hash,"
                " content_interest: $json.content_interest || 'all',"
                " brand: $json.brand || 'saverwell'"
                " }) }}"
            )
            print("  Updated Insert Subscriber jsonBody to include email_hash")
            break

    # ── PUT updated workflow ───────────────────────────────────────────
    update_payload = {
        "name": wf.name,
        "nodes": nodes_dicts,
        "connections": connections,
        "settings": wf.settings,
    }

    try:
        result = await client.update_workflow(workflow_id, update_payload)
        print(f"\nWorkflow updated successfully: {result.name}")
        print(f"  Total nodes: {len(result.nodes)}")
        print(f"  Active: {result.active}")
    except Exception as e:
        print(f"\nERROR updating workflow: {e}")
        debug_path = "data/saverwell/charlie_workflow_update_debug.json"
        with open(debug_path, "w") as f:
            json.dump(update_payload, f, indent=2)
        print(f"  Saved update payload to {debug_path} for debugging")
        sys.exit(1)
    finally:
        await client.close()

    print("\n--- DONE ---")
    print("Compute Email Hash node added to Subscribe workflow.")
    print("New subscribers will now have email_hash stored for web read tracking.")


if __name__ == "__main__":
    asyncio.run(main())
