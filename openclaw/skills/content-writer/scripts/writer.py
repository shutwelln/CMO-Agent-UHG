"""Content Writer skill — OpenClaw executable script.

Called by OpenClaw when the content-writer skill is triggered.
Communicates with the FastAPI service layer for brand voice and proofreading.

Usage (from OpenClaw):
    python writer.py --workspace saverwell --type blog_post --topic "..."
    python writer.py --workspace dsdn --type newsletter --topic "..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

import requests

SERVICE_URL = os.environ.get("CMO_SERVICE_URL", "http://localhost:8100")


def load_brand_voice(workspace_id: str) -> str:
    """Load brand voice from the service layer."""
    resp = requests.get(f"{SERVICE_URL}/api/brand-voice/{workspace_id}", timeout=10)
    if resp.status_code == 404:
        print(f"[WARN] No brand voice found for '{workspace_id}', using generic voice")
        return ""
    resp.raise_for_status()
    return resp.json()["brand_voice"]


def proofread(text: str, preserve_terms: Optional[list] = None, context: str = "") -> dict:
    """Proofread text via the service layer."""
    resp = requests.post(
        f"{SERVICE_URL}/api/proofread",
        json={
            "text": text,
            "preserve_terms": preserve_terms or [],
            "context": context,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def extract_brand_terms(brand_voice: str) -> list:
    """Extract brand-specific terms to preserve during proofreading."""
    terms = []
    for line in brand_voice.split("\n"):
        line = line.strip()
        if line.startswith("BRAND:"):
            terms.append(line.split(":", 1)[1].strip())
        if line.startswith("PARENT COMPANY:"):
            terms.append(line.split(":", 1)[1].strip())
        # Extract quoted terms from brand voice
        if '"' in line:
            import re
            quoted = re.findall(r'"([^"]+)"', line)
            terms.extend(quoted)
    return list(set(terms))


def build_prompt(
    content_type: str,
    topic: str,
    brand_voice: str,
    target_length: str = "medium",
    seo_keywords: Optional[list] = None,
    geo_optimize: bool = True,
) -> str:
    """Build the content generation prompt."""

    length_map = {
        "short": "approximately 300 words",
        "medium": "approximately 800 words",
        "long": "approximately 1500 words",
    }
    length_instruction = length_map.get(target_length, length_map["medium"])

    prompt_parts = [
        f"You are an expert marketing content writer. Write a {content_type.replace('_', ' ')} about: {topic}",
        f"\nTarget length: {length_instruction}.",
    ]

    if brand_voice:
        prompt_parts.append(f"\n## Brand Voice (follow exactly)\n\n{brand_voice}")

    prompt_parts.append("""
## Writing Rules

- Short paragraphs (2-3 sentences max)
- Use headers (H2, H3) for scannability
- Bullet points for lists of 3+ items
- No filler phrases ("In today's fast-paced world...", "It's no secret that...")
- No generic AI marketing language ("personalized", "cutting-edge", "revolutionary")
- Flag any unverified statistical claims with [VERIFY]
- Spell out abbreviations on first use — e.g., "Customer Acquisition Cost (CAC)"
- After first occurrence, use the abbreviation only
""")

    if seo_keywords:
        prompt_parts.append(f"\n## SEO Keywords (weave naturally, max once per 200 words)\n{', '.join(seo_keywords)}")

    if geo_optimize and content_type in ("blog_post", "article", "long_form"):
        prompt_parts.append("""
## GEO Optimization (Princeton Citation Framework)

Apply these techniques to maximize AI engine citation probability:

1. **Cite Sources (+40%)**: Include 3-5 authoritative source references. Use "According to [Source]..."
2. **Include Statistics (+30%)**: Embed 4-6 specific stats with attribution. Use exact numbers.
3. **Add Quotations (+25%)**: Include 1-2 real, attributed expert quotes.
4. **Fluency (+15%)**: Vary sentence structure. Mix short and compound sentences.
5. **Authoritative Tone (+12%)**: "The data shows" not "It might be the case that."
6. **Technical Terms (+10%)**: Use precise industry terms with brief definitions.
7. **AVOID Keyword Stuffing (-10%)**: Never repeat keywords unnaturally.

