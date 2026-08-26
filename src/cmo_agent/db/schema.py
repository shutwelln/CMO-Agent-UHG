"""Database schema definitions and migrations."""

from __future__ import annotations

SCHEMA_SQL = """
-- Workspaces
CREATE TABLE IF NOT EXISTS workspaces (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'owned_brand',
    slack_channel TEXT,
    brand_voice_path TEXT,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Opportunities (discovered content items)
CREATE TABLE IF NOT EXISTS opportunities (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    source_id TEXT,
    title TEXT NOT NULL,
    content TEXT,
    score INTEGER NOT NULL DEFAULT 0,
    score_breakdown TEXT,
    category TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    subreddit TEXT,
    expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
CREATE INDEX IF NOT EXISTS idx_opportunities_workspace_status
    ON opportunities(workspace_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_opportunities_source_id
    ON opportunities(source, source_id) WHERE source_id IS NOT NULL;

-- Drafts (generated content)
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    content_type TEXT NOT NULL,
    title TEXT,
    body TEXT NOT NULL,
    verify_flags TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    rejection_reason TEXT,
    opportunity_ids TEXT,
    slack_thread_ts TEXT,
    slack_message_ts TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at TEXT,
    revised_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
CREATE INDEX IF NOT EXISTS idx_drafts_workspace_status
    ON drafts(workspace_id, status, created_at DESC);

-- Per-workspace configuration
CREATE TABLE IF NOT EXISTS config (
    workspace_id TEXT NOT NULL,
    key TEXT NOT NULL,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (workspace_id, key),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Monitoring sources
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    type TEXT NOT NULL,
    url TEXT,
    name TEXT,
    keywords TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    last_checked_at TEXT,
    last_item_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);
CREATE INDEX IF NOT EXISTS idx_sources_workspace_type
    ON sources(workspace_id, type, active);

-- Media assets (centralized media storage)
CREATE TABLE IF NOT EXISTS media_assets (
    id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    media_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    cdn_url TEXT,
    local_path TEXT,
    source_agent TEXT NOT NULL,
    prompt TEXT,
    metadata TEXT,
    file_size_bytes INTEGER,
    content_type TEXT,
    draft_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_media_assets_workspace_type
    ON media_assets(workspace_id, media_type, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_media_assets_draft
    ON media_assets(draft_id) WHERE draft_id IS NOT NULL;

-- Scan history
CREATE TABLE IF NOT EXISTS scan_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    items_scanned INTEGER NOT NULL DEFAULT 0,
    items_found INTEGER NOT NULL DEFAULT 0,
    errors TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY (workspace_id) REFERENCES workspaces(id)
);

-- Workflow healing history
CREATE TABLE IF NOT EXISTS heal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT NOT NULL,
    workflow_name TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    issues_found TEXT,
    fixes_applied TEXT,
    snapshot_before TEXT,
    snapshot_after TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_heal_log_workflow
    ON heal_log(workflow_id, created_at DESC);

-- Skipped ideas (excluded from future idea generation)
CREATE TABLE IF NOT EXISTS skipped_ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_title TEXT NOT NULL,
    idea_type TEXT NOT NULL,
    workspace_id TEXT,
    skipped_by TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_skipped_ideas_type
    ON skipped_ideas(idea_type, created_at DESC);

-- Workflow build history
CREATE TABLE IF NOT EXISTS build_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id TEXT,
    workflow_name TEXT NOT NULL,
    request TEXT NOT NULL,
    status TEXT NOT NULL,
    node_count INTEGER NOT NULL DEFAULT 0,
    nodes_summary TEXT,
    connections_summary TEXT,
    credential_warnings TEXT,
    workflow_url TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_build_log_created
    ON build_log(created_at DESC);

-- Approved ideas (excluded from future generation, tracked for launch reminders)
CREATE TABLE IF NOT EXISTS approved_ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    idea_title TEXT NOT NULL,
    idea_type TEXT NOT NULL,
    workspace_id TEXT,
    approved_by TEXT,
    status TEXT NOT NULL DEFAULT 'approved',
    launched_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_approved_ideas_type_status
    ON approved_ideas(idea_type, status, created_at DESC);
"""

MIGRATION_OUTREACH_SQL = """
-- Outreach workflow columns
ALTER TABLE opportunities ADD COLUMN claimed_by TEXT;
ALTER TABLE opportunities ADD COLUMN claimed_at TEXT;
ALTER TABLE opportunities ADD COLUMN response_url TEXT;
ALTER TABLE opportunities ADD COLUMN response_notes TEXT;
ALTER TABLE opportunities ADD COLUMN draft_reply TEXT;
ALTER TABLE opportunities ADD COLUMN platform_post_type TEXT;
ALTER TABLE opportunities ADD COLUMN outreach_status TEXT DEFAULT 'new';
ALTER TABLE opportunities ADD COLUMN outreach_outcome TEXT;
ALTER TABLE opportunities ADD COLUMN content_hash TEXT;
ALTER TABLE opportunities ADD COLUMN canned_response_used TEXT;
ALTER TABLE opportunities ADD COLUMN engagement_risk TEXT;
ALTER TABLE opportunities ADD COLUMN posted_at TEXT;
ALTER TABLE opportunities ADD COLUMN poster_gender TEXT;
"""

MIGRATION_OUTREACH_INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_opportunities_outreach
    ON opportunities(workspace_id, outreach_status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunities_content_hash
    ON opportunities(content_hash) WHERE content_hash IS NOT NULL;
"""

SEED_WORKSPACE_SQL = """
INSERT OR IGNORE INTO workspaces (id, name, type, slack_channel, brand_voice_path, is_default)
VALUES (?, ?, 'owned_brand', ?, ?, 1);
"""
