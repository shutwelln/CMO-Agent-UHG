import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { ShieldCheck, Mail, MessageSquare, ArrowRight, ArrowLeft } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Stepper,
  Field,
  useToast,
} from "../../components/ui";
import { useData } from "../../data/store";
import type { Campaign, Persona, Product, Provider, Segment } from "../../data/schema";
import { PERSONAS, PRODUCTS, PRODUCT_LABEL } from "../../data/schema";
import { fdmForProvider } from "../../data/selectors";
import { useRole, ROLE_LABEL } from "../../context/role";
import { PERSONA_DETAIL } from "../../lib/personas";
import { num } from "../../lib/format";

const STEPS = ["Segment", "Message", "Connector", "Preview", "Launch"];
const NOW_ISO = "2026-08-22T12:00:00.000Z";

interface Template {
  id: string;
  name: string;
  stage: "onboarding" | "drop-off recovery" | "retention";
  detail: string;
}

const TEMPLATES: Template[] = [
  {
    id: "t_intro_apy",
    name: "3% intro APY",
    stage: "onboarding",
    detail: "Open the operating account with a 3% intro APY on balances.",
  },
  {
    id: "t_same_day",
    name: "Settle Optum Pay payments same-day for FREE",
    stage: "onboarding",
    detail: "Redirect Optum Pay flows for same-day settlement, no fee.",
  },
  {
    id: "t_bundle_apr",
    name: "Save 0.25% APR with the bank + loan bundle",
    stage: "retention",
    detail: "0.25% APR reduction when the bank account is opened alongside the loan.",
  },
  {
    id: "t_kyc_recovery",
    name: "Recovery: finish opening your account",
    stage: "drop-off recovery",
    detail: "Nudge stuck signups to complete KYC and fund the account.",
  },
  {
    id: "t_reconciliation",
    name: "Never miss a settled claim payment",
    stage: "retention",
    detail: "Reconciliation and settlement alerts for high-volume payers.",
  },
  {
    id: "t_reengage",
    name: "Your pre-qualified working capital offer",
    stage: "drop-off recovery",
    detail: "Re-engage funded-no-loan providers with a lending-led offer.",
  },
];

