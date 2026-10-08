#!/usr/bin/env python3
"""Jour 5, partie 1 : observer et diagnostiquer (slides 4 à 17), sur la copie jetable a9-pg.

  1. pg_stat_statements : temps cumulé contre temps unitaire (slides 6-7), avec la charge réelle de l'API (N+1 et groupé) ;
  2. journal des requêtes lentes (slide 9) : le N+1 y est absent, alors qu'il domine le temps cumulé ;
  3. pg_stat_activity : requête de la slide 8 pendant une attente de verrou ;
  4. work_mem : requête de la slide 13 et agrégation mensuelle, 4 MB contre 32 MB (slides 11 et 13) ;
  5. effective_cache_size : un plan change-t-il ? (slide 14) ;
  6. VACUUM et transaction longue (slides 16-17) ;
  7. connexions : budget (slide 15).
Usage : python3 atelier9/p1_diagnostics.py   (conteneur a9-pg démarré ; environ 2 minutes)
"""
import http.client
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

API = os.path.join(ROOT, "01_server", "api")
R = {"debut": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": machine(), "version": q("SELECT version()")}
Q2 = "SELECT date_trunc('month', created_at) AS mois, statut, count(*) AS nb_commandes, sum(total) AS chiffre_affaires FROM shopflow.commandes GROUP BY mois, statut ORDER BY mois, statut"
EXPORT = ("SELECT (created_at AT TIME ZONE 'UTC')::date AS jour, count(*) AS nb_commandes, sum(total) AS montant FROM shopflow.commandes "
          "WHERE statut = 'payee' GROUP BY 1 ORDER BY 1")


def step(t):
    print("\n==", t)


# ------------------------------------------------------------------------- 1. pg_stat_statements
step("1. pg_stat_statements : charge de l'API (N+1 puis groupé) + deux requêtes de rapport")
q("CREATE EXTENSION IF NOT EXISTS pg_stat_statements")
R["pgss_preload"] = q("SHOW shared_preload_libraries")
q("SELECT pg_stat_statements_reset()")
env = dict(os.environ, DATABASE_URL="postgresql://cours:cours-local@127.0.0.1:55433/shopflow", PORT="3001", POOL_MAX="5")
logf = open(os.path.join(OUT, "p1_api_journal.log"), "w")
api = subprocess.Popen(["node", "--env-file=.env", "server.mjs"], cwd=API, stdout=logf, stderr=subprocess.STDOUT, env=env)
try:
    for _ in range(60):
        try:
            urllib.request.urlopen("http://127.0.0.1:3001/", timeout=1)
        except urllib.error.HTTPError:
            break
        except Exception:
            time.sleep(0.25)
    token = [l.strip().split("=", 1)[1] for l in open(os.path.join(API, ".env")) if l.startswith("LAB_TOKEN=")][0]
    conn = http.client.HTTPConnection("127.0.0.1", 3001)

    def get(path):
        conn.request("GET", path, headers={"Authorization": f"Bearer {token}"})
        r = conn.getresponse(); r.read()
        assert r.status == 200
    t0 = time.time()
    for _ in range(1000):
        get("/commandes?limit=20&relations=n1")
    for _ in range(200):
        get("/commandes?limit=20&relations=groupe")
    R["pgss_duree_charge_api_s"] = round(time.time() - t0, 1)
finally:
    api.terminate()
    try:
        api.wait(timeout=10)
    except Exception:
        api.kill()
    logf.close()
for _ in range(10):
    q(Q2)
for _ in range(10):
    q(EXPORT)
rows = q("SELECT left(regexp_replace(query, '\\s+', ' ', 'g'), 78), calls, round(total_exec_time::numeric,1), round(mean_exec_time::numeric,3), rows "
         "FROM pg_stat_statements WHERE query ILIKE '%shopflow.%' OR query ILIKE '%commandes%' OR query ILIKE '%lignes%' ORDER BY total_exec_time DESC LIMIT 10",
         flags=("-At", "-F", "\t")).splitlines()
R["pgss_top"] = [dict(zip(("requete", "appels", "total_ms", "moyenne_ms", "lignes"), l.split("\t"))) for l in rows]
R["pgss_requete_slide"] = ("SELECT query, calls, round(total_exec_time::numeric, 1) AS total_ms, round(mean_exec_time::numeric, 1) AS moyenne_ms "
                           "FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;")
R["pgss_tri_moyenne"] = q("SELECT left(regexp_replace(query, '\\s+', ' ', 'g'), 60)||' | '||round(mean_exec_time::numeric,2) FROM pg_stat_statements "
                          "WHERE query ILIKE '%commandes%' OR query ILIKE '%lignes%' ORDER BY mean_exec_time DESC LIMIT 3").splitlines()
for l in R["pgss_top"][:5]:
    print(l)

# ------------------------------------------------------------------------- 2. journal des requêtes lentes
step("2. Journal des requêtes lentes (log_min_duration_statement = 20 ms sur la copie)")
R["log_min_duration_lab"] = q("SHOW log_min_duration_statement", container=LAB)
R["log_min_duration_copie"] = q("SHOW log_min_duration_statement")
R["log_destination"] = q("SHOW log_destination")
R["logging_collector"] = q("SHOW logging_collector")
R["pg_current_logfile"] = q("SELECT coalesce(pg_current_logfile()::text, 'NULL')")
logs = subprocess.run(["docker", "logs", COPIE], capture_output=True, text=True).stderr.splitlines()
dur = [l for l in logs if "duration:" in l]
R["slow_log_lignes_total"] = len(dur)
R["slow_log_extraits"] = [re.sub(r"\s+", " ", l)[:150] for l in dur[:4]]
R["slow_log_contient_ligne_n1"] = any("FROM shopflow.lignes" in l or "lignes WHERE" in l for l in dur)
print(len(dur), "lignes duration: ; contient le N+1 :", R["slow_log_contient_ligne_n1"])

# ------------------------------------------------------------------------- 3. pg_stat_activity
step("3. pg_stat_activity pendant une attente de verrou (requête de la slide 8)")
A, B, C = Sess("A"), Sess("B"), Sess("C")
A.send("BEGIN;"); A.send("SELECT id FROM shopflow.clients LIMIT 1;")
B.send("SET lock_timeout='8s';")
box = {}
th = threading.Thread(target=lambda: box.setdefault("b", B.send("ALTER TABLE shopflow.clients ADD COLUMN a9_test int;")))
th.start(); time.sleep(1.5)
R["activity_requete_slide"] = ("SELECT pid, state, wait_event_type, wait_event, pg_blocking_pids(pid) bloqueurs FROM pg_stat_activity "
                              "WHERE datname = current_database() AND pid <> pg_backend_pid();")
act = C.send("SELECT pid, state, wait_event_type, wait_event, pg_blocking_pids(pid) AS bloqueurs, application_name FROM pg_stat_activity "
             "WHERE datname = current_database() AND pid <> pg_backend_pid() AND application_name IN ('A','B') ORDER BY application_name;")
R["activity_sortie"] = act
A.send("COMMIT;"); th.join()
B.send("ALTER TABLE shopflow.clients DROP COLUMN IF EXISTS a9_test;")
for s in (A, B, C):
    s.close()
print(act)

# ------------------------------------------------------------------------- 4. work_mem
step("4. work_mem : 4 MB contre 32 MB (SET LOCAL dans une transaction annulée)")


def explain_wm(sql, wm, n=5):
    runs = []
    for _ in range(n):
        out = q(f"BEGIN; SET LOCAL work_mem = '{wm}'; EXPLAIN (ANALYZE, BUFFERS) {sql}; ROLLBACK;", flags=("-At",))
        ms = float(re.search(r"Execution Time: ([\d.]+) ms", out).group(1))
        m = re.search(r"Sort Method: (.+?)\s+(Disk|Memory): (\d+)kB", out)
        hb = re.search(r"Batches: (\d+)\s+Memory Usage: (\d+)kB(?:\s+Disk Usage: (\d+)kB)?", out)
        tmp = re.search(r"temp read=(\d+) written=(\d+)", out)
        runs.append({"ms": ms, "tri": (m.group(1) + " " + m.group(2) + " " + m.group(3) + " kB") if m else None,
                     "hash": (f"Batches {hb.group(1)}, mémoire {hb.group(2)} kB" + (f", disque {hb.group(3)} kB" if hb.group(3) else "")) if hb else None,
                     "temp_ecrit_pages": int(tmp.group(2)) if tmp else 0, "plan": out})
    ms = [r["ms"] for r in runs]
    return {"work_mem": wm, "mediane_ms": med(ms), "min_ms": min(ms), "ms": ms, "tri": runs[-1]["tri"], "hash": runs[-1]["hash"], "temp_ecrit_pages": runs[-1]["temp_ecrit_pages"], "plan": runs[-1]["plan"]}


slide13 = "SELECT client_id, SUM(total) FROM shopflow.commandes GROUP BY client_id ORDER BY SUM(total) DESC"
R["work_mem_slide13"] = {wm: explain_wm(slide13, wm) for wm in ("4MB", "32MB")}
R["work_mem_q2"] = {wm: explain_wm(Q2, wm) for wm in ("4MB", "32MB")}
for k in ("work_mem_slide13", "work_mem_q2"):
    for wm, d in R[k].items():
        print(k, wm, d["mediane_ms"], d["tri"], d["hash"], d["temp_ecrit_pages"])
R["work_mem_budget"] = {"work_mem_mb": 32, "operations_par_requete_q2": len(re.findall(r"(Sort|HashAggregate|GroupAggregate)", R["work_mem_q2"]["32MB"]["plan"])),
                        "max_connections": int(q("SHOW max_connections"))}

# ------------------------------------------------------------------------- 5. effective_cache_size
step("5. effective_cache_size : un plan change-t-il ?")
flips = []
for k in (20, 50, 100, 150, 200, 300, 500, 800):
    row = {"client_id <=": k}
    for ecs in ("1MB", "128MB", "4GB", "16GB"):
        out = q(f"SET effective_cache_size = '{ecs}'; EXPLAIN SELECT id FROM shopflow.commandes WHERE client_id BETWEEN 1 AND {k}", flags=("-At",))
        node = re.search(r"(Index Only Scan|Index Scan|Bitmap Heap Scan|Seq Scan)", out)
        row[ecs] = node.group(1) if node else "?"
    flips.append(row)
R["effective_cache_size_plans"] = flips
R["effective_cache_size_change"] = any(len({r[e] for e in ("1MB", "128MB", "4GB", "16GB")}) > 1 for r in flips)
R["shared_buffers"] = q("SHOW shared_buffers"); R["effective_cache_size"] = q("SHOW effective_cache_size")
print(flips[:3], "changement :", R["effective_cache_size_change"])

# ------------------------------------------------------------------------- 6. VACUUM et transaction longue
step("6. VACUUM et transaction longue")
M, L = Sess("M"), Sess("L")
M.send("DROP TABLE IF EXISTS shopflow.a9_dead;")
M.send("CREATE TABLE shopflow.a9_dead (id int PRIMARY KEY, v int) WITH (autovacuum_enabled = false);")
M.send("INSERT INTO shopflow.a9_dead SELECT g, 0 FROM generate_series(1,200000) g;")
size0 = int(q("SELECT pg_relation_size('shopflow.a9_dead')"))
L.send("BEGIN ISOLATION LEVEL REPEATABLE READ;"); L.send("SELECT count(*) FROM shopflow.a9_dead;")
M.send("UPDATE shopflow.a9_dead SET v = v + 1;")
size1 = int(q("SELECT pg_relation_size('shopflow.a9_dead')"))
time.sleep(1.5)
statsA = q("SELECT n_live_tup||' / '||n_dead_tup FROM pg_stat_user_tables WHERE relname='a9_dead'")
tx = q("SELECT state||' depuis '||round(extract(epoch FROM now()-xact_start)::numeric,1)||' s' FROM pg_stat_activity WHERE application_name='L'")
v1 = M.send("VACUUM (VERBOSE) shopflow.a9_dead;")
L.send("COMMIT;")
v2 = M.send("VACUUM (VERBOSE) shopflow.a9_dead;")
size2 = int(q("SELECT pg_relation_size('shopflow.a9_dead')"))
tup = lambda t: (re.search(r"tuples: (\d+) removed, (\d+) remain, (\d+) are dead but not yet removable", t) or [None])
m1 = re.search(r"tuples: (\d+) removed, (\d+) remain, (\d+) are dead but not yet removable", v1)
m2 = re.search(r"tuples: (\d+) removed, (\d+) remain, (\d+) are dead but not yet removable", v2)
R["vacuum"] = {"taille_initiale_octets": size0, "taille_apres_update_octets": size1, "taille_apres_vacuum_octets": size2,
               "n_live_n_dead_apres_update": statsA, "transaction_longue": tx,
               "vacuum_pendant_transaction": {"supprimees": int(m1.group(1)), "restantes": int(m1.group(2)), "mortes_non_supprimables": int(m1.group(3))} if m1 else None,
               "vacuum_apres_commit": {"supprimees": int(m2.group(1)), "restantes": int(m2.group(2)), "mortes_non_supprimables": int(m2.group(3))} if m2 else None,
               "sortie_vacuum_1": [l for l in v1.splitlines() if "tuples" in l or "vacuuming" in l][:4],
               "sortie_vacuum_2": [l for l in v2.splitlines() if "tuples" in l or "vacuuming" in l][:4]}
M.send("DROP TABLE shopflow.a9_dead;")
for s in (M, L):
    s.close()
R["autovacuum_lab"] = q("SHOW autovacuum", container=LAB); R["track_counts_lab"] = q("SHOW track_counts", container=LAB)
R["autovacuum_tables_lab"] = q("SELECT relname||' : dernier autovacuum '||coalesce(to_char(last_autovacuum,'DD/MM HH24:MI'),'jamais')||', dernier analyze auto '||coalesce(to_char(last_autoanalyze,'DD/MM HH24:MI'),'jamais')||', mortes '||n_dead_tup "
                               "FROM pg_stat_user_tables WHERE schemaname='shopflow' ORDER BY relname", container=LAB).splitlines()
print(json.dumps(R["vacuum"], ensure_ascii=False, indent=1)[:900])

# ------------------------------------------------------------------------- 7. connexions
step("7. Connexions")
R["connexions_lab"] = q("SELECT state||' '||count(*) FROM pg_stat_activity WHERE datname='shopflow' GROUP BY state", container=LAB).splitlines()
R["superuser_reserved"] = q("SHOW superuser_reserved_connections")
R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
save("p1_diagnostics.json", R)
print("OK")
