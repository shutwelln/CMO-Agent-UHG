---
name: segments-and-automations
description: Beehiiv segments, automation journeys, custom fields, tags, tiers, and referral programs
metadata:
  tags: beehiiv, segments, automations, custom-fields, tags, tiers
---

## Segments

Segments are filtered groups of subscribers used for targeted sends and analysis.

### List Segments

```
GET /v2/publications/{publication_id}/segments
```

Query parameters:
- `limit` — Results per page
- `page` — Page number

### Get Segment

```
GET /v2/publications/{publication_id}/segments/{segment_id}
```

### Expand Segment Results

```
GET /v2/publications/{publication_id}/segments/{segment_id}/results
```

Returns the subscribers that match the segment conditions.

Segments are defined through the Beehiiv web UI with conditions based on:
- Subscription status and tier
- Custom field values
- Tag membership
- Engagement metrics (opens, clicks)
- Sign-up date and source
- Referral activity

## Automation Journeys

Automations are multi-step workflows triggered by subscriber events.

### Add Subscription to Automation

```
POST /v2/publications/{publication_id}/automation_journeys/{automation_id}/subscriptions
```

```json
{
  "subscription_id": "sub_abc123"
}
```

This manually enrolls a subscriber into an automation flow.

### Common Automation Triggers (configured in UI)

- Subscriber signs up
- Tag is added/removed
- Custom field changes
- Referral milestone reached
- Manual API enrollment

### Automation Steps (configured in UI)

- Send email
- Wait/delay
- Add/remove tag
- Update custom field
- Branch/condition

## Custom Fields

Custom fields store key-value data on subscriptions for enrichment and segmentation.

### List Custom Fields

```
GET /v2/publications/{publication_id}/custom_fields
```

### Get Custom Field

```
GET /v2/publications/{publication_id}/custom_fields/{custom_field_id}
```

### Create Custom Field

```
POST /v2/publications/{publication_id}/custom_fields
```

```json
{
  "name": "company_size",
  "display_name": "Company Size"
}
```

### Update Custom Field

```
PATCH /v2/publications/{publication_id}/custom_fields/{custom_field_id}
```

Custom fields are set on individual subscriptions via the Subscriptions API:

```json
{
  "custom_fields": [
    { "name": "company_size", "value": "50-200" }
  ]
}
```

## Tags

Tags are string labels applied to subscriptions for lightweight categorization.

### Managing Tags via Subscriptions API

Add tags when creating a subscription:
```json
{ "tags": ["vip", "beta-tester"] }
```

Update tags on an existing subscription:
```json
{
  "tags_to_add": ["premium-trial"],
  "tags_to_remove": ["free-user"]
}
```

Tags are simpler than custom fields — use tags for boolean-style labels and custom fields for key-value data.

## Tiers

Tiers represent subscription levels (e.g., free, premium).

### List Tiers

```
GET /v2/publications/{publication_id}/tiers
```

### Get Tier

```
GET /v2/publications/{publication_id}/tiers/{tier_id}
```

Tiers control content access — posts can be gated to specific tiers. Manage tier assignments through the Beehiiv dashboard or subscription updates.

## Referral Program

Beehiiv's built-in referral system allows subscribers to earn rewards for referring others.

### Get Referral Program

```
GET /v2/publications/{publication_id}/referral_program
```

Returns program configuration, milestones, and reward details.

Referral data for individual subscribers is available via the Subscriptions API with `expand[]=referral_program`.

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Segments: `https://developers.beehiiv.com/api-reference/segments/index`
- Automation journeys: `https://developers.beehiiv.com/api-reference/automation-journeys/create`
- Custom fields: `https://developers.beehiiv.com/api-reference/custom-fields/index`
- Tiers: `https://developers.beehiiv.com/api-reference/email-tiers/index`
- Referral program: `https://developers.beehiiv.com/api-reference/referral-program/show`
