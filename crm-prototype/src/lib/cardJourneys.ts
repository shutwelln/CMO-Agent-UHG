import { nanoid } from "nanoid";
import type { CampaignTrigger, EmailVariant, Journey, JourneyNode } from "../data/schema";

/*
 * Provider Card + LOC lifecycle journey templates. Shared by the card data seed
 * and the campaign builder's template picker so the two stay in sync. Copy
 * follows the house style: no em-dashes, no inline bold.
 */

export const CARD_MERGE_TAGS = ["{{provider.name}}", "{{card_limit}}", "{{activation_link}}"];

const nid = () => `jn_${nanoid(8)}`;

function cardVariant(subject: string, bodyHtml: string): EmailVariant {
  return {
    id: `var_${nanoid(6)}`,
    label: "A",
    weight: 100,
    subject,
    fromName: "Optum Bank",
    fromEmail: "no-reply@optumbank.com",
    replyTo: "provider-team@optumbank.com",
    preheader: "The Provider Card, drawn on your Optum Bank line of credit.",
    bodyHtml,
  };
}

function email(
  name: string,
  subject: string,
  bodyHtml: string,
  sendClass: "transactional" | "marketing"
): JourneyNode {
  return { id: nid(), type: "email", name, abTest: false, sendClass, variants: [cardVariant(subject, bodyHtml)] };
}

function delay(value: number, unit: "minutes" | "hours" | "days"): JourneyNode {
  return { id: nid(), type: "delay", delayValue: value, delayUnit: unit };
}

function condition(
  conditionKind: NonNullable<JourneyNode["conditionKind"]>,
  conditionLabel: string,
  yes: JourneyNode[],
  no: JourneyNode[]
): JourneyNode {
  return { id: nid(), type: "condition", conditionKind, conditionLabel, yes, no };
}

const exit = (): JourneyNode => ({ id: nid(), type: "exit" });

/* ---------- the five card lifecycle templates ---------- */

export function cardAcquisitionJourney(): Journey {
  return {
    nodes: [
      email(
        "Card offer: put your line of credit to work",
        "{{provider.name}}, add a Provider Card to your line of credit",
        "<p>Hi {{provider.name}},</p><p>Your Optum Bank line of credit can now carry a Provider Card for your staff, with a limit up to {{card_limit}}. Controlled spend, one statement, and it draws on credit you already have.</p><p><a href=\"https://optumbank.com/providers/card\">See your card offer</a></p>",
        "marketing"
      ),
      delay(4, "days"),
      condition("clicked", "If viewed the card offer", [
        email(
          "Warm follow-up: apply in minutes",
          "Ready to add your Provider Card?",
          "<p>Applying takes a few minutes and uses the line of credit you already hold.</p>",
          "marketing"
        ),
      ], [
        email(
          "Reminder: your card offer is waiting",
          "Your Provider Card offer is still open",
          "<p>Your practice is pre-qualified for a Provider Card up to {{card_limit}}.</p>",
          "marketing"
        ),
      ]),
      exit(),
    ],
    goal: "card_activated",
  };
}

export function cardOnboardingActivationJourney(): Journey {
  return {
    nodes: [
      email(
        "Activate your Provider Card",
        "Activate your Provider Card to start spending",
        "<p>Hi {{provider.name}},</p><p>Your Provider Card is approved with a limit of {{card_limit}}. Activate it to begin using it for practice spend.</p><p><a href=\"{{activation_link}}\">Activate now</a></p>",
        "transactional"
      ),
      delay(2, "days"),
      condition("event", "If activated the card", [
        exit(),
      ], [
        email(
          "Quick nudge: your card is ready to activate",
          "One step left to use your Provider Card",
          "<p>Your card is issued and waiting. Activation takes under a minute.</p><p><a href=\"{{activation_link}}\">Activate your card</a></p>",
          "transactional"
        ),
      ]),
      exit(),
    ],
    goal: "card_first_spend",
  };
}

