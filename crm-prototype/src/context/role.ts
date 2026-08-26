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

// A representative signed-in rep for the Sales Rep role view.
export const CURRENT_REP_ID = "rep_1"; // Marcus Webb (senior)

interface RoleState {
  role: Role;
  setRole: (r: Role) => void;
}

export const useRole = create<RoleState>((set) => ({
  role: "sales_ops",
  setRole: (role) => set({ role }),
}));
