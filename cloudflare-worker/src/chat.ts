/**
 * Saverwell Chat Widget - Backend Handler
 *
 * Handles: intent classification, RAG queries via Supabase full-text search,
 * Anthropic Haiku streaming, SSE encoding, rate limiting.
 */

import type { Env } from "./index";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface ChatRequest {
  message: string;
  page_context: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
  turn_number: number;
}

type Intent =
  | "scam_triage"
  | "discount_lookup"
  | "content_qa"
  | "email_capture"
  | "off_topic";

interface ArticleResult {
  slug: string;
  title: string;
  url: string;
  content: string;
  monetization_type?: string;
}

// ---------------------------------------------------------------------------
// Rate limiter (in-memory, per-isolate — resets on deploy)
// ---------------------------------------------------------------------------
const rateLimitMap = new Map<string, number[]>();
const RATE_LIMIT_WINDOW_MS = 60_000;
const RATE_LIMIT_MAX = 10;

function checkRateLimit(ip: string): boolean {
  const now = Date.now();
  const timestamps = rateLimitMap.get(ip) || [];
  const recent = timestamps.filter((t) => now - t < RATE_LIMIT_WINDOW_MS);
  if (recent.length >= RATE_LIMIT_MAX) {
    rateLimitMap.set(ip, recent);
    return false;
  }
  recent.push(now);
  rateLimitMap.set(ip, recent);
  return true;
}

// ---------------------------------------------------------------------------
// Intent classification (keyword rules first, no LLM needed for common cases)
// ---------------------------------------------------------------------------
const SCAM_KEYWORDS = [
  "scam",
  "scammed",
  "suspicious call",
  "gave them my",
  "they said i owe",
  "fraud",
  "identity theft",
  "someone called",
  "phishing",
  "hacked",
  "stolen",
  "data breach",
  "suspicious email",
  "bank impostor",
  "they asked for my",
  "gave my information",
  "gave my number",
  "gave my social",
  "impersonat",
];

const DISCOUNT_KEYWORDS = [
  "discount",
  "deals",
  "near me",
  "coupon",
  "save money",
  "savings near",
  "local deals",
  "store discount",
  "senior discount",
];

const EMAIL_KEYWORDS = [
  "send me",
  "email me",
  "email the",
  "sign me up",
  "subscribe",
  "weekly digest",
  "send it to",
];

function classifyIntent(message: string): Intent {
  const lower = message.toLowerCase();

  for (const kw of EMAIL_KEYWORDS) {
    if (lower.includes(kw)) return "email_capture";
  }
  for (const kw of SCAM_KEYWORDS) {
    if (lower.includes(kw)) return "scam_triage";
  }
  for (const kw of DISCOUNT_KEYWORDS) {
    if (lower.includes(kw)) return "discount_lookup";
  }

  return "content_qa";
}

// ---------------------------------------------------------------------------
// Supabase REST query helper (mirrors index.ts supabaseQuery)
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
  return resp.json() as Promise<any[]>;
}

// ---------------------------------------------------------------------------
// RAG: Two-phase keyword search (fetch indexes → match → fetch content)
// ---------------------------------------------------------------------------

// Stop words to skip in keyword extraction
const STOP_WORDS = new Set([
  "a","an","the","is","are","was","were","be","been","being","have","has","had",
  "do","does","did","will","would","shall","should","may","might","must","can",
  "could","i","me","my","we","our","you","your","he","she","it","they","them",
  "this","that","these","those","what","which","who","whom","how","when","where",
  "why","am","or","and","but","if","in","on","at","to","for","of","with","by",
  "from","about","into","not","no","so","than","too","very","just","also",
]);

function extractKeywords(query: string): string[] {
  return query
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, "")
    .split(/\s+/)
    .filter((w) => w.length > 2 && !STOP_WORDS.has(w))
    .slice(0, 6);
}

// In-memory article index cache (refreshes per isolate lifecycle, ~minutes)
interface ArticleIndex {
  slug: string;
  title: string;
  type: "guide" | "protection";
}
let articleIndexCache: ArticleIndex[] | null = null;
let articleIndexExpiry = 0;
const INDEX_TTL_MS = 5 * 60 * 1000; // 5 minutes

