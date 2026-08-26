#!/usr/bin/env python3
"""Add Customer.io tracking + UTM email bypass to GTM.

Creates 3 Custom HTML tags in the Saverwell GTM container:
  1. Customer.io In-App SDK          - loads CIO tracking snippet on all pages
  2. Customer.io Identify (Email)    - identifies subscribers who click through from emails
  3. UTM Email Bypass Cookie         - sets sw_email_subscriber=true cookie when utm_medium=email

Publishes a new container version. Idempotent - skips tags that already exist.

Usage:  python scripts/setup_customerio_gtm.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

TOKEN_PATH = ROOT / "data" / "google-token.json"

CUSTOMERIO_SITE_ID = "8e297c5c2d9b929327fc"

GTM_SCOPES = [
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
]

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


# ── Tag HTML snippets ─────────────────────────────────────────────

TAG_CIO_SDK = f"""\
<script>
  var _cio = _cio || [];
  (function() {{
    var t,s;
    t = document.createElement('script');
    t.async = true;
    t.id = 'cio-tracker';
    t.setAttribute('data-site-id', '{CUSTOMERIO_SITE_ID}');
    t.setAttribute('data-use-array-params', 'true');
    t.setAttribute('data-use-in-app', 'true');
    t.src = 'https://assets.customer.io/assets/track.js';
    s = document.getElementsByTagName('script')[0];
    s.parentNode.insertBefore(t, s);
  }})();
</script>"""

TAG_CIO_IDENTIFY = """\
<script>
  (function() {
    var params = new URLSearchParams(window.location.search);
    var cioId = params.get('cio_id');
    if (cioId) {
      var _cio = window._cio || [];
      _cio.identify({ id: cioId });
    }
  })();
</script>"""

TAG_UTM_BYPASS = """\
<script>
  (function() {
    var params = new URLSearchParams(window.location.search);
    if (params.get('utm_medium') === 'email') {
      document.cookie = 'sw_email_subscriber=true; path=/; SameSite=Lax';
    }
  })();
