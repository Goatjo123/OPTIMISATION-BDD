// Atelier 9 : générateur de charge HTTP (Node >= 22, modules standard).
//   charge FERMÉE : N clients, chacun relance une requête dès la réponse précédente (slide 20) ;
//   charge OUVERTE : arrivées à cadence fixe (req/s), indépendantes des durées ; la latence est comptée depuis l'instant
//   PRÉVU d'arrivée (pas depuis l'envoi), pour ne pas sous-représenter les demandes en retard (« coordinated omission »).
// Usage : node loadgen.mjs --base http://127.0.0.1:3001 --path "/commandes?limit=20&relations=n1" --mode closed --clients 10 --seconds 10 --warmup 3
//         node loadgen.mjs ... --mode open --rate 30 --seconds 10 --warmup 3
// Sortie : une ligne JSON (débit terminé, p50, p95, p99, erreurs). Le jeton est lu dans 01_server/api/.env, jamais affiché.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const a = Object.fromEntries(process.argv.slice(2).reduce((acc, v, i, arr) => (v.startsWith('--') ? [...acc, [v.slice(2), arr[i + 1]]] : acc), []));
const here = path.dirname(fileURLToPath(import.meta.url));
const env = {};
for (const line of fs.readFileSync(path.join(here, '..', '01_server', 'api', '.env'), 'utf8').split(/\r?\n/)) {
  const m = line.match(/^\s*([A-Z_]+)\s*=(.*)$/); if (m) env[m[1]] = m[2].trim();
}
const base = a.base ?? 'http://127.0.0.1:3001', url = base + a.path, headers = { Authorization: `Bearer ${env.LAB_TOKEN}` };
const mode = a.mode ?? 'closed', seconds = Number(a.seconds ?? 10), warmup = Number(a.warmup ?? 3);
const clients = Number(a.clients ?? 1), rate = Number(a.rate ?? 10);

async function one() {
  const r = await fetch(url, { headers });
  await r.arrayBuffer();
  return r.status;
}
function summarize(lat, errors, statuses, windowS, extra = {}) {
  lat.sort((x, y) => x - y);
  const p = q => lat.length ? Number(lat[Math.min(lat.length - 1, Math.ceil(q * lat.length) - 1)].toFixed(3)) : null;
  return { mode, path: a.path, clients: mode === 'closed' ? clients : undefined, rate: mode === 'open' ? rate : undefined,
    termines: lat.length, erreurs: errors, statuts: statuses, secondes: Number(windowS.toFixed(2)),
    debit_termine: Number((lat.length / windowS).toFixed(2)), mediane_ms: p(0.5), p95_ms: p(0.95), p99_ms: p(0.99),
    max_ms: lat.length ? Number(lat[lat.length - 1].toFixed(3)) : null, moyenne_ms: lat.length ? Number((lat.reduce((s, v) => s + v, 0) / lat.length).toFixed(3)) : null, ...extra };
}

async function closed() {
  let measuring = false, stop = false; const lat = [], statuses = {}; let errors = 0;
  const worker = async () => {
    while (!stop) {
      const t = performance.now();
      try {
        const s = await one();
        if (measuring) { statuses[s] = (statuses[s] ?? 0) + 1; if (s === 200) lat.push(performance.now() - t); else errors++; }
      } catch { if (measuring) errors++; }
    }
  };
  const ws = Array.from({ length: clients }, worker);
  await new Promise(r => setTimeout(r, warmup * 1000));
  measuring = true; const t0 = performance.now();
  await new Promise(r => setTimeout(r, seconds * 1000));
  measuring = false; stop = true; const win = (performance.now() - t0) / 1000;
  await Promise.all(ws);
  return summarize(lat, errors, statuses, win);
}

async function open() {
  const lat = [], statuses = {}, lags = []; let errors = 0, inflight = 0, lancees = 0, maxInflight = 0;
  const interval = 1000 / rate, total = Math.floor(seconds * rate);
  const startAll = performance.now();
  const launch = async (sched, measured) => {
    inflight++; maxInflight = Math.max(maxInflight, inflight);
    const sent = performance.now(); if (measured) lags.push(sent - sched);
    try {
      const s = await one();
      if (measured) { statuses[s] = (statuses[s] ?? 0) + 1; if (s === 200) lat.push(performance.now() - sched); else errors++; }
    } catch { if (measured) errors++; }
    inflight--;
  };
  const pending = [];
  const nWarm = Math.floor(warmup * rate);
  for (let i = 0; i < nWarm + total; i++) {
    const sched = startAll + i * interval;
    const wait = sched - performance.now();
    if (wait > 0) await new Promise(r => setTimeout(r, wait));
    lancees++;
    pending.push(launch(sched, i >= nWarm));
  }
  const tEnd = performance.now();
  await Promise.race([Promise.all(pending), new Promise(r => setTimeout(r, 15000))]);
  const win = seconds;
  return summarize(lat, errors, statuses, win, { arrivees_prevues: total, non_terminees: total - lat.length - errors, en_vol_max: maxInflight,
    retard_envoi_max_ms: lags.length ? Number(Math.max(...lags).toFixed(2)) : 0, retard_envoi_p95_ms: lags.length ? Number(lags.sort((x, y) => x - y)[Math.ceil(0.95 * lags.length) - 1].toFixed(2)) : 0 });
}

console.log(JSON.stringify(await (mode === 'open' ? open() : closed())));
process.exit(0);
