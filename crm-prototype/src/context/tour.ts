import { create } from "zustand";
import type { Role } from "./role";

export interface TourStep {
  role: Role;
  path: string;
  title: string;
  body: string;
}

/* A self-driving walkthrough across all three roles: ingest and leads, the sales
 * workspace, reporting, then the full lifecycle capability (segments + journeys),
 * ending on the engineering handoff. */
export const TOUR_STEPS: TourStep[] = [
  {
    role: "sales_ops",
    path: "/ingest",
    title: "1. Ingest the monthly bank offer file",
    body: "The bank sends about 160,000 pre-qualified Provider Working Capital offers each month, with Capital and Cash Flow loan amounts, fees, a Max Offer, and a bank Tier A to D. The wizard maps the columns, merges on TIN, appends financial-decision-maker contacts, and auto-assigns by deal size. This replaces the giant spreadsheet.",
  },
  {
    role: "sales_ops",
    path: "/leads",
    title: "2. Offers become an actionable Lead Inbox",
    body: "Every offer lands as a lead showing its loan mix, Max Offer, bank Tier, assigned specialist, FDM confidence, Lead Type, and the real Lead Status. Filter by stage, tier, or lead type, sort, and bulk-act. No VLOOKUPs.",
  },
  {
    role: "sales_ops",
    path: "/pipeline",
    title: "3. The pipeline mirrors your real status journey",
    body: "The board columns are your actual bands: Ready or Upload, Engaged, KYC or Vetting, Disbursed, Renewal, and Closed. Drag a provider across stages or set the granular status from the card, exactly like the spreadsheet your team works today.",
  },
  {
    role: "sales_rep",
    path: "/",
    title: "4. Sales specialists get a focused workspace",
    body: "Switched to the Sales Specialist role (signed in as Angelo Altavilla). Each specialist sees only their assigned pipeline, their personal quarterly goal, next-best-offer alerts, and today's follow-ups. Internal specialists and a 3rd-party call center use the same tools.",
  },
  {
    role: "sales_rep",
    path: "/providers/prov_2",
    title: "5. Provider 360 with the funnel and next-best-offer",
    body: "A full view of the provider: firmographics, the bank offer, the signup funnel timeline (started, stuck, funded, originated), decision-maker contact with click-to-call and click-to-email, and a ranked next-best-offer rail using the real economics (0.25% APR bundle, NPx fee cut, Cash Acceleration).",
  },
  {
    role: "sales_rep",
    path: "/console",
    title: "6. Work the outbound queue",
    body: "A dialer-style console: prioritized queue, the decision-maker with click-to-call and email, a persona-matched talk track, dispositions that move the lead status, product-interest capture, and appointment setting for senior specialists. A caller-group toggle switches between internal specialists and a 3rd-party call center.",
  },
  {
    role: "sales_ops",
    path: "/reporting/goals",
    title: "7. Goals and targets, by specialist and product line",
    body: "Quarterly attainment tracked two ways: per sales specialist and per product line, with pace status (ahead, on track, behind, at risk) and progress against target. This is what Salesforce Go only handles at the very end for commissions.",
  },
  {
    role: "marketing",
    path: "/segments/new",
    title: "8. Build precise segments from the warehouse",
    body: "Switched to the Campaign Management role. Build data-driven segments on warehouse attributes, behavioral events (for example started the bank-account signup but has not completed it), and cross-product logic (has a bank account but not a term loan). The match count updates live against the real data. This mirrors Customer.io.",
  },
  {
    role: "marketing",
    path: "/campaigns/camp_1",
    title: "9. Design multi-step lifecycle journeys",
    body: "Campaigns trigger on segment entry or on an event, then run a visual journey: emails, delays, branches on open or click, random A/B splits, and exit goals, over 90 days. Each email has From, Reply-to, Subject, a rich-text or HTML editor, and A/B variants. Portable to Marketo or Salesforce.",
  },
  {
    role: "marketing",
    path: "/",
    title: "10. Self-serve, in seconds",
    body: "The Campaign Management dashboard shows the funnel drop-off in one place. Triggering a campaign against a live segment used to take 4 to 8 weeks of list-pulls. Now it takes seconds, with no ticket to another team.",
  },
  {
    role: "sales_ops",
    path: "/admin/connectors",
    title: "11. Swappable delivery connectors",
    body: "The CRM is ESP-agnostic. Marketo is the approved-vendor connector; Customer.io is available pending procurement. Journeys and segments defined here map onto either, so nothing is locked to one platform.",
  },
  {
    role: "sales_ops",
    path: "/admin/sources",
    title: "12. Built for the engineering handoff",
    body: "Every integration maps to a real system: the provider master data warehouse feed, the monthly bank SFTP file, the third-party FDM vendor, the ESP APIs, and the downstream Salesforce Go commission export. This is the blueprint for the real build.",
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
