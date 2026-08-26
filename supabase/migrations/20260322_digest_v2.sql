-- Digest V2: subscribers table, opened tracking, click tracking

-- 1. subscribers table (mirrors content_interest from CIO)
CREATE TABLE IF NOT EXISTS subscribers (
    id BIGSERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    content_interest TEXT NOT NULL DEFAULT 'all',
    brand TEXT DEFAULT 'saverwell',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subscribers ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY anon_read_subscribers ON subscribers
      FOR SELECT TO anon USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY anon_insert_subscribers ON subscribers
      FOR INSERT TO anon WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY anon_update_subscribers ON subscribers
      FOR UPDATE TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_subscribers_email ON subscribers(email);
CREATE INDEX IF NOT EXISTS idx_subscribers_interest ON subscribers(content_interest);

-- 2. Add opened column to subscriber_sends
ALTER TABLE subscriber_sends ADD COLUMN IF NOT EXISTS opened BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_sub_sends_engagement
  ON subscriber_sends(subscriber_email, opened, sent_at);

-- 3. subscriber_clicks table (article-level click tracking)
CREATE TABLE IF NOT EXISTS subscriber_clicks (
    id BIGSERIAL PRIMARY KEY,
    subscriber_email TEXT NOT NULL,
    article_slug TEXT NOT NULL,
    clicked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subscriber_clicks ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY anon_read_subscriber_clicks ON subscriber_clicks
      FOR SELECT TO anon USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY anon_insert_subscriber_clicks ON subscriber_clicks
      FOR INSERT TO anon WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_sub_clicks_email ON subscriber_clicks(subscriber_email);
CREATE INDEX IF NOT EXISTS idx_sub_clicks_slug ON subscriber_clicks(article_slug);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_clicks_dedup
  ON subscriber_clicks(subscriber_email, article_slug);

-- 4. Allow anon to UPDATE subscriber_sends (for marking opened)
DO $$ BEGIN
    CREATE POLICY anon_update_subscriber_sends ON subscriber_sends
      FOR UPDATE TO anon USING (true) WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
