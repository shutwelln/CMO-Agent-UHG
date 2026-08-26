import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Phone, ExternalLink, CalendarPlus } from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Field,
  Modal,
  ProductBadge,
  EmptyState,
  CallButton,
  EmailButton,
  useToast,
} from "../../components/ui";
import { useData } from "../../data/store";
import type { Appointment, Disposition, Product } from "../../data/schema";
import {
  DISPOSITIONS,
  DISPOSITION_LABEL,
  PRODUCTS,
  PRODUCT_LABEL,
} from "../../data/schema";
import { providerById, fdmForProvider, repById } from "../../data/selectors";
import { useRole, CURRENT_REP_ID } from "../../context/role";
import { PERSONA_DETAIL } from "../../lib/personas";
import { nextBestOffers } from "../../lib/nbo";
import { money, rate } from "../../lib/format";

const WORKABLE = new Set(["new", "working", "contacted"]);

// Availability slots for booking with a senior sales specialist.
const SLOTS = [
  "Aug 25, 9:00 AM",
  "Aug 25, 11:30 AM",
  "Aug 26, 10:00 AM",
  "Aug 26, 2:00 PM",
  "Aug 27, 9:30 AM",
  "Aug 27, 1:00 PM",
  "Aug 28, 11:00 AM",
  "Aug 28, 3:30 PM",
];
const SLOT_ISO = [
  "2026-08-25T13:00:00.000Z",
  "2026-08-25T15:30:00.000Z",
  "2026-08-26T14:00:00.000Z",
  "2026-08-26T18:00:00.000Z",
  "2026-08-27T13:30:00.000Z",
  "2026-08-27T17:00:00.000Z",
  "2026-08-28T15:00:00.000Z",
  "2026-08-28T19:30:00.000Z",
];

