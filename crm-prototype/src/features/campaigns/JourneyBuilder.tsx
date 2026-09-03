import { useState } from "react";
import { nanoid } from "nanoid";
import {
  Mail,
  Clock,
  GitBranch,
  Shuffle,
  LogOut,
  Plus,
  X,
} from "lucide-react";
import { Button, Drawer, Modal, Field } from "../../components/ui";
import type {
  CampaignTrigger,
  Journey,
  JourneyNode,
  JourneyNodeType,
} from "../../data/schema";
import { FUNNEL_EVENT_LABEL } from "../../data/schema";
import { EmailEditor, defaultVariant } from "./EmailEditor";

interface Props {
  value: Journey;
  onChange: (j: Journey) => void;
  trigger?: CampaignTrigger;
}

const nid = () => `jn_${nanoid(8)}`;

/* ---------- node factories ---------- */

export function makeNode(type: JourneyNodeType): JourneyNode {
  const base: JourneyNode = { id: nid(), type };
  if (type === "email") {
    return { ...base, name: "", abTest: false, variants: [defaultVariant("A", 100)] };
  }
  if (type === "delay") {
    return { ...base, delayValue: 3, delayUnit: "days" };
  }
  if (type === "condition") {
    return {
      ...base,
      conditionKind: "opened",
      conditionLabel: "If opened the previous email",
      yes: [],
      no: [],
    };
  }
  if (type === "split") {
    return { ...base, splitPercent: 50, branchA: [], branchB: [] };
  }
  return base; // exit
}

/* ---------- immutable tree helpers ---------- */

/* A path is a list of segments identifying a nested list within the tree.
 * Each segment names the parent node id and which child list to descend into. */
type Branch = "yes" | "no" | "branchA" | "branchB";
interface PathSeg {
  nodeId: string;
  branch: Branch;
}

function childKeyFor(seg: PathSeg): Branch {
  return seg.branch;
}

function mapListAt(
  nodes: JourneyNode[],
  path: PathSeg[],
  fn: (list: JourneyNode[]) => JourneyNode[]
): JourneyNode[] {
  if (path.length === 0) return fn(nodes);
  const [head, ...rest] = path;
  return nodes.map((n) => {
    if (n.id !== head.nodeId) return n;
    const key = childKeyFor(head);
    const child = (n[key] as JourneyNode[] | undefined) ?? [];
    return { ...n, [key]: mapListAt(child, rest, fn) };
  });
}

function insertAt(
  nodes: JourneyNode[],
  path: PathSeg[],
  index: number,
  node: JourneyNode
): JourneyNode[] {
  return mapListAt(nodes, path, (list) => {
    const copy = list.slice();
    copy.splice(index, 0, node);
    return copy;
  });
}

function updateNode(
  nodes: JourneyNode[],
  path: PathSeg[],
  nodeId: string,
  next: JourneyNode
): JourneyNode[] {
  return mapListAt(nodes, path, (list) =>
    list.map((n) => (n.id === nodeId ? next : n))
  );
}

function removeNode(nodes: JourneyNode[], path: PathSeg[], nodeId: string): JourneyNode[] {
  return mapListAt(nodes, path, (list) => list.filter((n) => n.id !== nodeId));
}

/* ---------- step menu popover ---------- */

const STEP_OPTIONS: { type: JourneyNodeType; label: string; icon: typeof Mail }[] = [
  { type: "email", label: "Email", icon: Mail },
  { type: "delay", label: "Wait / delay", icon: Clock },
  { type: "condition", label: "If / else condition", icon: GitBranch },
  { type: "split", label: "Random A/B split", icon: Shuffle },
  { type: "exit", label: "Exit journey", icon: LogOut },
];

