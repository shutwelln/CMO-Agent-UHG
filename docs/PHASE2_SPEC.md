# CMO Agent Phase 2 - Comprehensive Specification

## Document Info
- **Created**: 2026-02-02
- **Author**: Claude Code (via user interview)
- **Status**: Draft for Review

---

## 1. Executive Summary

Build a multi-agent marketing automation system orchestrated by a central CMO Agent accessible via Slack. The system monitors Reddit, RSS feeds, and Google Alerts to find opportunities, drafts content in brand voice, and delivers it for human approval before publishing.

### Key Principles
- **Human-in-the-loop**: All content requires user approval before publishing
- **Quality over speed**: Prefer thorough responses over fast ones
- **Lean budget**: Target under $100/month total operating cost
- **No-code configuration**: Changes via Slack commands, not code edits

---

## 2. System Architecture

### 2.1 Agent Hierarchy

```
CMO Agent (Orchestrator)
├── Research Agent
│   ├── Reddit Monitor (RSS-based, no API needed)
│   ├── RSS Feed Monitor
│   ├── Google Alerts Scanner (Gmail)
│   └── Fraud/Scam Detector
├── Writer Agent
│   ├── Newsletter drafting
│   ├── Blog post creation
│   ├── Reddit reply drafting
│   └── Social media content
└── Visual Agent (Phase 2b)
    ├── Social media graphics
    ├── Newsletter images
    └── Infographics
```

### 2.2 Agent Execution Model

**Sequential execution** for quality content:
1. Research Agent gathers data
2. Writer Agent creates content based on research
3. Visual Agent creates images based on written content
4. CMO Agent presents to user for approval

### 2.3 Technology Stack

| Component | Technology | Cost |
|-----------|------------|------|
| Orchestration | Python on Hostinger VPS | $0 (existing) |
| AI Models | Claude Haiku (scanning) + Sonnet (writing) | ~$60-80/mo |
| Data Storage | SQLite on VPS | $0 |
| Notifications | Slack (existing workspace) | $0 |
| Scheduling | Cron jobs on VPS | $0 |
| n8n | Existing Hostinger instance | $0 (existing) |

**Estimated Total: $60-80/month**

---

## 3. Workspaces & Multi-Tenant Design

### 3.1 Workspace Structure

```yaml
workspaces:
  saverwell:
    name: "Saverwell"
    type: "owned_brand"
    is_default: true
    slack_channel: "#saverwell-opportunities"
    brand_voice_file: "brand_voices/saverwell.txt"

  dsdn:
    name: "DSDN Non-Profit"
    type: "owned_brand"
    slack_channel: "#dsdn-opportunities"
    brand_voice_file: "brand_voices/dsdn.txt"

  # Future client template
  client_template:
    name: "Client Name"
    type: "client"
    slack_channel: "#client-content"
    brand_voice_file: "brand_voices/client.txt"
```

### 3.2 Default Brand Behavior

- **Saverwell** is the default workspace
- User can override per-request: "write this for DSDN"
- Each workspace has its own:
  - Subreddit monitoring list
  - RSS feed sources
  - Brand voice file
  - Slack channel
  - Keywords/filters

---

## 4. Research Agent Specification

### 4.1 Reddit Monitoring

**Method**: Public RSS feeds (no API required)
- URL format: `https://www.reddit.com/r/{subreddit}/new.json?limit=100`

**Saverwell Subreddits**:
- r/GenX, r/seniors, r/retirement, r/frugal
- r/personalfinance, r/FinancialPlanning
- r/medicare, r/socialsecurity

**DSDN Subreddits** (already created as workflow):
- r/downsyndrome, r/specialneedsparenting, r/newparents
- r/nonprofit, r/grants, r/fundraising

**Saverwell Keywords**:
```
senior discount, retirement saving, fixed income, frugal living,
money saving, budget, social security, medicare, pension, frugal,
tight budget, financial planning, cost cutting, discount, coupon,
deal, cheap, affordable, low cost, ssdi, disability, snap benefits
```

**Post Categorization**:
- High-intent lead (someone asking for help)
- General discussion (good for engagement)
- News/announcement (potential content)

### 4.2 RSS Feed Monitoring

**Suggested Sources for Saverwell**:

