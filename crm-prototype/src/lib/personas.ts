import type { Persona } from "../data/schema";

/*
 * The seven canonical provider personas from the GTM strategic intent log.
 * Winning lever, moment-that-matters, and positioning hook drive next-best-offer
 * rationale and persona-matched campaign copy.
 */
export interface PersonaDetail {
  persona: Persona;
  blurb: string;
  winningLever: string;
  moment: string;
  hook: string;
  specialties: string[];
}

export const PERSONA_DETAIL: Record<Persona, PersonaDetail> = {
  "Sole Practitioner": {
    persona: "Sole Practitioner",
    blurb: "Owner is the clinician. Minimal finance staff. More cash-flow-anxious than growth-minded.",
    winningLever: "Education and payment reconciliation; stop surprises",
    moment: "Payment delays and confusing remittances",
    hook: "The easiest way to know when claim payments have settled.",
    specialties: ["Family Medicine", "Chiropractic", "Optometry", "Dentistry", "Behavioral Health"],
  },
  "Growing Group": {
    persona: "Growing Group",
    blurb: "Actively expanding. Needs operationalization and automation to scale. Wants metric visibility.",
    winningLever: "Provider analytics and AP automation",
    moment: "Month-close and cash-flow predictability",
    hook: "Real visibility into cash flow as you grow.",
    specialties: ["Dermatology", "Orthopedics", "Physical Therapy", "Urgent Care", "Pediatrics"],
  },
  "High Volume Specialty": {
    persona: "High Volume Specialty",
    blurb: "Labs, imaging, infusion. Complex claims with frequent reconciliation and disputes.",
    winningLever: "Reconciliation and dispute workflow; settlement data",
    moment: "High-volume payer issues and payment variances",
    hook: "Fewer missing dollars, faster resolutions.",
    specialties: ["Diagnostic Lab", "Radiology / Imaging", "Infusion Center", "Pathology", "Cardiology"],
  },
  "Digital-First": {
    persona: "Digital-First",
    blurb: "Integrated-systems mindset. Expects real-time dashboards. Tied to fintech more than legacy banking.",
    winningLever: "Smart analytics; modern infrastructure",
    moment: "Onboarding, scaling, tech upgrades",
    hook: "Built for modern healthcare finance.",
    specialties: ["Telehealth", "Med Spa", "Digital Primary Care", "Concierge Medicine"],
  },
  "Multi-Specialty Group": {
    persona: "Multi-Specialty Group",
    blurb: "Finance-directed. Standardization across locations. Wants integrated systems and role-based access.",
    winningLever: "Standard-practice content; identity management (OHID)",
    moment: "Onboarding a new location; acquisition integration",
    hook: "The standardized settlement account tied to your verified OHID.",
    specialties: ["Multi-Specialty Clinic", "Ambulatory Surgery", "Womens Health Group", "ENT Group"],
  },
  "Hospital-affiliated": {
    persona: "Hospital-affiliated",
    blurb: "Constrained by hospital-led decisions. Change-fatigued. Not driven by marketing bells and whistles.",
    winningLever: "Standard-practice alignment; smart analytics",
    moment: "Network changes; contract renewals; compliance audits",
    hook: "Designed for healthcare-specific settlement requirements.",
    specialties: ["Affiliated Cardiology", "Affiliated Oncology", "Hospitalist Group", "Affiliated Surgery"],
  },
  "PE-backed Group": {
    persona: "PE-backed Group",
    blurb: "CFO- and valuation-driven. Visibility into metrics and risk mitigation are key.",
    winningLever: "Smart analytics across locations; compliance enablement",
    moment: "Valuation, diligence, quarterly board reporting",
    hook: "A clear, centralized view of healthcare cash across entities.",
    specialties: ["DSO (Dental)", "Vet Group", "Dermatology Platform", "Ophthalmology Platform", "GI Platform"],
  },
};

export const PERSONA_LIST = Object.values(PERSONA_DETAIL);
