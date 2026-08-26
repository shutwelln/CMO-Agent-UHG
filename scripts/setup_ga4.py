#!/usr/bin/env python3
"""One-off script: Full GA4 + GTM instrumentation for Saverwell.

Creates GA4 property, custom dimensions/metrics, key events, audiences,
GTM container with all variables/triggers/tags, and populates the
EventSchemaStore. Idempotent - safe to re-run.

Usage:
    python scripts/setup_ga4.py

User involvement: Click "Allow" in browser OAuth popup (once).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

TOKEN_PATH = ROOT / "data" / "google-token.json"
ENV_PATH = ROOT / ".env"

# All scopes needed (existing + new GA4/GTM)
ALL_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/analytics.edit",
    "https://www.googleapis.com/auth/tagmanager.edit.containers",
    "https://www.googleapis.com/auth/tagmanager.publish",
]

# ── Event taxonomy ─────────────────────────────────────────────────
# 13 client-side + 1 server-side = 14 total events

CLIENT_EVENTS: List[Dict[str, Any]] = [
    {
        "name": "page_view",
        "params": {
            "page_type": "string - homepage|merchant|dma|protection|guide|other",
            "merchant_id": "string - merchant ID (merchant pages only)",
            "dma_id": "string - DMA ID (DMA pages only)",
            "content_category": "string - content category",
            "first_touch_source": "string - first-touch UTM source",
            "first_touch_medium": "string - first-touch UTM medium",
            "first_touch_campaign": "string - first-touch UTM campaign",
            "first_touch_content": "string - first-touch UTM content",
            "last_touch_source": "string - last-touch UTM source",
            "last_touch_medium": "string - last-touch UTM medium",
        },
        "where": "Every page load",
    },
    {
        "name": "discount_click",
        "params": {
            "merchant_id": "string - merchant ID",
            "discount_type": "string - discount type",
            "location": "string - store location",
        },
        "where": "Click on discount detail",
    },
    {
        "name": "affiliate_click",
        "params": {
            "merchant_id": "string - merchant ID",
            "commission_type": "string - commission type",
            "page_type": "string - page type where click occurred",
        },
        "where": "Click on affiliate link",
    },
    {
        "name": "protection_read",
        "params": {
            "article_slug": "string - article URL slug",
            "category_slug": "string - category slug",
            "reading_minutes": "number - estimated reading time",
        },
        "where": "Protection article scroll >75%",
    },
    {
        "name": "protection_share",
        "params": {
            "article_slug": "string - article URL slug",
            "share_method": "string - share method (email, facebook, twitter, copy)",
        },
        "where": "Share a protection article",
    },
    {
        "name": "guide_read",
        "params": {
            "article_slug": "string - article URL slug",
            "category_slug": "string - category slug",
            "reading_minutes": "number - estimated reading time",
            "guide_vertical": "string - guide vertical (medicare, insurance, etc.)",
        },
        "where": "Guide article scroll >75%",
    },
    {
        "name": "guide_share",
        "params": {
            "article_slug": "string - article URL slug",
            "share_method": "string - share method",
        },
        "where": "Share a guide article",
    },
    {
        "name": "share_content",
        "params": {
            "share_method": "string - share method",
            "content_type": "string - content type being shared",
        },
        "where": "Any share button click",
    },
    {
        "name": "search_query",
        "params": {
            "search_term": "string - search query text",
            "results_count": "number - number of results returned",
        },
        "where": "Site search",
    },
    {
        "name": "zip_lookup",
        "params": {
            "zip_code": "string - ZIP code entered",
            "dma_id": "string - resolved DMA ID",
        },
        "where": "ZIP code entry",
    },
    {
        "name": "scroll_depth",
        "params": {
            "page_type": "string - page type",
            "depth_percent": "number - scroll depth percentage (25, 50, 75, 100)",
        },
        "where": "25/50/75/100% scroll thresholds",
    },
    {
        "name": "store_directions",
        "params": {
            "merchant_id": "string - merchant ID",
            "store_id": "string - store location ID",
        },
        "where": "Click for directions",
    },
    {
        "name": "scam_alert_view",
        "params": {
            "alert_type": "string - scam alert type",
            "merchant": "string - merchant name",
        },
        "where": "Scam alert displayed",
    },
]

SERVER_EVENTS: List[Dict[str, Any]] = [
    {
        "name": "email_signup",
        "params": {
            "signup_source": "string - where the signup occurred",
            "zip_code": "string - user's ZIP code",
            "content_interest": "string - content that drove signup",
        },
        "where": "Form submission via n8n webhook (server-side Measurement Protocol)",
    },
]

# Custom dimensions (EVENT-scoped)
EVENT_DIMENSIONS = [
    # Behavioral
    "page_type",
    "merchant_id",
    "dma_id",
    "content_category",
    "signup_source",
    "zip_code",
    "content_interest",
    "discount_type",
    "location",
    "commission_type",
    "article_slug",
    "category_slug",
    "share_method",
    "guide_vertical",
    "content_type",
    "store_id",
    "alert_type",
    "merchant",
    "campaign_id",
    "link_type",
    # Attribution / UTM
    "first_touch_source",
    "first_touch_medium",
    "first_touch_campaign",
    "first_touch_content",
    "last_touch_source",
    "last_touch_medium",
]

# Custom dimension (USER-scoped)
USER_DIMENSIONS = [
    ("user_type", "User lifecycle stage: anonymous, subscriber, engaged"),
]

# Custom metrics (EVENT-scoped)
EVENT_METRICS = [
    ("reading_minutes", "FLOAT"),
    ("results_count", "INT"),
    ("depth_percent", "INT"),
]

# GA4 Audiences
AUDIENCES = [
    {
        "display_name": "Protection Readers",
        "description": "Users who read 2+ protection articles in 30 days",
        "membership_duration_days": 30,
        "event_name": "protection_read",
        "min_count": 2,
    },
    {
        "display_name": "Guide Readers",
        "description": "Users who read 2+ guide articles in 30 days",
        "membership_duration_days": 30,
        "event_name": "guide_read",
        "min_count": 2,
    },
    {
        "display_name": "Email Subscribers",
        "description": "Users who completed email signup",
        "membership_duration_days": 540,
        "event_name": "email_signup",
        "min_count": 1,
    },
    {
        "display_name": "High-Value Prospects",
        "description": "Users who signed up AND clicked an affiliate link",
        "membership_duration_days": 90,
        "event_name": None,  # compound - handled specially
        "min_count": None,
    },
    {
        "display_name": "Discount Seekers",
        "description": "Users who clicked 3+ discounts in 30 days",
        "membership_duration_days": 30,
        "event_name": "discount_click",
        "min_count": 3,
    },
]


def _print(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERROR] {msg}")


# ═══════════════════════════════════════════════════════════════════
# Phase A: OAuth
# ═══════════════════════════════════════════════════════════════════


def ensure_oauth_scopes() -> Any:
    """Load or re-auth OAuth token with all required scopes."""
    from google.oauth2.credentials import Credentials

    print("\n=== Phase A: OAuth Credentials ===")

    needs_reauth = False
    creds = None

    if TOKEN_PATH.exists():
        token_data = json.loads(TOKEN_PATH.read_text())
        existing_scopes = set(token_data.get("scopes", []))
        required_scopes = set(ALL_SCOPES)

        missing = required_scopes - existing_scopes
        if missing:
            _print(f"Missing scopes: {', '.join(s.split('/')[-1] for s in missing)}")
            needs_reauth = True
        else:
            _ok("All required scopes present")
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), ALL_SCOPES)

            # Refresh if expired
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request

                _print("Refreshing expired token...")
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
                _ok("Token refreshed")

            if creds.valid:
                return creds
            needs_reauth = True
    else:
        _print("No token file found")
        needs_reauth = True

    if needs_reauth:
        _print("Re-authenticating with expanded scopes...")
        _print("A browser window will open - click 'Allow' to authorize.")
        print()

        # Build client config from existing token data (no separate client_secrets.json)
        if TOKEN_PATH.exists():
            token_data = json.loads(TOKEN_PATH.read_text())
            client_id = token_data.get("client_id", "")
            client_secret = token_data.get("client_secret", "")
        else:
            raise SystemExit(
                "No existing token and no client_secrets.json. "
                "Run the Google OAuth flow manually first."
            )

        client_config = {
            "installed": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": ["http://localhost"],
            }
        }

        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(client_config, scopes=ALL_SCOPES)
        creds = flow.run_local_server(port=0, open_browser=True)

        # Save token
        TOKEN_PATH.write_text(creds.to_json())
        _ok("Token saved with all scopes")

    return creds


# ═══════════════════════════════════════════════════════════════════
# Phase B: GA4 Property
# ═══════════════════════════════════════════════════════════════════


def setup_ga4_property(creds: Any) -> Tuple[str, str, str]:
    """Create GA4 property, data stream, dimensions, metrics, key events, audiences.

    Returns (property_id, measurement_id, api_secret).
    """
    from google.analytics.admin_v1beta import (
        AnalyticsAdminServiceClient,
    )
    from google.analytics.admin_v1beta.types import (
        Account,
        CustomDimension,
        CustomMetric,
        DataRetentionSettings,
        DataStream,
        Property,
    )

    print("\n=== Phase B: GA4 Property ===")

    client = AnalyticsAdminServiceClient(credentials=creds)

    # B1: List accounts
    _print("Listing GA Analytics accounts...")
    accounts: List[Account] = list(client.list_accounts())
    if not accounts:
        raise SystemExit(
            "No Google Analytics accounts found. Create one at https://analytics.google.com"
        )

    if len(accounts) == 1:
        account = accounts[0]
        _ok(f"Using account: {account.display_name} ({account.name})")
    else:
        print("\n  Multiple accounts found:")
        for i, a in enumerate(accounts):
            print(f"    [{i}] {a.display_name} ({a.name})")
        choice = input("  Select account number: ").strip()
        account = accounts[int(choice)]

    account_name = account.name  # e.g. "accounts/123456"

    # B2: Check for existing Saverwell property
    _print("Checking for existing Saverwell property...")
    existing_property = None
    from google.analytics.admin_v1beta.types import ListPropertiesRequest

    for prop in client.list_properties(
        request=ListPropertiesRequest(filter=f"parent:{account_name}"),
    ):
        if prop.display_name == "Saverwell":
            existing_property = prop
            break

    if existing_property:
        _skip(f"Property 'Saverwell' already exists: {existing_property.name}")
        property_name = existing_property.name
    else:
        # B3: Create property
        _print("Creating GA4 property 'Saverwell'...")
        prop = client.create_property(
            property=Property(
                parent=account_name,
                display_name="Saverwell",
                currency_code="USD",
                time_zone="America/Chicago",
                industry_category="FINANCE",
            )
        )
        property_name = prop.name
        _ok(f"Property created: {property_name}")

    property_id = property_name.split("/")[-1]

    # B4: Create web data stream
    _print("Checking for existing data stream...")
    existing_stream = None
    for stream in client.list_data_streams(parent=property_name):
        if stream.type_ == DataStream.DataStreamType.WEB_DATA_STREAM:
            existing_stream = stream
            break

    if existing_stream:
        _skip(f"Data stream exists: {existing_stream.web_stream_data.measurement_id}")
        stream = existing_stream
    else:
        _print("Creating web data stream...")
        stream = client.create_data_stream(
            parent=property_name,
            data_stream=DataStream(
                type_=DataStream.DataStreamType.WEB_DATA_STREAM,
                display_name="Saverwell Web",
                web_stream_data=DataStream.WebStreamData(
                    default_uri="https://seniorsaver-protection.lovable.app",
                ),
            ),
        )
        _ok(f"Data stream created: {stream.web_stream_data.measurement_id}")

    measurement_id = stream.web_stream_data.measurement_id
    stream_name = stream.name

    # B5: Set data retention to 14 months
    _print("Setting data retention to 14 months...")
    try:
        client.update_data_retention_settings(
            data_retention_settings=DataRetentionSettings(
                name=f"{property_name}/dataRetentionSettings",
                event_data_retention=DataRetentionSettings.RetentionDuration.FOURTEEN_MONTHS,
                reset_user_data_on_new_activity=True,
            ),
            update_mask={"paths": ["event_data_retention", "reset_user_data_on_new_activity"]},
        )
        _ok("Data retention set to 14 months")
    except Exception as e:
        _err(f"Data retention: {e}")

    # B6: Enhanced measurement - disable scroll and site search
    # (We track these as custom events to avoid double-counting)
    _print("Configuring enhanced measurement...")
    try:
        em = client.get_enhanced_measurement_settings(
            name=f"{stream_name}/enhancedMeasurementSettings"
        )
        client.update_enhanced_measurement_settings(
            enhanced_measurement_settings={
                "name": f"{stream_name}/enhancedMeasurementSettings",
                "stream_enabled": True,
                "scrolls_enabled": False,
                "site_search_enabled": False,
                "outbound_clicks_enabled": em.outbound_clicks_enabled,
                "page_views_enabled": em.page_views_enabled,
                "file_downloads_enabled": em.file_downloads_enabled,
                "page_changes_enabled": em.page_changes_enabled,
                "form_interactions_enabled": em.form_interactions_enabled,
                "video_engagement_enabled": em.video_engagement_enabled,
            },
            update_mask={"paths": ["scrolls_enabled", "site_search_enabled"]},
        )
        _ok("Enhanced measurement: scroll + site search disabled (custom events used)")
    except Exception as e:
        _err(f"Enhanced measurement: {e}")

    # B7: Register EVENT-scoped custom dimensions
    _print("Registering custom dimensions (event-scoped)...")
    existing_dims = {d.parameter_name for d in client.list_custom_dimensions(parent=property_name)}

    for dim_name in EVENT_DIMENSIONS:
        if dim_name in existing_dims:
            _skip(f"  Dimension '{dim_name}' already exists")
            continue
        try:
            client.create_custom_dimension(
                parent=property_name,
                custom_dimension=CustomDimension(
                    parameter_name=dim_name,
                    display_name=dim_name.replace("_", " ").title(),
                    scope=CustomDimension.DimensionScope.EVENT,
                ),
            )
            _ok(f"  Dimension '{dim_name}' created")
        except Exception as e:
            _err(f"  Dimension '{dim_name}': {e}")

    # B8: Register USER-scoped custom dimensions
    _print("Registering custom dimensions (user-scoped)...")
    for dim_name, description in USER_DIMENSIONS:
        if dim_name in existing_dims:
            _skip(f"  Dimension '{dim_name}' already exists")
            continue
        try:
            client.create_custom_dimension(
                parent=property_name,
                custom_dimension=CustomDimension(
                    parameter_name=dim_name,
                    display_name=dim_name.replace("_", " ").title(),
                    description=description,
                    scope=CustomDimension.DimensionScope.USER,
                ),
            )
            _ok(f"  Dimension '{dim_name}' created (user-scoped)")
        except Exception as e:
            _err(f"  Dimension '{dim_name}': {e}")

    # B9: Register custom metrics
    _print("Registering custom metrics...")
    existing_metrics = {m.parameter_name for m in client.list_custom_metrics(parent=property_name)}

    metric_type_map = {
        "INT": CustomMetric.MeasurementUnit.STANDARD,
        "FLOAT": CustomMetric.MeasurementUnit.STANDARD,
    }

    for metric_name, metric_type in EVENT_METRICS:
        if metric_name in existing_metrics:
            _skip(f"  Metric '{metric_name}' already exists")
            continue
        try:
            client.create_custom_metric(
                parent=property_name,
                custom_metric=CustomMetric(
                    parameter_name=metric_name,
                    display_name=metric_name.replace("_", " ").title(),
                    scope=CustomMetric.MetricScope.EVENT,
                    measurement_unit=metric_type_map.get(
                        metric_type, CustomMetric.MeasurementUnit.STANDARD
                    ),
                ),
            )
            _ok(f"  Metric '{metric_name}' created")
        except Exception as e:
            _err(f"  Metric '{metric_name}': {e}")

    # B10: Create Measurement Protocol API secret
    _print("Creating Measurement Protocol API secret...")
    api_secret = ""
    try:
        existing_secrets = list(client.list_measurement_protocol_secrets(parent=stream_name))
        sw_secret = None
        for s in existing_secrets:
            if s.display_name == "Saverwell GA4 Setup":
                sw_secret = s
                break

        if sw_secret:
            api_secret = sw_secret.secret_value
            _skip("MP secret already exists")
        else:
            from google.analytics.admin_v1beta.types import MeasurementProtocolSecret

            secret = client.create_measurement_protocol_secret(
                parent=stream_name,
                measurement_protocol_secret=MeasurementProtocolSecret(
                    display_name="Saverwell GA4 Setup",
                ),
            )
            api_secret = secret.secret_value
            _ok("MP API secret created")
    except Exception as e:
        _err(f"MP secret: {e}")

    # B11: Mark key events with conversion values
    _print("Marking key events...")
    key_events = [
        ("email_signup", 1.20),
        ("affiliate_click", 0.25),
    ]
    for event_name, value in key_events:
        try:
            from google.analytics.admin_v1beta.types import KeyEvent

            client.create_key_event(
                parent=property_name,
                key_event=KeyEvent(
                    event_name=event_name,
                    counting_method=KeyEvent.CountingMethod.ONCE_PER_EVENT,
                    default_value=KeyEvent.DefaultValue(
                        currency_code="USD",
                        numeric_value=value,
                    ),
                ),
            )
            _ok(f"  Key event '{event_name}' = ${value:.2f}")
        except Exception as e:
            if "ALREADY_EXISTS" in str(e) or "already exists" in str(e).lower():
                _skip(f"  Key event '{event_name}' already exists")
            else:
                _err(f"  Key event '{event_name}': {e}")

    # B12: Enable BigQuery export
    _print("BigQuery export...")
    _print("  Note: BigQuery linking requires setup in GA4 UI > Admin > BigQuery Links")
    _print("  The daily export is free and accumulates raw event data for MMM/MTA modeling.")
    _print("  Set this up manually: GA4 > Admin > Product Links > BigQuery")

    # B13: Create audiences
    _print("Creating GA4 audiences...")
    _print("  Note: Audience creation requires the GA4 Admin API v1alpha (not beta).")
    _print("  The 5 audience definitions are documented in the GTM strategy.")
    _print("  Create them manually in GA4 > Admin > Audiences, or wait for API v1alpha GA release:")
    for aud in AUDIENCES:
        _print(f"    - {aud['display_name']}: {aud['description']}")

    # B14: Populate EventSchemaStore
    _print("Populating EventSchemaStore...")
    from cmo_agent.experiments.events import EventDefinition, EventSchemaStore

    store = EventSchemaStore(base_dir=str(ROOT / "data" / "analytics"))
    count = 0

    for event in CLIENT_EVENTS + SERVER_EVENTS:
        store.define(
            EventDefinition(
                event_name=event["name"],
                workspace_id="saverwell",
                properties=event["params"],
                owner="GA4 Setup Script",
                where_fired=event["where"],
                notes="Client-side via GTM dataLayer"
                if event in CLIENT_EVENTS
                else "Server-side via n8n Measurement Protocol",
            )
        )
        count += 1

    _ok(f"EventSchemaStore populated with {count} event definitions")

    return property_id, measurement_id, api_secret


# ═══════════════════════════════════════════════════════════════════
# Phase C: GTM Container
# ═══════════════════════════════════════════════════════════════════


def setup_gtm_container(creds: Any, measurement_id: str) -> Tuple[str, str]:
    """Create GTM container with all variables, triggers, and tags.

    Returns (container_id, gtm_snippet).
    """
    from googleapiclient.discovery import build

    print("\n=== Phase C: GTM Container ===")

    service = build("tagmanager", "v2", credentials=creds)

    # C1: List GTM accounts
    _print("Listing GTM accounts...")
    result = service.accounts().list().execute()
    accounts = result.get("account", [])

    if not accounts:
        _print("No GTM accounts found. Creating one...")
        # GTM account creation isn't available via API - need manual setup
        raise SystemExit(
            "No GTM accounts found. Create one at https://tagmanager.google.com "
            "then re-run this script."
        )

    if len(accounts) == 1:
        gtm_account = accounts[0]
        _ok(f"Using GTM account: {gtm_account['name']}")
    else:
        print("\n  Multiple GTM accounts found:")
        for i, a in enumerate(accounts):
            print(f"    [{i}] {a['name']} ({a['accountId']})")
        choice = input("  Select account number: ").strip()
        gtm_account = accounts[int(choice)]

    account_path = gtm_account["path"]  # e.g. "accounts/123456"

    # C2: Check for existing container
    _print("Checking for existing 'Saverwell - GA4' container...")
    containers = (
        service.accounts().containers().list(parent=account_path).execute().get("container", [])
    )

    existing_container = None
    for c in containers:
        if c["name"] == "Saverwell - GA4":
            existing_container = c
            break

    if existing_container:
        container = existing_container
        _skip(f"Container 'Saverwell - GA4' already exists: {container['containerId']}")
    else:
        # C3: Create container
        _print("Creating GTM container 'Saverwell - GA4'...")
        container = (
            service.accounts()
            .containers()
            .create(
                parent=account_path,
                body={
                    "name": "Saverwell - GA4",
                    "usageContext": ["web"],
                },
            )
            .execute()
        )
        _ok(f"Container created: {container['containerId']}")

    container_path = container["path"]
    container_id = container["containerId"]
    public_id = container.get("publicId", f"GTM-{container_id}")

    # Get default workspace
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
    _ok(f"Using workspace: {workspace['name']}")

    # ── Helper: check existing entities ────────────────────────────
    def _list_existing(entity_type: str) -> Dict[str, Any]:
        """List existing entities in workspace, keyed by name."""
        method = getattr(service.accounts().containers().workspaces(), entity_type)
        try:
            items = method().list(parent=workspace_path).execute().get(entity_type[:-1], [])
            # Handle pluralization: "variables" -> item list, "triggers" -> item list
            if not items:
                # Try alternate key names
                alt_key = entity_type.rstrip("s")
                items = method().list(parent=workspace_path).execute().get(alt_key, [])
                if not items:
                    items = []
        except Exception:
            items = []
        return {item["name"]: item for item in items}

    existing_vars = _list_existing("variables")
    existing_triggers = _list_existing("triggers")
    existing_tags = _list_existing("tags")

    # ── C4a: Variables ─────────────────────────────────────────────
    _print("Creating GTM variables...")

    def create_variable(name: str, var_type: str, parameter: List[Dict]) -> Optional[str]:
        if name in existing_vars:
            _skip(f"  Variable '{name}' exists")
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
                        "type": var_type,
                        "parameter": parameter,
                    },
                )
                .execute()
            )
            _ok(f"  Variable '{name}' created")
            time.sleep(2)  # GTM API rate limit: ~30 req/min
            return v.get("variableId")
        except Exception as e:
            _err(f"  Variable '{name}': {e}")
            return None

    # Constant: GA4 Measurement ID
    create_variable(
        "GA4 Measurement ID",
        "c",  # Constant
        [{"type": "template", "key": "value", "value": measurement_id}],
    )

    # DataLayer Variables - behavioral params
    dlv_params = [
        "page_type",
        "merchant_id",
        "dma_id",
        "content_category",
        "signup_source",
        "zip_code",
        "content_interest",
        "discount_type",
        "location",
        "commission_type",
        "article_slug",
        "category_slug",
        "share_method",
        "guide_vertical",
        "content_type",
        "store_id",
        "alert_type",
        "merchant",
        "search_term",
        "reading_minutes",
        "results_count",
        "depth_percent",
    ]

    for param in dlv_params:
        create_variable(
            f"DLV - {param}",
            "v",  # DataLayer Variable
            [
                {"type": "template", "key": "name", "value": param},
                {"type": "integer", "key": "dataLayerVersion", "value": "2"},
            ],
        )

    # DataLayer Variables - attribution
    attribution_params = [
        "first_touch_source",
        "first_touch_medium",
        "first_touch_campaign",
        "first_touch_content",
        "last_touch_source",
        "last_touch_medium",
    ]

    for param in attribution_params:
        create_variable(
            f"DLV - {param}",
            "v",
            [
                {"type": "template", "key": "name", "value": param},
                {"type": "integer", "key": "dataLayerVersion", "value": "2"},
            ],
        )

    # ── C4b: Triggers ──────────────────────────────────────────────
    _print("Creating GTM triggers...")

    trigger_ids: Dict[str, str] = {}

    def create_trigger(name: str, event_name: str) -> Optional[str]:
        if name in existing_triggers:
            _skip(f"  Trigger '{name}' exists")
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
            _ok(f"  Trigger '{name}' created")
            time.sleep(2)  # GTM API rate limit
            return tid
        except Exception as e:
            _err(f"  Trigger '{name}': {e}")
            return None

    trigger_events = [
        ("CE - page_view", "page_view"),
        ("CE - discount_click", "discount_click"),
        ("CE - affiliate_click", "affiliate_click"),
        ("CE - protection_read", "protection_read"),
        ("CE - protection_share", "protection_share"),
        ("CE - guide_read", "guide_read"),
        ("CE - guide_share", "guide_share"),
        ("CE - share_content", "share_content"),
        ("CE - search_query", "search_query"),
        ("CE - zip_lookup", "zip_lookup"),
        ("CE - scroll_depth", "scroll_depth"),
        ("CE - store_directions", "store_directions"),
        ("CE - scam_alert_view", "scam_alert_view"),
    ]

    for trigger_name, event_name in trigger_events:
        create_trigger(trigger_name, event_name)

    # ── C4c: Tags ──────────────────────────────────────────────────
    _print("Creating GTM tags...")

    def _param_map(params: List[Tuple[str, str]]) -> List[Dict]:
        """Build GA4 event parameter map for a tag."""
        param_list = []
        for param_name, var_name in params:
            param_list.append(
                {
                    "type": "map",
                    "map": [
                        {"type": "template", "key": "name", "value": param_name},
                        {"type": "template", "key": "value", "value": f"{{{{DLV - {var_name}}}}}"},
                    ],
                }
            )
        return param_list

    def create_tag(
        name: str,
        tag_type: str,
        parameter: List[Dict],
        firing_trigger_id: List[str],
        priority: Optional[int] = None,
    ) -> Optional[str]:
        if name in existing_tags:
            _skip(f"  Tag '{name}' exists")
            return existing_tags[name].get("tagId")
        body: Dict[str, Any] = {
            "name": name,
            "type": tag_type,
            "parameter": parameter,
            "firingTriggerId": firing_trigger_id,
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
            _ok(f"  Tag '{name}' created")
            time.sleep(2)  # GTM API rate limit
            return t.get("tagId")
        except Exception as e:
            _err(f"  Tag '{name}': {e}")
            return None

    # GA4 Configuration tag - fires on All Pages (built-in trigger ID "2147479553")
    all_pages_trigger = "2147479553"
    create_tag(
        "GA4 Configuration",
        "gaawc",
        [
            {"type": "template", "key": "measurementId", "value": "{{GA4 Measurement ID}}"},
        ],
        [all_pages_trigger],
    )

    # Event tags - each maps specific DLV parameters
    event_tag_configs = [
        (
            "GA4 - page_view",
            "page_view",
            [
                ("page_type", "page_type"),
                ("merchant_id", "merchant_id"),
                ("dma_id", "dma_id"),
                ("content_category", "content_category"),
                ("first_touch_source", "first_touch_source"),
                ("first_touch_medium", "first_touch_medium"),
                ("first_touch_campaign", "first_touch_campaign"),
                ("first_touch_content", "first_touch_content"),
                ("last_touch_source", "last_touch_source"),
                ("last_touch_medium", "last_touch_medium"),
            ],
            None,
        ),
        (
            "GA4 - discount_click",
            "discount_click",
            [
                ("merchant_id", "merchant_id"),
                ("discount_type", "discount_type"),
                ("location", "location"),
            ],
            None,
        ),
        (
            "GA4 - affiliate_click",
            "affiliate_click",
            [
                ("merchant_id", "merchant_id"),
                ("commission_type", "commission_type"),
                ("page_type", "page_type"),
            ],
            100,  # high priority - user navigates away
        ),
        (
            "GA4 - protection_read",
            "protection_read",
            [
                ("article_slug", "article_slug"),
                ("category_slug", "category_slug"),
                ("reading_minutes", "reading_minutes"),
            ],
            None,
        ),
        (
            "GA4 - protection_share",
            "protection_share",
            [
                ("article_slug", "article_slug"),
                ("share_method", "share_method"),
            ],
            None,
        ),
        (
            "GA4 - guide_read",
            "guide_read",
            [
                ("article_slug", "article_slug"),
                ("category_slug", "category_slug"),
                ("reading_minutes", "reading_minutes"),
                ("guide_vertical", "guide_vertical"),
            ],
            None,
        ),
        (
            "GA4 - guide_share",
            "guide_share",
            [
                ("article_slug", "article_slug"),
                ("share_method", "share_method"),
            ],
            None,
        ),
        (
            "GA4 - share_content",
            "share_content",
            [
                ("share_method", "share_method"),
                ("content_type", "content_type"),
            ],
            None,
        ),
        (
            "GA4 - search_query",
            "search_query",
            [
                ("search_term", "search_term"),
                ("results_count", "results_count"),
            ],
            None,
        ),
        (
            "GA4 - zip_lookup",
            "zip_lookup",
            [
                ("zip_code", "zip_code"),
                ("dma_id", "dma_id"),
            ],
            None,
        ),
        (
            "GA4 - scroll_depth",
            "scroll_depth",
            [
                ("page_type", "page_type"),
                ("depth_percent", "depth_percent"),
            ],
            None,
        ),
        (
            "GA4 - store_directions",
            "store_directions",
            [
                ("merchant_id", "merchant_id"),
                ("store_id", "store_id"),
            ],
            None,
        ),
        (
            "GA4 - scam_alert_view",
            "scam_alert_view",
            [
                ("alert_type", "alert_type"),
                ("merchant", "merchant"),
            ],
            None,
        ),
    ]

    for tag_name, event_name, params, priority in event_tag_configs:
        tid = trigger_ids.get(event_name, "")
        if not tid:
            _err(f"  Tag '{tag_name}': no trigger ID for '{event_name}'")
            continue

        tag_params = [
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

        create_tag(tag_name, "gaawe", tag_params, [tid], priority)

    # C5: Create version and publish
    _print("Creating container version...")
    try:
        version = (
            service.accounts()
            .containers()
            .workspaces()
            .create_version(
                path=workspace_path,
                body={
                    "name": "GA4 Full Instrumentation",
                    "notes": "14 events, 28 DLVs, 13 triggers",
                },
            )
            .execute()
        )

        version_id = version.get("containerVersion", {}).get("containerVersionId")
        if version_id:
            _ok(f"Version created: {version_id}")

            _print("Publishing container...")
            service.accounts().containers().versions().publish(
                path=f"{container_path}/versions/{version_id}"
            ).execute()
            _ok("Container published!")
        else:
            _err("Version creation returned no version ID")
    except Exception as e:
        _err(f"Version/publish: {e}")
        _print("You can publish manually in GTM UI")

    # C6: Build GTM snippet
    gtm_snippet = f"""<!-- Google Tag Manager -->
