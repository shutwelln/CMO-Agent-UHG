#!/usr/bin/env python3
"""
Reddit auto-poster for Saverwell.

Reads from a JSON post queue, submits one post per run via PRAW,
and updates the queue with the result.

Usage:
    python scripts/reddit_poster.py                  # post next queued item
    python scripts/reddit_poster.py --dry-run        # validate queue without posting
    python scripts/reddit_poster.py --post-id 3      # post a specific queue item
    python scripts/reddit_poster.py --list            # show queue status
    python scripts/reddit_poster.py --to-profile  # post to user profile

Requires .env vars:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USERNAME
    REDDIT_PASSWORD
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUEUE_PATH = PROJECT_ROOT / "data" / "saverwell" / "reddit_post_queue.json"
POSTS_DIR = PROJECT_ROOT / "data" / "saverwell" / "reddit_posts"
USER_AGENT = "Saverwell-Poster/1.0 (by u/Saverwell-Info)"


# ---------------------------------------------------------------------------
# Queue helpers
# ---------------------------------------------------------------------------


def load_queue() -> list[dict]:
    """Load the post queue JSON."""
    if not QUEUE_PATH.exists():
        print(f"Error: Queue file not found at {QUEUE_PATH}")
        sys.exit(1)
    with open(QUEUE_PATH) as f:
        return json.load(f)


def save_queue(queue: list[dict]) -> None:
    """Write the queue back to disk."""
    with open(QUEUE_PATH, "w") as f:
        json.dump(queue, f, indent=2)
    print(f"Queue saved to {QUEUE_PATH}")


def get_next_queued(queue: list[dict]) -> dict | None:
    """Return the first item with status 'queued', ordered by id."""
    candidates = [p for p in queue if p["status"] == "queued"]
    if not candidates:
        return None
    return min(candidates, key=lambda p: p["id"])


def get_post_by_id(queue: list[dict], post_id: int) -> dict | None:
    """Find a specific post by id."""
    for p in queue:
        if p["id"] == post_id:
            return p
    return None


def read_post_body(post: dict) -> str:
    """Read the markdown post file and extract the Body section."""
    post_file = PROJECT_ROOT / post["post_file"]
    if not post_file.exists():
        print(f"Error: Post file not found at {post_file}")
        sys.exit(1)

    content = post_file.read_text()

    # Extract body after the "**Body:**" marker
    body_marker = "**Body:**"
    if body_marker in content:
        body = content.split(body_marker, 1)[1].strip()
    else:
        # Fallback: use everything after the --- separator
        parts = content.split("---")
        if len(parts) >= 2:
            body = parts[-1].strip()
        else:
            body = content.strip()

    return body


def clean_formatting(text: str) -> str:
    """Strip AI-style formatting from post body.

    Rules:
      - Remove bold markers (**text**) from mid-paragraph text.
        Keep bold only on standalone lines (section labels on their own line).
      - Replace em dashes and en dashes with spaced hyphens.
      - Remove numbered bold headers like **1. Title** or **Step 1: Title**.
    """
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()

        # Replace em/en dashes everywhere
        line = line.replace("\u2014", " - ").replace("\u2013", " - ")

        # If the entire line (after stripping) is a bold phrase, remove bold.
        # Patterns: **Some Header**, **Step 1: Something**, **1. Something**
        if re.match(r"^\*\*.*\*\*$", stripped):
            line = line.replace("**", "")

        # Remove bold markers wrapping text mid-sentence.
        # Match **word(s)** that appear inside a longer line (not standalone).
        elif "**" in line:
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)

        cleaned.append(line)

    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Reddit API
# ---------------------------------------------------------------------------


def get_reddit_client():
    """Create an authenticated PRAW Reddit instance."""
    try:
        import praw  # noqa: F811
    except ImportError:
        print("Error: praw is not installed. Run: pip install praw")
        sys.exit(1)

    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    username = os.getenv("REDDIT_USERNAME")
    password = os.getenv("REDDIT_PASSWORD")

    missing = []
    if not client_id:
        missing.append("REDDIT_CLIENT_ID")
    if not client_secret:
        missing.append("REDDIT_CLIENT_SECRET")
    if not username:
        missing.append("REDDIT_USERNAME")
    if not password:
        missing.append("REDDIT_PASSWORD")

    if missing:
        print(f"Error: Missing environment variables: {', '.join(missing)}")
        print("Add them to your .env file or export them in your shell.")
        sys.exit(1)

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        username=username,
        password=password,
        user_agent=USER_AGENT,
    )


def submit_post(
    reddit,
    post: dict,
    body: str,
    to_profile: bool = False,
) -> dict:
    """Submit a text post to Reddit. Returns result dict."""
    target = f"u_{reddit.user.me().name}" if to_profile else post["subreddit"]

    print(f"Submitting to r/{target}: {post['title']}")

    subreddit = reddit.subreddit(target)
    submission = subreddit.submit(
        title=post["title"],
        selftext=body,
        send_replies=True,
    )

    return {
        "reddit_url": f"https://reddit.com{submission.permalink}",
        "reddit_id": submission.id,
        "posted_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_list(queue: list[dict]) -> None:
    """Print queue status."""
    print(f"\nReddit Post Queue ({len(queue)} posts)\n{'=' * 60}")
    for p in queue:
        status_icon = {
            "queued": "[ ]",
            "posted": "[x]",
            "failed": "[!]",
        }.get(p["status"], "[?]")

        sub = f"r/{p['subreddit']}"
        title = p["title"][:50] + ("..." if len(p["title"]) > 50 else "")
        week = f"W{p['week']}"
        day = p.get("scheduled_day", "?")

        print(f"  {status_icon} #{p['id']} {week}/{day:<10} {sub:<20} {title}")

        if p["status"] == "posted" and p.get("reddit_url"):
            print(f"       -> {p['reddit_url']}")
        if p["status"] == "failed":
            print("       -> FAILED")

    queued = sum(1 for p in queue if p["status"] == "queued")
    posted = sum(1 for p in queue if p["status"] == "posted")
    failed = sum(1 for p in queue if p["status"] == "failed")
    print(f"\n  Queued: {queued} | Posted: {posted} | Failed: {failed}\n")


def cmd_dry_run(queue: list[dict], post_id: int | None = None) -> None:
    """Validate the queue and show what would be posted."""
    if post_id:
        post = get_post_by_id(queue, post_id)
        if not post:
            print(f"Error: No post with id {post_id}")
            sys.exit(1)
        posts_to_check = [post]
    else:
        post = get_next_queued(queue)
        if not post:
            print("No queued posts remaining.")
            return
        posts_to_check = [post]

    for p in posts_to_check:
        body = clean_formatting(read_post_body(p))
        print(f"\n{'=' * 60}")
        print(f"Post #{p['id']}")
        print(f"Title: {p['title']}")
        print(f"Subreddit: r/{p['subreddit']}")
        print(f"Week: {p['week']} / {p.get('scheduled_day', 'unscheduled')}")
        print(f"Status: {p['status']}")
        print(f"Source guide: {p.get('source_guide', 'Reddit-only')}")
        print(f"Body length: {len(body)} chars / ~{len(body.split())} words")
        print(f"Includes Saverwell link: {p.get('includes_saverwell_link', False)}")
        print(f"{'=' * 60}")
        print(f"\n{body[:500]}...")
        print(f"\n[DRY RUN] Would submit to r/{p['subreddit']}")


def cmd_post(
    queue: list[dict],
    post_id: int | None = None,
    to_profile: bool = False,
) -> None:
    """Submit a post to Reddit."""
    if post_id:
        post = get_post_by_id(queue, post_id)
        if not post:
            print(f"Error: No post with id {post_id}")
            sys.exit(1)
        if post["status"] == "posted":
            print(f"Post #{post_id} has already been posted: {post.get('reddit_url')}")
            sys.exit(1)
    else:
        post = get_next_queued(queue)
        if not post:
            print("No queued posts remaining. All posts have been submitted.")
            return

    body = clean_formatting(read_post_body(post))
    reddit = get_reddit_client()

    try:
        result = submit_post(reddit, post, body, to_profile=to_profile)
        post["status"] = "posted"
        post["reddit_url"] = result["reddit_url"]
        post["reddit_id"] = result["reddit_id"]
        post["posted_at"] = result["posted_at"]
        save_queue(queue)
        print("\nPosted successfully!")
        print(f"URL: {result['reddit_url']}")
    except Exception as e:
        post["status"] = "failed"
        post["notes"] = f"{post.get('notes', '')} | Error: {str(e)}"
        save_queue(queue)
        print(f"\nFailed to post: {e}")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Saverwell Reddit auto-poster",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/reddit_poster.py --dry-run          # preview next post
  python scripts/reddit_poster.py --list             # show queue status
  python scripts/reddit_poster.py                    # post next queued item
  python scripts/reddit_poster.py --post-id 3        # post specific item
  python scripts/reddit_poster.py --to-profile       # post to your profile
        """,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview without posting",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Show queue status",
    )
    parser.add_argument(
        "--post-id",
        type=int,
        default=None,
        help="Post a specific queue item by ID",
    )
    parser.add_argument(
        "--to-profile",
        action="store_true",
        help="Post to your user profile instead of the target subreddit",
    )

    args = parser.parse_args()

    # Load dotenv if available
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env")
    except ImportError:
        pass  # dotenv not installed, rely on env vars

    queue = load_queue()

    if args.list:
        cmd_list(queue)
    elif args.dry_run:
        cmd_dry_run(queue, post_id=args.post_id)
    else:
        cmd_post(queue, post_id=args.post_id, to_profile=args.to_profile)


if __name__ == "__main__":
    main()
