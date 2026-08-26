import { useMemo } from "react";
import { Users } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Pill,
  Avatar,
  Progress,
  Banner,
} from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { TierBadge } from "../../components/ui";
import { useData } from "../../data/store";
import type { Rep } from "../../data/schema";
import { leadsForRep } from "../../data/selectors";
import { num } from "../../lib/format";

export function RepsAdmin() {
  const data = useData((s) => s.data)!;

  const assignedCount = useMemo(() => {
    const m = new Map<string, number>();
    for (const r of data.reps) m.set(r.id, leadsForRep(data, r.id).length);
    return m;
  }, [data]);

  const columns: Column<Rep>[] = [
    {
      key: "name",
      header: "Sales Specialist",
      sortValue: (r) => r.name,
      render: (r) => (
        <div className="row gap-2 center">
          <Avatar initials={r.avatarInitials} sm />
          <span className="strong">{r.name}</span>
        </div>
      ),
    },
    {
      key: "seniority",
      header: "Tier",
      sortValue: (r) => r.seniority,
      render: (r) => <TierBadge tier={r.seniority} />,
    },
    {
      key: "team",
      header: "Team",
      sortValue: (r) => r.team,
      render: (r) => <span className="small">{r.team}</span>,
    },
    {
      key: "capacity",
      header: "Capacity",
      align: "right",
      sortValue: (r) => r.capacity,
      render: (r) => <span className="num">{num(r.capacity)}</span>,
    },
    {
      key: "assigned",
      header: "Assigned",
      align: "right",
      sortValue: (r) => assignedCount.get(r.id) ?? 0,
      render: (r) => <span className="num">{num(assignedCount.get(r.id) ?? 0)}</span>,
    },
    {
      key: "load",
      header: "Load",
      width: 160,
      sortValue: (r) => (assignedCount.get(r.id) ?? 0) / Math.max(1, r.capacity),
      render: (r) => {
        const assigned = assignedCount.get(r.id) ?? 0;
        const load = (assigned / Math.max(1, r.capacity)) * 100;
        const color =
          load >= 90 ? "var(--red)" : load >= 70 ? "var(--amber)" : "var(--teal)";
        return (
          <div className="col gap-1">
            <Progress value={load} color={color} />
            <span className="tiny muted num">{Math.round(load)}%</span>
          </div>
        );
      },
    },
    {
      key: "active",
      header: "Active",
      render: (r) =>
        r.active ? (
          <Pill tone="green" dot>
            Active
          </Pill>
        ) : (
          <Pill tone="gray">Inactive</Pill>
        ),
    },
  ];

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Admin"
        title="Sales Specialists &amp; Tiers"
        sub="Capacity and tier-based assignment across internal and 3rd-party call center teams"
      />

      <Banner tone="info" icon={<Users size={16} />}>
        Leads route by tier so deal size matches specialist seniority. Senior specialists take the
        largest offers and net-new relationships; mid and junior specialists handle the mid-market
        and follow-up volume.
      </Banner>

      <Panel>
        <DataTable rows={data.reps} columns={columns} rowKey={(r) => r.id} />
      </Panel>

      <Panel tint>
        <PanelHeader title="Assignment rules" />
        <div className="panel-body col gap-2">
          <div className="row between">
            <span className="small">Offer amount at or above 150K</span>
            <TierBadge tier="senior" />
          </div>
          <div className="row between">
            <span className="small">Offer amount 50K to 150K</span>
            <TierBadge tier="mid" />
          </div>
          <div className="row between">
            <span className="small">Offer amount below 50K</span>
            <TierBadge tier="junior" />
          </div>
        </div>
      </Panel>
    </div>
  );
}
