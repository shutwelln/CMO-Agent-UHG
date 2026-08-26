
CREATE TABLE IF NOT EXISTS broadcast_send_log (
    id SERIAL PRIMARY KEY,
    send_date DATE NOT NULL DEFAULT CURRENT_DATE,
    article_slug TEXT NOT NULL,
    article_title TEXT,
    category TEXT,
    send_type TEXT NOT NULL DEFAULT 'broadcast',
    seasonal_context TEXT DEFAULT '',
    broadcast_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE broadcast_send_log ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY anon_read_send_log ON broadcast_send_log FOR SELECT TO anon USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY anon_insert_send_log ON broadcast_send_log FOR INSERT TO anon WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_send_log_slug ON broadcast_send_log(article_slug);
CREATE INDEX IF NOT EXISTS idx_send_log_type ON broadcast_send_log(send_type);
