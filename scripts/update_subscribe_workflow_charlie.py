#!/usr/bin/env python3
"""
Update the Saverwell Subscribe Workflow to add Charlie Saver conversion tracking.

Adds 4 nodes between "Track Subscribe Event" and "Build GA4 Payload":
1. IF - Is Charlie Convert (checks brand == 'charliesaver')
2. Charlie CIO Track Event (POST converted_to_saverwell event to Charlie's CIO)
3. Supabase Charlie Update (PATCH charlie_clean_list converted_to_saverwell=true)
4. No Op - Rejoin Charlie Flow (merges true/false branches back to GA4 pipeline)

All new nodes: onError=continueRegardlessOfError (won't break main subscribe flow).

PREREQUISITES:
  - Create n8n credential "Charlie Customer.io Track API" (HTTP Basic Auth)
    Username: Charlie's site_id
    Password: Charlie's API key
  - The Supabase node references existing credential "Supabase account" (SvYiHFnN6BeUIQYA)
    If supabaseApi doesn't work with HTTP Request, open the node in n8n UI and configure auth.

Usage:
  source .venv/bin/activate
  python scripts/update_subscribe_workflow_charlie.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()


async def main() -> None:
    from src.cmo_agent.n8n.client import N8NClient

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

    # Convert Pydantic models to dicts for manipulation
    nodes_dicts = [n.model_dump(by_alias=True) for n in wf.nodes]
    # Strip None credentials (n8n API rejects null, expects object or absent)
    for nd in nodes_dicts:
        if nd.get("credentials") is None:
            del nd["credentials"]
    connections = dict(wf.connections)  # Already a dict, but copy it

    # ── Verify expected nodes exist ──────────────────────────────────────
    node_names = {n["name"] for n in nodes_dicts}
    required = {"Track Subscribe Event", "Build GA4 Payload"}
    missing = required - node_names
    if missing:
        print(f"ERROR: Missing expected nodes: {missing}")
        sys.exit(1)

    # Check if we already added Charlie nodes (idempotency)
    if "IF - Is Charlie Convert" in node_names:
        print("Charlie conversion nodes already exist in this workflow. Skipping.")
        await client.close()
        sys.exit(0)

    # ── Define new nodes ─────────────────────────────────────────────────
    new_nodes = [
        # 1. IF - Is Charlie Convert
        {
            "parameters": {
                "conditions": {
                    "options": {
                        "caseSensitive": True,
                        "leftValue": "",
                        "typeValidation": "strict",
                    },
                    "conditions": [
                        {
                            "id": "charlie-brand-check",
                            "leftValue": "={{ $json.brand }}",
                            "rightValue": "charliesaver",
                            "operator": {
                                "type": "string",
                                "operation": "equals",
                            },
                        }
                    ],
                    "combinator": "and",
                },
                "options": {},
            },
            "type": "n8n-nodes-base.if",
            "typeVersion": 2.2,
            "position": [2016, 304],
            "id": "charlie-if-check",
            "name": "IF - Is Charlie Convert",
        },
        # 2. Charlie CIO Track Event
        {
            "parameters": {
                "method": "POST",
                "url": (
                    "=https://track.customer.io/api/v1/customers/"
                    "{{ encodeURIComponent($json.email) }}/events"
                ),
                "authentication": "genericCredentialType",
                "genericAuthType": "httpBasicAuth",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": (
                    "={{ JSON.stringify({"
                    " name: 'converted_to_saverwell',"
                    " data: {"
                    " converted_date: $now.format('yyyy-MM-dd'),"
                    " saverwell_email: $json.email"
                    " }"
                    " }) }}"
                ),
                "options": {},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2240, 160],
            "id": "charlie-cio-track",
            "name": "Charlie CIO Track Event",
            "onError": "continueRegardlessOfError",
            "credentials": {
                "httpBasicAuth": {
                    "id": "",
                    "name": "Charlie Customer.io Track API",
                }
            },
        },
        # 3. Supabase Charlie Update
        {
            "parameters": {
                "method": "PATCH",
                "url": (
                    "=https://lmtrgkmgfermqatopkfp.supabase.co/rest/v1/"
                    "charlie_clean_list?email=eq."
                    "{{ encodeURIComponent($json.email) }}"
                ),
                "authentication": "predefinedCredentialType",
                "nodeCredentialType": "supabaseApi",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Prefer", "value": "return=minimal"},
                        {"name": "Content-Type", "value": "application/json"},
                    ]
                },
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": (
                    "={{ JSON.stringify({"
                    " converted_to_saverwell: true,"
                    " converted_at: new Date().toISOString()"
                    " }) }}"
                ),
                "options": {},
            },
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [2464, 160],
            "id": "charlie-supabase-update",
            "name": "Supabase Charlie Update",
            "onError": "continueRegardlessOfError",
            "credentials": {
                "supabaseApi": {
                    "id": "SvYiHFnN6BeUIQYA",
                    "name": "Supabase account",
                }
            },
        },
        # 4. No Op - Rejoin Charlie Flow
        {
            "parameters": {},
            "type": "n8n-nodes-base.noOp",
            "typeVersion": 1,
            "position": [2688, 304],
            "id": "charlie-rejoin-noop",
            "name": "No Op - Rejoin Charlie Flow",
        },
    ]

    # ── Shift downstream nodes right by 896px ────────────────────────────
    shift_nodes = {"Build GA4 Payload", "Send to GA4", "Mark Queue Done"}
    for node in nodes_dicts:
        if node["name"] in shift_nodes:
            x, y = node["position"]
            node["position"] = [x + 896, y]
            print(f"  Shifted '{node['name']}' to [{x + 896}, {y}]")

    # ── Add new nodes ────────────────────────────────────────────────────
    nodes_dicts.extend(new_nodes)

    # ── Update connections ───────────────────────────────────────────────
    # Remove: Track Subscribe Event -> Build GA4 Payload
    track_conns = connections.get("Track Subscribe Event", {}).get("main", [[]])
    new_track_main = []
    for output_conns in track_conns:
        filtered = [c for c in output_conns if c.get("node") != "Build GA4 Payload"]
        new_track_main.append(filtered)
    # Add: Track Subscribe Event -> IF - Is Charlie Convert
    if new_track_main:
        new_track_main[0].append(
            {"node": "IF - Is Charlie Convert", "type": "main", "index": 0}
        )
    else:
        new_track_main = [
            [{"node": "IF - Is Charlie Convert", "type": "main", "index": 0}]
        ]
    connections["Track Subscribe Event"]["main"] = new_track_main

    # IF - Is Charlie Convert connections
    # Output 0 (TRUE) -> Charlie CIO Track Event
    # Output 1 (FALSE) -> No Op - Rejoin Charlie Flow
    connections["IF - Is Charlie Convert"] = {
        "main": [
            [{"node": "Charlie CIO Track Event", "type": "main", "index": 0}],
            [{"node": "No Op - Rejoin Charlie Flow", "type": "main", "index": 0}],
        ]
    }

    # Charlie CIO Track Event -> Supabase Charlie Update
    connections["Charlie CIO Track Event"] = {
        "main": [
            [{"node": "Supabase Charlie Update", "type": "main", "index": 0}]
        ]
    }

    # Supabase Charlie Update -> No Op - Rejoin Charlie Flow
    connections["Supabase Charlie Update"] = {
        "main": [
            [{"node": "No Op - Rejoin Charlie Flow", "type": "main", "index": 0}]
        ]
    }

    # No Op - Rejoin Charlie Flow -> Build GA4 Payload
    connections["No Op - Rejoin Charlie Flow"] = {
        "main": [[{"node": "Build GA4 Payload", "type": "main", "index": 0}]]
    }

    # ── PUT updated workflow ─────────────────────────────────────────────
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
        # Save the payload for manual inspection
        debug_path = "data/saverwell/charlie_workflow_update_debug.json"
        with open(debug_path, "w") as f:
            json.dump(update_payload, f, indent=2)
        print(f"  Saved update payload to {debug_path} for debugging")
        sys.exit(1)
    finally:
        await client.close()

    print("\n--- NEXT STEPS ---")
    print("1. Open the workflow in n8n UI and verify the 4 new nodes are connected correctly")
    print("2. Create n8n credential 'Charlie Customer.io Track API' (HTTP Basic Auth)")
    print("   - Username: Charlie's Customer.io site_id")
    print("   - Password: Charlie's Customer.io API key")
    print("3. Open 'Charlie CIO Track Event' node and select the credential")
    print("4. Open 'Supabase Charlie Update' node and verify Supabase credential is set")
    print("   - If supabaseApi auth doesn't work with HTTP Request, switch to HTTP Header Auth")
    print("     with apikey + Authorization headers")
    print("5. Test with a subscribe from saverwell.com?utm_campaign=CharlieSaver")


if __name__ == "__main__":
    asyncio.run(main())
