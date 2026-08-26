import { create } from "zustand";
import clsx from "clsx";
import type { ReactNode, ButtonHTMLAttributes } from "react";
import { X, Check, Inbox, Mail, Phone } from "lucide-react";
import {
  PRODUCT_SHORT,
  STAGE_LABEL,
  type Confidence,
  type Product,
  type Stage,
  type Tier,
} from "../../data/schema";

/* ---------- Button ---------- */
type BtnVariant = "primary" | "outline" | "orange" | "teal" | "ghost" | "danger" | "text";
export function Button({
  variant = "primary",
  size,
  className,
  children,
  ...rest
}: {
  variant?: BtnVariant;
  size?: "sm" | "lg";
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={clsx(
        variant === "text" ? "btn-text" : `btn btn-${variant}`,
        size === "sm" && "btn-sm",
        size === "lg" && "btn-lg",
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

export function IconButton({ children, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button className={clsx("btn-icon", className)} {...rest}>
      {children}
    </button>
  );
}

/* ---------- Panel ---------- */
export function Panel({ children, className, tint }: { children: ReactNode; className?: string; tint?: boolean }) {
  return <div className={clsx(tint ? "panel-tint" : "panel", className)}>{children}</div>;
}
export function PanelHeader({ title, action }: { title: ReactNode; action?: ReactNode }) {
  return (
    <div className="panel-hd">
      <h3>{title}</h3>
      {action}
    </div>
  );
}

/* ---------- StatCard ---------- */
export function StatCard({
  label,
  value,
  delta,
  deltaDir,
  icon,
  iconColor,
}: {
  label: ReactNode;
  value: ReactNode;
  delta?: string;
  deltaDir?: "up" | "down";
  icon?: ReactNode;
  iconColor?: string;
}) {
  return (
    <div className="statcard">
      <div className="sc-label">
        {icon && (
          <span className="sc-ico" style={{ background: iconColor ? `${iconColor}1a` : "var(--navy-tint)", color: iconColor ?? "var(--navy)" }}>
            {icon}
          </span>
        )}
        {label}
      </div>
      <div className="sc-value">{value}</div>
      {delta && <div className={clsx("sc-delta", deltaDir === "down" ? "sc-down" : "sc-up")}>{delta}</div>}
    </div>
  );
}

/* ---------- Pills / badges ---------- */
export function Pill({ tone = "gray", children, dot }: { tone?: string; children: ReactNode; dot?: boolean }) {
  return (
    <span className={`pill pill-${tone}`}>
      {dot && <span className="pill-dot" style={{ background: "currentColor" }} />}
      {children}
    </span>
  );
}

const STAGE_TONE: Record<Stage, string> = {
  new: "gray",
  working: "blue",
  contacted: "navy",
  qualified: "teal",
  appt_set: "orange",
  won: "green",
  lost: "red",
};
export function StageBadge({ stage }: { stage: Stage }) {
  return <Pill tone={STAGE_TONE[stage]} dot>{STAGE_LABEL[stage]}</Pill>;
}

const PRODUCT_TONE: Record<Product, string> = {
  pwc: "pwc",
  bank_account: "bank",
  term_loan: "term",
  loc: "loc",
  equipment: "equip",
  cash_acceleration: "cash",
};
export function ProductBadge({ product }: { product: Product }) {
  const tone = PRODUCT_TONE[product];
  return (
    <span
      className="pill"
      style={{ background: `var(--p-${tone}-bg)`, color: `var(--p-${tone})` }}
    >
      {PRODUCT_SHORT[product]}
    </span>
  );
}

export function TierBadge({ tier }: { tier: Tier }) {
  const tone = tier === "senior" ? "navy" : tier === "mid" ? "blue" : "gray";
  const label = tier === "senior" ? "Senior" : tier === "mid" ? "Mid" : "Junior";
  return <Pill tone={tone}>{label}</Pill>;
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  if (confidence === "none") return <Pill tone="red">No FDM</Pill>;
  const tone = confidence === "high" ? "green" : confidence === "med" ? "amber" : "gray";
  const label = confidence === "high" ? "High" : confidence === "med" ? "Med" : "Low";
  return <Pill tone={tone}>{label}</Pill>;
}

/* ---------- Page header ---------- */
export function PageHeader({
  crumb,
  title,
  sub,
  action,
}: {
  crumb?: string;
  title: ReactNode;
  sub?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="pagehead">
      <div>
        {crumb && <div className="ph-crumb">{crumb}</div>}
        <h1>{title}</h1>
        {sub && <div className="ph-sub">{sub}</div>}
      </div>
      {action && <div className="row gap-2">{action}</div>}
    </div>
  );
}

/* ---------- Banner ---------- */
export function Banner({
  tone = "info",
  icon,
  children,
}: {
  tone?: "info" | "success" | "warn";
  icon?: ReactNode;
  children: ReactNode;
}) {
  const bg = tone === "success" ? "#bfe3cd" : tone === "warn" ? "#f0dfae" : "#cfe0f5";
  return (
    <div className={`banner banner-${tone}`}>
      {icon && <span className="b-ico" style={{ background: bg }}>{icon}</span>}
      <div className="grow">{children}</div>
    </div>
  );
}

/* ---------- Stepper ---------- */
export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <div className="stepper">
      {steps.map((s, i) => (
        <div key={s} className={clsx("step", i === current && "active", i < current && "done")}>
          {i > 0 && <span className="step-line" />}
          <span className="step-dot">{i < current ? <Check size={15} /> : i + 1}</span>
          <span className="step-label">{s}</span>
        </div>
      ))}
    </div>
  );
}

/* ---------- Modal ---------- */
export function Modal({ title, onClose, children, footer, width }: { title: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; width?: number }) {
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="modal" style={width ? { width } : undefined} role="dialog">
        <div className="modal-hd">
          <h3>{title}</h3>
          <IconButton onClick={onClose} aria-label="Close"><X size={18} /></IconButton>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-ft">{footer}</div>}
      </div>
    </>
  );
}

export function Drawer({ onClose, children, width }: { onClose: () => void; children: ReactNode; width?: number }) {
  return (
    <>
      <div className="overlay" onClick={onClose} />
      <div className="drawer" style={width ? { width } : undefined} role="dialog">
        {children}
      </div>
    </>
  );
}

/* ---------- Field ---------- */
export function Field({ label, children }: { label: ReactNode; children: ReactNode }) {
  return (
    <div className="field">
      <label>{label}</label>
      {children}
    </div>
  );
}

/* ---------- EmptyState ---------- */
export function EmptyState({ title, sub, icon }: { title: string; sub?: string; icon?: ReactNode }) {
  return (
    <div className="empty">
      <div className="e-ico">{icon ?? <Inbox size={22} />}</div>
      <div className="strong" style={{ color: "var(--text-main)" }}>{title}</div>
      {sub && <div className="small" style={{ marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

/* ---------- Avatar ---------- */
export function Avatar({ initials, sm }: { initials: string; sm?: boolean }) {
  return <span className={clsx("avatar", sm && "avatar-sm")}>{initials}</span>;
}

/* ---------- Progress ---------- */
export function Progress({ value, color }: { value: number; color?: string }) {
  return (
    <div className="progress">
      <span style={{ width: `${Math.min(100, Math.max(0, value))}%`, background: color }} />
    </div>
  );
}

/* ---------- Toast ---------- */
interface Toast { id: number; message: string; }
interface ToastState { toasts: Toast[]; push: (m: string) => void; remove: (id: number) => void; }
let tid = 1;
export const useToast = create<ToastState>((set) => ({
  toasts: [],
  push: (message) => {
    const id = tid++;
    set((s) => ({ toasts: [...s.toasts, { id, message }] }));
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 3600);
  },
  remove: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

export function ToastHost() {
  const toasts = useToast((s) => s.toasts);
  return (
    <div className="toast-wrap">
      {toasts.map((t) => (
        <div className="toast" key={t.id}>
          <span className="t-ico"><Check size={16} /></span>
          {t.message}
        </div>
      ))}
    </div>
  );
}

export function MockChip({ label = "Synthetic Data" }: { label?: string }) {
  return <span className="mockchip">{label}</span>;
}

/* ---------- Contact actions (click-to-call / click-to-email) ----------
 * Enables both internal sales specialists and a 3rd-party call center to act
 * on a provider directly. tel: and mailto: open the operator's dialer / mail. */
export function CallButton({ phone, size }: { phone: string; size?: "sm" }) {
  return (
    <a
      className={`contact-btn${size === "sm" ? " contact-btn-sm" : ""}`}
      href={`tel:${phone.replace(/[^\d+]/g, "")}`}
      onClick={(e) => e.stopPropagation()}
    >
      <Phone size={13} /> Call
    </a>
  );
}

export function EmailButton({ email, subject, size }: { email: string; subject?: string; size?: "sm" }) {
  const href = `mailto:${email}${subject ? `?subject=${encodeURIComponent(subject)}` : ""}`;
  return (
    <a
      className={`contact-btn${size === "sm" ? " contact-btn-sm" : ""}`}
      href={href}
      onClick={(e) => e.stopPropagation()}
    >
      <Mail size={13} /> Email
    </a>
  );
}
