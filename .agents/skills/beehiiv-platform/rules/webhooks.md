---
name: webhooks
description: Beehiiv webhook configuration, event types, and payload handling
metadata:
  tags: beehiiv, webhooks, events, callbacks
---

## Webhooks Overview

Beehiiv webhooks send HTTP callbacks to your endpoints when subscriber or content events occur. Use them to sync data with external systems, trigger automations, or build integrations.

## Create Webhook

```
POST /v2/publications/{publication_id}/webhooks
```

```json
{
  "url": "https://your-server.com/webhooks/beehiiv",
  "event_types": [
    "subscription.created",
    "subscription.deleted",
    "post.published"
  ]
}
```

Key fields:
- `url` (required) — The endpoint URL to receive webhook payloads
- `event_types` (required) — Array of event types to subscribe to

## List Webhooks

```
GET /v2/publications/{publication_id}/webhooks
```

## Get Webhook

```
GET /v2/publications/{publication_id}/webhooks/{webhook_id}
```

## Delete Webhook

```
DELETE /v2/publications/{publication_id}/webhooks/{webhook_id}
```

## Event Types

### Subscription Events

| Event | Description |
|-------|-------------|
| `subscription.created` | New subscriber signed up |
| `subscription.activated` | Subscription became active |
| `subscription.deleted` | Subscription was removed |
| `subscription.upgraded` | Subscriber upgraded tier |
| `subscription.downgraded` | Subscriber downgraded tier |

### Post Events

| Event | Description |
|-------|-------------|
| `post.published` | Post was published |
| `post.deleted` | Post was deleted |

## Webhook Payload Format

Webhooks are sent as `POST` requests with a JSON body:

```json
{
  "event_type": "subscription.created",
  "timestamp": "2024-01-15T10:30:00Z",
  "data": {
    "id": "sub_abc123",
    "email": "subscriber@example.com",
    "status": "active",
    "publication_id": "pub_xyz789",
    "created_at": "2024-01-15T10:30:00Z",
    "utm_source": "homepage",
    "custom_fields": {},
    "tags": []
  }
}
```

## Webhook Best Practices

- **Respond quickly**: Return a `2xx` status within a few seconds. Process payloads asynchronously if needed.
- **Idempotency**: Webhooks may be retried. Use the event ID or timestamp to deduplicate.
- **Validation**: Verify the webhook source (IP allowlisting or shared secret if supported).
- **Error handling**: Log failed webhook processing for debugging. Beehiiv will retry on non-2xx responses.

## Common Integration Patterns

- **Subscriber sync**: On `subscription.created`, add subscriber to Customer.io or CRM
- **Content distribution**: On `post.published`, share to social media or notify Slack
- **Churn tracking**: On `subscription.deleted`, trigger win-back automation in Customer.io
- **Analytics**: Track subscription events in your data warehouse

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Create webhook: `https://developers.beehiiv.com/api-reference/webhooks/create`
- List webhooks: `https://developers.beehiiv.com/api-reference/webhooks/index`
- Get webhook: `https://developers.beehiiv.com/api-reference/webhooks/show`
- Delete webhook: `https://developers.beehiiv.com/api-reference/webhooks/destroy`
