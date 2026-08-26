import { create } from "zustand";
import type {
  Activity,
  Appointment,
  Campaign,
  Dataset,
  Disposition,
  Product,
  Stage,
} from "./schema";

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
  updateCampaignStatus: (id: string, status: Campaign["status"]) => void;
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
  setActiveConnector: (name: "Marketo" | "Customer.io") => void;
  activeConnector: "Marketo" | "Customer.io";
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
        actor: rep?.name ?? "Outbound Rep",
        occurredAt: NOW,
        notes,
      };
      const nextStage: Stage =
        disposition === "qualified"
          ? "qualified"
          : disposition === "connected"
          ? "contacted"
          : disposition === "not_interested" || disposition === "dnc"
          ? "lost"
          : lead.stage === "new"
          ? "working"
          : lead.stage;
      return {
        data: {
          ...s.data,
          activities: [act, ...s.data.activities],
          leads: s.data.leads.map((l) =>
            l.id === leadId ? { ...l, attempts: attempt, stage: nextStage, lastOutreachAt: NOW } : l
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
        notes: `Appointment booked (${appt.type}) with senior rep`,
      };
      const leads = appt.leadId
        ? s.data.leads.map((l) => (l.id === appt.leadId ? { ...l, stage: "appt_set" as Stage } : l))
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
