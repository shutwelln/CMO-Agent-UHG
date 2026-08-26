---
name: app-api
description: Customer.io App API — broadcasts, transactional messages, campaigns, segments, people search
metadata:
  tags: customerio, app-api, broadcasts, transactional, campaigns, segments
---

## App API Overview

The App API reads data **from** Customer.io and triggers actions. Use it to send transactional messages, trigger broadcasts, query campaigns/segments, and search people.

- **Base URL**: `https://api.customer.io/v1/`
- **Auth**: Bearer token — `Authorization: Bearer <app_api_key>`
- **Content-Type**: `application/json`

## Broadcasts

### Trigger a Broadcast

```
POST /v1/campaigns/{broadcast_id}/triggers
```

```json
{
  "emails": ["user@example.com"],
  "data": {
    "coupon_code": "SAVE20",
    "offer_name": "Spring Sale"
  },
  "email_add_duplicates": false,
  "email_ignore_missing": true
}
```

Can target by: `emails`, `ids`, `per_user_data` (personalized data per recipient), or `data_file_url`.

### List Broadcasts

```
GET /v1/campaigns?type=broadcast
```

### Get Broadcast Metrics

```
GET /v1/campaigns/{broadcast_id}/metrics
```

**Rate limit**: 1 request per 10 seconds for broadcast triggers.

## Transactional Messages

### Send Transactional Email

```
POST /v1/send/email
```

```json
{
  "transactional_message_id": "order_confirmation",
  "to": "user@example.com",
  "identifiers": { "id": "user-123" },
  "message_data": {
    "order_id": "ORD-456",
    "total": "$49.99",
    "items": [{"name": "Widget", "qty": 2}]
  },
  "disable_message_retention": false
}
```

### Send Transactional Push

```
POST /v1/send/push
```

### Send Transactional SMS

```
POST /v1/send/sms
```

**Rate limit**: 100 requests per second for transactional sends.

## Campaigns

```
GET /v1/campaigns                        # List all campaigns
GET /v1/campaigns/{campaign_id}          # Get campaign details
GET /v1/campaigns/{campaign_id}/metrics  # Get campaign metrics
GET /v1/campaigns/{campaign_id}/actions  # List campaign actions/messages
```

## Segments

```
GET /v1/segments                                    # List all segments
GET /v1/segments/{segment_id}                       # Get segment details
GET /v1/segments/{segment_id}/membership            # List people in segment
GET /v1/segments/{segment_id}/used_by               # What uses this segment
```

## People

### Search People

```
POST /v1/customers
```

```json
{
  "filter": {
    "and": [
      {"attribute": {"field": "plan", "operator": "eq", "value": "premium"}},
      {"segment": {"id": 5}}
    ]
  }
}
```

### Lookup by ID or Email

```
GET /v1/customers?id_type=id&id={person_id}
GET /v1/customers?id_type=email&id={email}
```

### Get Person Attributes, Events, Segments

```
GET /v1/customers/{person_id}/attributes
GET /v1/customers/{person_id}/events
GET /v1/customers/{person_id}/segments
```

## Newsletters & Exports

```
GET /v1/newsletters           # List newsletters
POST /v1/exports/customers    # Export people data
POST /v1/exports/deliveries   # Export message delivery data
GET /v1/exports/{export_id}   # Check export status
```

## Response Format

All responses are JSON. Paginated endpoints use `next` cursor:

```json
{
  "results": [...],
  "next": "cursor_token_here"
}
```

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- App API reference: `https://customer.io/docs/api/app/`
- Transactional messages: `https://customer.io/docs/api/app/#tag/Transactional`
- Broadcasts: `https://customer.io/docs/api/app/#tag/Broadcasts`
- Campaigns: `https://customer.io/docs/api/app/#tag/Campaigns`
- Segments: `https://customer.io/docs/api/app/#tag/Segments`
- People/Customers: `https://customer.io/docs/api/app/#tag/Customers`
