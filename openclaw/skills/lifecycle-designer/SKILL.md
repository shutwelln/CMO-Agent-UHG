---
name: lifecycle-designer
description: Use when you need to design customer lifecycle marketing flows — email sequences, SMS drip campaigns, onboarding flows, welcome series, win-back campaigns, push notifications, or in-product messaging. Covers the full 8-stage lifecycle with event-driven segmentation, trigger logic, message frameworks, A/B test planning, and compliance per channel. Produces implementable flow specs for Customer.io, Beehiiv, or any ESP.
metadata: { "openclaw": { "emoji": "🔄" } }
---

# Lifecycle Designer

## Overview

Designs customer lifecycle marketing flows across email, SMS, push, and in-product messaging. Produces implementable flow specs with entry criteria, message sequences, branching rules, exit conditions, frequency caps, and A/B test recommendations.

## How to Use

1. **Identify lifecycle stage** — Map request to one of the 8 stages
2. **Design flow** — Entry criteria, message sequence, branching, exit conditions
3. **Create message frameworks** — Subject lines, body structure, personalization tokens
4. **Plan A/B tests** — Hypothesis, variants, statistical requirements
5. **Deliver** — Send to Slack for human approval

### Service Calls

**Load brand voice (for message tone):**
```
GET http://cmo-service:8100/api/brand-voice/{workspace_id}
```

## 8-Stage Lifecycle Framework

See `references/lifecycle-stages.md` for complete stage definitions, entry criteria, durations, and goal metrics.

| Stage | Entry Trigger | Duration | Primary Goal |
|-------|--------------|----------|-------------|
| 1. Welcome | Sign-up event | 3-7 days | Open rate >50% |
| 2. Onboarding | Welcome complete or +24h | 14-21 days | Activation within 7 days |
| 3. Activation | Key action completed | 1-2 messages | Transition to engaged |
| 4. Engagement | Activated state | Ongoing | Retention >80% at D30 |
| 5. Upsell | Usage threshold exceeded | 7-14 days | Upgrade conversion >5% |
| 6. Cross-sell | Purchase or engagement milestone | 1-2 messages | Cross-sell conversion >3% |
| 7. Win-back | No activity 30-60 days | 21-30 days | Reactivation >10% |
| 8. Churn Prevention | Risk signals detected | Immediate + follow-ups | Churn reduction >20% |

## Flow Design Structure

For each flow, produce:

**1. Entry Criteria** — Trigger event, conditions, entry frequency

**2. Message Sequence** — Step, delay, channel, subject/hook, goal

**3. Branching Rules** — IF/THEN logic for user behavior

**4. Exit Conditions** — Goal achieved, unsubscribed, duration exceeded, higher-priority flow entered

**5. Frequency Capping:**
```
max_emails_per_day: 1
max_emails_per_week: 3
max_sms_per_week: 1
max_push_per_day: 2
quiet_hours: "21:00-08:00" (user timezone)
cool_down_after_purchase: 48h
```

## Message Framework

For each message provide:
- **Subject lines** (3-5 variants ranked): Direct benefit, Curiosity, Social proof, Urgency
- **Preview text**: Complements subject, never repeats it
- **Body**: Hook → Value → Proof → CTA → PS
- **Personalization tokens**: `{{first_name}}`, `{{last_activity_date}}`, `{{savings_amount}}`
- **Compliance**: Unsubscribe link (CAN-SPAM/GDPR), physical address, SMS opt-out (TCPA)

## A/B Test Recommendations

For each flow, include at least one test:
```
Hypothesis: [If we change X, then Y will improve by Z% because...]
Variants: A=[control] vs B=[variant]
Metric: [primary metric]
Sample size: [calculated for 95% confidence, 5% MDE]
Duration: [minimum days]
```

## Integration

- Uses **content-writer** for actual message copy
- Uses **compliance-reviewer** for regulated industries
- Flow specs are platform-agnostic but include Customer.io/Beehiiv implementation notes when relevant

## References

See `references/lifecycle-stages.md` for complete 8-stage definitions with entry/exit criteria, message cadences, and benchmark metrics.
