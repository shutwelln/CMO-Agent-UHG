import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { useData } from "../../data/store";
import { useRole, CURRENT_REP_ID } from "../../context/role";
import {
  leadsForRep,
  repById,
  fdmForProvider,
} from "../../data/selectors";
import {
  PageHeader,
  ProductBadge,
  StageBadge,
  TierBadge,
  ConfidenceBadge,
  Button,
  useToast,
} from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { money, relTime } from "../../lib/format";
import {
  PRODUCTS,
  PRODUCT_LABEL,
  STAGES,
  STAGE_LABEL,
  TIERS,
  type OfferLead,
  type Provider,
  type Product,
  type Stage,
  type Tier,
} from "../../data/schema";

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
  const [product, setProduct] = useState<Product | "all">("all");
  const [stage, setStage] = useState<Stage | "all">("all");
  const [tier, setTier] = useState<Tier | "all">("all");
  const [fdmFilter, setFdmFilter] = useState<"all" | "present" | "missing">("all");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const rows = useMemo(() => {
    const q = search.trim().toLowerCase();
    return baseLeads.filter((l) => {
      if (product !== "all" && l.product !== product) return false;
      if (stage !== "all" && l.stage !== stage) return false;
      if (tier !== "all" && l.tier !== tier) return false;
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
  }, [baseLeads, search, product, stage, tier, fdmFilter, data, providerMap]);

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
      {
        key: "tin",
        header: "TIN",
        render: (l) => <span className="mono tiny">{l.tin}</span>,
        width: 110,
      },
      {
        key: "product",
        header: "Product",
        render: (l) => <ProductBadge product={l.product} />,
        sortValue: (l) => l.product,
        width: 120,
      },
      {
        key: "offer",
        header: "Offer $",
        render: (l) => <span className="num">{money(l.offerAmount)}</span>,
        sortValue: (l) => l.offerAmount,
        align: "right",
        width: 110,
      },
      {
        key: "tier",
        header: "Tier",
        render: (l) => <TierBadge tier={l.tier} />,
        sortValue: (l) => l.tier,
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
        key: "stage",
        header: "Stage",
        render: (l) => <StageBadge stage={l.stage} />,
        sortValue: (l) => l.stage,
        width: 120,
      },
      {
        key: "outreach",
        header: "Last Outreach",
        render: (l) => (
          <span className="small muted">{l.lastOutreachAt ? relTime(l.lastOutreachAt) : "-"}</span>
        ),
        sortValue: (l) => (l.lastOutreachAt ? +new Date(l.lastOutreachAt) : 0),
        width: 120,
      },
      {
        key: "attempts",
        header: "Attempts",
        render: (l) => (
          <span className="attempts">
            {[0, 1, 2].map((i) => (
              <span key={i} className={i < l.attempts ? "attempt-dot on" : "attempt-dot"} />
            ))}
          </span>
        ),
        sortValue: (l) => l.attempts,
        width: 90,
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
        <select className="select" value={product} onChange={(e) => setProduct(e.target.value as Product | "all")}>
          <option value="all">All products</option>
          {PRODUCTS.map((p) => (
            <option key={p} value={p}>
              {PRODUCT_LABEL[p]}
            </option>
          ))}
        </select>
        <select className="select" value={stage} onChange={(e) => setStage(e.target.value as Stage | "all")}>
          <option value="all">All stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
        <select className="select" value={tier} onChange={(e) => setTier(e.target.value as Tier | "all")}>
          <option value="all">All tiers</option>
          {TIERS.map((t) => (
            <option key={t} value={t}>
              {t.charAt(0).toUpperCase() + t.slice(1)}
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
          <Button variant="outline" size="sm" onClick={() => toast("Disposition applied to selected leads")}>
            Set disposition
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
