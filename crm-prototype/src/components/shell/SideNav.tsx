import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Inbox,
  GitBranch,
  UploadCloud,
  Megaphone,
  Send,
  Layers,
  CreditCard,
  PhoneCall,
  CalendarCheck,
  UsersRound,
  Plug,
  Database,
  Target,
  Lock,
} from "lucide-react";
import type { ReactNode } from "react";
import { useRole, type Role } from "../../context/role";
import { useData } from "../../data/store";
import { leadsForRep } from "../../data/selectors";
import { CURRENT_REP_ID } from "../../context/role";

interface Item {
  to: string;
  label: string;
  icon: ReactNode;
  roles: Role[];
  count?: number;
  locked?: boolean;
}
interface Group {
  label: string;
  items: Item[];
}

export function SideNav() {
  const role = useRole((s) => s.role);
  const data = useData((s) => s.data);
  const myLeads = data ? leadsForRep(data, CURRENT_REP_ID).filter((l) => l.stage !== "disbursed" && l.stage !== "closed").length : 0;
  const leadCount = data ? data.leads.filter((l) => l.stage === "ready").length : 0;
  const campaignCount = data ? data.campaigns.filter((c) => c.status === "active").length : 0;
  const broadcastCount = data ? data.broadcasts.filter((b) => b.status === "scheduled").length : 0;
  const cardCampaignCount = data ? data.campaigns.filter((c) => c.id.startsWith("camp_card_") && c.status === "active").length : 0;

  const groups: Group[] = [
    {
      label: "Overview",
      items: [{ to: "/", label: "Dashboard", icon: <LayoutDashboard size={18} />, roles: ["sales_rep", "marketing", "sales_ops"] }],
    },
    {
      label: "Leads",
      items: [
        { to: "/leads", label: "Lead Inbox", icon: <Inbox size={18} />, roles: ["sales_rep", "sales_ops"], count: role === "sales_rep" ? myLeads : leadCount },
        { to: "/pipeline", label: "Pipeline", icon: <GitBranch size={18} />, roles: ["sales_rep", "sales_ops"] },
        { to: "/ingest", label: "Ingest Wizard", icon: <UploadCloud size={18} />, roles: ["sales_ops"] },
      ],
    },
    {
      label: "Providers",
      items: [{ to: "/providers", label: "Provider 360", icon: <Users size={18} />, roles: ["sales_rep", "marketing", "sales_ops"] }],
    },
    {
      label: "Campaigns",
      items: [
        { to: "/campaigns", label: "Lifecycle Campaigns", icon: <Megaphone size={18} />, roles: ["marketing", "sales_ops"], count: campaignCount },
        { to: "/broadcasts", label: "Broadcasts", icon: <Send size={18} />, roles: ["marketing", "sales_ops"], count: broadcastCount },
        { to: "/segments", label: "Segments", icon: <Layers size={18} />, roles: ["marketing", "sales_ops"] },
      ],
    },
    {
      label: "Card Launch",
      items: [
        { to: "/card-lifecycle", label: "Provider Card + LOC", icon: <CreditCard size={18} />, roles: ["marketing", "sales_ops"], count: cardCampaignCount },
      ],
    },
    {
      label: "Outbound",
      items: [
        { to: "/console", label: "Sales Console", icon: <PhoneCall size={18} />, roles: ["sales_rep", "sales_ops"] },
        { to: "/appointments", label: "Appointments", icon: <CalendarCheck size={18} />, roles: ["sales_rep", "sales_ops"] },
      ],
    },
    {
      label: "Reporting",
      items: [
        { to: "/reporting/goals", label: "Goals & Targets", icon: <Target size={18} />, roles: ["sales_rep", "marketing", "sales_ops"] },
      ],
    },
    {
      label: "Admin",
      items: [
        { to: "/admin/reps", label: "Sales Specialists", icon: <UsersRound size={18} />, roles: ["sales_ops"] },
        { to: "/admin/connectors", label: "Connectors", icon: <Plug size={18} />, roles: ["sales_ops"] },
        { to: "/admin/sources", label: "Data Sources", icon: <Database size={18} />, roles: ["sales_ops"] },
      ],
    },
  ];

  return (
    <nav className="sidenav">
      {groups.map((g) => {
        const items = g.items.filter((i) => i.roles.includes(role));
        if (items.length === 0) return null;
        return (
          <div className="nav-group" key={g.label}>
            <div className="nav-group-label">{g.label}</div>
            {items.map((i) => (
              <NavLink key={i.to} to={i.to} end={i.to === "/"} className={({ isActive }) => `navitem ${isActive ? "active" : ""}`}>
                <span className="ni-ico">{i.icon}</span>
                {i.label}
                {i.locked ? <Lock size={14} className="ni-lock" /> : i.count ? <span className="ni-count">{i.count}</span> : null}
              </NavLink>
            ))}
          </div>
        );
      })}
    </nav>
  );
}
