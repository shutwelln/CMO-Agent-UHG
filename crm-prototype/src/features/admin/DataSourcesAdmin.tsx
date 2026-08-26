import type { ReactNode } from "react";
import { Database, FileSpreadsheet, Cloud, DollarSign, Workflow } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Banner,
} from "../../components/ui";
import { useData } from "../../data/store";
import type { DataSource } from "../../data/schema";
import { useToast } from "../../components/ui";
import { num, relTime } from "../../lib/format";

function iconFor(kind: string): { node: ReactNode; bg: string } {
  switch (kind) {
    case "warehouse":
      return { node: <Database size={20} style={{ color: "var(--navy)" }} />, bg: "var(--navy-tint)" };
    case "sftp_file":
      return {
        node: <FileSpreadsheet size={20} style={{ color: "var(--teal)" }} />,
        bg: "var(--teal-tint)",
      };
    case "vendor_api":
      return { node: <Cloud size={20} style={{ color: "var(--orange)" }} />, bg: "var(--orange-tint)" };
    case "downstream":
      return {
        node: <DollarSign size={20} style={{ color: "var(--amber)" }} />,
        bg: "var(--amber-bg)",
      };
    default:
      return { node: <Database size={20} />, bg: "var(--cream)" };
  }
}

export function DataSourcesAdmin() {
  const data = useData((s) => s.data)!;
  const toast = useToast((s) => s.push);

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Admin"
        title="Data Sources"
        sub="Connected feeds powering the CRM"
      />

      <Banner tone="info" icon={<Workflow size={16} />}>
        The CRM syncs from the provider master data warehouse feed, the monthly bank offer file, a
        third-party FDM vendor, and the Salesforce Go commission export.
      </Banner>

      <div className="grid grid-2">
        {data.dataSources.map((ds: DataSource) => {
          const ic = iconFor(ds.kind);
          const isDownstream = ds.kind === "downstream";
          return (
            <div key={ds.id} className="ds-card">
              <div className="ds-ico" style={{ background: ic.bg }}>
                {ic.node}
              </div>
              <div className="col gap-2 grow">
                <div className="row between center">
                  <span className="strong" style={{ fontSize: 15 }}>
                    {ds.name}
                  </span>
                  <Pill tone="green" dot>Connected</Pill>
                </div>
                {isDownstream && (
                  <div>
                    <Pill tone="amber">downstream / read-only, not the CRM</Pill>
                  </div>
                )}
                <div className="row gap-3 wrap tiny muted">
                  <span>Last sync {relTime(ds.lastSync)}</span>
                  <span>{num(ds.recordCount)} records</span>
                </div>
                <div className="tiny muted">{ds.note}</div>
                <div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast(`${ds.name} settings saved`)}
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
        <PanelHeader title="Data lineage" />
        <div className="panel-body col gap-2 small muted">
          <div>Provider Master Data Set streams funnel events into the CRM.</div>
          <div>Monthly Bank Offer File is picked up over SFTP between the 7th and 10th.</div>
          <div>Third-Party FDM Data is matched by TIN to lift decision-maker coverage.</div>
          <div>
            Salesforce Go is a downstream, read-only commission export. It receives closed-won deals
            and is not the CRM.
          </div>
        </div>
      </Panel>
    </div>
  );
}
