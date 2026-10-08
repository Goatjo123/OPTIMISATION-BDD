#!/usr/bin/env python3
"""Atelier 9 (slide 21) : la courbe de charge. Jour 5, slides 18 à 22 et 24.

Même consultation testée avec 1, 5, 10 et 20 clients, avec la même durée (10 s) et le même échauffement (3 s), 3 répétitions en
ordre alterné, UN SEUL changement par série :
  A. SQL (pgbench, script de la slide 19, protocole simple) : sans index / avec l'index composé de l'atelier 3 ;
  B. HTTP (loadgen.mjs, charge fermée, GET /commandes?limit=20) : N+1 / chargement groupé ;
  C. HTTP, N+1, 20 clients : taille du pool de l'API 5 / 10 / 20 (« agrandir le pool déplace-t-il la saturation ? ») ;
  D. HTTP, N+1 : charge fermée (20 clients) contre charge ouverte à 3 cadences (slide 20) ;
  E. OLTP contre rapport : pgbench (historique, 10 clients) seul puis pendant des rapports analytiques sur la même instance (slide 24).
Pendant chaque mesure : file d'attente du pool de l'API (/observations), sessions PostgreSQL actives, CPU et charge de la machine.
Toutes sur la copie jetable a9-pg (le laboratoire n'est jamais touché). Usage : python3 atelier9/p2_charge.py (environ 20 minutes)
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

API_DIR = os.path.join(ROOT, "01_server", "api")
LOADGEN = os.path.join(ROOT, "atelier9", "loadgen.mjs")
LEVELS = [1, 5, 10, 20]
SECONDS, WARMUP, REPEATS = 10, 3, 3
PORT = 3001
R = {"debut": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": machine(), "version": q("SELECT version()"), "duree_s": SECONDS, "echauffement_s": WARMUP, "repetitions": REPEATS}
HIST = ("\\set client_id random(1, 1000)\nSELECT id, created_at, total FROM commandes WHERE client_id = :client_id "
        "ORDER BY created_at DESC, id DESC LIMIT 20;\n")
REPORT = ("SELECT (created_at AT TIME ZONE 'UTC')::date AS jour, count(*) AS nb_commandes, sum(total) AS montant FROM commandes "
          "WHERE statut = 'payee' GROUP BY 1 ORDER BY 1;\n")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def put(path, text):
    subprocess.run(["docker", "exec", "-i", COPIE, "sh", "-c", f"cat > {path}"], input=text, text=True, check=True)


# ----------------------------------------------------------------------------- échantillonnage
class Echantillon:
    """Une fois par seconde : pool de l'API, sessions PostgreSQL, CPU et charge machine."""

    def __init__(self, api_port=None):
        self.api_port, self.rows, self.stop = api_port, [], False
        self.th = threading.Thread(target=self.run)

    @staticmethod
    def cpu():
        with open("/proc/stat") as f:
            v = list(map(int, f.readline().split()[1:]))
        return sum(v), v[3] + v[4]

    def run(self):
        t0, i0 = self.cpu()
        while not self.stop:
            time.sleep(1.0)
            row = {}
            try:
                if self.api_port:
                    with urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{self.api_port}/observations", headers={"Authorization": f"Bearer {TOKEN}"}), timeout=2) as r:
                        d = json.loads(r.read())["pool"]
                    row["pool_attente"], row["pool_total"] = d["enAttente"], d["total"]
            except Exception:
                pass
            try:
                row["pg_actives"] = int(q("SELECT count(*) FROM pg_stat_activity WHERE datname='shopflow' AND state='active' AND pid<>pg_backend_pid()"))
            except Exception:
                pass
            t1, i1 = self.cpu()
            row["cpu_pct"] = round(100 * (1 - (i1 - i0) / max(1, t1 - t0)), 1); t0, i0 = t1, i1
            row["charge_1min"] = float(open("/proc/loadavg").read().split()[0])
            self.rows.append(row)

    def start(self):
        self.th.start(); return self

    def end(self):
        self.stop = True; self.th.join()
        def agg(k, f):
            v = [r[k] for r in self.rows if k in r]
            return f(v) if v else None
        return {"echantillons": len(self.rows), "pool_attente_max": agg("pool_attente", max), "pg_actives_max": agg("pg_actives", max),
                "cpu_pct_moyen": agg("cpu_pct", lambda v: round(sum(v) / len(v), 1)), "cpu_pct_max": agg("cpu_pct", max), "charge_1min_max": agg("charge_1min", max)}


TOKEN = [l.strip().split("=", 1)[1] for l in open(os.path.join(API_DIR, ".env")) if l.startswith("LAB_TOKEN=")][0]


