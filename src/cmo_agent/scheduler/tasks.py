"""Predefined scheduled tasks for agent operations."""

from __future__ import annotations

from typing import Any, Dict, List

import structlog

from ..agents.registry import AgentRegistry
from ..db.database import Database
from ..db.repositories import ApprovedIdeaRepo, WorkspaceRepo
from ..n8n.client import N8NClient

logger = structlog.get_logger()

# Cache of channels the bot has already joined this session
_joined_channels: set[str] = set()


async def _ensure_bot_in_channel(slack_client: Any, channel: str) -> None:
    """Join the Slack channel if not already a member.

    Uses conversations.join which is a no-op if already in the channel.
    Caches joined channels to avoid repeated API calls.
    """
    if channel in _joined_channels:
        return
    try:
        await slack_client.conversations_join(channel=channel)
        _joined_channels.add(channel)
        logger.info("bot_joined_channel", channel=channel)
    except Exception as e:
        # conversations_join needs a channel ID, not a name. Try to look it up.
        error_str = str(e)
        if "channel_not_found" in error_str and channel.startswith("#"):
            try:
                # Look up the channel by name
                result = await slack_client.conversations_list(types="public_channel", limit=200)
                for ch in result.get("channels", []):
                    if ch.get("name") == channel.lstrip("#"):
                        await slack_client.conversations_join(channel=ch["id"])
                        _joined_channels.add(channel)
                        logger.info("bot_joined_channel", channel=channel, channel_id=ch["id"])
                        return
                logger.warning("channel_not_found_by_name", channel=channel)
            except Exception as e2:
                logger.warning("channel_join_lookup_failed", channel=channel, error=str(e2))
        else:
            # Already in channel or other non-fatal error
            _joined_channels.add(channel)
            logger.debug("channel_join_skipped", channel=channel, reason=error_str)


