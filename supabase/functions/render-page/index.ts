/**
 * Dynamic Rendering Edge Function for SEO
 *
 * Detects bot user agents and serves pre-rendered HTML with proper SEO tags
 * (title, meta description, JSON-LD, Open Graph) instead of the empty SPA shell.
 * Real users pass through to the Lovable SPA as normal.
 *
 * Deploy as a Cloudflare Worker (not a Supabase Edge Function) to intercept
 * requests before they hit the Lovable origin. The logic below is framework-
 * agnostic and can run in any edge runtime (Cloudflare Workers, Deno Deploy).
 *
 * Cloudflare Worker setup:
 *   1. Create a Worker in the Cloudflare dashboard
 *   2. Paste this code (adjust imports for Cloudflare if needed)
 *   3. Add a route: saverwell.com/retailer/*, saverwell.com/dma/*, etc.
 *   4. Set environment variables: SUPABASE_URL, SUPABASE_ANON_KEY
 */
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SITE_ORIGIN = "https://saverwell.com";
const SITE_NAME = "Saverwell";

// Bot user-agent patterns (case-insensitive match)
const BOT_PATTERNS = [
  "googlebot",
  "bingbot",
  "slurp",
  "duckduckbot",
  "baiduspider",
  "yandexbot",
  "facebookexternalhit",
  "twitterbot",
  "linkedinbot",
  "whatsapp",
  "telegrambot",
  "applebot",
];

interface RouteMatch {
  type: "retailer" | "dma" | "protect" | "guides";
  slug: string;
}

function matchRoute(pathname: string): RouteMatch | null {
  const patterns: Array<{ prefix: string; type: RouteMatch["type"] }> = [
    { prefix: "/retailer/", type: "retailer" },
    { prefix: "/dma/", type: "dma" },
    { prefix: "/protect/", type: "protect" },
    { prefix: "/guides/", type: "guides" },
  ];

  for (const p of patterns) {
    if (pathname.startsWith(p.prefix)) {
      const slug = pathname.slice(p.prefix.length).replace(/\/$/, "");
      if (slug) return { type: p.type, slug };
    }
  }
  return null;
}

function isBot(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return BOT_PATTERNS.some((pattern) => ua.includes(pattern));
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Simple markdown to HTML (headings, bold, paragraphs)
function mdToHtml(md: string | null): string {
  if (!md) return "";
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\n\n/g, "</p><p>")
    .replace(/^/, "<p>")
    .replace(/$/, "</p>");
}

interface PageData {
  title: string;
  description: string;
  canonical: string;
  breadcrumbs: Array<{ name: string; url?: string }>;
  headline: string;
  subhead: string;
  bodyHtml: string;
  faqJson: Array<{ question: string; answer: string }>;
}

async function fetchPageData(
  supabase: ReturnType<typeof createClient>,
  route: RouteMatch
): Promise<PageData | null> {
  switch (route.type) {
    case "retailer": {
      const { data } = await supabase
        .from("v_merchant_pages")
        .select("*")
        .eq("page_slug", route.slug)
        .single();
      if (!data) return null;
      return {
        title: data.page_seo_title || `${data.name} Senior Discount | ${SITE_NAME}`,
        description: data.page_seo_description || "",
        canonical: `${SITE_ORIGIN}/retailer/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Senior Discounts", url: `${SITE_ORIGIN}/retailers` },
          { name: data.name },
        ],
        headline: data.page_hero_headline || "",
        subhead: data.page_hero_subhead || "",
        bodyHtml: [
          mdToHtml(data.page_about_md),
          mdToHtml(data.page_how_to_save_md),
          mdToHtml(data.page_tips_md),
          mdToHtml(data.page_protection_note_md),
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson: Array.isArray(data.page_faq_json) ? data.page_faq_json : [],
      };
    }

    case "dma": {
      const { data } = await supabase
        .from("dma_page_content")
        .select("*")
        .eq("slug", route.slug)
        .eq("status", "published")
        .single();
      if (!data) return null;
      return {
        title: data.seo_title || `Senior Discounts in ${data.display_name} | ${SITE_NAME}`,
        description: data.seo_description || "",
        canonical: `${SITE_ORIGIN}/dma/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Local Senior Discounts", url: `${SITE_ORIGIN}/dma` },
          { name: data.display_name },
        ],
        headline: data.hero_headline || "",
        subhead: data.hero_subhead || "",
        bodyHtml: [
          mdToHtml(data.intro_md),
          mdToHtml(data.savings_spotlight_md),
          mdToHtml(data.local_tips_md),
          mdToHtml(data.protection_callout_md),
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson: Array.isArray(data.faq_json) ? data.faq_json : [],
      };
    }

    case "protect": {
      const { data } = await supabase
        .from("protection_articles")
        .select("*")
        .eq("slug", route.slug)
        .single();
      if (!data) return null;
      return {
        title: data.seo_title || `${data.title} | ${SITE_NAME}`,
        description: data.seo_description || "",
        canonical: `${SITE_ORIGIN}/protect/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Protection", url: `${SITE_ORIGIN}/protect` },
          { name: data.title },
        ],
        headline: data.title || "",
        subhead: "",
        bodyHtml: mdToHtml(data.body_md || data.content_md || ""),
        faqJson: Array.isArray(data.faq_json) ? data.faq_json : [],
      };
    }

    case "guides": {
      const { data } = await supabase
        .from("guide_articles")
        .select("*")
        .eq("slug", route.slug)
        .single();
      if (!data) return null;
      return {
        title: data.seo_title || `${data.title} | ${SITE_NAME}`,
        description: data.seo_description || "",
        canonical: `${SITE_ORIGIN}/guides/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Guides", url: `${SITE_ORIGIN}/guides` },
          { name: data.title },
        ],
        headline: data.title || "",
        subhead: data.subtitle || "",
        bodyHtml: mdToHtml(data.body_md || data.content_md || ""),
        faqJson: Array.isArray(data.faq_json) ? data.faq_json : [],
      };
    }
  }
}