| Source | URL | Focus |
|--------|-----|-------|
| AARP News | aarp.org/rss | Senior lifestyle, benefits |
| RetireGuide | retireguide.com/feed | Retirement planning |
| Medicare.gov | medicare.gov/rss | Medicare updates |
| SSA News | ssa.gov/rss | Social Security news |
| Consumer Reports | consumerreports.org/rss | Deals, product reviews |
| FTC Scam Alerts | ftc.gov/rss/scam-alerts | Fraud warnings |

**Fraud/Scam Dedicated Monitoring**:
- FTC Consumer Alerts RSS
- FBI IC3 (Internet Crime) news
- AARP Fraud Watch Network
- State Attorney General alerts
- Keywords: scam, fraud, phishing, elder abuse, identity theft

**Schedule**: Check every 6 hours, aggregate for weekly fraud digest

### 4.3 Google Alerts Integration

**Email**: saverwellalerts@gmail.com
**Current Alerts**: Senior discounts & deals

**Processing**:
1. Connect via Gmail API (OAuth)
2. Scan for new alert emails
3. Extract source URLs and summaries
4. Score relevance
5. Add to content queue

### 4.4 Opportunity Scoring

Each discovered item gets scored:
- **Relevance** (0-10): Keyword match strength
- **Recency** (0-10): How fresh is the content
- **Engagement potential** (0-10): Comments, upvotes, shares
- **Actionability** (0-10): Can we respond/use this?

Score >= 25 triggers Slack notification

---

## 5. Writer Agent Specification

### 5.1 Brand Voice - Saverwell

```
BRAND: Saverwell
PARENT COMPANY: Saverwell

TONE: Warm & empathetic
- We understand fixed incomes are challenging
- Supportive without being preachy
- Celebrates small wins and smart savings

VOICE CHARACTERISTICS:
- Friendly and approachable
- Clear and direct (no jargon)
- Respectful - NEVER use: "elderly", "old folks", or patronizing language
- Use: "seniors", "retirees", "experienced savers"

EXAMPLE SNIPPETS:
"Stretching your retirement dollars doesn't have to be stressful.
Let's find the discounts you've earned."

"Did you know Costco offers a senior shopping hour? Here's how
to take advantage of these quiet mornings."

"Social Security questions can be confusing. We break it down
in plain English so you know exactly what you're getting."

FORMATTING:
- Short paragraphs (2-3 sentences max)
- Bullet points for lists
- Headers for scannability
- No excessive emojis
```

### 5.2 Content Types

**Newsletter Content** (primary):
- Mostly curated from research (70%)
- Original tips/commentary (30%)
- Weekly fraud roundup section
- Time-sensitive deals flagged with deadlines

**Reddit Replies**:
- Context-dependent promotion
- Genuinely helpful first
- Soft SaverWell mention when appropriate (per subreddit rules)
- Requires user approval before posting

**Blog Posts**:
- Evergreen guides (e.g., "Complete Guide to Grocery Store Senior Discounts")
- News commentary (e.g., "What the New Medicare Changes Mean for You")
- Delivered for manual posting to site

### 5.3 Fact-Checking Protocol

All specific claims get flagged:
```
[VERIFY] Walgreens offers 20% senior discount on Tuesdays
[VERIFY] Social Security COLA increase is 3.2% for 2026
```

Writer marks uncertain claims. User verifies before approval.

### 5.4 Editorial Calendar

**Recurring Themes**:
- "Money Monday" - Weekly deals roundup
- "Fraud Friday" - Scam alerts and prevention tips
- "Senior Discount Spotlight" - Deep dive on one retailer

**Agent Suggestions**:
- Research Agent proposes trending topics
- Surfaces via Slack: "Trending: 47 Reddit posts about Medicare Part D changes this week. Want me to draft a newsletter section?"

---

## 6. Visual Agent Specification (Phase 2b)

### 6.1 Visual Types Needed

1. **Social Media Graphics**
   - Quote cards with savings tips
   - Promotional posts for Instagram/Facebook
   - Branded templates

2. **Newsletter Images**
   - Header images
   - Section dividers
   - Article thumbnails

3. **Infographics**
   - "Top 10 stores with senior discounts" charts
   - Comparison graphics
   - Data visualizations

### 6.2 Brand Assets

**Source**: Saverwell brand kit (user to provide)
- Logo files
- Color palette (hex codes)
- Fonts
- Style guidelines

### 6.3 Generation Platform

**Recommendation**: DALL-E 3 via OpenAI API
- Cost: ~$0.04/image
- Good for social graphics and simple infographics
- Alternative: Google Imagen 3 (similar cost, requires GCP setup)

