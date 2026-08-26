import type {
  Dataset,
  Provider,
  SegmentCondition,
  SegmentRules,
  FunnelEvent,
} from "../data/schema";
import { PERSONAS, PRODUCTS, FUNNEL_EVENTS, PRODUCT_LABEL, FUNNEL_EVENT_LABEL } from "../data/schema";

const NOW = new Date("2026-08-22T12:00:00Z").getTime();
const DAY = 86_400_000;

/* Attribute fields exposed in the segment builder (provider-level, from the
 * "data warehouse"). type drives the input control the UI renders. */
export interface AttrField {
  key: string;
  label: string;
  type: "enum" | "number" | "bool";
  options?: string[];
}

const STATES = ["CA", "TX", "FL", "NY", "OH", "PA", "IL", "GA", "NC", "MI", "AZ", "WA", "CO", "TN", "MA"];

export const ATTR_FIELDS: AttrField[] = [
  { key: "persona", label: "Persona", type: "enum", options: [...PERSONAS] },
  { key: "state", label: "State", type: "enum", options: STATES },
  {
    key: "pwcStatus",
    label: "PWC status",
    type: "enum",
    options: ["none", "eligible", "active", "runout"],
  },
  { key: "monthlyOptumPayVolume", label: "Monthly Optum Pay volume", type: "number" },
  { key: "locations", label: "Number of locations", type: "number" },
  { key: "npxEnrolled", label: "NPx enrolled", type: "bool" },
  { key: "hasOptumBankAccount", label: "Has Optum Bank account", type: "bool" },
  { key: "primaryBankOnFile", label: "Primary bank on file", type: "bool" },
];

export const EVENT_OPTIONS = FUNNEL_EVENTS.map((e) => ({ value: e, label: FUNNEL_EVENT_LABEL[e] }));
export const PRODUCT_OPTIONS = PRODUCTS.map((p) => ({ value: p, label: PRODUCT_LABEL[p] }));

function hashId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) >>> 0;
  return h;
}

function attrValue(p: Provider, key: string): string | number | boolean | undefined {
  return (p as unknown as Record<string, string | number | boolean>)[key];
}

function evalOne(
  c: SegmentCondition,
  p: Provider,
  eventsByProvider: Map<string, FunnelEvent[]>
): boolean {
  if (c.kind === "attribute") {
    const v = attrValue(p, c.field);
    if (v === undefined) return false;
    if (c.op === "gte") return Number(v) >= Number(c.value);
    if (c.op === "lte") return Number(v) <= Number(c.value);
    const eq =
      typeof v === "boolean" ? String(v) === String(c.value) : String(v) === String(c.value);
    return c.op === "is" ? eq : !eq;
  }
  if (c.kind === "product") {
    const has = p.productsHeld.includes(c.product);
    return c.has ? has : !has;
  }
  if (c.kind === "event") {
    const evs = eventsByProvider.get(p.id) ?? [];
    const cutoff =
      c.window === "any" ? -Infinity : NOW - Number(c.window.replace("d", "")) * DAY;
    const did = evs.some((e) => e.eventType === c.event && +new Date(e.occurredAt) >= cutoff);
    return c.performed ? did : !did;
  }
  // message activity (mock, deterministic per provider)
  const h = hashId(p.id);
  const opened = h % 5 < 2; // ~40%
  const clicked = h % 5 === 0; // ~20%
  if (c.activity === "opened") return opened;
  if (c.activity === "clicked") return clicked;
  return !opened; // not_opened
}

export function matchProviders(data: Dataset, rules: SegmentRules): Provider[] {
  const eventsByProvider = new Map<string, FunnelEvent[]>();
  for (const e of data.funnelEvents) {
    if (!eventsByProvider.has(e.providerId)) eventsByProvider.set(e.providerId, []);
    eventsByProvider.get(e.providerId)!.push(e);
  }
  if (rules.conditions.length === 0) return data.providers;
  return data.providers.filter((p) => {
    const results = rules.conditions.map((c) => evalOne(c, p, eventsByProvider));
    return rules.match === "all" ? results.every(Boolean) : results.some(Boolean);
  });
}

export function countMatches(data: Dataset, rules: SegmentRules): number {
  return matchProviders(data, rules).length;
}

/* A short human-readable summary of a condition, for chips and previews. */
export function describeCondition(c: SegmentCondition): string {
  if (c.kind === "attribute") {
    const f = ATTR_FIELDS.find((x) => x.key === c.field);
    const opTxt = c.op === "is" ? "is" : c.op === "is_not" ? "is not" : c.op === "gte" ? ">=" : "<=";
    return `${f?.label ?? c.field} ${opTxt} ${c.value}`;
  }
  if (c.kind === "product") {
    return `${c.has ? "has" : "does not have"} ${PRODUCT_LABEL[c.product]}`;
  }
  if (c.kind === "event") {
    const win = c.window === "any" ? "ever" : `in last ${c.window}`;
    return `${c.performed ? "did" : "did not"} ${FUNNEL_EVENT_LABEL[c.event]} ${win}`;
  }
  return `${c.activity === "not_opened" ? "did not open" : c.activity} a message`;
}
