-- RLS policies for admin content editing on merchants, dma_page_content, state_page_content
-- Run this in the Supabase SQL Editor BEFORE adding admin pages in Lovable.
--
-- What this does:
--   1. merchants: Enable RLS (currently unprotected) + add service_role, authenticated, anon policies
--   2. dma_page_content: Add authenticated full access policy (already has service_role + anon-read-published)
--   3. state_page_content: Add authenticated full access policy (already has service_role + anon-read-published)
--
-- Safe to re-run: uses DROP IF EXISTS before CREATE.

-- ============================================================================
-- 1. merchants table - Enable RLS + add policies
-- ============================================================================

-- Enable RLS (currently unprotected)
ALTER TABLE public.merchants ENABLE ROW LEVEL SECURITY;

-- Service role: full access (bypass RLS in practice, but explicit policy is cleaner)
DROP POLICY IF EXISTS "service_role_all_merchants" ON public.merchants;
CREATE POLICY "service_role_all_merchants"
    ON public.merchants
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Authenticated users (admin panel): full CRUD
DROP POLICY IF EXISTS "authenticated_all_merchants" ON public.merchants;
CREATE POLICY "authenticated_all_merchants"
    ON public.merchants
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

-- Anon users (consumer frontend + v_merchant_pages view): SELECT only
-- Required because v_merchant_pages inherits the calling role's RLS context.
DROP POLICY IF EXISTS "anon_select_merchants" ON public.merchants;
CREATE POLICY "anon_select_merchants"
    ON public.merchants
    FOR SELECT
    TO anon
    USING (true);

-- Grant permissions
GRANT SELECT ON public.merchants TO anon;
GRANT ALL ON public.merchants TO authenticated;
GRANT ALL ON public.merchants TO service_role;


-- ============================================================================
-- 2. dma_page_content table - Add authenticated policy
-- ============================================================================
-- Already has: service_role_all_dma_page_content (ALL), anon_read_published_dma_page_content (SELECT where published)

DROP POLICY IF EXISTS "authenticated_all_dma_page_content" ON public.dma_page_content;
CREATE POLICY "authenticated_all_dma_page_content"
    ON public.dma_page_content
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

GRANT ALL ON public.dma_page_content TO authenticated;


-- ============================================================================
-- 3. state_page_content table - Add authenticated policy
-- ============================================================================
-- Already has: service_role_all (ALL), anon_select_published (SELECT where published)

DROP POLICY IF EXISTS "authenticated_all_state_page_content" ON public.state_page_content;
CREATE POLICY "authenticated_all_state_page_content"
    ON public.state_page_content
    FOR ALL
    TO authenticated
    USING (true)
    WITH CHECK (true);

GRANT ALL ON public.state_page_content TO authenticated;
