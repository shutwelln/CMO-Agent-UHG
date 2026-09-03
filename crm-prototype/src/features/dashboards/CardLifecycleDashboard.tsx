import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowRight,
  CreditCard,
  Zap,
  DollarSign,
  Activity as ActivityIcon,
  Gauge,
  MoonStar,
} from "lucide-react";
import { PageHeader, Panel, PanelHeader, StatCard, Button, Pill } from "../../components/ui";
import { useData } from "../../data/store";
import { cardFunnelCounts, cardProgramStats } from "../../data/selectors";
import { money, num, pct } from "../../lib/format";
import { CardFunnelChart } from "./CardFunnelChart";

// Cardholder journey map (mirrors the Mastercard E2E journey deliverable).
const JOURNEY = [
  { stage: "Awareness", touch: "Card offer in Optum Pay and email" },
  { stage: "Acquisition", touch: "Apply and approve on the line of credit" },
  { stage: "Onboarding", touch: "Activation email, early month on book" },
  { stage: "Activation", touch: "Activate the card" },
  { stage: "Spend", touch: "First-spend incentive" },
  { stage: "Growth", touch: "Utilization nudges and staff cards" },
];

export function CardLifecycleDashboard() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();
  const counts = useMemo(() => cardFunnelCounts(data), [data]);
  const stats = useMemo(() => cardProgramStats(data), [data]);
  const cardSegments = data.segments.filter((s) => s.id.startsWith("seg_card_"));

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Card Launch"
        title="Provider Card + LOC lifecycle"
        sub="Acquisition through utilization for the card drawn on the provider line of credit"
      />

      <div className="hero-callout">
        <span className="hc-big">Awareness</span>
        <span className="hc-arrow">
          <ArrowRight size={30} />
        </span>
        <span className="hc-big">Growth</span>
        <div className="hc-body">
          <h3>Own the full card lifecycle</h3>
          <p>
            Move providers from card offer to activation to everyday spend with segment and
            event-triggered journeys. Roadmap product, tied to the line of credit.
          </p>
          <Button variant="orange" onClick={() => navigate("/campaigns/new")}>
            Build a card campaign
          </Button>
        </div>
      </div>

      <div className="grid grid-4">
        <StatCard label="Cards issued" value={num(stats.issued)} icon={<CreditCard size={16} />} />
        <StatCard
          label="Activation rate"
          value={pct(stats.activationRate)}
          icon={<Zap size={16} />}
          iconColor="var(--p-card)"
        />
        <StatCard
          label="First-spend rate"
          value={pct(stats.firstSpendRate)}
          icon={<DollarSign size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="Active spenders"
          value={num(stats.activeSpenders)}
          icon={<ActivityIcon size={16} />}
          iconColor="var(--orange)"
        />
      </div>

      {/* Cardholder journey map */}
      <Panel>
        <PanelHeader title="Cardholder journey map" />
        <div className="panel-body">
          <div className="card-journeymap">
            {JOURNEY.map((j, i) => (
              <div key={j.stage} className="cjm-stage">
                <div className="cjm-top">
                  <span className="cjm-badge">{j.stage}</span>
                  {i < JOURNEY.length - 1 && <ArrowRight size={14} className="cjm-arrow" />}
                </div>
                <div className="cjm-touch">{j.touch}</div>
              </div>
            ))}
          </div>
        </div>
      </Panel>

      <div className="grid grid-2">
        <Panel>
          <PanelHeader title="Card funnel - Awareness to Growth" />
          <div className="panel-body">
            <CardFunnelChart counts={counts} onStageClick={() => navigate("/campaigns/new")} />
          </div>
        </Panel>

        <div className="col gap-4">
          <Panel>
            <PanelHeader
              title="Card program measurement"
              action={<span className="tiny muted">EMOB and utilization KPIs</span>}
            />
            <div className="panel-body col gap-2">
              <MetricRow icon={<Zap size={15} />} label="Activation rate (EMOB)" value={pct(stats.activationRate)} />
              <MetricRow icon={<DollarSign size={15} />} label="First-spend rate" value={pct(stats.firstSpendRate)} />
              <MetricRow icon={<Gauge size={15} />} label="Avg utilization (active)" value={pct(stats.avgUtilization)} />
              <MetricRow icon={<ActivityIcon size={15} />} label="Monthly card spend" value={money(stats.totalMonthlySpend, true)} />
              <MetricRow icon={<MoonStar size={15} />} label="Dormant cardholders" value={num(stats.dormant)} />
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Card lifecycle segments" />
            <div className="panel-body col">
              {cardSegments.map((s) => (
                <div key={s.id} className="listrow">
                  <div className="col gap-1">
                    <div className="lr-title">{s.name}</div>
                    <div className="lr-sub">{num(s.size)} providers</div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/campaigns/new?segment=${s.id}`)}
                  >
                    Target
                  </Button>
                </div>
              ))}
            </div>
          </Panel>
        </div>
      </div>

      <div className="row gap-2 wrap">
        <Pill tone="navy" dot>
          Delivered via SendGrid today
        </Pill>
        <Pill tone="outline">Building toward Adobe Journey Optimizer</Pill>
        <Pill tone="outline">Transactional and marketing sends separated by class</Pill>
      </div>
    </div>
  );
}

function MetricRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="row between center">
      <span className="row gap-2 center small">
        <span style={{ color: "var(--p-card)" }}>{icon}</span>
        {label}
      </span>
      <span className="num strong">{value}</span>
    </div>
  );
}
