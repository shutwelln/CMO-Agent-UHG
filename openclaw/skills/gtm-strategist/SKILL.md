---
name: gtm-strategist
description: Use when you need go-to-market strategy, launch planning, market entry analysis, ICP (Ideal Customer Profile) definition, channel strategy, unit economics (CAC, LTV, payback period), beachhead selection, or risk assessment. Produces complete GTM plans with 3-phase launch sequencing and exit criteria per phase.
metadata: { "openclaw": { "emoji": "🚀" } }
---

# GTM Strategist

## Overview

Go-to-market strategy with 3-phase launch sequencing, Ideal Customer Profile (ICP) definition, channel strategy, unit economics, and risk assessment. Produces complete 7-section GTM plans with exit criteria per phase, beachhead selection, and execution briefs.

## How to Use

1. **Define ICP** — Beachhead segment, demographics, psychographics, behavior, problem, sizing
2. **Design channel strategy** — 5 categories with funnel role and CAC estimates
3. **Sequence launch** — 3-phase plan with specific exit criteria
4. **Calculate unit economics** — CAC, LTV, LTV:CAC ratio, payback period
5. **Assess risks** — Execution, channel, regulatory, operational
6. **Deliver** — Send to Slack for human review

### Service Calls

**Load brand voice (for positioning):**
```
GET http://cmo-service:8100/api/brand-voice/{workspace_id}
```

## 3-Phase GTM Launch Sequence

| Phase | Duration | Goal | Key Exit Criteria |
|-------|----------|------|-------------------|
| 1. Validation | 2-4 weeks | Prove message-market fit | ICP validated, landing page live, 50-100 signups, 2-3 channel experiments run |
| 2. Controlled Launch | 4-8 weeks | Scale with repeatable loops | CAC within 2x target, activation rate above threshold, 1+ consistent channel, D7/D30 retention validated |
| 3. Scaled Expansion | 8-16 weeks | Expand to adjacent segments | CAC at target across 2+ channels, LTV:CAC >3:1, second segment validated, revenue tracking to plan |

See `references/gtm-frameworks.md` for complete phase definitions with detailed actions.

## ICP Definition Framework

| Section | What to Define |
|---------|---------------|
| Beachhead Segment | Single most promising initial segment to dominate first |
| Demographics | Age, income, location, household, education |
| Psychographics | Values, motivations, fears/pain points, aspirations |
| Behavior | Online behavior, purchase patterns, info sources, decision process |
| The Problem | Urgent pain, current alternatives, gap we fill, why now |
| Segment Sizing | TAM, SAM, SOM with sources |
| Acquisition Signals | Where to find them, how to reach them, buying signals |

## Channel Strategy (5 Categories)

| Category | Funnel Role | Est. CAC | Priority |
|----------|-------------|----------|----------|
| Owned | Awareness → Retention | $5-20 | Highest |
| Earned | Awareness → Consideration | $0-10 | High |
| Paid | Traffic → Conversion | $15-50 | Medium |
| Partnerships | Traffic → Conversion | $10-30 | Medium |
| Direct | Lead → Customer | $50-200 | Lower |

## Unit Economics Calculator

```
CAC = Total Spend / Customers Acquired
LTV = Monthly Revenue / Monthly Churn Rate x Gross Margin
LTV:CAC Ratio = LTV / CAC
Payback Period = CAC / Monthly Gross Profit

Health Assessment:
  >= 3.0  → Healthy (sustainable growth)
  1.5-3.0 → Marginal (optimize before scaling)
  < 1.5   → Unsustainable (fix before spending more)
```

## 7-Section GTM Plan

1. **Market Definition** — ICP, problem, alternatives, timing
2. **Positioning & Narrative** — Value prop, 3 messaging pillars, competitive differentiation
3. **Channel Strategy** — 5 categories with role definitions
4. **Funnel Architecture** — Stage-by-stage with metrics
5. **Phased Rollout** — 3-phase plan with exit criteria
6. **Metrics & Economics** — CAC targets, LTV, conversion benchmarks
7. **Risk Assessment** — Execution, channel, regulatory, operational risks

## Operating Principles

1. **Beachhead First** — Dominate one segment before expanding
2. **Capital Efficient Growth** — Durable loops, not vanity reach
3. **Instrument Before Spend** — Analytics/attribution before traffic scales
4. **Message-Market Fit Before Channel Scale** — Validated positioning before aggressive paid
5. **Revenue Clarity** — Monetization mechanics defined before acceleration

## Integration

- Uses **analytics-reporter** for measurement framework alignment
- Uses **lifecycle-designer** for email flow planning
- Uses **compliance-reviewer** for regulated industries
- Uses **content-writer** for positioning copy

## References

See `references/gtm-frameworks.md` for complete 3-phase launch definitions, ICP template, and channel strategy details.