def start_api(pool_max=5):
    env = dict(os.environ, DATABASE_URL="postgresql://cours:cours-local@127.0.0.1:55433/shopflow", PORT=str(PORT), POOL_MAX=str(pool_max))
    p = subprocess.Popen(["node", "--env-file=.env", "server.mjs"], cwd=API_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
        except urllib.error.HTTPError:
            return p
        except Exception:
            time.sleep(0.25)
    raise RuntimeError("API non démarrée")


def stop_api(p):
    p.terminate()
    try:
        p.wait(timeout=10)
    except Exception:
        p.kill()


# ----------------------------------------------------------------------------- pgbench
def pgbench(script, clients, seconds, warm=False, log=True):
    prefix = f"/tmp/pgb_{os.getpid()}_{int(time.time()*1000)}"
    cmd = ["docker", "exec", "-e", "PGOPTIONS=-c search_path=shopflow", "-e", "PGPASSWORD=cours-local", COPIE, "pgbench", "-U", "cours", "-d", "shopflow", "-n", "-M", "simple",
           "-f", script, "-c", str(clients), "-j", str(min(clients, 4)), "-T", str(seconds)]
    if log and not warm:
        cmd += ["-l", f"--log-prefix={prefix}"]
    return cmd, prefix


def run_pgbench(script, clients, seconds=SECONDS, warmup=WARMUP, sampler=True):
    wcmd, _ = pgbench(script, clients, warmup, warm=True)
    sh(wcmd)
    cmd, prefix = pgbench(script, clients, seconds)
    smp = Echantillon().start() if sampler else None
    res = sh(cmd)
    s = smp.end() if smp else None
    out = res.stdout + res.stderr
    lat = []
    logs = sh(["docker", "exec", COPIE, "sh", "-c", f"cat {prefix}* 2>/dev/null; rm -f {prefix}*"]).stdout.splitlines()
    for l in logs:
        parts = l.split()
        if len(parts) >= 3 and parts[2].isdigit():
            lat.append(int(parts[2]) / 1000.0)
    tps = re.search(r"tps = ([\d.]+)", out)
    fails = re.search(r"number of failed transactions: (\d+)", out)
    return {"clients": clients, "tps": float(tps.group(1)) if tps else None, "transactions": len(lat), "echecs": int(fails.group(1)) if fails else 0,
            "mediane_ms": med(lat) if lat else None, "p95_ms": pct(lat, 95) if lat else None, "p99_ms": pct(lat, 99) if lat else None, "max_ms": round(max(lat), 3) if lat else None,
            "machine": s, "code": res.returncode, "sortie_brute": out.strip().splitlines()[-12:]}


def idx(on):
    present = q("SELECT count(*) FROM pg_indexes WHERE indexname='a9_idx_hist'") == "1"
    if on and not present:
        q("CREATE INDEX a9_idx_hist ON shopflow.commandes (client_id, created_at DESC, id DESC)"); q("ANALYZE shopflow.commandes")
    if not on and present:
        q("DROP INDEX shopflow.a9_idx_hist"); q("ANALYZE shopflow.commandes")


def loadgen(path, mode="closed", clients=1, rate=None):
    cmd = ["node", LOADGEN, "--base", f"http://127.0.0.1:{PORT}", "--path", path, "--mode", mode, "--seconds", str(SECONDS), "--warmup", str(WARMUP)]
    cmd += ["--clients", str(clients)] if mode == "closed" else ["--rate", str(rate)]
    smp = None

    def later():
        time.sleep(WARMUP)
        nonlocal smp
        smp = Echantillon(PORT).start()
    th = threading.Thread(target=later); th.start()
    res = sh(cmd, timeout=120)
    th.join()
    s = smp.end() if smp else None
    out = json.loads(res.stdout.strip().splitlines()[-1])
    out["machine"] = s
    return out


def synth(runs, keys):
    return {k: med([r[k] for r in runs if r.get(k) is not None]) for k in keys}


T0 = time.time()
# ============================================================================= A. SQL : index
print("== A. pgbench : sans index / avec index composé")
put("/tmp/a9_hist.sql", HIST); put("/tmp/a9_report.sql", REPORT)
idx(False)
A = {}
for lvl in LEVELS:
    A[lvl] = {"sans_index": [], "avec_index": []}
    for rep in range(REPEATS):
        for var in (("sans_index", "avec_index") if rep % 2 == 0 else ("avec_index", "sans_index")):
            idx(var == "avec_index")
            A[lvl][var].append(run_pgbench("/tmp/a9_hist.sql", lvl))
    for var in A[lvl]:
        A[lvl][var] = {"essais": A[lvl][var], "mediane": synth(A[lvl][var], ("tps", "mediane_ms", "p95_ms", "p99_ms"))}
    print(lvl, {v: A[lvl][v]["mediane"] for v in A[lvl]})
idx(False)
R["A_sql_index"] = A; save("p2_charge.json", R)

# ============================================================================= B. HTTP : N+1 / groupé
print("== B. HTTP : N+1 / groupé")
api = start_api(5)
B = {}
try:
    for lvl in LEVELS:
        B[lvl] = {"n1": [], "groupe": []}
        for rep in range(REPEATS):
            for var in (("n1", "groupe") if rep % 2 == 0 else ("groupe", "n1")):
                B[lvl][var].append(loadgen(f"/commandes?limit=20&relations={var}", "closed", lvl))
        for var in B[lvl]:
            B[lvl][var] = {"essais": B[lvl][var], "mediane": synth(B[lvl][var], ("debit_termine", "mediane_ms", "p95_ms", "p99_ms", "erreurs"))}
        print(lvl, {v: B[lvl][v]["mediane"] for v in B[lvl]})
    R["B_http_n1_groupe"] = B; save("p2_charge.json", R)
finally:
    stop_api(api)

# ============================================================================= C. pool de l'API
print("== C. taille du pool de l'API (N+1, 20 clients)")
C = {}
for pm in (5, 10, 20):
    api = start_api(pm)
    try:
        runs = [loadgen("/commandes?limit=20&relations=n1", "closed", 20) for _ in range(2)]
    finally:
        stop_api(api)
    C[pm] = {"essais": runs, "mediane": synth(runs, ("debit_termine", "mediane_ms", "p95_ms", "p99_ms", "erreurs"))}
    C[pm]["pool_attente_max"] = max(r["machine"]["pool_attente_max"] or 0 for r in runs); C[pm]["pg_actives_max"] = max(r["machine"]["pg_actives_max"] or 0 for r in runs)
    print(pm, C[pm]["mediane"], C[pm]["pool_attente_max"], C[pm]["pg_actives_max"])
R["C_pool_api"] = C; save("p2_charge.json", R)

# ============================================================================= D. charge fermée / ouverte
print("== D. charge fermée / ouverte (N+1)")
cap = B[20]["n1"]["mediane"]["debit_termine"]
api = start_api(5)
D = {"capacite_fermee_20_clients_req_s": cap, "fermee": B[20]["n1"]["mediane"], "ouvertes": []}
try:
    for frac in (0.5, 0.9, 1.3):
        rate = max(1, int(round(cap * frac)))
        runs = [loadgen("/commandes?limit=20&relations=n1", "open", rate=rate) for _ in range(2)]
        D["ouvertes"].append({"fraction_capacite": frac, "cadence_req_s": rate, "essais": runs,
                              "mediane": synth(runs, ("debit_termine", "mediane_ms", "p95_ms", "p99_ms", "erreurs", "non_terminees", "retard_envoi_p95_ms"))})
        print(frac, rate, D["ouvertes"][-1]["mediane"])
finally:
    stop_api(api)
R["D_fermee_ouverte"] = D; save("p2_charge.json", R)

# ============================================================================= E. OLTP contre rapport
print("== E. OLTP contre rapport (même instance)")
idx(True)
E = {"seul": [], "avec_rapports": []}
for rep in range(REPEATS):
    for var in (("seul", "avec_rapports") if rep % 2 == 0 else ("avec_rapports", "seul")):
        sh(pgbench("/tmp/a9_hist.sql", 10, WARMUP, warm=True)[0])
        rep_proc = None
        if var == "avec_rapports":
            rcmd, _ = pgbench("/tmp/a9_report.sql", 2, SECONDS + 4, warm=True)
            rep_proc = subprocess.Popen(rcmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            time.sleep(1.0)
        res = run_pgbench("/tmp/a9_hist.sql", 10, warmup=0)
        if rep_proc:
            out = rep_proc.communicate()[0]
            m = re.search(r"number of transactions actually processed: (\d+)", out)
            res["rapports_termines"] = int(m.group(1)) if m else None
        E[var].append(res)
idx(False)
for var in E:
    E[var] = {"essais": E[var], "mediane": synth(E[var], ("tps", "mediane_ms", "p95_ms", "p99_ms"))}
R["E_oltp_rapport"] = E
print({v: E[v]["mediane"] for v in E})
R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S"); R["duree_totale_min"] = round((time.time() - T0) / 60, 1)
save("p2_charge.json", R)
print("TERMINE", R["duree_totale_min"], "min")
