import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Phone,
  Calendar,
  Megaphone,
  AlertTriangle,
  Building2,
  Mail,
  UserPlus,
  CheckCircle2,
  Circle,
} from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Pill,
  Button,
  TierBadge,
  StageBadge,
  ProductBadge,
  ConfidenceBadge,
  EmptyState,
  Modal,
  Field,
  CallButton,
  EmailButton,
  useToast,
} from "../../components/ui";
import { useData } from "../../data/store";
import {
  providerById,
  leadsForProvider,
  activitiesForProvider,
  funnelForProvider,
  fdmForProvider,
} from "../../data/selectors";
import {
  FUNNEL_EVENT_LABEL,
  SURFACE_LABEL,
  DISPOSITION_LABEL,
  PRODUCT_LABEL,
  type OfferLead,
  type Tier,
} from "../../data/schema";
import { money, rate, relTime, num } from "../../lib/format";
import { nextBestOffers } from "../../lib/nbo";
import { CURRENT_REP_ID } from "../../context/role";

type Tab = "overview" | "funnel" | "activities";

const BUNDLE_LABEL: Record<string, string> = {
  apr_reduction: "0.25% APR",
  npx_reduction: "NPx 1.49% -> 0.49%",
  cash_accel: "Cash accel",
};

const TIER_RANK: Record<Tier, number> = { senior: 3, mid: 2, junior: 1 };

