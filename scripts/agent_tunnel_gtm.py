#!/usr/bin/env python3
"""Generate Agent Tunnel GTM strategy: Google Doc + Pitch Deck."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.runtime.session import CMOSession  # noqa: E402

GTM_DOC_PROMPT = """For workspace agent_tunnel, create a Google Doc with a comprehensive Go-to-Market strategy for Agent Tunnel.

Agent Tunnel is a Mac desktop app that lets you remote-control Claude Code from your smartphone via a secure Cloudflare tunnel. The product is live at agenttunnel.app. Founders: Nick and Justin. Budget is lean ($500-2k/mo), audience is zero, product is ready now.

The document should be structured as a detailed internal execution plan with these sections:

## 1. Executive Summary
One-page overview: product, market opportunity, strategy thesis, 90-day goals (500 paid users, 3:1 LTV:CAC, organic flywheel spinning).

## 2. Product Overview & Competitive Landscape
- What Agent Tunnel does (Mac app, Cloudflare tunnel, mobile Claude Code access)
- How it works (Install → Scan QR → Control from phone)
- Security model (Cloudflare tunnel encryption, Face ID/Touch ID, no exposed ports)
- Competitive alternatives: SSH tunnels (complex), screen sharing (laggy/insecure), nothing (desk-bound)
- Agent Tunnel's differentiation: security + simplicity, compliance-friendly, no terminal config needed

## 3. Target Market & ICP
- Beachhead: Busy Claude Code power users (parents, professionals, mobile-first workers)
- Demographics: 28-50, tech-comfortable, values time and productivity
- Psychographics: Willing to pay for convenience, security-conscious
- TAM: All Claude Code users. SAM: Mac users with smartphones. SOM: Power users who hit mobility friction daily

## 4. Positioning & Messaging Framework
- Primary value prop: "Claude Code in your pocket — secure, simple, mobile-first"
- 3 pillars: Security (Cloudflare + Face ID), Simplicity (no SSH/VPN), Mobility (work from anywhere)
- Competitive positioning matrix vs. SSH, VPN, screen sharing, nothing
- Key messages by audience segment

## 5. Pricing Strategy
- Free trial: 14-day full-feature trial (no credit card required)
- Monthly: $15/mo
- Annual: $150/yr ($12.50/mo effective — 17% discount)
- Early adopter: First 100 users grandfathered at $10/mo forever (creates urgency)
- Lifetime: $500 one-time (limit 50 seats)

## 6. Channel Strategy (Organic, Paid, Earned, Community)
Detailed channel-by-channel breakdown:

| Channel | Funnel Role | Monthly Budget | Priority |
|---------|-------------|----------------|----------|
| Organic SEO | Top-of-funnel awareness | $0 | P0 |
| Reddit (organic) | Awareness + social proof | $0 | P0 |
| ProductHunt launch | One-time spike | $0 | P0 |
| Hacker News Show HN | One-time spike | $0 | P0 |
| Dev newsletter sponsorships | Targeted awareness | $400-800/mo | P1 |
| YouTube/Twitter video demos | Awareness + conversion | $0-200/mo | P1 |
| Google Ads (branded + intent) | Bottom-of-funnel capture | $300-500/mo | P1 |
| Reddit Ads | Mid-funnel retargeting | $200-400/mo | P2 |
| Referral program | Viral loop | $0 (credit-based) | P0 |
| Affiliate/creator program | Earned distribution | $5-10/conversion | P2 |
| Discord community | Retention + advocacy | $0 | P0 |

Include specific tactical playbooks for each P0 channel.

## 7. Full-Funnel Architecture & Conversion Optimization
Awareness (SEO, Reddit, PH, newsletters) → Landing page (agenttunnel.app) → Free trial signup (14-day, no CC) → Activation (first mobile connection) → Engagement (daily usage) → Conversion (trial→paid at day 10-14) → Retention (lifecycle emails, community) → Referral (invite friends, earn free months)

