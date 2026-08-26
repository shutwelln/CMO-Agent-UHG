-- Affiliate Revenue Columns for Merchants
-- Run this in the Supabase SQL Editor.
--
-- Existing columns (already on table, no changes needed):
--   affiliate_url       TEXT (nullable, currently all NULL)
--   affiliate_network   TEXT (nullable, currently all NULL)
--   affiliate_priority_score  (nullable, currently all NULL - keep as-is)
--
-- This migration adds the missing columns only.
-- Safe to re-run (uses IF NOT EXISTS).

-- ── Add missing affiliate columns ───────────────────────────────────────────

ALTER TABLE public.merchants
ADD COLUMN IF NOT EXISTS commission_type TEXT DEFAULT '';

ALTER TABLE public.merchants
ADD COLUMN IF NOT EXISTS commission_rate TEXT DEFAULT '';

ALTER TABLE public.merchants
ADD COLUMN IF NOT EXISTS affiliate_status TEXT DEFAULT 'none';

-- ── Add check constraint for affiliate_status values ────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'merchants_affiliate_status_check'
    ) THEN
        ALTER TABLE public.merchants
        ADD CONSTRAINT merchants_affiliate_status_check
        CHECK (affiliate_status IN ('none', 'pending', 'active', 'paused'));
    END IF;
END $$;

-- ── Create index for quick affiliate status lookups ─────────────────────────

CREATE INDEX IF NOT EXISTS idx_merchants_affiliate_status
ON public.merchants(affiliate_status)
WHERE affiliate_status != 'none';
