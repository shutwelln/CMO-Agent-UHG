import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  UploadCloud,
  FileSpreadsheet,
  ArrowRight,
  CheckCircle2,
  Database,
  Sparkles,
} from "lucide-react";
import { useData } from "../../data/store";
import { useToast } from "../../components/ui";
import {
  Avatar,
  Banner,
  Button,
  Panel,
  PanelHeader,
  Pill,
  Progress,
  Stepper,
  TierBadge,
} from "../../components/ui";
import { money, num, pct } from "../../lib/format";
import type { Rep, SourceFile, Tier } from "../../data/schema";

const STEPS = ["Upload", "Map Columns", "TIN Merge", "FDM Append", "Assign & Review"];

interface ColMap {
  src: string;
  field: string;
  isKey?: boolean;
}

const COLUMN_MAPS: ColMap[] = [
  { src: "TIN", field: "TIN", isKey: true },
  { src: "Parent Entity", field: "Parent Entity" },
  { src: "Provider Name", field: "Provider Name" },
  { src: "Capital Loan Offer", field: "Capital Loan Offer" },
  { src: "Capital Loan Fee", field: "Capital Loan Fee" },
  { src: "Cash Flow Loan Offer", field: "Cash Flow Loan Offer" },
  { src: "Cash Flow Loan Fee", field: "Cash Flow Loan Fee" },
  { src: "Max Offer", field: "Max Offer" },
  { src: "Tier", field: "Bank Tier" },
];

const CRM_FIELDS = [
  "TIN",
  "Parent Entity",
  "Provider Name",
  "Capital Loan Offer",
  "Capital Loan Fee",
  "Cash Flow Loan Offer",
  "Cash Flow Loan Fee",
  "Max Offer",
  "Bank Tier",
  "Ignore column",
];

// Deterministic per-tier assignment weights so the split is stable across renders.
const TIER_WEIGHT: Record<Tier, number> = { senior: 0.7, mid: 1.0, junior: 1.6 };

interface RepAssignment {
  rep: Rep;
  count: number;
}

const ASSIGNABLE = 132000;
const ASSIGNED_TOTAL = 132410;

export function IngestWizard() {
  const data = useData((s) => s.data)!;
  const commitIngest = useData((s) => s.commitIngest);
  const toast = useToast((s) => s.push);
  const navigate = useNavigate();

  const [step, setStep] = useState(0);
  const [loaded, setLoaded] = useState(false);

  const sf = data.sourceFiles[0];

  const assignments = useMemo<RepAssignment[]>(() => {
    const weighted = data.reps.map((r) => ({ rep: r, w: r.capacity * TIER_WEIGHT[r.seniority] }));
    const totalW = weighted.reduce((s, x) => s + x.w, 0) || 1;
    const raw: RepAssignment[] = weighted.map((x) => ({
      rep: x.rep,
      count: Math.floor((x.w / totalW) * ASSIGNABLE),
    }));
    // Push remainder onto the first rep so the visible sum stays deterministic.
    const assigned = raw.reduce((s, x) => s + x.count, 0);
    if (raw.length > 0) raw[0].count += ASSIGNABLE - assigned;
    return raw;
  }, [data.reps]);

  const assignMax = useMemo(() => Math.max(...assignments.map((a) => a.count), 1), [assignments]);

  const goBack = () => setStep((s) => Math.max(0, s - 1));
  const goContinue = () => {
    if (step === STEPS.length - 1) {
      commitIngest();
      toast("160,004 leads from the July file committed");
      navigate("/leads");
      return;
    }
    setStep((s) => Math.min(STEPS.length - 1, s + 1));
  };

  return (
    <div className="col gap-4">
      <div>
        <h1 style={{ color: "var(--navy)", margin: 0 }}>Monthly Offer Ingest</h1>
        <div className="ph-sub">
          Load the monthly bank offer file, merge on TIN, append FDM contacts, and assign to sales specialists.
        </div>
      </div>

      <Stepper steps={STEPS} current={step} />

      <Panel className="panel-pad">
        {step === 0 && <StepUpload sf={sf} loaded={loaded} onUseSample={() => { setLoaded(true); setStep(1); }} />}
        {step === 1 && <StepMap />}
        {step === 2 && <StepMerge sf={sf} />}
        {step === 3 && <StepFdm sf={sf} onPurchase={() => toast("FDM record purchase queued")} />}
        {step === 4 && (
          <StepAssign assignments={assignments} assignMax={assignMax} />
        )}
      </Panel>

      <div className="row between">
        <Button variant="outline" onClick={goBack} disabled={step === 0}>
          Back
        </Button>
        <Button variant="primary" onClick={goContinue}>
          {step === STEPS.length - 1 ? "Commit ingest" : "Continue"}
        </Button>
      </div>
    </div>
  );
}