export function Provider360() {
  const { id } = useParams();
  const data = useData((s) => s.data)!;
  const navigate = useNavigate();
  const toast = useToast((s) => s.push);

  const provider = id ? providerById(data, id) : undefined;
  const [tab, setTab] = useState<Tab>("overview");
  const [showBook, setShowBook] = useState(false);

  const leads = useMemo(
    () => (provider ? leadsForProvider(data, provider.id) : []),
    [data, provider]
  );
  const activities = useMemo(
    () => (provider ? activitiesForProvider(data, provider.id) : []),
    [data, provider]
  );
  const funnel = useMemo(
    () => (provider ? funnelForProvider(data, provider.id) : []),
    [data, provider]
  );

  if (!provider) {
    return (
      <EmptyState
        title="Provider not found"
        sub="This provider is not in the master data set."
        icon={<Building2 size={22} />}
      />
    );
  }

  const fdm = fdmForProvider(data, provider.id);
  const offers = nextBestOffers(provider);
  const initials = provider.legalName
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  const largestTier =
    leads.length > 0
      ? leads.reduce<Tier>((best, l) => (TIER_RANK[l.tier] > TIER_RANK[best] ? l.tier : best), "junior")
      : "junior";

  return (
    <div className="col gap-4">
      <PageHeader crumb="Providers" title={provider.legalName} />

      <div className="prov-hd">
        <span className="ph-mark">{initials}</span>
        <div className="col gap-1 grow">
          <h1>{provider.legalName}</h1>
          <div className="muted small">
            {provider.dba && provider.dba !== provider.legalName ? `${provider.dba} · ` : ""}
            {provider.specialty}
          </div>
          <div className="prov-meta">
            <Pill tone="navy">{provider.persona}</Pill>
            <span className="small faint">
              {provider.city}, {provider.state}
            </span>
            {leads.length > 0 && <TierBadge tier={largestTier} />}
            <Pill tone={provider.hasOptumBankAccount ? "green" : "gray"} dot>
              AND account: {provider.hasOptumBankAccount ? "active" : "none"}
            </Pill>
            <Pill tone={provider.npxEnrolled ? "teal" : "gray"}>
              NPx {provider.npxEnrolled ? "enrolled" : "off"}
            </Pill>
          </div>
        </div>
        <div className="row gap-2 wrap">
          <Button variant="outline" onClick={() => navigate("/console")}>
            <Phone size={15} /> Log call
          </Button>
          <Button variant="outline" onClick={() => setShowBook(true)}>
            <Calendar size={15} /> Book appointment
          </Button>
          <Button variant="orange" onClick={() => navigate("/campaigns/new")}>
            <Megaphone size={15} /> Add to campaign
          </Button>
        </div>
      </div>

      <div className="prov-grid">
        <div className="col gap-4">
          <div className="tabs">
            <button
              className={tab === "overview" ? "tab active" : "tab"}
              onClick={() => setTab("overview")}
            >
              Overview
            </button>
            <button
              className={tab === "funnel" ? "tab active" : "tab"}
              onClick={() => setTab("funnel")}
            >
              Funnel Timeline
            </button>
            <button
              className={tab === "activities" ? "tab active" : "tab"}
              onClick={() => setTab("activities")}
            >
              Activities
            </button>
          </div>

          {tab === "overview" && (
            <OverviewTab provider={provider} leads={leads} />
          )}

          {tab === "funnel" && (
            <FunnelTab funnel={funnel} navigate={navigate} />
          )}

          {tab === "activities" && <ActivitiesTab activities={activities} />}
        </div>

        <div className="col gap-4">
          <Panel>
            <PanelHeader title="Next-Best-Offer" />
            <div className="panel-body col gap-3">
              {offers.length === 0 && <EmptyState title="No offers available" />}
              {offers.map((o, i) => (
                <div key={o.product + i} className={i === 0 ? "nbo-card top" : "nbo-card"}>
                  <div className="nbo-head">
                    <span className="nbo-title">{o.headline}</span>
                    <span className="nbo-score">score {o.score}</span>
                  </div>
                  <div className="nbo-detail">{o.detail}</div>
                  {o.incentive && <span className="nbo-incentive">{o.incentive}</span>}
                  <div className="nbo-rationale">{o.rationale}</div>
                  <div className="row gap-2">
                    <Button
                      variant="teal"
                      size="sm"
                      onClick={() => toast("Offer presented")}
                    >
                      Present offer
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => navigate("/campaigns/new")}
                    >
                      Add to campaign
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </Panel>

          <Panel>
            <PanelHeader title="Financial decision maker" />
            <div className="panel-body">
              {fdm ? (
                <div className="contact-card">
                  <div className="row between center">
                    <span className="strong">{fdm.name}</span>
                    <ConfidenceBadge confidence={fdm.matchConfidence} />
                  </div>
                  <div className="small faint">{fdm.title}</div>
                  <div className="row gap-2 center small">
                    <Mail size={13} />{" "}
                    <a className="contact-val" href={`mailto:${fdm.email}`}>{fdm.email}</a>
                  </div>
                  <div className="row gap-2 center small">
                    <Phone size={13} />{" "}
                    <a className="contact-val" href={`tel:${fdm.phone.replace(/[^\d+]/g, "")}`}>
                      {fdm.phone}
                    </a>
                  </div>
                  <div className="row gap-2" style={{ marginTop: 8 }}>
                    <CallButton phone={fdm.phone} />
                    <EmailButton email={fdm.email} subject={`Optum Banking Solutions - ${provider.legalName}`} />
                  </div>
                  <div className="tiny faint" style={{ marginTop: 8 }}>
                    Source: {fdm.source === "internal" ? "Internal" : "Third-party append"}
                  </div>
                </div>
              ) : (
                <div className="contact-card missing">
                  <div className="strong">No FDM on file</div>
                  <div className="small faint">
                    No financial decision maker identified for this provider.
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast("Third-party FDM append requested")}
                  >
                    <UserPlus size={14} /> Request third-party FDM append
                  </Button>
                </div>
              )}
            </div>
          </Panel>
        </div>
      </div>

      {showBook && (
        <BookModal
          providerId={provider.id}
          leadId={leads[0]?.id ?? null}
          onClose={() => setShowBook(false)}
          onBooked={() => {
            setShowBook(false);
            toast("Appointment booked with senior rep");
          }}
        />
      )}
    </div>
  );
}

function OverviewTab({ provider, leads }: { provider: import("../../data/schema").Provider; leads: OfferLead[] }) {
  return (
    <>
      <Panel>
        <PanelHeader title="Firmographics" />
        <div className="panel-body">
          <div className="factgrid">
            <Fact label="Specialty" value={provider.specialty} />
            <Fact label="Locations" value={num(provider.locations)} />
            <Fact label="State / City" value={`${provider.city}, ${provider.state}`} />
            <Fact
              label="Monthly Optum Pay volume"
              value={money(provider.monthlyOptumPayVolume)}
            />
            <Fact label="PWC status" value={cap(provider.pwcStatus)} />
            <Fact label="Primary bank on file" value={provider.primaryBankOnFile ? "Yes" : "No"} />
            <Fact label="NPx enrolled" value={provider.npxEnrolled ? "Yes" : "No"} />
            <Fact
              label="Products held"
              value={
                provider.productsHeld.length
                  ? provider.productsHeld.map((p) => PRODUCT_LABEL[p]).join(", ")
                  : "None"
              }
            />
          </div>
        </div>
      </Panel>

      <Panel>
        <PanelHeader title="Outstanding offers" />
        <div className="panel-body col">
          {leads.length === 0 && <EmptyState title="No outstanding offers" />}
          {leads.map((l) => (
            <div key={l.id} className="listrow">
              <div className="row gap-2 center">
                <ProductBadge product={l.product} />
                <span className="strong">{money(l.offerAmount)}</span>
                <span className="small faint">
                  {rate(l.rate)} {l.product === "term_loan" || l.product === "loc" ? "APR" : "fee"}
                </span>
              </div>
              <div className="row gap-2 center wrap">
                {l.bundleFlags.map((b) => (
                  <span key={b} className="pill pill-teal">
                    {BUNDLE_LABEL[b] ?? b}
                  </span>
                ))}
                <StageBadge stage={l.stage} />
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </>
  );
}

function FunnelTab({
  funnel,
  navigate,
}: {
  funnel: import("../../data/schema").FunnelEvent[];
  navigate: ReturnType<typeof useNavigate>;
}) {
  if (funnel.length === 0) {
    return (
      <Panel>
        <div className="panel-body">
          <EmptyState title="No funnel activity" sub="This provider has not entered the signup funnel." />
        </div>
      </Panel>
    );
  }

  const last = funnel[funnel.length - 1];
  const isDrop =
    last.eventType === "stuck_mid_funnel" ||
    (last.eventType === "account_funded" && !funnel.some((e) => e.eventType === "loan_originated"));

  return (
    <Panel>
      <PanelHeader title="Funnel timeline" />
      <div className="panel-body">
        <div className="timeline">
          {funnel.map((e) => {
            const dotColor =
              e.eventType === "completed_signup" ||
              e.eventType === "account_funded" ||
              e.eventType === "loan_originated"
                ? "var(--green)"
                : e.eventType === "stuck_mid_funnel"
                ? "var(--amber)"
                : "var(--navy)";
            return (
              <div key={e.id} className="tl-item">
                <span className="tl-dot" style={{ background: dotColor }} />
                <div className="tl-body">
                  <div className="tl-title">{FUNNEL_EVENT_LABEL[e.eventType]}</div>
                  <div className="tl-sub">
                    {SURFACE_LABEL[e.surface]} · {relTime(e.occurredAt)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        {isDrop && (
          <div className="tl-drop">
            <div className="row gap-2 center">
              <AlertTriangle size={16} style={{ color: "var(--amber)" }} />
              <span className="strong">
                Dropped at {last.eventType === "stuck_mid_funnel" ? last.stuckStep ?? "mid-funnel" : "funded, no loan"}
              </span>
            </div>
            <Button variant="orange" size="sm" onClick={() => navigate("/campaigns/new")}>
              Trigger recovery campaign
            </Button>
          </div>
        )}
      </div>
    </Panel>
  );
}

function ActivitiesTab({ activities }: { activities: import("../../data/schema").Activity[] }) {
  if (activities.length === 0) {
    return (
      <Panel>
        <div className="panel-body">
          <EmptyState title="No activity logged" />
        </div>
      </Panel>
    );
  }
  return (
    <Panel>
      <PanelHeader title="Activity history" />
      <div className="panel-body col">
        {activities.map((a) => {
          const Icon =
            a.type === "call"
              ? Phone
              : a.type === "email" || a.type === "sms"
              ? Mail
              : a.type === "appointment"
              ? Calendar
              : a.type === "campaign"
              ? Megaphone
              : a.type === "funnel"
              ? Circle
              : CheckCircle2;
          const primary = a.disposition
            ? DISPOSITION_LABEL[a.disposition]
            : a.notes || cap(a.type);
          return (
            <div key={a.id} className="listrow">
              <div className="row gap-2 center">
                <Icon size={15} style={{ color: "var(--navy)" }} />
                <div className="col gap-1">
                  <div className="lr-title">{primary}</div>
                  <div className="lr-sub">
                    {a.actor}
                    {a.attemptNumber ? ` · attempt ${a.attemptNumber}` : ""}
                  </div>
                </div>
              </div>
              <span className="small faint nowrap">{relTime(a.occurredAt)}</span>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function BookModal({
  providerId,
  leadId,
  onClose,
  onBooked,
}: {
  providerId: string;
  leadId: string | null;
  onClose: () => void;
  onBooked: () => void;
}) {
  const data = useData((s) => s.data)!;
  const bookAppointment = useData((s) => s.bookAppointment);
  const seniorReps = data.reps.filter((r) => r.seniority === "senior" && r.active);
  const [repId, setRepId] = useState(seniorReps[0]?.id ?? "");
  const [date, setDate] = useState("2026-08-29");

  const submit = () => {
    bookAppointment({
      providerId,
      leadId,
      repId: repId || CURRENT_REP_ID,
      scheduledFor: new Date(`${date}T15:00:00Z`).toISOString(),
      type: "discovery",
      status: "scheduled",
      createdBy: "Sales Specialist",
    });
    onBooked();
  };

  return (
    <Modal
      title="Book appointment"
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit}>
            Book
          </Button>
        </>
      }
    >
      <div className="col gap-3">
        <Field label="Senior sales specialist">
          <select className="select" value={repId} onChange={(e) => setRepId(e.target.value)}>
            {seniorReps.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} ({r.team})
              </option>
            ))}
          </select>
        </Field>
        <Field label="Date">
          <input
            type="date"
            className="select"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </Field>
      </div>
    </Modal>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <div className="f-label">{label}</div>
      <div className="f-value">{value}</div>
    </div>
  );
}

function cap(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
