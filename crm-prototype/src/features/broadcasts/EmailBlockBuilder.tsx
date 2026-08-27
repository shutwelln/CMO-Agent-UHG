import { useRef, useState } from "react";
import {
  Heading2,
  Type,
  Image as ImageIcon,
  MousePointerClick,
  Minus,
  MoveVertical,
  GripVertical,
  Trash2,
  Bold,
  Italic,
  Underline as UnderlineIcon,
  Link as LinkIcon,
  Tag,
  AlignLeft,
  AlignCenter,
  AlignRight,
} from "lucide-react";
import type { EmailBlock, EmailBlockType } from "../../data/schema";
import { makeBlock, MERGE_TAGS, renderBlocksToHtml } from "../../lib/emailBlocks";

interface Props {
  blocks: EmailBlock[];
  onChange: (blocks: EmailBlock[]) => void;
  subject: string;
  preheader: string;
}

const PALETTE: { type: EmailBlockType; label: string; icon: typeof Type }[] = [
  { type: "heading", label: "Heading", icon: Heading2 },
  { type: "text", label: "Text", icon: Type },
  { type: "image", label: "Image", icon: ImageIcon },
  { type: "button", label: "Button", icon: MousePointerClick },
  { type: "divider", label: "Divider", icon: Minus },
  { type: "spacer", label: "Spacer", icon: MoveVertical },
];

const BLOCK_LABEL: Record<EmailBlockType, string> = {
  heading: "Heading",
  text: "Text",
  image: "Image",
  button: "Button",
  divider: "Divider",
  spacer: "Spacer",
};

