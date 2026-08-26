import {
  PERSONAS,
  PRODUCTS,
  PRODUCT_LABEL,
  STAGES,
  TEAMS,
  type Activity,
  type Appointment,
  type Campaign,
  type Connector,
  type Contact,
  type Dataset,
  type DataSource,
  type FunnelEventType,
  type FunnelEvent,
  type Goal,
  type OfferLead,
  type Persona,
  type Product,
  type Provider,
  type Rep,
  type Segment,
  type SourceFile,
  type Stage,
  type Tier,
  type Team,
  type Disposition,
} from "../schema";
import { PERSONA_DETAIL } from "../../lib/personas";

/* Deterministic RNG (mulberry32) so every build is identical. */
function rng(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const HEADLINE_ROW_COUNT = 160_004; // the real monthly PWC file size (illustrative headline)

export function generateDataset(seed = 42): Dataset {
  const r = rng(seed);
  const pick = <T>(arr: readonly T[]): T => arr[Math.floor(r() * arr.length)];
  const chance = (p: number) => r() < p;
  const between = (lo: number, hi: number) => lo + r() * (hi - lo);
  const intBetween = (lo: number, hi: number) => Math.floor(between(lo, hi + 1));

  const DATE_NOW = new Date("2026-08-22T12:00:00Z").getTime();
  const DAY = 86_400_000;
  const daysAgo = (d: number) => new Date(DATE_NOW - d * DAY).toISOString();
  const daysAhead = (d: number) => new Date(DATE_NOW + d * DAY).toISOString();

  // ----- Sales specialists (the real inside sales team) -----
  // Seniority drives deal-size tiering (senior takes the largest offers). The
  // senior/junior split below is a working assumption - adjust as needed.
  const repNames: [string, Tier, Team][] = [
    ["Angelo Altavilla", "senior", "OI Provider Sales"],
    ["Trent Lloyd", "senior", "OI Provider Sales"],
    ["Jack Uecker", "junior", "OI Provider Sales"],
    ["Jack Hentges", "junior", "OI Provider Sales"],
  ];
  const reps: Rep[] = repNames.map(([name, seniority, team], i) => ({
    id: `rep_${i + 1}`,
    name,
    seniority,
    team,
    capacity: seniority === "senior" ? 1200 : seniority === "mid" ? 1800 : 2400,
    active: true,
    avatarInitials: name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase(),
  }));
  const repsByTier = (t: Tier) => reps.filter((rp) => rp.seniority === t);

  // ----- Providers -----
  const STATES = ["CA", "TX", "FL", "NY", "OH", "PA", "IL", "GA", "NC", "MI", "AZ", "WA", "CO", "TN", "MA"];
  const personaWeights: [Persona, number][] = [
    ["Sole Practitioner", 0.3],
    ["Growing Group", 0.24],
    ["High Volume Specialty", 0.16],
    ["Digital-First", 0.09],
    ["Multi-Specialty Group", 0.1],
    ["Hospital-affiliated", 0.06],
    ["PE-backed Group", 0.05],
  ];
  const weightedPersona = (): Persona => {
    let x = r();
    for (const [p, w] of personaWeights) {
      if (x < w) return p;
      x -= w;
    }
    return "Sole Practitioner";
  };

  const NAME_PREFIX = [
    "Summit", "Cedar", "Riverbend", "Lakeshore", "Pinnacle", "Bayview", "Northgate", "Harbor",
    "Valley", "Maplewood", "Sterling", "Beacon", "Crestline", "Copperfield", "Highland", "Meridian",
    "Prairie", "Coastal", "Redwood", "Brookside", "Ironwood", "Silverleaf", "Grandview", "Foxhollow",
  ];
  const N_PROVIDERS = 5200;
  const providers: Provider[] = [];
  const contacts: Contact[] = [];

  for (let i = 0; i < N_PROVIDERS; i++) {
    const persona = weightedPersona();
    const pd = PERSONA_DETAIL[persona];
    const specialty = pick(pd.specialties);
    const isGroup = persona !== "Sole Practitioner";
    const locations = persona === "PE-backed Group" ? intBetween(6, 40) : persona === "Multi-Specialty Group" ? intBetween(3, 12) : isGroup ? intBetween(2, 6) : 1;
    const baseVol = persona === "High Volume Specialty" ? between(180_000, 900_000) : persona === "PE-backed Group" ? between(220_000, 1_200_000) : isGroup ? between(60_000, 320_000) : between(12_000, 90_000);
    const monthlyOptumPayVolume = Math.round(baseVol / 1000) * 1000;
    const hasBank = chance(0.18);
    const held: Product[] = [];
    if (hasBank) held.push("bank_account");
    if (chance(0.22)) held.push("pwc");
    if (hasBank && chance(0.15)) held.push("term_loan");

    const prefix = pick(NAME_PREFIX);
    const legalName = `${prefix} ${specialty}${isGroup ? (persona === "PE-backed Group" ? " Partners" : " Group") : ""}`;
    const state = pick(STATES);
    const tin = `${intBetween(10, 99)}-${String(intBetween(1000000, 9999999)).padStart(7, "0")}`;

    const p: Provider = {
      id: `prov_${i + 1}`,
      tin,
      legalName,
      dba: chance(0.3) ? `${prefix} ${specialty}` : legalName,
      persona,
      specialty,
      state,
      city: pick(["Springfield", "Riverside", "Fairview", "Georgetown", "Franklin", "Clinton", "Madison", "Arlington", "Auburn", "Dayton"]),
      locations,
      monthlyOptumPayVolume,
      npxEnrolled: chance(0.72),
      pwcStatus: held.includes("pwc") ? (chance(0.15) ? "runout" : "active") : chance(0.5) ? "eligible" : "none",
      primaryBankOnFile: chance(0.65),
      hasOptumBankAccount: hasBank,
      productsHeld: held,
      currentStage: "new",
      createdAt: daysAgo(intBetween(20, 400)),
    };
    providers.push(p);

    // Contacts: always an admin contact; FDM present ~40% internally (the gap)
    const adminFirst = pick(["Jamie", "Chris", "Taylor", "Morgan", "Alex", "Casey", "Jordan", "Riley", "Sam", "Drew"]);
    const adminLast = pick(["Nguyen", "Patel", "Johnson", "Garcia", "Kim", "Brown", "Davis", "Lopez", "Miller", "Wilson"]);
    contacts.push({
      id: `ct_${i}_a`,
      providerId: p.id,
      name: `${adminFirst} ${adminLast}`,
      title: "Practice Administrator",
      role: "admin",
      email: `${adminFirst.toLowerCase()}.${adminLast.toLowerCase()}@${prefix.toLowerCase()}health.com`,
      phone: `(${intBetween(200, 989)}) ${intBetween(200, 989)}-${String(intBetween(1000, 9999))}`,
      isFdm: false,
      source: "internal",
      matchConfidence: "high",
      matchScore: intBetween(88, 99),
    });

    const fdmInternally = chance(0.4);
    if (fdmInternally) {
      const role = persona === "PE-backed Group" || persona === "Multi-Specialty Group" ? "cfo" : persona === "Sole Practitioner" ? "physician" : chance(0.5) ? "owner" : "cfo";
      const fFirst = pick(["Robert", "Linda", "Michael", "Susan", "David", "Karen", "James", "Patricia", "John", "Barbara"]);
      const fLast = pick(["Anderson", "Thomas", "Jackson", "White", "Harris", "Martin", "Thompson", "Moore", "Clark", "Lewis"]);
      contacts.push({
        id: `ct_${i}_f`,
        providerId: p.id,
        name: `${fFirst} ${fLast}`,
        title: role === "cfo" ? "Chief Financial Officer" : role === "owner" ? "Owner / Managing Partner" : "Physician Owner",
        role,
        email: `${fFirst.toLowerCase()}@${prefix.toLowerCase()}health.com`,
        phone: `(${intBetween(200, 989)}) ${intBetween(200, 989)}-${String(intBetween(1000, 9999))}`,
        isFdm: true,
        source: "internal",
        matchConfidence: "high",
        matchScore: intBetween(85, 98),
      });
    }
  }

  // Third-party FDM append lifts coverage from ~40% to ~85%
  const providersMissingFdm = providers.filter((p) => !contacts.some((c) => c.providerId === p.id && c.isFdm));
  const toAppend = providersMissingFdm.slice(0, Math.floor(providersMissingFdm.length * 0.75));
  for (const p of toAppend) {
    const conf = chance(0.5) ? "high" : chance(0.6) ? "med" : "low";
    const fFirst = pick(["Gregory", "Diane", "Steven", "Nancy", "Kevin", "Sandra", "Brian", "Donna", "Edward", "Carol"]);
    const fLast = pick(["Walker", "Hall", "Allen", "Young", "King", "Wright", "Scott", "Green", "Baker", "Adams"]);
    const role = p.persona === "PE-backed Group" || p.persona === "Multi-Specialty Group" ? "cfo" : chance(0.5) ? "owner" : "physician";
    contacts.push({
      id: `ct_${p.id}_tp`,
      providerId: p.id,
      name: `${fFirst} ${fLast}`,
      title: role === "cfo" ? "Chief Financial Officer" : role === "owner" ? "Owner" : "Physician Owner",
      role,
      email: `${fFirst.toLowerCase()}.${fLast.toLowerCase()}@practice-${p.id.slice(5)}.com`,
      phone: `(${intBetween(200, 989)}) ${intBetween(200, 989)}-${String(intBetween(1000, 9999))}`,
      isFdm: true,
      source: "third_party",
      matchConfidence: conf,
      matchScore: conf === "high" ? intBetween(80, 92) : conf === "med" ? intBetween(60, 79) : intBetween(40, 59),
    });
  }

  // ----- Offer leads (lending-led mix) -----
  const productWeights: [Product, number][] = [
    ["pwc", 0.4],
    ["term_loan", 0.24],
    ["bank_account", 0.14],
    ["cash_acceleration", 0.1],
    ["loc", 0.07],
    ["equipment", 0.05],
  ];
  const weightedProduct = (): Product => {
    let x = r();
    for (const [p, w] of productWeights) {
      if (x < w) return p;
      x -= w;
    }
    return "pwc";
  };
  const logNormalAmount = () => {
    // few big deals, many small; $10K–$250K
    const u = r();
    const v = Math.pow(u, 2.2);
    return Math.max(10_000, Math.round((10_000 + v * 240_000) / 1000) * 1000);
  };
  const tierFor = (amt: number): Tier => (amt >= 150_000 ? "senior" : amt >= 50_000 ? "mid" : "junior");
  const stageWeights: [Stage, number][] = [
    ["new", 0.34],
    ["working", 0.2],
    ["contacted", 0.16],
    ["qualified", 0.12],
    ["appt_set", 0.07],
    ["won", 0.06],
    ["lost", 0.05],
  ];
  const weightedStage = (): Stage => {
    let x = r();
    for (const [s, w] of stageWeights) {
      if (x < w) return s;
      x -= w;
    }
    return "new";
  };

  const leads: OfferLead[] = [];
  const N_LEADS = 6400;
  for (let i = 0; i < N_LEADS; i++) {
    const prov = providers[intBetween(0, providers.length - 1)];
    const product = weightedProduct();
    const amount = product === "bank_account" ? 0 : logNormalAmount();
    const tier = product === "bank_account" ? "junior" : tierFor(amount);
    const stage = weightedStage();
    const assigned = stage === "new" && chance(0.35) ? null : pick(repsByTier(tier).length ? repsByTier(tier) : reps).id;
    const bundleFlags: OfferLead["bundleFlags"] = [];
    if (product === "term_loan" && chance(0.5)) bundleFlags.push("apr_reduction");
    if (product === "bank_account" && chance(0.6)) bundleFlags.push("npx_reduction");
    if (product === "cash_acceleration") bundleFlags.push("cash_accel");
    const rate =
      product === "term_loan" ? between(8.99, 24.99) : product === "loc" ? between(9.99, 19.99) : product === "pwc" ? between(12, 26) : product === "cash_acceleration" ? 0.5 : product === "equipment" ? between(7.99, 15.99) : 1.5;
    leads.push({
      id: `lead_${i + 1}`,
      tin: prov.tin,
      providerId: prov.id,
      product,
      offerAmount: amount,
      rate: Math.round(rate * 100) / 100,
      offerMonth: "2026-07",
      bundleFlags,
      tier,
      stage,
      assignedRepId: assigned,
      sourceFileId: product === "pwc" ? "file_jul2026" : null,
      nboRank: intBetween(1, 4),
      lastOutreachAt: stage === "new" ? null : daysAgo(intBetween(1, 40)),
      attempts: stage === "new" ? 0 : stage === "working" ? 1 : intBetween(1, 3),
      createdAt: daysAgo(intBetween(5, 45)),
    });
  }
  // propagate a representative stage onto the provider record
  for (const l of leads) {
    const prov = providers.find((p) => p.id === l.providerId);
    if (prov && (prov.currentStage === "new" || STAGES.indexOf(l.stage) > STAGES.indexOf(prov.currentStage))) {
      prov.currentStage = l.stage;
    }
  }

  // ----- Funnel events (realistic drop-off, backfilled ~9 months) -----
  const funnelEvents: FunnelEvent[] = [];
  const STUCK_STEPS: Record<string, string[]> = {
    savana: ["KYC identity check", "Business verification", "Beneficial-owner disclosure", "Plaid link", "Funding step"],
    biz2x: ["Application form", "Document upload", "Financials review", "Underwriting hold", "Offer acceptance"],
    pwc: ["Legacy consent", "TIN confirmation", "Repayment authorization"],
  };
  const funnelProviders = providers.slice(0, 3400); // subset with signup activity
  let feId = 0;
  for (const p of funnelProviders) {
    const surface: FunnelEvent["surface"] = p.hasOptumBankAccount || chance(0.5) ? "savana" : chance(0.5) ? "biz2x" : "pwc";
    const start = intBetween(15, 270);
    const push = (eventType: FunnelEventType, dayOffset: number, stuckStep: string | null = null) => {
      funnelEvents.push({
        id: `fe_${feId++}`,
        providerId: p.id,
        eventType,
        surface,
        stuckStep,
        occurredAt: daysAgo(Math.max(1, start - dayOffset)),
      });
    };
    push("signup_started", 0);
    const x = r();
    // 100% started -> ~35% stuck -> ~50% completed -> ~35% funded -> ~20% originated
    if (x < 0.35) {
      push("stuck_mid_funnel", intBetween(1, 4), pick(STUCK_STEPS[surface]));
      continue;
    }
    push("completed_signup", intBetween(2, 7));
    if (r() < 0.5) continue;
    push("account_funded", intBetween(8, 20));
    if (r() < 0.45) continue;
    if (surface !== "savana") push("loan_originated", intBetween(21, 40));
    else if (chance(0.5)) push("loan_originated", intBetween(21, 40));
  }

  // ----- Activities -----
  const activities: Activity[] = [];
  let actId = 0;
  const dispoByStage: Record<Stage, Disposition[]> = {
    new: [],
    working: ["no_answer", "voicemail"],
    contacted: ["connected", "callback"],
    qualified: ["connected", "qualified"],
    appt_set: ["qualified", "connected"],
    won: ["qualified", "connected"],
    lost: ["not_interested", "dnc"],
  };
  for (const l of leads) {
    if (l.stage === "new") continue;
    const prov = providers.find((p) => p.id === l.providerId)!;
    const rep = reps.find((rp) => rp.id === l.assignedRepId);
    for (let a = 1; a <= l.attempts; a++) {
      const dispoPool = dispoByStage[l.stage].length ? dispoByStage[l.stage] : (["no_answer"] as Disposition[]);
      activities.push({
        id: `act_${actId++}`,
        providerId: prov.id,
        leadId: l.id,
        type: "call",
        channel: "phone",
        attemptNumber: a,
        disposition: a === l.attempts ? pick(dispoPool) : pick(["no_answer", "voicemail"] as Disposition[]),
        productInterest: a === l.attempts && (l.stage === "qualified" || l.stage === "appt_set" || l.stage === "won") ? [l.product] : [],
        interestLevel: l.stage === "won" ? "hot" : l.stage === "qualified" || l.stage === "appt_set" ? "warm" : "cold",
        actor: rep?.name ?? "Unassigned",
        occurredAt: daysAgo(intBetween(1, 38) + (l.attempts - a) * 3),
        notes: "",
      });
    }
  }
  // funnel activities mirrored into the timeline
  for (const fe of funnelEvents) {
    activities.push({
      id: `act_${actId++}`,
      providerId: fe.providerId,
      leadId: null,
      type: "funnel",
      channel: fe.surface,
      attemptNumber: null,
      disposition: null,
      productInterest: [],
      interestLevel: "none",
      actor: "Provider Master Data",
      occurredAt: fe.occurredAt,
      notes: fe.stuckStep ? `Stuck at: ${fe.stuckStep}` : "",
    });
  }

  // ----- Segments -----
  const stuckCount = funnelEvents.filter((f) => f.eventType === "stuck_mid_funnel").length;
  const fundedNoLoan = (() => {
    const funded = new Set(funnelEvents.filter((f) => f.eventType === "account_funded").map((f) => f.providerId));
    const originated = new Set(funnelEvents.filter((f) => f.eventType === "loan_originated").map((f) => f.providerId));
    return [...funded].filter((id) => !originated.has(id)).length;
  })();
  const startedNotCompleted = (() => {
    const started = new Set(funnelEvents.filter((f) => f.eventType === "signup_started").map((f) => f.providerId));
    const completed = new Set(funnelEvents.filter((f) => f.eventType === "completed_signup").map((f) => f.providerId));
    return [...started].filter((id) => !completed.has(id)).length;
  })();
  const segments: Segment[] = [
    { id: "seg_stuck7", name: "Stuck mid-funnel > 7 days", funnelStage: "stuck_mid_funnel", filters: { minDays: 7 }, size: Math.round(stuckCount * 0.7) },
    { id: "seg_started", name: "Signup started, not completed", funnelStage: "signup_started", filters: {}, size: startedNotCompleted },
    { id: "seg_funded_noloan", name: "Account funded, no loan originated", funnelStage: "account_funded", filters: {}, size: fundedNoLoan },
    { id: "seg_soleprac", name: "Sole Practitioners, PWC eligible", funnelStage: "any", filters: { persona: "Sole Practitioner" }, size: providers.filter((p) => p.persona === "Sole Practitioner" && p.pwcStatus === "eligible").length },
  ];

  // ----- Campaigns -----
  const campaigns: Campaign[] = [
    {
      id: "camp_1",
      name: "Mid-funnel recovery — Savana KYC drop-off",
      status: "active",
      segmentName: "Stuck mid-funnel > 7 days",
      connector: "Marketo",
      journeySteps: [
        { day: 0, channel: "email", template: "Recovery: finish opening your account" },
        { day: 3, channel: "email", template: "Recovery: what you need to complete KYC" },
        { day: 7, channel: "sms", template: "Reminder: your account is almost ready" },
      ],
      audienceSize: Math.round(stuckCount * 0.7),
      metrics: { sent: 1840, delivered: 1795, opens: 812, clicks: 214, conversions: 63 },
      createdByRole: "Campaign Management",
      launchedAt: daysAgo(12),
    },
    {
      id: "camp_2",
      name: "Funded, no loan — Term Loan bundle offer",
      status: "active",
      segmentName: "Account funded, no loan originated",
      connector: "Marketo",
      journeySteps: [
        { day: 0, channel: "email", template: "You could save 0.25% APR on a term loan" },
        { day: 5, channel: "email", template: "How the bank + loan bundle works" },
      ],
      audienceSize: fundedNoLoan,
      metrics: { sent: 640, delivered: 631, opens: 349, clicks: 118, conversions: 41 },
      createdByRole: "Campaign Management",
      launchedAt: daysAgo(20),
    },
    {
      id: "camp_3",
      name: "Sole Practitioner nurture — 3% intro APY",
      status: "paused",
      segmentName: "Sole Practitioners, PWC eligible",
      connector: "Customer.io",
      journeySteps: [{ day: 0, channel: "email", template: "Settle Optum Pay payments same-day for FREE" }],
      audienceSize: segments[3].size,
      metrics: { sent: 0, delivered: 0, opens: 0, clicks: 0, conversions: 0 },
      createdByRole: "Campaign Management",
      launchedAt: null,
    },
  ];

  // ----- Appointments -----
  const appointments: Appointment[] = [];
  const apptLeads = leads.filter((l) => l.stage === "appt_set");
  apptLeads.slice(0, 40).forEach((l, i) => {
    const senior = pick(repsByTier("senior"));
    appointments.push({
      id: `appt_${i + 1}`,
      providerId: l.providerId,
      leadId: l.id,
      repId: senior.id,
      scheduledFor: daysAhead(intBetween(1, 14)),
      type: pick(["discovery", "product_demo", "closing"] as const),
      status: "scheduled",
      createdBy: pick(repsByTier("junior")).name,
    });
  });

  // ----- Connectors -----
  const connectors: Connector[] = [
    { id: "conn_marketo", name: "Marketo", kind: "esp", status: "connected_mock", isApprovedVendor: true, note: "Approved vendor. Existing contract; a second instance can be provisioned for CRM-triggered journeys." },
    { id: "conn_cio", name: "Customer.io", kind: "esp", status: "not_approved", isApprovedVendor: false, note: "Known platform, strong fit. Pending procurement approval (4-6 month cycle)." },
  ];

  // ----- Data sources -----
  const dataSources: DataSource[] = [
    { id: "ds_pmds", name: "Provider Master Data Set (warehouse)", kind: "warehouse", status: "mock", lastSync: daysAgo(0), recordCount: 1_028_400, note: "Source of funnel events (signup_started … loan_originated). This CRM is the missing front end." },
    { id: "ds_bankfile", name: "Monthly Bank Offer File (PWC)", kind: "sftp_file", status: "mock", lastSync: daysAgo(43), recordCount: HEADLINE_ROW_COUNT, note: "~160K pre-qualified PWC offers received 7th-10th of each month. Consumed by the Ingest Wizard." },
    { id: "ds_fdm", name: "Third-Party FDM Data", kind: "vendor_api", status: "mock", lastSync: daysAgo(5), recordCount: 2_400_000, note: "Purchased financial-decision-maker records, matched by TIN to lift FDM coverage." },
    { id: "ds_sfgo", name: "Salesforce Go (commission)", kind: "downstream", status: "mock", lastSync: daysAgo(1), recordCount: 0, note: "Read-only, end-of-line commission calculation. Not the CRM; receives closed-won deals only." },
  ];

  // ----- Source file (the July ingest, pre-commit) -----
  const matchedPct = 0.84;
  const matched = Math.round(HEADLINE_ROW_COUNT * matchedPct);
  const newProv = Math.round(HEADLINE_ROW_COUNT * 0.11);
  const dup = Math.round(HEADLINE_ROW_COUNT * 0.02);
  const unmatched = HEADLINE_ROW_COUNT - matched - newProv - dup;
  const fdmBefore = Math.round(HEADLINE_ROW_COUNT * 0.4);
  const fdmAfter = Math.round(HEADLINE_ROW_COUNT * 0.86);
  const sourceFiles: SourceFile[] = [
    {
      id: "file_jul2026",
      filename: "PWC_Qualified_Offers_2026-07.csv",
      offerMonth: "2026-07",
      rowCount: HEADLINE_ROW_COUNT,
      totalOfferedAmount: Math.round(HEADLINE_ROW_COUNT * 78_000),
      matchStats: { matched, newProviders: newProv, unmatched, duplicates: dup },
      fdmStats: {
        before: fdmBefore,
        after: fdmAfter,
        high: Math.round((fdmAfter - fdmBefore) * 0.52),
        med: Math.round((fdmAfter - fdmBefore) * 0.31),
        low: Math.round((fdmAfter - fdmBefore) * 0.17),
      },
      committedAt: null,
    },
  ];

  // ----- Goals (per sales specialist and per product line) -----
  const PERIOD = "Q3 2026";
  const goals: Goal[] = [];
  // Product-line goals: quarterly originated / booked volume targets.
  const productTargets: Record<Product, [number, number]> = {
    // [targetRevenue, targetDeals]
    pwc: [42_000_000, 520],
    term_loan: [28_000_000, 260],
    bank_account: [9_000_000, 900],
    loc: [6_500_000, 90],
    equipment: [4_200_000, 70],
    cash_acceleration: [11_000_000, 340],
  };
  for (const prod of PRODUCTS) {
    const [tRev, tDeals] = productTargets[prod];
    const factor = between(0.52, 1.12);
    goals.push({
      id: `goal_prod_${prod}`,
      scope: "product",
      refId: prod,
      refLabel: PRODUCT_LABEL[prod],
      period: PERIOD,
      targetRevenue: tRev,
      attainedRevenue: Math.round((tRev * factor) / 1000) * 1000,
      targetDeals: tDeals,
      attainedDeals: Math.round(tDeals * factor),
    });
  }
  // Specialist goals: quarterly targets scaled by seniority.
  const seniorityTarget: Record<Tier, [number, number]> = {
    senior: [5_200_000, 46],
    mid: [2_400_000, 62],
    junior: [900_000, 88],
  };
  for (const rp of reps) {
    const [tRev, tDeals] = seniorityTarget[rp.seniority];
    const factor = between(0.44, 1.24);
    goals.push({
      id: `goal_spec_${rp.id}`,
      scope: "specialist",
      refId: rp.id,
      refLabel: rp.name,
      period: PERIOD,
      targetRevenue: tRev,
      attainedRevenue: Math.round((tRev * factor) / 1000) * 1000,
      targetDeals: tDeals,
      attainedDeals: Math.round(tDeals * factor),
    });
  }

  return {
    providers,
    contacts,
    leads,
    reps,
    activities,
    funnelEvents,
    segments,
    campaigns,
    appointments,
    connectors,
    dataSources,
    sourceFiles,
    goals,
  };
}

export { PERSONAS, PRODUCTS, STAGES, TEAMS, HEADLINE_ROW_COUNT };