async function getArticleIndex(env: Env): Promise<ArticleIndex[]> {
  const now = Date.now();
  if (articleIndexCache && now < articleIndexExpiry) {

    return articleIndexCache;
  }


  const [guides, protection] = await Promise.all([
    supabaseQuery(env, "guide_articles", {
      select: "slug,title",
      publish_web: "eq.true",
      limit: "200",
    }),
    supabaseQuery(env, "protection_articles", {
      select: "slug,title",
      limit: "100",
    }),
  ]);



  const index: ArticleIndex[] = [];
  if (guides) {
    for (const g of guides) {
      index.push({ slug: g.slug, title: g.title, type: "guide" });
    }
  }
  if (protection) {
    for (const p of protection) {
      index.push({ slug: p.slug, title: p.title, type: "protection" });
    }
  }


  articleIndexCache = index;
  articleIndexExpiry = now + INDEX_TTL_MS;
  return index;
}

// Score and rank articles by keyword match count
function rankArticles(
  index: ArticleIndex[],
  keywords: string[],
  preferType: "guide" | "protection" | null
): ArticleIndex[] {
  const scored = index
    .map((article) => {
      const text = `${article.title} ${article.slug}`.toLowerCase();
      let score = 0;
      for (const kw of keywords) {
        if (text.includes(kw)) score++;
      }
      // Boost preferred type
      if (preferType && article.type === preferType) score += 0.5;
      return { article, score };
    })
    .filter((s) => s.score > 0);

  scored.sort((a, b) => b.score - a.score);
  return scored.slice(0, 3).map((s) => s.article);
}

// Fetch full content for specific article slugs
async function fetchGuideContent(
  env: Env,
  slug: string
): Promise<ArticleResult | null> {
  const rows = await supabaseQuery(env, "guide_articles", {
    select:
      "slug,title,overview_md,key_takeaways_md,savings_tips_md,watch_out_md,faq_md,monetization_type",
    slug: `eq.${slug}`,
    limit: "1",
  });
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  return {
    slug: r.slug,
    title: r.title,
    url: `/guides/${r.slug}`,
    content: buildGuideContext(r),
    monetization_type: r.monetization_type || null,
  };
}

async function fetchProtectionContent(
  env: Env,
  slug: string
): Promise<ArticleResult | null> {
  const rows = await supabaseQuery(env, "protection_articles", {
    select:
      "slug,title,overview_md,red_flags_md,what_to_do_md,phone_script_md,prevention_md",
    slug: `eq.${slug}`,
    limit: "1",
  });
  if (!rows || rows.length === 0) return null;
  const r = rows[0];
  return {
    slug: r.slug,
    title: r.title,
    url: `/protect/${r.slug}`,
    content: buildProtectionContext(r),
  };
}

async function searchArticles(
  env: Env,
  query: string,
  intent: Intent
): Promise<ArticleResult[]> {
  const keywords = extractKeywords(query);

  if (keywords.length === 0) return [];

  // Phase 1: Match against cached index
  const index = await getArticleIndex(env);
  const preferType = intent === "scam_triage" ? "protection" : "guide";
  const matches = rankArticles(index, keywords, preferType);


  if (matches.length === 0) return [];

  // Phase 2: Fetch full content for top matches (parallel)
  const results = await Promise.all(
    matches.map((m) =>
      m.type === "guide"
        ? fetchGuideContent(env, m.slug)
        : fetchProtectionContent(env, m.slug)
    )
  );

  const filtered = results.filter((r): r is ArticleResult => r !== null);
  return filtered;
}

function buildGuideContext(row: any): string {
  const parts: string[] = [];
  if (row.overview_md) parts.push(`Overview: ${row.overview_md}`);
  if (row.key_takeaways_md)
    parts.push(`Key Takeaways: ${row.key_takeaways_md}`);
  if (row.savings_tips_md)
    parts.push(`Savings Tips: ${row.savings_tips_md}`);
  if (row.watch_out_md) parts.push(`Watch Out: ${row.watch_out_md}`);
  if (row.faq_md) parts.push(`FAQ: ${row.faq_md}`);
  // Truncate to keep token count reasonable
  return parts.join("\n\n").slice(0, 3000);
}

function buildProtectionContext(row: any): string {
  const parts: string[] = [];
  if (row.overview_md) parts.push(`Overview: ${row.overview_md}`);
  if (row.red_flags_md) parts.push(`Red Flags: ${row.red_flags_md}`);
  if (row.what_to_do_md)
    parts.push(`What To Do: ${row.what_to_do_md}`);
  if (row.phone_script_md)
    parts.push(`Phone Script: ${row.phone_script_md}`);
  if (row.prevention_md)
    parts.push(`Prevention: ${row.prevention_md}`);
  return parts.join("\n\n").slice(0, 3000);
}

