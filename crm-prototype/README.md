# Optum Banking Solutions — Provider CRM (Vision Prototype)

A demo-quality, clickable prototype of a marketing and sales CRM for Optum Financial / Optum Banking Solutions. It paints the vision for a system that ingests the monthly bank offer file, merges and enriches financial-decision-maker (FDM) data by TIN, auto-assigns leads by deal size, exposes provider signup-funnel events, and lets marketing and sales self-serve trigger lifecycle and outbound campaigns.

This is a prototype: it runs on synthetic data with all integrations stubbed as clearly-labeled connectors. It is structured so an engineering team can wire in production feeds later.

## Run locally

```bash
npm install
npm run seed      # regenerate synthetic fixtures into public/data/dataset.json (already committed)
npm run dev       # http://localhost:5173
```

Build check: `npm run build && npm run preview`.

## Deploy (Vercel)

The app is a static SPA. Point a Vercel project at this `crm-prototype/` directory as the root; `vercel.json` sets the Vite build and the SPA rewrite. Deploy into the same account as the existing Optum demos so it shares the environment and URL structure.

## Modules

- Lead Ingest Wizard — upload the monthly bank file, map columns, TIN merge, FDM append (coverage lift), auto-assign by deal-size tiers.
- Lead Inbox + Pipeline — data-dense lead table and a kanban with outreach-attempt tracking.
- Provider 360 — firmographics, funnel timeline (signup started, stuck, completed, funded, loan originated), activities, and a Next-Best-Offer rail.
- Marketing Lifecycle Campaigns — segment builder with a live audience counter, journey library, swappable Marketo / Customer.io connectors, mock launch.
- Outbound Sales Console + Appointments — work queue, dispositions, product-interest capture, appointment setting to senior reps.
- Role switcher — Sales Rep, Marketing, Sales Ops / Admin.

## Design

The look and feel is extracted from the live Optum demos (see `design-refs/`): navy `#002677`, orange `#FF612B`, teal, cream surfaces, Figtree typeface, pill buttons. Tokens live in `src/styles/tokens.css`.

## Architecture (for the engineering handoff)

- `src/data/schema/` — zod schemas that double as the production data contract.
- `src/data/store.ts` — in-memory store; each read maps to a REST GET and each action to a POST/PATCH in the real build.
- Integration stubs (Admin -> Data Sources / Connectors) map to: the provider master data warehouse feed, the monthly bank SFTP file, a third-party FDM data vendor API, the Marketo / Customer.io ESP APIs, and the downstream Salesforce Go commission export.

Synthetic data is deterministic (fixed RNG seed) so every build is identical.
