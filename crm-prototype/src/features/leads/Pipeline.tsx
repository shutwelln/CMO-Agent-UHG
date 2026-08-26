import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  DndContext,
  useDraggable,
  useDroppable,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useData } from "../../data/store";
import { useRole, CURRENT_REP_ID } from "../../context/role";
import { leadsForRep, pipelineValue } from "../../data/selectors";
import { PageHeader, ProductBadge, useToast } from "../../components/ui";
import { money } from "../../lib/format";
import {
  STAGE_LABEL,
  type OfferLead,
  type Provider,
  type Stage,
} from "../../data/schema";

const COLUMN_STAGES: Stage[] = ["new", "working", "contacted", "qualified", "appt_set", "won", "lost"];
const CARD_CAP = 40;

export function Pipeline() {
  const data = useData((s) => s.data)!;
  const role = useRole((s) => s.role);
  const setLeadStage = useData((s) => s.setLeadStage);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();

  const providerMap = useMemo(() => {
    const m = new Map<string, Provider>();
    for (const p of data.providers) m.set(p.id, p);
    return m;
  }, [data.providers]);

  const leads = useMemo(
    () => (role === "sales_rep" ? leadsForRep(data, CURRENT_REP_ID) : data.leads),
    [data, role]
  );

  const byStage = useMemo(() => {
    const m = new Map<Stage, OfferLead[]>();
    for (const s of COLUMN_STAGES) m.set(s, []);
    for (const l of leads) m.get(l.stage)?.push(l);
    return m;
  }, [leads]);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }));

  const onDragEnd = (e: DragEndEvent) => {
    const leadId = e.active.id as string;
    const newStage = e.over?.id as Stage | undefined;
    if (!newStage) return;
    const lead = leads.find((l) => l.id === leadId);
    if (!lead || lead.stage === newStage) return;
    setLeadStage(leadId, newStage);
    toast(`Moved to ${STAGE_LABEL[newStage]}`);
  };

  return (
    <div className="col gap-3">
      <PageHeader
        title="Pipeline"
        sub="Drag a lead across stages, or use the stage menu on each card."
      />
      <DndContext sensors={sensors} onDragEnd={onDragEnd}>
        <div className="kanban">
          {COLUMN_STAGES.map((stage) => (
            <KanbanColumn
              key={stage}
              stage={stage}
              leads={byStage.get(stage) ?? []}
              providerMap={providerMap}
              onSetStage={(id, s) => {
                setLeadStage(id, s);
                toast(`Moved to ${STAGE_LABEL[s]}`);
              }}
              onOpen={(pid) => navigate(`/providers/${pid}`)}
            />
          ))}
        </div>
      </DndContext>
    </div>
  );
}

function KanbanColumn({
  stage,
  leads,
  providerMap,
  onSetStage,
  onOpen,
}: {
  stage: Stage;
  leads: OfferLead[];
  providerMap: Map<string, Provider>;
  onSetStage: (leadId: string, stage: Stage) => void;
  onOpen: (providerId: string) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: stage });
  const total = pipelineValue(leads);
  const visible = leads.slice(0, CARD_CAP);
  const overflow = leads.length - visible.length;

  return (
    <div
      className="kcol"
      ref={setNodeRef}
      style={isOver ? { outline: "2px solid var(--navy)", outlineOffset: -2 } : undefined}
    >
      <div className="kcol-hd">
        <span className="kc-title">{STAGE_LABEL[stage]}</span>
        <span className="kc-meta">
          {leads.length} - {money(total, true)}
        </span>
      </div>
      {visible.map((l) => (
        <KanbanCard
          key={l.id}
          lead={l}
          provider={providerMap.get(l.providerId)}
          onSetStage={onSetStage}
          onOpen={onOpen}
        />
      ))}
      {overflow > 0 && <div className="tiny muted center" style={{ padding: "6px 0" }}>+{overflow} more</div>}
    </div>
  );
}

function KanbanCard({
  lead,
  provider,
  onSetStage,
  onOpen,
}: {
  lead: OfferLead;
  provider: Provider | undefined;
  onSetStage: (leadId: string, stage: Stage) => void;
  onOpen: (providerId: string) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({ id: lead.id });
  const style = transform
    ? { transform: `translate(${transform.x}px, ${transform.y}px)`, opacity: isDragging ? 0.6 : 1, zIndex: isDragging ? 50 : undefined }
    : undefined;

  return (
    <div className="kcard" ref={setNodeRef} style={style} {...attributes} {...listeners}>
      <button
        className="kc-name btn-text"
        style={{ padding: 0, textAlign: "left", color: "var(--navy)" }}
        onPointerDown={(e) => e.stopPropagation()}
        onClick={() => onOpen(lead.providerId)}
      >
        {provider?.legalName ?? "Unknown provider"}
      </button>
      <div className="kc-row">
        <ProductBadge product={lead.product} />
        <span className="num strong small">{money(lead.offerAmount)}</span>
      </div>
      <div className="kc-row">
        <span className="attempts">
          {[0, 1, 2].map((i) => (
            <span key={i} className={i < lead.attempts ? "attempt-dot on" : "attempt-dot"} />
          ))}
        </span>
        <select
          className="select"
          style={{ padding: "3px 6px", fontSize: 11.5 }}
          value={lead.stage}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onSetStage(lead.id, e.target.value as Stage)}
        >
          {COLUMN_STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
