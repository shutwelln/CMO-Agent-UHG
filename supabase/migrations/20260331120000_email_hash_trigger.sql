-- Auto-compute email_hash on INSERT/UPDATE to subscribers
-- Uses pgcrypto's digest() for SHA-256, matching the Cloudflare Worker's sw_user_id

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE OR REPLACE FUNCTION compute_email_hash()
RETURNS TRIGGER AS $$
BEGIN
  NEW.email_hash := encode(digest(lower(trim(NEW.email)), 'sha256'), 'hex');
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_subscribers_email_hash ON subscribers;
CREATE TRIGGER trg_subscribers_email_hash
  BEFORE INSERT OR UPDATE OF email ON subscribers
  FOR EACH ROW
  EXECUTE FUNCTION compute_email_hash();