function buildFaqJsonLd(faqs: Array<{ question: string; answer: string }>): string {
  if (!faqs.length) return "";
  const schema = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((faq) => ({
      "@type": "Question",
      name: faq.question,
      acceptedAnswer: {
        "@type": "Answer",
        text: faq.answer,
      },
    })),
  };
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function buildBreadcrumbJsonLd(
  breadcrumbs: Array<{ name: string; url?: string }>
): string {
  const schema = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: breadcrumbs.map((b, i) => {
      const item: Record<string, unknown> = {
        "@type": "ListItem",
        position: i + 1,
        name: b.name,
      };
      if (b.url) item.item = b.url;
      return item;
    }),
  };
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function renderFullHtml(page: PageData): string {
  const faqHtml = page.faqJson.length
    ? `<section class="faq">
  <h2>Frequently Asked Questions</h2>
  ${page.faqJson
    .map(
      (faq) =>
        `<details><summary>${escapeHtml(faq.question)}</summary><p>${escapeHtml(faq.answer)}</p></details>`
    )
    .join("\n  ")}
</section>`
    : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(page.title)}</title>
  <meta name="description" content="${escapeHtml(page.description)}">
  <link rel="canonical" href="${page.canonical}">
  <meta property="og:title" content="${escapeHtml(page.title)}">
  <meta property="og:description" content="${escapeHtml(page.description)}">
  <meta property="og:url" content="${page.canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="${SITE_NAME}">
  ${buildBreadcrumbJsonLd(page.breadcrumbs)}
  ${buildFaqJsonLd(page.faqJson)}
</head>
<body>
  <nav aria-label="breadcrumb">
    ${page.breadcrumbs
      .map((b, i) =>
        b.url
          ? `<a href="${b.url}">${escapeHtml(b.name)}</a>${i < page.breadcrumbs.length - 1 ? " &gt; " : ""}`
          : `<span>${escapeHtml(b.name)}</span>`
      )
      .join("")}
  </nav>
  <main>
    <h1>${escapeHtml(page.headline)}</h1>
    ${page.subhead ? `<p class="subhead">${escapeHtml(page.subhead)}</p>` : ""}
    <article>
      ${page.bodyHtml}
    </article>
    ${faqHtml}
  </main>
</body>
</html>`;
}

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  const pathname = url.pathname;

  // Only handle SEO page routes
  const route = matchRoute(pathname);
  if (!route) {
    return new Response("Not found", { status: 404 });
  }

  // Check if this is a bot request
  const userAgent = req.headers.get("user-agent") || "";
  if (!isBot(userAgent)) {
    // For real users, return a redirect or pass-through to the SPA
    // In Cloudflare Worker mode, use fetch(req) to pass to origin
    // In standalone mode, redirect to the SPA
    return new Response(null, {
      status: 302,
      headers: { Location: `${SITE_ORIGIN}${pathname}` },
    });
  }

  // Bot request: fetch data and return pre-rendered HTML
  const supabaseUrl = Deno.env.get("SUPABASE_URL")!;
  const supabaseAnonKey = Deno.env.get("SUPABASE_ANON_KEY")!;
  const supabase = createClient(supabaseUrl, supabaseAnonKey);

  const pageData = await fetchPageData(supabase, route);
  if (!pageData) {
    return new Response("Not found", { status: 404 });
  }

  const html = renderFullHtml(pageData);

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "public, max-age=3600, s-maxage=86400",
      "X-Robots-Tag": "index, follow",
    },
  });
});
