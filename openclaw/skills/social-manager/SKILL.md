---
name: social-manager
description: Use when you need to create social media content calendars, posting schedules, hashtag strategies, engagement plans, or platform-specific content planning. Strategy and planning only — delegates actual content writing to the content-writer skill. Triggers n8n workflows for publishing (never publishes directly).
metadata: { "openclaw": { "emoji": "📅" } }
---

# Social Manager

## Overview

Social media strategy and content calendar manager. Creates platform-specific calendars, posting schedules, hashtag strategies, and engagement plans. Coordinates with the content-writer skill for actual copy and triggers n8n workflows for publishing.

## How to Use

1. **Load brand voice** — Get workspace context from the service layer
2. **Create calendar** — Generate structured content calendar for the requested period
3. **Check due content** — During heartbeat, check if posts are due per calendar
4. **Trigger publishing** — After human approval in Slack, trigger n8n workflows

### Service Calls

**Load brand voice:**
```
GET http://cmo-service:8100/api/brand-voice/{workspace_id}
```

**Trigger publishing workflow (after approval):**
```
POST http://cmo-service:8100/api/n8n/execute/{workflow_id}
Body: {"data": {"platform": "linkedin", "content": "...", "schedule_time": "..."}}
```

## Platform Rules

| Platform | Max Length | Best Format | Optimal Times |
|----------|-----------|-------------|---------------|
| Instagram | 2,200 chars | Carousel, Reel | Tue-Thu 10am-2pm |
| LinkedIn | 3,000 chars | Text + image, Article | Tue-Thu 8am-10am |
| Twitter/X | 280 chars | Thread, Single | Mon-Fri 8am-12pm |
| TikTok | 2,200 chars | Short video (15-60s) | Tue-Thu 7pm-9pm |
| Facebook | 63,206 chars | Image + text, Video | Wed-Fri 1pm-4pm |

## Calendar Structure

Per post entry:
- Date and time (optimal for platform)
- Platform (with format requirements)
- Content pillar/theme
- Post concept (1-2 sentence description)
- Content type (carousel, reel, static, story, thread, article)
- Call-to-action direction
- Hashtag set (5-10, mix of branded + niche + trending)
- Cross-posting notes

## Content Pillar Distribution

- Thought Leadership: 30%
- Product/Service: 25%
- Community/Social Proof: 20%
- Education/How-to: 15%
- Culture/Behind-the-scenes: 10%

## Output Format

```markdown
# Content Calendar — [Brand] — [Period]

## Week of [Date]

| Day | Platform | Pillar | Concept | Type | Time | Status |
|-----|----------|--------|---------|------|------|--------|
| Mon | LinkedIn | Thought Leadership | [concept] | Text + image | 9:00 AM | Draft |
| ... | ... | ... | ... | ... | ... | ... |

## Hashtag Strategy

**Branded:** #[brand], #[tagline]
**Niche:** #[industry], #[topic]
**Trending:** [research current trends]
```

## Integration

- Delegates to **content-writer** for actual post copy
- Triggers **n8n workflows** for publishing (never direct API)
- Reports to Slack for human approval before any publishing
