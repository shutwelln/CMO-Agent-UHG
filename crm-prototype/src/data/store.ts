import { create } from "zustand";
import { STATUS_BY_CODE } from "./schema";
import type {
  Activity,
  Appointment,
  Broadcast,
  Campaign,
  Dataset,
  Disposition,
  Product,
  Segment,
  Stage,
} from "./schema";
import { seedBroadcasts } from "./generators/broadcastSeed";

/*
 * In-memory data store. Loads the synthetic dataset once, then serves as the
 * app's operational store. Every read here maps to a REST GET and every action
 * to a POST/PATCH in the production build (see the handoff blueprint).
 */
interface State {
  data: Dataset | null;
  loaded: boolean;
  ingestCommitted: boolean;
  load: () => Promise<void>;

  // actions (demo mutations)
  commitIngest: () => void;
  launchCampaign: (c: Campaign) => void;
  saveSegment: (seg: Segment) => void;
  updateCampaignStatus: (id: string, status: Campaign["status"]) => void;
  sendBroadcast: (b: Broadcast) => void;
  updateBroadcastStatus: (id: string, status: Broadcast["status"]) => void;
  setLeadStage: (leadId: string, stage: Stage) => void;
  assignLead: (leadId: string, repId: string) => void;
  logDisposition: (
    leadId: string,
    disposition: Disposition,
    notes: string,
    productInterest: Product[],
    interestLevel: Activity["interestLevel"]
  ) => void;
  bookAppointment: (appt: Omit<Appointment, "id">) => void;
  setActiveConnector: (name: "Marketo") => void;
  activeConnector: "Marketo";
}

let idc = 100000;
const nid = (p: string) => `${p}_${idc++}`;
const NOW = "2026-08-22T12:00:00Z";

export const useData = create<State>((set, get) => ({
  data: null,
  loaded: false,
  ingestCommitted: false,
  activeConnector: "Marketo",

  load: async () => {
    if (get().loaded) return;
    const res = await fetch(`${import.meta.env.BASE_URL}data/dataset.json`);
    const data = (await res.json()) as Dataset;
    // Broadcasts are seeded in-app so the shipped dataset stays back-compatible.
    if (!data.broadcasts || data.broadcasts.length === 0) {
      data.broadcasts = seedBroadcasts(data);
    }
    set({ data, loaded: true });
  },

  commitIngest: () =>
    set((s) => {
      if (!s.data) return s;
      const sf = s.data.sourceFiles.map((f) =>
        f.id === "file_jul2026" ? { ...f, committedAt: NOW } : f
      );
      return { data: { ...s.data, sourceFiles: sf }, ingestCommitted: true };
    }),

  launchCampaign: (c) =>
    set((s) => {
      if (!s.data) return s;
      return { data: { ...s.data, campaigns: [c, ...s.data.campaigns] } };
    }),

  saveSegment: (seg) =>
    set((s) => {
      if (!s.data) return s;
      const exists = s.data.segments.some((x) => x.id === seg.id);
      const segments = exists
        ? s.data.segments.map((x) => (x.id === seg.id ? seg : x))
        : [seg, ...s.data.segments];
      return { data: { ...s.data, segments } };
    }),

  updateCampaignStatus: (id, status) =>
    set((s) => {
      if (!s.data) return s;
      return {
        data: {
          ...s.data,
          campaigns: s.data.campaigns.map((c) => (c.id === id ? { ...c, status } : c)),
        },
      };
    }),

  sendBroadcast: (b) =>
    set((s) => {
      if (!s.data) return s;
      return { data: { ...s.data, broadcasts: [b, ...s.data.broadcasts] } };
    }),

  updateBroadcastStatus: (id, status) =>
    set((s) => {
      if (!s.data) return s;
      return {
        data: {
          ...s.data,
          broadcasts: s.data.broadcasts.map((b) =>
            b.id === id ? { ...b, status } : b
          ),
        },
      };
    }),

  setLeadStage: (leadId, stage) =>
    set((s) => {
      if (!s.data) return s;
      return {
        data: {
          ...s.data,
          leads: s.data.leads.map((l) => (l.id === leadId ? { ...l, stage } : l)),
        },
      };
    }),

  assignLead: (leadId, repId) =>
    set((s) => {
      if (!s.data) return s;
      return {
        data: {
          ...s.data,
          leads: s.data.leads.map((l) => (l.id === leadId ? { ...l, assignedRepId: repId } : l)),
        },
      };
    }),

  logDisposition: (leadId, disposition, notes, productInterest, interestLevel) =>
    set((s) => {
      if (!s.data) return s;
      const lead = s.data.leads.find((l) => l.id === leadId);
      if (!lead) return s;
      const rep = s.data.reps.find((r) => r.id === lead.assignedRepId);
      const attempt = lead.attempts + 1;
      const act: Activity = {
        id: nid("act"),
        providerId: lead.providerId,
        leadId,
        type: "call",
        channel: "phone",
        attemptNumber: attempt,
        disposition,
        productInterest,
        interestLevel,
        actor: rep?.name ?? "Outbound Specialist",
        occurredAt: NOW,
        notes,
      };
      const nextStatus =
        disposition === "qualified"
          ? "4.0" // KYC Submitted
          : disposition === "connected"
          ? "3" // Provider Reviewing
          : disposition === "not_interested" || disposition === "dnc"
          ? "0.3" // Provider Postponed/Declined
          : lead.stage === "ready"
          ? "2.0" // first engagement
          : lead.status;
      const nextStage: Stage = STATUS_BY_CODE[nextStatus]?.stage ?? lead.stage;
      return {
        data: {
          ...s.data,
          activities: [act, ...s.data.activities],
          leads: s.data.leads.map((l) =>
            l.id === leadId
              ? { ...l, attempts: attempt, status: nextStatus, stage: nextStage, lastOutreachAt: NOW }
              : l
          ),
        },
      };
    }),

  bookAppointment: (appt) =>
    set((s) => {
      if (!s.data) return s;
      const full: Appointment = { ...appt, id: nid("appt") };
      const act: Activity = {
        id: nid("act"),
        providerId: appt.providerId,
        leadId: appt.leadId,
        type: "appointment",
        channel: "calendar",
        attemptNumber: null,
        disposition: null,
        productInterest: [],
        interestLevel: "warm",
        actor: appt.createdBy,
        occurredAt: NOW,
        notes: `Appointment booked (${appt.type}) with senior sales specialist`,
      };
      const leads = appt.leadId
        ? s.data.leads.map((l) =>
            l.id === appt.leadId ? { ...l, status: "3.5", stage: "engaged" as Stage } : l
          )
        : s.data.leads;
      return {
        data: {
          ...s.data,
          appointments: [full, ...s.data.appointments],
          activities: [act, ...s.data.activities],
          leads,
        },
      };
    }),

  setActiveConnector: (name) => set({ activeConnector: name }),
}));

export const newId = nid;