export function cardFirstSpendJourney(): Journey {
  return {
    nodes: [
      email(
        "First-spend incentive",
        "Make your first purchase, earn a statement credit",
        "<p>Hi {{provider.name}},</p><p>Use your Provider Card for its first purchase this month and earn a statement credit. Supplies, software, or any practice expense counts.</p>",
        "marketing"
      ),
      delay(5, "days"),
      email(
        "Reminder: your first-spend credit is waiting",
        "Your first-spend credit expires soon",
        "<p>There is still time to earn your statement credit on your first Provider Card purchase.</p>",
        "marketing"
      ),
      exit(),
    ],
    goal: "card_first_spend",
  };
}

export function cardSpendGrowthJourney(): Journey {
  return {
    nodes: [
      email(
        "Grow with your Provider Card",
        "Three ways practices use the Provider Card",
        "<p>Hi {{provider.name}},</p><p>Move recurring vendor payments, staff purchases, and software subscriptions onto your Provider Card to consolidate spend and keep working capital available.</p>",
        "marketing"
      ),
      delay(7, "days"),
      email(
        "Add cards for your staff",
        "Give your team controlled spend",
        "<p>Issue additional cards with per-card limits so your staff can buy what they need without sharing one card.</p>",
        "marketing"
      ),
      exit(),
    ],
  };
}

export function cardDormantReactivationJourney(): Journey {
  return {
    nodes: [
      email(
        "We miss your spend",
        "Your Provider Card is ready when you are",
        "<p>Hi {{provider.name}},</p><p>Your Provider Card has been quiet lately. Your line of credit and limit of {{card_limit}} are still available whenever you need them.</p>",
        "marketing"
      ),
      delay(6, "days"),
      email(
        "A reason to come back",
        "Earn a credit on your next card purchase",
        "<p>Use your Provider Card this month and earn a statement credit.</p>",
        "marketing"
      ),
      exit(),
    ],
  };
}

/* Flatten a journey into the stored {day, channel, template} step list (pure,
 * mirrors JourneyBuilder.journeySteps without pulling in the React builder). */
export function journeyToSteps(journey: Journey): { day: number; channel: string; template: string }[] {
  const steps: { day: number; channel: string; template: string }[] = [];
  let day = 0;
  const unitDays = (n: JourneyNode) => {
    const v = n.delayValue ?? 1;
    if (n.delayUnit === "hours") return v / 24;
    if (n.delayUnit === "minutes") return v / (24 * 60);
    return v;
  };
  const walk = (nodes: JourneyNode[]) => {
    for (const n of nodes) {
      if (n.type === "delay") day += Math.round(unitDays(n));
      else if (n.type === "email")
        steps.push({ day, channel: "email", template: n.name?.trim() || n.variants?.[0]?.subject || "Email" });
      else if (n.type === "condition") walk(n.yes ?? []);
      else if (n.type === "split") walk(n.branchA ?? []);
    }
  };
  walk(journey.nodes);
  return steps;
}

export interface CardTemplate {
  key: string;
  label: string;
  stage: string;
  description: string;
  trigger: CampaignTrigger;
  build: () => Journey;
}

export const CARD_TEMPLATES: CardTemplate[] = [
  {
    key: "acquisition",
    label: "Acquisition / cross-sell",
    stage: "Awareness / Acquisition",
    description: "Offer the Provider Card to line-of-credit holders who do not have a card yet.",
    trigger: { type: "segment" },
    build: cardAcquisitionJourney,
  },
  {
    key: "onboarding_activation",
    label: "Onboarding & activation (EMOB)",
    stage: "Onboarding / Activation",
    description: "Drive activation in the early month on book after the card is approved.",
    trigger: { type: "event", event: "card_approved" },
    build: cardOnboardingActivationJourney,
  },
  {
    key: "first_spend",
    label: "First-spend incentive",
    stage: "Spend",
    description: "Move newly activated cardholders to their first purchase.",
    trigger: { type: "event", event: "card_activated" },
    build: cardFirstSpendJourney,
  },
  {
    key: "spend_growth",
    label: "Spend / utilization growth",
    stage: "Growth",
    description: "Grow utilization among active cardholders and add staff cards.",
    trigger: { type: "segment" },
    build: cardSpendGrowthJourney,
  },
  {
    key: "dormant_reactivation",
    label: "Dormant reactivation",
    stage: "Growth",
    description: "Win back cardholders who have gone quiet.",
    trigger: { type: "event", event: "card_dormant" },
    build: cardDormantReactivationJourney,
  },
];
