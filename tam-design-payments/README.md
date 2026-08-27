# TAM Design · Payments Preview Deck

Static prototype deck for Optum Financial payments design reviews. Mirrored into
CMO-Agent-UHG so it deploys through the same git pipeline as the rest of the site
(edit here, push to `main`, Vercel auto-deploys).

## Pages (served with cleanUrls)
- `index.html` — the preview deck / gallery
- `provider-portal.html` (`/provider-portal`) — Provider Payment Portal, incl. the provider **sign-in** (One Healthcare ID)
- `payer-portal.html` (`/payer-portal`) — Payer Portal; CCS/Payments variants via `?portal=ccs|payments`
- `banking-solutions.html` (`/banking-solutions`) — mounts provider-portal screens (one source of truth)
- `provider-preferencing.html` (`/provider-preferencing`)
- `summarization.html` (`/summarization`) — Consolidated Payments

Self-contained static HTML (some pages load Tailwind/React from CDN at runtime).