// ---------------------------------------------------------------------------
// Discount lookup via existing DMA/merchant data
// ---------------------------------------------------------------------------
async function lookupDiscounts(
  env: Env,
  zip: string
): Promise<{ merchants: any[]; dma: any } | null> {
  // Find DMA by ZIP
  const dmaRows = await supabaseQuery(env, "dma_zip_codes", {
    select: "dma_code",
    zip_code: `eq.${zip}`,
    limit: "1",
  });

  if (!dmaRows || dmaRows.length === 0) return null;

  const dmaCode = dmaRows[0].dma_code;

  // Get DMA info
  const dmaInfo = await supabaseQuery(env, "dma_page_content", {
    select: "display_name,slug,merchant_count",
    dma_code: `eq.${dmaCode}`,
    status: "eq.published",
    limit: "1",
  });

  // Get merchants
  const merchants = await supabaseQuery(env, "v_merchant_pages", {
    select: "name,page_slug,default_discount_text,default_discount_value",
    order: "name.asc",
    limit: "5",
  });

  return {
    merchants: merchants || [],
    dma: dmaInfo && dmaInfo[0] ? dmaInfo[0] : null,
  };
}

// ---------------------------------------------------------------------------
// System prompt builder
// ---------------------------------------------------------------------------
const SYSTEM_PROMPT_BASE = `You are the Saverwell help assistant on saverwell.com. You help seniors find savings and stay protected from financial threats.

RULES:
1. Answer ONLY from the article content provided below. If no articles match the question, say: "I don't have a specific article on that, but you might find what you're looking for in our [Guides](/guides) or [Protection Tips](/protect) sections."
2. Keep responses under 150 words unless the user asks for more detail.
3. Always include links to source articles as markdown: [Title](/guides/slug) or [Title](/protect/slug)
4. End each response with 1-2 follow-up question suggestions formatted as: **You might also want to know:** followed by the suggestions.
5. Never recommend specific financial products, insurance plans, or investment decisions. Use educational framing: "factors to consider," "options available," "types to compare."
6. Never use "elderly," "old folks," or patronizing language. Use "seniors" or "retirees."
7. When someone describes a potential scam: take it seriously, do not minimize, lead with reassurance, then provide actionable steps.
8. Never echo back personal information (phone numbers, SSNs, email addresses, card numbers) that the user shares.
9. If the user shares PII, acknowledge you received it but do NOT repeat it. Redirect to the relevant help steps.
10. Tone: warm, confident, empowering. Like a knowledgeable friend. Short sentences. No jargon. No em dashes.`;

function buildSystemPrompt(
  pageContext: string,
  articles: ArticleResult[],
  intent: Intent
): string {
  let prompt = SYSTEM_PROMPT_BASE;
  prompt += `\n\nCURRENT PAGE: ${pageContext}`;

  if (articles.length > 0) {
    prompt += "\n\nARTICLE CONTENT FOR REFERENCE:";
    for (const article of articles) {
      prompt += `\n\n--- ${article.title} (${article.url}) ---\n${article.content}`;
    }
  }

  if (intent === "scam_triage") {
    prompt +=
      "\n\nSCAM TRIAGE MODE: The user may be experiencing or have experienced a scam. Follow this structure:\n1. Reassurance: \"You're doing the right thing by checking.\"\n2. Classification: Ask what happened (call, email, or online) if not clear.\n3. Provide the specific action steps from the matched protection article's What To Do section.\n4. If available, share the phone script (\"Here's exactly what to say when you call your bank\").\n5. Offer: \"I can share these steps if you'd like to save them. Just let me know your email.\"";
  }

  if (intent === "discount_lookup") {
    prompt +=
      "\n\nDISCOUNT MODE: The user is looking for local discounts. If they haven't provided a ZIP code, ask for it. If discount results are provided below, summarize the top deals and link to the full DMA page.";
  }

  return prompt;
}

