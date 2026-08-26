---
name: webhooks-and-events
description: Customer.io event tracking patterns, reporting webhooks, and webhook actions in journeys
metadata:
  tags: customerio, webhooks, events, tracking, reporting
---

## Event Tracking

### Named Events

Events are the primary way to track user behavior. Each event has a `name` and optional `data` properties.

```json
{
  "name": "purchase",
  "data": {
    "product_id": "abc-123",
    "price": 49.99,
    "currency": "USD",
    "category": "widgets"
  }
}
```

Common event patterns:
- **Lifecycle**: `signed_up`, `activated`, `upgraded`, `churned`
- **Commerce**: `purchase`, `add_to_cart`, `checkout_started`, `refund_requested`
- **Engagement**: `feature_used`, `page_viewed`, `search_performed`
- **Content**: `article_read`, `video_watched`, `download_completed`

### Event Best Practices

- Use **snake_case** for event names
- Include relevant context in `data` properties (IDs, amounts, categories)
- Use **timestamps** (Unix seconds) for `created_at` if backdating events
- Track **both positive and negative** signals (e.g., `subscription_cancelled` not just `subscribed`)

### Pageview Tracking

```json
{
  "name": "page",
  "data": {
    "url": "https://example.com/pricing"
  }
}
```

Pageviews are a special event type that Customer.io uses for in-app messaging targeting and web activity segments.

### Anonymous Events

Events tracked before a person is identified. When the person is later identified, anonymous events can be merged using the `anonymous_id` field.

## Reporting Webhooks (Outbound)

Customer.io sends webhook notifications for message lifecycle events. Configure in **Settings > Webhooks**.

### Event Types

| Event | Description |
|-------|-------------|
| `email_sent` | Email accepted by Customer.io for delivery |
| `email_delivered` | Email delivered to recipient's mail server |
| `email_opened` | Recipient opened the email (pixel tracking) |
| `email_clicked` | Recipient clicked a link in the email |
| `email_bounced` | Email bounced (hard or soft) |
| `email_complained` | Recipient marked email as spam |
| `email_unsubscribed` | Recipient unsubscribed |
| `sms_sent` | SMS dispatched to carrier |
| `sms_delivered` | SMS confirmed delivered |
| `sms_failed` | SMS delivery failed |
| `push_sent` | Push notification sent |
| `push_opened` | Push notification opened |

### Webhook Payload Format

```json
{
  "event_type": "email_opened",
  "timestamp": 1704067200,
  "data": {
    "customer_id": "user-123",
    "email_address": "user@example.com",
    "campaign_id": 42,
    "action_id": 7,
    "broadcast_id": null,
    "subject": "Welcome to our platform"
  }
}
```

### Reporting Webhook Setup

- Configure the destination URL in workspace settings
- Select which event types to receive
- Webhooks are sent as `POST` requests with JSON body
- Implement **idempotency** — Customer.io may retry failed deliveries
- Respond with `2xx` within 10 seconds to acknowledge receipt

## Webhook Actions in Journeys

Journeys can include webhook **actions** that POST data to external APIs during the flow.

### Configuration

- **URL**: the endpoint to call
- **Method**: POST (default)
- **Headers**: custom headers (e.g., API keys)
- **Body**: JSON template with Liquid variables

```json
{
  "customer_id": "{{ customer.id }}",
  "email": "{{ customer.email }}",
  "campaign": "onboarding_day_3",
  "event": "journey_milestone"
}
```

### Use Cases

- Sync data to external CRM when a person reaches a journey step
- Trigger an n8n workflow when a lifecycle event occurs
- Update a data warehouse with campaign engagement data
- Notify Slack when a high-value lead enters a campaign

## Webhook-Triggered Campaigns

Campaigns can be triggered by **incoming webhooks** — external systems POST JSON to a Customer.io webhook URL.

### How It Works

1. Create an API-triggered campaign
2. Customer.io provides a webhook URL
3. External system POSTs JSON with person identifier and data
4. Person enters the campaign with the provided data available as Liquid variables

### Payload Requirements

```json
{
  "identifiers": {
    "id": "user-123"
  },
  "data": {
    "order_id": "ORD-456",
    "total": 49.99
  }
}
```

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Event tracking: `https://docs.customer.io/journeys/events/`
- Reporting webhooks: `https://customer.io/docs/api/webhooks/`
- Webhook actions: `https://docs.customer.io/journeys/webhooks-action/`
- API-triggered campaigns: `https://docs.customer.io/journeys/api-triggered-campaigns/`
- Anonymous events: `https://docs.customer.io/integrations/api/track/#tag/Track-Events/operation/trackAnonymous`
