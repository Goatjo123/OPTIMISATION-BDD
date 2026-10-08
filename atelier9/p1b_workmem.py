#!/usr/bin/env python3
"""Jour 5, slides 11 et 13 : work_mem 4 MB contre 32 MB, mesures ALTERNÉES (9 tours), et surcoût de pg_stat_statements (laboratoire sans / copie avec).
SET LOCAL dans une transaction annulée (aucune modification). Usage : python3 atelier9/p1b_workmem.py (environ 1 minute)."""
import os, re, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

SLIDE13 = "SELECT client_id, SUM(total) FROM shopflow.commandes GROUP BY client_id ORDER BY SUM(total) DESC"
Q2 = "SELECT date_trunc('month', created_at) AS mois, statut, count(*) AS nb_commandes, sum(total) AS chiffre_affaires FROM shopflow.commandes GROUP BY mois, statut ORDER BY mois, statut"


def run(sql, wm, container):
    out = q(f"BEGIN; SET LOCAL work_mem = '{wm}'; EXPLAIN (ANALYZE, BUFFERS) {sql}; ROLLBACK;", container=container)
    ms = float(re.search(r"Execution Time: ([\d.]+) ms", out).group(1))
    m = re.search(r"Sort Method: (.+?)\s+(Disk|Memory): (\d+)kB", out)
    tmp = re.search(r"temp read=(\d+) written=(\d+)", out)
    return ms, (f"{m.group(1)} {m.group(2)} {m.group(3)} kB" if m else None), int(tmp.group(2)) if tmp else 0


R = {"debut": time.strftime("%Y-%m-%d %H:%M:%S"), "machine": machine(), "tours": 9}
for nom, sql in (("slide13", SLIDE13), ("q2", Q2)):
    res = {"4MB": [], "32MB": []}; info = {}
    for i in range(3):  # échauffement
        run(sql, "4MB", COPIE); run(sql, "32MB", COPIE)
    for i in range(9):
        for wm in (("4MB", "32MB") if i % 2 == 0 else ("32MB", "4MB")):
            ms, tri, tmp = run(sql, wm, COPIE)
            res[wm].append(ms); info[wm] = (tri, tmp)
    R[nom] = {wm: {"ms": v, "mediane": med(v), "min": min(v), "p95": pct(v, 95), "tri": info[wm][0], "temp_ecrit_pages": info[wm][1]} for wm, v in res.items()}
    print(nom, {wm: (R[nom][wm]["mediane"], R[nom][wm]["tri"], R[nom][wm]["temp_ecrit_pages"]) for wm in R[nom]})
# surcoût de pg_stat_statements : Q2 à 4 MB sur le laboratoire (sans l'extension) et sur la copie (avec), alternés
sans, avec = [], []
for i in range(3):
    run(Q2, "4MB", LAB); run(Q2, "4MB", COPIE)
for i in range(9):
    for c, store in ((LAB, sans), (COPIE, avec)) if i % 2 == 0 else ((COPIE, avec), (LAB, sans)):
        store.append(run(Q2, "4MB", c)[0])
R["pgss_surcout_q2"] = {"sans_extension_lab": {"mediane": med(sans), "ms": sans}, "avec_extension_copie": {"mediane": med(avec), "ms": avec},
                        "rapport": round(med(avec) / med(sans), 3), "preload_lab": q("SHOW shared_preload_libraries", container=LAB) or "(vide)"}
print(R["pgss_surcout_q2"]["sans_extension_lab"]["mediane"], R["pgss_surcout_q2"]["avec_extension_copie"]["mediane"])
R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
save("p1b_workmem.json", R)