<script>(function(w,d,s,l,i){{w[l]=w[l]||[];w[l].push({{'gtm.start':
new Date().getTime(),event:'gtm.js'}});var f=d.getElementsByTagName(s)[0],
j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=
'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);
}})(window,document,'script','dataLayer','{public_id}');</script>
<!-- End Google Tag Manager -->"""

    noscript_snippet = f"""<!-- Google Tag Manager (noscript) -->
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={public_id}"
height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>
<!-- End Google Tag Manager (noscript) -->"""

    return container_id, public_id, gtm_snippet, noscript_snippet


# ═══════════════════════════════════════════════════════════════════
# Phase D: Finalize
# ═══════════════════════════════════════════════════════════════════


def update_env(
    property_id: str,
    measurement_id: str,
    api_secret: str,
    container_id: str,
) -> None:
    """Append GA4/GTM values to .env file."""
    print("\n=== Phase D: Finalize ===")

    env_content = ENV_PATH.read_text() if ENV_PATH.exists() else ""

    additions = []
    env_vars = {
        "GA4_PROPERTY_ID": property_id,
        "GA4_MEASUREMENT_ID": measurement_id,
        "GA4_API_SECRET": api_secret,
        "GTM_CONTAINER_ID": container_id,
    }

    for key, value in env_vars.items():
        if f"{key}=" in env_content:
            _skip(f"  {key} already in .env")
        else:
            additions.append(f"{key}={value}")

    if additions:
        with open(ENV_PATH, "a") as f:
            f.write("\n# GA4 Analytics (auto-generated by setup_ga4.py)\n")
            for line in additions:
                f.write(f"{line}\n")
        _ok(f"Added {len(additions)} values to .env")
    else:
        _skip("All GA4/GTM values already in .env")


def print_instructions(
    measurement_id: str,
    gtm_snippet: str,
    noscript_snippet: str,
) -> None:
    """Print paste-into-Lovable instructions."""
    print("\n" + "=" * 60)
    print("SETUP COMPLETE - 2 things to paste into Lovable:")
    print("=" * 60)

    print("\n1. GTM SNIPPET - Paste into Lovable's <head> custom code:\n")
    print(gtm_snippet)

    print("\n2. GTM NOSCRIPT - Paste right after opening <body> tag:\n")
    print(noscript_snippet)

    print("\n3. DATALAYER JS - Copy the contents of:")
    print("   data/saverwell/ga4_datalayer.js")
    print("   and paste into Lovable's custom scripts section.")

    print(f"\nGA4 Measurement ID: {measurement_id}")
    print("\nVerification steps:")
    print("  1. Open GTM Preview mode at https://tagmanager.google.com")
    print("  2. Load your Lovable site")
    print("  3. Verify GA4 Configuration tag fires on page load")
    print("  4. Open GA4 Realtime report to confirm events arrive")
    print("=" * 60)


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main() -> None:
    print("Saverwell GA4 + GTM Full Instrumentation Setup")
    print("=" * 50)

    # Phase A: OAuth
    creds = ensure_oauth_scopes()

    # Phase B: GA4
    property_id, measurement_id, api_secret = setup_ga4_property(creds)

    # Phase C: GTM
    container_id, public_id, gtm_snippet, noscript_snippet = setup_gtm_container(
        creds, measurement_id
    )

    # Phase D: Finalize
    update_env(property_id, measurement_id, api_secret, container_id)
    print_instructions(measurement_id, gtm_snippet, noscript_snippet)


if __name__ == "__main__":
    main()