**Budget allocation**: ~$5-10/month for ~125-250 images

---

## 7. CMO Agent (Orchestrator) Specification

### 7.1 Slack Interface

**Primary Channel**: DM with CMO Agent bot
**Notification Channels**:
- `#saverwell-opportunities` - Leads and content ideas
- `#dsdn-opportunities` - DSDN-specific alerts
- `#marketing-content` - Drafted content for review

### 7.2 Supported Commands

**Configuration (via natural language)**:
```
"Add r/frugal to Saverwell monitoring"
"Change fraud scan from weekly to daily"
"Remove 'coupon' from keywords"
"Show current subreddit list for DSDN"
```

**Content Requests**:
```
"Draft a newsletter about this week's senior discounts"
"Write a reply to this Reddit post" [link]
"Create a blog post about Medicare Part D enrollment"
"Write this for DSDN" [topic]
```

**Status Queries**:
```
"What did you find today?"
"Show pending content for approval"
"Health check"
```

### 7.3 Approval Workflow

1. Agent drafts content
2. Sends to Slack with preview
3. User options:
   - **Approve** - Content marked final, provided for copy/download
   - **Edit** - User provides feedback, agent revises
   - **Reject** - Content discarded with optional reason

4. Approved content delivered as:
   - Formatted text block (copy-paste ready)
   - Downloadable file (for longer content)
   - NOT auto-published anywhere

### 7.4 Time-Sensitive Content Handling

For deals with deadlines:
1. Agent flags with expiration: "Expires: Friday 2/7"
2. Priority notification in Slack
3. If not approved 24h before deadline, reminder sent
4. After deadline passes, content archived (not sent)

---

## 8. Monitoring Schedules

| Task | Frequency | Time |
|------|-----------|------|
| Reddit scanning (all workspaces) | Every 6 hours | 6am, 12pm, 6pm, 12am |
| RSS feed check | Every 6 hours | Offset by 3 hours from Reddit |
| Gmail alerts scan | Daily | 7am |
| Fraud monitoring | Weekly | Sunday 8am |
| Health summary | Daily | 9am |
| Editorial calendar update | Weekly | Monday 7am |

---

## 9. Error Handling & Health

### 9.1 Error Strategy

- **Transient errors**: Silent retry (3 attempts)
- **Persistent errors**: Log and include in daily health summary
- **Critical errors**: Immediate Slack alert (system down)

### 9.2 Daily Health Summary

Sent to user at 9am:
```
CMO Agent Health Report - Feb 2, 2026

✅ All systems operational

Monitoring Stats (last 24h):
- Reddit posts scanned: 847
- RSS items processed: 234
- Opportunities found: 12
- Content drafts pending: 3

⚠️ Notes:
- r/seniors had slow response (retried successfully)
```

---

## 10. Data Storage

### 10.1 SQLite Schema

```sql
-- Workspaces
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,  -- 'owned_brand' or 'client'
    slack_channel TEXT,
    brand_voice_path TEXT,
    is_default BOOLEAN,
    created_at TIMESTAMP
);

-- Opportunities (found content)
CREATE TABLE opportunities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT,
    source TEXT,  -- 'reddit', 'rss', 'gmail'
    source_url TEXT,
    title TEXT,
    content TEXT,
    score INTEGER,
    category TEXT,
    status TEXT,  -- 'new', 'reviewed', 'used', 'dismissed'
    expires_at TIMESTAMP,
    created_at TIMESTAMP
);

-- Drafted content
CREATE TABLE drafts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT,
    content_type TEXT,  -- 'newsletter', 'reddit_reply', 'blog', 'social'
    title TEXT,
    body TEXT,
    verify_flags TEXT,  -- JSON array of claims to verify
    status TEXT,  -- 'pending', 'approved', 'rejected', 'revised'
    slack_thread_ts TEXT,
    created_at TIMESTAMP,
    approved_at TIMESTAMP
);

-- Configuration
CREATE TABLE config (
    workspace_id TEXT,
    key TEXT,
    value TEXT,
    PRIMARY KEY (workspace_id, key)
);

-- Monitoring sources
CREATE TABLE sources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT,
    type TEXT,  -- 'subreddit', 'rss', 'gmail_filter'
    url TEXT,
    keywords TEXT,  -- JSON array
    active BOOLEAN,
    last_checked TIMESTAMP
);
```

---

## 11. Phase 2 Implementation Roadmap