def _split_text_for_slack(text: str, max_chars: int = 2900) -> List[str]:
    """Split long text into Slack-safe chunks, breaking at paragraph/line boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        cut_at = remaining.rfind("\n\n", 0, max_chars)
        if cut_at == -1 or cut_at < max_chars // 3:
            cut_at = remaining.rfind("\n", 0, max_chars)
        if cut_at == -1 or cut_at < max_chars // 3:
            cut_at = remaining.rfind(" ", 0, max_chars)
        if cut_at == -1:
            cut_at = max_chars

        chunks.append(remaining[:cut_at].rstrip())
        remaining = remaining[cut_at:].lstrip()

    return chunks


def make_scan_reddit(registry: AgentRegistry, db: Database, slack_client: Any = None):
    """Create a scheduled task for scanning Reddit across all workspaces."""

    async def scan_reddit() -> dict[str, Any]:
        agent = registry.get("reddit_ingest_agent")
        if not agent:
            return {"error": "reddit_ingest_agent not found"}

        workspaces = await WorkspaceRepo(db).list_all()
        results = {}
        for ws in workspaces:
            result = await agent.process_message(
                f"Scan all monitored subreddits for workspace {ws.id}",
                workspace_id=ws.id,
            )
            results[ws.id] = {
                "status": result.status,
                "text_preview": result.text[:200],
            }

        return results

    return scan_reddit


def make_scan_rss(registry: AgentRegistry, db: Database, slack_client: Any = None):
    """Create a scheduled task for scanning RSS feeds across all workspaces."""

    async def scan_rss() -> dict[str, Any]:
        agent = registry.get("research_agent")
        if not agent:
            return {"error": "research_agent not found"}

        workspaces = await WorkspaceRepo(db).list_all()
        results = {}
        for ws in workspaces:
            result = await agent.process_message(
                f"Scan all RSS feeds for workspace {ws.id}",
                workspace_id=ws.id,
            )
            results[ws.id] = {
                "status": result.status,
                "text_preview": result.text[:200],
            }
        return results

    return scan_rss


def make_scan_google_alerts(registry: AgentRegistry, db: Database, slack_client: Any = None):
    """Create a scheduled task for scanning Google Alert emails."""

    async def scan_google_alerts() -> dict[str, Any]:
        agent = registry.get("google_alerts_agent")
        if not agent:
            return {"error": "google_alerts_agent not found"}

        workspaces = await WorkspaceRepo(db).list_all()
        results = {}
        for ws in workspaces:
            result = await agent.process_message(
                f"Scan Google Alert emails for workspace {ws.id}",
                workspace_id=ws.id,
            )
            results[ws.id] = {
                "status": result.status,
                "text_preview": result.text[:200],
            }
        return results

    return scan_google_alerts


def make_scan_fraud(registry: AgentRegistry, db: Database, slack_client: Any = None):
    """Create a scheduled task for fraud monitoring."""

    async def scan_fraud() -> dict[str, Any]:
        agent = registry.get("research_agent")
        if not agent:
            return {"error": "research_agent not found"}

        workspaces = await WorkspaceRepo(db).list_all()
        results = {}
        for ws in workspaces:
            result = await agent.process_message(
                f"Scan fraud sources for workspace {ws.id}",
                workspace_id=ws.id,
            )
            results[ws.id] = {
                "status": result.status,
                "text_preview": result.text[:200],
            }
        return results

    return scan_fraud


def make_health_summary(registry: AgentRegistry, db: Database, slack_client: Any = None):
    """Create a scheduled task for daily health summary."""

    async def health_summary() -> dict[str, Any]:
        from ..db.repositories import DraftRepo, OpportunityRepo, ScanLogRepo

        workspaces = await WorkspaceRepo(db).list_all()
        summary: dict[str, Any] = {"workspaces": {}}

        for ws in workspaces:
            opps = await OpportunityRepo(db).list_by_workspace(ws.id, status="new")
            drafts = await DraftRepo(db).list_by_workspace(ws.id, status="pending")
            recent_scans = await ScanLogRepo(db).get_latest(ws.id, limit=5)

            summary["workspaces"][ws.id] = {
                "new_opportunities": len(opps),
                "pending_drafts": len(drafts),
                "recent_scans": len(recent_scans),
            }

        summary["agents"] = registry.list_agents()
        logger.info("health_summary_generated", summary=summary)

        # Send to Slack if client available
        if slack_client:
            try:
                await _ensure_bot_in_channel(slack_client, "#marketing-content")
                text = "CMO Agent Health Summary\n\n"
                for ws_id, data in summary["workspaces"].items():
                    text += f"*{ws_id}*: {data['new_opportunities']} new opportunities, "
                    text += f"{data['pending_drafts']} pending drafts\n"
                await slack_client.chat_postMessage(channel="#marketing-content", text=text)
            except Exception as e:
                logger.error("health_summary_slack_error", error=str(e))

        return summary

    return health_summary


def make_heal_workflows(registry: AgentRegistry, n8n_client: N8NClient):
    """Create a scheduled task for diagnosing and auto-repairing all workflows."""

    async def heal_workflows() -> dict[str, Any]:
        from ..agents.workflow_healer import WorkflowHealerAgent
        from ..n8n.client import N8NClientError

        agent = registry.get("workflow_healer_agent")
        if not agent or not isinstance(agent, WorkflowHealerAgent):
            return {"error": "workflow_healer_agent not found"}

        try:
            response = await n8n_client.list_workflows()
        except N8NClientError as e:
            logger.error("heal_workflows_list_failed", error=str(e))
            return {"error": f"Failed to list workflows: {e}"}

        results: dict[str, Any] = {
            "diagnosed": 0,
            "issues_found": 0,
            "repairs_attempted": 0,
            "repairs_succeeded": 0,
            "skipped_cooldown": 0,
        }

        for wf in response.data:
            wf_id = str(wf.id)
            results["diagnosed"] += 1

            diagnosis = await agent._diagnose_workflow_internal(wf_id)
            issues = diagnosis.get("issues", [])
            if not issues:
                continue

            results["issues_found"] += len(issues)

            repair_result = await agent._repair_workflow_internal(wf_id, issues)
            status = repair_result.get("status")

            if status == "skipped":
                results["skipped_cooldown"] += 1
            elif status == "repaired":
                results["repairs_attempted"] += 1
                results["repairs_succeeded"] += 1
            elif status in ("failed", "validation_failed", "no_fixable_issues"):
                results["repairs_attempted"] += 1

        logger.info("heal_workflows_completed", **results)
        return results

    return heal_workflows


def make_daily_growth_ideas(
    registry: AgentRegistry,
    db: Database,
    slack_client: Any = None,
    channel: str = "#marketing-content",
    ideas_count_min: int = 5,
    ideas_count_max: int = 10,
    product_ideas_dashboard: Any = None,
):
    """Create a scheduled task for generating growth ideas."""

    async def daily_growth_ideas() -> dict[str, Any]:
        agent = registry.get("growth_ideas_agent")
        if not agent:
            return {"error": "growth_ideas_agent not found"}

        result = await agent.process_message(
            f"Gather recent activity across all workspaces. "
            f"Then check for previous ideas for context. "
            f"Finally, generate {ideas_count_min}-{ideas_count_max} growth ideas based on the activity data.",
        )

        # Extract structured ideas from tool call results
        ideas: List[Dict[str, Any]] = []
        draft_id = ""
        recommended_pick = ""
        active_workspaces = 0

        for tc in result.tool_calls:
            tc_result = tc.get("result", {})
            if isinstance(tc_result, dict):
                if tc_result.get("ideas"):
                    ideas = tc_result["ideas"]
                    draft_id = tc_result.get("draft_id", "")
                    recommended_pick = tc_result.get("recommended_pick", "")
                if tc_result.get("active_workspaces"):
                    active_workspaces = tc_result["active_workspaces"]

        logger.info(
            "growth_ideas_extraction",
            ideas_count=len(ideas),
            tool_calls_count=len(result.tool_calls),
            channel=channel,
            has_text=bool(result.text),
        )

        # Post to Slack if client available
        if slack_client:
            try:
                await _ensure_bot_in_channel(slack_client, channel)
                if ideas:
                    # Structured Block Kit digest — may be split across messages
                    message_groups = _build_growth_ideas_blocks(
                        ideas=ideas,
                        draft_id=draft_id,
                        recommended_pick=recommended_pick,
                        active_workspaces=active_workspaces,
                    )
                    for msg_blocks in message_groups:
                        await slack_client.chat_postMessage(
                            channel=channel,
                            text=f"Daily Growth Ideas — {len(ideas)} ideas generated",
                            blocks=msg_blocks,
                        )
                    logger.info(
                        "growth_ideas_posted_to_slack",
                        ideas_count=len(ideas),
                        messages_sent=len(message_groups),
                        channel=channel,
                    )
                elif result.text:
                    # Only post fallback text if it doesn't contain internal errors
                    _error_indicators = [
                        "database",
                        "constraint",
                        "FOREIGN KEY",
                        "locked",
                        "Traceback",
                        "error code",
                        "OperationalError",
                    ]
                    has_error = any(ind.lower() in result.text.lower() for ind in _error_indicators)
                    if has_error:
                        logger.warning(
                            "growth_ideas_error_in_text",
                            channel=channel,
                            text_preview=result.text[:200],
                        )
                    else:
                        chunks = _split_text_for_slack(result.text)
                        for chunk in chunks:
                            await slack_client.chat_postMessage(
                                channel=channel,
                                text=f"*Daily Growth Ideas*\n\n{chunk}",
                            )
                        logger.info(
                            "growth_ideas_posted_text_fallback",
                            channel=channel,
                            chunks=len(chunks),
                        )
                else:
                    logger.warning(
                        "growth_ideas_no_output",
                        status=result.status,
                        channel=channel,
                    )
            except Exception as e:
                logger.error("growth_ideas_slack_error", error=str(e), channel=channel)

        # Sync ideas to Product Ideas Google Sheet (graceful — never blocks Slack)
        if product_ideas_dashboard and ideas:
            try:
                from datetime import date

                source_label = f"Daily Growth - {date.today().strftime('%b %-d')}"
                appended = await product_ideas_dashboard.append_ideas(ideas, source_label)
                logger.info(
                    "growth_ideas_sheet_synced",
                    appended=appended,
                    total_ideas=len(ideas),
                )
            except Exception as e:
                logger.error("growth_ideas_sheet_sync_failed", error=str(e))

        return {
            "status": result.status,
            "ideas_count": len(ideas),
            "draft_id": draft_id,
            "channel": channel,
        }

    return daily_growth_ideas


def _build_growth_ideas_blocks(
    ideas: List[Dict[str, Any]],
    draft_id: str,
    recommended_pick: str,
    active_workspaces: int,
) -> List[List[Dict[str, Any]]]:
    """Build Slack Block Kit blocks for the growth ideas digest.

    Returns a list of message-groups (list of list of blocks) to stay within
    Slack's 50-block-per-message limit. Each group is one chat_postMessage call.
    """
    _MAX_IDEAS_PER_MSG = 4  # keep well under 50 blocks per message

    # Build header blocks (sent with the first batch)
    header_blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": "Daily Growth Ideas"}},
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Based on 14 days of activity across {active_workspaces} workspace(s) | {len(ideas)} ideas",
                }
            ],
        },
        {"type": "divider"},
    ]

    # Build one section per idea
    idea_sections: List[Dict[str, Any]] = []
    for i, idea in enumerate(ideas, 1):
        title = idea.get("title", "Untitled")
        desc = idea.get("description", "")
        impact = idea.get("impact_score", "?")
        effort = idea.get("effort_score", "?")
        category = idea.get("category", "")
        workspaces = idea.get("workspaces", [])
        related = idea.get("related_projects", [])

        ws_tags = " ".join(f"`{w}`" for w in workspaces) if workspaces else ""
        related_text = ", ".join(related[:3]) if related else ""
        category_display = category.replace("_", " ") if category else ""

        text_parts = [f"*{i}. {title}*", desc]
        text_parts.append(
            f"Impact: *{impact}/10* | Effort: *{effort}/10* | Category: _{category_display}_"
        )
        if ws_tags:
            text_parts.append(f"Workspaces: {ws_tags}")
        if related_text:
            text_parts.append(f"Related: {related_text}")

        ws_value = ",".join(workspaces) if workspaces else "cross_workspace"
        button_value = f"{draft_id}:{i - 1}:{ws_value}"

        section: Dict[str, Any] = {
            "type": "section",
            "block_id": f"idea_{button_value}",
            "text": {"type": "mrkdwn", "text": "\n".join(text_parts)[:2900]},
        }

        actions_block: Dict[str, Any] = {
            "type": "actions",
            "block_id": f"actions_{button_value}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "\ud83d\udd25 Build It \ud83d\udd25"},
                    "action_id": "execute_growth_idea",
                    "value": button_value,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skip"},
                    "action_id": "skip_growth_idea",
                    "value": button_value,
                },
            ],
        }

        idea_sections.append(section)
        idea_sections.append(actions_block)

    # Build footer blocks (sent with the last batch)
    footer_blocks: List[Dict[str, Any]] = [{"type": "divider"}]
    if recommended_pick:
        # Split recommended pick if long
        pick_text = recommended_pick[:2900]
        footer_blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*RECOMMENDED PRIORITY*\n\n{pick_text}"},
            }
        )
    footer_blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Draft ID: `{draft_id}` | Generated by Growth Ideas Agent",
                }
            ],
        }
    )

    # Chunk ideas into message groups
    messages: List[List[Dict[str, Any]]] = []
    for batch_start in range(0, len(idea_sections), _MAX_IDEAS_PER_MSG):
        batch = idea_sections[batch_start : batch_start + _MAX_IDEAS_PER_MSG]
        msg_blocks: List[Dict[str, Any]] = []

        # Add header to first message
        if batch_start == 0:
            msg_blocks.extend(header_blocks)

        msg_blocks.extend(batch)

        # Add footer to last message
        if batch_start + _MAX_IDEAS_PER_MSG >= len(idea_sections):
            msg_blocks.extend(footer_blocks)

        messages.append(msg_blocks)

    return messages if messages else [header_blocks + footer_blocks]




def make_stale_growth_ideas_reminder(
    db: Database,
    slack_client: Any = None,
    channel: str = "#marketing-content",
    stale_days: int = 7,
):
    """Create a scheduled task for reminding about approved-but-not-launched growth ideas."""

    async def stale_growth_ideas_reminder() -> dict[str, Any]:
        if not slack_client:
            return {"status": "no_slack_client"}

        repo = ApprovedIdeaRepo(db)
        stale = await repo.list_stale("growth", stale_days=stale_days)

        if not stale:
            logger.debug("stale_growth_ideas_none", stale_days=stale_days)
            return {"status": "ok", "stale_count": 0}

        try:
            await _ensure_bot_in_channel(slack_client, channel)
            blocks = _build_stale_ideas_reminder_blocks(stale, "Growth")
            await slack_client.chat_postMessage(
                channel=channel,
                text=f"Reminder: {len(stale)} approved growth idea(s) awaiting launch",
                blocks=blocks,
            )
            logger.info(
                "stale_growth_ideas_reminder_posted",
                stale_count=len(stale),
                channel=channel,
            )
        except Exception as e:
            logger.error("stale_growth_ideas_reminder_error", error=str(e))

        return {"status": "ok", "stale_count": len(stale)}

    return stale_growth_ideas_reminder




def _build_stale_ideas_reminder_blocks(
    stale_ideas: List[Dict[str, Any]],
    idea_type_label: str,
) -> List[Dict[str, Any]]:
    """Build Slack Block Kit blocks for stale approved ideas reminder."""
    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"Reminder: Approved {idea_type_label} Ideas Awaiting Launch",
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{len(stale_ideas)} idea(s) were approved for building but haven't been launched yet.",
                }
            ],
        },
        {"type": "divider"},
    ]

    for idea in stale_ideas:
        idea_id = idea.get("id", 0)
        title = idea.get("idea_title", "Untitled")
        approved_by = idea.get("approved_by", "unknown")
        created_at = idea.get("created_at", "")
        idea_type = idea.get("idea_type", "growth")

        text_parts = [f"*{title}*"]
        text_parts.append(f"Approved by: <@{approved_by}> | Date: {created_at[:10]}")

        blocks.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(text_parts)},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Mark as Launched"},
                    "action_id": "mark_idea_launched",
                    "value": f"{idea_id}:{idea_type}",
                    "style": "primary",
                },
            }
        )

    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Click 'Mark as Launched' when an idea has been fully implemented.",
                }
            ],
        }
    )

    return blocks

