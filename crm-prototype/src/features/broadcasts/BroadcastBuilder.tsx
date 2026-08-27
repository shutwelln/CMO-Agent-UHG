import { useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ShieldCheck,
  ArrowRight,
  ArrowLeft,
  Users,
  UploadCloud,
  FileSpreadsheet,
  Send,
  CalendarClock,
  CheckCircle2,
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
import type { Broadcast, BroadcastAudience, Campaign, Segment } from "../../data/schema";
import { countMatches } from "../../lib/segmentEngine";
import { useRole, ROLE_LABEL } from "../../context/role";
import { num } from "../../lib/format";
import { defaultBroadcastBlocks, contentBlockCount } from "../../lib/emailBlocks";
import type { EmailBlock } from "../../data/schema";
import { EmailBlockBuilder } from "./EmailBlockBuilder";

const STEPS = ["Audience", "Design", "Schedule", "Review"];
const NOW_ISO = "2026-08-26T12:00:00.000Z";

/* A sample uploaded list, so the upload path can be previewed end-to-end. */
const SAMPLE_LIST = {
  listName: "provider_list_aug2026.csv",
  uploadedCount: 512,
  matchedCount: 468,
};

export function BroadcastBuilder() {
  const data = useData((s) => s.data)!;
  const activeConnector = useData((s) => s.activeConnector);
  const setActiveConnector = useData((s) => s.setActiveConnector);
  const sendBroadcast = useData((s) => s.sendBroadcast);
  const role = useRole((s) => s.role);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const [step, setStep] = useState(0);

  const querySegId = searchParams.get("segment");
  const preSeg =
    querySegId && data.segments.some((s) => s.id === querySegId) ? querySegId : null;

  // audience
  const [audienceKind, setAudienceKind] = useState<"segment" | "upload">("segment");
  const [segmentId, setSegmentId] = useState<string | null>(
    preSeg ?? data.segments[0]?.id ?? null
  );
  const [upload, setUpload] = useState<typeof SAMPLE_LIST | null>(null);

  // content
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("Your update from Optum Bank");
  const [preheader, setPreheader] = useState(
    "A banking offer built around how you already get paid."
  );
  const [fromName, setFromName] = useState("Optum Bank");
  const [fromEmail, setFromEmail] = useState("no-reply@optumbank.com");
  const [replyTo, setReplyTo] = useState("provider-team@optumbank.com");
  const [blocks, setBlocks] = useState<EmailBlock[]>(() => defaultBroadcastBlocks());

  // delivery + schedule
  const [connector, setConnector] = useState<Campaign["connector"]>(activeConnector);
  const [scheduleMode, setScheduleMode] = useState<"now" | "scheduled">("now");
  const [sendAt, setSendAt] = useState<string>("2026-08-29T09:00");

  const segment: Segment | undefined = useMemo(
    () => data.segments.find((s) => s.id === segmentId),
    [data.segments, segmentId]
  );

  const audienceSize = useMemo(() => {
    if (audienceKind === "upload") return upload?.matchedCount ?? 0;
    if (segment) return segment.rules ? countMatches(data, segment.rules) : segment.size;
    return 0;
  }, [audienceKind, upload, segment, data]);

  const audienceLabel =
    audienceKind === "upload"
      ? upload?.listName ?? "Uploaded list"
      : segment?.name ?? "Segment";

  const canAdvance =
    (step === 0 && (audienceKind === "segment" ? !!segment : !!upload)) ||
    (step === 1 && contentBlockCount(blocks) > 0 && subject.trim().length > 0) ||
    (step === 2 && !!connector && (scheduleMode === "now" || !!sendAt)) ||
    step === 3;

  const chooseConnector = (n: Campaign["connector"]) => {
    setConnector(n);
    setActiveConnector(n);
  };

  const send = () => {
    const audience: BroadcastAudience =
      audienceKind === "upload"
        ? {
            kind: "upload",
            listName: upload?.listName,
            uploadedCount: upload?.uploadedCount,
            matchedCount: upload?.matchedCount,
          }
        : { kind: "segment", segmentId: segment?.id, segmentName: segment?.name };

    const scheduled = scheduleMode === "scheduled";
    const sendAtIso = scheduled ? new Date(sendAt).toISOString() : null;

    const b: Broadcast = {
      id: `bcast_${Date.now()}`,
      name: name.trim() || subject.trim() || "Untitled broadcast",
      status: scheduled ? "scheduled" : "sent",
      subject: subject.trim(),
      preheader: preheader.trim(),
      fromName,
      fromEmail,
      replyTo,
      blocks,
      audience,
      connector,
      audienceSize,
      schedule: scheduled ? { mode: "scheduled", sendAt: sendAtIso! } : { mode: "now" },
      metrics: scheduled
        ? { sent: 0, delivered: 0, opens: 0, clicks: 0, unsubscribes: 0 }
        : {
            sent: audienceSize,
            delivered: Math.round(audienceSize * 0.98),
            opens: 0,
            clicks: 0,
            unsubscribes: 0,
          },
      createdByRole: ROLE_LABEL[role],
      sentAt: scheduled ? null : NOW_ISO,
      scheduledFor: sendAtIso,
    };
    sendBroadcast(b);
    toast(scheduled ? "Broadcast scheduled (mock)" : "Broadcast sent (mock)");
    navigate("/broadcasts");
  };

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Broadcasts"
        title="New broadcast"
        sub="Send a one-off email or newsletter to a segment or an uploaded list."
      />
      <Panel>
        <div className="panel-pad">
          <Stepper steps={STEPS} current={step} />
        </div>
      </Panel>

      {/* ---- Step 0: Audience ---- */}
      {step === 0 && (
        <div className="col gap-4">
          <div className="grid grid-2">
            <div
              className={`connector-card${audienceKind === "segment" ? " selected" : ""}`}
              onClick={() => setAudienceKind("segment")}
            >
              <span className="cc-name row gap-2 center">
                <Users size={16} /> Predefined segment
              </span>
              <div className="tiny muted" style={{ marginTop: 8 }}>
                Send to a saved audience, resolved from the provider master at send time.
              </div>
            </div>
            <div
              className={`connector-card${audienceKind === "upload" ? " selected" : ""}`}
              onClick={() => setAudienceKind("upload")}
            >
              <span className="cc-name row gap-2 center">
                <UploadCloud size={16} /> Upload a list
              </span>
              <div className="tiny muted" style={{ marginTop: 8 }}>
                Bring your own list of providers for this send only. Matched on TIN or email.
              </div>
            </div>
          </div>

          {audienceKind === "segment" ? (
            <Panel>
              <PanelHeader title="Pick a segment" />
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
              <PanelHeader title="Upload a provider list" />
              <div className="panel-body col gap-3">
                {upload ? (
                  <>
                    <div className="filecard">
                      <span className="fc-ico">
                        <FileSpreadsheet size={22} />
                      </span>
                      <div className="grow">
                        <div className="strong">{upload.listName}</div>
                        <div className="small muted">
                          {num(upload.uploadedCount)} rows uploaded, {num(upload.matchedCount)}{" "}
                          matched to a provider on TIN or email
                        </div>
                      </div>
                      <Pill tone="green" dot>
                        Ready
                      </Pill>
                    </div>
                    <Banner tone="warn">
                      {num(upload.uploadedCount - upload.matchedCount)} rows did not match a
                      provider and will be skipped. Only matched, opted-in providers receive this
                      send.
                    </Banner>
                    <div>
                      <Button variant="text" onClick={() => setUpload(null)}>
                        Replace file
                      </Button>
                    </div>
                  </>
                ) : (
                  <div className="dropzone">
                    <div className="dz-ico">
                      <UploadCloud size={26} />
                    </div>
                    <div className="strong" style={{ fontSize: 16 }}>
                      Drop a .csv or .xlsx of providers
                    </div>
                    <div
                      className="small muted"
                      style={{ marginTop: 6, maxWidth: 460, marginInline: "auto" }}
                    >
                      Include a TIN or email column so rows can be matched to the provider master.
                      This list is used for this broadcast only.
                    </div>
                    <div style={{ marginTop: 16 }}>
                      <Button variant="primary" onClick={() => setUpload(SAMPLE_LIST)}>
                        Use sample list
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </Panel>
          )}

          <Banner tone="info">
            Estimated recipients:{" "}
            <span className="strong">{num(audienceSize)} providers</span>. Each provider receives
            this message once.
          </Banner>
        </div>
      )}

      {/* ---- Step 1: Design ---- */}
      {step === 1 && (
        <div className="col gap-4">
          <Panel>
            <PanelHeader title="Email details" />
            <div className="panel-body ee-fields">
              <div className="full">
                <Field label="Broadcast name (internal)">
                  <input
                    className="select"
                    value={name}
                    placeholder="August provider newsletter"
                    onChange={(e) => setName(e.target.value)}
                  />
                </Field>
              </div>
              <div className="full">
                <Field label="Subject line">
                  <input
                    className="select"
                    value={subject}
                    onChange={(e) => setSubject(e.target.value)}
                  />
                </Field>
              </div>
              <div className="full">
                <Field label="Preheader">
                  <input
                    className="select"
                    value={preheader}
                    onChange={(e) => setPreheader(e.target.value)}
                  />
                </Field>
              </div>
              <Field label="From name">
                <input
                  className="select"
                  value={fromName}
                  onChange={(e) => setFromName(e.target.value)}
                />
              </Field>
              <Field label="From email">
                <input
                  className="select"
                  value={fromEmail}
                  onChange={(e) => setFromEmail(e.target.value)}
                />
              </Field>
              <div className="full">
                <Field label="Reply-to (optional)">
                  <input
                    className="select"
                    value={replyTo}
                    onChange={(e) => setReplyTo(e.target.value)}
                  />
                </Field>
              </div>
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Build the email" />
            <div className="panel-body">
              <EmailBlockBuilder
                blocks={blocks}
                onChange={setBlocks}
                subject={subject}
                preheader={preheader}
              />
            </div>
          </Panel>
        </div>
      )}

      {/* ---- Step 2: Schedule ---- */}
      {step === 2 && (
        <div className="col gap-4">
          <Panel>
            <PanelHeader title="When should this send?" />
            <div className="panel-body grid grid-2">
              <div
                className={`connector-card${scheduleMode === "now" ? " selected" : ""}`}
                onClick={() => setScheduleMode("now")}
              >
                <span className="cc-name row gap-2 center">
                  <Send size={16} /> Send now
                </span>
                <div className="tiny muted" style={{ marginTop: 8 }}>
                  Deliver to all {num(audienceSize)} recipients as soon as it clears review.
                </div>
              </div>
              <div
                className={`connector-card${scheduleMode === "scheduled" ? " selected" : ""}`}
                onClick={() => setScheduleMode("scheduled")}
              >
                <span className="cc-name row gap-2 center">
                  <CalendarClock size={16} /> Schedule for later
                </span>
                <div className="tiny muted" style={{ marginTop: 8 }}>
                  Pick a date and time. The audience is recalculated at send time.
                </div>
              </div>
            </div>
            {scheduleMode === "scheduled" && (
              <div className="panel-body" style={{ paddingTop: 0 }}>
                <Field label="Send date & time">
                  <input
                    type="datetime-local"
                    className="select"
                    value={sendAt}
                    onChange={(e) => setSendAt(e.target.value)}
                    style={{ maxWidth: 260 }}
                  />
                </Field>
              </div>
            )}
          </Panel>

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
          <div className="row">
            <Pill tone="navy" dot>
              EMR review: privacy, compliance, legal
            </Pill>
          </div>
        </div>
      )}

      {/* ---- Step 3: Review ---- */}
      {step === 3 && (
        <div className="grid grid-2">
          <Panel>
            <PanelHeader title="Summary" />
            <div className="panel-body col gap-2">
              <SummaryRow label="Broadcast" value={name.trim() || subject.trim() || "Untitled"} />
              <SummaryRow label="Subject" value={subject.trim() || "-"} />
              <SummaryRow
                label="Audience"
                value={`${audienceKind === "upload" ? "Uploaded list" : "Segment"}: ${audienceLabel}`}
              />
              <SummaryRow label="Recipients" value={num(audienceSize)} />
              <SummaryRow
                label="Timing"
                value={
                  scheduleMode === "now"
                    ? "Send now"
                    : `Scheduled: ${new Date(sendAt).toLocaleString("en-US")}`
                }
              />
              <SummaryRow label="Connector" value={connector} />
              <SummaryRow label="Created by" value={ROLE_LABEL[role]} />
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Send" />
            <div className="panel-body col gap-3">
              <div className="strong" style={{ fontSize: 16 }}>
                {scheduleMode === "now"
                  ? `Ready to send to ${num(audienceSize)} providers via ${connector}.`
                  : `Ready to schedule for ${num(audienceSize)} providers via ${connector}.`}
              </div>
              <div className="small muted">No real messages are sent from this prototype.</div>
              <div className="row gap-2 wrap">
                <Pill tone="navy" dot>
                  EMR review: privacy, compliance, legal
                </Pill>
                <Pill tone="outline">
                  <CheckCircle2 size={13} /> One send per provider
                </Pill>
              </div>
              <div className="row gap-2" style={{ marginTop: 4 }}>
                <Button size="lg" onClick={send}>
                  {scheduleMode === "now" ? (
                    <>
                      <Send size={16} /> Send broadcast
                    </>
                  ) : (
                    <>
                      <CalendarClock size={16} /> Schedule broadcast
                    </>
                  )}
                </Button>
              </div>
            </div>
          </Panel>

          <div style={{ gridColumn: "1 / -1" }}>
            <Panel>
              <PanelHeader title="Email preview" />
              <div className="panel-body">
                <EmailBlockBuilder
                  blocks={blocks}
                  onChange={setBlocks}
                  subject={subject}
                  preheader={preheader}
                />
              </div>
            </Panel>
          </div>
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
            <ShieldCheck size={13} /> Compliance-gated send
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
