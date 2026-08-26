-- Merchant Directory Performance Indexes
-- Run this in the Supabase SQL Editor.
--
-- These indexes support the paginated A-Z store directory on /retailers.
-- The frontend filters by first letter (ilike 'A%') and paginates with
-- limit/offset, so we need efficient name-based lookups on the view's
-- underlying table.

-- 1. B-tree index on name for ORDER BY name and ilike prefix matching.
--    Postgres can use a B-tree for left-anchored LIKE/ILIKE patterns
--    (e.g., WHERE name ILIKE 'A%') with the default C locale collation.
CREATE INDEX IF NOT EXISTS idx_merchants_name
  ON public.merchants (name);

-- 2. Composite index covering the v_merchant_pages view WHERE clause.
--    The view filters on page_status + page_slug + page_hero_headline.
--    This lets Postgres satisfy the view filter + name sort in one scan.
CREATE INDEX IF NOT EXISTS idx_merchants_published_name
  ON public.merchants (name)
  WHERE page_status = 'published'
    AND page_slug IS NOT NULL
    AND page_slug != ''
    AND page_hero_headline IS NOT NULL
    AND page_hero_headline != '';

-- 3. Category lookup index (may already exist, IF NOT EXISTS is safe).
CREATE INDEX IF NOT EXISTS idx_merchants_category_id
  ON public.merchants (category_id);
