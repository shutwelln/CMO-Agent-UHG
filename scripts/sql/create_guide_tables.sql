-- Guide Articles: Supabase tables, seed data, RLS, indexes, trigger
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query)

-- ── Categories ──────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.guide_categories (
    id          SERIAL PRIMARY KEY,
    slug        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    sort_order  INT DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

INSERT INTO public.guide_categories (slug, name, description, sort_order) VALUES
    ('medicare',       'Medicare',        'Medicare guides, enrollment, and coverage',                 1),
    ('insurance',      'Insurance',       'Health, life, and supplemental insurance guides',           2),
    ('medical-alerts', 'Medical Alerts',  'Medical alert system reviews and comparisons',              3),
    ('phones',         'Phones',          'Senior-friendly phone reviews and plans',                   4),
    ('hearing-aids',   'Hearing Aids',    'Hearing aid reviews, OTC options, and savings',             5),
    ('finance',        'Finance',         'Retirement finance, Social Security, and budgeting',        6),
    ('tools',          'Tools',           'Interactive calculators and comparison tools',              7)
ON CONFLICT (slug) DO NOTHING;

-- ── Articles ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS public.guide_articles (
    id                   UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    slug                 TEXT UNIQUE NOT NULL,
    title                TEXT NOT NULL,
    subtitle             TEXT,
    category_id          INT REFERENCES public.guide_categories(id),
    vertical             TEXT,
    -- Taxonomy
    tags                 JSONB DEFAULT '[]'::jsonb,
    intent_tags          JSONB DEFAULT '[]'::jsonb,
    seo_keywords         JSONB DEFAULT '[]'::jsonb,
    reading_minutes      INT DEFAULT 7,
    -- Content sections
    overview_md          TEXT DEFAULT '',
    key_takeaways_md     TEXT DEFAULT '',
    body_md              TEXT DEFAULT '',
    savings_tips_md      TEXT DEFAULT '',
    watch_out_md         TEXT DEFAULT '',
    faq_md               TEXT DEFAULT '',
    -- Product comparison (optional)
    comparison_table     JSONB,
    -- Internal linking
    related_slugs        JSONB DEFAULT '[]'::jsonb,
    -- Email variants
    email_subject        TEXT DEFAULT '',
    email_preheader      TEXT DEFAULT '',
    email_intro_md       TEXT DEFAULT '',
    email_cta_label      TEXT DEFAULT 'Read the full guide',
    email_cta_url        TEXT DEFAULT '',
    -- Monetization
    monetization_type    TEXT DEFAULT 'informational',
    affiliate_disclosure BOOLEAN DEFAULT FALSE,
    -- Metadata (mirrors protection_articles pattern)
    status               TEXT DEFAULT 'draft',
    publish_web          BOOLEAN DEFAULT FALSE,
    publish_email        BOOLEAN DEFAULT FALSE,
    source               TEXT DEFAULT 'generate_guide_content',
    source_name          TEXT DEFAULT 'generate_guide_content.py',
    author               TEXT DEFAULT 'Saverwell AI',
    review_score         INT,
    review_notes         TEXT,
    citations            JSONB,
    -- Timestamps
    created_at           TIMESTAMPTZ DEFAULT now(),
    updated_at           TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_guide_articles_category ON public.guide_articles(category_id);
CREATE INDEX IF NOT EXISTS idx_guide_articles_vertical ON public.guide_articles(vertical);
CREATE INDEX IF NOT EXISTS idx_guide_articles_status   ON public.guide_articles(status);
CREATE INDEX IF NOT EXISTS idx_guide_articles_slug     ON public.guide_articles(slug);

-- Updated_at trigger (reuse existing function if it exists)
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER guide_articles_updated_at
    BEFORE UPDATE ON public.guide_articles
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- ── Row Level Security ──────────────────────────────────────────────────────

ALTER TABLE public.guide_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guide_articles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "service_role_all_guide_categories" ON public.guide_categories
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read_guide_categories" ON public.guide_categories
    FOR SELECT USING (true);

CREATE POLICY "service_role_all_guide_articles" ON public.guide_articles
    FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "anon_read_published_guide_articles" ON public.guide_articles
    FOR SELECT USING (publish_web = true);
