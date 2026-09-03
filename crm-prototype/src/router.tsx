import { createBrowserRouter } from "react-router-dom";
import { Layout } from "./components/shell/Layout";
import { DashboardRouter } from "./features/dashboards/DashboardRouter";
import { CardLifecycleDashboard } from "./features/dashboards/CardLifecycleDashboard";
import { ProviderDirectory } from "./features/providers/ProviderDirectory";
import { Provider360 } from "./features/providers/Provider360";
import { IngestWizard } from "./features/ingest/IngestWizard";
import { LeadInbox } from "./features/leads/LeadInbox";
import { Pipeline } from "./features/leads/Pipeline";
import { CampaignsList } from "./features/campaigns/CampaignsList";
import { CampaignBuilder } from "./features/campaigns/CampaignBuilder";
import { CampaignDetail } from "./features/campaigns/CampaignDetail";
import { SegmentsPage } from "./features/campaigns/SegmentsPage";
import { SegmentBuilder } from "./features/campaigns/SegmentBuilder";
import { BroadcastsList } from "./features/broadcasts/BroadcastsList";
import { BroadcastBuilder } from "./features/broadcasts/BroadcastBuilder";
import { BroadcastDetail } from "./features/broadcasts/BroadcastDetail";
import { SalesConsole } from "./features/outbound/SalesConsole";
import { AppointmentsPage } from "./features/outbound/AppointmentsPage";
import { GoalsReport } from "./features/reporting/GoalsReport";
import { RepsAdmin } from "./features/admin/RepsAdmin";
import { ConnectorsAdmin } from "./features/admin/ConnectorsAdmin";
import { DataSourcesAdmin } from "./features/admin/DataSourcesAdmin";

export const router = createBrowserRouter(
  [
    {
      path: "/",
      element: <Layout />,
      children: [
        { index: true, element: <DashboardRouter /> },
        { path: "providers", element: <ProviderDirectory /> },
        { path: "providers/:id", element: <Provider360 /> },
        { path: "ingest", element: <IngestWizard /> },
        { path: "leads", element: <LeadInbox /> },
        { path: "pipeline", element: <Pipeline /> },
        { path: "campaigns", element: <CampaignsList /> },
        { path: "campaigns/new", element: <CampaignBuilder /> },
        { path: "campaigns/:id", element: <CampaignDetail /> },
        { path: "segments", element: <SegmentsPage /> },
        { path: "segments/new", element: <SegmentBuilder /> },
        { path: "segments/:id", element: <SegmentBuilder /> },
        { path: "broadcasts", element: <BroadcastsList /> },
        { path: "broadcasts/new", element: <BroadcastBuilder /> },
        { path: "broadcasts/:id", element: <BroadcastDetail /> },
        { path: "card-lifecycle", element: <CardLifecycleDashboard /> },
        { path: "console", element: <SalesConsole /> },
        { path: "appointments", element: <AppointmentsPage /> },
        { path: "reporting/goals", element: <GoalsReport /> },
        { path: "admin/reps", element: <RepsAdmin /> },
        { path: "admin/connectors", element: <ConnectorsAdmin /> },
        { path: "admin/sources", element: <DataSourcesAdmin /> },
      ],
    },
  ],
  { basename: import.meta.env.BASE_URL }
);
