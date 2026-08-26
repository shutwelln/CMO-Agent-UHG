-- Web Read Tracking: bridge website reading behavior into digest personalization
--
-- 1. email_hash on subscribers — allows matching anonymous website reads
--    (sw_user_id SHA-256 in localStorage) back to known subscribers
-- 2. source on subscriber_clicks — distinguishes email clicks vs web reads
--    (same weight for scoring, but useful for analytics)

-- Add email_hash column for matching website reads to subscribers
ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS email_hash TEXT;
CREATE INDEX IF NOT EXISTS idx_subscribers_hash ON subscribers(email_hash);

-- Add source column to subscriber_clicks (email clicks vs web reads)
ALTER TABLE subscriber_clicks ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'email';
