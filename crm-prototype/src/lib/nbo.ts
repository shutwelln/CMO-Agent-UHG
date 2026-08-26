import type { Provider, Product } from "../data/schema";
import { PRODUCT_LABEL } from "../data/schema";
import { PERSONA_DETAIL } from "./personas";

/*
 * Next-Best-Offer engine. Deterministic, rules-based, and transparent by design
 * (the demo shows the rationale). Rules echo the strategic intent log:
 * lending-led entry, bank-account-as-AND cross-sell attached via NPx redirection,
 * Cash Acceleration tied to opening a bank account, bundle incentives.
 */

export interface Offer {
  product: Product;
  headline: string;
  detail: string;
  rationale: string;
  incentive: string | null;
  score: number;
}

export function nextBestOffers(p: Provider): Offer[] {
  const held = new Set(p.productsHeld);
  const persona = PERSONA_DETAIL[p.persona];
  const offers: Offer[] = [];
  const highVolume = p.monthlyOptumPayVolume >= 120_000;

  // Cash Acceleration: strongest when they have UHC claim flows but no bank account
  if (!held.has("cash_acceleration") && p.npxEnrolled) {
    offers.push({
      product: "cash_acceleration",
      headline: "Accelerate claims payments ~20 days earlier",
      detail: "~50 bps fee. Requires opening an Optum Bank account and redirecting claims flows.",
      rationale: `${p.persona} at their moment-that-matters (${persona.moment.toLowerCase()}). Cash Acceleration solves cash-flow timing, powered by UHC claims visibility.`,
      incentive: "~50 bps for payment ~20 days early",
      score: highVolume ? 96 : 88,
    });
  }

  // Bundle: term loan + bank account for APR reduction (lending-led entry)
  if (!held.has("term_loan")) {
    offers.push({
      product: "term_loan",
      headline: "Term Loan + Bank Account bundle",
      detail: "0.25% APR reduction when the Optum Bank account is opened alongside the loan.",
      rationale: `Lending-led entry for ${p.persona}. Attach the bank account as the AND-account via the bundle incentive.`,
      incentive: "0.25% APR reduction",
      score: 90,
    });
  }

  // NPx fee reduction for redirecting payments into the bank account
  if (!held.has("bank_account") && p.npxEnrolled && !p.hasOptumBankAccount) {
    offers.push({
      product: "bank_account",
      headline: "Open the operating account, cut NPx fees",
      detail: "NPx payment fee drops from 1.49% to 0.49% when claims flows redirect into the account.",
      rationale: `${p.persona} value pillar: improved cash flow and cost savings. Redirect existing Optum Pay / NPx flows.`,
      incentive: "NPx fee 1.49% → 0.49%",
      score: highVolume ? 84 : 74,
    });
  }

  // Line of credit for growing / multi-location groups
  if (!held.has("loc") && (p.persona === "Growing Group" || p.persona === "Multi-Specialty Group" || p.persona === "PE-backed Group")) {
    offers.push({
      product: "loc",
      headline: "Line of Credit for working-capital flexibility",
      detail: "Revolving credit sized to claims volume; cards attach to the line.",
      rationale: `${p.persona} scaling across locations. LOC smooths month-close and expansion spend.`,
      incentive: null,
      score: 68,
    });
  }

  // Equipment financing for specialties that buy equipment
  if (!held.has("equipment") && (p.persona === "High Volume Specialty" || p.persona === "Digital-First")) {
    offers.push({
      product: "equipment",
      headline: "Equipment Financing",
      detail: "Finance imaging, lab, or practice equipment against claims flows.",
      rationale: `${p.specialty} typically has recurring equipment needs. Post-MVP flavor via existing supplier relationships.`,
      incentive: null,
      score: 58,
    });
  }

  return offers.sort((a, b) => b.score - a.score).slice(0, 4);
}

export function topOfferLabel(p: Provider): string {
  const o = nextBestOffers(p)[0];
  return o ? PRODUCT_LABEL[o.product] : "—";
}