// ---------------------------------------------------------------------------
// Build conversation messages for Anthropic API
// ---------------------------------------------------------------------------
function buildMessages(
  history: ChatRequest["history"],
  message: string,
  turnNumber: number
): Array<{ role: "user" | "assistant"; content: string }> {
  // Keep last 4 turns (8 messages) for context
  const recentHistory = history.slice(-8);

  const messages = [
    ...recentHistory,
    { role: "user" as const, content: message },
  ];

  // Turn limit nudges
  if (turnNumber >= 6 && turnNumber < 8) {
    // Append instruction to suggest full article
    const lastMsg = messages[messages.length - 1];
    if (lastMsg.role === "user") {
      messages[messages.length - 1] = {
        ...lastMsg,
        content:
          lastMsg.content +
          "\n\n[System: This is turn " +
          turnNumber +
          ". In your response, suggest the user read the full article for more detail.]",
      };
    }
  }

  return messages;
}

// ---------------------------------------------------------------------------
// SSE helpers
// ---------------------------------------------------------------------------
function sseEvent(type: string, data: unknown): string {
  return `data: ${JSON.stringify({ type, ...( typeof data === 'object' && data !== null ? data : { text: data }) })}\n\n`;
}

// ---------------------------------------------------------------------------
// Streaming response via Anthropic Messages API (direct fetch, no SDK)
// ---------------------------------------------------------------------------
async function streamAnthropicResponse(
  env: Env,
  systemPrompt: string,
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  articles: ArticleResult[],
  intent: Intent,
  controller: ReadableStreamDefaultController
): Promise<void> {
  const encoder = new TextEncoder();

  try {
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": env.ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-haiku-4-5-20251001",
        max_tokens: 1024,
        system: systemPrompt,
        messages,
        stream: true,
      }),
    });

    if (!resp.ok) {
      const errText = await resp.text();
      console.error("Anthropic API error:", resp.status, errText);
      controller.enqueue(
        encoder.encode(
          sseEvent("error", {
            text: "I'm having trouble right now. In the meantime, try our [search](/search) or browse [Guides](/guides).",
          })
        )
      );
      controller.enqueue(encoder.encode(sseEvent("done", {})));
      controller.close();
      return;
    }

    const reader = resp.body?.getReader();
    if (!reader) {
      controller.enqueue(
        encoder.encode(sseEvent("error", { text: "Stream unavailable." }))
      );
      controller.enqueue(encoder.encode(sseEvent("done", {})));
      controller.close();
      return;
    }

    const decoder = new TextDecoder();
    let buffer = "";
    let fullResponse = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") continue;

        try {
          const event = JSON.parse(data);

          if (
            event.type === "content_block_delta" &&
            event.delta?.type === "text_delta"
          ) {
            const text = event.delta.text;
            fullResponse += text;
            controller.enqueue(
              encoder.encode(sseEvent("token", { text }))
            );
          }
        } catch {
          // Skip unparseable lines
        }
      }
    }

    // Send source articles
    if (articles.length > 0) {
      const sources = articles.map((a) => {
        let url = a.url;
        if (a.monetization_type === "affiliate") {
          url += `?utm_source=saverwell&utm_medium=chat&utm_content=${a.slug}`;
        }
        return { slug: a.slug, title: a.title, url };
      });
      controller.enqueue(
        encoder.encode(sseEvent("sources", { articles: sources }))
      );
    }

    // Generate follow-up suggestions based on intent and content
    const suggestions = generateSuggestions(intent, articles);
    if (suggestions.length > 0) {
      controller.enqueue(
        encoder.encode(
          sseEvent("suggestions", { questions: suggestions })
        )
      );
    }

    // Check if email capture should be suggested
    if (
      intent === "scam_triage" ||
      (intent === "content_qa" && articles.length > 0)
    ) {
      const trigger =
        intent === "scam_triage" ? "scam_triage" : "value_moment";
      controller.enqueue(
        encoder.encode(
          sseEvent("email_prompt", { trigger })
        )
      );
    }

    controller.enqueue(encoder.encode(sseEvent("done", {})));
    controller.close();
  } catch (err) {
    console.error("Stream error:", err);
    controller.enqueue(
      encoder.encode(
        sseEvent("error", {
          text: "I'm having trouble right now. In the meantime, try our [search](/search) or browse [Guides](/guides).",
        })
      )
    );
    controller.enqueue(encoder.encode(sseEvent("done", {})));
    controller.close();
  }
}