export function SalesConsole() {
  const data = useData((s) => s.data)!;
  const role = useRole((s) => s.role);
  const logDisposition = useData((s) => s.logDisposition);
  const bookAppointment = useData((s) => s.bookAppointment);
  const toast = useToast((s) => s.push);

  const provMap = useMemo(() => {
    const m = new Map<string, ReturnType<typeof providerById>>();
    for (const p of data.providers) m.set(p.id, p);
    return m;
  }, [data.providers]);

  // Caller mode: support both internal sales specialists and a 3rd-party call center.
  const [callerMode, setCallerMode] = useState<"all" | "internal" | "call_center">("all");

  const repTeam = useMemo(() => {
    const m = new Map<string, string>();
    for (const r of data.reps) m.set(r.id, r.team);
    return m;
  }, [data.reps]);

  const queue = useMemo(() => {
    let leads = data.leads.filter((l) => WORKABLE.has(l.stage));
    if (role === "sales_rep") {
      leads = leads.filter((l) => l.assignedRepId === CURRENT_REP_ID);
    } else if (callerMode !== "all") {
      leads = leads.filter((l) => {
        const team = l.assignedRepId ? repTeam.get(l.assignedRepId) : undefined;
        const isCallCenter = team === "3rd-Party Call Center";
        // unassigned leads are workable by either group
        if (!team) return true;
        return callerMode === "call_center" ? isCallCenter : !isCallCenter;
      });
    }
    return [...leads].sort((a, b) => b.offerAmount - a.offerAmount).slice(0, 30);
  }, [data.leads, role, callerMode, repTeam]);

  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(
    () => queue[0]?.id ?? null
  );

  const selectedLead =
    queue.find((l) => l.id === selectedLeadId) ?? queue.find((l) => l.id) ?? null;
  const provider = selectedLead ? provMap.get(selectedLead.providerId) : undefined;
  const fdm = provider ? fdmForProvider(data, provider.id) : undefined;
  const nbo = provider ? nextBestOffers(provider)[0] : undefined;

  // Disposition form state
  const [disposition, setDisposition] = useState<Disposition | null>(null);
  const [notes, setNotes] = useState("");
  const [interestProducts, setInterestProducts] = useState<Product[]>([]);
  const [interestLevel, setInterestLevel] = useState<"hot" | "warm" | "cold">("warm");

  // Booking modal state
  const [booking, setBooking] = useState(false);
  const [bookRepId, setBookRepId] = useState<string>("");
  const [slotIdx, setSlotIdx] = useState<number | null>(null);
  const [meetingType, setMeetingType] = useState<Appointment["type"]>("discovery");

  const resetForm = () => {
    setDisposition(null);
    setNotes("");
    setInterestProducts([]);
    setInterestLevel("warm");
  };

  const advance = () => {
    if (!selectedLead) return;
    const idx = queue.findIndex((l) => l.id === selectedLead.id);
    const next = queue[idx + 1] ?? queue[0];
    setSelectedLeadId(next?.id ?? null);
  };

  const logAndNext = () => {
    if (!selectedLead || !disposition) return;
    logDisposition(selectedLead.id, disposition, notes, interestProducts, interestLevel);
    toast(`Logged ${DISPOSITION_LABEL[disposition]} for this lead`);
    resetForm();
    advance();
  };

  const toggleProduct = (p: Product) =>
    setInterestProducts((cur) =>
      cur.includes(p) ? cur.filter((x) => x !== p) : [...cur, p]
    );

  const seniorReps = data.reps.filter((r) => r.seniority === "senior");
  const currentRep = repById(data, CURRENT_REP_ID);

  const confirmBooking = () => {
    if (!selectedLead || !provider || !bookRepId || slotIdx === null) return;
    bookAppointment({
      providerId: provider.id,
      leadId: selectedLead.id,
      repId: bookRepId,
      scheduledFor: SLOT_ISO[slotIdx],
      type: meetingType,
      status: "scheduled",
      createdBy: currentRep?.name ?? "Outbound Specialist",
    });
    toast(`Appointment booked for ${SLOTS[slotIdx]}`);
    setBooking(false);
    setBookRepId("");
    setSlotIdx(null);
    setMeetingType("discovery");
  };

  return (
    <div className="col gap-4">
      <PageHeader
        crumb="Outbound"
        title="Sales Console"
        sub={
          role === "sales_rep"
            ? "Your prioritized call queue"
            : "Prioritized call queue across all sales specialists"
        }
        action={
          role !== "sales_rep" ? (
            <Field label="Caller group">
              <select
                className="select"
                value={callerMode}
                onChange={(e) => {
                  setCallerMode(e.target.value as "all" | "internal" | "call_center");
                  setSelectedLeadId(null);
                }}
              >
                <option value="all">All sales specialists</option>
                <option value="internal">Internal specialists</option>
                <option value="call_center">3rd-party call center</option>
              </select>
            </Field>
          ) : undefined
        }
      />

      {queue.length === 0 ? (
        <Panel>
          <EmptyState title="Queue is empty" sub="No workable leads in scope." />
        </Panel>
      ) : (
        <div className="console">
          {/* LEFT: queue */}
          <Panel>
            <PanelHeader title={`Queue (${queue.length})`} />
            <div>
              {queue.map((l) => {
                const p = provMap.get(l.providerId);
                const active = selectedLead?.id === l.id;
                return (
                  <div
                    key={l.id}
                    className={`queue-item${active ? " active" : ""}`}
                    onClick={() => setSelectedLeadId(l.id)}
                  >
                    <div className="row between">
                      <span className="qi-name">{p?.legalName ?? "Unknown"}</span>
                      <span className="num small strong" style={{ color: "var(--navy)" }}>
                        {money(l.offerAmount, true)}
                      </span>
                    </div>
                    <div className="row between center" style={{ marginTop: 6 }}>
                      <ProductBadge product={l.product} />
                      <span className="attempts">
                        {Array.from({ length: 3 }).map((_, i) => (
                          <span
                            key={i}
                            className={`attempt-dot${i < l.attempts ? " on" : ""}`}
                          />
                        ))}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>

          {/* CENTER: active lead mini-360 */}
          <Panel>
            <PanelHeader
              title="Active lead"
              action={
                provider && (
                  <Link to={`/providers/${provider.id}`} className="btn-text">
                    Open 360 <ExternalLink size={13} />
                  </Link>
                )
              }
            />
            <div className="panel-body col gap-3">
              {provider && selectedLead ? (
                <>
                  <div className="row between center">
                    <div className="col gap-1">
                      <span className="strong" style={{ fontSize: 16 }}>
                        {provider.legalName}
                      </span>
                      <span className="tiny muted mono">TIN {provider.tin}</span>
                    </div>
                    <Pill tone="gray">{provider.persona}</Pill>
                  </div>

                  <div className="col gap-1">
                    <span className="tiny muted upper">Financial decision maker</span>
                    {fdm ? (
                      <div className="small">
                        <span className="strong">{fdm.name}</span>, {fdm.title}
                        <div className="mono tiny muted" style={{ marginTop: 2 }}>
                          {fdm.phone} · {fdm.email}
                        </div>
                        <div className="row gap-2" style={{ marginTop: 8 }}>
                          <CallButton phone={fdm.phone} />
                          <EmailButton
                            email={fdm.email}
                            subject={`Optum Banking Solutions - ${provider.legalName}`}
                          />
                        </div>
                      </div>
                    ) : (
                      <span className="small muted">No FDM on file</span>
                    )}
                  </div>

                  <div className="col gap-1">
                    <span className="tiny muted upper">Offer</span>
                    <div className="row gap-2 center">
                      <ProductBadge product={selectedLead.product} />
                      <span className="num strong">{money(selectedLead.offerAmount)}</span>
                      <span className="small muted">{rate(selectedLead.rate)}</span>
                    </div>
                  </div>

                  {nbo && (
                    <div className="nbo-card top">
                      <div className="nbo-head">
                        <span className="nbo-title">{nbo.headline}</span>
                      </div>
                      <div className="nbo-detail">{nbo.detail}</div>
                      <div className="nbo-rationale">Talk track: {nbo.rationale}</div>
                      {nbo.incentive && <div className="nbo-incentive">{nbo.incentive}</div>}
                    </div>
                  )}

                  <div className="col gap-1">
                    <span className="tiny muted upper">Persona hook</span>
                    <span className="small" style={{ fontStyle: "italic" }}>
                      {PERSONA_DETAIL[provider.persona].hook}
                    </span>
                  </div>

                  <div className="tiny muted">
                    Attempt {selectedLead.attempts} logged this lead.
                  </div>
                </>
              ) : (
                <EmptyState title="Select a lead" icon={<Phone size={20} />} />
              )}
            </div>
          </Panel>

          {/* RIGHT: disposition */}
          <Panel>
            <PanelHeader title="Disposition" />
            <div className="panel-body col gap-3">
              <div className="dispo-grid">
                {DISPOSITIONS.map((d) => (
                  <button
                    key={d}
                    className={`dispo-btn${disposition === d ? " selected" : ""}`}
                    onClick={() => setDisposition(d)}
                  >
                    {DISPOSITION_LABEL[d]}
                  </button>
                ))}
              </div>

              <Field label="Notes">
                <textarea
                  rows={3}
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder="Call notes..."
                />
              </Field>

              <div className="col gap-1">
                <span className="tiny muted upper">Product interest</span>
                <div className="row gap-1 wrap">
                  {PRODUCTS.map((p) => (
                    <button
                      key={p}
                      className={`interest-chip${interestProducts.includes(p) ? " on" : ""}`}
                      onClick={() => toggleProduct(p)}
                    >
                      {PRODUCT_LABEL[p]}
                    </button>
                  ))}
                </div>
              </div>

              <Field label="Interest level">
                <select
                  className="select"
                  value={interestLevel}
                  onChange={(e) =>
                    setInterestLevel(e.target.value as "hot" | "warm" | "cold")
                  }
                >
                  <option value="hot">Hot</option>
                  <option value="warm">Warm</option>
                  <option value="cold">Cold</option>
                </select>
              </Field>

              <div className="col gap-2">
                <Button onClick={logAndNext} disabled={!disposition || !selectedLead}>
                  Log &amp; next
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setBooking(true)}
                  disabled={!selectedLead}
                >
                  <CalendarPlus size={15} /> Book appointment
                </Button>
              </div>
            </div>
          </Panel>
        </div>
      )}

      {booking && provider && (
        <Modal
          title={`Book appointment - ${provider.legalName}`}
          onClose={() => setBooking(false)}
          width={520}
          footer={
            <>
              <Button variant="outline" onClick={() => setBooking(false)}>
                Cancel
              </Button>
              <Button
                onClick={confirmBooking}
                disabled={!bookRepId || slotIdx === null}
              >
                Confirm booking
              </Button>
            </>
          }
        >
          <div className="col gap-3">
            <Field label="Senior sales specialist">
              <select
                className="select"
                value={bookRepId}
                onChange={(e) => setBookRepId(e.target.value)}
              >
                <option value="">Select a senior sales specialist</option>
                {seniorReps.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.name} - {r.team}
                  </option>
                ))}
              </select>
            </Field>

            <div className="col gap-1">
              <span className="tiny muted upper">Available slots</span>
              <div className="availgrid">
                {SLOTS.map((s, i) => (
                  <div
                    key={s}
                    className={`availslot${slotIdx === i ? " selected" : ""}`}
                    onClick={() => setSlotIdx(i)}
                  >
                    {s}
                  </div>
                ))}
              </div>
            </div>

            <Field label="Meeting type">
              <select
                className="select"
                value={meetingType}
                onChange={(e) => setMeetingType(e.target.value as Appointment["type"])}
              >
                <option value="discovery">Discovery</option>
                <option value="product_demo">Product demo</option>
                <option value="closing">Closing</option>
              </select>
            </Field>
          </div>
        </Modal>
      )}
    </div>
  );
}
