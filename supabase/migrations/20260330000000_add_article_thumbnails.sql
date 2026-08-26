-- Add thumbnail fields to guide and protection articles
-- Phase A: Image Library Strategy for Saverwell

-- Guide articles
ALTER TABLE guide_articles
  ADD COLUMN IF NOT EXISTS thumbnail_url TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_alt TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_prompt TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_status TEXT DEFAULT 'pending'
    CHECK (thumbnail_status IN ('pending', 'approved', 'rejected'));

-- Protection articles
ALTER TABLE protection_articles
  ADD COLUMN IF NOT EXISTS thumbnail_url TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_alt TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_prompt TEXT,
  ADD COLUMN IF NOT EXISTS thumbnail_status TEXT DEFAULT 'pending'
    CHECK (thumbnail_status IN ('pending', 'approved', 'rejected'));

-- Category hero images (for Browse by Topic tiles)
ALTER TABLE guide_categories
  ADD COLUMN IF NOT EXISTS hero_image_url TEXT,
  ADD COLUMN IF NOT EXISTS card_thumbnail_url TEXT,
  ADD COLUMN IF NOT EXISTS hero_image_alt TEXT;
