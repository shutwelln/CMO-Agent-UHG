import { Plug, Send, Mail } from "lucide-react";
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

export function ConnectorsAdmin() {
  const data = useData((s) => s.data)!;
  const toast = useToast((s) => s.push);

  const icon = (c: Connector) =>
    c.name === "Marketo" ? (
      <Send size={20} style={{ color: "var(--navy)" }} />
    ) : (
      <Mail size={20} style={{ color: "var(--orange)" }} />
    );

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Admin"
        title="Connectors"
        sub="Email service provider integrations for lifecycle journeys"
      />

      <Banner tone="info" icon={<Plug size={16} />}>
        The CRM is ESP-agnostic. Journeys are defined once and delivered through a swappable
        connector. Marketo is the preferred connector today because it is already contracted.
        Customer.io is an alternate that is pending procurement.
      </Banner>

      <div className="grid grid-2">
        {data.connectors.map((c) => (
          <div key={c.id} className="ds-card">
            <div
              className="ds-ico"
              style={{ background: c.name === "Marketo" ? "var(--navy-tint)" : "var(--orange-tint)" }}
            >
              {icon(c)}
            </div>
            <div className="col gap-2 grow">
              <div className="row between center">
                <span className="strong" style={{ fontSize: 15 }}>
                  {c.name}
                </span>
                {c.status === "connected_mock" ? (
                  <Pill tone="green" dot>
                    Connected
                  </Pill>
                ) : (
                  <Pill tone="amber" dot>
                    Not approved
                  </Pill>
                )}
              </div>
              <div>
                {c.isApprovedVendor ? (
                  <Pill tone="navy">Approved vendor</Pill>
                ) : (
                  <Pill tone="gray">Vendor review pending</Pill>
                )}
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
        ))}
      </div>

      <Panel tint>
        <PanelHeader title="Swappable connector abstraction" />
        <div className="panel-body small muted">
          Segments and journeys live in the CRM. The connector layer only handles delivery, so
          swapping Marketo for Customer.io, or running both, requires no changes to a campaign
          definition. This keeps the CRM independent of any single ESP contract.
        </div>
      </Panel>
    </div>
  );
}
