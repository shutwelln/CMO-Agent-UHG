---
name: daily-briefing
description: Use when you need growth ideas, a morning brief, daily priorities, or action items. Generates scored growth ideas by analyzing recent project activity across workspaces. Uses 4-dimension scoring (impact, effort, confidence, strategic value) with dedup against previous ideas. Also triggered daily by heartbeat at 8:30 AM ET.
metadata: { "openclaw": { "emoji": "🌅" } }
---

# Daily Briefing

## Overview

Generates scored growth ideas and morning action briefs by analyzing recent project activity. Uses 2-tier LLM approach: generate at high temperature (creative breadth), then score at low temperature (analytical precision). Deduplicates against 90 days of previous ideas.

DSDN has its own dedicated ideas process — exclude from cross-workspace growth ideas.

## How to Use

1. **Gather context** — Review recent Slack activity, tracked metrics, and project status across workspaces
2. **Generate ideas** — Use creative temperature for breadth
3. **Score & select** — Apply 4-dimension scoring, drop ideas below 4.0 composite
4. **Compile brief** — Structure with priorities, quick wins, calendar, and pending approvals
5. **Deliver to Slack** — Post to the growth ideas channel

## 4-Dimension Scoring

| Dimension | Scale | Weight | Description |
|-----------|-------|--------|-------------|
| Impact | 1-10 | 35% | Expected growth contribution |
| Effort | 1-10 | 25% | Implementation difficulty (1=easy, 10=hard) |
| Confidence | 1-10 | 20% | Evidence supporting the idea |
| Strategic Value | 1-10 | 20% | Alignment with long-term goals |

**Composite score:** `(Impact x 0.35) + ((11 - Effort) x 0.25) + (Confidence x 0.20) + (Strategic x 0.20)`

Higher composite = prioritize first. Ideas scoring < 4.0 are dropped.

## Idea Quality Criteria

- Reference specific recent projects by name
- Actionable within 1-2 weeks
- Mix of quick wins (effort 1-3) and bigger bets (effort 5-8)
- At least 2 ideas leverage existing content (repurposing/amplification)
- At least 1 idea involves cross-workspace synergy
- Flag performance claims with `[VERIFY]`
- Never re-suggest previous ideas (dedup against 90-day history)

## Output Format

```markdown
# Morning Brief — [Date]

## Top Growth Ideas

### 1. [Idea Title] — Score: 7.8/10
**Impact:** 9 | **Effort:** 3 | **Confidence:** 7 | **Strategic:** 8

[2-3 sentence description with specific action steps]

**Why now:** [Timing rationale]
**First step:** [Concrete next action]
**Workspace:** [Which brand]

### 2. [Idea Title] — Score: 7.2/10
...

---

## Quick Wins (Start Today)

- [ ] [Quick win 1] — Est. 30 min — [workspace]
- [ ] [Quick win 2] — Est. 1 hour — [workspace]

## Content Due This Week

| Day | Platform | Topic | Status |
|-----|----------|-------|--------|
| ... | ... | ... | Draft/Approved/Published |

## Pending Approvals

- [Draft title] — waiting since [date] — [Slack link]

---
*Generated [timestamp] | Ideas scored against 90-day history | [VERIFY] flags: [count]*
```
