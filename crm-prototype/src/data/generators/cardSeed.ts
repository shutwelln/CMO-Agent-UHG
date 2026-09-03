import { nanoid } from "nanoid";
import type {
  CardStage,
  Campaign,
  Dataset,
  FunnelEvent,
  FunnelEventType,
  Provider,
  Segment,
  SegmentRules,
} from "../schema";
import { countMatches } from "../../lib/segmentEngine";
import { CARD_TEMPLATES, journeyToSteps } from "../../lib/cardJourneys";

/*
 * Seeds the Provider Card + LOC lifecycle in-app, so the shipped dataset.json
 * stays back-compatible (mirrors how broadcasts are seeded). Deterministic:
 * assignment is a stable hash of the provider id, so the demo is stable across
 * reloads. Assigns card fields + loc/provider_card ownership to a realistic
 * subset, pushes a card funnel-event chain per card stage, and adds card
 * segments and card campaigns.
 */

const NOW = new Date("2026-08-22T12:00:00Z").getTime();
const DAY = 86_400_000;
const iso = (daysBack: number) => new Date(NOW - daysBack * DAY).toISOString();

function hashId(id: string, salt = ""): number {
  let h = 0;
  const s = id + salt;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

const CARD_PERSONAS = new Set([
  "PE-backed Group",
  "Multi-Specialty Group",
  "Growing Group",
  "High Volume Specialty",
  "Digital-First",
]);

const LIMITS = [15000, 25000, 50000, 75000, 100000, 150000, 250000];

// Day offsets (before NOW) for each event in a card lifecycle chain.
const EVENT_DAYS: Record<FunnelEventType, number> = {
  signup_started: 0,
  stuck_mid_funnel: 0,
  completed_signup: 0,
  account_funded: 0,
  loan_originated: 0,
  card_offer_viewed: 46,
  card_applied: 38,
  card_approved: 30,
  card_activated: 22,
  card_first_spend: 12,
  card_recurring_spend: 3,
  card_dormant: 5,
};

// Ordered event chain per stage.
const STAGE_EVENTS: Record<CardStage, FunnelEventType[]> = {
  none: [],
  eligible: ["card_offer_viewed"],
  applied: ["card_offer_viewed", "card_applied"],
  approved: ["card_offer_viewed", "card_applied", "card_approved"],
  activated: ["card_offer_viewed", "card_applied", "card_approved", "card_activated"],
  spending: [
    "card_offer_viewed",
    "card_applied",
    "card_approved",
    "card_activated",
    "card_first_spend",
    "card_recurring_spend",
  ],
  dormant: [
    "card_offer_viewed",
    "card_applied",
    "card_approved",
    "card_activated",
    "card_first_spend",
    "card_dormant",
  ],
};

function eligibleForCard(p: Provider): boolean {
  return (
    CARD_PERSONAS.has(p.persona) ||
    p.monthlyOptumPayVolume >= 100_000 ||
    p.productsHeld.includes("term_loan") ||
    p.productsHeld.includes("pwc")
  );
}

function cardStageFor(bucket: number): CardStage {
  if (bucket < 15) return "none"; // LOC holder without a card (cross-sell target)
  if (bucket < 28) return "eligible";
  if (bucket < 39) return "applied";
  if (bucket < 52) return "approved";
  if (bucket < 64) return "activated";
  if (bucket < 91) return "spending";
  return "dormant";
}

/* Mutates providers with card fields + ownership; returns the new funnel events. */
function assignCards(data: Dataset): FunnelEvent[] {
  const events: FunnelEvent[] = [];
  for (const p of data.providers) {
    if (!eligibleForCard(p)) {
      p.cardStage = "none";
      continue;
    }
    const hA = hashId(p.id);
    const hB = hashId(p.id, "card");
    const hasLoc = hA % 100 < 60;
    if (!hasLoc) {
      p.cardStage = "none";
      continue;
    }
    if (!p.productsHeld.includes("loc")) p.productsHeld.push("loc");

    const stage = cardStageFor(hB % 100);
    p.cardStage = stage;
    const limit = LIMITS[hB % LIMITS.length];

    if (stage === "none") continue; // LOC holder, no card yet

    if (!p.productsHeld.includes("provider_card")) p.productsHeld.push("provider_card");
    p.cardLimit = limit;

    if (stage === "spending") {
      const util = 20 + (hA % 71); // 20-90
      p.cardUtilization = util;
      p.monthlyCardSpend = Math.round((limit * util) / 100 / 100) * 100;
    } else if (stage === "dormant") {
      const util = hA % 4; // 0-3
      p.cardUtilization = util;
      p.monthlyCardSpend = Math.round((limit * util) / 100);
    } else {
      p.cardUtilization = 0;
      p.monthlyCardSpend = 0;
    }

    for (const et of STAGE_EVENTS[stage]) {
      events.push({
        id: `fe_card_${nanoid(8)}`,
        providerId: p.id,
        eventType: et,
        surface: "card",
        stuckStep: null,
        occurredAt: iso(EVENT_DAYS[et]),
      });
    }
  }
  return events;
}

function seg(id: string, name: string, funnelStage: string, rules: SegmentRules, data: Dataset): Segment {
  return { id, name, funnelStage, filters: {}, size: countMatches(data, rules), rules };
}

function cardSegments(data: Dataset): Segment[] {
  return [
    seg("seg_card_approved", "Card approved, not activated", "Activation", {
      match: "all",
      conditions: [{ kind: "attribute", field: "cardStage", op: "is", value: "approved" }],
    }, data),
    seg("seg_card_emob", "Activated, no first spend (EMOB)", "Onboarding", {
      match: "all",
      conditions: [{ kind: "attribute", field: "cardStage", op: "is", value: "activated" }],
    }, data),
    seg("seg_card_lowutil", "Spending, low utilization", "Growth", {
      match: "all",
      conditions: [
        { kind: "attribute", field: "cardStage", op: "is", value: "spending" },
        { kind: "attribute", field: "cardUtilization", op: "lte", value: 30 },
      ],
    }, data),
    seg("seg_card_dormant", "Dormant cardholders", "Growth", {
      match: "all",
      conditions: [{ kind: "attribute", field: "cardStage", op: "is", value: "dormant" }],
    }, data),
    seg("seg_card_loc_nocard", "LOC holders without a card", "Acquisition", {
      match: "all",
      conditions: [
        { kind: "product", has: true, product: "loc" },
        { kind: "attribute", field: "cardStage", op: "is", value: "none" },
      ],
    }, data),
  ];
}

function cardCampaigns(data: Dataset, segments: Segment[]): Campaign[] {
  const bySegName = (n: string) => segments.find((s) => s.name === n);
  const eventCount = (et: FunnelEventType) =>
    new Set(data.funnelEvents.filter((e) => e.eventType === et).map((e) => e.providerId)).size;

  const rows: {
    key: string;
    name: string;
    status: Campaign["status"];
    segmentName: string;
    audienceSize: number;
    launchedAt: string | null;
    metricsFactor: number;
  }[] = [
    {
      key: "onboarding_activation",
      name: "Provider Card activation - EMOB",
      status: "active",
      segmentName: "Card approved, not activated",
      audienceSize: bySegName("Card approved, not activated")?.size ?? eventCount("card_approved"),
      launchedAt: iso(20),
      metricsFactor: 1,
    },
    {
      key: "first_spend",
      name: "Provider Card first-spend incentive",
      status: "active",
      segmentName: "Activated, no first spend (EMOB)",
      audienceSize: bySegName("Activated, no first spend (EMOB)")?.size ?? eventCount("card_activated"),
      launchedAt: iso(12),
      metricsFactor: 0.8,
    },
    {
      key: "acquisition",
      name: "Provider Card cross-sell to LOC holders",
      status: "active",
      segmentName: "LOC holders without a card",
      audienceSize: bySegName("LOC holders without a card")?.size ?? 0,
      launchedAt: iso(28),
      metricsFactor: 1.2,
    },
  ];

  return rows.map((r) => {
    const tpl = CARD_TEMPLATES.find((t) => t.key === r.key)!;
    const journey = tpl.build();
    const sent = Math.round(r.audienceSize * r.metricsFactor);
    const delivered = Math.round(sent * 0.98);
    return {
      id: `camp_card_${r.key}`,
      name: r.name,
      status: r.status,
      segmentName: r.segmentName,
      connector: "SendGrid",
      journeySteps: journeyToSteps(journey),
      audienceSize: r.audienceSize,
      metrics: {
        sent,
        delivered,
        opens: Math.round(delivered * 0.44),
        clicks: Math.round(delivered * 0.11),
        conversions: Math.round(delivered * 0.06),
      },
      createdByRole: "Campaign Management",
      launchedAt: r.launchedAt,
      trigger:
        tpl.trigger.type === "segment"
          ? { type: "segment", segmentId: bySegName(r.segmentName)?.id }
          : tpl.trigger,
      journey,
    };
  });
}

export function seedCardLifecycle(data: Dataset): void {
  // Assign card ownership + fields (mutates providers) and collect card events.
  const cardEvents = assignCards(data);
  data.funnelEvents = [...data.funnelEvents, ...cardEvents];
  // Segments computed against the now-augmented providers.
  const segments = cardSegments(data);
  data.segments = [...segments, ...data.segments];
  // Card campaigns.
  data.campaigns = [...cardCampaigns(data, segments), ...data.campaigns];
}

/* True if the dataset has not yet had card data seeded. */
export function needsCardSeed(data: Dataset): boolean {
  return !data.providers.some((p) => p.cardStage !== undefined);
}
