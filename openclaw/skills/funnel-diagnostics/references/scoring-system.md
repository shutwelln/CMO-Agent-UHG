# 5-Weighted Experiment Prioritization — Full Reference

## Scoring Formula

```
Score = (Impact x 0.30) + (Confidence x 0.20) + (Traffic x 0.15) + (Ease x 0.15) + (Revenue Upside x 0.20)
```

### Dimension Details

**Impact (30%)**
- 1-2: Cosmetic change, no measurable effect expected
- 3-4: Minor improvement to secondary metric
- 5-6: Moderate improvement to primary metric
- 7-8: Significant improvement to primary metric
- 9-10: Transformative — changes funnel economics

**Confidence (20%)**
- 1-2: Pure hypothesis, no supporting data
- 3-4: Anecdotal evidence or competitor observation
- 5-6: Internal data suggests opportunity
- 7-8: Strong data signals + industry research
- 9-10: Prior test showed directional lift, now refining

**Traffic (15%)**
- 1-2: <100 daily visitors to target page
- 3-4: 100-500 daily visitors
- 5-6: 500-2,000 daily visitors
- 7-8: 2,000-10,000 daily visitors
- 9-10: >10,000 daily visitors

**Ease (15%)**
- 1-2: Requires engineering sprint, multiple teams
- 3-4: Backend changes needed, 1-2 weeks
- 5-6: Frontend changes, 3-5 days
- 7-8: Copy/design change, 1-2 days
- 9-10: Simple config change, <1 day

**Revenue Upside (20%)**
- 1-2: No direct revenue impact
- 3-4: Indirect revenue (engagement, retention)
- 5-6: Moderate direct revenue impact
- 7-8: Significant revenue impact if successful
- 9-10: High revenue impact + compounds over time

## Prioritized Output Format

| Rank | Experiment | Score | Impact | Conf. | Traffic | Ease | Rev. | Timeline |
|------|-----------|-------|--------|-------|---------|------|------|----------|
| 1 | [name] | 7.8 | 9 | 7 | 8 | 6 | 8 | 1-2 weeks |
| 2 | [name] | 7.2 | 8 | 6 | 7 | 8 | 7 | 1 week |

---

## Statistical Sample Size Calculator

Two-proportion z-test (two-tailed):

```
z_alpha = 1.960  (95% confidence)
z_beta  = 0.842  (80% power)

p1 = baseline conversion rate
p2 = p1 x (1 + expected_lift)
p_bar = (p1 + p2) / 2

sample_per_variant = ceil(
    (z_alpha x sqrt(2 x p_bar x (1 - p_bar)) + z_beta x sqrt(p1 x (1 - p1) + p2 x (1 - p2)))^2
    / (p2 - p1)^2
)

duration_days = ceil(sample_per_variant / (daily_traffic x traffic_split / num_variants))
```

## Bottleneck Analysis Template

```markdown
### Drop-off: [Stage A] → [Stage B]

**Current rate:** X% | **Benchmark:** Y% | **Gap:** -Zpp

**Root Cause Analysis:**
- UX: [specific friction point]
- Copy: [messaging issue]
- Offer: [value prop problem]
- Trust: [credibility gap]
- Technical: [performance/load issue]

**Data Signals:**
- [Supporting evidence from analytics]
- [User behavior pattern]

**Severity:** High | Medium | Low
```
