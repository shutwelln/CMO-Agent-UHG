import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { FileText, Percent, ShieldCheck, UserCheck, Upload } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  StatCard,
  Banner,
  Button,
  Avatar,
  TierBadge,
  Progress,
} from "../../components/ui";
import { useData } from "../../data/store";
import { leadsForRep, stageCounts, pipelineValue } from "../../data/selectors";
import { STAGES, STAGE_LABEL } from "../../data/schema";
import { OPS_LEAD_NAME } from "../../context/role";
import { money, num, pct } from "../../lib/format";

export function SalesOpsDashboard() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();
  const file = data.sourceFiles[0];

  const matchRate = file ? (file.matchStats.matched / Math.max(1, file.rowCount)) * 100 : 0;
  const fdmCoverage = file ? (file.fdmStats.after / Math.max(1, file.rowCount)) * 100 : 0;
  const assigned = data.leads.filter((l) => l.assignedRepId).length;

  const counts = useMemo(() => stageCounts(data), [data]);

  return (
    <div className="col gap-4">
      <PageHeader crumb="Dashboard" title="Sales Operations" sub={`Signed in as ${OPS_LEAD_NAME} - data ingest, assignment, and pipeline health`} />

      <div className="grid grid-4">
        <StatCard
          label="Latest bank file rows"
          value={file ? num(file.rowCount) : "0"}
          icon={<FileText size={16} />}
        />
        <StatCard
          label="TIN match rate"
          value={pct(matchRate)}
          icon={<Percent size={16} />}
          iconColor="var(--navy)"
        />
        <StatCard
          label="FDM coverage"
          value={pct(fdmCoverage)}
          icon={<ShieldCheck size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard
          label="Leads assigned"
          value={num(assigned)}
          icon={<UserCheck size={16} />}
          iconColor="var(--orange)"
        />
      </div>

      {file &&
        (file.committedAt ? (
          <Banner tone="success" icon={<ShieldCheck size={16} />}>
            File committed. The {file.offerMonth} bank offer file has been ingested.
          </Banner>
        ) : (
          <Banner tone="info" icon={<Upload size={16} />}>
            <div className="row between center wrap gap-3">
              <span>Monthly bank offer file for {file.offerMonth} is ready to ingest</span>
              <Button variant="primary" size="sm" onClick={() => navigate("/ingest")}>
                Open Ingest Wizard
              </Button>
            </div>
          </Banner>
        ))}

      <div className="grid grid-2">
        <Panel>
          <PanelHeader title="Sales specialist load" />
          <div className="panel-body col">
            {data.reps.map((rep) => {
              const load = leadsForRep(data, rep.id).length;
              const capacity = Math.max(1, rep.capacity);
              return (
                <div key={rep.id} className="listrow">
                  <div className="row gap-2 center grow">
                    <Avatar initials={rep.avatarInitials} sm />
                    <div className="col gap-1 grow">
                      <div className="row gap-2 center">
                        <span className="lr-title">{rep.name}</span>
                        <TierBadge tier={rep.seniority} />
                      </div>
                      <div className="lr-sub">{rep.team}</div>
                      <Progress
                        value={(load / capacity) * 100}
                        color={load > capacity ? "var(--amber)" : undefined}
                      />
                    </div>
                  </div>
                  <div className="right small nowrap">
                    <span className="num strong">{num(load)}</span>
                    <span className="faint"> / {num(rep.capacity)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Panel>

        <Panel>
          <PanelHeader title="Team pipeline" />
          <div className="panel-body col">
            {STAGES.map((s) => {
              const stageLeads = data.leads.filter((l) => l.stage === s);
              const value = pipelineValue(stageLeads);
              return (
                <div key={s} className="listrow">
                  <div className="col gap-1">
                    <div className="lr-title">{STAGE_LABEL[s]}</div>
                    <div className="lr-sub">{num(counts[s])} leads</div>
                  </div>
                  <span className="num strong">{money(value, true)}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      </div>
    </div>
  );
}
