import { useParams, Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Users,
  UploadCloud,
  Send,
  MailOpen,
  MousePointerClick,
  CalendarClock,
  UserMinus,
} from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Pill,
  StatCard,
  Button,
  EmptyState,
  useToast,
} from "../../components/ui";
import { useData } from "../../data/store";
import { renderBlocksToHtml } from "../../lib/emailBlocks";
import { num, pct, relTime } from "../../lib/format";

const STATUS_TONE: Record<string, string> = {
  draft: "gray",
  scheduled: "amber",
  sending: "blue",
  sent: "green",
};

export function BroadcastDetail() {
  const { id } = useParams();
  const data = useData((s) => s.data)!;
  const updateBroadcastStatus = useData((s) => s.updateBroadcastStatus);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();
  const b = data.broadcasts.find((x) => x.id === id);

  if (!b) {
    return (
      <div className="col gap-4">
        <PageHeader title="Broadcast" />
        <Panel>
          <EmptyState title="Broadcast not found" sub="It may have been removed." />
        </Panel>
      </div>
    );
  }

  const m = b.metrics;
  const openRate = m.delivered ? (m.opens / m.delivered) * 100 : 0;
  const clickRate = m.delivered ? (m.clicks / m.delivered) * 100 : 0;

  const audienceText =
    b.audience.kind === "upload"
      ? b.audience.listName ?? "Uploaded list"
      : b.audience.segmentName ?? "Segment";

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Broadcasts"
        title={b.name}
        sub={
          <span className="row gap-2 center wrap">
            <Pill tone={STATUS_TONE[b.status]} dot>
              {b.status.charAt(0).toUpperCase() + b.status.slice(1)}
            </Pill>
            <Pill tone={b.connector === "Marketo" ? "navy" : "orange"}>{b.connector}</Pill>
            <span className="row gap-1 center small muted">
              {b.audience.kind === "upload" ? <UploadCloud size={13} /> : <Users size={13} />}
              {audienceText}
            </span>
            {b.status === "sent" && b.sentAt && (
              <span className="small muted">Sent {relTime(b.sentAt)}</span>
            )}
            {b.status === "scheduled" && b.scheduledFor && (
              <span className="row gap-1 center small" style={{ color: "var(--amber)" }}>
                <CalendarClock size={13} />
                {new Date(b.scheduledFor).toLocaleString("en-US")}
              </span>
            )}
          </span>
        }
        action={
          <div className="row gap-2">
            {b.status === "scheduled" && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  updateBroadcastStatus(b.id, "draft");
                  toast("Schedule cancelled");
                }}
              >
                Cancel schedule
              </Button>
            )}
            {b.status === "draft" && (
              <Button
                size="sm"
                onClick={() => {
                  updateBroadcastStatus(b.id, "sent");
                  toast("Broadcast sent (mock)");
                }}
              >
                <Send size={14} /> Send now
              </Button>
            )}
            <Link to="/broadcasts">
              <Button variant="outline" size="sm">
                <ArrowLeft size={15} /> All broadcasts
              </Button>
            </Link>
          </div>
        }
      />

      <div className="grid grid-4">
        <StatCard label="Recipients" value={num(b.audienceSize)} icon={<Users size={16} />} />
        <StatCard
          label="Sent"
          value={num(m.sent)}
          icon={<Send size={16} />}
          iconColor="var(--navy)"
        />
        <StatCard
          label="Open rate"
          value={m.delivered ? pct(openRate) : "-"}
          icon={<MailOpen size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="Click rate"
          value={m.delivered ? pct(clickRate) : "-"}
          icon={<MousePointerClick size={16} />}
          iconColor="var(--orange)"
        />
      </div>

      <div className="grid grid-2">
        <Panel>
          <PanelHeader title="Delivery" />
          <div className="panel-body col gap-2">
            <Row label="Subject" value={b.subject} />
            <Row label="Preheader" value={b.preheader || "-"} />
            <Row label="From" value={`${b.fromName} <${b.fromEmail}>`} />
            <Row label="Reply-to" value={b.replyTo || "-"} />
            <Row
              label="Audience"
              value={`${b.audience.kind === "upload" ? "Uploaded list" : "Segment"}: ${audienceText}`}
            />
            {b.audience.kind === "upload" && b.audience.uploadedCount != null && (
              <Row
                label="List match"
                value={`${num(b.audience.matchedCount ?? 0)} of ${num(
                  b.audience.uploadedCount
                )} rows matched`}
              />
            )}
            <Row
              label="Timing"
              value={
                b.status === "scheduled" && b.scheduledFor
                  ? new Date(b.scheduledFor).toLocaleString("en-US")
                  : b.sentAt
                  ? new Date(b.sentAt).toLocaleString("en-US")
                  : "Not sent"
              }
            />
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Engagement" />
          <div className="panel-body col gap-2">
            <Row label="Delivered" value={num(m.delivered)} />
            <Row label="Opens" value={`${num(m.opens)}${m.delivered ? ` (${pct(openRate)})` : ""}`} />
            <Row label="Clicks" value={`${num(m.clicks)}${m.delivered ? ` (${pct(clickRate)})` : ""}`} />
            <Row
              label="Unsubscribes"
              value={
                <span className="row gap-1 center">
                  <UserMinus size={13} /> {num(m.unsubscribes)}
                </span>
              }
            />
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Email preview" />
        <div className="panel-body">
          <div className="bb-preview" style={{ maxWidth: 640, margin: "0 auto" }}>
            <div className="bb-mail">
              <div className="bb-mail-subject">{b.subject || "(no subject)"}</div>
              {b.preheader && <div className="bb-mail-preheader">{b.preheader}</div>}
              <div
                className="bb-mail-body"
                dangerouslySetInnerHTML={{ __html: renderBlocksToHtml(b.blocks) }}
              />
            </div>
          </div>
        </div>
      </Panel>

      <div>
        <Button variant="text" onClick={() => navigate("/broadcasts/new")}>
          Duplicate as new broadcast
        </Button>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="row between">
      <span className="small muted">{label}</span>
      <span className="small strong right">{value}</span>
    </div>
  );
}