</script>"""


# ── Auth ──────────────────────────────────────────────────────────

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
            print(
                f"Missing GTM scopes: {', '.join(s.split('/')[-1] for s in missing)}"
            )
            needs_reauth = True
        else:
            _ok("GTM scopes present")
            creds = Credentials.from_authorized_user_file(
                str(TOKEN_PATH), ALL_SCOPES
            )

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

        flow = InstalledAppFlow.from_client_config(
            client_config, scopes=ALL_SCOPES
        )
        creds = flow.run_local_server(port=0, open_browser=True)
        TOKEN_PATH.write_text(creds.to_json())
        _ok("Token saved with GTM scopes")

    return creds


# ── Main ──────────────────────────────────────────────────────────

def main() -> None:
    from googleapiclient.discovery import build

    print("=== Customer.io + UTM Bypass GTM Setup ===\n")
    print(f"Customer.io Site ID: {CUSTOMERIO_SITE_ID}\n")

    # ── Auth ──────────────────────────────────────────────────────
    creds = ensure_gtm_credentials()
    service = build("tagmanager", "v2", credentials=creds)

    # ── Find container ────────────────────────────────────────────
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

    # ── Get workspace ─────────────────────────────────────────────
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

    # ── List existing tags ────────────────────────────────────────
    def _list_existing(entity_type: str) -> Dict[str, Any]:
        method = getattr(
            service.accounts().containers().workspaces(), entity_type
        )
        try:
            result = method().list(parent=workspace_path).execute()
            items = result.get(entity_type[:-1], result.get(entity_type, []))
            if not items:
                items = []
        except Exception:
            items = []
        return {item["name"]: item for item in items}

    existing_tags = _list_existing("tags")
    existing_triggers = _list_existing("triggers")

    # ── Find "All Pages" trigger ──────────────────────────────────
    all_pages_trigger_id = None
    for name, trigger in existing_triggers.items():
        if trigger.get("type") == "pageview":
            all_pages_trigger_id = trigger.get("triggerId")
            _ok(f"Found All Pages trigger: '{name}' (ID: {all_pages_trigger_id})")
            break

    if not all_pages_trigger_id:
        # Create All Pages trigger if it doesn't exist
        print("\nCreating All Pages trigger...")
        try:
            t = (
                service.accounts()
                .containers()
                .workspaces()
                .triggers()
                .create(
                    parent=workspace_path,
                    body={
                        "name": "All Pages",
                        "type": "pageview",
                    },
                )
                .execute()
            )
            all_pages_trigger_id = t.get("triggerId")
            _ok(f"All Pages trigger created (ID: {all_pages_trigger_id})")
            time.sleep(2)
        except Exception as e:
            _err(f"Could not create All Pages trigger: {e}")
            raise SystemExit("Cannot proceed without All Pages trigger")

    # ── Create Custom HTML Tags ───────────────────────────────────
    print("\nCreating Custom HTML tags...")

    tags_to_create: List[Dict[str, Any]] = [
        {
            "name": "CIO - In-App SDK",
            "html": TAG_CIO_SDK,
            "priority": 200,  # fires first
        },
        {
            "name": "CIO - Identify from Email Click",
            "html": TAG_CIO_IDENTIFY,
            "priority": 100,  # fires after SDK
        },
        {
            "name": "UTM - Email Subscriber Bypass Cookie",
            "html": TAG_UTM_BYPASS,
            "priority": 100,
        },
    ]

    created_tags: List[str] = []

    for tag_spec in tags_to_create:
        tag_name = tag_spec["name"]
        if tag_name in existing_tags:
            _skip(f"Tag '{tag_name}' exists")
            continue

        body: Dict[str, Any] = {
            "name": tag_name,
            "type": "html",  # Custom HTML
            "parameter": [
                {
                    "type": "template",
                    "key": "html",
                    "value": tag_spec["html"],
                },
                {
                    "type": "boolean",
                    "key": "supportDocumentWrite",
                    "value": "false",
                },
            ],
            "firingTriggerId": [all_pages_trigger_id],
        }

        if tag_spec.get("priority"):
            body["priority"] = {
                "type": "integer",
                "value": str(tag_spec["priority"]),
            }

        try:
            t = (
                service.accounts()
                .containers()
                .workspaces()
                .tags()
                .create(parent=workspace_path, body=body)
                .execute()
            )
            _ok(f"Tag '{tag_name}' created (ID: {t.get('tagId')})")
            created_tags.append(tag_name)
            time.sleep(2)  # GTM API rate limit
        except Exception as e:
            _err(f"Tag '{tag_name}': {e}")

    # ── Publish ───────────────────────────────────────────────────
    if not created_tags:
        print("\nNo new tags created - skipping publish.")
        print("\n=== Done (no changes) ===")
        return

    print("\nCreating container version and publishing...")
    try:
        version = (
            service.accounts()
            .containers()
            .workspaces()
            .create_version(
                path=workspace_path,
                body={
                    "name": "Customer.io SDK + UTM Email Bypass",
                    "notes": (
                        "Added Customer.io In-App SDK (site: "
                        f"{CUSTOMERIO_SITE_ID}), "
                        "email click identify, and UTM email "
                        "subscriber bypass cookie."
                    ),
                },
            )
            .execute()
        )

        version_id = version.get("containerVersion", {}).get(
            "containerVersionId"
        )
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
    for tag_name in created_tags:
        print(f"  - {tag_name}")
    print(f"\nCustomer.io Site ID: {CUSTOMERIO_SITE_ID}")
    print("UTM bypass: sw_email_subscriber=true cookie set when utm_medium=email")
    print("\nVerify in GTM Preview mode before relying on data.")


if __name__ == "__main__":
    main()
