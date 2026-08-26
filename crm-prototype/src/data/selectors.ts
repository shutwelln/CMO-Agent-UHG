import type {
  Activity,
  Contact,
  Dataset,
  FunnelEvent,
  OfferLead,
  Provider,
  Stage,
} from "./schema";
import { STAGES } from "./schema";

export function providerById(d: Dataset, id: string): Provider | undefined {
  return d.providers.find((p) => p.id === id);
}

export function contactsForProvider(d: Dataset, providerId: string): Contact[] {
  return d.contacts.filter((c) => c.providerId === providerId);
}

export function fdmForProvider(d: Dataset, providerId: string): Contact | undefined {
  const fdms = d.contacts.filter((c) => c.providerId === providerId && c.isFdm);
  return fdms.sort((a, b) => b.matchScore - a.matchScore)[0];
}

export function leadsForProvider(d: Dataset, providerId: string): OfferLead[] {
  return d.leads.filter((l) => l.providerId === providerId);
}

export function activitiesForProvider(d: Dataset, providerId: string): Activity[] {
  return d.activities
    .filter((a) => a.providerId === providerId)
    .sort((a, b) => +new Date(b.occurredAt) - +new Date(a.occurredAt));
}

export function funnelForProvider(d: Dataset, providerId: string): FunnelEvent[] {
  return d.funnelEvents
    .filter((e) => e.providerId === providerId)
    .sort((a, b) => +new Date(a.occurredAt) - +new Date(b.occurredAt));
}

export function leadsForRep(d: Dataset, repId: string): OfferLead[] {
  return d.leads.filter((l) => l.assignedRepId === repId);
}

export function repById(d: Dataset, id: string | null) {
  return id ? d.reps.find((r) => r.id === id) : undefined;
}

export interface FunnelCounts {
  started: number;
  stuck: number;
  completed: number;
  funded: number;
  originated: number;
}

export function funnelCounts(d: Dataset): FunnelCounts {
  const set = (t: string) => new Set(d.funnelEvents.filter((e) => e.eventType === t).map((e) => e.providerId));
  return {
    started: set("signup_started").size,
    stuck: set("stuck_mid_funnel").size,
    completed: set("completed_signup").size,
    funded: set("account_funded").size,
    originated: set("loan_originated").size,
  };
}

export function stageCounts(d: Dataset, leads: OfferLead[] = d.leads): Record<Stage, number> {
  const out = Object.fromEntries(STAGES.map((s) => [s, 0])) as Record<Stage, number>;
  for (const l of leads) out[l.stage]++;
  return out;
}

export function pipelineValue(leads: OfferLead[]): number {
  return leads.filter((l) => l.stage !== "closed").reduce((s, l) => s + l.offerAmount, 0);
}

/* Providers whose latest funnel event is a drop-off (stuck, or funded-no-loan). */
export function droppedProviders(d: Dataset): { provider: Provider; step: string; event: FunnelEvent }[] {
  const out: { provider: Provider; step: string; event: FunnelEvent }[] = [];
  const byProv = new Map<string, FunnelEvent[]>();
  for (const e of d.funnelEvents) {
    if (!byProv.has(e.providerId)) byProv.set(e.providerId, []);
    byProv.get(e.providerId)!.push(e);
  }
  for (const [pid, events] of byProv) {
    const sorted = events.sort((a, b) => +new Date(a.occurredAt) - +new Date(b.occurredAt));
    const last = sorted[sorted.length - 1];
    const p = providerById(d, pid);
    if (!p) continue;
    if (last.eventType === "stuck_mid_funnel") {
      out.push({ provider: p, step: last.stuckStep ?? "mid-funnel", event: last });
    } else if (last.eventType === "account_funded") {
      out.push({ provider: p, step: "funded, no loan originated", event: last });
    }
  }
  return out;
}
