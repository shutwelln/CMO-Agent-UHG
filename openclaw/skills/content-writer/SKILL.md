---
name: content-writer
description: Use when you need to write, draft, or create marketing content — blog posts, newsletters, social posts, email copy, articles, landing pages, or Reddit replies. Produces brand-voice-matched content with Princeton GEO optimization and automated proofreading. All output sent to Slack for human approval before publishing.
metadata: { "openclaw": { "emoji": "✍️" } }
---

# Content Writer

## Overview

Expert content writer producing brand-voice-matched marketing content with Princeton Generative Engine Optimization (GEO) for AI engine citation. Every piece passes through automated proofreading before delivery.

## How to Use

1. **Load brand voice** — Call the service layer to get the workspace's brand voice before writing anything
2. **Write content** — Follow the brand voice exactly, apply quality standards and GEO framework
3. **Proofread** — Send output through the proofreading endpoint
4. **Deliver** — Post to Slack for human approval. Never publish directly.

### Service Calls

**Load brand voice:**
```
GET http://cmo-service:8100/api/brand-voice/{workspace_id}
```

**Proofread finished content:**
```
POST http://cmo-service:8100/api/proofread
Body: {"text": "...", "preserve_terms": ["BrandName"], "context": "Brand: workspace, Type: blog_post"}
```

## Content Types

- **blog_post** — Headline, intro hook, H2 sections, conclusion with CTA
- **newsletter** — Subject line (3 variants), preview text, 2-3 sections, CTA, send time recommendation
- **social_post** — Platform-optimized with hashtags, CTA, character count
- **email** — Subject line (3 variants), preview text, body, CTA
- **article** — Long-form with headline, subtitle, H2/H3 sections, expert quotes
- **reddit_reply** — Helpful, non-promotional, conversational. Anti-self-promotion rules.
- **landing_page** — Hero headline + subhead, benefit sections, social proof, FAQ, primary CTA

## Writing Rules

- Match the brand voice exactly — tone, vocabulary, formatting rules
- Short paragraphs (2-3 sentences max)
- Headers (H2, H3) for scannability
- Bullet points for lists of 3+ items
- No filler phrases ("In today's fast-paced world...")
- No generic AI marketing language ("personalized", "cutting-edge", "revolutionary")
- Flag unverified claims with `[VERIFY]`
- Spell out abbreviations on first use — e.g., "Customer Acquisition Cost (CAC)"

## GEO Optimization (Blog Posts & Articles)

Apply the Princeton Generative Engine Optimization framework to maximize AI engine citation:

| Method | Citation Impact | How |
|--------|----------------|-----|
| Cite Sources | +40% | 3-5 authoritative references. "According to [Source]..." |
| Include Statistics | +30% | 4-6 specific stats with attribution. Exact numbers. |
| Add Quotations | +25% | 1-2 real, attributed expert quotes |
| Fluency | +15% | Vary sentence structure. Mix short and compound. |
| Authoritative Tone | +12% | "The data shows" not "It might be the case that" |
| Technical Terms | +10% | Precise industry terms with brief definitions |
| AVOID Keyword Stuffing | -10% | Max one mention per 200 words |

### Engine-Specific Optimization

| Engine | What It Prioritizes |
|--------|-------------------|
| ChatGPT Search | FAQ sections, H2 structure, structured data, concise answers |
| Perplexity | Source-heavy (5-15 citations), recency signals, statistics |
| Google AI Overviews | E-E-A-T signals, schema alignment, entity clarity |
| Claude (web search) | Depth, nuance, cited statistics, long-form authority |

## Output Metadata

Always include at the end of delivered content:
- Word count and reading time estimate
- `[VERIFY]` flag count and list
- Proofreading corrections applied (max 5 shown)

## References

See `references/geo-framework.md` for the full Princeton GEO citation methodology.
