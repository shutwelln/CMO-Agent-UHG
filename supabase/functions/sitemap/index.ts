/**
 * Sitemap Edge Function
 *
 * Queries v_sitemap_urls view and returns XML sitemap with saverwell.com prefix.
 * Supports sub-sitemaps via ?type= parameter:
 *   - type=index  -> <sitemapindex> pointing to sub-sitemaps
 *   - type=dma    -> only /dma/* URLs
 *   - type=merchants -> only /retailer/* URLs
 *   - type=guides -> only /guides/* URLs
 *   - type=protect -> only /protect/* URLs
 *   - type=states -> only /state/* URLs
 *   - type=pages  -> listing/nav pages only
 *   - (no type)   -> flat sitemap (backward compat)
 *
 * Deploy: supabase functions deploy sitemap --project-ref lmtrgkmgfermqatopkfp --no-verify-jwt
 */
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SITE_ORIGIN = "https://saverwell.com";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET",
};

const XML_HEADERS = {
  ...corsHeaders,
  "Content-Type": "application/xml; charset=utf-8",
  "Cache-Control": "public, max-age=3600, s-maxage=3600",
};

// URL prefix filters for sub-sitemaps
const TYPE_FILTERS: Record<string, string> = {
  dma: "/dma/",
  merchants: "/retailer/",
  guides: "/guides/",
  protect: "/protect/",
  states: "/state/",
};

// Listing pages (homepage, nav, category pages)
const LISTING_PAGES = [
  { path: "/", priority: "1.0", changefreq: "daily" },
  { path: "/retailers", priority: "0.8", changefreq: "weekly" },
  { path: "/dma", priority: "0.8", changefreq: "weekly" },
  { path: "/protect", priority: "0.8", changefreq: "weekly" },
  { path: "/guides", priority: "0.8", changefreq: "weekly" },
  { path: "/guides/medicare", priority: "0.75", changefreq: "weekly" },
  { path: "/guides/insurance", priority: "0.75", changefreq: "weekly" },
  { path: "/guides/retirement-taxes", priority: "0.75", changefreq: "weekly" },
  { path: "/guides/saving-money", priority: "0.75", changefreq: "weekly" },
  { path: "/guides/caregiving", priority: "0.75", changefreq: "weekly" },
  { path: "/guides/senior-products", priority: "0.75", changefreq: "weekly" },
  { path: "/states", priority: "0.8", changefreq: "weekly" },
];

// Sub-sitemap types for the index
const SUB_SITEMAP_TYPES = ["dma", "merchants", "guides", "protect", "states", "pages"];

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders });
  }

  const url = new URL(req.url);
  const type = url.searchParams.get("type");

  // --- Sitemap index ---
  if (type === "index") {
    return buildSitemapIndex();
  }

  // --- Pages-only sub-sitemap ---
  if (type === "pages") {
    return buildPagesSitemap();
  }

  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
  const supabase = createClient(supabaseUrl, supabaseAnonKey);

  // Apply URL prefix filter if type is specified
  const prefix = type ? TYPE_FILTERS[type] : null;
  if (type && !prefix) {
    return new Response(`Unknown sitemap type: ${type}`, { status: 400 });
  }

  let query = supabase.from("v_sitemap_urls").select("url, lastmod");
  if (prefix) {
    query = query.like("url", `${prefix}%`);
  }

  const { data: rows, error } = await query;

  if (error) {
    return new Response(`Error: ${error.message}`, { status: 500 });
  }

  const today = new Date().toISOString().split("T")[0];

  // Build URL entries
  const urlEntries = (rows || []).map((row: { url: string; lastmod: string | null }) => {
    const loc = `${SITE_ORIGIN}${row.url}`;
    const lastmod = row.lastmod
      ? new Date(row.lastmod).toISOString().split("T")[0]
      : null;

    // Assign priority by content type
    let priority = "0.6";
    if (row.url.startsWith("/retailer/")) priority = "0.7";
    else if (row.url.startsWith("/dma/")) priority = "0.6";
    else if (row.url.startsWith("/protect/")) priority = "0.7";
    else if (row.url.startsWith("/guides/")) priority = "0.7";
    else if (row.url.startsWith("/state/")) priority = "0.7";

    return `  <url>
    <loc>${escapeXml(loc)}</loc>${lastmod ? `\n    <lastmod>${lastmod}</lastmod>` : ""}
    <changefreq>weekly</changefreq>
    <priority>${priority}</priority>
  </url>`;
  });

  // For sub-sitemaps, return just the filtered URLs
  if (type) {
    const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urlEntries.join("\n")}
</urlset>`;
    return new Response(xml, { headers: XML_HEADERS });
  }

  // --- Flat sitemap (backward compat, no type param) ---
  const homepageEntry = `  <url>
    <loc>${SITE_ORIGIN}/</loc>
    <lastmod>${today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>`;

  const listingEntries = LISTING_PAGES
    .filter((p) => p.path !== "/")
    .map(
      (p) => `  <url>
    <loc>${SITE_ORIGIN}${p.path}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${p.changefreq}</changefreq>
    <priority>${p.priority}</priority>
  </url>`
    );

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${homepageEntry}
${listingEntries.join("\n")}
${urlEntries.join("\n")}
</urlset>`;

  return new Response(xml, { headers: XML_HEADERS });
});

/** Sitemap index pointing to sub-sitemaps */
function buildSitemapIndex(): Response {
  const today = new Date().toISOString().split("T")[0];
  const sitemaps = SUB_SITEMAP_TYPES.map(
    (t) => `  <sitemap>
    <loc>${SITE_ORIGIN}/sitemap-${t}.xml</loc>
    <lastmod>${today}</lastmod>
  </sitemap>`
  );

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${sitemaps.join("\n")}
</sitemapindex>`;

  return new Response(xml, { headers: XML_HEADERS });
}

/** Pages-only sub-sitemap (listing/nav pages) */
function buildPagesSitemap(): Response {
  const today = new Date().toISOString().split("T")[0];
  const entries = LISTING_PAGES.map(
    (p) => `  <url>
    <loc>${SITE_ORIGIN}${p.path}</loc>
    <lastmod>${today}</lastmod>
    <changefreq>${p.changefreq}</changefreq>
    <priority>${p.priority}</priority>
  </url>`
  );

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${entries.join("\n")}
</urlset>`;

  return new Response(xml, { headers: XML_HEADERS });
}

function escapeXml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}
