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

// Board stages: the color bands of the real PWC lead-status sheet, used as
// pipeline columns. Each granular lead status (below) rolls up to one of these.
export const STAGES = [
  "ready",
  "engaged",
  "kyc",
  "disbursed",
  "renewal",
  "closed",
] as const;
export type Stage = (typeof STAGES)[number];

export const STAGE_LABEL: Record<Stage, string> = {
  ready: "Ready / Upload",
  engaged: "Engaged",
  kyc: "KYC / Vetting",
  disbursed: "Disbursed",
  renewal: "Renewal",
  closed: "Closed / Lost",
};

// The real Lead Status taxonomy from the working PWC spreadsheet. This is the
// primary field sales specialists move providers through.
export interface LeadStatusDef {
  code: string;
  label: string;
  definition: string;
  stage: Stage;
}
export const LEAD_STATUSES: LeadStatusDef[] = [
  { code: "0.1", label: "Bank Rejected/Restricted", definition: "Provider restricted by bank", stage: "closed" },
  { code: "0.2", label: "Ineligible", definition: "Not eligible for an offer", stage: "closed" },
  { code: "0.3", label: "Provider Postponed/Declined", definition: "Provider declined or postponed", stage: "closed" },
  { code: "0.4", label: "No Response From Drip Campaign", definition: "No response on the drip campaign", stage: "closed" },
  { code: "0.9", label: "Needs To Be Uploaded", definition: "Offer/provider data needs to be uploaded into PWC CSR", stage: "ready" },
  { code: "1", label: "Ready For Outreach", definition: "Ready to solicit; provider can now fill out KYC", stage: "ready" },
  { code: "2.0", label: "Engaged Once", definition: "First round of emailing", stage: "engaged" },
  { code: "2.1", label: "White Glove Treatment", definition: "Bigger provider (typically Bs and Cs); not part of drip", stage: "engaged" },
  { code: "2.2", label: "Engaged Twice", definition: "Second round of emailing, ~2 business days after first", stage: "engaged" },
  { code: "2.4", label: "Engaged Three Times", definition: "Third round of emailing", stage: "engaged" },
  { code: "2.6", label: "Engaged Four Times", definition: "Fourth round of emailing", stage: "engaged" },
  { code: "2.8", label: "Engaged Five Times", definition: "Last round of emailing", stage: "engaged" },
  { code: "3", label: "Provider Reviewing", definition: "Pending provider decision", stage: "engaged" },
  { code: "3.5", label: "Meeting With Provider", definition: "Pending meeting with provider", stage: "engaged" },
  { code: "4.0", label: "KYC Submitted", definition: "Provider submitted KYC, no bank action yet", stage: "kyc" },
  { code: "4.1", label: "KYC More Info/Edits Needed", definition: "KYC submitted, provider action needed", stage: "kyc" },
  { code: "4.2", label: "KYC Complete/Ready To Accept Offer", definition: "All vetting complete, offer ready for acceptance", stage: "kyc" },
  { code: "4.25", label: "KYC Complete/Ready (Reduced Offer)", definition: "Ready for acceptance, reduced offer", stage: "kyc" },
  { code: "4.3", label: "Vetting Expired/New KYC Needed", definition: "KYC expired, need a new submission", stage: "kyc" },
  { code: "5", label: "Offer Accepted/Disbursed", definition: "Vetting approved, loan disbursed", stage: "disbursed" },
  { code: "5.5", label: "Disbursed (Reduced Offer)", definition: "Approved for a lowered offer, disbursed", stage: "disbursed" },
  { code: "6.0", label: "Loan Repaid/Subsequent KYC Needed", definition: "Renewal opportunity, new KYC needed", stage: "renewal" },
  { code: "6.01", label: "Subsequent White Glove Treatment", definition: "Renewal, bigger provider", stage: "renewal" },
  { code: "6.02", label: "Subsequent: First Engage", definition: "Renewal, first round of emailing", stage: "renewal" },
  { code: "6.03", label: "Subsequent: Second Engage", definition: "Renewal, second round of emailing", stage: "renewal" },
  { code: "6.04", label: "Subsequent: Third Engage", definition: "Renewal, third round of emailing", stage: "renewal" },
  { code: "6.05", label: "Reviewing/Meeting With Provider", definition: "Renewal, provider reviewing or meeting", stage: "renewal" },
  { code: "6.1", label: "Subsequent KYC Submitted", definition: "Renewal KYC submitted", stage: "renewal" },
  { code: "6.2", label: "Subsequent KYC More Info/Edits Needed", definition: "Renewal KYC needs info/edits", stage: "renewal" },
  { code: "6.3", label: "Subsequent Offer Ready For Acceptance", definition: "Renewal vetting complete", stage: "renewal" },
  { code: "6.35", label: "Subsequent Offer Ready (Reduced Offer)", definition: "Renewal ready, reduced offer", stage: "renewal" },
  { code: "6.4", label: "Subsequent Offer Disbursed", definition: "Renewal offer disbursed", stage: "renewal" },
  { code: "6.45", label: "Subsequent Offer Disbursed (Reduced Offer)", definition: "Renewal disbursed, reduced offer", stage: "renewal" },
];
export const STATUS_BY_CODE: Record<string, LeadStatusDef> = Object.fromEntries(
  LEAD_STATUSES.map((s) => [s.code, s])
);