// ---------------------------------------------------------------------------
// Follow-up suggestion generator
// ---------------------------------------------------------------------------
function generateSuggestions(
  intent: Intent,
  articles: ArticleResult[]
): string[] {
  if (intent === "scam_triage") {
    return [
      "What should I do right now?",
      "How can I protect myself going forward?",
    ];
  }
  if (intent === "discount_lookup") {
    return [
      "Which stores have the biggest discounts?",
      "Are there any restaurant deals?",
    ];
  }

  // Content QA: suggest related topics based on returned articles
  const suggestions: string[] = [];
  for (const article of articles.slice(0, 2)) {
    if (article.url.includes("medicare")) {
      suggestions.push("How can I save on Medicare premiums?");
    } else if (article.url.includes("insurance")) {
      suggestions.push("What insurance options should I compare?");
    } else if (article.url.includes("social-security")) {
      suggestions.push("When should I claim Social Security?");
    } else if (article.url.includes("protect")) {
      suggestions.push("What are the warning signs of a scam?");
    }
  }

  if (suggestions.length === 0) {
    suggestions.push(
      "What topics does Saverwell cover?",
      "Find discounts near me"
    );
  }

  return suggestions.slice(0, 2);
}

// ---------------------------------------------------------------------------
// Input sanitization
// ---------------------------------------------------------------------------
function sanitizeInput(input: string): string {
  // Strip HTML/markdown, limit length
  return input
    .replace(/<[^>]*>/g, "")
    .replace(/[[\](){}*_~`#>|]/g, "")
    .trim()
    .slice(0, 500);
}

// ---------------------------------------------------------------------------
// Main handler
// ---------------------------------------------------------------------------
export async function handleChat(
  request: Request,
  env: Env
): Promise<Response> {
  const CORS: HeadersInit = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
  };

  // Rate limit check
  const clientIp =
    request.headers.get("cf-connecting-ip") ||
    request.headers.get("x-forwarded-for") ||
    "unknown";
  if (!checkRateLimit(clientIp)) {
    return new Response(
      JSON.stringify({
        error:
          "You're asking great questions! Give me a moment to catch up. Try again in about a minute.",
      }),
      { status: 429, headers: { ...CORS, "Content-Type": "application/json" } }
    );
  }

  // Parse request
  let body: ChatRequest;
  try {
    body = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
      status: 400,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  const message = sanitizeInput(body.message || "");
  const pageContext = (body.page_context || "/").slice(0, 200);
  const history = Array.isArray(body.history) ? body.history.slice(-8) : [];
  const turnNumber = typeof body.turn_number === "number" ? body.turn_number : 1;

  if (!message) {
    return new Response(JSON.stringify({ error: "Message is required" }), {
      status: 400,
      headers: { ...CORS, "Content-Type": "application/json" },
    });
  }

  // Turn limit
  if (turnNumber > 8) {
    return new Response(
      JSON.stringify({
        type: "turn_limit",
        text: "I've shared what I can. For the full picture, browse our [Guides](/guides) or [Protection Tips](/protect). You can start a new conversation anytime!",
      }),
      { status: 200, headers: { ...CORS, "Content-Type": "application/json" } }
    );
  }

  // Classify intent
  const intent = classifyIntent(message);

  // Search for relevant articles
  const articles = await searchArticles(env, message, intent);

  // No results fallback (no LLM call needed)
  if (articles.length === 0 && intent === "content_qa") {
    const noResultStream = new ReadableStream({
      start(controller) {
        const encoder = new TextEncoder();
        controller.enqueue(
          encoder.encode(
            sseEvent("token", {
              text: "I don't have a specific article on that, but you might find what you're looking for in our [Guides](/guides) or [Protection Tips](/protect) sections.",
            })
          )
        );
        controller.enqueue(
          encoder.encode(
            sseEvent("suggestions", {
              questions: [
                "I need help with Medicare",
                "I think I'm being scammed",
                "Find discounts near me",
              ],
            })
          )
        );
        controller.enqueue(encoder.encode(sseEvent("done", {})));
        controller.close();
      },
    });

    return new Response(noResultStream, {
      status: 200,
      headers: {
        ...CORS,
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      },
    });
  }

  // Build system prompt and messages
  const systemPrompt = buildSystemPrompt(pageContext, articles, intent);
  const messages = buildMessages(history, message, turnNumber);

  // Stream response via SSE
  const stream = new ReadableStream({
    async start(controller) {
      await streamAnthropicResponse(
        env,
        systemPrompt,
        messages,
        articles,
        intent,
        controller
      );
    },
  });

  return new Response(stream, {
    status: 200,
    headers: {
      ...CORS,
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  });
}
