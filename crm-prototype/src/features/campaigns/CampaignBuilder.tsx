import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ShieldCheck,
  ArrowRight,
  ArrowLeft,
  Zap,
  Users,
  Plus,
} from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Stepper,
  Field,
  Banner,
  useToast,
} from "../../components/ui";
import { useData } from "../../data/store";
import type {
  Campaign,
  CampaignTrigger,
  FunnelEventType,
  Journey,
  Segment,
} from "../../data/schema";
import { FUNNEL_EVENTS, FUNNEL_EVENT_LABEL } from "../../data/schema";
import { countMatches } from "../../lib/segmentEngine";
import { useRole, ROLE_LABEL } from "../../context/role";
import { num } from "../../lib/format";
import { JourneyBuilder, makeNode, flattenJourney, journeySteps } from "./JourneyBuilder";
import { CARD_TEMPLATES } from "../../lib/cardJourneys";

const STEPS = ["Trigger", "Journey", "Delivery", "Review"];
const NOW_ISO = "2026-08-26T12:00:00.000Z";

/* A short, populated default journey: email -> wait 3d -> if opened -> yes/no emails -> exit. */
function seedJourney(): Journey {
  const first = makeNode("email");
  first.name = "Intro: open your Optum Bank account";
  if (first.variants?.[0]) first.variants[0].subject = "Open your Optum Bank account";

  const wait = makeNode("delay");
  wait.delayValue = 3;
  wait.delayUnit = "days";

  const cond = makeNode("condition");
  cond.conditionKind = "opened";
  cond.conditionLabel = "If opened the previous email";

  const yesEmail = makeNode("email");
  yesEmail.name = "Warm follow-up: same-day settlement";
  if (yesEmail.variants?.[0])
    yesEmail.variants[0].subject = "Settle Optum Pay payments same-day, no fee";

  const noEmail = makeNode("email");
  noEmail.name = "Recovery: your offer is still waiting";
  if (noEmail.variants?.[0]) noEmail.variants[0].subject = "Your Optum Bank offer is still open";

  cond.yes = [yesEmail];
  cond.no = [noEmail];

  const exit = makeNode("exit");

  return { nodes: [first, wait, cond, exit], goal: "account_funded" };
}

