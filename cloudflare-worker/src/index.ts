/**
 * Saverwell Cloudflare Worker
 *
 * Three responsibilities:
 * 1. SEO Dynamic Rendering - pre-renders HTML for bot user agents on SEO routes
 * 2. Embeddable Widget API - serves embed.js + discount/subscribe APIs for partners
 * 3. Chat Widget - contextual AI chat assistant (RAG + Haiku streaming)
 *
 * SEO routes:   /retailer/*, /dma/*, /protect/*, /guides/*, /state/*, /sitemap.xml
 * Widget routes: /widget/v1/embed.js, /widget/v1/api/discounts, /widget/v1/api/subscribe
 * Chat routes:  /widget/v1/chat.js, /widget/v1/api/chat
 */

import { handleChat } from "./chat";
import { buildChatWidgetJs } from "./chat-widget";

export interface Env {
  SUPABASE_URL: string;
  SUPABASE_ANON_KEY: string;
  ANTHROPIC_API_KEY: string;
  SUBSCRIBE_WEBHOOK_URL?: string; // Optional n8n webhook for email signups
  WEB_READ_WEBHOOK_URL?: string;  // Optional n8n webhook for website read tracking
}

// Bot user-agent patterns (case-insensitive)
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
  "python-requests", // our validator
  "httpx",           // our validator
];

const SITE_ORIGIN = "https://saverwell.com";
const SITE_NAME = "Saverwell";

// State code -> URL slug lookup (51 entries: 50 states + DC)
const STATE_SLUGS: Record<string, string> = {
  AL: "alabama", AK: "alaska", AZ: "arizona", AR: "arkansas",
  CA: "california", CO: "colorado", CT: "connecticut",
  DE: "delaware", FL: "florida", GA: "georgia",
  HI: "hawaii", ID: "idaho", IL: "illinois",
  IN: "indiana", IA: "iowa", KS: "kansas",
  KY: "kentucky", LA: "louisiana", ME: "maine", MD: "maryland",
  MA: "massachusetts", MI: "michigan", MN: "minnesota",
  MS: "mississippi", MO: "missouri", MT: "montana",
  NE: "nebraska", NV: "nevada", NH: "new-hampshire",
  NJ: "new-jersey", NM: "new-mexico", NY: "new-york",
  NC: "north-carolina", ND: "north-dakota", OH: "ohio",
  OK: "oklahoma", OR: "oregon", PA: "pennsylvania",
  RI: "rhode-island", SC: "south-carolina", SD: "south-dakota",
  TN: "tennessee", TX: "texas", UT: "utah",
  VT: "vermont", VA: "virginia", WA: "washington",
  WV: "west-virginia", WI: "wisconsin", WY: "wyoming",
  DC: "district-of-columbia",
};

// State code -> display name lookup
const STATE_NAMES: Record<string, string> = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas",
  CA: "California", CO: "Colorado", CT: "Connecticut",
  DE: "Delaware", FL: "Florida", GA: "Georgia",
  HI: "Hawaii", ID: "Idaho", IL: "Illinois",
  IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota",
  MS: "Mississippi", MO: "Missouri", MT: "Montana",
  NE: "Nebraska", NV: "Nevada", NH: "New Hampshire",
  NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio",
  OK: "Oklahoma", OR: "Oregon", PA: "Pennsylvania",
  RI: "Rhode Island", SC: "South Carolina", SD: "South Dakota",
  TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington",
  WV: "West Virginia", WI: "Wisconsin", WY: "Wyoming",
  DC: "District of Columbia",
};

// Guide category slugs -> display info (matches guide_categories table)
// NOTE: categoryId values are assigned by Supabase. If IDs differ after migration,
// update them here. The migration script logs final IDs.
const GUIDE_CATEGORIES: Record<string, { name: string; description: string; categoryId: number }> = {
  "medicare": { name: "Medicare", description: "Medicare guides, enrollment, and coverage", categoryId: 1 },
  "insurance": { name: "Insurance", description: "Health, life, and supplemental insurance guides", categoryId: 2 },
  "retirement-taxes": { name: "Retirement & Taxes", description: "Social Security, pensions, tax strategy, and retirement planning", categoryId: 8 },
  "saving-money": { name: "Saving Money", description: "Budgeting, debt management, discounts, and everyday savings", categoryId: 9 },
  "caregiving": { name: "Caregiving", description: "Supporting aging parents with finances, legal, and end-of-life planning", categoryId: 10 },
  "senior-products": { name: "Senior Products", description: "Medical alerts, phones, and hearing aid reviews and comparisons", categoryId: 11 },
};

// "Find Local Discounts" CTA for guide and protection articles (bidirectional linking to DMA hub)
const LOCAL_DISCOUNTS_CTA = `<div class="local-cta"><h2>Find Senior Discounts Near You</h2><p>Browse verified discounts in your area.</p><ul><li><a href="${SITE_ORIGIN}/dma">Browse by Metro Area</a></li><li><a href="${SITE_ORIGIN}/states">Browse by State</a></li></ul></div>`;

// 301 redirects for old category URLs -> new destinations
const OLD_CATEGORY_REDIRECTS: Record<string, string> = {
  "medical-alerts": "/guides/senior-products",
  "phones": "/guides/senior-products",
  "hearing-aids": "/guides/senior-products",
  "finance": "/guides",
  "tools": "/guides",
  "protection": "/guides/saving-money",
  "discounts": "/guides/saving-money",
};

interface RouteMatch {
  type: "retailer" | "dma" | "protect" | "guides" | "state";
  slug: string;
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
  // SEO enhancements
  keywords?: string[];
  publishedTime?: string;
  modifiedTime?: string;
  author?: string;
  relatedLinks?: Array<{ title: string; url: string }>;
  alternativeHeadline?: string;
  wordCount?: number;
  articleSection?: string;
}

function matchRoute(pathname: string): RouteMatch | null {
  const patterns: Array<{ prefix: string; type: RouteMatch["type"] }> = [
    { prefix: "/retailer/", type: "retailer" },
    { prefix: "/dma/", type: "dma" },
    { prefix: "/protect/", type: "protect" },
    { prefix: "/guides/", type: "guides" },
    { prefix: "/state/", type: "state" },
  ];

  for (const p of patterns) {
    if (pathname.startsWith(p.prefix)) {
      const slug = pathname.slice(p.prefix.length).replace(/\/$/, "");
      if (slug && !slug.includes("/")) {
        // Skip category slugs — they are handled as listing pages, not articles
        if (p.type === "guides" && slug in GUIDE_CATEGORIES) continue;
        return { type: p.type, slug };
      }
    }
  }
  return null;
}

function isBot(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return BOT_PATTERNS.some((pattern) => ua.includes(pattern));
}

/**
 * Inject GTM, GA4 gtag, dataLayer helper, and GTM noscript into HTML.
 * Each component is independently idempotent (checks before injecting).
 * This handles the case where the Lovable origin already has GTM but not GA4.
 */
function injectAnalytics(html: string): string {
  // 1. Inject GTM snippet into <head> (if not already present)
  if (!html.includes("GTM-PZBKHZ6C")) {
    const gtmSnippet = [
      "<!-- Google Tag Manager -->",
      "<script>(function(w,d,s,l,i){w[l]=w[l]||[];w[l].push({'gtm.start':",
      "new Date().getTime(),event:'gtm.js'});var f=d.getElementsByTagName(s)[0],",
      "j=d.createElement(s),dl=l!='dataLayer'?'&l='+l:'';j.async=true;j.src=",
      "'https://www.googletagmanager.com/gtm.js?id='+i+dl;f.parentNode.insertBefore(j,f);",
      "})(window,document,'script','dataLayer','GTM-PZBKHZ6C');</script>",
      "<!-- End Google Tag Manager -->",
    ].join("\n");
    html = html.replace("</head>", gtmSnippet + "\n</head>");
  }
  // 2. Inject GA4 gtag into <head> (independent of GTM — check for GA4 measurement ID)
  if (!html.includes("G-YFGSQ1WTQM")) {
    const ga4Snippet = [
      "<!-- GA4 global site tag -->",
      '<script async src="https://www.googletagmanager.com/gtag/js?id=G-YFGSQ1WTQM"></script>',
      "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}",
      "gtag('js',new Date());gtag('config','G-YFGSQ1WTQM');</script>",
    ].join("\n");
    html = html.replace("</head>", ga4Snippet + "\n</head>");
  }
  // 3. Inject dataLayer helper into <head> (if not already present)
  if (!html.includes("sw-datalayer.js")) {
    const dlHelper =
      '<!-- Saverwell GA4 DataLayer Helper -->\n<script src="/scripts/sw-datalayer.js"></script>';
    html = html.replace("</head>", dlHelper + "\n</head>");
  }
  // 4. Inject GTM noscript fallback into <body> (if not already present)
  if (!html.includes("ns_GTM-PZBKHZ6C")) {
    const noscript =
      '<!-- Google Tag Manager (noscript) --><noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-PZBKHZ6C" id="ns_GTM-PZBKHZ6C" height="0" width="0" style="display:none;visibility:hidden"></iframe></noscript>';
    html = html.replace(/<body[^>]*>/, (match) => match + "\n" + noscript);
  }
  return html;
}

/**
 * Fetch origin, inject analytics if HTML, return response.
 */
