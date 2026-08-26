import { useState } from "react";
import { Link } from "react-router-dom";
import { Search, Bell, ChevronDown, Check, HelpCircle, Sparkles } from "lucide-react";
import { useRole, ROLE_LABEL, ROLE_DESC, type Role } from "../../context/role";
import { useTour } from "../../context/tour";

const ROLES: Role[] = ["sales_ops", "sales_rep", "marketing"];

function RoleSwitcher() {
  const { role, setRole } = useRole();
  const [open, setOpen] = useState(false);
  return (
    <div className="roleswitch">
      <button className="roleswitch-btn" onClick={() => setOpen((o) => !o)}>
        <div className="col" style={{ alignItems: "flex-start", lineHeight: 1.2 }}>
          <span className="rs-you">Viewing as</span>
          <span className="rs-role">{ROLE_LABEL[role]}</span>
        </div>
        <ChevronDown size={16} />
      </button>
      {open && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 55 }} onClick={() => setOpen(false)} />
          <div className="roleswitch-menu">
            <div className="rs-hd">Switch role</div>
            {ROLES.map((r) => (
              <div
                key={r}
                className={`roleswitch-item ${r === role ? "active" : ""}`}
                onClick={() => {
                  setRole(r);
                  setOpen(false);
                }}
              >
                <div>
                  <div className="rs-name">{ROLE_LABEL[r]}</div>
                  <div className="rs-desc">{ROLE_DESC[r]}</div>
                </div>
                {r === role && <Check size={16} className="rs-check" />}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

export function AppHeader() {
  const startTour = useTour((s) => s.start);
  return (
    <header className="appheader">
      <Link to="/" className="brand" aria-label="Provider Flux Capacitor home">
        <img src={`${import.meta.env.BASE_URL}brand/optum_logo.svg`} alt="Optum" />
        <span className="brand-txt">
          Provider <span className="brand-sub">Flux Capacitor</span>
        </span>
      </Link>
      <div className="h-search">
        <Search size={15} />
        <input placeholder="Search providers, TINs, leads…" />
      </div>
      <div className="h-right">
        <button className="tour-btn" onClick={startTour}>
          <Sparkles size={14} /> Take the tour
        </button>
        <button className="h-iconbtn" aria-label="Help"><HelpCircle size={19} /></button>
        <button className="h-iconbtn" aria-label="Notifications"><Bell size={19} /></button>
        <RoleSwitcher />
      </div>
    </header>
  );
}