export function CampaignBuilder() {
  const data = useData((s) => s.data)!;
  const activeConnector = useData((s) => s.activeConnector);
  const setActiveConnector = useData((s) => s.setActiveConnector);
  const launchCampaign = useData((s) => s.launchCampaign);
  const role = useRole((s) => s.role);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [step, setStep] = useState(0);

  const querySegId = searchParams.get("segment");
  const preSeg =
    querySegId && data.segments.some((s) => s.id === querySegId)
      ? querySegId
      : null;

  const [triggerType, setTriggerType] = useState<"segment" | "event">("segment");
  const [segmentId, setSegmentId] = useState<string | null>(
    preSeg ?? data.segments[0]?.id ?? null
  );
  const [eventType, setEventType] = useState<FunnelEventType>(FUNNEL_EVENTS[0]);
  const [connector, setConnector] = useState<Campaign["connector"]>(activeConnector);
  const [journey, setJourney] = useState<Journey>(() => seedJourney());
  const [templateKey, setTemplateKey] = useState<string>("blank");

  // Card templates whose trigger is a segment map to a seeded card segment.
  const CARD_TEMPLATE_SEGMENT: Record<string, string> = {
    acquisition: "seg_card_loc_nocard",
    spend_growth: "seg_card_lowutil",
  };

  const applyTemplate = (key: string) => {
    setTemplateKey(key);
    if (key === "blank") {
      setJourney(seedJourney());
      return;
    }
    const tpl = CARD_TEMPLATES.find((t) => t.key === key);
    if (!tpl) return;
    setJourney(tpl.build());
    if (tpl.trigger.type === "event" && tpl.trigger.event) {
      setTriggerType("event");
      setEventType(tpl.trigger.event);
    } else {
      setTriggerType("segment");
      const segId = CARD_TEMPLATE_SEGMENT[key];
      if (segId && data.segments.some((s) => s.id === segId)) setSegmentId(segId);
    }
  };

  const segment: Segment | undefined = useMemo(
    () => data.segments.find((s) => s.id === segmentId),
    [data.segments, segmentId]
  );

  const trigger: CampaignTrigger = useMemo(
    () =>
      triggerType === "segment"
        ? { type: "segment", segmentId: segmentId ?? undefined }
        : { type: "event", event: eventType },
    [triggerType, segmentId, eventType]
  );

  const audienceSize = useMemo(() => {
    if (triggerType === "segment" && segment) {
      if (segment.rules) return countMatches(data, segment.rules);
      return segment.size;
    }
    if (triggerType === "event") {
      return data.funnelEvents.filter((e) => e.eventType === eventType).length;
    }
    return 0;
  }, [triggerType, segment, eventType, data]);

  const firstSubject = useMemo(() => {
    for (const n of journey.nodes) {
      if (n.type === "email") return n.variants?.[0]?.subject ?? "Email";
    }
    return "Lifecycle campaign";
  }, [journey]);

  const outline = useMemo(() => flattenJourney(journey), [journey]);

  const canAdvance =
    (step === 0 && (triggerType === "event" || !!segment)) ||
    step === 1 ||
    (step === 2 && !!connector) ||
    step === 3;

  const chooseConnector = (name: Campaign["connector"]) => {
    setConnector(name);
    setActiveConnector(name);
  };

  const launch = () => {
    const triggerName =
      triggerType === "segment"
        ? segment?.name ?? "Segment"
        : FUNNEL_EVENT_LABEL[eventType];
    const c: Campaign = {
      id: `camp_${Date.now()}`,
      name: `${triggerName} - ${firstSubject}`,
      status: "active",
      segmentName: triggerType === "segment" ? segment?.name ?? "Segment" : triggerName,
      connector,
      journeySteps: journeySteps(journey),
      audienceSize,
      metrics: { sent: 0, delivered: 0, opens: 0, clicks: 0, conversions: 0 },
      createdByRole: ROLE_LABEL[role],
      launchedAt: NOW_ISO,
      trigger,
      journey,
    };
    launchCampaign(c);
    toast("Campaign launched (mock)");
    navigate("/campaigns");
  };

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Lifecycle"
        title="New campaign"
        sub="Trigger, journey, delivery, launch."
      />
      <Panel>
        <div className="panel-pad">
          <Stepper steps={STEPS} current={step} />
        </div>
      </Panel>

      {step === 0 && (
        <div className="col gap-4">
          <Panel>
            <PanelHeader
              title="Start from a template"
              action={<span className="tiny muted">Provider Card + LOC lifecycle</span>}
            />
            <div className="panel-body">
              <div className="tmpl-grid">
                <button
                  className={`tmpl-card${templateKey === "blank" ? " selected" : ""}`}
                  onClick={() => applyTemplate("blank")}
                >
                  <div className="tmpl-stage">Standard</div>
                  <div className="tmpl-label">Blank lifecycle</div>
                  <div className="tmpl-desc">Start from the default journey and build your own.</div>
                </button>
                {CARD_TEMPLATES.map((t) => (
                  <button
                    key={t.key}
                    className={`tmpl-card${templateKey === t.key ? " selected" : ""}`}
                    onClick={() => applyTemplate(t.key)}
                  >
                    <div className="tmpl-stage">{t.stage}</div>
                    <div className="tmpl-label">{t.label}</div>
                    <div className="tmpl-desc">{t.description}</div>
                  </button>
                ))}
              </div>
            </div>
          </Panel>

          <div className="grid grid-2">
            <div
              className={`connector-card${triggerType === "segment" ? " selected" : ""}`}
              onClick={() => setTriggerType("segment")}
            >
              <div className="row between">
                <span className="cc-name row gap-2 center">
                  <Users size={16} /> Segment-triggered
                </span>
              </div>
              <div className="tiny muted" style={{ marginTop: 8 }}>
                Enroll providers as they enter a segment. Live from the provider master.
              </div>
            </div>
            <div
              className={`connector-card${triggerType === "event" ? " selected" : ""}`}
              onClick={() => setTriggerType("event")}
            >
              <div className="row between">
                <span className="cc-name row gap-2 center">
                  <Zap size={16} /> Event-triggered
                </span>
              </div>
              <div className="tiny muted" style={{ marginTop: 8 }}>
                Enroll providers the moment a funnel event is performed.
              </div>
            </div>
          </div>

          {triggerType === "segment" ? (
            <Panel>
              <PanelHeader
                title="Pick a segment"
                action={
                  <Button variant="text" onClick={() => navigate("/segments/new")}>
                    <Plus size={14} /> Build a new segment
                  </Button>
                }
              />
              <div className="panel-body col">
                {data.segments.map((s) => (
                  <div
                    key={s.id}
                    className={`segpick${segmentId === s.id ? " selected" : ""}`}
                    onClick={() => setSegmentId(s.id)}
                  >
                    <div className="row between">
                      <span className="strong">{s.name}</span>
                      <span className="num strong" style={{ color: "var(--navy)" }}>
                        {num(s.size)}
                      </span>
                    </div>
                    <div className="tiny muted upper" style={{ marginTop: 4 }}>
                      {s.funnelStage}
                    </div>
                  </div>
                ))}
              </div>
            </Panel>
          ) : (
            <Panel>
              <PanelHeader title="Pick a trigger event" />
              <div className="panel-body">
                <Field label="Enroll when this event is performed">
                  <select
                    className="select"
                    value={eventType}
                    onChange={(e) => setEventType(e.target.value as FunnelEventType)}
                  >
                    {FUNNEL_EVENTS.map((ev) => (
                      <option key={ev} value={ev}>
                        {FUNNEL_EVENT_LABEL[ev]}
                      </option>
                    ))}
                  </select>
                </Field>
                <div className="small muted" style={{ marginTop: 10 }}>
                  {num(audienceSize)} providers have performed this event historically.
                </div>
              </div>
            </Panel>
          )}
        </div>
      )}

      {step === 1 && (
        <Panel>
          <PanelHeader title="Design the journey" />
          <div className="panel-body">
            <JourneyBuilder value={journey} onChange={setJourney} trigger={trigger} />
          </div>
        </Panel>
      )}

      {step === 2 && (
        <div className="col gap-4">
          <Panel>
            <PanelHeader title="Choose a delivery connector" />
            <div className="panel-body grid grid-2">
              {data.connectors.filter((cn) => cn.lifecycle !== "legacy").map((cn) => (
                <div
                  key={cn.id}
                  className={`connector-card${connector === cn.name ? " selected" : ""}`}
                  onClick={() => chooseConnector(cn.name)}
                >
                  <div className="row between">
                    <span className="cc-name">{cn.name}</span>
                    {cn.isApprovedVendor && (
                      <Pill tone="green" dot>
                        Approved vendor
                      </Pill>
                    )}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 8 }}>
                    {cn.note}
                  </div>
                </div>
              ))}
            </div>
          </Panel>
          <Banner tone="info">
            The journey model is delivery-agnostic. The same triggers, branches, and A/B
            splits run on whichever approved delivery connector you choose.
          </Banner>
          <div className="row">
            <Pill tone="navy" dot>
              EMR review: privacy, compliance, legal
            </Pill>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="grid grid-2">
          <Panel>
            <PanelHeader title="Summary" />
            <div className="panel-body col gap-2">
              <SummaryRow
                label="Trigger"
                value={
                  triggerType === "segment"
                    ? `Segment entry: ${segment?.name ?? "-"}`
                    : `Event: ${FUNNEL_EVENT_LABEL[eventType]}`
                }
              />
              <SummaryRow label="Audience size" value={num(audienceSize)} />
              <SummaryRow label="Connector" value={connector} />
              <SummaryRow label="Created by" value={ROLE_LABEL[role]} />
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Journey steps" />
            <div className="panel-body col gap-1">
              {outline.map((o, i) => (
                <div
                  key={i}
                  className="small"
                  style={{ paddingLeft: o.depth * 16 }}
                >
                  {o.depth > 0 ? "- " : ""}
                  {o.label}
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Launch" />
            <div className="panel-body col gap-3">
              <div className="strong" style={{ fontSize: 16 }}>
                Ready to launch to {num(audienceSize)} providers via {connector}.
              </div>
              <div className="small muted">
                No real messages are sent from this prototype.
              </div>
              <div className="row gap-2 wrap">
                <Pill tone="navy" dot>
                  EMR review: privacy, compliance, legal
                </Pill>
              </div>
              <div className="row gap-2" style={{ marginTop: 4 }}>
                <Button size="lg" onClick={launch}>
                  Launch campaign
                </Button>
              </div>
            </div>
          </Panel>
        </div>
      )}

      <div className="row between">
        <Button
          variant="outline"
          onClick={() => setStep((s) => Math.max(0, s - 1))}
          disabled={step === 0}
        >
          <ArrowLeft size={15} /> Back
        </Button>
        {step < STEPS.length - 1 && (
          <Button onClick={() => setStep((s) => s + 1)} disabled={!canAdvance}>
            Next <ArrowRight size={15} />
          </Button>
        )}
        {step === STEPS.length - 1 && (
          <Pill tone="outline">
            <ShieldCheck size={13} /> Compliance-gated launch
          </Pill>
        )}
      </div>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="row between">
      <span className="small muted">{label}</span>
      <span className="small strong right">{value}</span>
    </div>
  );
}
