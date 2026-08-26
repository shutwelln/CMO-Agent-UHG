---
name: funnel-diagnostics
description: Use when you need funnel bottleneck analysis, conversion rate optimization, A/B test design, experiment prioritization, landing page optimization specs, or CRO strategy. Diagnoses where users drop off, prioritizes fixes with 5-weighted scoring, and designs experiments with statistical rigor. Vertical-agnostic — auto-detects business model.
metadata: { "openclaw": { "emoji": "🔬" } }
---

# Funnel Diagnostics

## Overview

Combines funnel bottleneck analysis with conversion experiment design. Diagnoses drop-offs, prioritizes fixes with 5-weighted scoring, designs A/B tests with statistical rigor, and produces landing page optimization specs. Vertical-agnostic — auto-detects business model and maps optimization areas accordingly.

## Capabilities

- **Funnel audit** — 5-stage analysis with benchmarks and gap identification
- **Experiment design** — Hypothesis-driven with 9 required fields
- **Landing page optimization** — Copy, layout, trust signals, CTA recommendations
- **Experiment results analysis** — Statistical validation, durability assessment, SHIP/ITERATE/KILL verdict
- **Prioritization** — 5-weighted scoring for experiment backlog

## Vertical-Agnostic Discovery

Auto-detect business model → map optimization areas:

| Vertical | Key Conversion Events | Unique Areas |
|----------|---------------------|-------------|
| SaaS | Trial, activation, upgrade | Free-to-paid, onboarding friction, pricing |
| Ecommerce | Cart, checkout, purchase | Cart abandonment, product pages, checkout |
| Marketplace | Buyer/seller signup, first transaction | Two-sided activation, trust signals |
| B2B | Form fill, demo request, proposal | Form optimization, social proof |
| Fintech | Account open, first deposit | KYC friction, trust, security messaging |
| Nonprofit | Donate, volunteer, share | Donation form, impact messaging, recurring giving |

## 5-Stage Funnel Audit

```
AWARENESS → TRAFFIC → LEAD → CUSTOMER → REVENUE

Per transition:
1. Current conversion rate
2. Benchmark rate (industry average)
3. Gap analysis (current vs. benchmark)
4. Top 3 likely causes of drop-off
5. Recommended tests (ordered by impact)
```

## 5-Weighted Experiment Prioritization

```
Score = (Impact x 0.30) + (Confidence x 0.20) + (Traffic x 0.15) + (Ease x 0.15) + (Revenue Upside x 0.20)
```

| Dimension | Weight | Scale | Description |
|-----------|--------|-------|-------------|
| Impact | 30% | 1-10 | Expected lift to primary metric |
| Confidence | 20% | 1-10 | Evidence supporting hypothesis |
| Traffic | 15% | 1-10 | Available traffic for testing |
| Ease | 15% | 1-10 | Implementation simplicity (1=hard, 10=easy) |
| Revenue Upside | 20% | 1-10 | Direct revenue impact if successful |

## Experiment Design (9 Required Fields)

Every experiment must specify:
1. **Hypothesis** — If we [change], then [metric] will [improve by X%] because [rationale]
2. **Target page** — URL or page type, estimated daily visitors
3. **Primary metric** — Single metric
4. **Secondary metrics** — 2-4 supporting metrics
5. **Guardrail metrics** — Must NOT degrade (bounce rate, time on site, etc.)
6. **Expected impact** — X-Y% lift with confidence level
7. **Control vs. Variant** — Current state vs. proposed change with design rationale
8. **Statistical requirements** — MDE, confidence level (95%), power (80%), sample per variant, duration
9. **Rollout plan** — Partial → monitor → full ship / iterate / kill

## Statistical Sample Size Reference

Two-proportion z-test (two-tailed), 95% confidence, 80% power:

| Baseline Rate | 5% Lift | 10% Lift | 20% Lift |
|--------------|---------|----------|----------|
| 1% | 382,734 | 95,778 | 23,996 |
| 3% | 122,853 | 30,759 | 7,711 |
| 5% | 71,532 | 17,900 | 4,488 |
| 10% | 33,504 | 8,386 | 2,104 |

## Results Verdicts

- **SHIP** — Statistically significant, positive lift, guardrails preserved
- **ITERATE** — Promising signals but not significant, or mixed results
- **KILL** — No lift, negative impact, or guardrail violation

## References

See `references/scoring-system.md` for the full 5-weighted prioritization methodology and sample size calculator formulas.
