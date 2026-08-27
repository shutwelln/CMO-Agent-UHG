import { useNavigate } from "react-router-dom";
import { Plus, Users, UploadCloud, Send, CalendarClock } from "lucide-react";
import { PageHeader, Panel, Button, Pill, Banner } from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { useData } from "../../data/store";
import type { Broadcast } from "../../data/schema";
import { num, pct, relTime } from "../../lib/format";

const STATUS_TONE: Record<Broadcast["status"], string> = {
  draft: "gray",
  scheduled: "amber",
  sending: "blue",
  sent: "green",
};
const STATUS_LABEL: Record<Broadcast["status"], string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  sending: "Sending",
  sent: "Sent",
};

export function BroadcastsList() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();

  const openRate = (b: Broadcast) =>
    b.metrics.delivered > 0 ? (b.metrics.opens / b.metrics.delivered) * 100 : 0;

  const columns: Column<Broadcast>[] = [
    {
      key: "name",
      header: "Name",
      sortValue: (b) => b.name,
      render: (b) => (
        <div className="col gap-1">
          <span className="strong">{b.name}</span>
          <span className="tiny muted">{b.subject}</span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortValue: (b) => b.status,
      render: (b) => (
        <Pill tone={STATUS_TONE[b.status]} dot>
          {STATUS_LABEL[b.status]}
        </Pill>
      ),
    },
    {
      key: "audience",
      header: "Audience",
      sortValue: (b) => b.audience.kind,
      render: (b) => (
        <span className="row gap-2 center small">
          {b.audience.kind === "upload" ? <UploadCloud size={14} /> : <Users size={14} />}
          {b.audience.kind === "upload"
            ? b.audience.listName ?? "Uploaded list"
            : b.audience.segmentName ?? "Segment"}
        </span>
      ),
    },
    {
      key: "recipients",
      header: "Recipients",
      align: "right",
      sortValue: (b) => b.audienceSize,
      render: (b) => <span className="num">{num(b.audienceSize)}</span>,
    },
    {
      key: "opens",
      header: "Opens",
      align: "right",
      sortValue: (b) => b.metrics.opens,
      render: (b) =>
        b.metrics.delivered > 0 ? (
          <div className="col" style={{ alignItems: "flex-end" }}>
            <span className="num">{num(b.metrics.opens)}</span>
            <span className="tiny muted">{pct(openRate(b))}</span>
          </div>
        ) : (
          <span className="tiny muted">-</span>
        ),
    },
    {
      key: "clicks",
      header: "Clicks",
      align: "right",
      sortValue: (b) => b.metrics.clicks,
      render: (b) =>
        b.metrics.delivered > 0 ? (
          <span className="num">{num(b.metrics.clicks)}</span>
        ) : (
          <span className="tiny muted">-</span>
        ),
    },
    {
      key: "when",
      header: "Sent / scheduled",
      align: "right",
      sortValue: (b) =>
        b.sentAt ? +new Date(b.sentAt) : b.scheduledFor ? +new Date(b.scheduledFor) : 0,
      render: (b) => {
        if (b.status === "sent" && b.sentAt)
          return <span className="small muted">{relTime(b.sentAt)}</span>;
        if (b.status === "scheduled" && b.scheduledFor)
          return (
            <span className="row gap-1 center small" style={{ justifyContent: "flex-end", color: "var(--amber)" }}>
              <CalendarClock size={13} />
              {new Date(b.scheduledFor).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
              })}
            </span>
          );
        return <span className="tiny muted">-</span>;
      },
    },
  ];

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Broadcasts"
        title="Broadcasts"
        sub="One-off emails and newsletters to a segment or an uploaded provider list"
        action={
          <Button onClick={() => navigate("/broadcasts/new")}>
            <Plus size={16} /> New broadcast
          </Button>
        }
      />
      <Banner tone="info" icon={<Send size={16} />}>
        A broadcast delivers a single email to an audience resolved at send time. Choose a saved
        segment or upload a list for this send only. Each provider receives the message once, and
        preference and unsubscribe rules are always applied.
      </Banner>
      <Panel>
        <DataTable
          rows={data.broadcasts}
          columns={columns}
          rowKey={(b) => b.id}
          onRowClick={(b) => navigate(`/broadcasts/${b.id}`)}
          emptyMessage="No broadcasts yet. Send one from the builder."
        />
      </Panel>
    </div>
  );
}
