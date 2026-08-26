---
name: subscriptions-api
description: Beehiiv Subscriptions API — subscriber management, CRUD operations, bulk operations, custom fields
metadata:
  tags: beehiiv, subscriptions, subscribers, api
---

## Subscriptions Overview

Subscriptions represent subscriber records within a publication. Each subscription has an email, status, metadata, custom fields, and tags.

## List Subscriptions

```
GET /v2/publications/{publication_id}/subscriptions
```

Query parameters:
- `email` — Filter by exact email address
- `status` — Filter by status: `active`, `inactive`, `pending`, `all`
- `tier` — Filter by tier: `free`, `premium`
- `limit` — Results per page (default: 10, max: 100)
- `page` — Page number (1-based)
- `order_by` — Sort field: `created`, `email`
- `direction` — Sort direction: `asc`, `desc`
- `expand[]` — Include related data: `stats`, `custom_fields`, `referral_program`

## Create Subscription

```
POST /v2/publications/{publication_id}/subscriptions
```

```json
{
  "email": "subscriber@example.com",
  "reactivate_existing": false,
  "send_welcome_email": true,
  "utm_source": "api",
  "utm_medium": "integration",
  "utm_campaign": "lifecycle_import",
  "referring_site": "https://example.com",
  "custom_fields": [
    { "name": "company", "value": "Acme Inc" },
    { "name": "plan_tier", "value": "enterprise" }
  ],
  "tags": ["vip", "imported"]
}
```

Key fields:
- `email` (required) — Subscriber email address
- `reactivate_existing` — If true, reactivates an inactive subscription with the same email
- `send_welcome_email` — Whether to send the publication's welcome email
- `utm_source`, `utm_medium`, `utm_campaign` — UTM attribution
- `referring_site` — URL of the referring site
- `custom_fields` — Array of `{name, value}` pairs
- `tags` — Array of tag strings to apply

## Get Subscription

### By ID

```
GET /v2/publications/{publication_id}/subscriptions/{subscription_id}
```

### By Email

```
GET /v2/publications/{publication_id}/subscriptions?email=subscriber@example.com
```

Expand options: `expand[]=stats&expand[]=custom_fields&expand[]=referral_program`

## Update Subscription

```
PATCH /v2/publications/{publication_id}/subscriptions/{subscription_id}
```

```json
{
  "unsubscribe": false,
  "custom_fields": [
    { "name": "company", "value": "New Company" }
  ],
  "tags_to_add": ["premium-trial"],
  "tags_to_remove": ["free-user"]
}
```

Updatable fields:
- `unsubscribe` — Set to `true` to unsubscribe
- `custom_fields` — Update custom field values
- `tags_to_add` — Tags to add
- `tags_to_remove` — Tags to remove

## Bulk Operations

### Bulk Create Subscriptions

```
POST /v2/publications/{publication_id}/subscriptions/bulk
```

```json
{
  "subscriptions": [
    { "email": "user1@example.com", "utm_source": "import" },
    { "email": "user2@example.com", "utm_source": "import" }
  ],
  "send_welcome_email": false
}
```

## Subscription Statuses

| Status | Description |
|--------|-------------|
| `active` | Receiving emails, fully subscribed |
| `inactive` | Unsubscribed or removed. Not receiving emails |
| `pending` | Awaiting double opt-in confirmation |

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- List subscriptions: `https://developers.beehiiv.com/api-reference/subscriptions/index`
- Create subscription: `https://developers.beehiiv.com/api-reference/subscriptions/create`
- Get subscription: `https://developers.beehiiv.com/api-reference/subscriptions/show`
- Update subscription: `https://developers.beehiiv.com/api-reference/subscriptions/update`
- Bulk create: `https://developers.beehiiv.com/api-reference/subscriptions/bulk-create`
