-- Published Merchant Pages View
-- Run this in the Supabase SQL Editor.
--
-- Exposes only page-display fields for published merchants with actual content.
-- No anon RLS exists on the merchants table, so this view serves as the
-- read-only interface for the frontend (Lovable SPA + Cloudflare Worker).
--
-- DROP + CREATE required when adding columns before existing ones (Postgres
-- cannot reorder columns with CREATE OR REPLACE).

DROP VIEW IF EXISTS public.v_merchant_pages;

CREATE VIEW public.v_merchant_pages AS
SELECT
    id,
    name,
    page_slug,
    page_direct_answer,
    page_hero_headline,
    page_hero_subhead,
    page_about_md,
    page_how_to_save_md,
    page_tips_md,
    page_faq_md,
    page_faq_json,
    page_protection_note_md,
    page_related_protection_slugs,
    page_related_guide_slugs,
    page_related_merchant_ids,
    page_seo_title,
    page_seo_description,
    page_seo_keywords,
    logo_url,
    website_url,
    is_national,
    category_id,
    default_discount_value,
    default_discount_text,
    default_discount_requirement,
    default_discount_type,
    default_discount_details,
    -- Affiliate fields: only expose when status is active and URL is set
    CASE WHEN affiliate_status = 'active' AND COALESCE(affiliate_url, '') != ''
         THEN affiliate_url ELSE '' END AS affiliate_url,
    CASE WHEN affiliate_status = 'active' AND COALESCE(affiliate_url, '') != ''
         THEN COALESCE(commission_type, '') ELSE '' END AS commission_type,
    (affiliate_status = 'active' AND COALESCE(affiliate_url, '') != '') AS has_affiliate
FROM public.merchants
WHERE page_status = 'published'
  AND page_slug IS NOT NULL
  AND page_slug != ''
  AND page_hero_headline IS NOT NULL
  AND page_hero_headline != '';

GRANT SELECT ON public.v_merchant_pages TO anon;
