-- Sitemap View: All published SEO page URLs for sitemap generation
-- Run this in the Supabase SQL Editor.
--
-- Fixes applied:
--   1. Merchant URL uses page_slug (not id)
--   2. NULL/empty slug guard on merchants
--   3. Guide articles filtered by publish_web (aligns with RLS)
--   4. Public-schema alias view for PostgREST/anon access
--
-- Safe to re-run (uses DROP + CREATE).
--
-- Check existing definition first:
--   SELECT pg_get_viewdef('seo.v_sitemap_urls', true);

-- Ensure schema exists
CREATE SCHEMA IF NOT EXISTS seo;

-- Drop and recreate to avoid column mismatch issues with OR REPLACE
DROP VIEW IF EXISTS public.v_sitemap_urls;
DROP VIEW IF EXISTS seo.v_sitemap_urls;

CREATE VIEW seo.v_sitemap_urls AS

-- DMA pages (only published ones)
SELECT
    '/dma/' || slug AS url,
    updated_at AS lastmod
FROM public.dma_page_content
WHERE status = 'published'

UNION ALL

-- Merchant pages (only those with populated content and a valid slug)
SELECT
    '/retailer/' || page_slug AS url,
    page_updated_at AS lastmod
FROM public.merchants
WHERE page_hero_headline IS NOT NULL
  AND page_hero_headline != ''
  AND page_slug IS NOT NULL
  AND page_slug != ''
  AND COALESCE(page_status, 'draft') = 'published'

UNION ALL

-- Protection articles
SELECT
    '/protect/' || slug AS url,
    updated_at AS lastmod
FROM public.protection_articles
WHERE status = 'published'

UNION ALL

-- Guide articles (filtered by publish_web to match RLS)
SELECT
    '/guides/' || slug AS url,
    updated_at AS lastmod
FROM public.guide_articles
WHERE status = 'published'
  AND publish_web = true

UNION ALL

-- State hub pages
SELECT
    '/state/' || slug AS url,
    updated_at AS lastmod
FROM public.state_page_content
WHERE status = 'published';

-- Grant read access to anon role for sitemap generation
GRANT USAGE ON SCHEMA seo TO anon;
GRANT SELECT ON seo.v_sitemap_urls TO anon;

-- Public-schema alias for PostgREST access (anon can query via /rest/v1/v_sitemap_urls)
CREATE OR REPLACE VIEW public.v_sitemap_urls AS
SELECT * FROM seo.v_sitemap_urls;

GRANT SELECT ON public.v_sitemap_urls TO anon;
