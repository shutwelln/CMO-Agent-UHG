"""Create the Saverwell Lifecycle Marketing Plan as a Google Doc.

Constructs the full 10-section document structure and creates it via
the Docs Agent's Google Docs API builder. Bypasses LLM generation to
ensure exact content fidelity.

Usage:
    python scripts/create_lifecycle_plan_doc.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))


def build_document_structure() -> dict:
    """Build the full lifecycle marketing plan document structure."""
    return {
        "title": "Saverwell Lifecycle Marketing Plan",
        "include_toc": True,
        "sections": [
            # ── Section 1: Subscriber Profile Architecture ──────────────
            {
                "heading": "Subscriber Profile Architecture",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This section defines the subscriber data model in Customer.io. "
                            "When a visitor subscribes on the Saverwell website, the form data "
                            "flows through Supabase and n8n before landing in Customer.io as a "
                            "fully enriched profile. The subscriber pipeline is live: website "
                            "form to Supabase edge function to n8n webhook to Customer.io "
                            "profile creation."
                        ),
                    },
                ],
            },
            {
                "heading": "Profile Attributes (n8n to Customer.io)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The n8n subscriber webhook pushes these fields to Customer.io "
                            "via the Track API (PUT /api/v1/customers/{email}):"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Source Field", "Customer.io Attribute", "Purpose"],
                        "rows": [
                            ["email", "(identifier)", "Primary ID"],
                            ["zip", "zip_code", "Geographic personalization"],
                            [
                                "source",
                                "signup_source",
                                "Form placement (homepage, header, exit_popup, inline)",
                            ],
                            ["timestamp", "created_at", "Lifecycle timing (Unix)"],
                            ["ip_address", "ip_address", "Geo-enrichment"],
                            [
                                "All 12 UTM params",
                                "utm_source, utm_campaign, utm_medium, etc.",
                                "Attribution",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Computed Attributes (Set by n8n Code Node)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "These attributes are computed by an n8n Code node at profile "
                            "creation time, before the Customer.io API call:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Attribute", "Logic", "Purpose"],
                        "rows": [
                            [
                                "content_interest",
                                'Derived from signup page: "protection" / "guides" / "savings" / "all"',
                                "Content preference seeding",
                            ],
                            [
                                "state_resolved",
                                "ZIP-to-state lookup",
                                "State targeting",
                            ],
                            [
                                "lifecycle_stage",
                                '"new"',
                                "Lifecycle tracking",
                            ],
                            [
                                "welcome_flow_started",
                                "false",
                                "Flow gating",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Note: Subscription preferences are managed natively by "
                            "Customer.io's Subscription Center (Topics), not as profile "
                            "attributes. See Section 2 for details."
                        ),
                    },
                ],
            },
            {
                "heading": "Custom Events to Track",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Event", "Trigger", "Source"],
                        "rows": [
                            ["subscribed", "Profile creation", "n8n webhook"],
                            [
                                "article_read",
                                "75% scroll on article page",
                                "Website dataLayer to n8n to Customer.io",
                            ],
                            [
                                "discount_viewed",
                                "Discount detail view",
                                "Website dataLayer to n8n to Customer.io",
                            ],
                            [
                                "welcome_completed",
                                "Finished welcome flow",
                                "Customer.io journey Update Attribute action",
                            ],
                            [
                                "re_engaged",
                                'User clicks "Keep My Updates" in win-back',
                                "n8n webhook",
                            ],
                        ],
                    },
                ],
            },
            # ── Section 2: Unsubscribe Group Architecture ──────────────
            {
                "heading": "Unsubscribe Group Architecture (Customer.io Subscription Center)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All subscription management lives natively in Customer.io using "
                            "their Subscription Center with Topics. No external preference "
                            "pages are needed. This approach is CAN-SPAM compliant and gives "
                            "subscribers granular control over what they receive."
                        ),
                    },
                ],
            },
            {
                "heading": "Five Subscription Topics",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "These five topics are created in Customer.io UI under "
                            "Settings > Subscription Center:"
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "Savings & Discounts - Weekly discount alerts, personalized merchant content",
                            "Fraud Protection - Protection article spotlights, fraud alerts, safety tips",
                            "Educational Guides - Medicare guides, insurance guides, financial education",
                            "Weekly Digest - The weekly newsletter compilation",
                            "Product & Marketing - Product announcements, partnerships, promotions",
                        ],
                    },
                ],
            },
            {
                "heading": "How the Subscription Center Works",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Each campaign/broadcast is associated with a Topic in Customer.io's journey builder. Customer.io automatically skips people who have unsubscribed from that topic.",
                            "Customer.io hosts a Subscription Center page automatically. The unsubscribe link in every email shows a page listing all 5 topics with toggles. Users can unsubscribe from individual topics or all at once.",
                            'The Subscription Center URL is auto-generated by Customer.io and embedded via the {{ unsubscribe_url }} Liquid tag in email footers.',
                            'CAN-SPAM "Unsubscribe from all" is always available as an option on the Subscription Center page.',
                            "New subscribers are opted in to all 5 topics by default (configurable per topic in Customer.io settings).",
                        ],
                    },
                ],
            },
            {
                "heading": "Email Footer (Every Email)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Every email includes this footer: "
                            '"Manage your email preferences | Unsubscribe from all". '
                            "Both links are auto-generated by Customer.io and point to "
                            "the hosted Subscription Center."
                        ),
                    },
                ],
            },
            {
                "heading": "Subscription Center Setup (One-Time)",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Go to Settings > Subscription Center",
                            "Enable the Subscription Center",
                            "Create 5 topics with names and descriptions",
                            'Set all topics to "opted in by default"',
                            "Associate each campaign/broadcast with its relevant topic",
                        ],
                    },
                ],
            },
            # ── Section 3: Welcome/Onboarding Campaign ─────────────────
            {
                "heading": "Welcome/Onboarding Campaign (5 Emails, 14 Days)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Type: Segment-triggered campaign in Customer.io. "
                            'Trigger segment: lifecycle_stage = "new" AND '
                            "welcome_flow_started = false. "
                            "Goal: Person clicks any email link within 14 days. "
                            "Exit: Person unsubscribes."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "#",
                            "Day",
                            "Subject",
                            "Content",
                            "Topic",
                            "Personalization",
                        ],
                        "rows": [
                            [
                                "1",
                                "0",
                                '"Senior Discounts Near {{ zip_code }}"',
                                "ZIP-personalized discount highlights. Top 5-8 merchants near their zip. CTA: Explore All Discounts",
                                "Savings & Discounts",
                                "ZIP to local merchants from Supabase",
                            ],
                            [
                                "2",
                                "3",
                                '"3 Discounts Most Seniors Miss"',
                                'Top 3 under-discovered discounts. "Did you know?" format.',
                                "Savings & Discounts",
                                "ZIP in CTA URL param",
                            ],
                            [
                                "3",
                                "6",
                                "Uses protection article email_subject",
                                "Protection spotlight. Uses email_intro_md from a featured protection article (e.g., safe-online-shopping-tips). 3 red flags teaser.",
                                "Fraud Protection",
                                "Article email variant data",
                            ],
                            [
                                "4",
                                "10",
                                '"How One Retiree Saves $200/Month"',
                                "Community story + guide teaser. Uses email_intro_md from a featured Medicare guide (e.g., save-money-medicare-premiums).",
                                "Educational Guides",
                                "Article email variant data",
                            ],
                            [
                                "5",
                                "14",
                                '"Your First Weekly Digest is Ready"',
                                'Preview of digest format (1 discount, 1 protection tip, 1 guide). CTA: "Customize What You Receive" links to Customer.io Subscription Center',
                                "None (meta)",
                                "{{ unsubscribe_url }}",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Welcome Campaign - Journey End Actions",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            'Journey end action: Update Attribute - set lifecycle_stage = "active" '
                            "and welcome_flow_started = true."
                        ),
                    },
                ],
            },
            {
                "heading": "ZIP Personalization for Email 1",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Two approaches for ZIP-based merchant personalization:"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            'Phase 1 (recommended): Generic "discounts near you" with ZIP as URL parameter; the website landing page handles personalization at page load.',
                            "Phase 2 (advanced): n8n queries Supabase for merchants near subscriber ZIP, passes per_user_data to Customer.io broadcast with personalized merchant list rendered via Liquid loops.",
                        ],
                    },
                ],
            },
            # ── Section 4: Content Drip Campaigns ──────────────────────
            {
                "heading": "Content Drip Campaigns",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Two parallel content drip campaigns deliver the 20 existing "
                            "articles (12 Medicare guides + 8 protection articles) to "
                            "subscribers over 12 weeks. Each email uses pre-built email "
                            "variants from the article models, so no new copywriting is needed."
                        ),
                    },
                ],
            },
            {
                "heading": "Protection Content Series (8 Articles, 8 Weeks)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Trigger: welcome_flow_started = true AND subscribed to "
                            "Fraud Protection topic. "
                            "Start: Day 21 from signup (7 days after welcome flow ends). "
                            "Cadence: 1 email/week on Tuesdays."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Each email directly uses the pre-built email variants from "
                            "the ProtectionArticle model (content/protection.py):"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "email_subject - Subject line (max 45 chars, pre-validated)",
                            "email_preheader - Preheader text (max 90 chars)",
                            "email_intro_md - Email body intro (2-4 sentences, markdown to HTML)",
                            'email_cta_label - "Read full guide" (fixed)',
                            "email_cta_url - /protection/article/{slug} (prepend https://saverwell.com)",
                        ],
                    },
                ],
            },
            {
                "heading": "Protection Article Sequence (Broad Appeal to Specific)",
                "level": 3,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "safe-online-shopping-tips",
                            "password-safety-guide",
                            "bank-impostor-calls",
                            "subscription-traps-unauthorized-charges",
                            "email-account-hacked",
                            "what-to-do-after-a-data-breach",
                            "two-factor-authentication-guide",
                            "tax-identity-theft",
                        ],
                    },
                ],
            },
            {
                "heading": "Guide Content Series (12 Articles, 12 Weeks)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Trigger: welcome_flow_started = true AND subscribed to "
                            "Educational Guides topic. "
                            "Start: Day 24 from signup (offset from protection to avoid same-day sends). "
                            "Cadence: 1 email/week on Thursdays."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Uses pre-built email variants from GuideArticle model "
                            "(content/guide.py). Same field mapping as protection articles."
                        ),
                    },
                ],
            },
            {
                "heading": "Guide Article Sequence (Broadest Appeal First)",
                "level": 3,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "medicare-explained-simple-guide",
                            "medicare-parts-a-b-c-d-explained",
                            "save-money-medicare-premiums",
                            "medicare-enrollment-deadlines",
                            "medicare-advantage-vs-original",
                            "does-medicare-cover-prescriptions",
                            "medicare-vs-medicaid-difference",
                            "does-medicare-cover-dental",
                            "does-medicare-cover-vision",
                            "does-medicare-cover-hearing-aids",
                            "irmaa-avoid-higher-medicare-premiums",
                            "medicare-extra-help-prescription-savings",
                        ],
                    },
                ],
            },
            {
                "heading": "Frequency Cap",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Max 3 emails/week per subscriber: Monday digest + Tuesday "
                            "protection + Thursday guide. This cadence prevents email fatigue "
                            "while maintaining consistent touchpoints."
                        ),
                    },
                ],
            },
            # ── Section 5: Weekly Newsletter/Digest ────────────────────
            {
                "heading": "Weekly Newsletter/Digest (API-Triggered Broadcast)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Type: API-triggered broadcast (not a campaign). n8n builds "
                            "content dynamically and triggers via the Customer.io App API. "
                            "This approach ensures fresh, personalized content each week "
                            "without manual effort."
                        ),
                    },
                ],
            },
            {
                "heading": 'n8n Workflow: "Saverwell Weekly Digest Builder"',
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Schedule Trigger: Monday 6:00 AM CST",
                            "Code Node: Query Supabase for newest protection article, newest guide article, top 3 trending discounts",
                            "Code Node: For each unique ZIP code group, query Supabase for local merchants",
                            "HTTP Request: POST https://api.customer.io/v1/campaigns/{broadcast_id}/triggers with per_user_data",
                        ],
                    },
                ],
            },
            {
                "heading": "Broadcast Template (Created Once in Customer.io UI)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": 'Subject: "Your Weekly Saverwell Update"',
                    },
                    {
                        "type": "paragraph",
                        "text": "The broadcast template has 3 sections:",
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            '"Discounts Near You" - ZIP-personalized merchant highlights',
                            '"This Week\'s Protection Tip" - Uses article email variant data from the newest protection article',
                            '"Featured Guide" - Uses article email variant data from the newest guide article',
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Footer includes preference center link. "
                            "Targets segment: subscribed to Weekly Digest topic AND not unsubscribed."
                        ),
                    },
                ],
            },
            {
                "heading": "Scale Considerations",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "For lists over 10K subscribers, use data_file_url (CSV hosted on "
                            "Supabase Storage) instead of inline per_user_data. The Customer.io "
                            "API rate limit is 1 request per 10 seconds for broadcast triggers."
                        ),
                    },
                ],
            },
            # ── Section 6: Win-Back / Re-Engagement Campaign ──────────
            {
                "heading": "Win-Back / Re-Engagement Campaign",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            'Trigger segment: lifecycle_stage = "active" AND no email_opened '
                            "in 30 days AND no email_clicked in 30 days."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["#", "Day", "Subject", "Content"],
                        "rows": [
                            [
                                "1",
                                "0",
                                '"Still Finding Savings Near You?"',
                                "Value reminder. 2-3 new articles/discounts since last engagement.",
                            ],
                            [
                                "2",
                                "7",
                                '"Your Fraud Protection Update"',
                                "Lead with protection (emotional urgency). Feature newest protection article.",
                            ],
                            [
                                "3",
                                "14",
                                '"Should We Keep Your Updates Coming?"',
                                'Direct ask. "Yes, Keep My Updates" button triggers n8n webhook that tracks re_engaged event. Secondary: preference center link.',
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Sunset Policy",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "If no engagement across all 3 re-engagement emails (44 days total "
                            "from first re-engagement send):"
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            'Set lifecycle_stage = "sunset"',
                            "Suppress person in Customer.io (retain data, stop all messaging)",
                            "This is a reversible action - if the person later re-engages via a direct site visit, their profile can be reactivated",
                        ],
                    },
                ],
            },
            # ── Section 7: Automation Architecture ─────────────────────
            {
                "heading": "Automation Architecture",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The full automation flow from website subscribe to lifecycle "
                            "messaging:"
                        ),
                    },
                ],
            },
            {
                "heading": "Subscribe Flow (Automated)",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Website (Lovable): Subscriber fills form, POST to Supabase Edge Function",
                            "Supabase Edge Function: Validates, stores, forwards to n8n webhook with all fields (email, zip, brand, consent, UTMs, source, url, referrer, ip)",
                            "n8n Webhook (Saverwell Subscriber): Code Node computes attributes (state, content_interest, lifecycle_stage)",
                            "n8n HTTP Request: PUT Customer.io Track API to identify person with all attributes",
                            "n8n HTTP Request: POST Customer.io Track API to track 'subscribed' event",
                        ],
                    },
                ],
            },
            {
                "heading": "Customer.io Auto-Triggered Campaigns",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            'Segment "New Subscribers" triggers Welcome Campaign (5 emails, 14 days)',
                            'Segment "Active - Protection" triggers Protection Drip (8 emails, 8 weeks)',
                            'Segment "Active - Guides" triggers Guide Drip (12 emails, 12 weeks)',
                            'Segment "Inactive 30d" triggers Re-Engagement Campaign (3 emails, 14 days)',
                            "Reporting Webhooks forward engagement data to n8n for tracking",
                        ],
                    },
                ],
            },
            {
                "heading": "n8n Scheduled Workflows",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Weekly Digest Builder (Monday 6 AM CST): Queries Supabase, assembles content, triggers Customer.io Broadcast API",
                            "Engagement Scoring (Daily): Calculates engagement scores, updates lifecycle stages via Customer.io Batch API",
                        ],
                    },
                ],
            },
            {
                "heading": "What MUST Be Done in Customer.io UI (No API Alternative)",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Create 4 campaigns (welcome, protection drip, guide drip, re-engagement) with journey flows",
                            "Create 1 broadcast template (weekly digest)",
                            "Create 5 data-driven segments",
                            "Enable Subscription Center + create 5 topics",
                            "Associate each campaign/broadcast with its relevant topic",
                            "Paste HTML email templates into each journey step",
                        ],
                    },
                ],
            },
            {
                "heading": "What Is Fully Automated via API/n8n",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Profile creation + attribute updates (Track API)",
                            "Event tracking (Track API)",
                            "Weekly digest content assembly + broadcast trigger (App API)",
                            "Engagement scoring + lifecycle transitions (Batch API)",
                            "HTML email template generation (CMO Agent Writer)",
                        ],
                    },
                ],
            },
            # ── Section 8: Email Template Strategy ─────────────────────
            {
                "heading": "Email Template Strategy",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "HTML templates are generated by the CMO Agent Writer and pasted into "
                            "Customer.io campaign steps. A single responsive base template with "
                            "Liquid variables serves all email types."
                        ),
                    },
                ],
            },
            {
                "heading": "Base Template Structure",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Saverwell logo",
                            "Preheader: {{ preheader }}",
                            "Intro text: {{ intro_text }}",
                            "Content cards (conditional Liquid blocks per email type)",
                            "CTA button: {{ cta_label }} linking to {{ cta_url }}",
                            "Footer: Manage preferences | Unsubscribe | Physical address",
                        ],
                    },
                ],
            },
            {
                "heading": "Article Email Variant Mapping",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "How the pre-built email variants from each article map to the template:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Article Field",
                            "Template Variable",
                            "Notes",
                        ],
                        "rows": [
                            [
                                "email_subject",
                                "Customer.io subject line field",
                                "Max 45 chars, pre-validated",
                            ],
                            [
                                "email_preheader",
                                "Hidden preheader <span>",
                                "Max 90 chars",
                            ],
                            [
                                "email_intro_md",
                                "Content area (markdown to HTML)",
                                "2-4 sentences",
                            ],
                            [
                                "email_cta_label",
                                "CTA button text",
                                "Fixed: Read full guide",
                            ],
                            [
                                "email_cta_url",
                                "CTA button href",
                                "Prepend https://saverwell.com",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Design Specs for Senior Audience",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Single-column, 600px max-width",
                            "16px minimum body text, 20px headings",
                            "48px minimum CTA button height (large touch targets)",
                            "High-contrast colors, no light gray text",
                            "No em dashes, no mid-sentence bolding (brand voice rules)",
                            "Preheader text hidden but present for inbox preview",
                            "Dark mode compatible (use both light and dark background colors)",
                        ],
                    },
                ],
            },
            # ── Section 9: Implementation Roadmap ──────────────────────
            {
                "heading": "Implementation Roadmap",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The implementation is phased over 6 weeks. Total manual "
                            "Customer.io UI work is approximately 9 hours. Everything else "
                            "is automated via API and n8n."
                        ),
                    },
                ],
            },
            {
                "heading": "Phase 1: Foundation (Week 1-2) - ~4 Hours Manual",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Day", "Task", "Method"],
                        "rows": [
                            [
                                "1-2",
                                "Add Customer.io API keys to .env, update n8n subscriber webhook with computed attributes, test profile creation",
                                "n8n + API (automated)",
                            ],
                            [
                                "3",
                                "Create 5 data-driven segments in Customer.io",
                                "Customer.io UI (manual)",
                            ],
                            [
                                "4-5",
                                "Create Welcome Campaign (5-email journey), paste HTML templates, set attribute conditions + Update Attribute actions",
                                "Customer.io UI (manual)",
                            ],
                            [
                                "5-6",
                                "Build reporting webhook receiver in n8n (capture opens, clicks, bounces as events)",
                                "n8n (automated)",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Phase 2: Content Drips + Digest (Week 3-4) - ~3 Hours Manual",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Day", "Task", "Method"],
                        "rows": [
                            [
                                "7-8",
                                "Create Protection Drip Campaign (8-email journey, Tuesdays) + Guide Drip Campaign (12-email journey, Thursdays)",
                                "Customer.io UI (manual)",
                            ],
                            [
                                "9-10",
                                'Create Weekly Digest broadcast template, build n8n "Weekly Digest Builder" workflow',
                                "Split (1 template UI, rest n8n)",
                            ],
                            [
                                "10-11",
                                "Configure Customer.io Subscription Center: enable, create 5 topics, set defaults",
                                "Customer.io UI (manual, ~15 min)",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Phase 3: Win-Back + Optimization (Week 5-6) - ~2 Hours Manual",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Day", "Task", "Method"],
                        "rows": [
                            [
                                "12-13",
                                "Create Re-Engagement Campaign (3-email journey), configure sunset actions",
                                "Customer.io UI (manual)",
                            ],
                            [
                                "14",
                                "Build engagement scoring n8n workflow, set up A/B test tracking",
                                "n8n (automated)",
                            ],
                        ],
                    },
                ],
            },
            # ── Section 10: KPIs and Success Metrics ───────────────────
            {
                "heading": "KPIs and Success Metrics",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "These targets are based on industry benchmarks for the 55+ "
                            "demographic in financial services and education verticals."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Metric", "Target", "Source"],
                        "rows": [
                            [
                                "Welcome flow completion rate",
                                "50%+",
                                "Customer.io campaign metrics",
                            ],
                            [
                                "Welcome flow click rate",
                                "15%+ (at least 1 click across 5 emails)",
                                "Customer.io campaign metrics",
                            ],
                            [
                                "Protection drip open rate",
                                "25%+",
                                "Customer.io campaign metrics",
                            ],
                            [
                                "Guide drip open rate",
                                "30%+",
                                "Customer.io campaign metrics",
                            ],
                            [
                                "Weekly digest open rate",
                                "22%+",
                                "Customer.io broadcast metrics",
                            ],
                            [
                                "Unsubscribe rate",
                                "Below 0.5% per send",
                                "Customer.io reporting webhooks",
                            ],
                            [
                                "Preference center usage",
                                "10%+ of subscribers customize",
                                "n8n tracking",
                            ],
                            [
                                "Re-engagement recovery rate",
                                "15%+ return to active",
                                "Customer.io segment transitions",
                            ],
                            [
                                "Sunset rate",
                                "Below 20% of list per quarter",
                                "Customer.io segment size",
                            ],
                        ],
                    },
                ],
            },
        ],
    }


def main() -> None:
    """Create the Google Doc."""
    from cmo_agent.agents.docs import DocsAgent, _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    # --- Load credentials -----------------------------------------------
    # Service account lacks Docs API permission; use OAuth2 token instead.
    oauth_path = (
        "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
    )

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=SCOPES,
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    # --- Build document structure ---------------------------------------
    structure = build_document_structure()
    title = structure["title"]
    include_toc = structure.get("include_toc", False)
    sections = _normalize_sections(structure, skip_toc=include_toc)

    print(f"Building Google Doc: {title}")
    print(f"Sections: {len(sections)}")

    # --- Create doc and populate ----------------------------------------
    # 1. Create empty document
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    print(f"Document created: {doc_id}")

    # 2. Build requests using a sequential cursor
    requests = []
    cursor = 1

    def _heading_style(level: int) -> str:
        mapping = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3", 4: "HEADING_4"}
        return mapping.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        # Insert heading
        if heading:
            heading_text = heading + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": heading_text}}
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": h_start, "endIndex": h_end},
                        "paragraphStyle": {
                            "namedStyleType": _heading_style(level),
                            "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        # Insert content blocks
        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text:
                    continue
                para_text = text + "\n"
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": para_text}}
                )
                p_start = cursor
                p_end = cursor + len(para_text)
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": p_start, "endIndex": p_end},
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {"magnitude": 6, "unit": "PT"},
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": item_text,
                            }
                        }
                    )
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)

                # Insert table
                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                # Execute current batch, then populate table
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                # Re-read doc to find table cell indices
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem  # last table is the one we just inserted

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts = []
                    for ri, row_data in enumerate(all_table_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(table_row.get("tableCells", [])):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get("startIndex", 0)
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append((cell_idx, cell_text))

                    # Sort descending to avoid shifting indices
                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cell_idx},
                                    "text": cell_text,
                                }
                            }
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                    # Bold header row
                    doc_state2 = docs_service.documents().get(documentId=doc_id).execute()
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get("tableRows"):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si,
                                                    "endIndex": ei,
                                                },
                                                "textStyle": {"bold": True},
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                # Update cursor position after table
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                # Add newline after table
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": "\n"}}
                )
                cursor += 1

    # 3. Execute remaining batch
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    # 4. Insert Table of Contents
    if include_toc:
        _insert_toc(docs_service, doc_id)

    # 5. Share document (restricted access)
    share_file_restricted(drive_service, doc_id)

    # 6. Move to CMO Agent folder
    folder_id = ensure_drive_folder(drive_service)
    if folder_id:
        move_file_to_folder(drive_service, doc_id, folder_id)

    docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"\nGoogle Doc created successfully!")
    print(f"URL: {docs_url}")


def _insert_toc(docs_service, doc_id: str) -> None:
    """Insert a linked table of contents at the beginning of the document."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])

    headings = []
    for elem in body_content:
        if "paragraph" not in elem:
            continue
        para = elem["paragraph"]
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        heading_id = style.get("headingId", "")
        if not named_style.startswith("HEADING_") or not heading_id:
            continue
        level = int(named_style.replace("HEADING_", ""))
        if level > 3:
            continue
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()
        if text:
            headings.append({"text": text, "level": level, "heading_id": heading_id})

    if not headings:
        return

    toc_title = "Table of Contents\n"
    toc_tip = (
        "For page numbers: select this TOC, delete it, then "
        "Insert \u2192 Table of contents \u2192 With page numbers.\n"
    )
    entry_lines = []
    for h in headings:
        entry_lines.append(h["text"] + "\n")
    separator = "\n"

    toc_text = toc_title + toc_tip + "".join(entry_lines) + separator

    requests = [
        {"insertText": {"location": {"index": 1}, "text": toc_text}},
    ]

    # Style title
    title_start = 1
    title_end = title_start + len(toc_title)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end - 1},
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 16, "unit": "PT"},
                },
                "fields": "bold,fontSize",
            }
        }
    )

    # Style tip line
    tip_start = title_end
    tip_end = tip_start + len(toc_tip)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 6, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end - 1},
                "textStyle": {
                    "italic": True,
                    "fontSize": {"magnitude": 9, "unit": "PT"},
                    "foregroundColor": {
                        "color": {
                            "rgbColor": {"red": 0.6, "green": 0.6, "blue": 0.6}
                        }
                    },
                },
                "fields": "italic,fontSize,foregroundColor",
            }
        }
    )

    # Style each entry
    entry_cursor = tip_end
    for h in headings:
        entry_text = h["text"] + "\n"
        entry_start = entry_cursor
        entry_end = entry_cursor + len(entry_text) - 1

        if entry_end > entry_start:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": entry_start,
                            "endIndex": entry_start + len(entry_text),
                        },
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "spaceAbove": {"magnitude": 2, "unit": "PT"},
                            "spaceBelow": {"magnitude": 2, "unit": "PT"},
                            "indentStart": {
                                "magnitude": 18 * (h["level"] - 1),
                                "unit": "PT",
                            },
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow,indentStart",
                    }
                }
            )

            style_fields = "fontSize,link"
            text_style = {
                "fontSize": {"magnitude": 11, "unit": "PT"},
                "link": {"headingId": h["heading_id"]},
            }
            if h["level"] == 1:
                text_style["bold"] = True
                style_fields += ",bold"

            requests.append(
                {
                    "updateTextStyle": {
                        "range": {
                            "startIndex": entry_start,
                            "endIndex": entry_end,
                        },
                        "textStyle": text_style,
                        "fields": style_fields,
                    }
                }
            )

        entry_cursor += len(entry_text)

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    print(f"TOC inserted with {len(headings)} entries")


if __name__ == "__main__":
    main()
