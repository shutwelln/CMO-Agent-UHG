import { create } from "zustand";

export type Role = "sales_rep" | "marketing" | "sales_ops";

export const ROLE_LABEL: Record<Role, string> = {
  sales_rep: "Sales Specialist",
  marketing: "Campaign Management",
  sales_ops: "Sales Ops / Admin",
};

export const ROLE_DESC: Record<Role, string> = {
  sales_rep: "Work assigned leads, providers, and appointments",
  marketing: "Trigger lifecycle campaigns against funnel segments",
  sales_ops: "Ingest data, assign leads, configure connectors",
};

// The signed-in sales specialist for the Sales Specialist role view.
export const CURRENT_REP_ID = "rep_1"; // Angelo Altavilla (senior)

// Signed-in people for the other roles.
export const OPS_LEAD_NAME = "Manav Mendonca"; // uploads files, pulls lists, assigns leads
export const GROWTH_LEAD_NAME = "Growth & Marketing"; // growth/marketing seat (name TBD)

interface RoleState {
  role: Role;
  setRole: (r: Role) => void;
}

export const useRole = create<RoleState>((set) => ({
  role: "sales_ops",
  setRole: (role) => set({ role }),
}));
