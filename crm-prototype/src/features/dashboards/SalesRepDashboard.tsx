import { useMemo } from "react";
import { Link } from "react-router-dom";
import { Briefcase, DollarSign, Calendar, Target } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  StatCard,
  StageBadge,
  Progress,
  Pill,
  Button,
  EmptyState,
} from "../../components/ui";
import { useData } from "../../data/store";
import {
  leadsForRep,
  repById,
  providerById,
  stageCounts,
  pipelineValue,
} from "../../data/selectors";
import { CURRENT_REP_ID } from "../../context/role";
import { STAGES, STAGE_LABEL } from "../../data/schema";
import { topOfferLabel, nextBestOffers } from "../../lib/nbo";
import { money, num, pct, relTime } from "../../lib/format";

const PACE = 0.59; // Q3 2026 is ~59% elapsed in late August

function goalStatus(attPct: number): { label: string; tone: string; color: string } {
  const e = PACE * 100;
  if (attPct >= 100) return { label: "Goal met", tone: "green", color: "var(--green)" };
  if (attPct >= e + 6) return { label: "Ahead", tone: "green", color: "var(--green)" };
  if (attPct >= e - 6) return { label: "On track", tone: "blue", color: "var(--navy)" };
  if (attPct >= e - 18) return { label: "Behind", tone: "amber", color: "var(--amber)" };
  return { label: "At risk", tone: "red", color: "var(--red)" };
}

export function SalesRepDashboard() {
  const data = useData((s) => s.data)!;
  const rep = repById(data, CURRENT_REP_ID);
  const myLeads = useMemo(() => leadsForRep(data, CURRENT_REP_ID), [data]);

  const openLeads = myLeads.filter((l) => l.stage !== "disbursed" && l.stage !== "closed");
  const pipeline = pipelineValue(myLeads);
  const counts = useMemo(() => stageCounts(data, myLeads), [data, myLeads]);

  const now = new Date("2026-08-22T12:00:00Z").getTime();
  const weekOut = now + 7 * 86_400_000;
  const apptsThisWeek = data.appointments.filter((a) => {
    const t = +new Date(a.scheduledFor);
    return a.repId === CURRENT_REP_ID && t >= now && t <= weekOut;
  }).length;

  const monthStart = +new Date("2026-08-01T00:00:00Z");
  const qualifiedThisMonth = myLeads.filter(
    (l) => l.stage === "kyc" && l.lastOutreachAt && +new Date(l.lastOutreachAt) >= monthStart
  ).length;

  const nboAlerts = useMemo(() => {
    const seen = new Set<string>();
    const out: { providerId: string; label: string; incentive: string | null }[] = [];
    for (const l of myLeads) {
      if (seen.has(l.providerId)) continue;
      const p = providerById(data, l.providerId);
      if (!p) continue;
      seen.add(l.providerId);
      const top = nextBestOffers(p)[0];
      out.push({ providerId: p.id, label: topOfferLabel(p), incentive: top?.incentive ?? null });
      if (out.length >= 5) break;
    }
    return out;
  }, [data, myLeads]);

  const myGoal = data.goals.find((g) => g.scope === "specialist" && g.refId === CURRENT_REP_ID);
  const goalPct = myGoal ? (myGoal.attainedRevenue / myGoal.targetRevenue) * 100 : 0;
  const goalS = goalStatus(goalPct);

  const followUps = useMemo(
    () =>
      [...myLeads]
        .filter((l) => l.stage !== "disbursed" && l.stage !== "closed")
        .sort((a, b) => {
          const at = a.lastOutreachAt ? +new Date(a.lastOutreachAt) : 0;
          const bt = b.lastOutreachAt ? +new Date(b.lastOutreachAt) : 0;
          return at - bt;
        })
        .slice(0, 6),
    [myLeads]
  );

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Dashboard"
        title="My Dashboard"
        sub={rep ? `Signed in as ${rep.name}, ${rep.team}` : undefined}
      />

      <div className="grid grid-4">
        <StatCard
          label="Open leads"
          value={num(openLeads.length)}
          icon={<Briefcase size={16} />}
        />
        <StatCard
          label="Pipeline value"
          value={money(pipeline, true)}
          icon={<DollarSign size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="Appointments this week"
          value={num(apptsThisWeek)}
          icon={<Calendar size={16} />}
          iconColor="var(--orange)"
        />
        <StatCard
          label="Qualified this month"
          value={num(qualifiedThisMonth)}
          icon={<Target size={16} />}
          iconColor="var(--teal)"
        />
      </div>

      {myGoal && (
        <Panel>
          <div className="panel-hd">
            <h3>My Q3 2026 goal</h3>
            <Link to="/reporting/goals">
              <Button variant="text">View all goals</Button>
            </Link>
          </div>
          <div className="panel-body">
            <div className="row between center" style={{ marginBottom: 10 }}>
              <div className="row gap-3 center">
                <span className="num" style={{ fontSize: 26, fontWeight: 800, color: "var(--navy)" }}>
                  {money(myGoal.attainedRevenue, true)}
                </span>
                <span className="muted small">attained of {money(myGoal.targetRevenue, true)} target</span>
              </div>
              <Pill tone={goalS.tone} dot>
                {goalS.label} · {pct(goalPct)}
              </Pill>
            </div>
            <Progress value={goalPct} color={goalS.color} />
            <div className="row between tiny muted" style={{ marginTop: 6 }}>
              <span>
                {num(myGoal.attainedDeals)} / {num(myGoal.targetDeals)} deals closed
              </span>
              <span>Quarter ~59% elapsed</span>
            </div>
          </div>
        </Panel>
      )}

      <div className="grid grid-2">
        <Panel>
          <PanelHeader title="My pipeline by stage" />
          <div className="panel-body col gap-3">
            {STAGES.map((s) => {
              const c = counts[s];
              const denom = Math.max(1, myLeads.length);
              return (
                <div key={s} className="col gap-1">
                  <div className="row between">
                    <span className="small strong">{STAGE_LABEL[s]}</span>
                    <span className="small num">{num(c)}</span>
                  </div>
                  <Progress value={(c / denom) * 100} />
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Next-best-offer alerts" />
          <div className="panel-body col">
            {nboAlerts.length === 0 && (
              <EmptyState title="No offers to surface" sub="Assigned leads will appear here." />
            )}
            {nboAlerts.map((a) => (
              <Link key={a.providerId} to={`/providers/${a.providerId}`} className="listrow">
                <div className="col gap-1">
                  <div className="lr-title">{a.label}</div>
                  {a.incentive && <div className="lr-sub">{a.incentive}</div>}
                </div>
                <Target size={16} style={{ color: "var(--orange)" }} />
              </Link>
            ))}
          </div>
        </Panel>
      </div>

      <Panel>
        <PanelHeader title="Today's follow-ups" />
        <div className="panel-body col">
          {followUps.length === 0 && (
            <EmptyState title="No follow-ups queued" sub="You are all caught up." />
          )}
          {followUps.map((l) => {
            const p = providerById(data, l.providerId);
            return (
              <Link key={l.id} to={`/providers/${l.providerId}`} className="listrow">
                <div className="col gap-1">
                  <div className="lr-title">{p?.legalName ?? "Unknown provider"}</div>
                  <div className="lr-sub">
                    {l.lastOutreachAt ? `Last touch ${relTime(l.lastOutreachAt)}` : "No outreach yet"}
                    {p ? ` · ${p.city}, ${p.state}` : ""}
                  </div>
                </div>
                <StageBadge stage={l.stage} />
              </Link>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
