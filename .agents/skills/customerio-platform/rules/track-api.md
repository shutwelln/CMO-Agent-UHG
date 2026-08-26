---
name: track-api
description: Customer.io Track API — identify people, track events, batch operations, device management
metadata:
  tags: customerio, track-api, identify, events, batch
---

## Track API Overview

The Track API sends data **into** Customer.io. Use it to identify people, track events, manage devices, and send batch operations.

- **Base URL**: `https://track.customer.io/api/`
- **Auth**: Basic auth — `Authorization: Basic base64(site_id:api_key)`
- **Content-Type**: `application/json`

## v1 Endpoints

### Identify (create or update a person)

```
PUT /api/v1/customers/{identifier}
```

Body: JSON object of attributes to set. The `identifier` is the person's `id` or `email` depending on workspace settings.

```json
{
  "email": "user@example.com",
  "first_name": "Jane",
  "plan": "premium",
  "created_at": 1704067200
}
```

### Track Event

```
POST /api/v1/customers/{identifier}/events
```

```json
{
  "name": "purchase",
  "data": {
    "product_id": "abc-123",
    "price": 49.99,
    "currency": "USD"
  }
}
```

### Anonymous Event

```
POST /api/v1/events
```

Track events without tying them to a known person. Useful for pre-identification tracking.

### Delete Person

```
DELETE /api/v1/customers/{identifier}
```

### Suppress Person

```
POST /api/v1/customers/{identifier}/suppress
POST /api/v1/customers/{identifier}/unsuppress
```

Suppressed people cannot receive messages but their data is retained.

### Device Management (Mobile Push)

```
PUT /api/v1/customers/{identifier}/devices
DELETE /api/v1/customers/{identifier}/devices/{device_id}
```

Register or remove mobile devices for push notifications.

## v2 Endpoints (Recommended)

The v2 API uses a unified entity + action model for all operations.

### Single Entity Operation

```
POST /api/v2/entity
```

```json
{
  "type": "person",
  "identifiers": { "id": "user-123" },
  "action": "identify",
  "attributes": {
    "email": "user@example.com",
    "first_name": "Jane"
  }
}
```

Actions: `identify`, `track`, `delete`, `suppress`, `unsuppress`, `add_relationships`, `remove_relationships`

### Batch Operations

```
POST /api/v2/batch
```

Send up to 1000 operations in a single request. Each item follows the same type + action model.

```json
{
  "batch": [
    { "type": "person", "identifiers": {"id": "1"}, "action": "identify", "attributes": {"plan": "pro"} },
    { "type": "person", "identifiers": {"id": "1"}, "action": "track", "name": "login", "data": {} }
  ]
}
```

## Request Limits

- **Single request**: 32 KB max body size
- **Batch request**: 500 KB max body size, 1000 items max
- **Rate limits**: 100 requests/second for Track API

## Common Patterns

- **Timestamps**: Use Unix timestamps (seconds) for date attributes. Customer.io auto-detects `created_at`.
- **Nested attributes**: Supported up to 5 levels deep. Stored as JSON.
- **Reserved attributes**: `email`, `created_at`, `unsubscribed`, `cio_id` have special meaning.

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Track API overview: `https://docs.customer.io/integrations/api/track/`
- v2 Entity endpoint: `https://customer.io/docs/api/track/#operation/entity`
- v2 Batch endpoint: `https://customer.io/docs/api/track/#operation/batch`
- Rate limits: `https://docs.customer.io/integrations/api/api-limits/`
