
CREATE TABLE IF NOT EXISTS subscriber_sends (
    id BIGSERIAL PRIMARY KEY,
    subscriber_email TEXT NOT NULL,
    article_slug TEXT NOT NULL,
    send_type TEXT NOT NULL DEFAULT 'digest',
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE subscriber_sends ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    CREATE POLICY anon_read_subscriber_sends ON subscriber_sends
      FOR SELECT TO anon USING (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE POLICY anon_insert_subscriber_sends ON subscriber_sends
      FOR INSERT TO anon WITH CHECK (true);
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_sub_sends_email ON subscriber_sends(subscriber_email);
CREATE INDEX IF NOT EXISTS idx_sub_sends_slug ON subscriber_sends(article_slug);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sub_sends_dedup
  ON subscriber_sends(subscriber_email, article_slug, send_type);
