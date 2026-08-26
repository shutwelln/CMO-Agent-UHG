import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { ArrowRight, Users, AlertTriangle, Megaphone, TrendingUp } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  StatCard,
  Button,
  Pill,
} from "../../components/ui";
import { useData } from "../../data/store";
import { funnelCounts } from "../../data/selectors";
import { num, pct } from "../../lib/format";
import { FunnelChart } from "./FunnelChart";

export function MarketingDashboard() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();
  const counts = useMemo(() => funnelCounts(data), [data]);

  const activeCampaigns = data.campaigns.filter((c) => c.status === "active");
  const avgOpenRate = useMemo(() => {
    const withDelivery = activeCampaigns.filter((c) => c.metrics.delivered > 0);
    if (withDelivery.length === 0) return 0;
    const total = withDelivery.reduce((s, c) => s + c.metrics.opens / c.metrics.delivered, 0);
    return (total / withDelivery.length) * 100;
  }, [activeCampaigns]);

  return (
    <div className="col gap-4">
      <PageHeader crumb="Dashboard" title="Campaign Management" sub="Self-serve lifecycle campaigns" />

      <div className="hero-callout">
        <span className="hc-big">4-8 wks</span>
        <span className="hc-arrow">
          <ArrowRight size={30} />
        </span>
        <span className="hc-big">seconds</span>
        <div className="hc-body">
          <h3>Self-serve lifecycle campaigns</h3>
          <p>
            Marketing list pulls used to take 4 to 8 weeks. Trigger campaigns against live funnel
            segments in seconds.
          </p>
          <Button variant="orange" onClick={() => navigate("/campaigns/new")}>
            Build a campaign
          </Button>
        </div>
      </div>

      <div className="grid grid-4">
        <StatCard
          label="Providers in funnel"
          value={num(counts.started)}
          icon={<Users size={16} />}
        />
        <StatCard
          label="Stuck mid-funnel"
          value={num(counts.stuck)}
          icon={<AlertTriangle size={16} />}
          iconColor="var(--amber)"
        />
        <StatCard
          label="Active campaigns"
          value={num(activeCampaigns.length)}
          icon={<Megaphone size={16} />}
          iconColor="var(--orange)"
        />
        <StatCard
          label="Avg open rate"
          value={pct(avgOpenRate)}
          icon={<TrendingUp size={16} />}
          iconColor="var(--teal)"
        />
      </div>

      <div className="grid grid-2">
        <Panel>
          <PanelHeader title="Provider funnel - drop-off" />
          <div className="panel-body">
            <FunnelChart counts={counts} onDropClick={() => navigate("/campaigns/new")} />
          </div>
        </Panel>

        <div className="col gap-4">
          <Panel>
            <PanelHeader title="Recoverable segments" />
            <div className="panel-body col">
              {data.segments.map((s) => (
                <div key={s.id} className="listrow">
                  <div className="col gap-1">
                    <div className="lr-title">{s.name}</div>
                    <div className="lr-sub">{num(s.size)} providers</div>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => navigate("/campaigns/new")}>
                    Target
                  </Button>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Connector health" />
            <div className="panel-body col">
              {data.connectors.map((c) => (
                <div key={c.id} className="listrow">
                  <div className="col gap-1">
                    <div className="lr-title">{c.name}</div>
                    <div className="lr-sub">{c.note}</div>
                  </div>
                  <Pill tone={c.status === "connected_mock" ? "green" : "amber"} dot>
                    {c.status === "connected_mock" ? "Connected" : "Not approved"}
                  </Pill>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>
    </div>
  );
}
