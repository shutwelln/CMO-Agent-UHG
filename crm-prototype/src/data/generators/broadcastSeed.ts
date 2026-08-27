import { nanoid } from "nanoid";
import type { Broadcast, Dataset, EmailBlock } from "../schema";
import { defaultBroadcastBlocks } from "../../lib/emailBlocks";

/*
 * Seeds a handful of realistic broadcasts (one sent, one scheduled, one draft)
 * so the Broadcasts surface opens populated. Seeded in-app so the shipped
 * dataset.json stays back-compatible.
 */

function newsletterBlocks(headline: string, body: string): EmailBlock[] {
  return [
    { id: `blk_${nanoid(6)}`, type: "heading", text: headline, align: "left" },
    { id: `blk_${nanoid(6)}`, type: "text", align: "left", html: `<p>${body}</p>` },
    {
      id: `blk_${nanoid(6)}`,
      type: "button",
      text: "See your offer",
      href: "https://optumbank.com/providers",
      align: "center",
    },
  ];
}

export function seedBroadcasts(data: Dataset): Broadcast[] {
  const seg = (id: string) => data.segments.find((s) => s.id === id);
  const funded = seg("seg_funded_noloan");
  const sole = seg("seg_soleprac");

  const common = {
    fromName: "Optum Bank",
    fromEmail: "no-reply@optumbank.com",
    replyTo: "provider-team@optumbank.com",
    connector: "Marketo" as const,
  };

  return [
    {
      id: `bcast_${nanoid(6)}`,
      name: "August provider newsletter",
      status: "sent",
      subject: "Your August banking update from Optum Bank",
      preheader: "Faster settlement, new working-capital limits, and a fee change.",
      ...common,
      blocks: defaultBroadcastBlocks(),
      audience: {
        kind: "segment",
        segmentId: funded?.id,
        segmentName: funded?.name ?? "Account funded, no loan originated",
      },
      audienceSize: funded?.size ?? 4200,
      schedule: { mode: "now" },
      metrics: {
        sent: funded?.size ?? 4200,
        delivered: Math.round((funded?.size ?? 4200) * 0.981),
        opens: Math.round((funded?.size ?? 4200) * 0.412),
        clicks: Math.round((funded?.size ?? 4200) * 0.086),
        unsubscribes: Math.round((funded?.size ?? 4200) * 0.004),
      },
      createdByRole: "Campaign Management",
      sentAt: "2026-08-14T15:00:00.000Z",
      scheduledFor: null,
    },
    {
      id: `bcast_${nanoid(6)}`,
      name: "Same-day settlement announcement",
      status: "scheduled",
      subject: "New: settle Optum Pay payments same-day",
      preheader: "A change to how quickly you get your money.",
      ...common,
      blocks: newsletterBlocks(
        "Your payments now settle same-day",
        "Starting this month, Optum Bank operating accounts settle Optum Pay payments on the same business day, at no additional cost. Nothing to enable, {{provider.name}} — it is already on for your account."
      ),
      audience: {
        kind: "segment",
        segmentId: sole?.id,
        segmentName: sole?.name ?? "Sole Practitioners, PWC eligible",
      },
      audienceSize: sole?.size ?? 2600,
      schedule: { mode: "scheduled", sendAt: "2026-08-29T14:00:00.000Z" },
      metrics: { sent: 0, delivered: 0, opens: 0, clicks: 0, unsubscribes: 0 },
      createdByRole: "Campaign Management",
      sentAt: null,
      scheduledFor: "2026-08-29T14:00:00.000Z",
    },
    {
      id: `bcast_${nanoid(6)}`,
      name: "Conference follow-up list",
      status: "draft",
      subject: "Great meeting you at the conference",
      preheader: "Here is the offer we discussed.",
      ...common,
      blocks: newsletterBlocks(
        "Thanks for stopping by our booth",
        "It was great talking through how {{provider.dba}} handles payments. Here is the operating-account offer we discussed, ready when you are."
      ),
      audience: {
        kind: "upload",
        listName: "conference_attendees_aug2026.csv",
        uploadedCount: 318,
        matchedCount: 291,
      },
      audienceSize: 291,
      schedule: { mode: "now" },
      metrics: { sent: 0, delivered: 0, opens: 0, clicks: 0, unsubscribes: 0 },
      createdByRole: "Campaign Management",
      sentAt: null,
      scheduledFor: null,
    },
  ];
}
