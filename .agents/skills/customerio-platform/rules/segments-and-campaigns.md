---
name: segments-and-campaigns
description: Customer.io segments, campaigns, broadcasts, and journey design patterns
metadata:
  tags: customerio, segments, campaigns, broadcasts, journeys
---

## Segment Types

### Data-Driven Segments (Auto-Updating)

People are added/removed automatically based on conditions. Conditions can reference:

- **Attributes**: profile fields (e.g., `plan = "premium"`, `created_at < 30 days ago`)
- **Events**: event history (e.g., `performed "purchase" in last 7 days`, `did not perform "login" in last 30 days`)
- **Relationships**: object associations (e.g., `related to company where plan = "enterprise"`)
- **Other segments**: membership in other segments (nested conditions)
- **Message activity**: opened/clicked/received specific messages

Conditions support `AND`/`OR` logic with nesting.

### Manual Segments

People are added/removed explicitly via the UI, API, or CSV upload. Useful for one-off lists, exclusion lists, or imported audiences.

## Campaign Types

### Segment-Triggered Campaigns

- Triggered when a person **enters** a segment
- Most common type for lifecycle flows
- Example: person enters "Trial Started" segment → send onboarding sequence

### Event-Triggered Campaigns

- Triggered when a person performs a specific **event**
- Example: "purchase" event → send order confirmation + upsell sequence

### Date-Triggered Campaigns

- Triggered based on a **date attribute** on the person
- Example: `subscription_renewal_date` is 7 days from now → send renewal reminder

### API-Triggered Campaigns

- Triggered by an API call to the campaign's trigger endpoint
- Example: external system calls API → person enters campaign with custom data

## Broadcasts vs Campaigns

| Aspect | Campaign | Broadcast |
|--------|----------|-----------|
| Trigger | Ongoing (segment/event/date/API) | One-time or scheduled |
| Audience | People entering trigger conditions | Explicit segment at send time |
| Flow | Multi-step journey with logic | Usually single message |
| Use case | Lifecycle automation | Announcements, newsletters |
| Re-entry | People can re-enter (configurable) | One send per person per broadcast |

## Transactional Messages

Separate from campaigns/broadcasts. Key differences:
- Triggered by **direct API call** with recipient and data
- Not subject to unsubscribe preferences (receipts, password resets)
- Support email, push, and SMS
- Have their own metrics and reporting
- Created in the Transactional section, not Campaigns

## Journey Design (Visual Workflow Builder)

### Available Actions
- **Send Email/SMS/Push**: deliver a message using a template
- **Send Webhook**: POST data to an external URL
- **Update Attribute**: set/unset profile attributes
- **Add/Remove from Segment**: manual segment management
- **Create Event**: trigger an event on the person
- **Send Slack Message**: notify a Slack channel

### Available Conditions
- **Attribute check**: if attribute matches value
- **Segment membership**: if person is in segment
- **Event performed**: if person did/didn't do event in timeframe
- **Message activity**: if person opened/clicked a specific message
- **Random split**: A/B/C testing with percentage splits

### Delays
- **Time delay**: wait N minutes/hours/days
- **Wait until**: wait for a condition to become true
- **Wait until date**: wait until a specific date attribute

### Best Practices
- Use **goals** to exit people who convert before finishing the journey
- Use **exit conditions** to remove people who no longer qualify
- Use **frequency caps** to prevent message fatigue
- **Test with a small segment** before activating broadly

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- Segments overview: `https://docs.customer.io/journeys/segments/`
- Campaign types: `https://docs.customer.io/journeys/types-of-campaigns-and-broadcasts/`
- Journey builder: `https://docs.customer.io/journeys/journey-overview/`
- Transactional messages: `https://docs.customer.io/transactional/`
- Goals and exit conditions: `https://docs.customer.io/journeys/campaign-goals/`