// Bank quality tier from the monthly offer file.
export const BANK_TIERS = ["A", "B", "C", "D"] as const;
export type BankTier = (typeof BANK_TIERS)[number];

// Lead Type (source) values from the master spreadsheet.
export const LEAD_TYPES = [
  "Conference",
  "Existing Customer",
  "Growth Office/OI",
  "In App (Site/Widget)",
  "Marketing Ad Campaign",
  "Marketing Email",
  "MPP",
  "Prospect",
  "Provider Referral",
  "Sales Calls",
  "Sales Emails",
  "UHC",
  "Website",
] as const;
export type LeadType = (typeof LEAD_TYPES)[number];

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
  parentEntity: z.string(), // Parent Entity column (often blank)
  providerId: z.string(),
  // Offer file loan components (each with a fee); "-" in the file becomes 0
  capitalOffer: z.number(),
  capitalFee: z.number(),
  cashFlowOffer: z.number(),
  cashFlowFee: z.number(),
  offerAmount: z.number(), // Max Offer
  bankTier: z.enum(BANK_TIERS), // A/B/C/D from the bank file
  offerMonth: z.string(),
  leadType: z.enum(LEAD_TYPES), // source
  status: z.string(), // granular lead-status code, e.g. "2.2"
  stage: z.enum(STAGES), // board group derived from status
  tier: z.enum(TIERS), // internal deal-size assignment tier (senior/mid/junior)
  assignedRepId: z.string().nullable(),
  sourceFileId: z.string().nullable(),
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

// ----- Segment condition model (data-driven, auto-updating segments) -----
export type MatchOp = "all" | "any"; // AND / OR
export interface AttributeCondition {
  kind: "attribute";
  field: string; // provider attribute key
  op: "is" | "is_not" | "gte" | "lte";
  value: string | number;
}
export interface EventCondition {
  kind: "event";
  performed: boolean; // performed / did not perform
  event: FunnelEventType;
  window: "any" | "7d" | "30d" | "90d";
}
export interface ProductCondition {
  kind: "product";
  has: boolean; // has / does not have
  product: Product;
}
export interface MessageCondition {
  kind: "message";
  activity: "opened" | "clicked" | "not_opened";
}
export type SegmentCondition =
  | AttributeCondition
  | EventCondition
  | ProductCondition
  | MessageCondition;
export interface SegmentRules {
  match: MatchOp;
  conditions: SegmentCondition[];
}

export const segmentSchema = z.object({
  id: z.string(),
  name: z.string(),
  funnelStage: z.string(),
  filters: z.record(z.string(), z.any()),
  size: z.number(),
  rules: z.any().optional(), // SegmentRules
});
export type Segment = z.infer<typeof segmentSchema> & { rules?: SegmentRules };

// ----- Campaign trigger + visual journey model -----
export type TriggerType = "segment" | "event" | "date" | "api";
export interface CampaignTrigger {
  type: TriggerType;
  segmentId?: string;
  event?: FunnelEventType;
  dateField?: string;
}