/* ---------- Step 0: Upload ---------- */
function StepUpload({
  sf,
  loaded,
  onUseSample,
}: {
  sf: SourceFile;
  loaded: boolean;
  onUseSample: () => void;
}) {
  if (loaded) {
    return (
      <div className="filecard">
        <span className="fc-ico">
          <FileSpreadsheet size={22} />
        </span>
        <div className="grow">
          <div className="strong">{sf.filename}</div>
          <div className="small muted">
            {num(sf.rowCount)} rows, offer month {sf.offerMonth}, total offered {money(sf.totalOfferedAmount, true)}
          </div>
        </div>
        <Pill tone="green" dot>
          Ready
        </Pill>
      </div>
    );
  }
  return (
    <div className="col gap-3">
      <div className="dropzone">
        <div className="dz-ico">
          <UploadCloud size={26} />
        </div>
        <div className="strong" style={{ fontSize: 16 }}>
          Drop the monthly bank offer file
        </div>
        <div className="small muted" style={{ marginTop: 6, maxWidth: 460, marginInline: "auto" }}>
          The offer file lands between the 7th and 10th each month from the bank partner. Drag the .csv or
          .xlsx here, or use the sample July file to preview the flow.
        </div>
        <div style={{ marginTop: 16 }}>
          <Button variant="primary" onClick={onUseSample}>
            Use sample July file
          </Button>
        </div>
      </div>
    </div>
  );
}

