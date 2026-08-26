---
name: overview
description: Customer.io platform concepts, entity model, authentication, and architecture
metadata:
  tags: customerio, overview, architecture, auth
---

## Three APIs

Customer.io exposes three distinct APIs:

1. **Track API** — Data in. Send people, events, and device data to Customer.io.
   - Base URL: `https://track.customer.io/api/`
   - Auth: Basic auth with Site ID (username) and API Key (password)

2. **App API** — Data out and triggers. Query people, segments, campaigns; trigger broadcasts and transactional messages.
   - Base URL: `https://api.customer.io/v1/`
   - Auth: Bearer token (App API Key from workspace settings)

3. **Pipelines API** — CDP-style data ingestion. Similar to Track API but with a Segment-compatible interface for routing data from other tools.
   - Base URL: `https://cdp.customer.io/v1/`
   - Auth: API key

## Core Entities

- **People** — Identified by `id` or `email`. Have attributes (profile data) and can receive messages. Can be identified, updated, suppressed, or deleted.
- **Objects** — Non-person entities (e.g., companies, accounts) that can have relationships to people. Useful for account-based marketing.
- **Segments** — Groups of people based on attribute conditions, event history, or manual membership. Two types: data-driven (auto-updating) and manual.
- **Campaigns** — Automated message sequences triggered by segment membership, events, dates, or API calls. Built in the visual journey builder.
- **Broadcasts** — One-time or scheduled sends to a segment. Used for announcements, newsletters, product updates.
- **Transactional Messages** — One-to-one messages triggered by API call. Used for receipts, password resets, order confirmations. Separate from marketing campaigns.

## Journeys (Visual Workflow Builder)

Journeys are the campaign workflow builder. They support:
- **Triggers**: segment entry, event received, date attribute, API call
- **Actions**: send email, send SMS, send push, send webhook, update attribute, add to segment
- **Conditions**: attribute checks, event history, segment membership, random split
- **Delays**: time-based waits, wait until condition, wait until date
- **Branching**: true/false conditions, multi-branch splits

## Authentication

- **Track API**: Basic auth — `Authorization: Basic base64(site_id:api_key)`
- **App API**: Bearer token — `Authorization: Bearer <app_api_key>`
- **API Key Scopes**: Keys can be scoped to specific permissions. Create separate keys for different integrations.

## Reporting Webhooks

Customer.io can send webhook notifications for message events: sent, delivered, opened, clicked, bounced, complained, unsubscribed. Configure in workspace settings.

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Platform overview: `https://docs.customer.io/`
- Track API reference: `https://docs.customer.io/integrations/api/track/`
- App API reference: `https://customer.io/docs/api/app/`
- Journeys overview: `https://docs.customer.io/journeys/`
- People & attributes: `https://docs.customer.io/journeys/people-overview/`
- Objects: `https://docs.customer.io/journeys/objects-overview/`