export interface EmailVariant {
  id: string;
  label: string; // "A" / "B"
  weight: number; // split %
  subject: string;
  fromName: string;
  fromEmail: string;
  replyTo: string;
  preheader: string;
  bodyHtml: string;
}
export type JourneyNodeType = "email" | "delay" | "condition" | "split" | "exit";
export interface JourneyNode {
  id: string;
  type: JourneyNodeType;
  // email
  name?: string;
  abTest?: boolean;
  variants?: EmailVariant[];
  // delay
  delayValue?: number;
  delayUnit?: "minutes" | "hours" | "days";
  // condition (branches on yes/no)
  conditionKind?: "opened" | "clicked" | "attribute" | "event";
  conditionLabel?: string;
  yes?: JourneyNode[];
  no?: JourneyNode[];
  // split (random A/B)
  splitPercent?: number;
  branchA?: JourneyNode[];
  branchB?: JourneyNode[];
}
export interface Journey {
  nodes: JourneyNode[];
  goal?: string; // exit-on-conversion goal
  exitOn?: string; // exit condition
}

export const campaignSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(["draft", "active", "paused", "complete"]),
  segmentName: z.string(),
  connector: z.enum(["Marketo"]),
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
  trigger: z.any().optional(), // CampaignTrigger
  journey: z.any().optional(), // Journey
});
export type Campaign = z.infer<typeof campaignSchema> & {
  trigger?: CampaignTrigger;
  journey?: Journey;
};

// ----- Broadcast model (one-off / scheduled single-message sends) -----
// A broadcast delivers a single email or newsletter to an explicit audience
// resolved at send time: either a saved segment or a list uploaded for this
// send. Unlike a lifecycle journey there is no ongoing trigger and each
// recipient receives the message once.
export type EmailBlockType =
  | "heading"
  | "text"
  | "image"
  | "button"
  | "divider"
  | "spacer";

export interface EmailBlock {
  id: string;
  type: EmailBlockType;
  text?: string; // heading text or button label
  html?: string; // rich-text body for text blocks
  href?: string; // button / image link target
  src?: string; // image url
  alt?: string; // image alt text
  align?: "left" | "center" | "right";
  height?: number; // spacer height in px
}

export type BroadcastAudienceKind = "segment" | "upload";
export interface BroadcastAudience {
  kind: BroadcastAudienceKind;
  // saved-segment audience
  segmentId?: string;
  segmentName?: string;
  // uploaded-list audience
  listName?: string;
  uploadedCount?: number; // rows in the uploaded file
  matchedCount?: number; // rows matched to a provider on TIN/email
}

export type BroadcastStatus = "draft" | "scheduled" | "sending" | "sent";

export interface BroadcastSchedule {
  mode: "now" | "scheduled";
  sendAt?: string; // ISO, when mode === "scheduled"
}

export const broadcastSchema = z.object({
  id: z.string(),
  name: z.string(),
  status: z.enum(["draft", "scheduled", "sending", "sent"]),
  subject: z.string(),
  preheader: z.string(),
  fromName: z.string(),
  fromEmail: z.string(),
  replyTo: z.string(),
  blocks: z.any(), // EmailBlock[]
  audience: z.any(), // BroadcastAudience
  connector: z.enum(["Marketo"]),
  audienceSize: z.number(),
  schedule: z.any(), // BroadcastSchedule
  metrics: z.object({
    sent: z.number(),
    delivered: z.number(),
    opens: z.number(),
    clicks: z.number(),
    unsubscribes: z.number(),
  }),
  createdByRole: z.string(),
  sentAt: z.string().nullable(),
  scheduledFor: z.string().nullable(),
});
export type Broadcast = z.infer<typeof broadcastSchema> & {
  blocks: EmailBlock[];
  audience: BroadcastAudience;
  schedule: BroadcastSchedule;
};

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
  name: z.enum(["Marketo"]),
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
  broadcasts: Broadcast[];
  appointments: Appointment[];
  connectors: Connector[];
  dataSources: DataSource[];
  sourceFiles: SourceFile[];
  goals: Goal[];
}
