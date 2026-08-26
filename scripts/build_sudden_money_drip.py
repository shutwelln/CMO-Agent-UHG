"""Build the 'Sudden Money After 55' email drip campaign for Saverwell.

Invokes Lifecycle Marketing Agent, Writer Agent, and Docs Agent via CMOSession.
Run: cd /path/to/CMO\ Agent && source .venv/bin/activate && python scripts/build_sudden_money_drip.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.runtime.session import CMOSession  # noqa: E402


WORKSPACE = "saverwell"

# Reddit context to repurpose
REDDIT_CONTEXT = (
    "Two Reddit threads scored 24+: 'I came into some money, now what?' and "
    "'Old person offering personal loan backed by inheritance'. These signal seniors "
    "navigating unexpected windfalls or estate situations with no clear guidance."
)

BRAND_RULES = (
    "Saverwell brand voice: warm & empathetic, clear and direct, no jargon, "
    "never use 'elderly' or patronizing language. Use 'seniors', 'retirees', "
    "'experienced savers'. Short paragraphs (2-3 sentences), bullet points, "
    "scannable headers, no excessive emojis."
)

STEPS = [
    {
        "name": "Step 1: Lifecycle Flow Design",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to design a "
            "complete lifecycle flow.\n\n"
            "Flow type: 'Email Drip - Sudden Money After 55: A Week-by-Week Action Plan'\n\n"
            "Goal: Convert Reddit-sourced windfall/inheritance audience into engaged "
            "Saverwell subscribers via a 4-email drip sequence gated behind a landing page, "
            "using Customer.io event-triggered automation.\n\n"
            "Channels: email only\n\n"
            f"Audience: Seniors (55+) navigating unexpected windfalls, inheritances, or estate "
            f"situations with no clear financial guidance. {REDDIT_CONTEXT}\n\n"
            "Email cadence:\n"
            "- Email 1 (Day 0): Welcome + orientation — validate their situation, preview the plan\n"
            "- Email 2 (Day 2): First action steps — immediate financial triage\n"
            "- Email 3 (Day 5): Deeper planning — longer-term strategy\n"
            "- Email 4 (Day 7): Next steps + CTA — Saverwell tools/resources\n\n"
            "Platform: Customer.io with event-triggered campaign entry via "
            "'landed_sudden_money_page' event.\n\n"
            f"{BRAND_RULES}\n\n"
            "Save the result as a draft."
        ),
    },
    {
        "name": "Step 2: Email 1 — Welcome + Orientation (Day 0)",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to write a "
            "message framework for the FIRST email in the 'Sudden Money After 55' drip.\n\n"
            "Channel: email\n"
            "Flow stage: welcome / Day 0\n"
            "Audience segment: Seniors 55+ who just landed on the Sudden Money landing page — "
            "navigating unexpected windfalls, inheritance, or estate situations\n"
            "Goal: Validate their emotional situation, build trust, preview the 4-email "
            "week-by-week action plan, and set expectations for the sequence.\n\n"
            f"{BRAND_RULES}\n\n"
            f"Reddit framing to repurpose: {REDDIT_CONTEXT}\n\n"
            "Include: 3-5 subject line options, preview text, full body copy framework, "
            "3 CTA variants, personalization tokens. Save as draft."
        ),
    },
    {
        "name": "Step 3: Email 2 — First Action Steps (Day 2)",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to write a "
            "message framework for the SECOND email in the 'Sudden Money After 55' drip.\n\n"
            "Channel: email\n"
            "Flow stage: activation / Day 2\n"
            "Audience segment: Seniors 55+ navigating unexpected windfalls or inheritance — "
            "they opened Email 1 (welcome) 2 days ago\n"
            "Goal: Provide concrete, immediate financial triage steps for the first week "
            "after receiving unexpected money. Actionable, not theoretical.\n\n"
            "Key content angles:\n"
            "- Don't make any big decisions yet (park the money safely)\n"
            "- Tell 2 people, not 20 (privacy protection)\n"
            "- Get a simple snapshot of current finances\n"
            "- Identify urgent obligations first (medical bills, taxes owed)\n\n"
            f"{BRAND_RULES}\n\n"
            "Include: 3-5 subject line options, preview text, full body copy framework, "
            "3 CTA variants, personalization tokens. Save as draft."
        ),
    },
    {
        "name": "Step 4: Email 3 — Deeper Planning (Day 5)",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to write a "
            "message framework for the THIRD email in the 'Sudden Money After 55' drip.\n\n"
            "Channel: email\n"
            "Flow stage: engagement / Day 5\n"
            "Audience segment: Seniors 55+ navigating sudden money — engaged through "
            "emails 1-2, now ready for deeper planning\n"
            "Goal: Guide them through longer-term financial planning: who to talk to, "
            "how to think about allocation, common mistakes to avoid.\n\n"
            "Key content angles:\n"
            "- When to talk to a financial advisor (and what to ask)\n"
            "- The 3-bucket approach: immediate needs, medium-term, long-term\n"
            "- Common mistakes seniors make with windfalls (scam vulnerability, family pressure)\n"
            "- Tax implications they should know about\n\n"
            f"{BRAND_RULES}\n\n"
            "Include: 3-5 subject line options, preview text, full body copy framework, "
            "3 CTA variants, personalization tokens. Save as draft."
        ),
    },
    {
        "name": "Step 5: Email 4 — Next Steps + CTA (Day 7)",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to write a "
            "message framework for the FOURTH and FINAL email in the 'Sudden Money After 55' drip.\n\n"
            "Channel: email\n"
            "Flow stage: conversion / Day 7\n"
            "Audience segment: Seniors 55+ who completed the 3-email journey — now warm, "
            "trusting, and ready for next steps\n"
            "Goal: Summarize the week's action plan, introduce Saverwell as their "
            "ongoing resource, drive to Saverwell tools/signup/further engagement.\n\n"
            "Key content angles:\n"
            "- Recap: what they've accomplished in 7 days\n"
            "- What Saverwell can help with going forward\n"
            "- Specific tool/resource CTA (benefit finder, savings calculator, etc.)\n"
            "- Warm close: 'You've got this' empowerment message\n\n"
            f"{BRAND_RULES}\n\n"
            "Include: 3-5 subject line options, preview text, full body copy framework, "
            "3 CTA variants, personalization tokens. Save as draft."
        ),
    },
    {
        "name": "Step 6: Landing Page Spec",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Writer Agent to create a full landing page "
            "specification for the 'Sudden Money After 55: A Week-by-Week Action Plan' "
            "email drip gate page.\n\n"
            "This is a lead capture landing page where seniors sign up to receive the "
            "4-email drip sequence.\n\n"
            "Include ALL of the following:\n"
            "1. **Headline** (3 options ranked)\n"
            "2. **Subheadline**\n"
            "3. **Hero body copy** (2-3 short paragraphs, empathetic, validating)\n"
            "4. **What you'll learn bullets** (4 items matching the 4 emails)\n"
            "5. **Form fields** (name, email — minimal friction)\n"
            "6. **CTA button text** (3 options)\n"
            "7. **Trust signals** (no spam promise, unsubscribe anytime, privacy note)\n"
            "8. **Thank-you page copy** (confirmation + what to expect)\n"
            "9. **Layout wireframe description** (section-by-section, mobile-first)\n"
            "10. **Meta title and description** for SEO\n\n"
            f"Audience: {REDDIT_CONTEXT}\n\n"
            f"{BRAND_RULES}\n\n"
            "Save as a draft."
        ),
    },
    {
        "name": "Step 7: Customer.io Trigger Logic",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Lifecycle Marketing Agent to define "
            "trigger logic for the 'Sudden Money After 55' email drip.\n\n"
            "Flow name: Sudden Money After 55 Email Drip\n"
            "Platform: Customer.io\n"
            "Available events: landed_sudden_money_page, email_opened, email_clicked, "
            "signed_up, tool_used\n\n"
            "The campaign should:\n"
            "- Trigger on 'landed_sudden_money_page' event (fired when user submits "
            "the landing page form)\n"
            "- Set attribute 'sudden_money_drip_entered = true' on entry\n"
            "- Send Email 1 immediately (Day 0)\n"
            "- Wait 2 days → Send Email 2 (Day 2)\n"
            "- Wait 3 more days → Send Email 3 (Day 5)\n"
            "- Wait 2 more days → Send Email 4 (Day 7)\n"
            "- Goal: person performs 'signed_up' or 'tool_used' event → exit as converted\n"
            "- Exit condition: person unsubscribes → exit immediately\n"
            "- Frequency cap: suppress if person received any other Saverwell campaign "
            "email in last 24 hours\n\n"
            "Include: event taxonomy, trigger conditions, delay logic, branching rules, "
            "exit conditions, frequency capping, Customer.io-specific setup instructions, "
            "and testing checklist. Save as draft."
        ),
    },
    {
        "name": "Step 8: Google Doc — All Deliverables",
        "prompt": (
            f"For workspace {WORKSPACE}: Use the Docs Agent to create a Google Doc titled "
            "'Sudden Money After 55 — Email Drip Campaign (Saverwell)'.\n\n"
            "Compile ALL the drafts we just created into a single polished document:\n\n"
            "1. **Campaign Overview** — brief summary of the campaign, audience, and goal\n"
            "2. **Lifecycle Flow Design** — the flow architecture from our lifecycle flow draft\n"
            "3. **Email 1: Welcome + Orientation (Day 0)** — full message framework\n"
            "4. **Email 2: First Action Steps (Day 2)** — full message framework\n"
            "5. **Email 3: Deeper Planning (Day 5)** — full message framework\n"
            "6. **Email 4: Next Steps + CTA (Day 7)** — full message framework\n"
            "7. **Landing Page Specification** — full page spec with wireframe\n"
            "8. **Customer.io Implementation Spec** — trigger logic, segments, technical setup\n\n"
            "Pull all content from the most recent saverwell drafts. Format cleanly "
            "with headers, bullet points, and clear section breaks. This document will be "
            "the single source of truth for the campaign build."
        ),
    },
]


async def main() -> None:
    results = []
    async with CMOSession() as session:
        for i, step in enumerate(STEPS):
            print(f"\n{'='*60}")
            print(f"  {step['name']}")
            print(f"{'='*60}\n")

            response = await session.ask(step["prompt"])

            print(f"Status: {response.status}")
            print(f"Actions: {response.actions_taken}")
            print(f"Response preview: {response.text[:300]}...")
            print()

            results.append(
                {
                    "step": step["name"],
                    "status": response.status,
                    "actions": response.actions_taken,
                    "artifacts": response.artifacts,
                    "text_length": len(response.text),
                }
            )

    # Write summary
    summary_path = Path("data/sudden_money_build_log.json")
    summary_path.write_text(json.dumps(results, indent=2))
    print(f"\nBuild log saved to {summary_path}")
    print(f"Completed {len(results)} steps.")


if __name__ == "__main__":
    asyncio.run(main())
