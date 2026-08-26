import type { FunnelCounts } from "../../data/selectors";
import { num, pct } from "../../lib/format";

interface FunnelRowSpec {
  key: keyof FunnelCounts;
  label: string;
  color: string;
}

const ROWS: FunnelRowSpec[] = [
  { key: "started", label: "Signup Started", color: "var(--navy)" },
  { key: "stuck", label: "Stuck Mid-Funnel", color: "var(--amber)" },
  { key: "completed", label: "Completed Signup", color: "#12507a" },
  { key: "funded", label: "Account Funded", color: "#0f8a72" },
  { key: "originated", label: "Loan Originated", color: "var(--teal)" },
];

export function FunnelChart({
  counts,
  onDropClick,
}: {
  counts: FunnelCounts;
  onDropClick?: () => void;
}) {
  const started = Math.max(1, counts.started);

  return (
    <div className="funnel">
      {ROWS.map((r, i) => {
        const count = counts[r.key];
        const width = Math.max(2, (count / started) * 100);
        const prev = i > 0 ? counts[ROWS[i - 1].key] : count;
        const drop = prev > 0 ? ((prev - count) / prev) * 100 : 0;
        const isStuck = r.key === "stuck";
        const clickable = isStuck && onDropClick;

        return (
          <div
            key={r.key}
            className="funnel-row"
            onClick={clickable ? onDropClick : undefined}
            style={{
              cursor: clickable ? "pointer" : undefined,
              opacity: 1,
            }}
            title={clickable ? "Trigger a recovery campaign" : undefined}
          >
            <div className="funnel-meta">
              <div className="fm-label">{r.label}</div>
              <div className="fm-sub">{num(count)} providers</div>
            </div>
            <div className="funnel-bar-wrap">
              <div
                className="funnel-bar"
                style={{
                  width: `${width}%`,
                  background: r.color,
                }}
              >
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
