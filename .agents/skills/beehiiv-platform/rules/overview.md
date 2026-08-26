---
name: overview
description: Beehiiv platform concepts, entity model, authentication, and API architecture
metadata:
  tags: beehiiv, overview, architecture, auth, api
---

## API Overview

Beehiiv provides a single REST API (v2) for managing publications, subscriptions, posts, and related resources.

- **Base URL**: `https://api.beehiiv.com/v2/`
- **Auth**: Bearer token — `Authorization: Bearer <api_key>`
- **Content-Type**: `application/json`
- **Pagination**: Cursor-based for list endpoints (returns `next_cursor` and `has_more`)
- **Rate limiting**: Varies by plan

## Authentication

API keys are created in **Settings > Integrations > API** within the Beehiiv dashboard. Each key is scoped to a specific publication.

```
Authorization: Bearer <api_key>
```

## Core Entities

- **Publications** — The top-level entity. Each publication is an independent newsletter with its own subscribers, posts, and settings. Most API endpoints are scoped under `/publications/{publication_id}/`.

- **Subscriptions** — Subscriber records within a publication. Each subscription has an email, status, UTM data, custom fields, and tags. Statuses: `active`, `inactive`, `pending`.

- **Posts** — Newsletter content. Posts can be drafted, confirmed (published), or archived. Posts are the primary content unit sent to subscribers.

- **Segments** — Filtered groups of subscribers based on conditions (engagement, custom fields, tags, etc.). Used for targeted sends.

- **Custom Fields** — Key-value pairs on subscriptions for subscriber enrichment and segmentation. Defined per publication.

- **Tags** — Labels applied to subscriptions for organization and filtering. Simpler than custom fields — just a string label.

- **Automations** — Workflow sequences triggered by subscriber events (signup, tag added, etc.). Support delays and conditions.

- **Tiers** — Subscription levels (e.g., free, premium). Used for gating content and managing paid subscriptions.

- **Referral Program** — Built-in referral system where subscribers earn rewards for referring others.

- **Webhooks** — HTTP callbacks for subscriber and post events.

## Common URL Patterns

All resource endpoints follow this pattern:

```
GET    /v2/publications/{pub_id}/{resource}           # List
POST   /v2/publications/{pub_id}/{resource}           # Create
GET    /v2/publications/{pub_id}/{resource}/{id}      # Get by ID
PATCH  /v2/publications/{pub_id}/{resource}/{id}      # Update
DELETE /v2/publications/{pub_id}/{resource}/{id}      # Delete
```

## Pagination Pattern

```json
{
  "data": [...],
  "page": 1,
  "limit": 10,
  "total_results": 150,
  "total_pages": 15
}
```

Some endpoints use cursor-based pagination instead:

```json
{
  "data": [...],
  "next_cursor": "cursor_token",
  "has_more": true
}
```

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Getting started: `https://developers.beehiiv.com/welcome/getting-started`
- Authentication: `https://developers.beehiiv.com/welcome/authentication`
- Publications: `https://developers.beehiiv.com/api-reference/publications/index`
- Rate limits: `https://developers.beehiiv.com/welcome/rate-limiting`
