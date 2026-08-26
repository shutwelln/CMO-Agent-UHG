import { useNavigate } from "react-router-dom";
import { Plus, Play, Pause } from "lucide-react";
import { PageHeader, Panel, Button, Pill, useToast } from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { useData } from "../../data/store";
import type { Campaign } from "../../data/schema";
import { num, pct, relTime } from "../../lib/format";

const STATUS_TONE: Record<Campaign["status"], string> = {
  active: "green",
  paused: "amber",
  draft: "gray",
  complete: "blue",
};

const STATUS_LABEL: Record<Campaign["status"], string> = {
  active: "Active",
  paused: "Paused",
  draft: "Draft",
  complete: "Complete",
};

export function CampaignsList() {
  const data = useData((s) => s.data)!;
  const updateCampaignStatus = useData((s) => s.updateCampaignStatus);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();

  const openRate = (c: Campaign) =>
    c.metrics.delivered > 0 ? (c.metrics.opens / c.metrics.delivered) * 100 : 0;

  const toggle = (c: Campaign) => {
    const next: Campaign["status"] = c.status === "active" ? "paused" : "active";
    updateCampaignStatus(c.id, next);
    toast(next === "paused" ? `Paused "${c.name}"` : `Activated "${c.name}"`);
  };

  const columns: Column<Campaign>[] = [
    {
      key: "name",
      header: "Name",
      sortValue: (c) => c.name,
      render: (c) => (
        <div className="col gap-1">
          <span className="strong">{c.name}</span>
          <span className="tiny muted">Created by {c.createdByRole}</span>
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      sortValue: (c) => c.status,
      render: (c) => (
        <Pill tone={STATUS_TONE[c.status]} dot>
          {STATUS_LABEL[c.status]}
        </Pill>
      ),
    },
    {
      key: "segment",
      header: "Segment",
      sortValue: (c) => c.segmentName,
      render: (c) => <span className="small">{c.segmentName}</span>,
    },
    {
      key: "connector",
      header: "Connector",
      sortValue: (c) => c.connector,
      render: (c) => (
        <div className="col gap-1">
          <Pill tone={c.connector === "Marketo" ? "navy" : "orange"}>{c.connector}</Pill>
          {c.connector === "Customer.io" && (
            <span className="tiny muted">pending procurement</span>
          )}
        </div>
      ),
    },
    {
      key: "audience",
      header: "Audience",
      align: "right",
      sortValue: (c) => c.audienceSize,
      render: (c) => <span className="num">{num(c.audienceSize)}</span>,
    },
    {
      key: "sent",
      header: "Sent",
      align: "right",
      sortValue: (c) => c.metrics.sent,
      render: (c) => <span className="num">{num(c.metrics.sent)}</span>,
    },
    {
      key: "opens",
      header: "Opens",
      align: "right",
      sortValue: (c) => c.metrics.opens,
      render: (c) => (
        <div className="col" style={{ alignItems: "flex-end" }}>
          <span className="num">{num(c.metrics.opens)}</span>
          <span className="tiny muted">{pct(openRate(c))}</span>
        </div>
      ),
    },
    {
      key: "clicks",
      header: "Clicks",
      align: "right",
      sortValue: (c) => c.metrics.clicks,
      render: (c) => <span className="num">{num(c.metrics.clicks)}</span>,
    },
    {
      key: "conv",
      header: "Conv",
      align: "right",
      sortValue: (c) => c.metrics.conversions,
      render: (c) => <span className="num strong">{num(c.metrics.conversions)}</span>,
    },
    {
      key: "launched",
      header: "Launched",
      align: "right",
      sortValue: (c) => (c.launchedAt ? +new Date(c.launchedAt) : 0),
      render: (c) => (
        <span className="small muted">{c.launchedAt ? relTime(c.launchedAt) : "-"}</span>
      ),
    },
    {
      key: "action",
      header: "",
      align: "right",
      render: (c) =>
        c.status === "active" || c.status === "paused" ? (
          <Button
            variant="outline"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              toggle(c);
            }}
          >
            {c.status === "active" ? (
              <>
                <Pause size={13} /> Pause
              </>
            ) : (
              <>
                <Play size={13} /> Activate
              </>
            )}
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Lifecycle"
        title="Lifecycle Campaigns"
        sub="Journeys triggered against provider-master funnel segments"
        action={
          <Button onClick={() => navigate("/campaigns/new")}>
            <Plus size={16} /> New campaign
          </Button>
        }
      />
      <Panel>
        <DataTable
          rows={data.campaigns}
          columns={columns}
          rowKey={(c) => c.id}
          emptyMessage="No campaigns yet. Launch one from the builder."
        />
      </Panel>
    </div>
  );
}
