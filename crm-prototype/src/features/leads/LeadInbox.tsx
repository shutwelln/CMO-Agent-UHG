import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useData } from "../../data/store";
import { useRole, CURRENT_REP_ID } from "../../context/role";
import { leadsForRep, repById, fdmForProvider } from "../../data/selectors";
import {
  PageHeader,
  StatusBadge,
  BankTierBadge,
  ConfidenceBadge,
  Button,
  useToast,
} from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { money, relTime } from "../../lib/format";
import {
  BANK_TIERS,
  LEAD_TYPES,
  STAGES,
  STAGE_LABEL,
  type BankTier,
  type LeadType,
  type OfferLead,
  type Provider,
  type Stage,
} from "../../data/schema";

function loanMix(l: OfferLead): string {
  if (l.capitalOffer > 0 && l.cashFlowOffer > 0) return "Capital + Cash Flow";
  if (l.cashFlowOffer > 0) return "Cash Flow";
  return "Capital";
}

export function LeadInbox() {
  const data = useData((s) => s.data)!;
  const role = useRole((s) => s.role);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();

  const providerMap = useMemo(() => {
    const m = new Map<string, Provider>();
    for (const p of data.providers) m.set(p.id, p);
    return m;
  }, [data.providers]);

  const baseLeads = useMemo(
    () => (role === "sales_rep" ? leadsForRep(data, CURRENT_REP_ID) : data.leads),
    [data, role]
  );

  const [search, setSearch] = useState("");
  const [leadType, setLeadType] = useState<LeadType | "all">("all");
  const [stage, setStage] = useState<Stage | "all">("all");
  const [bankTier, setBankTier] = useState<BankTier | "all">("all");
  const [fdmFilter, setFdmFilter] = useState<"all" | "present" | "missing">("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return baseLeads.filter((l) => {
      if (leadType !== "all" && l.leadType !== leadType) return false;
      if (stage !== "all" && l.stage !== stage) return false;
      if (bankTier !== "all" && l.bankTier !== bankTier) return false;
      if (fdmFilter !== "all") {
        const has = !!fdmForProvider(data, l.providerId);
        if (fdmFilter === "present" && !has) return false;
        if (fdmFilter === "missing" && has) return false;
      }
      if (q) {
        const p = providerMap.get(l.providerId);
        const hay = `${p?.legalName ?? ""} ${l.tin}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [baseLeads, search, leadType, stage, bankTier, fdmFilter, data, providerMap]);

  const toggle = (id: string) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const toggleAll = (ids: string[]) =>
    setSelected((s) => {
      const allOn = ids.length > 0 && ids.every((id) => s.has(id));
      return allOn ? new Set() : new Set(ids);
    });

  const columns: Column<OfferLead>[] = useMemo(
    () => [
      {
        key: "provider",
        header: "Provider",
        render: (l) => {
          const p = providerMap.get(l.providerId);
          return (
            <div>
              <div className="strong small">{p?.legalName ?? "Unknown provider"}</div>
              <div className="tiny muted">{p ? `${p.city}, ${p.state}` : ""}</div>
            </div>
          );
        },
        sortValue: (l) => providerMap.get(l.providerId)?.legalName ?? "",
      },
      { key: "tin", header: "TIN", render: (l) => <span className="mono tiny">{l.tin}</span>, width: 100 },
      {
        key: "loan",
        header: "Loan",
        render: (l) => <span className="small">{loanMix(l)}</span>,
        sortValue: (l) => loanMix(l),
        width: 140,
      },
      {
        key: "offer",
        header: "Max Offer",
        render: (l) => <span className="num">{money(l.offerAmount)}</span>,
        sortValue: (l) => l.offerAmount,
        align: "right",
        width: 110,
      },
      {
        key: "bankTier",
        header: "Bank Tier",
        render: (l) => <BankTierBadge tier={l.bankTier} />,
        sortValue: (l) => l.bankTier,
        width: 90,
      },
      {
        key: "rep",
        header: "Assigned Specialist",
        render: (l) => {
          const rep = repById(data, l.assignedRepId);
          return rep ? <span className="small">{rep.name}</span> : <span className="small faint">Unassigned</span>;
        },
        sortValue: (l) => repById(data, l.assignedRepId)?.name ?? "~",
        width: 150,
      },
      {
        key: "fdm",
        header: "FDM",
        render: (l) => {
          const c = fdmForProvider(data, l.providerId);
          return <ConfidenceBadge confidence={c?.matchConfidence ?? "none"} />;
        },
        width: 90,
      },
      {
        key: "status",
        header: "Lead Status",
        render: (l) => <StatusBadge code={l.status} />,
        sortValue: (l) => Number(l.status),
        width: 230,
      },
      {
        key: "type",
        header: "Lead Type",
        render: (l) => <span className="tiny muted">{l.leadType}</span>,
        sortValue: (l) => l.leadType,
        width: 130,
      },
      {
        key: "outreach",
        header: "Last Outreach",
        render: (l) => (
          <span className="small muted">{l.lastOutreachAt ? relTime(l.lastOutreachAt) : "-"}</span>
        ),
        sortValue: (l) => (l.lastOutreachAt ? +new Date(l.lastOutreachAt) : 0),
        width: 110,
      },
    ],
    [data, providerMap]
  );

  return (
    <div className="col gap-3">
      <PageHeader
        title="Lead Inbox"
        sub={`${rows.length.toLocaleString("en-US")} offers ingested from the monthly bank file, merged and enriched by TIN`}
      />

      <div className="filterbar">
        <div className="row gap-1 center" style={{ position: "relative" }}>
          <Search size={15} style={{ position: "absolute", left: 10, color: "var(--text-faint)" }} />
          <input
            className="select"
            style={{ paddingLeft: 30, width: 240 }}
            placeholder="Search provider or TIN"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select className="select" value={stage} onChange={(e) => setStage(e.target.value as Stage | "all")}>
          <option value="all">All stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
        <select className="select" value={bankTier} onChange={(e) => setBankTier(e.target.value as BankTier | "all")}>
          <option value="all">All bank tiers</option>
          {BANK_TIERS.map((t) => (
            <option key={t} value={t}>
              Tier {t}
            </option>
          ))}
        </select>
        <select className="select" value={leadType} onChange={(e) => setLeadType(e.target.value as LeadType | "all")}>
          <option value="all">All lead types</option>
          {LEAD_TYPES.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={fdmFilter}
          onChange={(e) => setFdmFilter(e.target.value as "all" | "present" | "missing")}
        >
          <option value="all">FDM: any</option>
          <option value="present">FDM present</option>
          <option value="missing">FDM missing</option>
        </select>
      </div>

      {selected.size > 0 && (
        <div className="bulkbar">
          <span className="strong">{selected.size.toLocaleString("en-US")} selected</span>
          <div className="grow" />
          <Button variant="outline" size="sm" onClick={() => toast(`${selected.size} leads queued for reassignment`)}>
            Reassign
          </Button>
          <Button variant="outline" size="sm" onClick={() => navigate("/campaigns/new")}>
            Add to campaign
          </Button>
          <Button variant="outline" size="sm" onClick={() => toast("Status applied to selected leads")}>
            Set status
          </Button>
        </div>
      )}

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(l) => l.id}
        onRowClick={(l) => navigate(`/providers/${l.providerId}`)}
        selectable
        selected={selected}
        onToggle={toggle}
        onToggleAll={toggleAll}
        virtualize
        maxHeight={600}
        dense
        emptyMessage="No leads match these filters."
      />
    </div>
  );
}
