import { create } from "zustand";
import type { Role } from "./role";

export interface TourStep {
  role: Role;
  path: string;
  title: string;
  body: string;
}

/* A self-driving walkthrough that hits all four modules across the three roles.
 * Mirrors the demo script: ingest -> leads -> rep 360 -> console -> marketing funnel
 * -> campaign builder -> integration handoff. */
export const TOUR_STEPS: TourStep[] = [
  {
    role: "sales_ops",
    path: "/ingest",
    title: "1. Ingest the monthly bank file",
    body: "The bank sends ~160,000 pre-qualified Provider Working Capital offers each month. The wizard matches them on TIN, appends financial-decision-maker contacts, and auto-assigns by deal size. This replaces the giant spreadsheet.",
  },
  {
    role: "sales_ops",
    path: "/leads",
    title: "2. Offers become an actionable inbox",
    body: "Every offer lands as a lead with its product, amount, tier, assigned specialist, FDM confidence, stage, and outreach attempts. Filter, sort, and bulk-act. No VLOOKUPs.",
  },
  {
    role: "sales_rep",
    path: "/",
    title: "3. Sales specialists get a focused workspace",
    body: "Switched to the Sales Specialist role. Each specialist sees only their assigned pipeline, next-best-offer alerts, and today's follow-ups. Internal specialists and 3rd-party call center staff use the same tools.",
  },
  {
    role: "sales_rep",
    path: "/providers/prov_2",
    title: "4. Provider 360 with the funnel and next-best-offer",
    body: "A full view of the provider: firmographics, the signup funnel timeline (started, stuck, funded, originated), and a ranked next-best-offer rail using the real economics (0.25% APR bundle, NPx fee cut, Cash Acceleration).",
  },
  {
    role: "sales_rep",
    path: "/console",
    title: "5. Work the outbound queue",
    body: "A dialer-style console: prioritized queue, the decision-maker contact with click-to-call and click-to-email, a persona-matched talk track, dispositions, product-interest capture, and appointment setting for senior specialists. Filter the queue by internal specialists or a 3rd-party call center.",
  },
  {
    role: "marketing",
    path: "/",
    title: "6. Campaign Management sees the drop-off story",
    body: "Switched to the Campaign Management role. The funnel drop-off is visible in one place, sourced from the provider master data set.",
  },
  {
    role: "marketing",
    path: "/campaigns/new",
    title: "7. Self-serve lifecycle campaigns",
    body: "Pick a funnel-stage segment and the audience size updates live. What used to take 4 to 8 weeks to pull a list now takes seconds. Choose Marketo or Customer.io as a swappable connector, then launch.",
  },
  {
    role: "sales_ops",
    path: "/admin/sources",
    title: "8. Built for the engineering handoff",
    body: "Every integration is a clearly-labeled stub that maps to a real system: the provider master data warehouse, the monthly bank SFTP file, the third-party FDM vendor, the ESP APIs, and the downstream Salesforce Go commission export.",
  },
];

interface TourState {
  active: boolean;
  step: number;
  start: () => void;
  stop: () => void;
  next: () => void;
  prev: () => void;
}

export const useTour = create<TourState>((set, get) => ({
  active: false,
  step: 0,
  start: () => set({ active: true, step: 0 }),
  stop: () => set({ active: false }),
  next: () => {
    const { step } = get();
    if (step >= TOUR_STEPS.length - 1) set({ active: false });
    else set({ step: step + 1 });
  },
  prev: () => set((s) => ({ step: Math.max(0, s.step - 1) })),
}));
