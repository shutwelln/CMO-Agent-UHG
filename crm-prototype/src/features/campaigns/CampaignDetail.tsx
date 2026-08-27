import { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ArrowLeft, Users, Send, MailOpen, Target } from "lucide-react";
import { PageHeader, Panel, PanelHeader, Pill, StatCard, Button, EmptyState } from "../../components/ui";
import { useData } from "../../data/store";
import type { Journey } from "../../data/schema";
import { JourneyBuilder } from "./JourneyBuilder";
import { num, pct, relTime } from "../../lib/format";

const STATUS_TONE: Record<string, string> = {
  active: "green",
  paused: "amber",
  draft: "gray",
  complete: "blue",
};

function countEmails(j?: Journey): number {
  if (!j) return 0;
  let n = 0;
  const walk = (nodes: import("../../data/schema").JourneyNode[]) => {
    for (const node of nodes) {
      if (node.type === "email") n++;
      if (node.yes) walk(node.yes);
      if (node.no) walk(node.no);
      if (node.branchA) walk(node.branchA);
      if (node.branchB) walk(node.branchB);
    }
  };
  walk(j.nodes);
  return n;
}

export function CampaignDetail() {
  const { id } = useParams();
  const data = useData((s) => s.data)!;
  const campaign = data.campaigns.find((c) => c.id === id);
  const [journey, setJourney] = useState<Journey | undefined>(campaign?.journey);

  if (!campaign) {
    return (
      <div className="col gap-4">
        <PageHeader title="Campaign" />
        <Panel>
          <EmptyState title="Campaign not found" sub="It may have been removed." />
        </Panel>
      </div>
    );
  }

  const m = campaign.metrics;
  const openRate = m.delivered ? (m.opens / m.delivered) * 100 : 0;
  const emails = countEmails(campaign.journey);

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Lifecycle Campaigns"
        title={campaign.name}
        sub={
          <span className="row gap-2 center wrap">
            <Pill tone={STATUS_TONE[campaign.status]} dot>
              {campaign.status.charAt(0).toUpperCase() + campaign.status.slice(1)}
            </Pill>
            <Pill tone={campaign.connector === "Marketo" ? "navy" : "orange"}>{campaign.connector}</Pill>
            <span className="small muted">Segment: {campaign.segmentName}</span>
            <span className="small muted">
              {campaign.launchedAt ? `Launched ${relTime(campaign.launchedAt)}` : "Not launched"}
            </span>
            <span className="small muted">{emails} emails</span>
          </span>
        }
        action={
          <Link to="/campaigns">
            <Button variant="outline" size="sm">
              <ArrowLeft size={15} /> All campaigns
            </Button>
          </Link>
        }
      />

      <div className="grid grid-4">
        <StatCard label="Audience" value={num(campaign.audienceSize)} icon={<Users size={16} />} />
        <StatCard label="Sent" value={num(m.sent)} icon={<Send size={16} />} iconColor="var(--navy)" />
        <StatCard
          label="Open rate"
          value={pct(openRate)}
          icon={<MailOpen size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="Conversions"
          value={num(m.conversions)}
          icon={<Target size={16} />}
          iconColor="var(--orange)"
        />
      </div>

      <Panel>
        <PanelHeader
          title="Journey"
          action={<span className="small muted">Delivered via {campaign.connector}.</span>}
        />
        <div className="panel-body">
          {journey ? (
            <JourneyBuilder value={journey} onChange={setJourney} trigger={campaign.trigger} />
          ) : (
            <EmptyState title="No journey defined" sub="This campaign uses a simple step list." />
          )}
        </div>
      </Panel>
    </div>
  );
}