Structure for AI engines:
- FAQ section at the end (3-5 questions with concise answers)
- Clear H2 headers that match search queries
- Statistics in the first 200 words (Perplexity prioritizes early data)
- Source citations inline (ChatGPT prioritizes attributed claims)
""")

    type_instructions = {
        "blog_post": "Format as a blog post with a compelling headline, introduction hook, body sections with H2 headers, and a conclusion with CTA.",
        "newsletter": "Format as a newsletter with subject line, preview text, greeting, 2-3 content sections, and CTA. Include 3 subject line variants.",
        "social_post": "Write platform-optimized posts. Include hashtags, CTA, and character count. Adapt tone per platform.",
        "email": "Write marketing email with subject line, preview text, body, and CTA. Include 3 subject line variants and send time recommendation.",
        "article": "Format as a long-form article with headline, subtitle, introduction, body sections with H2/H3 headers, expert quotes, and conclusion.",
        "reddit_reply": "Write a helpful, non-promotional reply that adds genuine value. Follow anti-self-promotion rules. Be conversational, not corporate.",
        "landing_page": "Write landing page copy: hero headline + subhead, 3-4 benefit sections, social proof section, FAQ, and primary CTA.",
    }
    if content_type in type_instructions:
        prompt_parts.append(f"\n## Format\n{type_instructions[content_type]}")

    return "\n".join(prompt_parts)


def estimate_reading_time(text: str) -> int:
    """Estimate reading time in minutes (average 250 wpm)."""
    words = len(text.split())
    return max(1, round(words / 250))


def count_verify_flags(text: str) -> list:
    """Extract [VERIFY] flagged claims."""
    import re
    flags = []
    for match in re.finditer(r'\[VERIFY\][^\n]*', text):
        flags.append(match.group(0))
    return flags


def format_output(
    content: str,
    content_type: str,
    topic: str,
    corrections: list,
    verify_flags: list,
) -> str:
    """Format the final output for Slack delivery."""
    word_count = len(content.split())
    reading_time = estimate_reading_time(content)

    output_parts = [content]

    output_parts.append(f"\n---\n**Word count:** {word_count} | **Reading time:** ~{reading_time} min")

    if verify_flags:
        output_parts.append(f"\n**[VERIFY] flags ({len(verify_flags)}):**")
        for flag in verify_flags:
            output_parts.append(f"- {flag}")

    if corrections:
        output_parts.append(f"\n**Proofreading corrections ({len(corrections)}):**")
        for c in corrections[:5]:  # Show max 5
            output_parts.append(f"- \"{c.get('original', '')}\" → \"{c.get('corrected', '')}\" ({c.get('reason', '')})")

    return "\n".join(output_parts)


def main():
    parser = argparse.ArgumentParser(description="Content Writer Skill")
    parser.add_argument("--workspace", default="saverwell", help="Workspace ID for brand voice")
    parser.add_argument("--type", default="blog_post", dest="content_type",
                        choices=["blog_post", "newsletter", "social_post", "email", "article", "reddit_reply", "landing_page"])
    parser.add_argument("--topic", required=True, help="Content topic")
    parser.add_argument("--length", default="medium", choices=["short", "medium", "long"])
    parser.add_argument("--keywords", nargs="*", help="SEO keywords")
    parser.add_argument("--no-geo", action="store_true", help="Disable GEO optimization")
    parser.add_argument("--no-proofread", action="store_true", help="Skip proofreading")
    args = parser.parse_args()

    # Step 1: Load brand voice
    print(f"[content-writer] Loading brand voice for '{args.workspace}'...")
    brand_voice = load_brand_voice(args.workspace)

    # Step 2: Build prompt
    prompt = build_prompt(
        content_type=args.content_type,
        topic=args.topic,
        brand_voice=brand_voice,
        target_length=args.length,
        seo_keywords=args.keywords,
        geo_optimize=not args.no_geo,
    )

    # Step 3: Output the prompt for OpenClaw's LLM to process
    # OpenClaw handles the actual LLM call — we provide the prompt
    print("---PROMPT_START---")
    print(prompt)
    print("---PROMPT_END---")

    # Note: In OpenClaw, the LLM processes this prompt and returns content.
    # The script below handles post-processing after OpenClaw's LLM responds.
    # This is invoked as a second pass with --post-process flag.


def post_process(content: str, workspace_id: str, content_type: str, topic: str):
    """Post-process LLM output: proofread and format."""
    # Extract brand terms for preservation
    brand_voice = load_brand_voice(workspace_id)
    preserve_terms = extract_brand_terms(brand_voice)

    # Proofread
    print(f"[content-writer] Proofreading...")
    result = proofread(
        text=content,
        preserve_terms=preserve_terms,
        context=f"Brand: {workspace_id}, Type: {content_type}",
    )
    final_content = result["corrected_text"]
    corrections = result["corrections"]

    # Check for verify flags
    verify_flags = count_verify_flags(final_content)

    # Format output
    output = format_output(
        content=final_content,
        content_type=content_type,
        topic=topic,
        corrections=corrections,
        verify_flags=verify_flags,
    )

    print(output)
    return output


if __name__ == "__main__":
    if "--post-process" in sys.argv:
        # Read content from stdin for post-processing
        sys.argv.remove("--post-process")
        content = sys.stdin.read()
        parser = argparse.ArgumentParser()
        parser.add_argument("--workspace", default="saverwell")
        parser.add_argument("--type", default="blog_post", dest="content_type")
        parser.add_argument("--topic", default="")
        args, _ = parser.parse_known_args()
        post_process(content, args.workspace, args.content_type, args.topic)
    else:
        main()