Key metrics at each stage:
- Landing → Trial: 8-12% signup rate
- Trial → Activation: 60%+ first-connection within 24hrs
- Activation → Paid: 15-25% trial-to-paid
- Paid → Retained: 80%+ D30 retention
- Retained → Referral: 10% referral rate

## 8. Lifecycle Marketing & Retention
Full trial onboarding email sequence:
- Day 0: Welcome — download link, setup guide
- Day 1: Setup nudge — 60-second video walkthrough
- Day 3: Power user tips — voice input, push notifications, shortcuts
- Day 5: Social proof — early user testimonials
- Day 7: Mid-trial check-in — usage stats
- Day 10: Conversion nudge — early-adopter pricing deadline
- Day 13: Last chance — trial ending tomorrow
- Day 14: Trial expired — config saved, reactivate anytime
- Day 21: Win-back — 20% off first month

## 9. Retargeting Strategy
- Website visitors who didn't sign up → demo video ads on Google/Reddit
- Trial users who didn't activate → email + in-app nudges
- Trial users who didn't convert → win-back at day 21 + day 45
- Churned paid users → quarterly re-engagement with new features

## 10. Launch Phases & Timeline
Phase 1 — Validation (Weeks 1-3): ProductHunt, Show HN, Reddit seeding, Discord, referral program, 3-5 SEO posts. Exit: 100 trials, 40%+ activation.
Phase 2 — Controlled Launch (Weeks 4-8): Google Ads, newsletter sponsorships, demo videos, affiliate program, Windows/Linux waitlist. Exit: 300 trials, 20%+ trial-to-paid, CAC <$50.
Phase 3 — Scaled Expansion (Weeks 9-16): Scale paid channels, Windows/Linux launch, partnerships, 50+ SEO pages, creator partnerships. Exit: 500 paid users, LTV:CAC >3:1.

## 11. Unit Economics & Financial Model
- Price: $15/mo
- Average lifetime: 12 months
- Gross margin: ~90%
- LTV: $15 × 12 × 0.9 = $162
- Target CAC (blended): $40-50
- LTV:CAC: 3.2-4.0x
- Break-even: ~Month 4 with 100 paid users at $1.5k/mo spend

## 12. Risk Assessment & Mitigation
- Low initial traffic → PH + Reddit seeding (free, immediate)
- Activation friction → video walkthroughs, simplified onboarding
- Platform dependency → Anthropic ecosystem relationship
- Competition → differentiate on security/compliance + community
- Budget constraints → $0 channels first, scale paid after CAC validation

## 13. Appendix
- SEO keyword targets (20+ target keywords with search intent)
- Email sequence detail (subject lines, CTAs for each email)
- Reddit strategy (subreddits, post types, engagement rules)
- ProductHunt launch checklist
- Referral program mechanics

Make this a thorough, actionable document that serves as the internal execution playbook. Use the Agent Tunnel brand voice (confident, approachable, productivity-focused). Include specific numbers, timelines, and tactical details throughout."""

PITCH_DECK_PROMPT = """For workspace agent_tunnel, create a Google Slides pitch deck telling the Agent Tunnel Go-to-Market story.

Agent Tunnel is a Mac desktop app that lets you remote-control Claude Code from your smartphone via a secure Cloudflare tunnel. Live at agenttunnel.app. Founders: Nick and Justin. Budget: $500-2k/mo. Audience: zero. Product: ready now.

Create a 12-14 slide pitch deck with this outline:

Slide 1 — Title: "Agent Tunnel: Go-to-Market Plan"
Subtitle: "Claude Code in your pocket — secure, simple, mobile-first"

Slide 2 — The Problem: Claude Code users are desk-bound. You can't code from your phone, the couch, or your kid's soccer game. SSH tunnels are complex. Screen sharing is laggy. Most people just... don't.

Slide 3 — The Solution: Secure mobile access via Cloudflare tunnel. Install the Mac app, scan a QR code, control Claude Code from your phone. Three steps, under 5 minutes.

