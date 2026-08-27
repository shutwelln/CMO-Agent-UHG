import { nanoid } from "nanoid";
import type { EmailBlock, EmailBlockType } from "../data/schema";

/*
 * Content-block model for the broadcast (newsletter / one-off) email builder.
 * Blocks are ordered top-to-bottom and rendered to a simple inline-styled
 * HTML email. Merge tags resolve per recipient at send time.
 */

export const MERGE_TAGS = ["{{provider.name}}", "{{provider.dba}}", "{{first_offer}}"];

const SAMPLE_IMAGE =
  "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=1200&q=70";

export function makeBlock(type: EmailBlockType): EmailBlock {
  const base: EmailBlock = { id: `blk_${nanoid(6)}`, type, align: "left" };
  switch (type) {
    case "heading":
      return { ...base, text: "A new heading", align: "left" };
    case "text":
      return {
        ...base,
        html: "<p>Write your message here. Personalize it with {{provider.name}}.</p>",
      };
    case "image":
      return { ...base, src: SAMPLE_IMAGE, alt: "Banner image", align: "center" };
    case "button":
      return {
        ...base,
        text: "See your offer",
        href: "https://optumbank.com/providers",
        align: "center",
      };
    case "spacer":
      return { ...base, height: 24 };
    case "divider":
    default:
      return base;
  }
}

/* A populated starter newsletter so the builder opens with something real. */
export function defaultBroadcastBlocks(): EmailBlock[] {
  return [
    { id: `blk_${nanoid(6)}`, type: "image", src: SAMPLE_IMAGE, alt: "Optum Bank", align: "center" },
    { id: `blk_${nanoid(6)}`, type: "heading", text: "Banking built around how you get paid", align: "left" },
    {
      id: `blk_${nanoid(6)}`,
      type: "text",
      align: "left",
      html:
        "<p>Hi {{provider.name}},</p><p>Your practice already runs on Optum Pay. An Optum Bank " +
        "operating account settles those payments faster, with no monthly fee, and puts working " +
        "capital within reach when you need it.</p>",
    },
    { id: `blk_${nanoid(6)}`, type: "button", text: "See your offer", href: "https://optumbank.com/providers", align: "center" },
    { id: `blk_${nanoid(6)}`, type: "divider", align: "left" },
    {
      id: `blk_${nanoid(6)}`,
      type: "text",
      align: "left",
      html: "<p style=\"color:#6b7280;font-size:13px\">You are receiving this because your practice is enrolled with Optum. Manage preferences or unsubscribe below.</p>",
    },
  ];
}

const alignStyle = (a?: EmailBlock["align"]) => `text-align:${a ?? "left"}`;

/* Render blocks to a self-contained, inline-styled HTML email body. */
export function renderBlocksToHtml(blocks: EmailBlock[]): string {
  const parts = blocks.map((b) => {
    switch (b.type) {
      case "heading":
        return `<h1 style="${alignStyle(b.align)};font-size:22px;line-height:1.3;color:#0b1f3a;margin:0 0 12px;font-weight:800">${b.text ?? ""}</h1>`;
      case "text":
        return `<div style="${alignStyle(b.align)};font-size:15px;line-height:1.6;color:#1f2937;margin:0 0 14px">${b.html ?? ""}</div>`;
      case "image":
        return `<div style="${alignStyle(b.align)};margin:0 0 14px"><img src="${b.src ?? ""}" alt="${b.alt ?? ""}" style="max-width:100%;border-radius:10px;display:inline-block"/></div>`;
      case "button": {
        const wrap = b.align ?? "center";
        return `<div style="text-align:${wrap};margin:6px 0 18px"><a href="${b.href ?? "#"}" style="display:inline-block;background:#ff6a13;color:#fff;text-decoration:none;font-weight:700;font-size:15px;padding:12px 26px;border-radius:9px">${b.text ?? "Button"}</a></div>`;
      }
      case "divider":
        return `<hr style="border:none;border-top:1px solid #e5e7eb;margin:18px 0"/>`;
      case "spacer":
        return `<div style="height:${b.height ?? 24}px"></div>`;
      default:
        return "";
    }
  });
  return parts.join("\n");
}

/* Count the "content" blocks (excludes structural spacers/dividers). */
export function contentBlockCount(blocks: EmailBlock[]): number {
  return blocks.filter((b) => b.type !== "spacer" && b.type !== "divider").length;
}
