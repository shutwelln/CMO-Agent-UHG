import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { PageHeader, Pill, StageBadge, ProductBadge, ConfidenceBadge } from "../../components/ui";
import { DataTable, type Column } from "../../components/ui/DataTable";
import { useData } from "../../data/store";
import { fdmForProvider } from "../../data/selectors";
import {
  PERSONAS,
  STAGES,
  PRODUCTS,
  STAGE_LABEL,
  PRODUCT_SHORT,
  type Provider,
  type Persona,
  type Stage,
  type Product,
} from "../../data/schema";
import { money } from "../../lib/format";
import { topOfferLabel } from "../../lib/nbo";

export function ProviderDirectory() {
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();

  const [q, setQ] = useState("");
  const [persona, setPersona] = useState<Persona | "">("");
  const [stage, setStage] = useState<Stage | "">("");
  const [product, setProduct] = useState<Product | "">("");

  const rows = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return data.providers.filter((p) => {
      if (persona && p.persona !== persona) return false;
      if (stage && p.currentStage !== stage) return false;
      if (product && !p.productsHeld.includes(product)) return false;
      if (needle) {
        const hay = `${p.legalName} ${p.dba} ${p.tin} ${p.city}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [data.providers, q, persona, stage, product]);

  const columns: Column<Provider>[] = [
    {
      key: "provider",
      header: "Provider",
      width: 240,
      render: (p) => (
        <div className="col gap-1">
          <span className="strong">{p.legalName}</span>
          <span className="tiny faint">
            {p.dba && p.dba !== p.legalName ? `${p.dba} · ` : ""}
            {p.city}, {p.state}
          </span>
        </div>
      ),
    },
    {
      key: "tin",
      header: "TIN",
      width: 110,
      render: (p) => <span className="mono tiny">{p.tin}</span>,
    },
    {
      key: "persona",
      header: "Persona",
      width: 150,
      render: (p) => <Pill tone="navy">{p.persona}</Pill>,
    },
    {
      key: "state",
      header: "State",
      width: 64,
      render: (p) => p.state,
      sortValue: (p) => p.state,
    },
    {
      key: "volume",
      header: "Monthly Optum Pay Vol",
      align: "right",
      width: 150,
      render: (p) => <span className="num">{money(p.monthlyOptumPayVolume, true)}</span>,
      sortValue: (p) => p.monthlyOptumPayVolume,
    },
    {
      key: "products",
      header: "Products held",
      width: 200,
      render: (p) => (
        <div className="row gap-1">
          {p.productsHeld.slice(0, 3).map((pr) => (
            <ProductBadge key={pr} product={pr} />
          ))}
          {p.productsHeld.length > 3 && (
            <span className="tiny faint">+{p.productsHeld.length - 3}</span>
          )}
        </div>
      ),
    },
    {
      key: "stage",
      header: "Stage",
      width: 110,
      render: (p) => <StageBadge stage={p.currentStage} />,
    },
    {
      key: "fdm",
      header: "FDM",
      width: 92,
      render: (p) => {
        const fdm = fdmForProvider(data, p.id);
        return <ConfidenceBadge confidence={fdm?.matchConfidence ?? "none"} />;
      },
    },
    {
      key: "nbo",
      header: "Next-Best-Offer",
      width: 170,
      render: (p) => <span className="small">{topOfferLabel(p)}</span>,
    },
  ];

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Providers"
        title="Provider 360"
        sub="Search the provider master data set"
      />

      <div className="filterbar">
        <div className="search">
          <Search size={15} />
          <input
            placeholder="Search legal name, DBA, TIN, or city"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <select
          className="select"
          value={persona}
          onChange={(e) => setPersona(e.target.value as Persona | "")}
        >
          <option value="">All personas</option>
          {PERSONAS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={stage}
          onChange={(e) => setStage(e.target.value as Stage | "")}
        >
          <option value="">All stages</option>
          {STAGES.map((s) => (
            <option key={s} value={s}>
              {STAGE_LABEL[s]}
            </option>
          ))}
        </select>
        <select
          className="select"
          value={product}
          onChange={(e) => setProduct(e.target.value as Product | "")}
        >
          <option value="">All products</option>
          {PRODUCTS.map((pr) => (
            <option key={pr} value={pr}>
              {PRODUCT_SHORT[pr]}
            </option>
          ))}
        </select>
        <span className="small faint nowrap">{rows.length.toLocaleString("en-US")} providers</span>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/providers/${p.id}`)}
        virtualize
        maxHeight={620}
        emptyMessage="No providers match these filters."
      />
    </div>
  );
}
