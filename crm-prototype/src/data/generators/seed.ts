/* Run with `npm run seed`. Writes deterministic synthetic fixtures to JSON so
 * the deployed app needs no runtime backend. */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { generateDataset } from "./generate";

const __dirname = dirname(fileURLToPath(import.meta.url));
// Served statically and fetched at startup (keeps the JS bundle small).
const outDir = resolve(__dirname, "../../../public/data");
mkdirSync(outDir, { recursive: true });

const data = generateDataset(42);
const outPath = resolve(outDir, "dataset.json");
writeFileSync(outPath, JSON.stringify(data));

const sizeMb = (JSON.stringify(data).length / 1_048_576).toFixed(2);
console.log(`Seeded ${outPath} (${sizeMb} MB)`);
console.log(
  `  providers=${data.providers.length} contacts=${data.contacts.length} leads=${data.leads.length} ` +
    `funnelEvents=${data.funnelEvents.length} activities=${data.activities.length} ` +
    `reps=${data.reps.length} campaigns=${data.campaigns.length} appts=${data.appointments.length}`
);
