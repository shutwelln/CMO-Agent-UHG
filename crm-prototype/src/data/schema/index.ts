import { z } from "zod";

/*
 * The data contract for the Optum Financial / Optum Banking Solutions CRM.
 * These zod schemas double as the handoff spec for the engineering team:
 * production feeds (provider master data warehouse, monthly bank offer file,
 * third-party FDM data) map onto these shapes.
 */

// ----- Enumerations grounded in the GTM strategic intent log -----

export const PERSONAS = [
  "Sole Practitioner",
  "Growing Group",
  "High Volume Specialty",
  "Digital-First",
  "Multi-Specialty Group",
  "Hospital-affiliated",
  "PE-backed Group",
] as const;
export type Persona = (typeof PERSONAS)[number];

export const PRODUCTS = [
  "pwc",
  "bank_account",
  "term_loan",
  "loc",
  "equipment",
  "cash_acceleration",
] as const;
export type Product = (typeof PRODUCTS)[number];

export const PRODUCT_LABEL: Record<Product, string> = {
  pwc: "Provider Working Capital",
  bank_account: "Bank Account",
  term_loan: "Term Loan",
  loc: "Line of Credit",
  equipment: "Equipment Financing",
  cash_acceleration: "Cash Acceleration",
};

export const PRODUCT_SHORT: Record<Product, string> = {
  pwc: "PWC",
  bank_account: "Bank Acct",
  term_loan: "Term Loan",
  loc: "LOC",
  equipment: "Equipment",
  cash_acceleration: "Cash Accel",
};

export const STAGES = [
  "new",
  "working",
  "contacted",
  "qualified",
  "appt_set",
  "won",
  "lost",
] as const;
export type Stage = (typeof STAGES)[number];

export const STAGE_LABEL: Record<Stage, string> = {
  new: "New",
  working: "Working",
  contacted: "Contacted",
  qualified: "Qualified",
  appt_set: "Appt Set",
  won: "Won",
  lost: "Lost",
};

export const TIERS = ["senior", "mid", "junior"] as const;
export type Tier = (typeof TIERS)[number];

export const TEAMS = [
  "OI Provider Sales",
  "OFS Commercial",
  "OI Provider AM",
  "3rd-Party Call Center",
] as const;
export type Team = (typeof TEAMS)[number];

export const FUNNEL_EVENTS = [
  "signup_started",
  "stuck_mid_funnel",
  "completed_signup",
  "account_funded",
  "loan_originated",
] as const;
export type FunnelEventType = (typeof FUNNEL_EVENTS)[number];

export const FUNNEL_EVENT_LABEL: Record<FunnelEventType, string> = {
  signup_started: "Signup Started",
  stuck_mid_funnel: "Stuck Mid-Funnel",
  completed_signup: "Completed Signup",
  account_funded: "Account Funded",
  loan_originated: "Loan Originated",
};

export const FUNNEL_SURFACES = ["savana", "biz2x", "pwc"] as const;
export type FunnelSurface = (typeof FUNNEL_SURFACES)[number];

export const SURFACE_LABEL: Record<FunnelSurface, string> = {
  savana: "Savana (Bank Account)",
  biz2x: "Biz2X (Term Loan)",
  pwc: "Legacy PWC",
};

export const DISPOSITIONS = [
  "connected",
  "no_answer",
  "voicemail",
  "callback",
  "not_interested",
  "qualified",
  "dnc",
] as const;
export type Disposition = (typeof DISPOSITIONS)[number];

export const DISPOSITION_LABEL: Record<Disposition, string> = {
  connected: "Connected",
  no_answer: "No Answer",
  voicemail: "Voicemail",
  callback: "Callback",
  not_interested: "Not Interested",
  qualified: "Qualified",
  dnc: "Do Not Call",
};

export const CONFIDENCE = ["high", "med", "low", "none"] as const;
export type Confidence = (typeof CONFIDENCE)[number];

// ----- Entity schemas -----

export const contactSchema = z.object({
  id: z.string(),
  providerId: z.string(),
  name: z.string(),
  title: z.string(),
  role: z.enum(["admin", "owner", "cfo", "physician"]),
  email: z.string(),
  phone: z.string(),
  isFdm: z.boolean(),
  source: z.enum(["internal", "third_party"]),
  matchConfidence: z.enum(CONFIDENCE),
  matchScore: z.number(),
});
export type Contact = z.infer<typeof contactSchema>;

export const providerSchema = z.object({
  id: z.string(),
  tin: z.string(),
  legalName: z.string(),
  dba: z.string(),
  persona: z.enum(PERSONAS),
  specialty: z.string(),
  state: z.string(),
  city: z.string(),
  locations: z.number(),
  monthlyOptumPayVolume: z.number(),
  npxEnrolled: z.boolean(),
  pwcStatus: z.enum(["none", "eligible", "active", "runout"]),
  primaryBankOnFile: z.boolean(),
  hasOptumBankAccount: z.boolean(),
  productsHeld: z.array(z.enum(PRODUCTS)),
  currentStage: z.enum(STAGES),
  createdAt: z.string(),
});
export type Provider = z.infer<typeof providerSchema>;

