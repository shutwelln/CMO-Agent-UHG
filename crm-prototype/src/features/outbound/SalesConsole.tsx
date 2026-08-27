import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Phone,
  PhoneCall,
  PhoneOff,
  Mail,
  ExternalLink,
  CalendarPlus,
  Sparkles,
  RefreshCw,
  Send,
} from "lucide-react";
import {
  PageHeader,
  Panel,
  PanelHeader,
  Button,
  Pill,
  Field,
  Modal,
  BankTierBadge,
  StatusBadge,
  EmptyState,
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
import { money } from "../../lib/format";
import { draftProviderEmail, VARIANT_LABELS } from "../../lib/emailDraft";

/* Synthesized work email for a sales rep (reps carry no email in the data). */
const repEmail = (name: string) =>
  `${name.toLowerCase().replace(/[^a-z\s]/g, "").trim().replace(/\s+/g, ".")}@optumbank.com`;

/* Shared mailboxes a broadcast-style or unbranded send can originate from. */
const SHARED_MAILBOXES = [
  { id: "mbx_providers", name: "Optum Banking Solutions", email: "providers@optumbank.com" },
  { id: "mbx_team", name: "Optum Provider Team", email: "provider-team@optumbank.com" },
];

const WORKABLE = new Set(["ready", "engaged", "kyc"]);

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
  const logEmail = useData((s) => s.logEmail);
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

  // Dialer state: assumes an integrated dialer that auto-dials out (no tel: hand-off).
  const [calling, setCalling] = useState<{ name: string; phone: string } | null>(null);

  // In-platform email composer state (drafted, sent, and logged without leaving the app).
  const [composing, setComposing] = useState(false);
  const [emailFromId, setEmailFromId] = useState<string>("");
  const [emailTo, setEmailTo] = useState("");
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [emailVariant, setEmailVariant] = useState(0);

  // Sender options: any active rep, or a shared mailbox.
  const fromOptions = useMemo(() => {
    const reps = data.reps
      .filter((r) => r.active)
      .map((r) => ({ id: r.id, name: r.name, email: repEmail(r.name), team: r.team }));
    return { reps, mailboxes: SHARED_MAILBOXES };
  }, [data.reps]);

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
    setCalling(null);
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

  const selectLead = (id: string | null) => {
    setSelectedLeadId(id);
    setCalling(null);
  };

  // Dialer: assume an integrated softphone that dials out automatically.
  const startCall = () => {
    if (!fdm) return;
    setCalling({ name: fdm.name, phone: fdm.phone });
    toast(`Dialing ${fdm.phone} through the connected dialer`);
  };
  const endCall = () => {
    setCalling(null);
    toast("Call ended. Log the outcome below.");
  };

  // Email compose (in-platform, AI-drafted, sender-selectable).
  const senderName = (id: string) =>
    fromOptions.reps.find((x) => x.id === id)?.name ??
    fromOptions.mailboxes.find((x) => x.id === id)?.name ??
    "Optum Banking Solutions";
  const senderLabel = (id: string) => {
    const r = fromOptions.reps.find((x) => x.id === id);
    if (r) return `${r.name} <${r.email}>`;
    const m = fromOptions.mailboxes.find((x) => x.id === id);
    return m ? `${m.name} <${m.email}>` : id;
  };
  const buildDraft = (fromId: string, variant: number) =>
    provider && selectedLead
      ? draftProviderEmail(
          { provider, lead: selectedLead, fdmName: fdm?.name, nbo, fromName: senderName(fromId) },
          variant
        )
      : { subject: "", body: "" };

  const openCompose = () => {
    if (!provider || !selectedLead) return;
    const id =
      role === "sales_rep"
        ? CURRENT_REP_ID
        : selectedLead.assignedRepId ?? fromOptions.reps[0]?.id ?? fromOptions.mailboxes[0].id;
    const d = buildDraft(id, 0);
    setEmailFromId(id);
    setEmailTo(fdm?.email ?? "");
    setEmailVariant(0);
    setEmailSubject(d.subject);
    setEmailBody(d.body);
    setComposing(true);
  };
  const changeFrom = (id: string) => {
    setEmailFromId(id);
    const d = buildDraft(id, emailVariant);
    setEmailSubject(d.subject);
    setEmailBody(d.body);
  };
  const regenerate = () => {
    const v = emailVariant + 1;
    setEmailVariant(v);
    const d = buildDraft(emailFromId, v);
    setEmailSubject(d.subject);
    setEmailBody(d.body);
  };
  const sendEmail = () => {
    if (!provider) return;
    logEmail(provider.id, selectedLead?.id ?? null, senderLabel(emailFromId), emailSubject);
    toast(`Email sent to ${fdm?.name ?? emailTo} from ${senderName(emailFromId)}`);
    setComposing(false);
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
                    onClick={() => selectLead(l.id)}
                  >
                    <div className="row between">
                      <span className="qi-name">{p?.legalName ?? "Unknown"}</span>
                      <span className="num small strong" style={{ color: "var(--navy)" }}>
                        {money(l.offerAmount, true)}
                      </span>
                    </div>
                    <div className="row between center" style={{ marginTop: 6 }}>
                      <BankTierBadge tier={l.bankTier} />
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
                          <Button size="sm" variant="teal" onClick={startCall} disabled={!!calling}>
                            <PhoneCall size={13} /> Call
                          </Button>
                          <Button size="sm" variant="outline" onClick={openCompose}>
                            <Mail size={13} /> Email
                          </Button>
                        </div>
                        {calling && (
                          <div className="callbar">
                            <span className="callbar-dot" />
                            <div className="grow">
                              <div className="strong small">On call · {calling.name}</div>
                              <div className="tiny muted mono">
                                {calling.phone} · connected dialer
                              </div>
                            </div>
                            <Button size="sm" variant="danger" onClick={endCall}>
                              <PhoneOff size={13} /> End call
                            </Button>
                          </div>
                        )}
                      </div>
                    ) : (
                      <span className="small muted">No FDM on file</span>
                    )}
                  </div>

                  <div className="col gap-1">
                    <span className="tiny muted upper">Offer</span>
                    <div className="row gap-2 center wrap">
                      <BankTierBadge tier={selectedLead.bankTier} />
                      <span className="num strong">{money(selectedLead.offerAmount)}</span>
                      <span className="small muted">max offer</span>
                    </div>
                    <div className="tiny muted" style={{ marginTop: 2 }}>
                      Capital {money(selectedLead.capitalOffer)} (fee {money(selectedLead.capitalFee)})
                      {selectedLead.cashFlowOffer > 0
                        ? ` · Cash Flow ${money(selectedLead.cashFlowOffer)} (fee ${money(selectedLead.cashFlowFee)})`
                        : ""}
                    </div>
                    <div style={{ marginTop: 4 }}>
                      <StatusBadge code={selectedLead.status} />
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
            <div className="dispo-hint">
              Appointment-setter handoff: you qualified interest, now book a closing sales agent
              to follow up. You stay recorded as the setter on this appointment.
            </div>
            <Field label="Closing sales agent (follows up)">
              <select
                className="select"
                value={bookRepId}
                onChange={(e) => setBookRepId(e.target.value)}
              >
                <option value="">Select a closing sales agent</option>
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

      {composing && provider && (
        <Modal
          title={`Compose email - ${provider.legalName}`}
          onClose={() => setComposing(false)}
          width={660}
          footer={
            <>
              <Button variant="outline" onClick={() => setComposing(false)}>
                Cancel
              </Button>
              <Button onClick={sendEmail} disabled={!emailTo.trim() || !emailSubject.trim()}>
                <Send size={14} /> Send email
              </Button>
            </>
          }
        >
          <div className="col gap-3">
            <div className="row gap-2 center wrap">
              <Pill tone="navy" dot>
                <Sparkles size={12} /> Drafted by AI
              </Pill>
              <span className="tiny muted">
                Personalized to {provider.legalName} and their live offer.
              </span>
              <div className="grow" />
              <Button variant="text" onClick={regenerate}>
                <RefreshCw size={13} /> Regenerate
              </Button>
            </div>

            <Field label="From">
              <select
                className="select"
                value={emailFromId}
                onChange={(e) => changeFrom(e.target.value)}
              >
                <optgroup label="Send from a sales rep">
                  {fromOptions.reps.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name} · {r.email}
                    </option>
                  ))}
                </optgroup>
                <optgroup label="Send from a shared mailbox">
                  {fromOptions.mailboxes.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.name} · {m.email}
                    </option>
                  ))}
                </optgroup>
              </select>
            </Field>

            <Field label="To">
              <input
                className="select"
                value={emailTo}
                onChange={(e) => setEmailTo(e.target.value)}
              />
            </Field>

            <Field label="Subject">
              <input
                className="select"
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
              />
            </Field>

            <Field label={`Message (tone: ${VARIANT_LABELS[emailVariant % VARIANT_LABELS.length]})`}>
              <textarea
                rows={12}
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
              />
            </Field>

            <span className="tiny muted">
              Sends and logs on the provider timeline in-platform. Nothing routes through a
              personal mailbox.
            </span>
          </div>
        </Modal>
      )}
    </div>
  );
}
