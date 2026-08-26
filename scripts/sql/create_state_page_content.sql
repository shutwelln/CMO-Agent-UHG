-- State Page Content: 51 state-level hub pages (50 states + DC)
-- Run this in the Supabase SQL Editor.
--
-- Each state page aggregates DMA sub-pages and captures queries like
-- "senior discounts in [State]", "[State] senior savings programs".
--
-- Safe to re-run: uses IF NOT EXISTS for table, DROP + CREATE for policies.

CREATE TABLE IF NOT EXISTS public.state_page_content (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state_code      TEXT UNIQUE NOT NULL,     -- "TX", "CA", "DC"
    state_name      TEXT NOT NULL,            -- "Texas", "California"
    slug            TEXT UNIQUE NOT NULL,     -- "texas", "new-york"
    region          TEXT,                     -- "South", "West Coast"

    -- Coverage stats
    zip_count       INT DEFAULT 0,
    county_count    INT DEFAULT 0,
    dma_count       INT DEFAULT 0,
    location_count  INT DEFAULT 0,
    merchant_count  INT DEFAULT 0,
    coverage_tier   TEXT DEFAULT 'emerging',  -- "full" (50+ locations) / "emerging"

    -- DMA sub-pages directory
    dma_pages       JSONB DEFAULT '[]'::jsonb,  -- [{slug, display_name, merchant_count, location_count}]

    -- Hero section
    direct_answer   TEXT DEFAULT '',
    hero_headline   TEXT DEFAULT '',
    hero_subhead    TEXT DEFAULT '',

    -- Markdown content sections
    intro_md               TEXT DEFAULT '',
    savings_spotlight_md   TEXT DEFAULT '',
    explore_areas_md       TEXT DEFAULT '',   -- Unique to state pages: DMA directory prose
    local_tips_md          TEXT DEFAULT '',
    protection_callout_md  TEXT DEFAULT '',
    faq_md                 TEXT DEFAULT '',
    faq_json               JSONB DEFAULT '[]'::jsonb,

    -- Cross-link arrays
    featured_protection_slugs  JSONB DEFAULT '[]'::jsonb,
    featured_guide_slugs       JSONB DEFAULT '[]'::jsonb,

    -- SEO metadata
    seo_title        TEXT DEFAULT '',
    seo_description  TEXT DEFAULT '',
    seo_keywords     JSONB DEFAULT '[]'::jsonb,

    -- Publishing
    status           TEXT DEFAULT 'draft',    -- "draft" / "published"
    source           TEXT DEFAULT '',
    author           TEXT DEFAULT '',
    review_notes     TEXT DEFAULT '',

    -- Timestamps
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_state_page_content_slug
    ON public.state_page_content (slug);
CREATE INDEX IF NOT EXISTS idx_state_page_content_status
    ON public.state_page_content (status);
CREATE INDEX IF NOT EXISTS idx_state_page_content_state_code
    ON public.state_page_content (state_code);

-- Updated-at trigger (reuse existing function or create)
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_state_page_content_updated_at
    ON public.state_page_content;
CREATE TRIGGER trg_state_page_content_updated_at
    BEFORE UPDATE ON public.state_page_content
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS
ALTER TABLE public.state_page_content ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role_all" ON public.state_page_content;
CREATE POLICY "service_role_all"
    ON public.state_page_content
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "anon_select_published" ON public.state_page_content;
CREATE POLICY "anon_select_published"
    ON public.state_page_content
    FOR SELECT
    TO anon
    USING (status = 'published');

-- Grant access
GRANT SELECT ON public.state_page_content TO anon;
GRANT ALL ON public.state_page_content TO service_role;