export const offerLeadSchema = z.object({
  id: z.string(),
  tin: z.string(),
  providerId: z.string(),
  product: z.enum(PRODUCTS),
  offerAmount: z.number(),
  rate: z.number(), // APR or fee %, product-dependent
  offerMonth: z.string(),
  bundleFlags: z.array(z.enum(["apr_reduction", "npx_reduction", "cash_accel"])),
  tier: z.enum(TIERS),
  stage: z.enum(STAGES),
  assignedRepId: z.string().nullable(),
  sourceFileId: z.string().nullable(),
  nboRank: z.number(),
  lastOutreachAt: z.string().nullable(),
  attempts: z.number(),
  createdAt: z.string(),
});
export type OfferLead = z.infer<typeof offerLeadSchema>;

export const repSchema = z.object({
  id: z.string(),
  name: z.string(),
  seniority: z.enum(TIERS),
  team: z.enum(TEAMS),
  capacity: z.number(),
  active: z.boolean(),
  avatarInitials: z.string(),
});
export type Rep = z.infer<typeof repSchema>;

export const activitySchema = z.object({
  id: z.string(),
  providerId: z.string(),
  leadId: z.string().nullable(),
  type: z.enum(["call", "email", "sms", "note", "campaign", "appointment", "funnel"]),
  channel: z.string(),
  attemptNumber: z.number().nullable(),
  disposition: z.enum(DISPOSITIONS).nullable(),
  productInterest: z.array(z.enum(PRODUCTS)),
  interestLevel: z.enum(["hot", "warm", "cold", "none"]),
  actor: z.string(), // rep name or campaign name
  occurredAt: z.string(),
  notes: z.string(),
});
export type Activity = z.infer<typeof activitySchema>;

export const funnelEventSchema = z.object({
  id: z.string(),
  providerId: z.string(),
  eventType: z.enum(FUNNEL_EVENTS),
  surface: z.enum(FUNNEL_SURFACES),
  stuckStep: z.string().nullable(),
  occurredAt: z.string(),
});
export type FunnelEvent = z.infer<typeof funnelEventSchema>;

export const segmentSchema = z.object({
  id: z.string(),
  name: z.string(),
  funnelStage: z.string(),
  filters: z.record(z.string(), z.any()),
  size: z.number(),
});
export type Segment = z.infer<typeof segmentSchema>;

export const campaignSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(["draft", "active", "paused", "complete"]),
  segmentName: z.string(),
  connector: z.enum(["Marketo", "Customer.io"]),
  journeySteps: z.array(
    z.object({ day: z.number(), channel: z.string(), template: z.string() })
  ),
  audienceSize: z.number(),
  metrics: z.object({
    sent: z.number(),
    delivered: z.number(),
    opens: z.number(),
    clicks: z.number(),
    conversions: z.number(),
  }),
  createdByRole: z.string(),
  launchedAt: z.string().nullable(),
});
export type Campaign = z.infer<typeof campaignSchema>;

export const appointmentSchema = z.object({
  id: z.string(),
  providerId: z.string(),
  leadId: z.string().nullable(),
  repId: z.string(),
  scheduledFor: z.string(),
  type: z.enum(["discovery", "product_demo", "closing"]),
  status: z.enum(["scheduled", "completed", "no_show", "cancelled"]),
  createdBy: z.string(),
});
export type Appointment = z.infer<typeof appointmentSchema>;

export const connectorSchema = z.object({
  id: z.string(),
  name: z.enum(["Marketo", "Customer.io"]),
  kind: z.literal("esp"),
  status: z.enum(["connected_mock", "not_approved"]),
  isApprovedVendor: z.boolean(),
  note: z.string(),
});
export type Connector = z.infer<typeof connectorSchema>;

export const dataSourceSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.string(),
  status: z.string(),
  lastSync: z.string(),
  recordCount: z.number(),
  note: z.string(),
});
export type DataSource = z.infer<typeof dataSourceSchema>;

export const sourceFileSchema = z.object({
  id: z.string(),
  filename: z.string(),
  offerMonth: z.string(),
  rowCount: z.number(),
  totalOfferedAmount: z.number(),
  matchStats: z.object({
    matched: z.number(),
    newProviders: z.number(),
    unmatched: z.number(),
    duplicates: z.number(),
  }),
  fdmStats: z.object({
    before: z.number(),
    after: z.number(),
    high: z.number(),
    med: z.number(),
    low: z.number(),
  }),
  committedAt: z.string().nullable(),
});
export type SourceFile = z.infer<typeof sourceFileSchema>;

export const goalSchema = z.object({
  id: z.string(),
  scope: z.enum(["specialist", "product"]),
  refId: z.string(), // rep id or product key
  refLabel: z.string(),
  period: z.string(), // e.g. "Q3 2026"
  targetRevenue: z.number(),
  attainedRevenue: z.number(),
  targetDeals: z.number(),
  attainedDeals: z.number(),
});
export type Goal = z.infer<typeof goalSchema>;

export interface Dataset {
  providers: Provider[];
  contacts: Contact[];
  leads: OfferLead[];
  reps: Rep[];
  activities: Activity[];
  funnelEvents: FunnelEvent[];
  segments: Segment[];
  campaigns: Campaign[];
  appointments: Appointment[];
  connectors: Connector[];
  dataSources: DataSource[];
  sourceFiles: SourceFile[];
  goals: Goal[];
}