const STAGE_TONE: Record<Template["stage"], string> = {
  onboarding: "blue",
  "drop-off recovery": "amber",
  retention: "teal",
};

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
  const [segmentId, setSegmentId] = useState<string | null>(
    querySegId && data.segments.some((s) => s.id === querySegId)
      ? querySegId
      : data.segments[0]?.id ?? null
  );
  const [persona, setPersona] = useState<Persona | "">("");
  const [product, setProduct] = useState<Product | "">("");
  const [minOffer, setMinOffer] = useState(0);
  const [connector, setConnector] = useState<Campaign["connector"]>(activeConnector);
  const [templateId, setTemplateId] = useState<string>(TEMPLATES[0].id);

  const segment: Segment | undefined = useMemo(
    () => data.segments.find((s) => s.id === segmentId),
    [data.segments, segmentId]
  );

  const baseSize = segment?.size ?? 0;
  const liveCount = useMemo(() => {
    let n = baseSize;
    if (persona) n *= 0.35;
    if (product) n *= 0.6;
    if (minOffer > 0) n *= 0.7;
    return Math.round(n);
  }, [baseSize, persona, product, minOffer]);

  const template = TEMPLATES.find((t) => t.id === templateId) ?? TEMPLATES[0];

  const hookLine = persona ? PERSONA_DETAIL[persona].hook : "Your Optum banking offer is ready.";

  const journeySteps = useMemo(
    () => [
      { day: 0, channel: "email", template: template.name },
      { day: 3, channel: "email", template: `${template.name} - reminder` },
      { day: 7, channel: "sms", template: `${template.name} - final nudge` },
    ],
    [template]
  );

  const previewProviders: Provider[] = useMemo(() => {
    const pool = persona
      ? data.providers.filter((p) => p.persona === persona)
      : data.providers;
    return pool.slice(0, 8);
  }, [data.providers, persona]);

  const canAdvance =
    (step === 0 && !!segment) ||
    (step === 1 && !!templateId) ||
    (step === 2 && !!connector) ||
    step === 3 ||
    step === 4;

  const chooseConnector = (name: Campaign["connector"]) => {
    setConnector(name);
    setActiveConnector(name);
  };

  const launch = () => {
    if (!segment) return;
    const c: Campaign = {
      id: `camp_${Date.now()}`,
      name: `${segment.name} - ${template.name}`,
      status: "active",
      segmentName: segment.name,
      connector,
      journeySteps,
      audienceSize: liveCount,
      metrics: { sent: 0, delivered: 0, opens: 0, clicks: 0, conversions: 0 },
      createdByRole: ROLE_LABEL[role],
      launchedAt: NOW_ISO,
    };
    launchCampaign(c);
    toast(`Campaign launched to ${num(liveCount)} providers via ${connector}`);
    navigate("/campaigns");
  };

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Lifecycle"
        title="New campaign"
        sub="Define a segment, pick a message, launch a lifecycle journey"
      />
      <Panel>
        <div className="panel-pad">
          <Stepper steps={STEPS} current={step} />
        </div>
      </Panel>

      {step === 0 && (
        <div className="grid grid-2">
          <Panel>
            <PanelHeader title="1. Pick a segment" />
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

          <div className="col gap-4">
            <Panel>
              <PanelHeader title="2. Refine (optional)" />
              <div className="panel-body col gap-3">
                <Field label="Persona">
                  <select
                    className="select"
                    value={persona}
                    onChange={(e) => setPersona(e.target.value as Persona | "")}
                  >
                    <option value="">All personas</option>
                    {PERSONAS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Product interest">
                  <select
                    className="select"
                    value={product}
                    onChange={(e) => setProduct(e.target.value as Product | "")}
                  >
                    <option value="">Any product</option>
                    {PRODUCTS.map((p) => (
                      <option key={p} value={p}>
                        {PRODUCT_LABEL[p]}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Minimum offer amount">
                  <input
                    type="number"
                    min={0}
                    step={5000}
                    value={minOffer}
                    onChange={(e) => setMinOffer(Math.max(0, Number(e.target.value) || 0))}
                  />
                </Field>
              </div>
            </Panel>

            <div className="audience-counter">
              <div className="ac-num" key={liveCount}>
                {segment ? num(liveCount) : "-"}
              </div>
              <div className="ac-label">providers match, updated live</div>
            </div>
            <div className="small muted center">
              Live from the provider master. The old way was a 4-8 week list pull.
            </div>
          </div>
        </div>
      )}

      {step === 1 && (
        <div className="col gap-4">
          <Panel>
            <PanelHeader title="Choose a message template" />
            <div className="panel-body grid grid-3">
              {TEMPLATES.map((t) => (
                <div
                  key={t.id}
                  className={`segpick${templateId === t.id ? " selected" : ""}`}
                  onClick={() => setTemplateId(t.id)}
                >
                  <Pill tone={STAGE_TONE[t.stage]}>{t.stage}</Pill>
                  <div className="strong" style={{ marginTop: 8 }}>
                    {t.name}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 4 }}>
                    {t.detail}
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Journey" />
            <div className="panel-body">
              <div className="small muted" style={{ marginBottom: 12 }}>
                Persona-matched hook: {hookLine}
              </div>
              {journeySteps.map((j) => (
                <div key={j.day} className="journey-step">
                  <span className="js-day">Day {j.day}</span>
                  {j.channel === "email" ? (
                    <Mail size={16} style={{ color: "var(--navy)" }} />
                  ) : (
                    <MessageSquare size={16} style={{ color: "var(--orange)" }} />
                  )}
                  <span className="small strong upper" style={{ width: 46 }}>
                    {j.channel}
                  </span>
                  <span className="small grow">{j.template}</span>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      )}

      {step === 2 && (
        <Panel>
          <PanelHeader title="Choose a delivery connector" />
          <div className="panel-body grid grid-2">
            {data.connectors.map((cn) => (
              <div
                key={cn.id}
                className={`connector-card${connector === cn.name ? " selected" : ""}`}
                onClick={() => chooseConnector(cn.name)}
              >
                <div className="row between">
                  <span className="cc-name">{cn.name}</span>
                  {cn.isApprovedVendor ? (
                    <Pill tone="green" dot>
                      Approved vendor
                    </Pill>
                  ) : (
                    <Pill tone="amber" dot>
                      Pending procurement
                    </Pill>
                  )}
                </div>
                <div className="tiny muted" style={{ marginTop: 8 }}>
                  {cn.note}
                </div>
                <div className="small teal-text" style={{ marginTop: 10, color: "var(--teal)" }}>
                  Connection status: connected
                </div>
              </div>
            ))}
          </div>
        </Panel>
      )}

      {step === 3 && (
        <div className="grid grid-2">
          <Panel>
            <PanelHeader title="Summary" />
            <div className="panel-body col gap-2">
              <SummaryRow label="Segment" value={segment?.name ?? "-"} />
              <SummaryRow label="Persona filter" value={persona || "All personas"} />
              <SummaryRow
                label="Product filter"
                value={product ? PRODUCT_LABEL[product] : "Any product"}
              />
              <SummaryRow label="Min offer" value={minOffer > 0 ? num(minOffer) : "None"} />
              <SummaryRow label="Audience size" value={num(liveCount)} />
              <SummaryRow label="Connector" value={connector} />
              <div className="col gap-1" style={{ marginTop: 8 }}>
                <span className="tiny muted upper">Journey</span>
                {journeySteps.map((j) => (
                  <span key={j.day} className="small">
                    Day {j.day}: {j.channel} - {j.template}
                  </span>
                ))}
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Sample recipients" />
            <div className="panel-body col gap-2">
              {previewProviders.map((p) => {
                const fdm = fdmForProvider(data, p.id);
                return (
                  <div key={p.id} className="row between" style={{ padding: "6px 0" }}>
                    <div className="col gap-1">
                      <span className="small strong">{p.legalName}</span>
                      <span className="tiny muted">
                        {fdm ? (
                          <a className="contact-val" href={`mailto:${fdm.email}`} onClick={(e) => e.stopPropagation()}>
                            {fdm.email}
                          </a>
                        ) : (
                          "No FDM email on file"
                        )}
                      </span>
                    </div>
                    <Pill tone="gray">{p.persona}</Pill>
                  </div>
                );
              })}
            </div>
          </Panel>
        </div>
      )}

      {step === 4 && (
        <Panel>
          <PanelHeader title="Launch" />
          <div className="panel-body col gap-3">
            <div className="strong" style={{ fontSize: 16 }}>
              Ready to launch to {num(liveCount)} providers via {connector}.
            </div>
            <div className="small muted">
              This activates the campaign and begins the lifecycle journey.
            </div>
            <div className="row gap-2 wrap" style={{ marginTop: 4 }}>
              <Pill tone="navy" dot>
EMR review: privacy, compliance, legal
              </Pill>
            </div>
            <div className="row gap-2" style={{ marginTop: 8 }}>
              <Button size="lg" onClick={launch} disabled={!segment}>
                Launch campaign
              </Button>
            </div>
          </div>
        </Panel>
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