### Phase 2a: Research + Writer (4-6 weeks)

**Week 1-2: Foundation**
- [ ] Set up SQLite database with schema
- [ ] Create workspace configuration system
- [ ] Build Slack bot with basic commands
- [ ] Implement health check system

**Week 3-4: Research Agent**
- [ ] Reddit RSS monitoring (already have n8n workflow as base)
- [ ] RSS feed aggregator
- [ ] Gmail alerts integration
- [ ] Opportunity scoring system
- [ ] Slack notifications for opportunities

**Week 5-6: Writer Agent**
- [ ] Brand voice file system
- [ ] Newsletter draft generation
- [ ] Reddit reply drafting
- [ ] Blog post creation
- [ ] Approval workflow in Slack

### Phase 2b: Visual Agent (2-3 weeks)

**Week 7-8:**
- [ ] DALL-E 3 API integration
- [ ] Social media graphic templates
- [ ] Newsletter image generation

**Week 9:**
- [ ] Infographic generation
- [ ] Brand asset integration
- [ ] Visual + Writer coordination

### Phase 2c: Polish & Scale (2 weeks)

**Week 10-11:**
- [ ] Editorial calendar automation
- [ ] Configuration via Slack commands
- [ ] Multi-workspace testing (DSDN)
- [ ] Documentation and runbooks

---

## 12. Budget Summary

### Monthly Operating Costs

| Item | Low | High |
|------|-----|------|
| Claude API (Haiku scanning) | $15 | $25 |
| Claude API (Sonnet writing) | $30 | $45 |
| Claude API (CMO conversations) | $10 | $15 |
| DALL-E 3 (images) | $5 | $10 |
| Hosting (existing VPS) | $0 | $0 |
| **Total** | **$60** | **$95** |

### One-Time Setup Costs

- Development time: ~40-60 hours over 10 weeks
- No additional infrastructure purchases needed

---

## 13. Success Metrics

### Phase 2 Goals

1. **Opportunities Found**: 50+ relevant opportunities/week across all workspaces
2. **Content Velocity**: Produce 3+ newsletter drafts/week
3. **Approval Rate**: >80% of drafts approved (not rejected)
4. **Time Savings**: Reduce manual research time by 10+ hours/week
5. **System Uptime**: >99% (daily health checks pass)

---

## 14. Open Questions for User

1. **Saverwell brand assets**: When can you share logo, colors, fonts?
2. **Gmail OAuth**: Need to set up Google Cloud project for alerts access
3. **Hostinger VPS access**: SSH credentials for deployment
4. **Existing n8n workflows**: Should we keep them or migrate to Python?
5. **Newsletter platform**: Need to choose before Phase 2 complete

---

## 15. Appendix

### A. Suggested RSS Feeds (Full List)

**Senior Discounts & Lifestyle**:
- AARP: https://www.aarp.org/rss/
- RetireGuide: https://www.retireguide.com/feed/
- The Senior List: https://www.theseniorlist.com/feed/
- Senior Planet: https://seniorplanet.org/feed/

**Retirement Finance**:
- Kiplinger Retirement: https://www.kiplinger.com/rss/retirement
- MarketWatch Retirement: https://www.marketwatch.com/rss/retirement
- Investopedia Retirement: https://www.investopedia.com/rss/retirement

**Fraud & Security**:
- FTC Consumer Blog: https://www.consumer.ftc.gov/blog/rss.xml
- FBI News: https://www.fbi.gov/feeds/fbi-news
- AARP Fraud Watch: https://www.aarp.org/rss/fraud/

**Medicare & Social Security**:
- Medicare.gov News: https://www.medicare.gov/blog/feed
- SSA News: https://www.ssa.gov/rss/

### B. Competitor Sites to Exclude from Curation

- TheSeniorList.com
- SeniorDiscounts.com
- RetailMeNot (senior section)
- [Add others as identified]

### C. Brand Voice File Template

```
BRAND: [Brand Name]
PARENT COMPANY: [Parent if applicable]

TONE: [Primary tone descriptor]
- [Characteristic 1]
- [Characteristic 2]
- [Characteristic 3]

VOICE DO's:
- [Preferred language/approach]

VOICE DON'Ts:
- [Words/phrases to avoid]

EXAMPLE SNIPPETS:
"[Example 1]"
"[Example 2]"
"[Example 3]"

FORMATTING:
- [Paragraph length]
- [Use of lists]
- [Headers]
- [Emoji policy]
```
