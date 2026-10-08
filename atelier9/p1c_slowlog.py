#!/usr/bin/env python3
"""Jour 5, slide 9 : relit le journal du conteneur a9-pg (déjà produit par p1_diagnostics.py) et classe les lignes « duration: » par type de requête.
Met à jour p1_diagnostics.json (slow_log_*). Usage : python3 atelier9/p1c_slowlog.py"""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa
logs = subprocess.run(["docker", "logs", COPIE], capture_output=True, text=True).stderr.splitlines()
import json as _j
_d0 = _j.load(open(os.path.join(OUT, "p1_diagnostics.json")))
# fenêtre de p1_diagnostics.py : l'horodatage du journal est en UTC, celui de p1 en heure locale (UTC+2, CEST)
import datetime as _dt
_t0 = (_dt.datetime.strptime(_d0["debut"], "%Y-%m-%d %H:%M:%S") - _dt.timedelta(hours=2, minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
_t1 = (_dt.datetime.strptime(_d0["fin"], "%Y-%m-%d %H:%M:%S") - _dt.timedelta(hours=2) + _dt.timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
dur = [re.sub(r"\s+", " ", l) for l in logs if "duration:" in l and _t0 <= l[:19] <= _t1]
d_all = [l for l in logs if "duration:" in l]
def kind(l):
    if "date_trunc" in l:
        return "agrégation mensuelle"
    if "AT TIME ZONE" in l and "GROUP BY 1" in l and "payee" in l:
        return "export journalier"
    if "FROM shopflow.lignes" in l or "lignes WHERE" in l:
        return "lignes (N+1 ou groupé)"
    if "FROM shopflow.commandes WHERE client_id" in l:
        return "page de commandes"
    return "autre (contrôles de préparation)"
types = {}
for l in dur:
    types[kind(l)] = types.get(kind(l), 0) + 1
d = json.load(open(os.path.join(OUT, "p1_diagnostics.json")))
d["slow_log_fenetre_utc"] = [_t0, _t1]
d["slow_log_par_type"] = types
d["slow_log_total_journal_complet"] = len(d_all)
d["slow_log_lignes_n1_journal_complet"] = sum(1 for l in d_all if "FROM shopflow.lignes" in l or "lignes WHERE" in l)
d["slow_log_lignes_total"] = len(dur)
d["slow_log_contient_ligne_n1"] = types.get("lignes (N+1 ou groupé)", 0) > 0
ex = [l for l in dur if kind(l) == "agrégation mensuelle"][:1] + [l for l in dur if kind(l) == "export journalier"][:1]
d["slow_log_extraits"] = [re.sub(r"^(\S+ \S+) UTC \[(\d+)\] LOG: ", r"\1 [\2] ", l)[:170] for l in ex]
save("p1_diagnostics.json", d)
print(types, d["slow_log_extraits"])
