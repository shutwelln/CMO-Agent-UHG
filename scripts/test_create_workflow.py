#!/usr/bin/env python3
"""Test script to reproduce and verify n8n workflow creation."""

import asyncio
import json
import sys
sys.path.insert(0, "src")

from cmo_agent.config import get_settings
from cmo_agent.n8n.client import N8NClient
from cmo_agent.core.agent import _normalize_nodes, _normalize_connections, _normalize_settings


async def test_create_workflow_direct():
    """Test creating a minimal workflow directly via n8n client."""
    settings = get_settings()

    print(f"Connecting to n8n at: {settings.n8n_base_url}")

    client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
    )

    async with client:
        # Health check first
        is_healthy = await client.health_check()
        print(f"n8n health check: {'OK' if is_healthy else 'FAILED'}")

        if not is_healthy:
            print("Cannot proceed - n8n is not reachable")
            return

        # Minimal workflow payload - strict whitelist
        # n8n requires 'settings' to be present (even if empty object)
        workflow_payload = {
            "name": "Test Workflow from Script",
            "nodes": [
                {
                    "name": "Manual Trigger",
                    "type": "n8n-nodes-base.manualTrigger",
                    "typeVersion": 1,
                    "position": [250, 300],
                    "parameters": {}
                },
                {
                    "name": "Set Data",
                    "type": "n8n-nodes-base.set",
                    "typeVersion": 1,
                    "position": [450, 300],
                    "parameters": {
                        "values": {
                            "string": [{"name": "test", "value": "hello"}]
                        }
                    }
                }
            ],
            "connections": {
                "Manual Trigger": {
                    "main": [[{"node": "Set Data", "type": "main", "index": 0}]]
                }
            },
            "settings": {}  # Required by n8n, even if empty
        }

        print("\n=== Test 1: Direct API call ===")
        print(f"Payload keys: {list(workflow_payload.keys())}")
        print(f"'active' in payload: {'active' in workflow_payload}")

        try:
            workflow = await client.create_workflow(workflow_payload)
            print(f"✅ SUCCESS! Workflow created: ID={workflow.id}")

            # Clean up
            await client.delete_workflow(workflow.id)
            print("✅ Test workflow deleted")

        except Exception as e:
            print(f"❌ FAILED: {e}")
            return

        # Test 2: Simulate what the agent tool does
        print("\n=== Test 2: Via agent normalization ===")
        nodes = [
            {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"},
            {"name": "HTTP", "type": "n8n-nodes-base.httpRequest"},
        ]
        connections = {
            "Trigger": {"main": [[{"node": "HTTP", "type": "main", "index": 0}]]}
        }

        normalized_nodes = _normalize_nodes(nodes)
        normalized_connections = _normalize_connections(connections)
        normalized_settings = _normalize_settings(None)

        workflow_data = {
            "name": "Test via Agent Normalization",
            "nodes": normalized_nodes,
            "connections": normalized_connections,
            "settings": normalized_settings,  # Should be {} even when None
        }

        print(f"Payload keys: {list(workflow_data.keys())}")
        print(f"settings value: {workflow_data['settings']}")
        print(f"'active' in payload: {'active' in workflow_data}")

        try:
            workflow = await client.create_workflow(workflow_data)
            print(f"✅ SUCCESS! Workflow created: ID={workflow.id}")

            # Clean up
            await client.delete_workflow(workflow.id)
            print("✅ Test workflow deleted")

        except Exception as e:
            print(f"❌ FAILED: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(test_create_workflow_direct())
