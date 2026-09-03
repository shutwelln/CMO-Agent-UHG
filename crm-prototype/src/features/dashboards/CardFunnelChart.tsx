import type { CardFunnelCounts } from "../../data/selectors";
import { num, pct } from "../../lib/format";

interface Row {
  key: keyof CardFunnelCounts;
  label: string;
  color: string;
}

// Awareness -> Acquisition -> Onboarding -> Activation -> Spend -> Growth
const ROWS: Row[] = [
  { key: "offerViewed", label: "Card Offer Viewed", color: "var(--navy)" },
  { key: "applied", label: "Card Applied", color: "#12507a" },
  { key: "approved", label: "Card Approved", color: "#0e6f86" },
  { key: "activated", label: "Card Activated", color: "var(--p-card)" },
  { key: "firstSpend", label: "First Spend", color: "#0f8a72" },
  { key: "recurringSpend", label: "Recurring Spend", color: "var(--teal)" },
];

export function CardFunnelChart({
  counts,
  onStageClick,
}: {
  counts: CardFunnelCounts;
  onStageClick?: (key: keyof CardFunnelCounts) => void;
}) {
  const top = Math.max(1, counts.offerViewed);

  return (
    <div className="funnel">
      {ROWS.map((r, i) => {
        const count = counts[r.key];
        const width = Math.max(2, (count / top) * 100);
        const prev = i > 0 ? counts[ROWS[i - 1].key] : count;
        const drop = prev > 0 ? ((prev - count) / prev) * 100 : 0;
        const clickable = !!onStageClick;
        return (
          <div
            key={r.key}
            className="funnel-row"
            onClick={clickable ? () => onStageClick!(r.key) : undefined}
            style={{ cursor: clickable ? "pointer" : undefined }}
            title={clickable ? "Target this stage with a card campaign" : undefined}
          >
            <div className="funnel-meta">
              <div className="fm-label">{r.label}</div>
              <div className="fm-sub">{num(count)} providers</div>
            </div>
            <div className="funnel-bar-wrap">
              <div className="funnel-bar" style={{ width: `${width}%`, background: r.color }}>
                <span>{num(count)}</span>
              </div>
            </div>
            <div className="funnel-drop">
              {i > 0 && drop > 0 && <span className="fd-pct">-{pct(drop)}</span>}
            </div>
          </div>
        );
      })}
    </div>
  );
}
