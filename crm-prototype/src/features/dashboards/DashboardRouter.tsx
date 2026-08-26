import { useRole } from "../../context/role";
import { SalesRepDashboard } from "./SalesRepDashboard";
import { MarketingDashboard } from "./MarketingDashboard";
import { SalesOpsDashboard } from "./SalesOpsDashboard";

export function DashboardRouter() {
  const role = useRole((s) => s.role);
  if (role === "sales_rep") return <SalesRepDashboard />;
  if (role === "marketing") return <MarketingDashboard />;
  return <SalesOpsDashboard />;
}
