import type { ReactNode } from "react";
import { Plug, Send, Sparkles, Mail, Database } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Field,
  Banner,
} from "../../components/ui";
import { useData } from "../../data/store";
import type { Connector } from "../../data/schema";
import { useToast } from "../../components/ui";

const MODE_LABEL: Record<Connector["mode"], string> = {
  direct_esp: "Direct ESP",
  orchestration_platform: "Marketing automation",
  experience_platform: "Experience platform",
};

const LIFECYCLE: Record<Connector["lifecycle"], { label: string; tone: string }> = {
  active: { label: "Active", tone: "green" },
  roadmap: { label: "Building toward", tone: "navy" },
  legacy: { label: "Legacy, sunsetting", tone: "gray" },
};

function iconFor(c: Connector): { node: ReactNode; bg: string; color: string } {
  if (c.mode === "direct_esp")
    return { node: <Send size={20} />, bg: "var(--teal-tint)", color: "var(--teal)" };
  if (c.mode === "experience_platform")
    return { node: <Sparkles size={20} />, bg: "var(--navy-tint)", color: "var(--navy)" };
  return { node: <Mail size={20} />, bg: "var(--cream)", color: "var(--text-muted)" };
}

export function ConnectorsAdmin() {
  const data = useData((s) => s.data)!;
  const toast = useToast((s) => s.push);

  // Show active first, then roadmap, then legacy.
  const order: Record<Connector["lifecycle"], number> = { active: 0, roadmap: 1, legacy: 2 };
  const connectors = [...data.connectors].sort((a, b) => order[a.lifecycle] - order[b.lifecycle]);

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Admin"
        title="Connectors"
        sub="Delivery for lifecycle journeys and card campaigns"
      />

      <Banner tone="info" icon={<Plug size={16} />}>
        The CRM owns orchestration: segments, journeys, and triggers live here. A connector only
        handles delivery, so a direct ESP is enough. SendGrid delivers the card launch today,
        Adobe Journey Optimizer is the strategic path we build toward, and Marketo is sunsetting.
      </Banner>

      <div className="grid grid-2">
        {connectors.map((c) => {
          const ic = iconFor(c);
          const lc = LIFECYCLE[c.lifecycle];
          return (
            <div key={c.id} className="ds-card">
              <div className="ds-ico" style={{ background: ic.bg, color: ic.color }}>
                {ic.node}
              </div>
              <div className="col gap-2 grow">
                <div className="row between center">
                  <span className="strong" style={{ fontSize: 15 }}>
                    {c.name}
                  </span>
                  <Pill tone={lc.tone} dot>
                    {lc.label}
                  </Pill>
                </div>
                <div className="row gap-2 wrap">
                  <Pill tone="outline">{MODE_LABEL[c.mode]}</Pill>
                  {c.lifecycle === "active" && <Pill tone="teal">Default for card sends</Pill>}
                </div>
                <div className="tiny muted">{c.note}</div>
                <Field label="API key">
                  <input value="••••••••••••" disabled />
                </Field>
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast(`${c.name} settings saved`)}
                  >
                    Configure
                  </Button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <Panel tint>
        <PanelHeader title="Two planes: data and delivery" />
        <div className="panel-body col gap-2 small muted">
          <div className="row gap-2 center">
            <Database size={15} style={{ color: "var(--navy)" }} />
            <span>
              <span className="strong" style={{ color: "var(--text-main)" }}>
                Data plane
              </span>{" "}
              is Adobe Experience Platform (Real-Time CDP): the profile, identity, and consent
              source of truth. Card events stream in, audiences activate out to the CRM. See Data
              Sources.
            </span>
          </div>
          <div className="row gap-2 center">
            <Send size={15} style={{ color: "var(--teal)" }} />
            <span>
              <span className="strong" style={{ color: "var(--text-main)" }}>
                Delivery plane
              </span>{" "}
              is pluggable. Ship on SendGrid now, add Adobe Journey Optimizer for enterprise
              transactional delivery and consent as it comes online, and never route the card
              program through Marketo.
            </span>
          </div>
          <div>
            Because the journey model is delivery-agnostic, the same triggers, branches, and A/B
            splits run on whichever connector you choose. Transactional sends (card activation and
            servicing) and marketing sends (nurture and growth) ride different rails with different
            consent rules; the send class is set per email.
          </div>
        </div>
      </Panel>
    </div>
  );
}
