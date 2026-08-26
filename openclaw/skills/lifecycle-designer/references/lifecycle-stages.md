# 8-Stage Lifecycle Framework — Complete Reference

## Stage 1: WELCOME
- **Purpose:** First impression, set expectations, deliver value promise
- **Entry:** Sign-up event
- **Duration:** 1-3 messages over 3-7 days
- **Goal:** Open rate >50%, click rate >15%
- **Key messages:** Welcome + value prop, quick start, expectations setting
- **Channel priority:** Email (primary), push (secondary)

## Stage 2: ONBOARDING
- **Purpose:** Guide to first value delivery (activation)
- **Entry:** Welcome complete OR 24h after signup
- **Duration:** 5-7 messages over 14-21 days
- **Goal:** Activation within 7 days
- **Key messages:** Quick start guide, feature highlights, success stories, nudges
- **Channel priority:** Email (primary), in-product (secondary), SMS (tertiary)

## Stage 3: ACTIVATION
- **Purpose:** User reaches "aha moment" — first meaningful value
- **Entry:** Key action completed (first purchase, first use, profile complete)
- **Duration:** 1-2 messages
- **Goal:** Transition to engaged state
- **Key messages:** Congratulations, next steps, deeper feature introduction
- **Channel priority:** Email + in-product

## Stage 4: ENGAGEMENT
- **Purpose:** Deepen usage, build habit
- **Entry:** Activated state
- **Duration:** Ongoing (weekly/biweekly cadence)
- **Goal:** Retention rate >80% at D30
- **Key messages:** Tips, new features, community, content digest
- **Channel priority:** Email (primary), push (secondary)

## Stage 5: UPSELL
- **Purpose:** Move to higher tier/plan
- **Entry:** Usage threshold exceeded OR time-based trigger
- **Duration:** 2-3 messages over 7-14 days
- **Goal:** Upgrade conversion rate >5%
- **Key messages:** Feature limits approaching, premium benefits, ROI calculator
- **Channel priority:** Email + in-product

## Stage 6: CROSS-SELL
- **Purpose:** Adjacent product/service recommendation
- **Entry:** Purchase event OR engagement milestone
- **Duration:** 1-2 messages
- **Goal:** Cross-sell conversion >3%
- **Key messages:** Complementary product, bundle offer, personalized recommendation
- **Channel priority:** Email

## Stage 7: WIN-BACK
- **Purpose:** Re-engage lapsed users
- **Entry:** No activity for 30-60 days (configurable)
- **Duration:** 3-5 messages over 21-30 days
- **Goal:** Reactivation rate >10%
- **Key messages:** We miss you, what's new, special offer, last chance, feedback request
- **Channel priority:** Email → SMS (if no email response)

## Stage 8: CHURN PREVENTION
- **Purpose:** Intervene before loss
- **Entry:** Risk signals (reduced usage, support complaints, downgrade intent)
- **Duration:** Immediate intervention + 2-3 follow-ups
- **Goal:** Churn reduction >20%
- **Key messages:** Personal outreach, problem resolution, exclusive offer, exit survey
- **Channel priority:** In-product → Email → SMS → Phone (escalation ladder)

---

## Branching Logic Patterns

```
IF user completed activation → EXIT flow, enter Engagement
IF user opened email 2 but no action → Send variant B (different CTA)
IF user hasn't opened any email → Switch to SMS channel
IF user unsubscribed → EXIT flow immediately
IF user entered higher-priority flow → EXIT current flow
```

## Personalization Token Reference

```
{{first_name}} — User's first name (fallback: "there")
{{company_name}} — Their company (B2B)
{{last_activity_date}} — Last engagement date
{{savings_amount}} — Calculated savings (if applicable)
{{days_since_signup}} — For onboarding progression
{{plan_name}} — Current plan/tier
{{usage_percent}} — Usage relative to limit
```
