import { useRef, useState } from "react";
import { nanoid } from "nanoid";
import {
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Heading2,
  List,
  Link as LinkIcon,
  Tag,
} from "lucide-react";
import { Button, Field } from "../../components/ui";
import type { EmailVariant, JourneyNode } from "../../data/schema";

interface Props {
  node: JourneyNode;
  onChange: (node: JourneyNode) => void;
  onClose: () => void;
}

/* A plausible default email variant, mirrored by JourneyBuilder's email helper. */
export function defaultVariant(label: string, weight: number): EmailVariant {
  return {
    id: `var_${nanoid(6)}`,
    label,
    weight,
    subject: "Your Optum Bank offer is ready",
    fromName: "Optum Bank",
    fromEmail: "no-reply@optumbank.com",
    replyTo: "provider-team@optumbank.com",
    preheader: "A banking offer built around how you already get paid.",
    bodyHtml:
      "<p>Hi {{provider.name}},</p>" +
      "<p>You are pre-qualified for {{first_offer}}. Open your Optum Bank operating account " +
      "and settle Optum Pay payments faster, with no monthly fee.</p>" +
      "<p><a href=\"https://optumbank.com/providers\">See your offer</a></p>" +
      "<p>The Optum Bank provider team</p>",
  };
}

const MERGE_TAGS = ["{{provider.name}}", "{{first_offer}}", "{{card_limit}}", "{{activation_link}}"];

