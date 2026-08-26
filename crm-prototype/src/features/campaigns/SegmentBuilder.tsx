import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Plus, X, Save } from "lucide-react";
import { PageHeader, Panel, Button, Field, useToast } from "../../components/ui";
import { useData } from "../../data/store";
import { num } from "../../lib/format";
import {
  ATTR_FIELDS,
  EVENT_OPTIONS,
  PRODUCT_OPTIONS,
  matchProviders,
  countMatches,
  describeCondition,
} from "../../lib/segmentEngine";
import type {
  Segment,
  SegmentCondition,
  SegmentRules,
  MatchOp,
  FunnelEventType,
  Product,
} from "../../data/schema";

type CondKind = SegmentCondition["kind"];

const KIND_LABEL: Record<CondKind, string> = {
  attribute: "Attribute",
  event: "Behavior (event)",
  product: "Product",
  message: "Message activity",
};

const WINDOW_OPTIONS: { value: "any" | "7d" | "30d" | "90d"; label: string }[] = [
  { value: "any", label: "Any time" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
];

/* A default condition for a given kind, used when adding a row or switching kind. */
function defaultCondition(kind: CondKind): SegmentCondition {
  switch (kind) {
    case "attribute": {
      const f = ATTR_FIELDS[0];
      return {
        kind: "attribute",
        field: f.key,
        op: "is",
        value: f.options ? f.options[0] : 0,
      };
    }
    case "event":
      return {
        kind: "event",
        performed: true,
        event: EVENT_OPTIONS[0].value,
        window: "any",
      };
    case "product":
      return { kind: "product", has: true, product: PRODUCT_OPTIONS[0].value };
    case "message":
      return { kind: "message", activity: "opened" };
  }
}

/* When the attribute field changes, reset op + value to sensible defaults for its type. */
function conditionForField(fieldKey: string): SegmentCondition {
  const f = ATTR_FIELDS.find((x) => x.key === fieldKey) ?? ATTR_FIELDS[0];
  if (f.type === "enum") {
    return { kind: "attribute", field: f.key, op: "is", value: f.options?.[0] ?? "" };
  }
  if (f.type === "bool") {
    return { kind: "attribute", field: f.key, op: "is", value: "true" };
  }
  return { kind: "attribute", field: f.key, op: "gte", value: 0 };
}

export function SegmentBuilder() {
  const data = useData((s) => s.data)!;
  const saveSegment = useData((s) => s.saveSegment);
  const { id } = useParams();
  const navigate = useNavigate();
  const toast = useToast((s) => s.push);

  const existing = id ? data.segments.find((s) => s.id === id) : undefined;

  const [name, setName] = useState<string>(existing?.name ?? "Untitled segment");
  const [match, setMatch] = useState<MatchOp>(existing?.rules?.match ?? "all");
  const [conditions, setConditions] = useState<SegmentCondition[]>(
    existing?.rules?.conditions ?? [
      { kind: "attribute", field: "persona", op: "is", value: "Growing Group" },
    ]
  );

  const rules: SegmentRules = useMemo(() => ({ match, conditions }), [match, conditions]);

  const count = useMemo(() => countMatches(data, rules), [data, rules]);
  const sample = useMemo(() => matchProviders(data, rules).slice(0, 6), [data, rules]);

  function updateCondition(idx: number, next: SegmentCondition) {
    setConditions((cs) => cs.map((c, i) => (i === idx ? next : c)));
  }

  function removeCondition(idx: number) {
    setConditions((cs) => cs.filter((_, i) => i !== idx));
  }

  function addCondition() {
    setConditions((cs) => [...cs, defaultCondition("attribute")]);
  }

  function handleSave() {
    const seg: Segment = {
      id: existing?.id ?? `seg_${Date.now()}`,
      name: name.trim() || "Untitled segment",
      funnelStage: "custom",
      filters: {},
      size: count,
      rules,
    };
    saveSegment(seg);
    toast(`Segment saved (${num(count)} providers)`);
    navigate("/segments");
  }

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Campaigns"
        title="Segment builder"
        sub="Select providers from the warehouse by attributes, behavior, and product mix. Counts update live against the real data."
        action={
          <Button variant="primary" onClick={handleSave}>
            <Save size={15} /> Save segment
          </Button>
        }
      />

      <div className="seg-layout">
        {/* Left: condition builder */}
        <div className="col gap-3">
          <Panel className="panel-pad">
            <Field label="Segment name">
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Untitled segment"
              />
            </Field>
          </Panel>

          <Panel className="panel-pad">
            <div className="col gap-3">
              <div className="row between center">
                <span className="section-title">Conditions</span>
                <div className="match-toggle">
                  <button
                    type="button"
                    className={match === "all" ? "on" : ""}
                    onClick={() => setMatch("all")}
                  >
                    Match ALL
                  </button>
                  <button
                    type="button"
                    className={match === "any" ? "on" : ""}
                    onClick={() => setMatch("any")}
                  >
                    Match ANY
                  </button>
                </div>
              </div>

              <div className="col gap-2">
                {conditions.map((c, idx) => (
                  <div key={idx} className="col gap-2">
                    {idx > 0 && (
                      <div className="cond-join">{match === "all" ? "AND" : "OR"}</div>
                    )}
                    <ConditionRow
                      condition={c}
                      onChange={(next) => updateCondition(idx, next)}
                      onRemove={() => removeCondition(idx)}
                    />
                  </div>
                ))}
              </div>

              <button type="button" className="add-cond" onClick={addCondition}>
                <Plus size={15} /> Add condition
              </button>
            </div>
          </Panel>
        </div>

        {/* Right: live count */}
        <div className="seg-count">
          <div className="sc-num num">{num(count)}</div>
          <div className="sc-cap">providers match, updated live</div>

          <div className="sc-sample col gap-1">
            {sample.map((p) => (
              <div key={p.id} className="sc-p">
                <div className="strong">{p.legalName}</div>
                <div className="muted small">
                  {p.persona} · {p.state}
                </div>
              </div>
            ))}
            {sample.length === 0 && <div className="muted small">No providers match yet</div>}
          </div>

          {conditions.length > 0 && (
            <div className="row wrap gap-1" style={{ marginTop: 12 }}>
              {conditions.map((c, idx) => (
                <span key={idx} className="cond-chip">
                  {describeCondition(c)}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---------- Condition row ---------- */

function ConditionRow({
  condition,
  onChange,
  onRemove,
}: {
  condition: SegmentCondition;
  onChange: (next: SegmentCondition) => void;
  onRemove: () => void;
}) {
  function changeKind(kind: CondKind) {
    onChange(defaultCondition(kind));
  }

  return (
    <div className="cond-row">
      <select
        className="cond-kind"
        value={condition.kind}
        onChange={(e) => changeKind(e.target.value as CondKind)}
      >
        {(Object.keys(KIND_LABEL) as CondKind[]).map((k) => (
          <option key={k} value={k}>
            {KIND_LABEL[k]}
          </option>
        ))}
      </select>

      <div className="cond-body">
        {condition.kind === "attribute" && (
          <AttributeControls condition={condition} onChange={onChange} />
        )}
        {condition.kind === "event" && (
          <EventControls condition={condition} onChange={onChange} />
        )}
        {condition.kind === "product" && (
          <ProductControls condition={condition} onChange={onChange} />
        )}
        {condition.kind === "message" && (
          <MessageControls condition={condition} onChange={onChange} />
        )}
      </div>

      <button type="button" className="cond-x" onClick={onRemove} aria-label="Remove condition">
        <X size={15} />
      </button>
    </div>
  );
}

/* ---------- Attribute ---------- */

function AttributeControls({
  condition,
  onChange,
}: {
  condition: Extract<SegmentCondition, { kind: "attribute" }>;
  onChange: (next: SegmentCondition) => void;
}) {
  const field = ATTR_FIELDS.find((f) => f.key === condition.field) ?? ATTR_FIELDS[0];

  return (
    <>
      <select
        value={condition.field}
        onChange={(e) => onChange(conditionForField(e.target.value))}
      >
        {ATTR_FIELDS.map((f) => (
          <option key={f.key} value={f.key}>
            {f.label}
          </option>
        ))}
      </select>

      {field.type === "number" ? (
        <select
          value={condition.op}
          onChange={(e) =>
            onChange({ ...condition, op: e.target.value as "gte" | "lte" })
          }
        >
          <option value="gte">is at least</option>
          <option value="lte">is at most</option>
        </select>
      ) : (
        <select
          value={condition.op}
          onChange={(e) =>
            onChange({ ...condition, op: e.target.value as "is" | "is_not" })
          }
        >
          <option value="is">is</option>
          <option value="is_not">is not</option>
        </select>
      )}

      {field.type === "enum" && (
        <select
          value={String(condition.value)}
          onChange={(e) => onChange({ ...condition, value: e.target.value })}
        >
          {(field.options ?? []).map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
      )}

      {field.type === "number" && (
        <input
          type="number"
          value={condition.value}
          onChange={(e) => onChange({ ...condition, value: Number(e.target.value) })}
          style={{ width: 120 }}
        />
      )}

      {field.type === "bool" && (
        <select
          value={String(condition.value)}
          onChange={(e) => onChange({ ...condition, value: e.target.value })}
        >
          <option value="true">yes</option>
          <option value="false">no</option>
        </select>
      )}
    </>
  );
}

/* ---------- Event ---------- */

function EventControls({
  condition,
  onChange,
}: {
  condition: Extract<SegmentCondition, { kind: "event" }>;
  onChange: (next: SegmentCondition) => void;
}) {
  return (
    <>
      <div className="col gap-1" style={{ width: "100%" }}>
        <div className="row wrap gap-1 center">
          <select
            value={condition.performed ? "yes" : "no"}
            onChange={(e) => onChange({ ...condition, performed: e.target.value === "yes" })}
          >
            <option value="yes">has done</option>
            <option value="no">has not done</option>
          </select>

          <select
            value={condition.event}
            onChange={(e) =>
              onChange({ ...condition, event: e.target.value as FunnelEventType })
            }
          >
            {EVENT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>

          <select
            value={condition.window}
            onChange={(e) =>
              onChange({
                ...condition,
                window: e.target.value as "any" | "7d" | "30d" | "90d",
              })
            }
          >
            {WINDOW_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>
        <span className="tiny faint">
          Tip: to find providers who started signup but never completed it, add two conditions:
          has done signup_started, and has not done completed_signup.
        </span>
      </div>
    </>
  );
}

/* ---------- Product ---------- */

function ProductControls({
  condition,
  onChange,
}: {
  condition: Extract<SegmentCondition, { kind: "product" }>;
  onChange: (next: SegmentCondition) => void;
}) {
  return (
    <>
      <select
        value={condition.has ? "has" : "not"}
        onChange={(e) => onChange({ ...condition, has: e.target.value === "has" })}
      >
        <option value="has">has</option>
        <option value="not">does not have</option>
      </select>

      <select
        value={condition.product}
        onChange={(e) => onChange({ ...condition, product: e.target.value as Product })}
      >
        {PRODUCT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </>
  );
}

/* ---------- Message activity ---------- */

function MessageControls({
  condition,
  onChange,
}: {
  condition: Extract<SegmentCondition, { kind: "message" }>;
  onChange: (next: SegmentCondition) => void;
}) {
  return (
    <select
      value={condition.activity}
      onChange={(e) =>
        onChange({
          ...condition,
          activity: e.target.value as "opened" | "clicked" | "not_opened",
        })
      }
    >
      <option value="opened">opened a message</option>
      <option value="clicked">clicked a message</option>
      <option value="not_opened">did not open a message</option>
    </select>
  );
}