/* ---------- Step 1: Map Columns ---------- */
function StepMap() {
  return (
    <div className="col gap-3">
      <Banner tone="info" icon={<Sparkles size={16} />}>
        Columns auto-detected. TIN is the merge key.
      </Banner>
      <div className="maprow" style={{ borderBottom: "2px solid var(--border)", paddingBottom: 8 }}>
        <div className="mapcol strong">Source column</div>
        <div />
        <div className="mapcol strong">CRM field</div>
        <div className="mapcol strong right">Status</div>
      </div>
      {COLUMN_MAPS.map((m) => (
        <div className="maprow" key={m.src}>
          <div className="row gap-2 nowrap">
            <span className="mapcol src">{m.src}</span>
            {m.isKey && <Pill tone="navy">merge key</Pill>}
          </div>
          <ArrowRight size={16} style={{ color: "var(--text-faint)" }} />
          <select className="select" defaultValue={m.field}>
            {CRM_FIELDS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <div className="right">
            <Pill tone="green" dot>
              matched
            </Pill>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ---------- Step 2: TIN Merge ---------- */
function StepMerge({ sf }: { sf: SourceFile }) {
  const ms = sf.matchStats;
  const total = sf.rowCount || 1;
  const segs = [
    { key: "matched", label: "Matched", value: ms.matched, color: "var(--green)" },
    { key: "newProviders", label: "New", value: ms.newProviders, color: "var(--navy)" },
    { key: "unmatched", label: "Unmatched", value: ms.unmatched, color: "var(--amber)" },
    { key: "duplicates", label: "Duplicates", value: ms.duplicates, color: "var(--text-faint)" },
  ];
  return (
    <div className="col gap-4">
      <div>
        <h3 style={{ margin: 0, color: "var(--navy)" }}>TIN merge</h3>
        <div className="small muted" style={{ marginTop: 4 }}>
          Every offer row is matched to the provider master by TIN. Matched rows update existing providers,
          new TINs create provider records, and duplicate TINs are collapsed.
        </div>
      </div>

      <div className="matchbar">
        {segs.map((s) => {
          const w = (s.value / total) * 100;
          return (
            <div key={s.key} style={{ width: `${w}%`, background: s.color }}>
              {w > 8 ? `${s.label} ${pct(w)}` : ""}
            </div>
          );
        })}
      </div>

      <div className="grid grid-4">
        <StatBig num={num(ms.matched)} label={`Matched to existing provider (${pct((ms.matched / total) * 100)})`} color="var(--green)" />
        <StatBig num={num(ms.newProviders)} label={`New providers created (${pct((ms.newProviders / total) * 100)})`} color="var(--navy)" />
        <StatBig num={num(ms.unmatched)} label={`Unmatched / needs review (${pct((ms.unmatched / total) * 100)})`} color="var(--amber)" />
        <StatBig num={num(ms.duplicates)} label={`Duplicate TINs collapsed (${pct((ms.duplicates / total) * 100)})`} color="var(--text-faint)" />
      </div>
    </div>
  );
}

/* ---------- Step 3: FDM Append ---------- */
function StepFdm({ sf, onPurchase }: { sf: SourceFile; onPurchase: () => void }) {
  const total = sf.rowCount || 1;
  const fs = sf.fdmStats;
  const beforePct = (fs.before / total) * 100;
  const afterPct = (fs.after / total) * 100;
  const stillMissing = total - fs.after;
  return (
    <div className="col gap-4">
      <div>
        <h3 style={{ margin: 0, color: "var(--navy)" }}>FDM append</h3>
        <div className="small muted" style={{ marginTop: 4 }}>
          Automated TIN match against third-party FDM data replaces manual VLOOKUPs.
        </div>
      </div>

      <div className="grid grid-2">
        <div className="statbig">
          <span className="sb-num" style={{ color: "var(--text-faint)" }}>
            Before: {pct(beforePct)}
          </span>
          <span className="sb-label">Rows with a usable FDM contact before append ({num(fs.before)})</span>
        </div>
        <div className="statbig">
          <span className="sb-num reveal-num" style={{ color: "var(--teal)" }}>
            After: {pct(afterPct)}
          </span>
          <span className="sb-label">Rows with a usable FDM contact after append ({num(fs.after)})</span>
        </div>
      </div>

      <div className="col gap-1">
        <div className="small muted">FDM coverage</div>
        <Progress value={afterPct} color="var(--teal)" />
      </div>

      <div>
        <PanelHeader title="Newly appended contacts by match confidence" />
        <div className="grid grid-3" style={{ marginTop: 10 }}>
          <StatBig num={num(fs.high)} label="High confidence" color="var(--green)" />
          <StatBig num={num(fs.med)} label="Medium confidence" color="var(--amber)" />
          <StatBig num={num(fs.low)} label="Low confidence" color="var(--text-faint)" />
        </div>
      </div>

      <Banner tone="warn">
        {num(stillMissing)} rows still have no FDM contact and will route to manual research.
      </Banner>

      <div className="row gap-2">
        <Button variant="outline" onClick={onPurchase}>
          <Database size={15} /> Purchase additional FDM records
        </Button>
      </div>
    </div>
  );
}

/* ---------- Step 4: Assign & Review ---------- */
interface TierRule {
  label: string;
  threshold: number;
  tier: Tier;
}
const TIER_RULES: TierRule[] = [
  { label: ">= $150K", threshold: 150000, tier: "senior" },
  { label: "$50K - $150K", threshold: 50000, tier: "mid" },
  { label: "< $50K", threshold: 0, tier: "junior" },
];

function StepAssign({
  assignments,
  assignMax,
}: {
  assignments: RepAssignment[];
  assignMax: number;
}) {
  return (
    <div className="col gap-4">
      <div>
        <h3 style={{ margin: 0, color: "var(--navy)" }}>Assign & review</h3>
        <div className="small muted" style={{ marginTop: 4 }}>
          Offer amount drives the tier, and tier drives which reps get the lead. Adjust thresholds below.
        </div>
      </div>

      <Panel tint className="panel-pad">
        <PanelHeader title="Tier rules" />
        <div className="col gap-2" style={{ marginTop: 8 }}>
          <div className="maprow" style={{ gridTemplateColumns: "1fr 160px 160px", borderBottom: "2px solid var(--border)" }}>
            <div className="mapcol strong">Offer band</div>
            <div className="mapcol strong">Threshold</div>
            <div className="mapcol strong">Tier</div>
          </div>
          {TIER_RULES.map((r) => (
            <div className="maprow" key={r.tier} style={{ gridTemplateColumns: "1fr 160px 160px" }}>
              <div className="mapcol">{r.label}</div>
              <input
                className="select"
                type="text"
                defaultValue={r.threshold.toLocaleString("en-US")}
                style={{ width: 150 }}
              />
              <select className="select" defaultValue={r.tier} style={{ width: 150 }}>
                <option value="senior">Senior</option>
                <option value="mid">Mid</option>
                <option value="junior">Junior</option>
              </select>
            </div>
          ))}
        </div>
      </Panel>

      <div>
        <PanelHeader title="Assignment preview by sales specialist" />
        <div className="col" style={{ marginTop: 8 }}>
          {assignments.map((a) => (
            <div className="assignrow" key={a.rep.id}>
              <Avatar initials={a.rep.avatarInitials} sm />
              <div style={{ width: 150 }} className="nowrap">
                <div className="strong small">{a.rep.name}</div>
                <div className="tiny muted">{a.rep.team}</div>
              </div>
              <TierBadge tier={a.rep.seniority} />
              <div className="ar-bar">
                <Progress value={(a.count / assignMax) * 100} color="var(--navy)" />
              </div>
              <div className="num strong" style={{ width: 72, textAlign: "right" }}>
                {num(a.count)}
              </div>
            </div>
          ))}
        </div>
      </div>

      <Banner tone="success" icon={<CheckCircle2 size={16} />}>
        {num(ASSIGNED_TOTAL)} of 160,004 leads will be assigned across {assignments.length} sales specialists.
      </Banner>
    </div>
  );
}

/* ---------- shared statbig ---------- */
function StatBig({ num: value, label, color }: { num: string; label: string; color?: string }) {
  return (
    <div className="statbig">
      <span className="sb-num" style={color ? { color } : undefined}>
        {value}
      </span>
      <span className="sb-label">{label}</span>
    </div>
  );
}
