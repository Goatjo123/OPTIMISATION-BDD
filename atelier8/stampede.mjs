// Atelier 8, ajout : N lectures SIMULTANÉES du même produit quand sa clé Redis est absente (slide 31).
// Lit le jeton dans 01_server/api/.env (jamais affiché). Usage : node atelier8/stampede.mjs [N]
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const env = {};
for (const line of fs.readFileSync(path.join(here, '..', '01_server', 'api', '.env'), 'utf8').split(/\r?\n/)) {
  const m = line.match(/^\s*([A-Z_]+)\s*=(.*)$/); if (m) env[m[1]] = m[2].trim();
}
const n = Number(process.argv[2] ?? 20);
const base = `http://127.0.0.1:${env.PORT ?? 3000}`;
async function one() {
  const t = performance.now();
  const r = await fetch(base + '/produits/42', { headers: { Authorization: `Bearer ${env.LAB_TOKEN}` } });
  await r.text();
  return { status: r.status, cache: r.headers.get('X-Cache'), sql: Number(r.headers.get('X-SQL-Count')),
           trace: r.headers.get('X-Trace-Id'), ms: Number((performance.now() - t).toFixed(1)) };
}
const res = await Promise.all(Array.from({ length: n }, one));
console.log(JSON.stringify(res));