function AddStep({ onPick }: { onPick: (type: JourneyNodeType) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "relative" }}>
      <button className="jadd" onClick={() => setOpen((o) => !o)} title="Add a step">
        <Plus size={16} />
      </button>
      {open && (
        <>
          <div
            style={{ position: "fixed", inset: 0, zIndex: 40 }}
            onClick={() => setOpen(false)}
          />
          <div className="stepmenu" style={{ zIndex: 41 }}>
            {STEP_OPTIONS.map((o) => {
              const Icon = o.icon;
              return (
                <button
                  key={o.type}
                  className="stepmenu-item"
                  onClick={() => {
                    onPick(o.type);
                    setOpen(false);
                  }}
                >
                  <span className="smi-ico">
                    <Icon size={15} />
                  </span>
                  {o.label}
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- editing modals ---------- */

function DelayModal({
  node,
  onSave,
  onClose,
}: {
  node: JourneyNode;
  onSave: (n: JourneyNode) => void;
  onClose: () => void;
}) {
  const [val, setVal] = useState(node.delayValue ?? 1);
  const [unit, setUnit] = useState(node.delayUnit ?? "days");
  return (
    <Modal
      title="Wait / delay"
      onClose={onClose}
      footer={
        <Button
          onClick={() => {
            onSave({ ...node, delayValue: Math.max(1, val), delayUnit: unit });
            onClose();
          }}
        >
          Save
        </Button>
      }
    >
      <div className="row gap-2">
        <Field label="Wait">
          <input
            type="number"
            min={1}
            value={val}
            onChange={(e) => setVal(Number(e.target.value) || 1)}
            style={{ width: 120 }}
          />
        </Field>
        <Field label="Unit">
          <select
            className="select"
            value={unit}
            onChange={(e) => setUnit(e.target.value as "minutes" | "hours" | "days")}
          >
            <option value="minutes">minutes</option>
            <option value="hours">hours</option>
            <option value="days">days</option>
          </select>
        </Field>
      </div>
    </Modal>
  );
}

const CONDITION_KINDS: { value: NonNullable<JourneyNode["conditionKind"]>; label: string }[] = [
  { value: "opened", label: "Opened the previous email" },
  { value: "clicked", label: "Clicked a link" },
  { value: "attribute", label: "Matches an attribute" },
  { value: "event", label: "Performed an event" },
  { value: "card_activated", label: "Activated the card" },
  { value: "card_first_spend", label: "Made a first purchase" },
  { value: "card_spend_threshold", label: "Reached a spend threshold" },
];

function ConditionModal({
  node,
  onSave,
  onClose,
}: {
  node: JourneyNode;
  onSave: (n: JourneyNode) => void;
  onClose: () => void;
}) {
  const [kind, setKind] = useState(node.conditionKind ?? "opened");
  const [label, setLabel] = useState(node.conditionLabel ?? "");
  return (
    <Modal
      title="Condition"
      onClose={onClose}
      footer={
        <Button
          onClick={() => {
            const finalLabel =
              label.trim() ||
              CONDITION_KINDS.find((k) => k.value === kind)?.label ||
              "Condition";
            onSave({ ...node, conditionKind: kind, conditionLabel: finalLabel });
            onClose();
          }}
        >
          Save
        </Button>
      }
    >
      <div className="col gap-3">
        <Field label="Branch on">
          <select
            className="select"
            value={kind}
            onChange={(e) => {
              const k = e.target.value as NonNullable<JourneyNode["conditionKind"]>;
              setKind(k);
              if (!label.trim())
                setLabel(CONDITION_KINDS.find((c) => c.value === k)?.label ?? "");
            }}
          >
            {CONDITION_KINDS.map((k) => (
              <option key={k.value} value={k.value}>
                {k.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Label shown on the node">
          <input
            className="select"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="If opened the previous email"
          />
        </Field>
      </div>
    </Modal>
  );
}

function SplitModal({
  node,
  onSave,
  onClose,
}: {
  node: JourneyNode;
  onSave: (n: JourneyNode) => void;
  onClose: () => void;
}) {
  const [pct, setPct] = useState(node.splitPercent ?? 50);
  return (
    <Modal
      title="Random A/B split"
      onClose={onClose}
      footer={
        <Button
          onClick={() => {
            onSave({ ...node, splitPercent: Math.max(0, Math.min(100, pct)) });
            onClose();
          }}
        >
          Save
        </Button>
      }
    >
      <Field label="Percent sent down branch A">
        <input
          type="number"
          min={0}
          max={100}
          value={pct}
          onChange={(e) => setPct(Number(e.target.value) || 0)}
          style={{ width: 120 }}
        />
        <span className="tiny muted" style={{ marginLeft: 10 }}>
          Branch B gets {100 - pct}%
        </span>
      </Field>
    </Modal>
  );
}

/* ---------- recursive flow renderer ---------- */

type EditState =
  | { kind: "email"; node: JourneyNode; path: PathSeg[] }
  | { kind: "delay"; node: JourneyNode; path: PathSeg[] }
  | { kind: "condition"; node: JourneyNode; path: PathSeg[] }
  | { kind: "split"; node: JourneyNode; path: PathSeg[] }
  | null;

export function JourneyBuilder({ value, onChange, trigger }: Props) {
  const [edit, setEdit] = useState<EditState>(null);

  const applyInsert = (path: PathSeg[], index: number, type: JourneyNodeType) => {
    onChange({ ...value, nodes: insertAt(value.nodes, path, index, makeNode(type)) });
  };
  const applyUpdate = (path: PathSeg[], node: JourneyNode) => {
    onChange({ ...value, nodes: updateNode(value.nodes, path, node.id, node) });
  };
  const applyRemove = (path: PathSeg[], nodeId: string) => {
    onChange({ ...value, nodes: removeNode(value.nodes, path, nodeId) });
  };

  const triggerText = (): string => {
    if (!trigger) return "When a provider enters the journey";
    if (trigger.type === "event" && trigger.event)
      return `When event "${FUNNEL_EVENT_LABEL[trigger.event]}" is performed`;
    return "When a provider ENTERS the segment";
  };

  const renderList = (list: JourneyNode[], path: PathSeg[]) => (
    <div className="jflow">
      {list.map((node, i) => (
        <div key={node.id} className="col" style={{ alignItems: "center" }}>
          <NodeCard
            node={node}
            path={path}
            onOpen={() => {
              if (node.type === "email") setEdit({ kind: "email", node, path });
              else if (node.type === "delay") setEdit({ kind: "delay", node, path });
              else if (node.type === "condition") setEdit({ kind: "condition", node, path });
              else if (node.type === "split") setEdit({ kind: "split", node, path });
            }}
            onRemove={() => applyRemove(path, node.id)}
            renderList={renderList}
          />
          {i < list.length - 1 && <div className="jconnector" />}
        </div>
      ))}
      <div className="jconnector dashed" />
      <AddStep onPick={(type) => applyInsert(path, list.length, type)} />
    </div>
  );

  return (
    <div className="jb-canvas">
      <div className="jtrigger">
        <div className="jt-k">Trigger</div>
        <div className="jt-v">
          {triggerText()}
          {trigger?.type === "segment" && trigger.segmentId ? "" : ""}
        </div>
      </div>

      {renderList(value.nodes, [])}

      {edit?.kind === "email" && (
        <Drawer onClose={() => setEdit(null)} width={620}>
          <EmailEditor
            node={edit.node}
            onChange={(n) => {
              applyUpdate(edit.path, n);
              setEdit({ ...edit, node: n });
            }}
            onClose={() => setEdit(null)}
          />
        </Drawer>
      )}
      {edit?.kind === "delay" && (
        <DelayModal
          node={edit.node}
          onSave={(n) => applyUpdate(edit.path, n)}
          onClose={() => setEdit(null)}
        />
      )}
      {edit?.kind === "condition" && (
        <ConditionModal
          node={edit.node}
          onSave={(n) => applyUpdate(edit.path, n)}
          onClose={() => setEdit(null)}
        />
      )}
      {edit?.kind === "split" && (
        <SplitModal
          node={edit.node}
          onSave={(n) => applyUpdate(edit.path, n)}
          onClose={() => setEdit(null)}
        />
      )}
    </div>
  );
}

/* ---------- individual node card ---------- */

function NodeCard({
  node,
  path,
  onOpen,
  onRemove,
  renderList,
}: {
  node: JourneyNode;
  path: PathSeg[];
  onOpen: () => void;
  onRemove: () => void;
  renderList: (list: JourneyNode[], path: PathSeg[]) => React.ReactNode;
}) {
  const RemoveBtn = (
    <button
      className="jn-remove"
      title="Remove step"
      onClick={(e) => {
        e.stopPropagation();
        onRemove();
      }}
      style={{
        position: "absolute",
        top: 6,
        right: 6,
        border: "none",
        background: "transparent",
        cursor: "pointer",
        color: "var(--text-faint)",
        lineHeight: 0,
      }}
    >
      <X size={14} />
    </button>
  );

  if (node.type === "email") {
    const subj = node.variants?.[0]?.subject ?? "Email";
    const title = node.name?.trim() || subj;
    return (
      <div className="jnode jn-email" onClick={onOpen} style={{ position: "relative" }}>
        {RemoveBtn}
        <div className="jn-head">
          <span className="jn-ico">
            <Mail size={16} />
          </span>
          <span className="jn-title">{title}</span>
        </div>
        <div className="jn-sub row gap-2 center">
          <span>Email</span>
          {node.abTest && <span className="jn-variant">A/B</span>}
        </div>
      </div>
    );
  }

  if (node.type === "delay") {
    return (
      <div className="jnode jn-delay" onClick={onOpen} style={{ position: "relative" }}>
        {RemoveBtn}
        <div className="jn-head">
          <span className="jn-ico">
            <Clock size={16} />
          </span>
          <span className="jn-title">
            Wait {node.delayValue ?? 1} {node.delayUnit ?? "days"}
          </span>
        </div>
      </div>
    );
  }

  if (node.type === "condition") {
    return (
      <div className="col" style={{ alignItems: "center" }}>
        <div
          className="jnode jn-condition"
          onClick={onOpen}
          style={{ position: "relative" }}
        >
          {RemoveBtn}
          <div className="jn-head">
            <span className="jn-ico">
              <GitBranch size={16} />
            </span>
            <span className="jn-title">{node.conditionLabel || "Condition"}</span>
          </div>
        </div>
        <div className="jbranches">
          <div className="jbranch jbranch-yes">
            <div className="jbranch-label">Yes</div>
            {renderList(node.yes ?? [], [...path, { nodeId: node.id, branch: "yes" }])}
          </div>
          <div className="jbranch jbranch-no">
            <div className="jbranch-label">No</div>
            {renderList(node.no ?? [], [...path, { nodeId: node.id, branch: "no" }])}
          </div>
        </div>
      </div>
    );
  }

  if (node.type === "split") {
    const a = node.splitPercent ?? 50;
    return (
      <div className="col" style={{ alignItems: "center" }}>
        <div className="jnode jn-split" onClick={onOpen} style={{ position: "relative" }}>
          {RemoveBtn}
          <div className="jn-head">
            <span className="jn-ico">
              <Shuffle size={16} />
            </span>
            <span className="jn-title">
              Random split {a}% / {100 - a}%
            </span>
          </div>
          <div className="jsplit-bar" style={{ ["--a" as string]: `${a}%` }} />
        </div>
        <div className="jbranches">
          <div className="jbranch jbranch-a">
            <div className="jbranch-label">A</div>
            {renderList(node.branchA ?? [], [...path, { nodeId: node.id, branch: "branchA" }])}
          </div>
          <div className="jbranch jbranch-b">
            <div className="jbranch-label">B</div>
            {renderList(node.branchB ?? [], [...path, { nodeId: node.id, branch: "branchB" }])}
          </div>
        </div>
      </div>
    );
  }

  // exit
  return (
    <div className="jnode jn-exit" style={{ position: "relative" }}>
      {RemoveBtn}
      <div className="jn-head">
        <span className="jn-ico">
          <LogOut size={16} />
        </span>
        <span className="jn-title">Exit journey</span>
      </div>
    </div>
  );
}

/* Flatten the journey tree into a readable linear outline for review. */
export function flattenJourney(journey: Journey): { label: string; depth: number }[] {
  const out: { label: string; depth: number }[] = [];
  const walk = (nodes: JourneyNode[], depth: number) => {
    for (const n of nodes) {
      if (n.type === "email") {
        const subj = n.variants?.[0]?.subject ?? "Email";
        out.push({ label: `Email: ${n.name?.trim() || subj}${n.abTest ? " (A/B)" : ""}`, depth });
      } else if (n.type === "delay") {
        out.push({ label: `Wait ${n.delayValue ?? 1} ${n.delayUnit ?? "days"}`, depth });
      } else if (n.type === "condition") {
        out.push({ label: `If ${n.conditionLabel || "condition"}`, depth });
        if (n.yes?.length) {
          out.push({ label: "Yes", depth: depth + 1 });
          walk(n.yes, depth + 2);
        }
        if (n.no?.length) {
          out.push({ label: "No", depth: depth + 1 });
          walk(n.no, depth + 2);
        }
      } else if (n.type === "split") {
        const a = n.splitPercent ?? 50;
        out.push({ label: `Random split ${a}% / ${100 - a}%`, depth });
        if (n.branchA?.length) {
          out.push({ label: "A", depth: depth + 1 });
          walk(n.branchA, depth + 2);
        }
        if (n.branchB?.length) {
          out.push({ label: "B", depth: depth + 1 });
          walk(n.branchB, depth + 2);
        }
      } else {
        out.push({ label: "Exit journey", depth });
      }
    }
  };
  walk(journey.nodes, 0);
  return out;
}

/* Flatten into simple {day, channel, template} steps for the stored Campaign. */
export function journeySteps(journey: Journey): { day: number; channel: string; template: string }[] {
  const steps: { day: number; channel: string; template: string }[] = [];
  let day = 0;
  const unitDays = (n: JourneyNode) => {
    const v = n.delayValue ?? 1;
    if (n.delayUnit === "days") return v;
    if (n.delayUnit === "hours") return v / 24;
    return v / (24 * 60);
  };
  const walk = (nodes: JourneyNode[]) => {
    for (const n of nodes) {
      if (n.type === "delay") {
        day += Math.round(unitDays(n));
      } else if (n.type === "email") {
        const subj = n.variants?.[0]?.subject ?? "Email";
        steps.push({ day, channel: "email", template: n.name?.trim() || subj });
      } else if (n.type === "condition") {
        walk(n.yes ?? []);
      } else if (n.type === "split") {
        walk(n.branchA ?? []);
      }
    }
  };
  walk(journey.nodes);
  return steps;
}
