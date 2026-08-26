---
name: posts-and-content
description: Beehiiv Posts API — newsletter post management, content creation, and programmatic sends
metadata:
  tags: beehiiv, posts, content, newsletter, api
---

## Posts Overview

Posts are the primary content unit in Beehiiv. Each post represents a newsletter issue that can be drafted, published, and sent to subscribers.

## List Posts

```
GET /v2/publications/{publication_id}/posts
```

Query parameters:
- `status` — Filter by status: `draft`, `confirmed`, `archived`, `all`
- `content_tags` — Filter by content tags
- `limit` — Results per page (default: 10, max: 100)
- `page` — Page number
- `order_by` — Sort field: `created`, `publish_date`, `displayed_date`
- `direction` — Sort direction: `asc`, `desc`
- `expand[]` — Include related data: `stats`, `free_web_content`, `free_email_content`, `free_rss_content`, `premium_web_content`, `premium_email_content`
- `platform` — Filter by platform: `web`, `email`, `both`
- `audience` — Filter by audience: `free`, `premium`, `both`

## Get Post by ID

```
GET /v2/publications/{publication_id}/posts/{post_id}
```

Same `expand[]` options available for including content and stats.

## Create Post (Enterprise Plan)

```
POST /v2/publications/{publication_id}/posts
```

```json
{
  "title": "Weekly Growth Digest #42",
  "subtitle": "This week's top marketing insights",
  "content": "<p>Your HTML content here...</p>",
  "content_tags": ["growth", "weekly-digest"],
  "audience": "both",
  "platform": "both",
  "status": "draft"
}
```

Key fields:
- `title` (required) — Post title / subject line
- `subtitle` — Post subtitle
- `content` — HTML content of the post
- `content_tags` — Array of tags for categorization
- `audience` — Who can see it: `free`, `premium`, `both`
- `platform` — Where to publish: `web`, `email`, `both`
- `status` — Initial status: `draft` (default)

**Note**: Post creation via API requires an Enterprise plan. Most publications create posts through the Beehiiv web editor.

## Post Statuses

| Status | Description |
|--------|-------------|
| `draft` | Work in progress, not yet sent or published |
| `confirmed` | Published and/or sent to subscribers |
| `archived` | Removed from active view, still accessible |

## Delete Post

```
DELETE /v2/publications/{publication_id}/posts/{post_id}
```

## Content Types

Posts support different content for different audiences:
- **Free web content** — What free subscribers see on the website
- **Free email content** — What free subscribers receive via email
- **Premium web content** — What premium subscribers see on the website
- **Premium email content** — What premium subscribers receive via email
- **RSS content** — Content distributed via RSS feed

Use the `expand[]` parameter to retrieve specific content types.

## Programmatic Sends

While direct send endpoints are limited, you can:
1. Create a post via API (Enterprise)
2. Use automations to trigger sends based on post creation
3. Use the Beehiiv web UI to schedule and send

For transactional-style sends, consider using automations triggered by custom fields or tags applied via the Subscriptions API.

## Live Reference URLs

Use WebFetch on these URLs when you need detailed or current documentation:

- List posts: `https://developers.beehiiv.com/api-reference/posts/index`
- Get post: `https://developers.beehiiv.com/api-reference/posts/show`
- Create post: `https://developers.beehiiv.com/api-reference/posts/create`
- Delete post: `https://developers.beehiiv.com/api-reference/posts/destroy`
