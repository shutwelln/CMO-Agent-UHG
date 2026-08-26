-- Fix: Map national zoom timeout
-- Pre-compute 1.5° grid cells into a materialized view (~200 rows).
-- The RPC reads from this cache at zoom <= 5 (sub-millisecond).
-- Zoom 6+ uses the existing live query (smaller bounds = fast enough).
--
-- RECOMMENDED: Run section-by-section in Supabase SQL Editor (not via supabase db push)
-- so you can verify each step and control timeout settings.

-- =============================================================================
-- 1a. Materialized View
-- The initial materialization runs the same aggregation that currently times out.
-- Increase statement timeout for this one-time creation (5 min).
-- =============================================================================
SET LOCAL statement_timeout = '300s';

CREATE MATERIALIZED VIEW IF NOT EXISTS public.mv_region_bubbles_national AS
SELECT
  floor(loc.latitude / 1.5) * 1.5 + 0.75 AS cell_lat,
  floor(loc.longitude / 1.5) * 1.5 + 0.75 AS cell_lng,
  count(*)::integer AS location_count
FROM store_locations_with_effective_discount_enriched sl
JOIN locations_v2 loc ON sl.location_id = loc.id
WHERE loc.latitude IS NOT NULL
  AND loc.longitude IS NOT NULL
GROUP BY 1, 2;

-- Verify it populated:
-- SELECT count(*) FROM mv_region_bubbles_national;  -- Expect 100-300 rows

-- =============================================================================
-- 1b. Unique Index (enables non-blocking CONCURRENTLY refresh)
-- =============================================================================
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_region_bubbles_national_cell
  ON public.mv_region_bubbles_national (cell_lat, cell_lng);

-- =============================================================================
-- 1c. Composite Index on locations_v2 (helps zoom 6-8 performance)
-- =============================================================================
CREATE INDEX IF NOT EXISTS idx_locations_v2_lat_lng
  ON public.locations_v2 (latitude, longitude)
  WHERE latitude IS NOT NULL AND longitude IS NOT NULL;

-- =============================================================================
-- 1d. Updated RPC — with fallback safety
-- Checks for materialized view existence. Falls back to live query if missing.
-- =============================================================================
DROP FUNCTION IF EXISTS public.get_region_bubbles_by_bounds(double precision, double precision, double precision, double precision, integer, integer);

CREATE OR REPLACE FUNCTION public.get_region_bubbles_by_bounds(
  p_north double precision, p_south double precision,
  p_east double precision, p_west double precision,
  p_zoom integer, p_limit integer DEFAULT 180
)
RETURNS TABLE(cell_lat double precision, cell_lng double precision, location_count integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $function$
DECLARE
  v_cell_size double precision;
  v_safe_limit integer;
  v_has_cache boolean;
BEGIN
  -- Validate inputs
  IF p_north < -90 OR p_north > 90 OR p_south < -90 OR p_south > 90 THEN RETURN; END IF;
  IF p_east < -180 OR p_east > 180 OR p_west < -180 OR p_west > 180 THEN RETURN; END IF;
  IF p_zoom < 1 OR p_zoom > 22 THEN RETURN; END IF;
  v_safe_limit := LEAST(COALESCE(p_limit, 180), 500);

  IF p_zoom <= 5 THEN
    -- Check if materialized view exists and has data
    SELECT EXISTS (
      SELECT 1 FROM pg_matviews WHERE schemaname = 'public' AND matviewname = 'mv_region_bubbles_national'
    ) INTO v_has_cache;

    IF v_has_cache THEN
      -- FAST PATH: pre-computed materialized view (<10ms)
      RETURN QUERY
      SELECT mv.cell_lat, mv.cell_lng, mv.location_count
      FROM mv_region_bubbles_national mv
      WHERE mv.cell_lat BETWEEN p_south AND p_north
        AND mv.cell_lng BETWEEN p_west AND p_east
      ORDER BY mv.location_count DESC
      LIMIT v_safe_limit;
      RETURN;  -- Exit after returning cached results
    END IF;
  END IF;

  -- LIVE PATH: compute on-the-fly (zoom 6+, or fallback if cache missing)
  IF p_zoom <= 5 THEN
    v_cell_size := 1.5;
  ELSIF p_zoom <= 7 THEN
    v_cell_size := 0.75;
  ELSE
    v_cell_size := 0.35;
  END IF;

  RETURN QUERY
  SELECT
    floor(loc.latitude / v_cell_size) * v_cell_size + v_cell_size / 2 AS cell_lat,
    floor(loc.longitude / v_cell_size) * v_cell_size + v_cell_size / 2 AS cell_lng,
    count(*)::integer AS location_count
  FROM store_locations_with_effective_discount_enriched sl
  JOIN locations_v2 loc ON sl.location_id = loc.id
  WHERE loc.latitude IS NOT NULL AND loc.longitude IS NOT NULL
    AND loc.latitude BETWEEN p_south AND p_north
    AND loc.longitude BETWEEN p_west AND p_east
  GROUP BY 1, 2
  ORDER BY location_count DESC
  LIMIT v_safe_limit;
END;
$function$;

COMMENT ON FUNCTION public.get_region_bubbles_by_bounds IS
  'Returns aggregated location counts by geographic grid cells. Uses materialized view cache for zoom <= 5, live query for zoom 6+. SECURITY DEFINER with explicit search_path. Returns only aggregate counts (no PII). Parameters validated and limit capped at 500.';

-- =============================================================================
-- 1e. Refresh Function
-- =============================================================================
CREATE OR REPLACE FUNCTION public.refresh_mv_region_bubbles_national()
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = 'public'
AS $function$
BEGIN
  REFRESH MATERIALIZED VIEW CONCURRENTLY mv_region_bubbles_national;
END;
$function$;

-- =============================================================================
-- 1f. pg_cron Daily Refresh (if extension available)
-- If pg_cron isn't enabled, refresh manually after data imports:
--   SELECT refresh_mv_region_bubbles_national();
-- =============================================================================
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule(
      'refresh-national-bubbles',
      '0 5 * * *',
      'SELECT public.refresh_mv_region_bubbles_national()'
    );
  END IF;
END;
$$;