export function EmailEditor({ node, onChange, onClose }: Props) {
  const variants: EmailVariant[] =
    node.variants && node.variants.length > 0
      ? node.variants
      : [defaultVariant("A", 100)];
  const abOn = !!node.abTest;
  const [activeIdx, setActiveIdx] = useState(0);
  const [mode, setMode] = useState<"rich" | "html">("rich");
  const areaRef = useRef<HTMLDivElement | null>(null);

  const active = variants[Math.min(activeIdx, variants.length - 1)];

  const pushVariants = (next: EmailVariant[], patch?: Partial<JourneyNode>) => {
    onChange({ ...node, variants: next, ...patch });
  };

  const patchActive = (patch: Partial<EmailVariant>) => {
    const idx = Math.min(activeIdx, variants.length - 1);
    const next = variants.map((v, i) => (i === idx ? { ...v, ...patch } : v));
    pushVariants(next);
  };

  const toggleAb = (on: boolean) => {
    if (on) {
      const a = { ...variants[0], label: "A", weight: 50 };
      const b = defaultVariant("B", 50);
      pushVariants([a, b], { abTest: true });
      setActiveIdx(0);
    } else {
      const a = { ...variants[0], label: "A", weight: 100 };
      pushVariants([a], { abTest: false });
      setActiveIdx(0);
    }
  };

  const setWeight = (w: number) => {
    const clamped = Math.max(0, Math.min(100, w));
    const next = variants.map((v, i) =>
      i === 0 ? { ...v, weight: clamped } : { ...v, weight: 100 - clamped }
    );
    pushVariants(next);
  };

  const readArea = () => {
    if (areaRef.current) patchActive({ bodyHtml: areaRef.current.innerHTML });
  };

  const exec = (cmd: string, value?: string) => {
    areaRef.current?.focus();
    document.execCommand(cmd, false, value);
    readArea();
  };

  const insertTag = (tag: string) => {
    areaRef.current?.focus();
    document.execCommand("insertText", false, tag);
    readArea();
  };

  const insertLink = () => {
    const url = window.prompt("Link URL", "https://optumbank.com/providers");
    if (url) exec("createLink", url);
  };

  return (
    <div className="email-editor">
      <div className="ee-head">
        <div className="col gap-1">
          <span className="strong" style={{ fontSize: 16 }}>
            Edit email
          </span>
          <span className="tiny muted">No real messages are sent from this prototype.</span>
        </div>
        <div className="row gap-3 center">
          <label className="row gap-2 center">
            <span className="small strong">Send class</span>
            <select
              className="select"
              value={node.sendClass ?? "marketing"}
              onChange={(e) =>
                onChange({ ...node, sendClass: e.target.value as "transactional" | "marketing" })
              }
              style={{ width: 150 }}
            >
              <option value="marketing">Marketing</option>
              <option value="transactional">Transactional</option>
            </select>
          </label>
          <label className="row gap-2 center" style={{ cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={abOn}
              onChange={(e) => toggleAb(e.target.checked)}
            />
            <span className="small strong">A/B test</span>
          </label>
        </div>
      </div>

      <div className="ee-body col gap-3">
        {abOn && (
          <div className="ab-tabs">
            {variants.map((v, i) => (
              <button
                key={v.id}
                className={`tab${activeIdx === i ? " on" : ""}`}
                onClick={() => setActiveIdx(i)}
              >
                Variant {v.label}
              </button>
            ))}
          </div>
        )}

        {abOn && (
          <Field label="Variant A weight (%)">
            <input
              type="number"
              min={0}
              max={100}
              value={variants[0].weight}
              onChange={(e) => setWeight(Number(e.target.value) || 0)}
              style={{ width: 120 }}
            />
            <span className="tiny muted" style={{ marginLeft: 10 }}>
              Variant B gets {100 - variants[0].weight}%
            </span>
          </Field>
        )}

        <div className="ee-fields">
          <Field label="From name">
            <input
              className="select"
              value={active.fromName}
              onChange={(e) => patchActive({ fromName: e.target.value })}
            />
          </Field>
          <Field label="From email">
            <input
              className="select"
              value={active.fromEmail}
              onChange={(e) => patchActive({ fromEmail: e.target.value })}
            />
          </Field>
          <div className="full">
            <Field label="Reply-to (optional)">
              <input
                className="select"
                value={active.replyTo}
                onChange={(e) => patchActive({ replyTo: e.target.value })}
              />
            </Field>
          </div>
          <div className="full">
            <Field label="Subject">
              <input
                className="select"
                value={active.subject}
                onChange={(e) => patchActive({ subject: e.target.value })}
              />
            </Field>
          </div>
          <div className="full">
            <Field label="Preheader">
              <input
                className="select"
                value={active.preheader}
                onChange={(e) => patchActive({ preheader: e.target.value })}
              />
            </Field>
          </div>
        </div>

        <div className="col gap-2">
          <div className="editor-mode">
            <button
              className={`tab${mode === "rich" ? " on" : ""}`}
              onClick={() => setMode("rich")}
            >
              Rich text
            </button>
            <button
              className={`tab${mode === "html" ? " on" : ""}`}
              onClick={() => {
                readArea();
                setMode("html");
              }}
            >
              HTML
            </button>
          </div>

          {mode === "rich" ? (
            <div className="wysiwyg">
              <div className="wys-toolbar">
                <button className="wys-btn" title="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("bold")}>
                  <Bold size={15} />
                </button>
                <button className="wys-btn" title="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("italic")}>
                  <Italic size={15} />
                </button>
                <button className="wys-btn" title="Underline" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("underline")}>
                  <UnderlineIcon size={15} />
                </button>
                <span className="wys-sep" />
                <button className="wys-btn" title="Heading" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("formatBlock", "H2")}>
                  <Heading2 size={15} />
                </button>
                <button className="wys-btn" title="Bulleted list" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("insertUnorderedList")}>
                  <List size={15} />
                </button>
                <button className="wys-btn" title="Insert link" onMouseDown={(e) => e.preventDefault()} onClick={insertLink}>
                  <LinkIcon size={15} />
                </button>
                <span className="wys-sep" />
                {MERGE_TAGS.map((tag) => (
                  <button
                    key={tag}
                    className="wys-btn"
                    title={`Insert ${tag}`}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => insertTag(tag)}
                  >
                    <Tag size={13} />
                    <span className="mono tiny" style={{ marginLeft: 4 }}>
                      {tag.replace(/[{}]/g, "")}
                    </span>
                  </button>
                ))}
              </div>
              <div
                ref={areaRef}
                className="wys-area"
                contentEditable
                suppressContentEditableWarning
                onInput={readArea}
                dangerouslySetInnerHTML={{ __html: active.bodyHtml }}
              />
            </div>
          ) : (
            <textarea
              className="html-area"
              value={active.bodyHtml}
              onChange={(e) => patchActive({ bodyHtml: e.target.value })}
            />
          )}
        </div>
      </div>

      <div className="ee-ft">
        <span className="tiny muted">Prototype only. No real messages are sent.</span>
        <Button onClick={onClose}>Done</Button>
      </div>
    </div>
  );
}
