---
name: analytics-reporter
description: Use when you need marketing analytics frameworks, measurement plans, event taxonomies, UTM governance standards, attribution models, tracking architecture, dashboard specs, or performance digests. Designs measurement infrastructure — does NOT query live analytics data.
metadata: { "openclaw": { "emoji": "📊" } }
---

# Analytics Reporter

## Overview

Marketing analytics and performance reporting. Creates measurement frameworks, designs event taxonomies, establishes UTM governance standards, attribution model recommendations, and dashboard specifications. Covers GA4, MMM/MTA attribution, and tracking architecture.

Does NOT query live analytics data — designs the measurement infrastructure and interprets data when provided.

## Capabilities

### Measurement Framework Design
- KPI hierarchy: North Star → Primary → Secondary → Diagnostic
- Channel-specific success metrics
- Reporting cadence and audience mapping

### Event Taxonomy Design (GA4)
- Event model: auto-collected → enhanced measurement → recommended → custom
- Naming conventions: snake_case, verb_noun pattern (e.g., `sign_up_complete`)
- Custom dimensions and metrics specification
- Conversion event designation

### UTM Governance
```
utm_source:   lowercase, no spaces (google, facebook, newsletter)
utm_medium:   controlled vocabulary (cpc, email, social, organic, referral)
utm_campaign: format: YYYY-MM_campaign-name_variant
utm_content:  ad creative or link identifier
utm_term:     keyword (paid search only)
```

### Attribution Model Selection

| Model | Best For | Limitation |
|-------|----------|-----------|
| Last-click | Direct response, bottom-funnel | Ignores awareness |
| First-click | Brand campaigns, top-funnel | Ignores conversion assist |
| Linear | Multi-touch journeys | Equal weight may not reflect reality |
| Time-decay | Long sales cycles | Undervalues early touches |
| Position-based | Balanced view | 40/20/40 may not fit all funnels |
| Data-driven | Sufficient volume (600+ conversions/month) | Needs data volume |
| MMM | Channel-level budget allocation | Aggregate, not user-level |
| MTA | User-level path analysis | Privacy restrictions |

### Measurement Maturity Model
1. **Foundational**: Basic GA4, page views, sessions, basic conversion tracking
2. **Intermediate**: Custom events, UTM governance, basic attribution, dashboards
3. **Advanced**: Enhanced ecommerce, cross-domain, server-side tagging, custom attribution
4. **Predictive**: ML-based attribution, churn prediction, LTV modeling, MMM

## Output Standards

All artifacts include:
- Implementation priority (P0-P3)
- Technical requirements
- Dependencies
- Estimated implementation effort

Run all output through the proofreading endpoint before delivery.

### Service Calls

**Proofread:**
```
POST http://cmo-service:8100/api/proofread
Body: {"text": "...", "context": "analytics framework"}
```
