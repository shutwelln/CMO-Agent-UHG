import { useMemo } from "react";
import { CalendarClock, CalendarCheck, Presentation } from "lucide-react";
import { PageHeader, Panel, StatCard, Pill, Button, EmptyState, useToast } from "../../components/ui";
import { useData } from "../../data/store";
import type { Appointment, Provider, Rep } from "../../data/schema";
import { dayMonth } from "../../lib/format";

const TYPE_LABEL: Record<Appointment["type"], string> = {
  discovery: "Discovery",
  product_demo: "Product Demo",
  closing: "Closing",
};
const TYPE_TONE: Record<Appointment["type"], string> = {
  discovery: "blue",
  product_demo: "orange",
  closing: "teal",
};
const STATUS_TONE: Record<Appointment["status"], string> = {
  scheduled: "green",
  completed: "navy",
  no_show: "red",
  cancelled: "gray",
};
const STATUS_LABEL: Record<Appointment["status"], string> = {
  scheduled: "Scheduled",
  completed: "Completed",
  no_show: "No Show",
  cancelled: "Cancelled",
};

export function AppointmentsPage() {
  const data = useData((s) => s.data)!;
  const toast = useToast((s) => s.push);

  const provMap = useMemo(() => {
    const m = new Map<string, Provider>();
    for (const p of data.providers) m.set(p.id, p);
    return m;
  }, [data.providers]);
  const repMap = useMemo(() => {
    const m = new Map<string, Rep>();
    for (const r of data.reps) m.set(r.id, r);
    return m;
  }, [data.reps]);

  const sorted = useMemo(
    () =>
      [...data.appointments].sort(
        (a, b) => +new Date(a.scheduledFor) - +new Date(b.scheduledFor)
      ),
    [data.appointments]
  );

  const now = +new Date("2026-08-22T12:00:00Z");
  const weekOut = now + 7 * 86_400_000;
  const scheduled = data.appointments.filter((a) => a.status === "scheduled");
  const thisWeek = scheduled.filter((a) => {
    const t = +new Date(a.scheduledFor);
    return t >= now && t <= weekOut;
  }).length;
  const discovery = data.appointments.filter((a) => a.type === "discovery").length;
  const demo = data.appointments.filter((a) => a.type === "product_demo").length;

  return (
    <div className="col gap-4">
      <PageHeader crumb="Outbound" title="Appointments" sub="Booked meetings with senior sales specialists" />

      <div className="grid grid-4">
        <StatCard label="Total scheduled" value={scheduled.length} icon={<CalendarClock size={16} />} />
        <StatCard
          label="This week"
          value={thisWeek}
          icon={<CalendarCheck size={16} />}
          iconColor="var(--teal)"
        />
        <StatCard label="Discovery" value={discovery} icon={<CalendarClock size={16} />} iconColor="var(--navy)" />
        <StatCard label="Product demos" value={demo} icon={<Presentation size={16} />} iconColor="var(--orange)" />
      </div>

      <Panel>
        <div className="panel-body col">
          {sorted.length === 0 && <EmptyState title="No appointments booked" />}
          {sorted.map((a) => {
            const p = provMap.get(a.providerId);
            const rep = repMap.get(a.repId);
            const d = new Date(a.scheduledFor);
            return (
              <div key={a.id} className="appt-row">
                <div className="appt-date">
                  <div className="ad-day">{d.getUTCDate()}</div>
                  <div className="ad-mon">
                    {d.toLocaleDateString("en-US", { month: "short", timeZone: "UTC" })}
                  </div>
                </div>
                <div className="col gap-1 grow">
                  <span className="strong">{p?.legalName ?? "Unknown provider"}</span>
                  <span className="tiny muted">
                    {rep?.name ?? "Unassigned"} · {dayMonth(a.scheduledFor)}
                  </span>
                </div>
                <Pill tone={TYPE_TONE[a.type]}>{TYPE_LABEL[a.type]}</Pill>
                <Pill tone={STATUS_TONE[a.status]} dot>
                  {STATUS_LABEL[a.status]}
                </Pill>
                <div className="row gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast("Reschedule request sent")}
                  >
                    Reschedule
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast("Reassignment saved")}
                  >
                    Reassign
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