export function EmailBlockBuilder({ blocks, onChange, subject, preheader }: Props) {
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [overIndex, setOverIndex] = useState<number | null>(null);
  const [selected, setSelected] = useState<string | null>(blocks[0]?.id ?? null);

  const add = (type: EmailBlockType) => {
    const b = makeBlock(type);
    onChange([...blocks, b]);
    setSelected(b.id);
  };

  const patch = (id: string, next: Partial<EmailBlock>) =>
    onChange(blocks.map((b) => (b.id === id ? { ...b, ...next } : b)));

  const remove = (id: string) => {
    onChange(blocks.filter((b) => b.id !== id));
    if (selected === id) setSelected(null);
  };

  const move = (from: number, to: number) => {
    if (from === to || to < 0 || to >= blocks.length) return;
    const next = blocks.slice();
    const [item] = next.splice(from, 1);
    next.splice(to, 0, item);
    onChange(next);
  };

  const onDrop = (to: number) => {
    if (dragIndex !== null) move(dragIndex, to > dragIndex ? to - 1 : to);
    setDragIndex(null);
    setOverIndex(null);
  };

  return (
    <div className="bb-layout">
      {/* ---- editor column ---- */}
      <div className="col gap-3">
        <div className="bb-palette">
          <span className="bb-palette-label">Drag blocks in, or click to add</span>
          <div className="bb-palette-row">
            {PALETTE.map((p) => {
              const Icon = p.icon;
              return (
                <button
                  key={p.type}
                  className="bb-chip"
                  draggable
                  onDragStart={() => setDragIndex(-1 - PALETTE.findIndex((x) => x.type === p.type))}
                  onClick={() => add(p.type)}
                  title={`Add ${p.label}`}
                >
                  <Icon size={14} /> {p.label}
                </button>
              );
            })}
          </div>
        </div>

        <div
          className="bb-canvas"
          onDragOver={(e) => {
            e.preventDefault();
            if (dragIndex !== null && dragIndex < 0) setOverIndex(blocks.length);
          }}
          onDrop={() => {
            // dropping a palette chip onto empty canvas appends
            if (dragIndex !== null && dragIndex < 0) {
              const type = PALETTE[-dragIndex - 1]?.type;
              if (type) add(type);
            }
            setDragIndex(null);
            setOverIndex(null);
          }}
        >
          {blocks.length === 0 && (
            <div className="bb-empty">Add a block to start building your email.</div>
          )}

          {blocks.map((b, i) => (
            <div key={b.id}>
              {overIndex === i && dragIndex !== null && dragIndex >= 0 && (
                <div className="bb-dropline" />
              )}
              <div
                className={`bb-block${selected === b.id ? " sel" : ""}${
                  dragIndex === i ? " dragging" : ""
                }`}
                onClick={() => setSelected(b.id)}
                onDragOver={(e) => {
                  e.preventDefault();
                  if (dragIndex !== null && dragIndex >= 0) setOverIndex(i);
                }}
                onDrop={(e) => {
                  e.stopPropagation();
                  if (dragIndex !== null && dragIndex >= 0) onDrop(i);
                }}
              >
                <div className="bb-block-bar">
                  <span
                    className="bb-grip"
                    draggable
                    onDragStart={() => setDragIndex(i)}
                    onDragEnd={() => {
                      setDragIndex(null);
                      setOverIndex(null);
                    }}
                    title="Drag to reorder"
                  >
                    <GripVertical size={14} />
                  </span>
                  <span className="bb-block-kind">{BLOCK_LABEL[b.type]}</span>
                  <div className="grow" />
                  <button className="bb-icon" title="Move up" onClick={(e) => { e.stopPropagation(); move(i, i - 1); }}>
                    ↑
                  </button>
                  <button className="bb-icon" title="Move down" onClick={(e) => { e.stopPropagation(); move(i, i + 1); }}>
                    ↓
                  </button>
                  <button
                    className="bb-icon danger"
                    title="Remove block"
                    onClick={(e) => {
                      e.stopPropagation();
                      remove(b.id);
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
                <BlockEditor block={b} onPatch={(n) => patch(b.id, n)} />
              </div>
            </div>
          ))}

          {overIndex === blocks.length && dragIndex !== null && dragIndex >= 0 && (
            <div className="bb-dropline" />
          )}
          <div
            className="bb-tail"
            onDragOver={(e) => {
              e.preventDefault();
              if (dragIndex !== null && dragIndex >= 0) setOverIndex(blocks.length);
            }}
            onDrop={() => {
              if (dragIndex !== null && dragIndex >= 0) onDrop(blocks.length);
            }}
          />
        </div>
      </div>

      {/* ---- live preview column ---- */}
      <div className="bb-preview-wrap">
        <div className="bb-preview-head">Live preview</div>
        <div className="bb-preview">
          <div className="bb-mail">
            <div className="bb-mail-subject">{subject || "(no subject)"}</div>
            {preheader && <div className="bb-mail-preheader">{preheader}</div>}
            <div
              className="bb-mail-body"
              dangerouslySetInnerHTML={{ __html: renderBlocksToHtml(blocks) }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- per-block editors ---------- */

function AlignPicker({
  value,
  onChange,
}: {
  value: EmailBlock["align"];
  onChange: (a: EmailBlock["align"]) => void;
}) {
  const opts: { a: NonNullable<EmailBlock["align"]>; icon: typeof AlignLeft }[] = [
    { a: "left", icon: AlignLeft },
    { a: "center", icon: AlignCenter },
    { a: "right", icon: AlignRight },
  ];
  return (
    <div className="bb-align">
      {opts.map((o) => {
        const Icon = o.icon;
        return (
          <button
            key={o.a}
            className={`bb-align-btn${(value ?? "left") === o.a ? " on" : ""}`}
            onClick={(e) => {
              e.stopPropagation();
              onChange(o.a);
            }}
            title={`Align ${o.a}`}
          >
            <Icon size={13} />
          </button>
        );
      })}
    </div>
  );
}

function BlockEditor({
  block,
  onPatch,
}: {
  block: EmailBlock;
  onPatch: (n: Partial<EmailBlock>) => void;
}) {
  if (block.type === "heading") {
    return (
      <div className="bb-edit">
        <input
          className="bb-heading-input"
          value={block.text ?? ""}
          placeholder="Heading text"
          onChange={(e) => onPatch({ text: e.target.value })}
        />
        <AlignPicker value={block.align} onChange={(a) => onPatch({ align: a })} />
      </div>
    );
  }

  if (block.type === "text") {
    return <RichText block={block} onPatch={onPatch} />;
  }

  if (block.type === "image") {
    return (
      <div className="bb-edit col gap-2">
        {block.src ? (
          <img className="bb-img-prev" src={block.src} alt={block.alt ?? ""} />
        ) : (
          <div className="bb-img-empty">
            <ImageIcon size={20} /> No image set
          </div>
        )}
        <input
          className="bb-inp"
          value={block.src ?? ""}
          placeholder="Image URL"
          onChange={(e) => onPatch({ src: e.target.value })}
        />
        <div className="row gap-2 center">
          <input
            className="bb-inp grow"
            value={block.alt ?? ""}
            placeholder="Alt text"
            onChange={(e) => onPatch({ alt: e.target.value })}
          />
          <AlignPicker value={block.align} onChange={(a) => onPatch({ align: a })} />
        </div>
      </div>
    );
  }

  if (block.type === "button") {
    return (
      <div className="bb-edit col gap-2">
        <div className="row gap-2 center">
          <input
            className="bb-inp grow"
            value={block.text ?? ""}
            placeholder="Button label"
            onChange={(e) => onPatch({ text: e.target.value })}
          />
          <AlignPicker value={block.align} onChange={(a) => onPatch({ align: a })} />
        </div>
        <input
          className="bb-inp"
          value={block.href ?? ""}
          placeholder="https://optumbank.com/providers"
          onChange={(e) => onPatch({ href: e.target.value })}
        />
      </div>
    );
  }

  if (block.type === "spacer") {
    return (
      <div className="bb-edit row gap-2 center">
        <span className="tiny muted">Height</span>
        <input
          type="range"
          min={8}
          max={80}
          value={block.height ?? 24}
          onChange={(e) => onPatch({ height: Number(e.target.value) })}
          style={{ flex: 1 }}
        />
        <span className="tiny mono">{block.height ?? 24}px</span>
      </div>
    );
  }

  // divider
  return <div className="bb-edit bb-divider-prev" />;
}

/* Rich-text editor for text blocks (mirrors the lifecycle email editor). */
function RichText({
  block,
  onPatch,
}: {
  block: EmailBlock;
  onPatch: (n: Partial<EmailBlock>) => void;
}) {
  const areaRef = useRef<HTMLDivElement | null>(null);

  const read = () => {
    if (areaRef.current) onPatch({ html: areaRef.current.innerHTML });
  };
  const exec = (cmd: string, value?: string) => {
    areaRef.current?.focus();
    document.execCommand(cmd, false, value);
    read();
  };
  const insertTag = (tag: string) => {
    areaRef.current?.focus();
    document.execCommand("insertText", false, tag);
    read();
  };
  const insertLink = () => {
    const url = window.prompt("Link URL", "https://optumbank.com/providers");
    if (url) exec("createLink", url);
  };

  return (
    <div className="bb-edit col gap-2">
      <div className="bb-rt-toolbar" onClick={(e) => e.stopPropagation()}>
        <button className="wys-btn" title="Bold" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("bold")}>
          <Bold size={14} />
        </button>
        <button className="wys-btn" title="Italic" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("italic")}>
          <Italic size={14} />
        </button>
        <button className="wys-btn" title="Underline" onMouseDown={(e) => e.preventDefault()} onClick={() => exec("underline")}>
          <UnderlineIcon size={14} />
        </button>
        <button className="wys-btn" title="Link" onMouseDown={(e) => e.preventDefault()} onClick={insertLink}>
          <LinkIcon size={14} />
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
            <Tag size={12} />
            <span className="mono tiny" style={{ marginLeft: 3 }}>
              {tag.replace(/[{}]/g, "").replace("provider.", "")}
            </span>
          </button>
        ))}
        <div className="grow" />
        <AlignPicker value={block.align} onChange={(a) => onPatch({ align: a })} />
      </div>
      <div
        ref={areaRef}
        className="bb-rt-area"
        contentEditable
        suppressContentEditableWarning
        onInput={read}
        onClick={(e) => e.stopPropagation()}
        dangerouslySetInnerHTML={{ __html: block.html ?? "" }}
      />
    </div>
  );
}
