"""End-to-end batch FraudWatch conversion runner.

Instantiates the real WriterAgent with the real LLM, DB, and workspace manager,
then runs batch_convert_fraudwatch on the newsletters directory.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def main() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.text.proofreader import Proofreader
    from cmo_agent.workspace.manager import WorkspaceManager

    settings = Settings()

    # Init DB (initialize() creates connection + runs schema DDL)
    db = Database(settings.db_path)
    await db.initialize()

    # Init LLM (use the writing model — Sonnet)
    writing_llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
    )
    scanning_llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_scanning,
    )

    # Init proofreader
    proofreader = Proofreader(llm=scanning_llm)

    # Init workspace manager
    workspace_mgr = WorkspaceManager(db=db)

    # Init WriterAgent
    from cmo_agent.agents.writer import WriterAgent

    writer = WriterAgent(
        llm=writing_llm,
        db=db,
        workspace_manager=workspace_mgr,
        proofreader=proofreader,
    )

    # Run batch conversion
    newsletters_dir = os.path.join(
        os.path.dirname(__file__),
        "..",
        "data",
        "example_files",
        "saverwell",
        "charlie-fraudwatch",
        "newsletters",
    )
    newsletters_dir = os.path.abspath(newsletters_dir)
    print(f"Converting PDFs from: {newsletters_dir}")
    print("=" * 70)

    result = await writer._batch_convert_fraudwatch(newsletters_dir)

    print(f"\n{'=' * 70}")
    print(f"Total: {result.get('total', 0)}")
    print(f"Success: {result.get('success', 0)}")
    print(f"Failed: {result.get('failed', 0)}")
    print(f"{'=' * 70}")

    for r in result.get("results", []):
        if "error" in r:
            print(f"  FAIL  {r['filename']}: {r['error']}")
        else:
            print(f"  OK    {r['filename']} -> slug={r['slug']}, draft_id={r['draft_id']}")

    # Query drafts table for recent protection_article rows
    print(f"\n{'=' * 70}")
    print("Recent protection_article drafts from SQLite:")
    from cmo_agent.db.repositories import DraftRepo

    drafts_repo = DraftRepo(db)
    recent = await drafts_repo.list_recent(
        workspace_id="saverwell",
        days=1,
        limit=10,
        content_type="protection_article",
    )
    for d in recent:
        try:
            body_data = json.loads(d.body)
            slug = body_data.get("slug", "?")
        except Exception:
            slug = "?"
        print(f"  id={d.id[:12]}...  slug={slug}  created_at={d.created_at}")

    await db.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
