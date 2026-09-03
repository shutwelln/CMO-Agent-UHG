import type { Connector, DataSource, Dataset } from "../schema";

/*
 * Seeds the delivery + data plane in-app so the shipped dataset.json stays
 * back-compatible. The CRM owns orchestration; connectors only handle delivery.
 * SendGrid is the active direct-ESP path for the card launch, Adobe Journey
 * Optimizer is the concurrent strategic path (data backbone via AEP), and
 * Marketo is legacy/sunsetting. AEP Real-Time CDP is modeled as a data source
 * (a CDP, not an ESP): card events stream in, audiences activate out.
 */

const CONNECTORS: Connector[] = [
  {
    id: "conn_sendgrid",
    name: "SendGrid",
    kind: "esp",
    mode: "direct_esp",
    lifecycle: "active",
    status: "connected_mock",
    isApprovedVendor: true,
    note: "Direct ESP. The CRM owns segments, journeys, and triggers; SendGrid handles delivery, deliverability, suppression, and delivery-event webhooks (open, click, bounce, unsubscribe). Fastest path to ship the card launch.",
  },
  {
    id: "conn_ajo",
    name: "Adobe Journey Optimizer",
    kind: "esp",
    mode: "experience_platform",
    lifecycle: "roadmap",
    status: "not_approved",
    isApprovedVendor: false,
    note: "Strategic path, building toward. Real-time journeys on Adobe Experience Platform, API-triggered campaigns with High Throughput transactional delivery, and consent at the data plane. Leverages the company Adobe investment.",
  },
  {
    id: "conn_marketo",
    name: "Marketo",
    kind: "esp",
    mode: "orchestration_platform",
    lifecycle: "legacy",
    status: "connected_mock",
    isApprovedVendor: true,
    note: "Legacy, sunsetting. Shared-instance queue makes changes slow, and it is not used for the card lifecycle. Existing non-card programs migrate off over time.",
  },
];

const AEP_SOURCE: DataSource = {
  id: "ds_aep",
  name: "Adobe Experience Platform (Real-Time CDP)",
  kind: "cdp",
  status: "mock",
  lastSync: "2026-08-22T11:30:00.000Z",
  recordCount: 1_028_400,
  note: "Profile, identity, and consent source of truth. Card lifecycle events stream in (Streaming Ingestion, XDM); AEP audiences activate out to the CRM over a custom HTTP destination. This is the data backbone we build toward while shipping on a direct ESP today.",
};

/* Replace connectors with the delivery-plane set and add AEP as a data source. */
export function seedDeliveryPlane(data: Dataset): void {
  data.connectors = CONNECTORS;
  if (!data.dataSources.some((d) => d.id === AEP_SOURCE.id)) {
    data.dataSources = [AEP_SOURCE, ...data.dataSources];
  }
}
