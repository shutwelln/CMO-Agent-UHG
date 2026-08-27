import type { OfferLead, Provider } from "../data/schema";
import type { Offer } from "./nbo";
import { money } from "./format";

/*
 * Draft-assist for outbound provider email. Stands in for the model-backed
 * drafting the production console would call: it composes a subject and body
 * personalized to the provider, the financial decision maker, the live offer,
 * and the next-best-offer. `variant` cycles alternate angles on "Regenerate".
 * Copy follows the house style: no em-dashes, no inline bold.
 */

export interface DraftInput {
  provider: Provider;
  lead: OfferLead;
  fdmName?: string;
  nbo?: Offer;
  fromName: string; // sender display name used in the signature
}

export interface EmailDraft {
  subject: string;
  body: string;
}

const firstName = (full?: string) => (full ? full.split(/\s+/)[0] : "there");

const practiceName = (p: Provider) =>
  p.dba && p.dba !== p.legalName ? p.dba : p.legalName;

export const VARIANT_LABELS = ["Cash-flow angle", "Working-capital angle", "Concise intro"];
export const VARIANT_COUNT = VARIANT_LABELS.length;

export function draftProviderEmail(input: DraftInput, variant = 0): EmailDraft {
  const { provider, lead, fdmName, nbo, fromName } = input;
  const name = practiceName(provider);
  const hi = firstName(fdmName);
  const vol = money(provider.monthlyOptumPayVolume, true);
  const offer = money(lead.offerAmount);
  const sig = `${fromName}\nOptum Banking Solutions`;

  const nboLine = nbo
    ? `${nbo.headline}. ${nbo.detail}`
    : "There is also a faster way to get paid on your existing Optum Pay claims.";
  const incentiveLine = nbo?.incentive ? `The current incentive: ${nbo.incentive}.` : "";

  const v = ((variant % VARIANT_COUNT) + VARIANT_COUNT) % VARIANT_COUNT;

  if (v === 1) {
    // Working-capital / lending-led angle
    return {
      subject: `${offer} in working capital for ${name}`,
      body: [
        `Hi ${hi},`,
        "",
        `${name} is pre-qualified for up to ${offer} in working capital through Optum Bank, sized to the ${vol}/month in Optum Pay volume already running through your practice.`,
        "",
        `${nboLine} ${incentiveLine}`.trim(),
        "",
        "Because it is built on claims you already generate, funding is fast and there is no monthly account fee. Would a short call this week work to walk through the terms?",
        "",
        "Best,",
        sig,
      ].join("\n"),
    };
  }

  if (v === 2) {
    // Concise intro
    return {
      subject: `Quick note for ${name}`,
      body: [
        `Hi ${hi},`,
        "",
        `I lead Optum Banking Solutions for practices like ${name}. You are pre-qualified for up to ${offer}, and I think there is a clean fit with how you already get paid.`,
        "",
        `${nboLine}`,
        "",
        "Open to 15 minutes this week?",
        "",
        "Best,",
        sig,
      ].join("\n"),
    };
  }

  // Default: cash-flow angle
  return {
    subject: `${hi}, a faster way to get paid at ${name}`,
    body: [
      `Hi ${hi},`,
      "",
      `I work with ${provider.persona.toLowerCase()} practices like ${name} on the banking side of Optum. With ${vol} a month in Optum Pay volume, you are leaving cash-flow timing on the table, and you are already pre-qualified for up to ${offer} in working capital.`,
      "",
      `${nboLine} ${incentiveLine}`.trim(),
      "",
      "Nothing changes about how you deliver care. It just moves your money sooner and lowers what you pay to get it. Could we grab 15 minutes this week?",
      "",
      "Best,",
      sig,
    ].join("\n"),
  };
}
