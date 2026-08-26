import { useNavigate } from "react-router-dom";
import { Layers, ArrowRight, Plus, Pencil } from "lucide-react";
import { PageHeader, Panel, PanelHeader, Button, Pill, Banner } from "../../components/ui";
import { useData } from "../../data/store";
import { num } from "../../lib/format";

export function SegmentsPage() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();

  const maxSize = Math.max(1, ...data.segments.map((s) => s.size));

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Lifecycle"
        title="Segments"
        sub="Audiences defined against provider-master funnel stages"
        action={
          <Button variant="primary" onClick={() => navigate("/segments/new")}>
            <Plus size={15} /> New segment
          </Button>
        }
      />

      <Banner tone="info" icon={<Layers size={16} />}>
        Segments are computed live against provider-master funnel stages (signup_started through
        loan_originated). No list pull required. Build a campaign from any segment to trigger a
        lifecycle journey.
      </Banner>

      <div className="grid grid-2">
        {data.segments.map((s) => (
          <Panel key={s.id}>
            <PanelHeader
              title={s.name}
              action={
                <button
                  type="button"
                  className="row center gap-1 tiny muted"
                  onClick={() => navigate(`/segments/${s.id}`)}
                  style={{ background: "none", border: "none", cursor: "pointer", padding: 0 }}
                >
                  <Pill tone="gray">{s.funnelStage}</Pill>
                  <Pencil size={13} />
                </button>
              }
            />
            <div className="panel-body col gap-3">
              <div className="row between center">
                <div className="col gap-1">
                  <span className="tiny muted upper">Audience size</span>
                  <span className="num strong" style={{ fontSize: 26, color: "var(--navy)" }}>
                    {num(s.size)}
                  </span>
                </div>
                <div
                  style={{
                    width: 140,
                    height: 10,
                    background: "var(--navy-tint)",
                    borderRadius: 999,
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      width: `${(s.size / maxSize) * 100}%`,
                      height: "100%",
                      background: "var(--orange)",
                    }}
                  />
                </div>
              </div>
              <div className="row gap-2">
                <Button variant="outline" onClick={() => navigate(`/segments/${s.id}`)}>
                  <Pencil size={14} /> Edit
                </Button>
                <Button
                  variant="outline"
                  className="grow"
                  onClick={() => navigate(`/campaigns/new?segment=${s.id}`)}
                >
                  Build campaign <ArrowRight size={15} />
                </Button>
              </div>
            </div>
          </Panel>
        ))}
      </div>
    </div>
  );
}
