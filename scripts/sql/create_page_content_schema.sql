-- Page Content Schema: dma_page_content table + merchants page_* columns
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query)
-- Two schema changes:
--   1. Create dma_page_content table (DMA landing pages)
--   2. Add page_* columns to merchants table (merchant landing pages)

-- ════════════════════════════════════════════════════════════════════════════
-- Schema Change 1: Create dma_page_content table
-- ════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS public.dma_page_content (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    dma_description TEXT UNIQUE NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    state_codes JSONB DEFAULT '[]'::jsonb,
    county_names JSONB DEFAULT '[]'::jsonb,
    zip_count INT DEFAULT 0,
    location_count INT DEFAULT 0,
    merchant_count INT DEFAULT 0,
    coverage_tier TEXT DEFAULT 'full',

    -- Direct answer (featured snippet / AI engine extraction)
    direct_answer TEXT DEFAULT '',

    -- SEO content
    hero_headline TEXT DEFAULT '',
    hero_subhead TEXT DEFAULT '',
    intro_md TEXT DEFAULT '',
    savings_spotlight_md TEXT DEFAULT '',
    local_tips_md TEXT DEFAULT '',
    protection_callout_md TEXT DEFAULT '',
    faq_md TEXT DEFAULT '',
    faq_json JSONB DEFAULT '[]'::jsonb,

    -- Cross-links
    featured_protection_slugs JSONB DEFAULT '[]'::jsonb,
    featured_guide_slugs JSONB DEFAULT '[]'::jsonb,

    -- SEO meta
    seo_title TEXT DEFAULT '',
    seo_description TEXT DEFAULT '',
    seo_keywords JSONB DEFAULT '[]'::jsonb,

    -- Metadata
    status TEXT DEFAULT 'draft',
    source TEXT DEFAULT 'generate_dma_page_content',
    author TEXT DEFAULT 'Saverwell AI',
    review_score INT,
    review_notes TEXT,

    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dma_page_content_slug ON public.dma_page_content(slug);
CREATE INDEX IF NOT EXISTS idx_dma_page_content_status ON public.dma_page_content(status);
CREATE INDEX IF NOT EXISTS idx_dma_page_content_dma ON public.dma_page_content(dma_description);

-- Updated_at trigger (reuses existing set_updated_at function from guide_articles)
CREATE TRIGGER dma_page_content_updated_at
    BEFORE UPDATE ON public.dma_page_content
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- Row Level Security
ALTER TABLE public.dma_page_content ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_dma_page_content" ON public.dma_page_content
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read_published_dma_page_content" ON public.dma_page_content
    FOR SELECT USING (status = 'published');


-- ════════════════════════════════════════════════════════════════════════════
-- Schema Change 2: Add page_* columns to merchants table
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.merchants
ADD COLUMN IF NOT EXISTS page_slug TEXT,
ADD COLUMN IF NOT EXISTS page_direct_answer TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_hero_headline TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_hero_subhead TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_about_md TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_how_to_save_md TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_tips_md TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_faq_md TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_faq_json JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS page_protection_note_md TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_related_protection_slugs JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS page_related_guide_slugs JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS page_related_merchant_ids JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS page_seo_title TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_seo_description TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_seo_keywords JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS page_status TEXT DEFAULT 'draft',
ADD COLUMN IF NOT EXISTS page_source TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_author TEXT DEFAULT '',
ADD COLUMN IF NOT EXISTS page_review_score INT,
ADD COLUMN IF NOT EXISTS page_review_notes TEXT,
ADD COLUMN IF NOT EXISTS page_updated_at TIMESTAMPTZ;

-- Unique partial index on page_slug (only non-null values)
CREATE UNIQUE INDEX IF NOT EXISTS idx_merchants_page_slug
    ON public.merchants(page_slug) WHERE page_slug IS NOT NULL;
