/// <reference types="jsr:@supabase/functions-js/edge-runtime.d.ts" />

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers":
    "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

function pickClientIp(req: Request): string | null {
  const xf = req.headers.get("x-forwarded-for");
  if (xf && xf.trim()) return xf.split(",")[0].trim();
  const cf = req.headers.get("cf-connecting-ip");
  if (cf && cf.trim()) return cf.trim();
  const xr = req.headers.get("x-real-ip");
  if (xr && xr.trim()) return xr.trim();
  return null;
}

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 204, headers: corsHeaders });
  }

  if (req.method !== "POST") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405,
      headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }

  try {
    const body = await req.json().catch(() => ({}));
    if (!body || typeof body !== "object") {
      return new Response(JSON.stringify({ error: "Invalid JSON body" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    const { email, source, metadata, timestamp: _clientTimestamp, ...rest } =
      body as Record<string, unknown>;

    if (!email || typeof email !== "string") {
      return new Response(JSON.stringify({ error: "Email is required" }), {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // Build the payload (same structure the n8n workflow expects)
    const payload: Record<string, unknown> = {
      email,
      source: typeof source === "string" && source.trim() ? source : "site",
      metadata: metadata && typeof metadata === "object" ? metadata : {},
      timestamp: new Date().toISOString(),
      ip_address: pickClientIp(req),
      ...rest,
    };

    // INSERT into subscribe_queue for async processing by n8n.
    // Edge functions have SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    // available automatically.
    const supabaseUrl = Deno.env.get("SUPABASE_URL");
    const serviceRoleKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");

    if (!supabaseUrl || !serviceRoleKey) {
      return new Response(
        JSON.stringify({ error: "Supabase credentials missing" }),
        {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    const insertResp = await fetch(
      `${supabaseUrl}/rest/v1/subscribe_queue`,
      {
        method: "POST",
        headers: {
          apikey: serviceRoleKey,
          Authorization: `Bearer ${serviceRoleKey}`,
          "Content-Type": "application/json",
          Prefer: "return=minimal",
        },
        body: JSON.stringify({ payload }),
      }
    );

    if (!insertResp.ok) {
      const errText = await insertResp.text();
      return new Response(
        JSON.stringify({
          error: "Queue insert failed",
          status: insertResp.status,
          body: errText.slice(0, 500),
        }),
        {
          status: 502,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        }
      );
    }

    return new Response(
      JSON.stringify({ ok: true, success: true }),
      {
        status: 200,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  } catch (e) {
    return new Response(
      JSON.stringify({ error: "Invalid request", detail: String(e) }),
      {
        status: 400,
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      }
    );
  }
});
