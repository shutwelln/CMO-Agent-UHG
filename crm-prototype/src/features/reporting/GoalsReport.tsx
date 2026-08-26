import { useMemo } from "react";
import { Target, TrendingUp, Trophy, DollarSign } from "lucide-react";
import { PageHeader, Panel, PanelHeader, StatCard, Progress, Pill } from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { useData } from "../../data/store";
import type { Goal, Tier } from "../../data/schema";
import { repById } from "../../data/selectors";
import { money, num, pct } from "../../lib/format";

// Q3 2026 runs Jul 1 - Sep 30. As of late August the quarter is ~59% elapsed.
const PACE = 0.59;

function attainment(g: Goal): number {
  return g.targetRevenue > 0 ? (g.attainedRevenue / g.targetRevenue) * 100 : 0;
}

function paceStatus(attPct: number): { label: string; tone: string } {
  const expected = PACE * 100;
  if (attPct >= 100) return { label: "Goal met", tone: "green" };
  if (attPct >= expected + 6) return { label: "Ahead", tone: "green" };
  if (attPct >= expected - 6) return { label: "On track", tone: "blue" };
  if (attPct >= expected - 18) return { label: "Behind", tone: "amber" };
  return { label: "At risk", tone: "red" };
}

function barColor(attPct: number): string {
  const s = paceStatus(attPct);
  return s.tone === "green"
    ? "var(--green)"
    : s.tone === "blue"
    ? "var(--navy)"
    : s.tone === "amber"
    ? "var(--amber)"
    : "var(--red)";
}

const TIER_LABEL: Record<Tier, string> = { senior: "Senior", mid: "Mid", junior: "Junior" };

export function GoalsReport() {
  const data = useData((s) => s.data)!;

  const productGoals = useMemo(
    () => data.goals.filter((g) => g.scope === "product"),
    [data.goals]
  );
  const specialistGoals = useMemo(
    () => data.goals.filter((g) => g.scope === "specialist"),
    [data.goals]
  );

  const totalTarget = data.goals
    .filter((g) => g.scope === "specialist")
    .reduce((s, g) => s + g.targetRevenue, 0);
  const totalAttained = specialistGoals.reduce((s, g) => s + g.attainedRevenue, 0);
  const planPct = totalTarget > 0 ? (totalAttained / totalTarget) * 100 : 0;
  const atGoal = specialistGoals.filter((g) => attainment(g) >= 100).length;
  const onTrackOrBetter = specialistGoals.filter(
    (g) => attainment(g) >= (PACE - 0.06) * 100
  ).length;

  const specColumns: Column<Goal>[] = [
    {
      key: "name",
      header: "Sales Specialist",
      sortValue: (g) => g.refLabel,
      render: (g) => {
        const rep = repById(data, g.refId);
        return (
          <div className="col" style={{ lineHeight: 1.25 }}>
            <span className="strong">{g.refLabel}</span>
            <span className="tiny muted">{rep ? `${TIER_LABEL[rep.seniority]} - ${rep.team}` : ""}</span>
          </div>
        );
      },
    },
    {
      key: "target",
      header: "Target",
      align: "right",
      sortValue: (g) => g.targetRevenue,
      render: (g) => <span className="num">{money(g.targetRevenue, true)}</span>,
    },
    {
      key: "attained",
      header: "Attained",
      align: "right",
      sortValue: (g) => g.attainedRevenue,
      render: (g) => <span className="num strong">{money(g.attainedRevenue, true)}</span>,
    },
    {
      key: "deals",
      header: "Deals",
      align: "right",
      sortValue: (g) => g.attainedDeals,
      render: (g) => (
        <span className="num tiny muted">
          {num(g.attainedDeals)} / {num(g.targetDeals)}
        </span>
      ),
    },
    {
      key: "progress",
      header: "To goal",
      width: 220,
      sortValue: (g) => attainment(g),
      render: (g) => {
        const a = attainment(g);
        return (
          <div className="row gap-3 center">
            <div style={{ flex: 1 }}>
              <Progress value={a} color={barColor(a)} />
            </div>
            <span className="num tiny strong" style={{ width: 38, textAlign: "right" }}>
              {pct(a)}
            </span>
          </div>
        );
      },
    },
    {
      key: "status",
      header: "Status",
      sortValue: (g) => attainment(g),
      render: (g) => {
        const s = paceStatus(attainment(g));
        return (
          <Pill tone={s.tone} dot>
            {s.label}
          </Pill>
        );
      },
    },
  ];

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Reporting"
        title="Goals & Targets"
        sub="Quarterly attainment by sales specialist and product line - Q3 2026"
      />

      <div className="grid grid-4">
        <StatCard
          label="Team revenue target"
          value={money(totalTarget, true)}
          icon={<Target size={16} />}
        />
        <StatCard
          label="Attained to date"
          value={money(totalAttained, true)}
          delta={`${pct(planPct)} of plan`}
          deltaDir={planPct >= PACE * 100 ? "up" : "down"}
          icon={<DollarSign size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="On track or better"
          value={`${onTrackOrBetter} / ${specialistGoals.length}`}
          icon={<TrendingUp size={16} />}
          iconColor="var(--navy)"
        />
        <StatCard
          label="At or above goal"
          value={`${atGoal} / ${specialistGoals.length}`}
          icon={<Trophy size={16} />}
          iconColor="var(--orange)"
        />
      </div>

      <Panel>
        <PanelHeader title="Product line goals" />
        <div className="panel-body grid grid-3">
          {productGoals.map((g) => {
            const a = attainment(g);
            const s = paceStatus(a);
            return (
              <div key={g.id} className="panel-tint" style={{ padding: 16 }}>
                <div className="row between center">
                  <span className="strong">{g.refLabel}</span>
                  <Pill tone={s.tone} dot>
                    {s.label}
                  </Pill>
                </div>
                <div className="row between" style={{ marginTop: 10, marginBottom: 6 }}>
                  <span className="num" style={{ fontSize: 22, fontWeight: 800, color: "var(--navy)" }}>
                    {money(g.attainedRevenue, true)}
                  </span>
                  <span className="tiny muted">of {money(g.targetRevenue, true)}</span>
                </div>
                <Progress value={a} color={barColor(a)} />
                <div className="row between tiny muted" style={{ marginTop: 6 }}>
                  <span className="strong" style={{ color: barColor(a) }}>
                    {pct(a)} to goal
                  </span>
                  <span>
                    {num(g.attainedDeals)} / {num(g.targetDeals)} deals
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Sales specialist goals" />
        <DataTable
          rows={specialistGoals}
          columns={specColumns}
          rowKey={(g) => g.id}
          maxHeight={620}
        />
      </Panel>
    </div>
  );
}