async function fetchWithAnalytics(request: Request): Promise<Response> {
  const originResp = await fetch(request);
  const ct = originResp.headers.get("Content-Type") || "";
  if (ct.includes("text/html")) {
    let html = await originResp.text();
    html = injectAnalytics(html);
    const headers = new Headers(originResp.headers);
    return new Response(html, { status: originResp.status, headers });
  }
  return originResp;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function mdToHtml(md: string | null): string {
  if (!md) return "";
  return md
    .replace(/^### (.+)$/gm, "<h3>$1</h3>")
    .replace(/^## (.+)$/gm, "<h2>$1</h2>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\- (.+)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
    .replace(/\n\n/g, "</p><p>")
    .replace(/^(?!<)/, "<p>")
    .replace(/(?<!>)$/, "</p>");
}

// ---------------------------------------------------------------------------
// Supabase REST API helpers
// ---------------------------------------------------------------------------
async function supabaseQuery(
  env: Env,
  table: string,
  params: Record<string, string>
): Promise<any[] | null> {
  const url = new URL(`${env.SUPABASE_URL}/rest/v1/${table}`);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }

  const resp = await fetch(url.toString(), {
    headers: {
      apikey: env.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${env.SUPABASE_ANON_KEY}`,
      "Content-Type": "application/json",
    },
  });

  if (!resp.ok) return null;
  return resp.json();
}

async function supabaseSingle(
  env: Env,
  table: string,
  params: Record<string, string>
): Promise<any | null> {
  const rows = await supabaseQuery(env, table, { ...params, limit: "1" });
  return rows && rows.length > 0 ? rows[0] : null;
}

// ---------------------------------------------------------------------------
// Structured discount template helpers (no LLM, data-driven)
// ---------------------------------------------------------------------------
function formatRequirementClause(req: string | null | undefined): string {
  if (!req) return "";
  const r = req.trim();
  const lower = r.toLowerCase();
  // Age-style: "55+", "60+ years" -> " for customers aged 55+"
  if (/^\d{2}\+/.test(r)) return ` for customers aged ${r}`;
  // "Ages 65 and up" style
  if (lower.startsWith("ages ") || lower.startsWith("age "))
    return ` for customers ${lower}`;
  // Instruction-style: "Must show..." -> ". Must show..."
  if (["must ", "requires ", "need ", "show "].some((p) => lower.startsWith(p)))
    return `. ${r}`;
  // Named group: "AARP members" -> " for AARP members"
  return ` for ${r}`;
}

function buildDirectAnswer(data: any): string {
  if (!data.default_discount_text && !data.default_discount_value) {
    return data.page_direct_answer || "";
  }
  const discount = data.default_discount_text || `${data.default_discount_value} off`;
  const req = formatRequirementClause(data.default_discount_requirement);
  const details = data.default_discount_details
    ? ` ${data.default_discount_details}`
    : "";
  const dtype = (data.default_discount_type || "").toLowerCase();
  const where = dtype && dtype !== "n/a" ? ` ${dtype}` : "";
  return `Yes, ${data.name} offers ${discount}${req}.${details} The discount is available${where} at participating locations.`;
}

function buildHeroSubhead(data: any): string {
  if (data.default_discount_text) {
    return `${data.default_discount_text} at ${data.name}.`;
  }
  if (data.default_discount_value) {
    return `Save ${data.default_discount_value} at ${data.name} with their senior discount.`;
  }
  return data.page_hero_subhead || `Find senior savings at ${data.name}.`;
}

function buildSeoDescription(data: any): string {
  let base: string;
  if (data.default_discount_text) {
    base = `${data.name} offers ${data.default_discount_text}`;
  } else if (data.default_discount_value) {
    base = `${data.name} offers ${data.default_discount_value} off for seniors`;
  } else {
    return data.page_seo_description || "";
  }
  const req = data.default_discount_requirement
    ? ` (${data.default_discount_requirement})`
    : "";
  const suffix = ". See eligibility, how to save, and locations on Saverwell.";
  let desc = `${base}${req}${suffix}`;
  if (desc.length > 160) {
    desc = desc.substring(0, 157).replace(/\s\S*$/, "") + "...";
  }
  return desc;
}

function buildFaqs(data: any): Array<{ question: string; answer: string }> {
  if (!data.default_discount_text && !data.default_discount_value) {
    // Fall back to stored FAQ data
    if (Array.isArray(data.page_faq_json)) return data.page_faq_json;
    return tryParse(data.page_faq_json);
  }

  const name = data.name;
  const faqs: Array<{ question: string; answer: string }> = [];

  // Q1: Age requirement
  if (data.default_discount_requirement) {
    const reqClause = formatRequirementClause(data.default_discount_requirement);
    faqs.push({
      question: `What age do you need for ${name} senior discount?`,
      answer: `${name}'s senior discount is available${reqClause}.`,
    });
  } else {
    faqs.push({
      question: `What age do you need for ${name} senior discount?`,
      answer: `Age requirements for ${name}'s senior discount may vary by location. Check with your local store for specific eligibility details.`,
    });
  }

  // Q2: How much
  const discountDesc = data.default_discount_text || (data.default_discount_value ? `${data.default_discount_value} off` : null);
  if (discountDesc) {
    faqs.push({
      question: `How much is ${name} senior discount?`,
      answer: `${name} offers ${discountDesc} for eligible seniors.`,
    });
  }

  // Q3: How to get it
  if (data.default_discount_type) {
    faqs.push({
      question: `How do I get the ${name} senior discount?`,
      answer: `The ${name} senior discount is available ${data.default_discount_type.toLowerCase()}. Ask a team member at checkout or check their website for details.`,
    });
  }

  // Q4: When available
  if (data.default_discount_details) {
    faqs.push({
      question: `When is the ${name} senior discount available?`,
      answer: data.default_discount_details,
    });
  }

  return faqs;
}

// ---------------------------------------------------------------------------
// Page data fetchers (SEO rendering)
// ---------------------------------------------------------------------------
async function fetchPageData(
  env: Env,
  route: RouteMatch
): Promise<PageData | null> {
  switch (route.type) {
    case "retailer": {
      const data = await supabaseSingle(env, "v_merchant_pages", {
        select: "*",
        page_slug: `eq.${route.slug}`,
      });
      if (!data) return null;
      const faqJson = buildFaqs(data);

      // Affiliate disclosure + CTA for merchants with active affiliate links
      const affiliateUrl = data.affiliate_url || "";
      const hasAffiliate = data.has_affiliate === true && affiliateUrl;
      const ctaUrl = hasAffiliate ? affiliateUrl : (data.website_url || "");
      const ctaRel = hasAffiliate
        ? 'rel="sponsored nofollow noopener"'
        : 'rel="noopener"';
      const disclosureHtml = hasAffiliate
        ? `<div class="affiliate-disclosure"><p><small>This page contains affiliate links. Saverwell may earn a commission at no extra cost to you. This does not influence our recommendations. <a href="${SITE_ORIGIN}/disclosure">Learn more</a>.</small></p></div>`
        : "";
      const ctaHtml = ctaUrl
        ? `<div class="merchant-cta"><a href="${escapeHtml(ctaUrl)}" ${ctaRel} target="_blank" class="cta-button">${hasAffiliate ? "Shop " + escapeHtml(data.name) + " Deals" : "Visit " + escapeHtml(data.name)}</a></div>`
        : "";

      // Use template helpers for discount-derived fields, falling back to stored data
      const directAnswer = buildDirectAnswer(data);
      const heroSubhead = buildHeroSubhead(data);
      const seoDescription = buildSeoDescription(data);

      return {
        title:
          data.page_seo_title ||
          `${data.name} Senior Discount | ${SITE_NAME}`,
        description: seoDescription || data.page_seo_description || "",
        canonical: `${SITE_ORIGIN}/retailer/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Senior Discounts", url: `${SITE_ORIGIN}/retailers` },
          { name: data.name },
        ],
        headline: data.page_hero_headline || "",
        subhead: heroSubhead,
        bodyHtml: [
          disclosureHtml,
          directAnswer
            ? `<div class="direct-answer"><p>${escapeHtml(directAnswer)}</p></div>`
            : "",
          mdToHtml(data.page_about_md),
          ctaHtml,
          mdToHtml(data.page_how_to_save_md),
          mdToHtml(data.page_tips_md),
          mdToHtml(data.page_protection_note_md),
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson,
      };
    }

    case "dma": {
      const data = await supabaseSingle(env, "dma_page_content", {
        select: "*",
        slug: `eq.${route.slug}`,
        status: "eq.published",
      });
      if (!data) return null;
      const faqJson = Array.isArray(data.faq_json)
        ? data.faq_json
        : tryParse(data.faq_json);

      // Resolve parent state for breadcrumb
      const stateCodes = Array.isArray(data.state_codes)
        ? data.state_codes
        : tryParse(data.state_codes).map((s: any) => String(s));
      const primaryState = stateCodes.length > 0 ? stateCodes[0] : null;
      const stateSlug = primaryState ? STATE_SLUGS[primaryState] : null;
      const stateName = primaryState ? STATE_NAMES[primaryState] : null;

      // Cross-links to featured guides and protection articles (same pattern as state pages)
      const featuredGuideSlugs: string[] = Array.isArray(data.featured_guide_slugs)
        ? data.featured_guide_slugs
        : (typeof data.featured_guide_slugs === "string" ? tryParseJson(data.featured_guide_slugs) : []);
      const featuredProtectSlugs: string[] = Array.isArray(data.featured_protection_slugs)
        ? data.featured_protection_slugs
        : (typeof data.featured_protection_slugs === "string" ? tryParseJson(data.featured_protection_slugs) : []);
      let dmaRelatedLinks: Array<{ title: string; url: string }> = [];
      if (featuredGuideSlugs.length > 0) {
        const relGuides = await supabaseQuery(env, "guide_articles", {
          select: "title,slug",
          slug: `in.(${featuredGuideSlugs.join(",")})`,
          publish_web: "eq.true",
        });
        if (relGuides) {
          dmaRelatedLinks = dmaRelatedLinks.concat(relGuides.map((g: any) => ({
            title: g.title,
            url: `${SITE_ORIGIN}/guides/${g.slug}`,
          })));
        }
      }
      if (featuredProtectSlugs.length > 0) {
        const relProtect = await supabaseQuery(env, "protection_articles", {
          select: "title,slug",
          slug: `in.(${featuredProtectSlugs.join(",")})`,
        });
        if (relProtect) {
          dmaRelatedLinks = dmaRelatedLinks.concat(relProtect.map((p: any) => ({
            title: p.title,
            url: `${SITE_ORIGIN}/protect/${p.slug}`,
          })));
        }
      }

      // Sibling DMA cross-links ("Nearby Metro Areas")
      let siblingDmaHtml = "";
      if (primaryState) {
        const siblingDmas = await supabaseQuery(env, "dma_page_content", {
          select: "display_name,slug,merchant_count",
          "state_codes": `cs.["${primaryState}"]`,
          slug: `neq.${route.slug}`,
          status: "eq.published",
          order: "merchant_count.desc.nullslast",
          limit: "6",
        });
        if (siblingDmas && siblingDmas.length > 0) {
          const stateLabel = stateName || primaryState;
          siblingDmaHtml = `<div class="nearby-dmas"><h2>Nearby Metro Areas in ${escapeHtml(stateLabel)}</h2><ul>${siblingDmas.map((d: any) => `<li><a href="${SITE_ORIGIN}/dma/${escapeHtml(d.slug)}">${escapeHtml(d.display_name)}</a> - ${d.merchant_count || 0} merchants</li>`).join("")}</ul></div>`;
        }
      }

      return {
        title:
          data.seo_title ||
          `Senior Discounts in ${data.display_name} | ${SITE_NAME}`,
        description: data.seo_description || "",
        canonical: `${SITE_ORIGIN}/dma/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Senior Discounts by State", url: `${SITE_ORIGIN}/states` },
          ...(stateSlug && stateName
            ? [{ name: stateName, url: `${SITE_ORIGIN}/state/${stateSlug}` }]
            : []),
          { name: data.display_name },
        ],
        headline: data.hero_headline || "",
        subhead: data.hero_subhead || "",
        bodyHtml: [
          data.direct_answer
            ? `<div class="direct-answer"><p>${escapeHtml(data.direct_answer)}</p></div>`
            : "",
          data.merchant_count
            ? `<div class="stats"><span>${data.merchant_count} merchants</span> <span>${data.location_count || 0} locations</span> <span>${data.zip_count || 0} ZIP codes</span></div>`
            : "",
          mdToHtml(data.intro_md),
          mdToHtml(data.savings_spotlight_md),
          mdToHtml(data.local_tips_md),
          mdToHtml(data.protection_callout_md),
          siblingDmaHtml,
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson,
        publishedTime: data.created_at || undefined,
        modifiedTime: data.updated_at || undefined,
        relatedLinks: dmaRelatedLinks.length > 0 ? dmaRelatedLinks : undefined,
      };
    }

    case "state": {
      const data = await supabaseSingle(env, "state_page_content", {
        select: "*",
        slug: `eq.${route.slug}`,
        status: "eq.published",
      });
      if (!data) return null;
      const faqJson = Array.isArray(data.faq_json)
        ? data.faq_json
        : tryParse(data.faq_json);

      // Build DMA sub-links from dma_pages JSONB
      const dmaPages = Array.isArray(data.dma_pages)
        ? data.dma_pages
        : tryParse(data.dma_pages);
      const dmaLinksHtml = dmaPages.length
        ? `<div class="dma-directory"><h2>Explore Metro Areas in ${escapeHtml(data.state_name)}</h2><ul>${dmaPages.map((d: any) => `<li><a href="${SITE_ORIGIN}/dma/${escapeHtml(d.slug)}">${escapeHtml(d.display_name)}</a> - ${d.merchant_count || 0} merchants, ${d.location_count || 0} locations</li>`).join("")}</ul></div>`
        : "";

      const stateKeywords: string[] = Array.isArray(data.seo_keywords)
        ? data.seo_keywords
        : (typeof data.seo_keywords === "string" ? tryParseJson(data.seo_keywords) : []);

      // Cross-links to featured guides and protection articles
      const featuredGuideSlugs: string[] = Array.isArray(data.featured_guide_slugs)
        ? data.featured_guide_slugs
        : (typeof data.featured_guide_slugs === "string" ? tryParseJson(data.featured_guide_slugs) : []);
      const featuredProtectSlugs: string[] = Array.isArray(data.featured_protection_slugs)
        ? data.featured_protection_slugs
        : (typeof data.featured_protection_slugs === "string" ? tryParseJson(data.featured_protection_slugs) : []);
      let stateRelatedLinks: Array<{ title: string; url: string }> = [];
      if (featuredGuideSlugs.length > 0) {
        const relGuides = await supabaseQuery(env, "guide_articles", {
          select: "title,slug",
          slug: `in.(${featuredGuideSlugs.join(",")})`,
          publish_web: "eq.true",
        });
        if (relGuides) {
          stateRelatedLinks = stateRelatedLinks.concat(relGuides.map((g: any) => ({
            title: g.title,
            url: `${SITE_ORIGIN}/guides/${g.slug}`,
          })));
        }
      }
      if (featuredProtectSlugs.length > 0) {
        const relProtect = await supabaseQuery(env, "protection_articles", {
          select: "title,slug",
          slug: `in.(${featuredProtectSlugs.join(",")})`,
        });
        if (relProtect) {
          stateRelatedLinks = stateRelatedLinks.concat(relProtect.map((p: any) => ({
            title: p.title,
            url: `${SITE_ORIGIN}/protect/${p.slug}`,
          })));
        }
      }

      return {
        title:
          data.seo_title ||
          `Senior Discounts in ${data.state_name} | ${SITE_NAME}`,
        description: data.seo_description || "",
        canonical: `${SITE_ORIGIN}/state/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Senior Discounts by State", url: `${SITE_ORIGIN}/states` },
          { name: data.state_name },
        ],
        headline: data.hero_headline || "",
        subhead: data.hero_subhead || "",
        bodyHtml: [
          data.direct_answer
            ? `<div class="direct-answer"><p>${escapeHtml(data.direct_answer)}</p></div>`
            : "",
          data.merchant_count
            ? `<div class="stats"><span>${data.merchant_count} merchants</span> <span>${data.location_count || 0} locations</span> <span>${data.dma_count || 0} metro areas</span> <span>${data.zip_count || 0} ZIP codes</span></div>`
            : "",
          mdToHtml(data.intro_md),
          mdToHtml(data.savings_spotlight_md),
          mdToHtml(data.explore_areas_md),
          dmaLinksHtml,
          `<p><a href="${SITE_ORIGIN}/dma">Browse all metro areas nationwide</a></p>`,
          mdToHtml(data.local_tips_md),
          mdToHtml(data.protection_callout_md),
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson,
        keywords: stateKeywords,
        publishedTime: data.created_at || undefined,
        modifiedTime: data.updated_at || undefined,
        relatedLinks: stateRelatedLinks.length > 0 ? stateRelatedLinks : undefined,
      };
    }

    case "protect": {
      const data = await supabaseSingle(env, "protection_articles", {
        select: "*",
        slug: `eq.${route.slug}`,
      });
      if (!data) return null;
      const faqJson = Array.isArray(data.faq_json)
        ? data.faq_json
        : tryParse(data.faq_json);
      const protectKeywords: string[] = Array.isArray(data.seo_keywords)
        ? data.seo_keywords
        : (typeof data.seo_keywords === "string" ? tryParseJson(data.seo_keywords) : []);
      return {
        title: data.seo_title || `${data.title} | ${SITE_NAME}`,
        description: data.seo_description || data.subtitle || data.overview_md || "",
        canonical: `${SITE_ORIGIN}/protect/${route.slug}`,
        breadcrumbs: [
          { name: SITE_NAME, url: SITE_ORIGIN },
          { name: "Protection", url: `${SITE_ORIGIN}/protect` },
          { name: data.title },
        ],
        headline: data.title || "",
        subhead: data.subtitle || "",
        bodyHtml: [
          buildDirectAnswerBlock(data.overview_md),
          data.overview_md
            ? `<div class="overview"><h2>Overview</h2>${mdToHtml(data.overview_md)}</div>`
            : "",
          mdToHtml(data.body_md || data.content_md || ""),
          mdToHtml(data.red_flags_md),
          mdToHtml(data.what_to_do_md),
          mdToHtml(data.prevention_md),
          mdToHtml(data.phone_script_md),
          mdToHtml(data.resources_md),
          LOCAL_DISCOUNTS_CTA,
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson,
        keywords: protectKeywords,
        publishedTime: data.created_at || undefined,
        modifiedTime: data.updated_at || undefined,
        author: SITE_NAME,
        alternativeHeadline: data.subtitle || undefined,
        wordCount: (data.body_md || data.content_md || "").split(/\s+/).filter(Boolean).length || undefined,
      };
    }

    case "guides": {
      const data = await supabaseSingle(env, "guide_articles", {
        select: "*",
        slug: `eq.${route.slug}`,
        publish_web: "eq.true",
      });
      if (!data) return null;
      // guide_articles has faq_md (markdown) not faq_json - parse it
      const faqJson = parseFaqMd(data.faq_md);

      // Parse SEO keywords
      const seoKeywords: string[] = Array.isArray(data.seo_keywords)
        ? data.seo_keywords
        : (typeof data.seo_keywords === "string" ? tryParseJson(data.seo_keywords) : []);

      // Fetch related guide titles for cross-linking
      const relatedSlugs: string[] = Array.isArray(data.related_slugs)
        ? data.related_slugs
        : (typeof data.related_slugs === "string" ? tryParseJson(data.related_slugs) : []);
      let relatedLinks: Array<{ title: string; url: string }> = [];
      if (relatedSlugs.length > 0) {
        const relatedGuides = await supabaseQuery(env, "guide_articles", {
          select: "title,slug",
          slug: `in.(${relatedSlugs.join(",")})`,
          publish_web: "eq.true",
        });
        if (relatedGuides) {
          relatedLinks = relatedGuides.map((g: any) => ({
            title: g.title,
            url: `${SITE_ORIGIN}/guides/${g.slug}`,
          }));
        }
      }

      // Affiliate disclosure for monetized guides
      const guideDisclosure = data.affiliate_disclosure === true
        ? `<div class="affiliate-disclosure"><p><small>This article contains affiliate links. Saverwell may earn a commission at no extra cost to you. This does not influence our recommendations. <a href="${SITE_ORIGIN}/disclosure">Learn more</a>.</small></p></div>`
        : "";

      // Render comparison table with affiliate CTAs
      let comparisonHtml = "";
      const compTable = Array.isArray(data.comparison_table)
        ? data.comparison_table
        : tryParseJson(data.comparison_table);
      if (compTable.length > 0) {
        const keys = Object.keys(compTable[0]).filter(k => k !== "affiliate_url");
        const headerRow = keys.map(k => `<th>${escapeHtml(k)}</th>`).join("");
        const hasAnyAffiliate = compTable.some((r: any) => r.affiliate_url);
        const rows = compTable.map((row: any) => {
          const cells = keys.map(k => `<td>${escapeHtml(String(row[k] || ""))}</td>`).join("");
          const affiliateCell = row.affiliate_url
            ? `<td><a href="${escapeHtml(row.affiliate_url)}" rel="sponsored nofollow noopener" target="_blank">Check Rates</a></td>`
            : (hasAnyAffiliate ? `<td></td>` : "");
          return `<tr>${cells}${affiliateCell}</tr>`;
        }).join("");
        const affiliateHeader = hasAnyAffiliate ? `<th></th>` : "";
        comparisonHtml = `<div class="comparison-table"><table><thead><tr>${headerRow}${affiliateHeader}</tr></thead><tbody>${rows}</tbody></table></div>`;
      }

      // Resolve category for breadcrumbs
      const guideCatEntry = Object.entries(GUIDE_CATEGORIES).find(
        ([, c]) => c.categoryId === data.category_id
      );
      const guideBreadcrumbs: Array<{ name: string; url?: string }> = [
        { name: SITE_NAME, url: SITE_ORIGIN },
        { name: "Guides", url: `${SITE_ORIGIN}/guides` },
      ];
      if (guideCatEntry) {
        guideBreadcrumbs.push({
          name: guideCatEntry[1].name,
          url: `${SITE_ORIGIN}/guides/${guideCatEntry[0]}`,
        });
      }
      guideBreadcrumbs.push({ name: data.title });

      return {
        title: `${data.title} | ${SITE_NAME}`,
        description: data.subtitle || data.overview_md || "",
        canonical: `${SITE_ORIGIN}/guides/${route.slug}`,
        breadcrumbs: guideBreadcrumbs,
        headline: data.title || "",
        subhead: data.subtitle || "",
        bodyHtml: [
          guideDisclosure,
          buildDirectAnswerBlock(data.overview_md),
          data.overview_md
            ? `<div class="overview"><h2>Overview</h2>${mdToHtml(data.overview_md)}</div>`
            : "",
          data.key_takeaways_md
            ? `<div class="key-takeaways"><h2>Key Takeaways</h2>${mdToHtml(data.key_takeaways_md)}</div>`
            : "",
          mdToHtml(data.body_md || data.content_md || ""),
          comparisonHtml,
          data.savings_tips_md
            ? `<div class="savings-tips"><h2>Savings Tips</h2>${mdToHtml(data.savings_tips_md)}</div>`
            : "",
          data.watch_out_md
            ? `<div class="watch-out"><h2>Watch Out For</h2>${mdToHtml(data.watch_out_md)}</div>`
            : "",
          LOCAL_DISCOUNTS_CTA,
        ]
          .filter(Boolean)
          .join("\n"),
        faqJson,
        keywords: seoKeywords,
        publishedTime: data.created_at || undefined,
        modifiedTime: data.updated_at || undefined,
        author: data.author || SITE_NAME,
        relatedLinks,
        alternativeHeadline: data.subtitle || undefined,
        wordCount: (data.body_md || data.content_md || "").split(/\s+/).filter(Boolean).length || undefined,
        articleSection: guideCatEntry ? guideCatEntry[1].name : undefined,
      };
    }
  }
}

function tryParse(val: any): Array<{ question: string; answer: string }> {
  if (!val || typeof val !== "string") return [];
  try {
    const parsed = JSON.parse(val);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function tryParseJson(val: any): any[] {
  if (Array.isArray(val)) return val;
  if (!val || typeof val !== "string") return [];
  try {
    const parsed = JSON.parse(val);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// ---------------------------------------------------------------------------
// Gated content interstitial for guide pages
// ---------------------------------------------------------------------------
function isGatedVisit(request: Request, route: RouteMatch): boolean {
  if (route.type !== "guides") return false;
  const userAgent = request.headers.get("user-agent") || "";
  if (isBot(userAgent)) return false;
  const url = new URL(request.url);
  if (url.searchParams.get("utm_source") === "partner") return false;
  if (url.searchParams.get("utm_medium") === "email") return false;
  const cookie = request.headers.get("cookie") || "";
  if (cookie.split(";").some((c) => c.trim().startsWith("sw_subscribed="))) return false;
  return true;
}

function buildGateOverlay(slug: string): string {
  return `
<div id="sw-gate-overlay" style="position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.55);z-index:9999;display:flex;align-items:center;justify-content:center;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <div style="background:#fff;border-radius:12px;padding:32px 28px;max-width:440px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.25);text-align:center">
    <h2 style="margin:0 0 8px;font-size:22px;color:#1f2937">Get the Full Guide - Free</h2>
    <p style="margin:0 0 20px;font-size:15px;color:#6b7280">Enter your email and ZIP code to continue reading.</p>
    <form id="sw-gate-form" style="display:flex;flex-direction:column;gap:10px">
      <input id="sw-gate-email" type="email" required placeholder="Email address" style="padding:10px 14px;border:1px solid #d1d5db;border-radius:8px;font-size:15px;outline:none;font-family:inherit" />
      <input id="sw-gate-zip" type="text" pattern="[0-9]{5}" required placeholder="ZIP code" maxlength="5" style="padding:10px 14px;border:1px solid #d1d5db;border-radius:8px;font-size:15px;outline:none;font-family:inherit" />
      <button type="submit" id="sw-gate-btn" style="padding:12px;background:#2E7D32;color:#fff;border:none;border-radius:8px;font-size:16px;font-weight:600;cursor:pointer;font-family:inherit">Continue Reading</button>
    </form>
    <div id="sw-gate-error" style="display:none;margin-top:10px;color:#ef4444;font-size:14px"></div>
    <a href="#" id="sw-gate-skip" style="display:inline-block;margin-top:14px;color:#9ca3af;font-size:13px;text-decoration:none">Skip for now</a>
  </div>
</div>
<script>
(function(){
  var overlay=document.getElementById('sw-gate-overlay');
  var form=document.getElementById('sw-gate-form');
  var emailInput=document.getElementById('sw-gate-email');
  var zipInput=document.getElementById('sw-gate-zip');
  var btn=document.getElementById('sw-gate-btn');
  var errEl=document.getElementById('sw-gate-error');
  var skipLink=document.getElementById('sw-gate-skip');
  var slug=${JSON.stringify(slug)};

  function removeOverlay(){
    if(overlay&&overlay.parentNode){overlay.parentNode.removeChild(overlay)}
  }

  skipLink.addEventListener('click',function(e){
    e.preventDefault();
    removeOverlay();
  });

  form.addEventListener('submit',function(e){
    e.preventDefault();
    var email=emailInput.value.trim();
    var zip=zipInput.value.trim();
    if(!email||!zip)return;
    btn.disabled=true;
    btn.textContent='Submitting...';
    errEl.style.display='none';
    fetch('/widget/v1/api/subscribe',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({email:email,zip:zip,partner:'gated_content',source:'gated_content',content_slug:slug})
    }).then(function(r){
      if(r.ok){
        document.cookie='sw_subscribed=true;path=/;max-age=2592000;SameSite=Lax';
        removeOverlay();
      }else{
        btn.disabled=false;
        btn.textContent='Continue Reading';
        errEl.style.display='block';
        errEl.textContent='Something went wrong. Please try again.';
      }
    }).catch(function(){
      btn.disabled=false;
      btn.textContent='Continue Reading';
      errEl.style.display='block';
      errEl.textContent='Something went wrong. Please try again.';
    });
  });
})();
</script>`;
}

// ---------------------------------------------------------------------------
// HTML rendering (SEO)
// ---------------------------------------------------------------------------
function buildFaqJsonLd(
  faqs: Array<{ question: string; answer: string }>
): string {
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

function buildArticleJsonLd(page: PageData): string {
  if (!page.publishedTime) return "";
  const schema: Record<string, unknown> = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: page.headline,
    description: page.description,
    url: page.canonical,
    mainEntityOfPage: { "@type": "WebPage", "@id": page.canonical },
    image: "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/og-image.jpg",
    datePublished: page.publishedTime,
    author: {
      "@type": "Organization",
      name: page.author || SITE_NAME,
      url: SITE_ORIGIN,
    },
    publisher: {
      "@type": "Organization",
      name: SITE_NAME,
      url: SITE_ORIGIN,
    },
    speakable: {
      "@type": "SpeakableSpecification",
      cssSelector: [".direct-answer", ".overview", ".key-takeaways"],
    },
  };
  if (page.modifiedTime) schema.dateModified = page.modifiedTime;
  if (page.keywords && page.keywords.length > 0) {
    schema.keywords = page.keywords.join(", ");
  }
  if (page.alternativeHeadline) schema.alternativeHeadline = page.alternativeHeadline;
  if (page.wordCount) schema.wordCount = page.wordCount;
  if (page.articleSection) schema.articleSection = page.articleSection;
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function buildOrganizationJsonLd(): string {
  const schema = {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE_NAME,
    url: SITE_ORIGIN,
    description: "Saverwell helps seniors save money with verified discounts, savings guides, and fraud protection.",
  };
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function buildWebSiteJsonLd(): string {
  const schema = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: SITE_NAME,
    url: SITE_ORIGIN,
  };
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function buildItemListJsonLd(name: string, items: Array<{ name: string; url: string }>): string {
  if (!items.length) return "";
  const schema = {
    "@context": "https://schema.org",
    "@type": "ItemList",
    name,
    itemListElement: items.map((item, i) => ({
      "@type": "ListItem",
      position: i + 1,
      name: item.name,
      url: item.url,
    })),
  };
  return `<script type="application/ld+json">${JSON.stringify(schema)}</script>`;
}

function buildDirectAnswerBlock(overviewMd: string | null): string {
  if (!overviewMd) return "";
  const html = mdToHtml(overviewMd);
  const firstPMatch = html.match(/<p>([\s\S]*?)<\/p>/);
  if (!firstPMatch) return "";
  return `<div class="direct-answer"><p>${firstPMatch[1]}</p></div>`;
}

function parseFaqMd(faqMd: string | null): Array<{ question: string; answer: string }> {
  if (!faqMd) return [];
  const items: Array<{ question: string; answer: string }> = [];
  const parts = faqMd.split(/\*\*Q:\s*/);
  for (const part of parts.slice(1)) {
    const match = part.match(/^(.+?)\*\*\s*\n([\s\S]*?)(?=$)/);
    if (match) {
      const q = match[1].trim().replace(/\?$/, "") + "?";
      const a = match[2].trim();
      if (q && a) items.push({ question: q, answer: a });
    }
  }
  return items;
}

function renderFullHtml(page: PageData, gateOverlayHtml: string = ""): string {
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

  // Related guides section
  const relatedHtml = page.relatedLinks && page.relatedLinks.length > 0
    ? `<section class="related-guides">
  <h2>Related Guides</h2>
  <ul>
    ${page.relatedLinks.map(link => `<li><a href="${link.url}">${escapeHtml(link.title)}</a></li>`).join("\n    ")}
  </ul>
</section>`
    : "";

  // Keywords meta tag
  const keywordsMeta = page.keywords && page.keywords.length > 0
    ? `\n  <meta name="keywords" content="${escapeHtml(page.keywords.join(", "))}">`
    : "";

  // Article date meta tags
  const dateMeta = [
    page.publishedTime ? `\n  <meta property="article:published_time" content="${page.publishedTime}">` : "",
    page.modifiedTime ? `\n  <meta property="article:modified_time" content="${page.modifiedTime}">` : "",
  ].join("");

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(page.title)}</title>
  <meta name="description" content="${escapeHtml(page.description)}">${keywordsMeta}
  <link rel="canonical" href="${page.canonical}">
  <meta property="og:title" content="${escapeHtml(page.title)}">
  <meta property="og:description" content="${escapeHtml(page.description)}">
  <meta property="og:url" content="${page.canonical}">
  <meta property="og:type" content="article">
  <meta property="og:site_name" content="${SITE_NAME}">
  <meta property="og:image" content="https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/og-image.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">${dateMeta}
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${escapeHtml(page.title)}">
  <meta name="twitter:description" content="${escapeHtml(page.description)}">
  <meta name="twitter:image" content="https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/og-image.jpg">
  ${buildBreadcrumbJsonLd(page.breadcrumbs)}
  ${buildFaqJsonLd(page.faqJson)}
  ${buildArticleJsonLd(page)}
  ${buildOrganizationJsonLd()}
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
    ${relatedHtml}
  </main>
${gateOverlayHtml}
</body>
</html>`;
}

// ===========================================================================
// Widget: Embeddable discount widget for distribution partners
// ===========================================================================

const CORS_HEADERS: HeadersInit = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
};

function corsJson(body: unknown, status = 200, cache?: string): Response {
  const headers: Record<string, string> = {
    ...CORS_HEADERS,
    "Content-Type": "application/json",
  };
  if (cache) headers["Cache-Control"] = cache;
  return new Response(JSON.stringify(body), { status, headers });
}

// ---------------------------------------------------------------------------
// Widget API: GET /widget/v1/api/discounts?zip=XXXXX&categories=a,b&limit=5
// ---------------------------------------------------------------------------
async function handleWidgetDiscounts(
  url: URL,
  env: Env
): Promise<Response> {
  const zip = (url.searchParams.get("zip") || "").trim();
  if (!zip || !/^\d{5}$/.test(zip)) {
    return corsJson({ error: "Valid 5-digit zip parameter is required" }, 400);
  }

  const categories = url.searchParams.get("categories") || "";
  const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") || "5", 10), 1), 10);

  // 1. Look up DMA for this ZIP using the existing Zip_County_DMA table
  const zipRow = await supabaseSingle(env, "Zip_County_DMA", {
    select: "DMA_description",
    zip: `eq.${zip}`,
  });

  // Convert DMA description to URL slug (matches frontend createSlug + Python slugify_dma)
  let dmaSlug: string | null = null;
  let dmaName: string | null = null;
  let merchantCount = 0;

  if (zipRow?.DMA_description) {
    dmaSlug = zipRow.DMA_description.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");

    // Readable fallback: "PHOENIX (PRESCOTT)" -> "Phoenix (Prescott)"
    dmaName = zipRow.DMA_description
      .toLowerCase()
      .replace(/\b\w/g, (c: string) => c.toUpperCase());

    // Try to get the curated display name + merchant count from published DMA page
    const dmaPage = await supabaseSingle(env, "dma_page_content", {
      select: "display_name,merchant_count",
      slug: `eq.${dmaSlug}`,
      status: "eq.published",
    });
    if (dmaPage) {
      dmaName = dmaPage.display_name || dmaName;
      merchantCount = dmaPage.merchant_count || 0;
    }
  }

  // 2. Query published merchants
  const merchantParams: Record<string, string> = {
    select: "name,page_slug,logo_url,website_url,default_discount_value,default_discount_text,category_id",
    limit: String(limit),
    order: "name.asc",
  };

  // If categories provided, filter by category_id (caller must know IDs or we map names)
  if (categories) {
    const catList = categories.split(",").map((c) => c.trim()).filter(Boolean);
    if (catList.length > 0) {
      merchantParams.category_id = `in.(${catList.join(",")})`;
    }
  }

  const merchants = await supabaseQuery(env, "v_merchant_pages", merchantParams);

  // 3. Fetch latest protection article for alert teaser
  const alertRow = await supabaseSingle(env, "protection_articles", {
    select: "title,slug",
    order: "updated_at.desc",
    limit: "1",
  });

  // 4. Build response
  const response: Record<string, unknown> = {
    dma: dmaSlug
      ? { slug: dmaSlug, name: dmaName, merchantCount }
      : null,
    merchants: (merchants || []).map((m: any) => ({
      name: m.name,
      pageSlug: m.page_slug,
      logoUrl: m.logo_url || null,
      discountText: m.default_discount_text || "",
      discountValue: m.default_discount_value || "",
      websiteUrl: m.website_url || null,
    })),
    alert: alertRow ? { title: alertRow.title, slug: alertRow.slug } : null,
  };

  return corsJson(response, 200, "public, max-age=3600, s-maxage=14400");
}

// ---------------------------------------------------------------------------
// Widget API: POST /widget/v1/api/subscribe
// ---------------------------------------------------------------------------
async function handleWidgetSubscribe(
  request: Request,
  env: Env
): Promise<Response> {
  let body: {
    email?: string;
    zip?: string;
    partner?: string;
    source?: string;
    content_slug?: string;
  };
  try {
    body = await request.json();
  } catch {
    return corsJson({ error: "Invalid JSON body" }, 400);
  }

  const email = (body.email || "").trim().toLowerCase();
  const zip = (body.zip || "").trim();
  const partner = (body.partner || "").trim();
  const source = (body.source || "widget").trim();

  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return corsJson({ error: "Valid email is required" }, 400);
  }

  const payload: Record<string, string> = {
    email,
    zip,
    signup_type: "subscribe",
    brand: partner || "saverwell",
    utm_source: "partner",
    utm_campaign: partner,
    utm_medium: source === "chat" ? "chat" : "widget",
    source,
  };

  // Helper: insert directly into Supabase signups table
  const insertSignup = async (): Promise<Response> => {
    const supaUrl = `${env.SUPABASE_URL}/rest/v1/signups`;
    const resp = await fetch(supaUrl, {
      method: "POST",
      headers: {
        apikey: env.SUPABASE_ANON_KEY,
        Authorization: `Bearer ${env.SUPABASE_ANON_KEY}`,
        "Content-Type": "application/json",
        Prefer: "return=minimal",
      },
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const errText = await resp.text();
      console.error("Supabase insert error:", resp.status, errText);
      return corsJson({ error: "Subscription failed" }, 502);
    }
    return corsJson({ success: true });
  };

  try {
    // Option A: Forward to n8n webhook if configured
    if (env.SUBSCRIBE_WEBHOOK_URL) {
      const resp = await fetch(env.SUBSCRIBE_WEBHOOK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!resp.ok) {
        const errText = await resp.text();
        console.error("Webhook error:", resp.status, errText, "— falling back to Supabase insert");
        return insertSignup();
      }
      return corsJson({ success: true });
    }

    // Option B: Insert directly into Supabase signups table
    return insertSignup();
  } catch (err) {
    console.error("Subscribe error:", err);
    // Last-resort fallback to Supabase insert
    try {
      return await insertSignup();
    } catch (err2) {
      console.error("Supabase fallback also failed:", err2);
      return corsJson({ error: "Subscription failed" }, 500);
    }
  }
}

// ---------------------------------------------------------------------------
// Widget embed.js bundle (served as application/javascript)
// ---------------------------------------------------------------------------
const WIDGET_CSS = `\
:host{display:block;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;line-height:1.5}
*,*::before,*::after{box-sizing:border-box}
.sw{border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;max-width:400px;background:#fff;color:#1f2937}
.sw.dark{background:#1f2937;color:#f9fafb;border-color:#374151}
.sw-hd{display:flex;align-items:center;gap:8px;padding:16px 16px 8px}
.sw-hd h2{font-size:16px;font-weight:600;margin:0;line-height:1.3}
.sw-tag{flex-shrink:0;width:20px;height:20px}
.sw-cards{padding:0 16px}
.sw-cd{display:flex;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid #f3f4f6;text-decoration:none;color:inherit;transition:background .15s}
.dark .sw-cd{border-color:#374151}
.sw-cd:last-child{border-bottom:none}
.sw-cd:hover{background:#f9fafb}
.dark .sw-cd:hover{background:#283444}
.sw-logo{width:40px;height:40px;border-radius:8px;object-fit:contain;background:#f9fafb;flex-shrink:0}
.dark .sw-logo{background:#374151}
.sw-lp{width:40px;height:40px;border-radius:8px;background:#2A9D8F;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:18px;flex-shrink:0}
.sw-cb{min-width:0;flex:1}
.sw-mn{font-weight:600;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sw-dv{font-size:13px;color:#2A9D8F;margin-top:2px}
.sw-cta{display:block;text-align:center;padding:12px 16px;color:#2A9D8F;font-weight:600;font-size:14px;text-decoration:none;border-top:1px solid #f3f4f6}
.dark .sw-cta{border-color:#374151}
.sw-cta:hover{background:#f0fdfa}
.dark .sw-cta:hover{background:#1a3a36}
.sw-su{padding:12px 16px;border-top:1px solid #f3f4f6}
.dark .sw-su{border-color:#374151}
.sw-fm{display:flex;gap:8px}
.sw-em{flex:1;padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:13px;background:#fff;color:#1f2937;outline:none;font-family:inherit}
.dark .sw-em{background:#374151;border-color:#4b5563;color:#f9fafb}
.sw-em:focus{border-color:#2A9D8F;box-shadow:0 0 0 2px rgba(42,157,143,.2)}
.sw-btn{padding:8px 16px;background:#2A9D8F;color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:600;cursor:pointer;white-space:nowrap;font-family:inherit}
.sw-btn:hover{background:#238577}
.sw-btn:disabled{opacity:.6;cursor:not-allowed}
.sw-msg{font-size:13px;padding:8px 0}
.sw-ok{color:#2A9D8F}
.sw-err{color:#ef4444}
.sw-al{display:flex;align-items:center;gap:8px;padding:10px 16px;background:#fef2f2;color:#991b1b;font-size:13px;text-decoration:none;border-top:1px solid #f3f4f6}
.dark .sw-al{background:#451a1a;color:#fca5a5;border-color:#374151}
.sw-al:hover{background:#fee2e2}
.dark .sw-al:hover{background:#5a2424}
.sw-ft{text-align:center;padding:10px 16px;border-top:1px solid #f3f4f6}
.dark .sw-ft{border-color:#374151}
.sw-ft a{color:#9ca3af;font-size:11px;text-decoration:none}
.sw-ft a:hover{color:#2A9D8F}
.sw-ld{padding:40px;text-align:center}
.sw-sp{width:24px;height:24px;border:3px solid #e5e7eb;border-top-color:#2A9D8F;border-radius:50%;animation:swspin .8s linear infinite;margin:0 auto}
.dark .sw-sp{border-color:#374151;border-top-color:#2A9D8F}
@keyframes swspin{to{transform:rotate(360deg)}}
.sw-no{padding:16px;text-align:center;color:#9ca3af;font-size:14px}
.sw-no a{color:#2A9D8F}`;

const WIDGET_JS = `\
(function(){
'use strict';
var s=document.currentScript;
if(!s)return;
var C={
p:s.getAttribute('data-partner')||'',
z:s.getAttribute('data-zip')||'',
cat:s.getAttribute('data-categories')||'',
n:Math.min(Math.max(parseInt(s.getAttribute('data-count')||'5',10),1),10),
t:s.getAttribute('data-theme')||'light',
sp:s.getAttribute('data-show-protection')!=='false'
};
if(!C.z){console.warn('Saverwell widget: data-zip is required');return}
var O='https://saverwell.com';
var A=O+'/widget/v1';
function utm(c){return'utm_source=partner&utm_campaign='+encodeURIComponent(C.p)+'&utm_medium=widget&utm_content='+encodeURIComponent(c)}
function lnk(path,c){return O+path+(path.indexOf('?')>-1?'&':'?')+utm(c)}
function esc(str){var d=document.createElement('div');d.textContent=str;return d.innerHTML}
var host=document.createElement('div');
s.parentNode.insertBefore(host,s.nextSibling);
var sh=host.attachShadow({mode:'closed'});
var sty=document.createElement('style');
sty.textContent='__WIDGET_CSS__';
sh.appendChild(sty);
var root=document.createElement('div');
root.className='sw'+(C.t==='dark'?' dark':'');
sh.appendChild(root);
root.innerHTML='<div class="sw-ld"><div class="sw-sp"></div></div>';
var u=A+'/api/discounts?zip='+encodeURIComponent(C.z);
if(C.cat)u+='&categories='+encodeURIComponent(C.cat);
u+='&limit='+C.n;
fetch(u).then(function(r){return r.json()}).then(render).catch(errState);
function render(d){
var h='';
var title=d.dma?'Senior Discounts Near '+esc(d.dma.name):'Senior Discounts Near You';
h+='<div class="sw-hd"><svg class="sw-tag" viewBox="0 0 24 24" fill="none" stroke="#2A9D8F" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><circle cx="7" cy="7" r="1"/></svg><h2>'+title+'</h2></div>';
if(d.merchants&&d.merchants.length){
h+='<div class="sw-cards">';
d.merchants.forEach(function(m){
var href=lnk('/retailer/'+m.pageSlug,'discount_card');
h+='<a href="'+href+'" class="sw-cd" target="_blank" rel="noopener">';
if(m.logoUrl){h+='<img class="sw-logo" src="'+esc(m.logoUrl)+'" alt="'+esc(m.name)+'" loading="lazy" onerror="this.style.display=\\'none\\';this.nextElementSibling.style.display=\\'flex\\'"><div class="sw-lp" style="display:none">'+esc(m.name.charAt(0))+'</div>'}
else{h+='<div class="sw-lp">'+esc(m.name.charAt(0))+'</div>'}
h+='<div class="sw-cb"><div class="sw-mn">'+esc(m.name)+'</div>';
h+='<div class="sw-dv">'+esc(m.discountText||m.discountValue||'')+'</div>';
h+='</div></a>';
});
h+='</div>';
if(d.dma){
var seeAll=lnk('/dma/'+d.dma.slug,'see_all');
var ct=d.dma.merchantCount?'See all '+d.dma.merchantCount+' discounts near you':'See all discounts near you';
h+='<a href="'+seeAll+'" class="sw-cta" target="_blank" rel="noopener">'+ct+' \\u2192</a>';
}
}else{h+='<p class="sw-no">No discounts found for this area.</p>'}
h+='<div class="sw-su"><form class="sw-fm"><input type="email" class="sw-em" placeholder="Your email address" required><button type="submit" class="sw-btn">Subscribe</button></form><div class="sw-msg" style="display:none"></div></div>';
if(C.sp&&d.alert){
var ah=lnk('/protect/'+d.alert.slug,'protection_alert');
h+='<a href="'+ah+'" class="sw-al" target="_blank" rel="noopener"><span>\\u26A0\\uFE0F</span> '+esc(d.alert.title)+'</a>';
}
h+='<div class="sw-ft"><a href="'+lnk('/','powered_by')+'" target="_blank" rel="noopener">Powered by Saverwell</a></div>';
root.innerHTML=h;
var fm=root.querySelector('.sw-fm');
var em=root.querySelector('.sw-em');
var msg=root.querySelector('.sw-msg');
if(fm)fm.addEventListener('submit',function(e){
e.preventDefault();
var v=em.value.trim();
if(!v||!/.+@.+\\..+/.test(v))return;
var btn=root.querySelector('.sw-btn');
btn.disabled=true;btn.textContent='...';
fetch(A+'/api/subscribe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:v,zip:C.z,partner:C.p})})
.then(function(r){return r.json()})
.then(function(res){
if(res.success){fm.style.display='none';msg.style.display='block';msg.textContent='Check your inbox for your first savings digest!';msg.className='sw-msg sw-ok'}
else{btn.disabled=false;btn.textContent='Subscribe';msg.style.display='block';msg.textContent='Something went wrong. Try again.';msg.className='sw-msg sw-err'}
})
.catch(function(){btn.disabled=false;btn.textContent='Subscribe';msg.style.display='block';msg.textContent='Something went wrong. Try again.';msg.className='sw-msg sw-err'});
});
}
function errState(){root.innerHTML='<p class="sw-no">Unable to load discounts. <a href="'+lnk('/','powered_by')+'" target="_blank" rel="noopener">Visit Saverwell</a></p>'}
})();`;

function buildEmbedJs(): string {
  // Inject the CSS into the JS bundle at the placeholder
  return WIDGET_JS.replace("'__WIDGET_CSS__'", JSON.stringify(WIDGET_CSS));
}

function handleWidgetEmbed(): Response {
  return new Response(buildEmbedJs(), {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=900, s-maxage=3600",
      ...CORS_HEADERS,
    },
  });
}

function handleChatWidgetJs(): Response {
  return new Response(buildChatWidgetJs(), {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Cache-Control": "public, max-age=900, s-maxage=3600",
      ...CORS_HEADERS,
    },
  });
}

// ---------------------------------------------------------------------------
// GA4 DataLayer script (serves updated version with emailSignup method)
// ---------------------------------------------------------------------------
const SW_DATALAYER_JS = `\
(function () {
  "use strict";

  window.__swWebReadUrl = "__WEB_READ_WEBHOOK_URL__";

  window.dataLayer = window.dataLayer || [];

  function getCookie(name) {
    var match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : "";
  }

  function getUtmParam(name) {
    var params = new URLSearchParams(window.location.search);
    return params.get(name) || getCookie(name) || "";
  }

  function getFirstTouch() {
    var key = "sw_first_touch";
    var stored = localStorage.getItem(key);
    if (stored) {
      try { return JSON.parse(stored); } catch (e) {}
    }
    var ft = {
      source: getUtmParam("utm_source"),
      medium: getUtmParam("utm_medium"),
      campaign: getUtmParam("utm_campaign"),
      content: getUtmParam("utm_content"),
    };
    if (ft.source || ft.medium || ft.campaign || ft.content) {
      localStorage.setItem(key, JSON.stringify(ft));
    }
    return ft;
  }

  function getLastTouch() {
    return {
      source: getUtmParam("utm_source"),
      medium: getUtmParam("utm_medium"),
    };
  }

  function getAttributionParams() {
    var ft = getFirstTouch();
    var lt = getLastTouch();
    return {
      first_touch_source: ft.source,
      first_touch_medium: ft.medium,
      first_touch_campaign: ft.campaign,
      first_touch_content: ft.content,
      last_touch_source: lt.source,
      last_touch_medium: lt.medium,
    };
  }

  function getUserId() {
    return localStorage.getItem("sw_user_id") || "";
  }

  function hashEmail(email) {
    var normalized = email.toLowerCase().trim();
    if (window.crypto && window.crypto.subtle) {
      return window.crypto.subtle
        .digest("SHA-256", new TextEncoder().encode(normalized))
        .then(function (buffer) {
          var hashArray = Array.from(new Uint8Array(buffer));
          return hashArray.map(function (b) { return b.toString(16).padStart(2, "0"); }).join("");
        });
    }
    var hash = 5381;
    for (var i = 0; i < normalized.length; i++) {
      hash = ((hash << 5) + hash + normalized.charCodeAt(i)) & 0xffffffff;
    }
    return Promise.resolve("djb2_" + (hash >>> 0).toString(16));
  }

  function detectPageType() {
    var path = window.location.pathname;
    if (path === "/") return "homepage";
    if (path.indexOf("/retailer/") === 0) return "merchant";
    if (path.indexOf("/dma/") === 0) return "dma";
    if (path.indexOf("/protect/") === 0) return "protection";
    if (path.indexOf("/guides/") === 0) return "guide";
    return "other";
  }

  function extractIdFromPath(prefix) {
    var path = window.location.pathname;
    if (path.indexOf(prefix) === 0) {
      return path.substring(prefix.length).replace(/\\/$/, "");
    }
    return "";
  }

  function push(eventName, params) {
    var data = { event: eventName };
    if (params) {
      for (var key in params) {
        if (params.hasOwnProperty(key)) {
          data[key] = params[key];
        }
      }
    }
    var uid = getUserId();
    if (uid) { data.user_id = uid; }
    window.dataLayer.push(data);
  }

  var scrollThresholds = [25, 50, 75, 100];
  var firedThresholds = {};

  function getScrollPercent() {
    var h = document.documentElement;
    var b = document.body;
    var st = window.pageYOffset || h.scrollTop || b.scrollTop || 0;
    var sh = Math.max(b.scrollHeight, h.scrollHeight, b.offsetHeight, h.offsetHeight, b.clientHeight, h.clientHeight);
    var ch = window.innerHeight || h.clientHeight || b.clientHeight;
    if (sh <= ch) return 100;
    return Math.round((st / (sh - ch)) * 100);
  }

  var scrollTimer = null;
  function onScroll() {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () {
      scrollTimer = null;
      var pct = getScrollPercent();
      var pageType = detectPageType();
      for (var i = 0; i < scrollThresholds.length; i++) {
        var t = scrollThresholds[i];
        if (pct >= t && !firedThresholds[t]) {
          firedThresholds[t] = true;
          push("scroll_depth", { page_type: pageType, depth_percent: t });
        }
      }
    }, 200);
  }

  window.addEventListener("scroll", onScroll, { passive: true });

  var pageLoadTime = Date.now();

  function getReadingMinutes() {
    return Math.round((Date.now() - pageLoadTime) / 60000 * 10) / 10;
  }

  window.swTrack = {
    setUserId: function (email) {
      hashEmail(email).then(function (hashed) {
        localStorage.setItem("sw_user_id", hashed);
        window.dataLayer.push({ user_id: hashed });
      });
    },

    pageView: function (params) {
      var pageType = detectPageType();
      var attribution = getAttributionParams();
      var data = {
        page_type: pageType,
        merchant_id: extractIdFromPath("/retailer/"),
        dma_id: extractIdFromPath("/dma/"),
        content_category: pageType,
      };
      for (var key in attribution) {
        if (attribution.hasOwnProperty(key)) { data[key] = attribution[key]; }
      }
      if (params) {
        for (var key in params) {
          if (params.hasOwnProperty(key)) { data[key] = params[key]; }
        }
      }
      push("page_view", data);

      // Beacon website reads to n8n for digest personalization
      if ((pageType === "guide" || pageType === "protection") && getUserId()) {
        var slug = window.location.pathname.split("/").pop();
        if (slug && navigator.sendBeacon && window.__swWebReadUrl) {
          navigator.sendBeacon(
            window.__swWebReadUrl,
            JSON.stringify({
              email_hash: getUserId(),
              article_slug: slug,
              page_type: pageType
            })
          );
        }
      }
    },

    outboundClick: function (params) {
      var data = params || {};
      data.page_type = data.page_type || detectPageType();
      push("outbound_click", data);
    },

    discountClick: function (params) {
      push("discount_click", params || {});
    },

    affiliateClick: function (params) {
      var data = params || {};
      push("affiliate_click", data);
      if (navigator.sendBeacon) {
        var payload = JSON.stringify({
          event: "affiliate_click",
          merchant_id: data.merchant_id || "",
          commission_type: data.commission_type || "",
          page_type: detectPageType(),
        });
        navigator.sendBeacon(
          "https://www.google-analytics.com/g/collect?v=2&tid=" +
            (document.querySelector("[data-gtm-id]")
              ? document.querySelector("[data-gtm-id]").dataset.gtmId
              : ""),
          payload
        );
      }
    },

    protectionRead: function (params) {
      var data = params || {};
      data.reading_minutes = data.reading_minutes || getReadingMinutes();
      push("protection_read", data);
    },

    protectionShare: function (params) {
      push("protection_share", params || {});
    },

    guideRead: function (params) {
      var data = params || {};
      data.reading_minutes = data.reading_minutes || getReadingMinutes();
      push("guide_read", data);
    },

    guideShare: function (params) {
      push("guide_share", params || {});
    },

    shareContent: function (params) {
      push("share_content", params || {});
    },

    searchQuery: function (params) {
      push("search_query", params || {});
    },

    zipLookup: function (params) {
      push("zip_lookup", params || {});
    },

    storeDirections: function (params) {
      push("store_directions", params || {});
    },

    scamAlertView: function (params) {
      push("scam_alert_view", params || {});
    },

    emailSignup: function (params) {
      var data = params || {};
      push("email_signup_client", data);
      if (data.email) {
        window.swTrack.setUserId(data.email);
      }
    },
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      window.swTrack.pageView();
    });
  } else {
    window.swTrack.pageView();
  }
})();`;

// ---------------------------------------------------------------------------
// Listing page types for hub/index pages
// ---------------------------------------------------------------------------
type ListingType = "home" | "retailers" | "states" | "dma_index" | "protect_index" | "guides_index" | "guides_category";

interface ListingMatch {
  type: ListingType;
  categorySlug?: string;
}

function matchListingPage(pathname: string): ListingMatch | null {
  const p = pathname.replace(/\/$/, "") || "/";
  if (p === "/") return { type: "home" };
  if (p === "/retailers") return { type: "retailers" };
  if (p === "/states") return { type: "states" };
  if (p === "/dma") return { type: "dma_index" };
  if (p === "/protect") return { type: "protect_index" };
  if (p === "/guides") return { type: "guides_index" };
  // Guide category pages: /guides/{category-slug}
  const guideCatMatch = p.match(/^\/guides\/([a-z][a-z0-9-]+)$/);
  if (guideCatMatch && guideCatMatch[1] in GUIDE_CATEGORIES) {
    return { type: "guides_category", categorySlug: guideCatMatch[1] };
  }
  return null;
}

interface ListingItem {
  name: string;
  slug: string;
  detail?: string;
}

function groupByLetter(items: ListingItem[]): Record<string, ListingItem[]> {
  const groups: Record<string, ListingItem[]> = {};
  for (const item of items) {
    const letter = (item.name[0] || "#").toUpperCase();
    const key = /[A-Z]/.test(letter) ? letter : "#";
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

function renderListingHtml(
  title: string,
  description: string,
  canonical: string,
  headline: string,
  intro: string,
  breadcrumbs: Array<{ name: string; url?: string }>,
  sections: Array<{ heading?: string; items: ListingItem[]; pathPrefix: string }>,
  useLetterGroups: boolean = false,
  extraJsonLd: string = ""
): string {
  const bcJsonLd = buildBreadcrumbJsonLd(breadcrumbs);
  const bcNav = breadcrumbs
    .map((b, i) =>
      b.url
        ? `<a href="${b.url}">${escapeHtml(b.name)}</a>${i < breadcrumbs.length - 1 ? " &gt; " : ""}`
        : `<span>${escapeHtml(b.name)}</span>`
    )
    .join("");

  let bodyHtml = `<p>${escapeHtml(intro)}</p>`;

  for (const section of sections) {
    if (section.heading) {
      bodyHtml += `<h2>${escapeHtml(section.heading)}</h2>`;
    }
    if (useLetterGroups && section.items.length > 50) {
      const groups = groupByLetter(section.items);
      const letters = Object.keys(groups).sort();
      bodyHtml += `<nav class="alpha-nav">${letters.map((l) => `<a href="#letter-${l}">${l}</a>`).join(" ")}</nav>`;
      for (const letter of letters) {
        bodyHtml += `<h3 id="letter-${letter}">${letter}</h3><ul>`;
        for (const item of groups[letter]) {
          bodyHtml += `<li><a href="${SITE_ORIGIN}${section.pathPrefix}${escapeHtml(item.slug)}">${escapeHtml(item.name)}</a>${item.detail ? ` - ${escapeHtml(item.detail)}` : ""}</li>`;
        }
        bodyHtml += `</ul>`;
      }
    } else {
      bodyHtml += `<ul>`;
      for (const item of section.items) {
        bodyHtml += `<li><a href="${SITE_ORIGIN}${section.pathPrefix}${escapeHtml(item.slug)}">${escapeHtml(item.name)}</a>${item.detail ? ` - ${escapeHtml(item.detail)}` : ""}</li>`;
      }
      bodyHtml += `</ul>`;
    }
  }

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <meta name="description" content="${escapeHtml(description)}">
  <link rel="canonical" href="${canonical}">
  <meta property="og:title" content="${escapeHtml(title)}">
  <meta property="og:description" content="${escapeHtml(description)}">
  <meta property="og:url" content="${canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="${SITE_NAME}">
  <meta property="og:image" content="https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/og-image.jpg">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${escapeHtml(title)}">
  <meta name="twitter:description" content="${escapeHtml(description)}">
  <meta name="twitter:image" content="https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/og-image.jpg">
  ${bcJsonLd}
  ${buildOrganizationJsonLd()}
  ${extraJsonLd}
</head>
<body>
  <nav aria-label="breadcrumb">${bcNav}</nav>
  <main>
    <h1>${escapeHtml(headline)}</h1>
    <article>${bodyHtml}</article>
  </main>
</body>
</html>`;
}

async function fetchListingPage(
  env: Env,
  listing: ListingMatch
): Promise<Response | null> {
  switch (listing.type) {
    case "home": {
      const [merchants, states, dmas, articles, guides] = await Promise.all([
        supabaseQuery(env, "v_merchant_pages", { select: "name,page_slug", order: "name.asc", limit: "2000" }),
        supabaseQuery(env, "state_page_content", { select: "state_name,slug,merchant_count,dma_count", status: "eq.published", order: "state_name.asc", limit: "60" }),
        supabaseQuery(env, "dma_page_content", { select: "display_name,slug,merchant_count", status: "eq.published", order: "merchant_count.desc.nullslast", limit: "10" }),
        supabaseQuery(env, "protection_articles", { select: "title,slug", order: "updated_at.desc", limit: "10" }),
        supabaseQuery(env, "guide_articles", { select: "title,slug", publish_web: "eq.true", order: "updated_at.desc", limit: "10" }),
      ]);
      const mCount = merchants?.length || 0;
      const sCount = states?.length || 0;
      const dCount = dmas?.length || 0;
      return new Response(
        renderListingHtml(
          `Saverwell | Money-Saving Guides for Medicare, Insurance & Retirement`,
          `Expert guides on Medicare, Social Security, insurance, and everyday savings, plus verified discounts at ${mCount.toLocaleString()}+ stores. Free resources for seniors across all 50 states.`,
          SITE_ORIGIN,
          "Money-Saving Guides for Medicare, Insurance & Retirement",
          `Saverwell helps seniors save money with ${mCount.toLocaleString()} verified discounts across ${sCount} states, 100+ expert guides on Medicare, insurance, and retirement, and safety tips to keep your finances secure.`,
          [{ name: SITE_NAME }],
          [
            {
              heading: `Browse ${mCount.toLocaleString()} Senior Discounts`,
              items: [
                { name: `All ${mCount.toLocaleString()} Senior Discounts`, slug: "retailers", detail: "Browse the full store directory" },
                { name: `Senior Discounts by State`, slug: "states", detail: `${sCount} states with local deals` },
                { name: `Senior Discounts by Metro Area`, slug: "dma", detail: `${dCount}+ metro areas` },
              ],
              pathPrefix: "/",
            },
            {
              heading: "Top Metro Areas for Senior Discounts",
              items: (dmas || []).map((d: any) => ({
                name: d.display_name,
                slug: d.slug,
                detail: `${d.merchant_count || 0} merchants`,
              })),
              pathPrefix: "/dma/",
            },
            {
              heading: "Savings Guides",
              items: (guides || []).map((g: any) => ({ name: g.title, slug: g.slug })),
              pathPrefix: "/guides/",
            },
            {
              heading: "Safety & Security Guides",
              items: (articles || []).map((a: any) => ({ name: a.title, slug: a.slug })),
              pathPrefix: "/protect/",
            },
          ],
          false,
          buildWebSiteJsonLd()
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "retailers": {
      const merchants = await supabaseQuery(env, "v_merchant_pages", {
        select: "name,page_slug,default_discount_text",
        order: "name.asc",
        limit: "2000",
      });
      if (!merchants || merchants.length === 0) return null;
      return new Response(
        renderListingHtml(
          `All Senior Discounts: ${merchants.length.toLocaleString()}+ Stores & Restaurants | ${SITE_NAME}`,
          `Browse ${merchants.length.toLocaleString()} verified senior discounts at stores, restaurants, and services across America. Find savings near you.`,
          `${SITE_ORIGIN}/retailers`,
          `All ${merchants.length.toLocaleString()} Senior Discounts`,
          `Browse every verified senior discount in our directory. From grocery stores and restaurants to hardware stores and pharmacies, find savings at ${merchants.length.toLocaleString()} merchants across America.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Senior Discounts" },
          ],
          [{
            items: merchants.map((m: any) => ({
              name: m.name,
              slug: m.page_slug,
              detail: m.default_discount_text || undefined,
            })),
            pathPrefix: "/retailer/",
          }],
          true
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "states": {
      const states = await supabaseQuery(env, "state_page_content", {
        select: "state_name,slug,merchant_count,dma_count",
        status: "eq.published",
        order: "state_name.asc",
        limit: "60",
      });
      if (!states || states.length === 0) return null;
      const totalMerchants = states.reduce((sum: number, s: any) => sum + (s.merchant_count || 0), 0);
      return new Response(
        renderListingHtml(
          `Senior Discounts by State: All 50 States | ${SITE_NAME}`,
          `Find senior discounts in your state. Browse ${totalMerchants.toLocaleString()} verified discounts across all 50 states and Washington D.C.`,
          `${SITE_ORIGIN}/states`,
          "Senior Discounts by State",
          `Find senior discounts near you by browsing your state. We track ${totalMerchants.toLocaleString()} verified senior discounts across all 50 states and Washington D.C.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Senior Discounts by State" },
          ],
          [{
            items: states.map((s: any) => ({
              name: s.state_name,
              slug: s.slug,
              detail: `${s.merchant_count || 0} merchants, ${s.dma_count || 0} metro areas`,
            })),
            pathPrefix: "/state/",
          }]
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "dma_index": {
      const dmas = await supabaseQuery(env, "dma_page_content", {
        select: "display_name,slug,merchant_count,state_codes",
        status: "eq.published",
        order: "display_name.asc",
        limit: "300",
      });
      if (!dmas || dmas.length === 0) return null;

      // Group DMAs by primary state
      const byState: Record<string, Array<{ display_name: string; slug: string; merchant_count: number }>> = {};
      for (const d of dmas) {
        const codes = Array.isArray(d.state_codes)
          ? d.state_codes
          : (typeof d.state_codes === "string" ? tryParseJson(d.state_codes) : []);
        const primary = codes.length > 0 ? String(codes[0]) : "Other";
        if (!byState[primary]) byState[primary] = [];
        byState[primary].push(d);
      }

      // Sort states alphabetically by state name
      const sortedStates = Object.keys(byState).sort((a, b) => {
        const nameA = STATE_NAMES[a] || a;
        const nameB = STATE_NAMES[b] || b;
        return nameA.localeCompare(nameB);
      });

      // Build sections: one per state
      const sections = sortedStates.map((code) => ({
        heading: STATE_NAMES[code] || code,
        items: byState[code].map((d: any) => ({
          name: d.display_name,
          slug: d.slug,
          detail: `${d.merchant_count || 0} merchants`,
        })),
        pathPrefix: "/dma/",
      }));

      return new Response(
        renderListingHtml(
          `Senior Discounts by Metro Area: ${dmas.length} Cities | ${SITE_NAME}`,
          `Find senior discounts in ${dmas.length} metro areas across ${sortedStates.length} states. Browse local deals near you.`,
          `${SITE_ORIGIN}/dma`,
          `Senior Discounts by Metro Area`,
          `Browse senior discounts in ${dmas.length} metro areas across ${sortedStates.length} states. Find verified local deals from stores, restaurants, and services near you.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Senior Discounts by Metro Area" },
          ],
          sections
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "protect_index": {
      const articles = await supabaseQuery(env, "protection_articles", {
        select: "title,slug,subtitle",
        order: "updated_at.desc",
        limit: "100",
      });
      if (!articles || articles.length === 0) return null;
      return new Response(
        renderListingHtml(
          `Senior Fraud Protection & Scam Alerts | ${SITE_NAME}`,
          `Protect yourself from scams targeting seniors. Read ${articles.length} guides on fraud prevention, identity theft, and online safety.`,
          `${SITE_ORIGIN}/protect`,
          "Senior Fraud Protection & Scam Alerts",
          `Stay safe with ${articles.length} fraud protection guides written for seniors. Learn to spot scams, protect your identity, and keep your money safe.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Protection" },
          ],
          [{
            items: articles.map((a: any) => ({
              name: a.title,
              slug: a.slug,
              detail: a.subtitle || undefined,
            })),
            pathPrefix: "/protect/",
          }]
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "guides_index": {
      const guides = await supabaseQuery(env, "guide_articles", {
        select: "title,slug,subtitle,category_id",
        publish_web: "eq.true",
        order: "category_id.asc,updated_at.desc",
        limit: "200",
      });
      if (!guides || guides.length === 0) return null;

      // Group guides by category for structured display
      const categoryOrder = Object.entries(GUIDE_CATEGORIES);
      const sections: Array<{ heading?: string; items: ListingItem[]; pathPrefix: string }> = [];

      // Add a category navigation section
      const catNavItems: ListingItem[] = categoryOrder
        .filter(([slug, cat]) => guides.some((g: any) => g.category_id === cat.categoryId))
        .map(([slug, cat]) => {
          const count = guides.filter((g: any) => g.category_id === cat.categoryId).length;
          return { name: cat.name, slug, detail: `${count} guide${count !== 1 ? "s" : ""}` };
        });
      sections.push({ heading: "Browse by Category", items: catNavItems, pathPrefix: "/guides/" });

      // Add each category with its guides
      for (const [catSlug, cat] of categoryOrder) {
        const catGuides = guides.filter((g: any) => g.category_id === cat.categoryId);
        if (catGuides.length === 0) continue;
        sections.push({
          heading: `${cat.name} Guides`,
          items: catGuides.map((g: any) => ({
            name: g.title,
            slug: g.slug,
            detail: g.subtitle || undefined,
          })),
          pathPrefix: "/guides/",
        });
      }

      return new Response(
        renderListingHtml(
          `Savings Guides for Seniors: Medicare, Retirement, Insurance & More | ${SITE_NAME}`,
          `Read ${guides.length} expert guides on Medicare, retirement planning, insurance, caregiving, and senior products. Save money on the things that matter.`,
          `${SITE_ORIGIN}/guides`,
          "Savings Guides for Seniors",
          `Expert guides to help seniors save on Medicare, retirement, insurance, caregiving, and senior products. Written in plain language with actionable tips.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Guides" },
          ],
          sections,
          false,
          buildItemListJsonLd(
            "Savings Guides for Seniors",
            guides.map((g: any) => ({ name: g.title, url: `${SITE_ORIGIN}/guides/${g.slug}` }))
          )
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }

    case "guides_category": {
      const catSlug = listing.categorySlug;
      if (!catSlug || !(catSlug in GUIDE_CATEGORIES)) return null;
      const cat = GUIDE_CATEGORIES[catSlug];

      const guides = await supabaseQuery(env, "guide_articles", {
        select: "title,slug,subtitle",
        publish_web: "eq.true",
        category_id: `eq.${cat.categoryId}`,
        order: "updated_at.desc",
        limit: "100",
      });
      if (!guides || guides.length === 0) return null;

      // Other categories for cross-navigation
      const otherCats = Object.entries(GUIDE_CATEGORIES)
        .filter(([s]) => s !== catSlug)
        .map(([s, c]) => ({ name: c.name, slug: s, detail: c.description }));

      return new Response(
        renderListingHtml(
          `${cat.name} Guides for Seniors | ${SITE_NAME}`,
          `${cat.description}. Read ${guides.length} expert ${cat.name.toLowerCase()} guide${guides.length !== 1 ? "s" : ""} written in plain language for seniors.`,
          `${SITE_ORIGIN}/guides/${catSlug}`,
          `${cat.name} Guides for Seniors`,
          `${cat.description}. Written in plain language with actionable savings tips.`,
          [
            { name: SITE_NAME, url: SITE_ORIGIN },
            { name: "Guides", url: `${SITE_ORIGIN}/guides` },
            { name: cat.name },
          ],
          [
            {
              items: guides.map((g: any) => ({
                name: g.title,
                slug: g.slug,
                detail: g.subtitle || undefined,
              })),
              pathPrefix: "/guides/",
            },
            {
              heading: "More Guide Categories",
              items: otherCats,
              pathPrefix: "/guides/",
            },
          ],
          false,
          buildItemListJsonLd(
            `${cat.name} Guides for Seniors`,
            guides.map((g: any) => ({ name: g.title, url: `${SITE_ORIGIN}/guides/${g.slug}` }))
          )
        ),
        {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=3600, s-maxage=86400",
            "X-Robots-Tag": "index, follow",
            "X-Rendered-By": "saverwell-seo-renderer",
          },
        }
      );
    }
  }
}

// ---------------------------------------------------------------------------
// Worker entry point
// ---------------------------------------------------------------------------
export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    const url = new URL(request.url);
    const pathname = url.pathname;

    // --- Legacy URL redirects (from old saverwell.com site) ---
    const LEGACY_REDIRECTS: Record<string, string> = {
      "/terms": "/terms-of-service",
      "/privacy": "/privacy-policy",
    };
    const redirectTarget = LEGACY_REDIRECTS[pathname];
    if (redirectTarget) {
      const dest = new URL(redirectTarget, SITE_ORIGIN);
      dest.search = url.search;
      return Response.redirect(dest.toString(), 301);
    }

    // --- Old guide category redirects (category restructuring) ---
    const oldCatMatch = pathname.match(/^\/guides\/([a-z][a-z0-9-]+)\/?$/);
    if (oldCatMatch && oldCatMatch[1] in OLD_CATEGORY_REDIRECTS) {
      const dest = new URL(OLD_CATEGORY_REDIRECTS[oldCatMatch[1]], SITE_ORIGIN);
      return Response.redirect(dest.toString(), 301);
    }

    // --- Guide category-prefix URLs (email CTAs: /guides/{category}/{slug} -> /guides/{slug}) ---
    const catPrefixMatch = pathname.match(/^\/guides\/([a-z][a-z0-9-]+)\/([a-z][a-z0-9-]+)\/?$/);
    if (catPrefixMatch && catPrefixMatch[1] in GUIDE_CATEGORIES) {
      const dest = new URL(`/guides/${catPrefixMatch[2]}`, SITE_ORIGIN);
      dest.search = url.search;
      return Response.redirect(dest.toString(), 301);
    }

    // /platform was saverwellholdings.com-only — permanently gone from consumer site
    if (pathname === "/platform") {
      return new Response(
        "<!DOCTYPE html><html><head><title>410 Gone</title></head><body><h1>410 Gone</h1><p>This page has been permanently removed.</p></body></html>",
        {
          status: 410,
          headers: { "Content-Type": "text/html; charset=utf-8" },
        }
      );
    }

    // --- Widget routes (before SEO routing) ---
    if (pathname.startsWith("/widget/v1/")) {
      // CORS preflight
      if (request.method === "OPTIONS") {
        return new Response(null, { status: 204, headers: CORS_HEADERS });
      }

      // GET /widget/v1/embed.js
      if (pathname === "/widget/v1/embed.js" && request.method === "GET") {
        return handleWidgetEmbed();
      }

      // GET /widget/v1/api/discounts
      if (pathname === "/widget/v1/api/discounts" && request.method === "GET") {
        return handleWidgetDiscounts(url, env);
      }

      // POST /widget/v1/api/subscribe
      if (pathname === "/widget/v1/api/subscribe" && request.method === "POST") {
        return handleWidgetSubscribe(request, env);
      }

      // GET /widget/v1/chat.js — chat widget bundle
      if (pathname === "/widget/v1/chat.js" && request.method === "GET") {
        return handleChatWidgetJs();
      }

      // POST /widget/v1/api/chat — chat streaming endpoint
      if (pathname === "/widget/v1/api/chat" && request.method === "POST") {
        return handleChat(request, env);
      }

      return corsJson({ error: "Not found" }, 404);
    }

    // --- GA4 DataLayer script (overrides stale Lovable-hosted version) ---
    if (pathname === "/scripts/sw-datalayer.js" && request.method === "GET") {
      const dlJs = SW_DATALAYER_JS.replace(
        "__WEB_READ_WEBHOOK_URL__",
        env.WEB_READ_WEBHOOK_URL || ""
      );
      return new Response(dlJs, {
        status: 200,
        headers: {
          "Content-Type": "application/javascript; charset=utf-8",
          "Cache-Control": "public, max-age=3600, s-maxage=3600",
          "Access-Control-Allow-Origin": "*",
        },
      });
    }

    // --- Sitemap proxy (supports sub-sitemaps) ---
    const sitemapMatch = pathname.match(/^\/sitemap(?:-([a-z]+))?\.xml$/);
    if (sitemapMatch) {
      const sitemapType = sitemapMatch[1]; // undefined for /sitemap.xml, "dma" for /sitemap-dma.xml, etc.
      const sitemapUrl = new URL(`${env.SUPABASE_URL}/functions/v1/sitemap`);
      if (sitemapType) {
        sitemapUrl.searchParams.set("type", sitemapType);
      } else {
        // /sitemap.xml now returns the sitemap index
        sitemapUrl.searchParams.set("type", "index");
      }
      const resp = await fetch(sitemapUrl.toString());
      return new Response(resp.body, {
        status: resp.status,
        headers: {
          "Content-Type": "application/xml; charset=utf-8",
          "Cache-Control": "public, max-age=3600, s-maxage=3600",
        },
      });
    }

    // --- Listing page pre-rendering (for bots only) ---
    const listingMatch = matchListingPage(pathname);
    if (listingMatch) {
      const userAgent = request.headers.get("user-agent") || "";
      if (!isBot(userAgent)) {
        return fetchWithAnalytics(request);
      }
      const listingResponse = await fetchListingPage(env, listingMatch);
      if (listingResponse) return listingResponse;
      // Bot got no data — return 404 instead of falling through to SPA shell (soft 404)
      return new Response("Not Found", {
        status: 404,
        headers: { "X-Robots-Tag": "noindex" },
      });
    }

    // --- SEO dynamic rendering ---
    const route = matchRoute(pathname);
    if (!route) {
      return fetchWithAnalytics(request);
    }

    const userAgent = request.headers.get("user-agent") || "";

    // Gated content interstitial for guide pages (non-bot visitors only)
    if (route.type === "guides" && !isBot(userAgent) && isGatedVisit(request, route)) {
      const originResponse = await fetch(request);
      const contentType = originResponse.headers.get("content-type") || "";
      if (contentType.includes("text/html")) {
        let originHtml = await originResponse.text();
        originHtml = injectAnalytics(originHtml);
        const overlay = buildGateOverlay(route.slug);
        originHtml = originHtml.replace("</body>", overlay + "\n</body>");
        const newHeaders = new Headers(originResponse.headers);
        newHeaders.set("Cache-Control", "no-store");
        return new Response(originHtml, {
          status: originResponse.status,
          headers: newHeaders,
        });
      }
      return originResponse;
    }

    if (!isBot(userAgent)) {
      return fetchWithAnalytics(request);
    }

    const pageData = await fetchPageData(env, route);
    if (!pageData) {
      // Bot got no data — return 404 instead of falling through to SPA shell (soft 404)
      return new Response("Not Found", {
        status: 404,
        headers: { "X-Robots-Tag": "noindex" },
      });
    }

    const html = renderFullHtml(pageData);

    return new Response(html, {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "public, max-age=3600, s-maxage=86400",
        "X-Robots-Tag": "index, follow",
        "X-Rendered-By": "saverwell-seo-renderer",
      },
    });
  },
};
