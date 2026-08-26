#!/usr/bin/env python3
"""Add partner promotion GA4 event tags to GTM.

Creates 4 DataLayer variables, 2 custom triggers, and 2 GA4 event tags
for partner_promo_view and partner_promo_click events. Publishes a new
container version. Idempotent - skips entities that already exist.

Usage:  python scripts/setup_partner_promo_gtm.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

TOKEN_PATH = ROOT / "data" / "google-token.json"

GTM_SCOPES = [
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
]

# Include existing scopes so we don't lose them on re-auth
ALL_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
]


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERR] {msg}")


def ensure_gtm_credentials() -> Any:
    """Load OAuth token, re-auth if GTM scopes are missing."""
    from google.oauth2.credentials import Credentials

    needs_reauth = False
    creds = None

    if TOKEN_PATH.exists():
        token_data = json.loads(TOKEN_PATH.read_text())
        existing_scopes = set(token_data.get("scopes", []))
        required = set(GTM_SCOPES)

        missing = required - existing_scopes
        if missing:
            print(f"Missing GTM scopes: {', '.join(s.split('/')[-1] for s in missing)}")
            needs_reauth = True
        else:
            _ok("GTM scopes present")
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)

            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                print("Refreshing expired token...")
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                _ok("Token refreshed")

            if creds.valid:
                return creds
            needs_reauth = True
    else:
        print("No token file found")
        needs_reauth = True

    if needs_reauth:
        print("Re-authenticating with GTM scopes...")
        print("A browser window will open - click 'Allow' to authorize.\n")

        token_data = json.loads(TOKEN_PATH.read_text())
        client_config = {
            "installed": {
                "client_id": token_data.get("client_id", ""),
                "client_secret": token_data.get("client_secret", ""),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(client_config, scopes=ALL_SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN_PATH.write_text(creds.to_json())
        _ok("Token saved with GTM scopes")

    return creds


def main() -> None:
    from googleapiclient.discovery import build

    print("=== Partner Promotion GTM Setup ===\n")

    # ── Auth ─────────────────────────────────────────────────────────
    creds = ensure_gtm_credentials()
    service = build("tagmanager", "v2", credentials=creds)

    # ── Find container ───────────────────────────────────────────────
    print("\nFinding Saverwell GTM container...")
    accounts = service.accounts().list().execute().get("account", [])
    if not accounts:
        raise SystemExit("No GTM accounts found.")

    gtm_account = accounts[0]
    account_path = gtm_account["path"]
    _ok(f"Account: {gtm_account['name']}")

    containers = (
        service.accounts()
        .containers()
        .list(parent=account_path)
        .execute()
        .get("container", [])
    )

    container = None
    for c in containers:
        if c["name"] == "Saverwell - GA4":
            container = c
            break

    if not container:
        raise SystemExit("Container 'Saverwell - GA4' not found.")

    container_path = container["path"]
    _ok(f"Container: {container['containerId']}")

    # ── Get workspace ────────────────────────────────────────────────
    workspaces = (
        service.accounts()
        .containers()
        .workspaces()
        .list(parent=container_path)
        .execute()
        .get("workspace", [])
    )

    if not workspaces:
        raise SystemExit("No workspaces found in container")

    workspace = workspaces[0]
    workspace_path = workspace["path"]
    _ok(f"Workspace: {workspace['name']}")

    # ── List existing entities ───────────────────────────────────────
    def _list_existing(entity_type: str) -> Dict[str, Any]:
        method = getattr(service.accounts().containers().workspaces(), entity_type)
        try:
            result = method().list(parent=workspace_path).execute()
            # Try both plural and singular keys
            items = result.get(entity_type[:-1], result.get(entity_type, []))
            if not items:
                items = []
        except Exception:
            items = []
        return {item["name"]: item for item in items}

    existing_vars = _list_existing("variables")
    existing_triggers = _list_existing("triggers")
    existing_tags = _list_existing("tags")

    # ── Create DataLayer Variables ───────────────────────────────────
    print("\nCreating DataLayer variables...")

    def create_variable(name: str) -> Optional[str]:
        if name in existing_vars:
            _skip(f"Variable '{name}' exists")
            return existing_vars[name].get("variableId")
        try:
            v = (
                service.accounts()
                .containers()
                .workspaces()
                .variables()
                .create(
                    parent=workspace_path,
                    body={
                        "name": name,
                        "type": "v",  # DataLayer Variable
                        "parameter": [
                            {
                                "type": "template",
                                "key": "name",
                                "value": name.replace("DLV - ", ""),
                            },
                            {"type": "integer", "key": "dataLayerVersion", "value": "2"},
                        ],
                    },
                )
                .execute()
            )
            _ok(f"Variable '{name}' created")
            time.sleep(2)  # GTM API rate limit
            return v.get("variableId")
        except Exception as e:
            _err(f"Variable '{name}': {e}")
            return None

    new_dlvs = ["partner_slug", "promotion_type", "guide_slug", "position"]
    for param in new_dlvs:
        create_variable(f"DLV - {param}")

    # ── Create Triggers ──────────────────────────────────────────────
    print("\nCreating triggers...")

    trigger_ids: Dict[str, str] = {}

    def create_trigger(name: str, event_name: str) -> Optional[str]:
        if name in existing_triggers:
            _skip(f"Trigger '{name}' exists")
            trigger_ids[event_name] = existing_triggers[name].get("triggerId", "")
            return trigger_ids[event_name]
        try:
            t = (
                service.accounts()
                .containers()
                .workspaces()
                .triggers()
                .create(
                    parent=workspace_path,
                    body={
                        "name": name,
                        "type": "customEvent",
                        "customEventFilter": [
                            {
                                "type": "equals",
                                "parameter": [
                                    {"type": "template", "key": "arg0", "value": "{{_event}}"},
                                    {"type": "template", "key": "arg1", "value": event_name},
                                ],
                            }
                        ],
                    },
                )
                .execute()
            )
            tid = t.get("triggerId", "")
            trigger_ids[event_name] = tid
            _ok(f"Trigger '{name}' created (ID: {tid})")
            time.sleep(2)
            return tid
        except Exception as e:
            _err(f"Trigger '{name}': {e}")
            return None

    create_trigger("CE - partner_promo_view", "partner_promo_view")
    create_trigger("CE - partner_promo_click", "partner_promo_click")

    # ── Create GA4 Event Tags ────────────────────────────────────────
    print("\nCreating GA4 event tags...")

    def _param_map(params: List[Tuple[str, str]]) -> List[Dict]:
        return [
            {
                "type": "map",
                "map": [
                    {"type": "template", "key": "name", "value": param_name},
                    {"type": "template", "key": "value", "value": f"{{{{DLV - {var_name}}}}}"},
                ],
            }
            for param_name, var_name in params
        ]

    def create_tag(
        name: str,
        event_name: str,
        params: List[Tuple[str, str]],
        trigger_id: str,
        priority: Optional[int] = None,
    ) -> Optional[str]:
        if name in existing_tags:
            _skip(f"Tag '{name}' exists")
            return existing_tags[name].get("tagId")

        tag_params: List[Dict[str, Any]] = [
            {
                "type": "template",
                "key": "measurementIdOverride",
                "value": "{{GA4 Measurement ID}}",
            },
            {"type": "template", "key": "eventName", "value": event_name},
        ]

        if params:
            tag_params.append(
                {
                    "type": "list",
                    "key": "eventParameters",
                    "list": _param_map(params),
                }
            )

        body: Dict[str, Any] = {
            "name": name,
            "type": "gaawe",  # GA4 Event tag
            "parameter": tag_params,
            "firingTriggerId": [trigger_id],
        }
        if priority is not None:
            body["priority"] = {"type": "integer", "value": str(priority)}

        try:
            t = (
                service.accounts()
                .containers()
                .workspaces()
                .tags()
                .create(parent=workspace_path, body=body)
                .execute()
            )
            _ok(f"Tag '{name}' created")
            time.sleep(2)
            return t.get("tagId")
        except Exception as e:
            _err(f"Tag '{name}': {e}")
            return None

    # Both events share the same 4 parameters
    promo_params = [
        ("partner_slug", "partner_slug"),
        ("promotion_type", "promotion_type"),
        ("guide_slug", "guide_slug"),
        ("position", "position"),
    ]

    # partner_promo_view - impression tracking
    view_trigger = trigger_ids.get("partner_promo_view", "")
    if view_trigger:
        create_tag("GA4 - partner_promo_view", "partner_promo_view", promo_params, view_trigger)
    else:
        _err("No trigger ID for partner_promo_view - skipping tag")

    # partner_promo_click - click tracking (high priority, user navigates away)
    click_trigger = trigger_ids.get("partner_promo_click", "")
    if click_trigger:
        create_tag(
            "GA4 - partner_promo_click",
            "partner_promo_click",
            promo_params,
            click_trigger,
            priority=100,
        )
    else:
        _err("No trigger ID for partner_promo_click - skipping tag")

    # ── Publish ──────────────────────────────────────────────────────
    print("\nCreating container version and publishing...")
    try:
        version = (
            service.accounts()
            .containers()
            .workspaces()
            .create_version(
                path=workspace_path,
                body={
                    "name": "Partner Promotion Events",
                    "notes": "Added partner_promo_view and partner_promo_click events with 4 DLVs",
                },
            )
            .execute()
        )

        version_id = version.get("containerVersion", {}).get("containerVersionId")
        if version_id:
            _ok(f"Version created: {version_id}")

            service.accounts().containers().versions().publish(
                path=f"{container_path}/versions/{version_id}"
            ).execute()
            _ok("Container published!")
        else:
            _err("Version creation returned no version ID")
    except Exception as e:
        _err(f"Version/publish: {e}")
        print("  You can publish manually in the GTM UI")

    print("\n=== Done! ===")
    print("Created:")
    print("  4 DataLayer Variables: partner_slug, promotion_type, guide_slug, position")
    print("  2 Triggers: CE - partner_promo_view, CE - partner_promo_click")
    print("  2 GA4 Event Tags: GA4 - partner_promo_view, GA4 - partner_promo_click")
    print("\nVerify in GTM Preview mode before going live.")


if __name__ == "__main__":
    main()