Slide 4 — How It Works: 3-step visual. Step 1: Install Agent Tunnel on your Mac. Step 2: Scan the QR code with your phone. Step 3: Full Claude Code access from anywhere.

Slide 5 — Security Model: Cloudflare tunnel (no exposed ports), Face ID/Touch ID authentication, end-to-end encryption. Enterprise-grade security, zero configuration.

Slide 6 — Target Market: ICP profile. Busy professionals using Claude Code, 28-50 age range, tech-comfortable, values time. TAM/SAM/SOM breakdown.

Slide 7 — Competitive Landscape: 2x2 matrix. X-axis: Simple → Complex. Y-axis: Secure → Risky. Agent Tunnel in top-left (simple + secure). SSH in top-right (secure but complex). Screen sharing in bottom-left (simple but risky). Nothing in bottom-right.

Slide 8 — Pricing & Business Model: $15/mo SaaS, 14-day free trial (no CC), $150/yr annual plan, early-adopter $10/mo forever (first 100), $500 lifetime (limit 50).

Slide 9 — GTM Strategy Overview: Channel mix visual showing P0 ($0 channels: SEO, Reddit, PH, HN, referrals), P1 ($400-800: newsletters, Google Ads, video), P2 ($200-400: Reddit Ads, affiliates).

Slide 10 — Full Funnel: Awareness → Landing → Trial → Activation → Engagement → Conversion → Retention → Referral. With target conversion rates at each stage.

Slide 11 — Launch Phases: 3-phase timeline. Phase 1 (Weeks 1-3): Validation — 100 trials. Phase 2 (Weeks 4-8): Controlled Launch — 300 trials, CAC <$50. Phase 3 (Weeks 9-16): Scaled Expansion — 500 paid users, 3:1 LTV:CAC.

Slide 12 — Unit Economics: LTV $162, CAC $40-50, LTV:CAC 3.2-4.0x, break-even ~Month 4 with 100 paid users, 90% gross margin.

Slide 13 — 90-Day Goals: 500 paid users, 3:1 LTV:CAC ratio, organic flywheel spinning, Discord community of 1,000+, 3 newsletter sponsorships running.

Slide 14 — Next Steps: What we need now — finalize trial onboarding flow, schedule ProductHunt launch, set up Google Ads, build referral program, start SEO content production.

Output format: google_slides. Make it visually clean, use the Agent Tunnel brand voice, and ensure the narrative flows as a compelling story from problem to solution to execution plan."""


async def main() -> None:
    """Generate GTM doc and deck."""
    print("=" * 60)
    print("Agent Tunnel GTM — Generating deliverables")
    print("=" * 60)

    async with CMOSession() as session:
        # 1. Google Doc
        print("\n[1/2] Creating GTM Strategy Google Doc...")
        doc_response = await session.ask(GTM_DOC_PROMPT)
        print(f"\nDoc response text:\n{doc_response.text[:500]}...")
        print(f"\nActions taken: {doc_response.actions_taken}")
        print(f"Artifacts: {doc_response.artifacts}")

        doc_url = None
        for artifact in doc_response.artifacts:
            if artifact.get("type") == "doc":
                doc_url = artifact.get("url")
                print(f"\n>>> GOOGLE DOC URL: {doc_url}")

        # 2. Pitch Deck
        print("\n" + "=" * 60)
        print("[2/2] Creating GTM Pitch Deck...")
        deck_response = await session.ask(PITCH_DECK_PROMPT)
        print(f"\nDeck response text:\n{deck_response.text[:500]}...")
        print(f"\nActions taken: {deck_response.actions_taken}")
        print(f"Artifacts: {deck_response.artifacts}")

        deck_url = None
        for artifact in deck_response.artifacts:
            if artifact.get("type") == "deck":
                deck_url = artifact.get("url")
                print(f"\n>>> GOOGLE SLIDES URL: {deck_url}")

        # Summary
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        print(f"Google Doc:    {doc_url or 'NOT CREATED'}")
        print(f"Google Slides: {deck_url or 'NOT CREATED'}")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
