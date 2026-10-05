#!/usr/bin/env python3
"""Atelier 3 : l'historique client (Jour 2, slide 12).

Compare quatre états de la base pour la requête d'historique :
  initiale / index simple / index composé / index couvrant (+ une variante INCLUDE (total)).

Phases
  1. LECTURE (protocole du cours) : vraie table du laboratoire, 5 clients, 3 échauffements puis 5 mesures
     EXPLAIN (ANALYZE, BUFFERS), médiane. Les variantes sont créées puis SUPPRIMÉES l'une après l'autre :
     deux variantes ne coexistent jamais dans un plan.
  2. MESURE RENFORCÉE : les temps sub-milliseconde sont bruités, donc on mesure aussi en alternance
     (un tour de chaque variante, 51 tours) sur des tables de travail identiques, une par variante.
     Ce sont les mêmes lignes, chaque table n'a que ses propres index.
  3. ÉCRITURE : lot de 20 000 insertions dans une transaction annulée (ROLLBACK), 15 tours en alternance,
     avec le volume de WAL (déterministe, contrairement au temps).
  4. VISIBILITÉ : INCLUDE ne garantit pas zéro Heap Fetches (slide 9), sur une table jetable séparée.
  5. CLIENT TRÈS ACTIF : un client porté à 20 100 commandes (slide 6 : cas défavorable).

La base du laboratoire est vérifiée avant et après : elle doit retrouver exactement son état initial.
Les tables de travail vivent dans le schéma a3_tmp, supprimé à la fin.

Requêtes mesurées (slide 13 : « tester avec le SQL réellement émis par l'application ») :
  slide   : la requête du cours (id, created_at, total, LIMIT 20)
  api     : la requête exacte de 01_server/api/commandes.mjs, première page (id, created_at, statut, total, LIMIT 21)
  api_alias : la même SANS le qualificatif commandes. dans ORDER BY (piège d'alias, client 42 seulement)
  curseur : la même, page suivante par curseur  AND (created_at, id) < (date, id)

Usage : python3 atelier3/benchmark.py     (conteneur Docker api-postgres-1 démarré)
"""
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys

CONT, DB, USER = "api-postgres-1", "shopflow", "cours"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "resultats")
PLANS = os.path.join(OUT, "plans")
os.makedirs(PLANS, exist_ok=True)

REAL = "shopflow.commandes"
CLIENTS = [1, 42, 250, 500, 1000]  # 1 000 clients, tous à 100 commandes dans le jeu fourni
HOT_CLIENT = 7
N_WARM, N_RUNS = 3, 5              # protocole du cours
N_ROUNDS_READ, N_ROUNDS_WRITE = 51, 15

VARIANTS = {  # nom -> (instruction de création de l'index, nom de l'index)
    "initiale": (None, None),
    "simple": ("CREATE INDEX a3_idx_simple ON {t} (client_id)", "a3_idx_simple"),
    "compose": ("CREATE INDEX a3_idx_compose ON {t} (client_id, created_at DESC, id DESC)", "a3_idx_compose"),
    "couvrant": ("CREATE INDEX a3_idx_couvrant ON {t} (client_id, created_at DESC, id DESC) "
                 "INCLUDE (statut, total)", "a3_idx_couvrant"),
    "couvrant_total": ("CREATE INDEX a3_idx_couvrant_total ON {t} (client_id, created_at DESC, id DESC) "
                       "INCLUDE (total)", "a3_idx_couvrant_total"),
}


def psql(statements, db=DB):
    """Exécute des instructions dans UNE session psql ; renvoie la sortie brute."""
    cmd = ["docker", "exec", "-i", CONT, "psql", "-U", USER, "-d", db, "-X", "-A", "-t", "-q",
           "-v", "ON_ERROR_STOP=1"]
    for s in statements:
        cmd += ["-c", s]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql a échoué : {r.stderr}\nSQL : {statements}")
    return r.stdout


API_FIELDS = ("id::text AS id, to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD\"T\"HH24:MI:SS.US\"Z\"') "
              "AS created_at, statut, total::text AS total")


def q1(table, client):
    return (f"SELECT id, created_at, total FROM {table} WHERE client_id = {client} "
            f"ORDER BY created_at DESC, id DESC LIMIT 20")


def queries(table, client, names=("slide", "api", "curseur")):
    """Les requêtes mesurées pour (table, client). Le curseur est la 20e ligne de la première page.

    L'API écrit `FROM shopflow.commandes` et `ORDER BY commandes.created_at DESC, commandes.id DESC` :
    le qualificatif est indispensable, car les colonnes de sortie s'appellent aussi `id` et `created_at`
    (ce sont des textes formatés). Sans qualificatif, ORDER BY trierait sur ces alias texte (variante
    `api_alias`, mesurée à part pour montrer l'effet). `AS commandes` rend la requête identique sur les
    tables de travail, qui portent d'autres noms.
    """
    out = {}
    order_ok = "ORDER BY commandes.created_at DESC, commandes.id DESC LIMIT 21"
    order_alias = "ORDER BY created_at DESC, id DESC LIMIT 21"
    base = f"SELECT {API_FIELDS} FROM {table} AS commandes WHERE client_id = {client}"
    if "slide" in names:
        out["slide"] = q1(table, client)
    if "api" in names:
        out["api"] = f"{base} {order_ok}"
    if "api_alias" in names:
        out["api_alias"] = f"{base} {order_alias}"
    if "curseur" in names:
        row = psql([f"SELECT created_at, id FROM {table} WHERE client_id = {client} "
                    f"ORDER BY created_at DESC, id DESC OFFSET 19 LIMIT 1"]).strip()
        date, ident = row.split("|")
        out["curseur"] = (f"{base} AND (created_at, id) < ('{date}'::timestamptz, {ident}::bigint) {order_ok}")
    return out


def p95(values):
    """Convention : rang le plus proche (nearest-rank), ceil(0,95 n)-ième valeur triée."""
    v = sorted(values)
    return v[math.ceil(0.95 * len(v)) - 1]


def parse_plan(text):
    t = re.search(r"Execution Time: ([\d.]+) ms", text)
    nodes = re.findall(r"(Index Only Scan|Index Scan|Bitmap Heap Scan|Bitmap Index Scan|Seq Scan|Sort)", text)
    using = re.findall(r"(?:Index Only Scan|Index Scan)(?: Backward)? using (\S+)", text)
    using += re.findall(r"Bitmap Index Scan on (\S+)", text)
    buf = re.search(r"Buffers: shared hit=(\d+)(?: read=(\d+))?", text)
    hf = re.search(r"Heap Fetches: (\d+)", text)
    return {"ms": float(t.group(1)), "noeuds": nodes, "index_utilises": using,
            "buffers_hit": int(buf.group(1)), "buffers_read": int(buf.group(2) or 0),
            "heap_fetches": int(hf.group(1)) if hf else None, "tri": "Sort" in nodes}


def measure(label, sql, client, reference_md5=None):
    """Protocole du cours : 3 échauffements, 5 mesures, médiane, empreinte du résultat."""
    for _ in range(N_WARM):
        psql([sql])
    res = psql([sql])
    md5 = hashlib.md5(res.encode()).hexdigest()[:12]
    nrows = len([l for l in res.splitlines() if l.strip()])
    runs, last = [], None
    for _ in range(N_RUNS):
        last = psql([f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
        runs.append(parse_plan(last))
    with open(os.path.join(PLANS, f"{label}_client{client}.txt"), "w") as f:
        f.write(f"-- {sql}\n{last}")
    ms = [r["ms"] for r in runs]
    p = runs[-1]
    return {"label": label, "client": client, "lignes": nrows, "md5": md5,
            "identique_a_la_reference": (md5 == reference_md5) if reference_md5 else None,
            "ms": ms, "mediane_ms": statistics.median(ms),
            "noeuds": p["noeuds"], "index_utilises": p["index_utilises"],
            "buffers_hit": p["buffers_hit"], "buffers_read": p["buffers_read"],
            "heap_fetches": p["heap_fetches"], "tri": p["tri"],
            "plan_identique_5_fois": len({(tuple(r["noeuds"]), tuple(r["index_utilises"])) for r in runs}) == 1}


def lab_state():
    idx = psql(["SELECT indexname FROM pg_indexes WHERE schemaname='shopflow' ORDER BY 1"]).split()
    stats = int(psql(["SELECT count(*) FROM pg_statistic_ext"]).strip())
    pages = psql(["SELECT relpages||'/'||relallvisible FROM pg_class "
                  "WHERE oid='shopflow.commandes'::regclass"]).strip()
    return {"index": idx, "statistiques_etendues": stats, "pages_et_visibles": pages}


def index_size(schema, name):
    return int(psql([f"SELECT pg_relation_size('{schema}.{name}')"]).strip())


# ---------------------------------------------------------------- phase 1
def phase_lecture_reelle():
    """results[variante][requête][client]. Les variantes sont créées puis supprimées l'une après l'autre."""
    results, sizes, refs = {}, {}, {}
    sizes["initiale (index unique existant)"] = index_size("shopflow", "commandes_client_id_cle_idempotence_key")
    for var, (ddl, name) in VARIANTS.items():
        if ddl:
            psql([ddl.format(t=REAL)])
            sizes[var] = index_size("shopflow", name)
        results[var] = {}
        for c in CLIENTS:
            for qn, sql in queries(REAL, c).items():
                m = measure(f"reel_{var}_{qn}", sql, c, refs.get((qn, c)))
                if var == "initiale":
                    refs[(qn, c)] = m["md5"]
                    m["identique_a_la_reference"] = True
                results[var].setdefault(qn, {})[c] = m
        if ddl:
            psql([f"DROP INDEX shopflow.{name}"])
    return results, sizes


# ---------------------------------------------------------------- tables de travail
def build_tables():
    """Une table de travail par variante : mêmes lignes que la vraie table, ses propres index."""
    psql(["DROP SCHEMA IF EXISTS a3_tmp CASCADE", "CREATE SCHEMA a3_tmp"])
    sizes = {}
    for var, (ddl, name) in VARIANTS.items():
        t = f"a3_tmp.t_{var}"
        psql([f"CREATE TABLE {t} (LIKE {REAL} INCLUDING ALL)", f"INSERT INTO {t} SELECT * FROM {REAL}"])
        if ddl:
            psql([ddl.format(t=t)])
        psql([f"VACUUM ANALYZE {t}"])
        if ddl:
            sizes[var] = index_size("a3_tmp", name)
    return sizes


def rotate(lst, k):
    k %= len(lst)
    return lst[k:] + lst[:k]


# ---------------------------------------------------------------- phase 2
def phase_mesure_renforcee(client, qnames=("slide", "api")):
    """51 tours en alternance (ordre tournant) : médiane et p95 par variante et par requête."""
    names = list(VARIANTS)
    qs = {v: queries(f"a3_tmp.t_{v}", client, qnames) for v in names}
    ms = {(v, qn): [] for v in names for qn in qnames}
    for v in names:
        for qn in qnames:
            for _ in range(N_WARM):
                psql([qs[v][qn]])
    last = {}
    for r in range(N_ROUNDS_READ):
        for v in rotate(names, r):
            for qn in qnames:
                p = parse_plan(psql([f"EXPLAIN (ANALYZE, BUFFERS) {qs[v][qn]}"]))
                ms[(v, qn)].append(p["ms"])
                last[(v, qn)] = p
    out = {}
    for qn in qnames:
        out[qn] = {}
        for v in names:
            x, p = ms[(v, qn)], last[(v, qn)]
            out[qn][v] = {"mediane_ms": statistics.median(x), "p95_ms": p95(x), "min_ms": min(x), "n": len(x),
                          "buffers_hit": p["buffers_hit"], "noeuds": p["noeuds"],
                          "index_utilises": p["index_utilises"], "heap_fetches": p["heap_fetches"],
                          "md5": hashlib.md5(psql([qs[v][qn]]).encode()).hexdigest()[:12]}
        for v in names:
            out[qn][v]["identique_a_initiale"] = out[qn][v]["md5"] == out[qn]["initiale"]["md5"]
    return out


# ---------------------------------------------------------------- phase 3
def phase_ecriture():
    """Lot de 20 000 insertions annulé (ROLLBACK), 15 tours en alternance, avec le volume de WAL."""
    names = list(VARIANTS)

    def insert(v):
        t = f"a3_tmp.t_{v}"
        return (f"INSERT INTO {t} SELECT id + 1000000, client_id, created_at, statut, total, NULL "
                f"FROM {t} WHERE id <= 20000")

    for v in names:
        psql(["BEGIN", insert(v), "ROLLBACK"])  # échauffement
    runs = {v: [] for v in names}
    for r in range(N_ROUNDS_WRITE):
        for v in rotate(names, r):
            txt = psql(["BEGIN", f"EXPLAIN (ANALYZE, BUFFERS, WAL) {insert(v)}", "ROLLBACK"])
            ms = float(re.search(r"Execution Time: ([\d.]+) ms", txt).group(1))
            wal = re.search(r"WAL: records=(\d+)(?: fpi=(\d+))? bytes=(\d+)", txt)
            runs[v].append({"ms": ms, "wal_records": int(wal.group(1)), "wal_bytes": int(wal.group(3))})
        if r % 5 == 4:  # évite l'accumulation de lignes mortes qui fausserait la fin de la série
            for v in names:
                psql([f"VACUUM a3_tmp.t_{v}"])
    out = {}
    for v in names:
        ms = [x["ms"] for x in runs[v]]
        out[v] = {"mediane_ms": statistics.median(ms), "min_ms": min(ms), "p95_ms": p95(ms), "n": len(ms),
                  "wal_bytes_mediane": int(statistics.median(x["wal_bytes"] for x in runs[v])),
                  "wal_records_mediane": int(statistics.median(x["wal_records"] for x in runs[v])),
                  "nb_index_sur_la_table": int(psql([
                      f"SELECT count(*) FROM pg_indexes WHERE schemaname='a3_tmp' AND tablename='t_{v}'"]).strip())}
    return out


# ---------------------------------------------------------------- phase 4
def phase_visibilite():
    """Slide 9 : INCLUDE ne garantit pas zéro Heap Fetches si la table a été modifiée (table jetable séparée)."""
    t = "a3_tmp.visibilite"
    psql([f"CREATE TABLE {t} (LIKE {REAL} INCLUDING ALL)", f"INSERT INTO {t} SELECT * FROM {REAL}",
          f"CREATE INDEX a3_idx_vis ON {t} (client_id, created_at DESC, id DESC) INCLUDE (statut, total)",
          f"VACUUM ANALYZE {t}"])
    sql = q1(t, 42)

    def plan():
        return parse_plan(psql([f"EXPLAIN (ANALYZE, BUFFERS) {sql}"]))

    a = plan()
    psql([f"UPDATE {t} SET total = total WHERE client_id = 42"])  # réécrit les 100 lignes, sans VACUUM
    b = plan()
    psql([f"VACUUM {t}"])
    c = plan()
    return {"1_apres_vacuum_initial": a, "2_apres_update_sans_vacuum": b, "3_apres_nouveau_vacuum": c}


# ---------------------------------------------------------------- phase 5
def phase_client_actif():
    """Un client porté à 20 100 commandes (cas défavorable de la slide 6), tables fraîches."""
    build_tables()
    sizes = {}
    for v, (ddl, name) in VARIANTS.items():
        t = f"a3_tmp.t_{v}"
        psql([f"INSERT INTO {t} SELECT id + 2000000, {HOT_CLIENT}, created_at, statut, total, NULL "
              f"FROM {t} WHERE id <= 20000", f"VACUUM ANALYZE {t}"])
        if ddl:
            sizes[v] = index_size("a3_tmp", name)  # mesurée APRÈS l'ajout des lignes
    nb = int(psql([f"SELECT count(*) FROM a3_tmp.t_initiale WHERE client_id = {HOT_CLIENT}"]).strip())
    stats = phase_mesure_renforcee(HOT_CLIENT)
    return nb, stats, sizes


def main():
    env = {
        "version": psql(["SELECT version()"]).strip(),
        "work_mem": psql(["SHOW work_mem"]).strip(),
        "shared_buffers": psql(["SHOW shared_buffers"]).strip(),
        "pages_commandes": int(psql(["SELECT relpages FROM pg_class WHERE oid='shopflow.commandes'::regclass"]).strip()),
        "taille_commandes_octets": int(psql(["SELECT pg_relation_size('shopflow.commandes')"]).strip()),
    }
    before = lab_state()
    print("Etat initial du labo :", before)
    assert not any(i.startswith("a3_") for i in before["index"]), "des index a3_ traînent déjà"

    print("== Phase 1 : lecture, vraie table, clients", CLIENTS)
    lecture, tailles = phase_lecture_reelle()

    print("== Tables de travail (une par variante)")
    tailles_tmp = build_tables()
    # contrôle : la table de travail doit se comporter comme la vraie (mêmes pages lues pour la requête initiale)
    ctrl = parse_plan(psql([f"EXPLAIN (ANALYZE, BUFFERS) {q1('a3_tmp.t_initiale', 42)}"]))
    ctrl_reel = lecture["initiale"]["slide"][42]["buffers_hit"]
    print(f"   contrôle client 42, requête initiale : {ctrl['buffers_hit']} buffers (vraie table : {ctrl_reel})")

    print("== Phase 2 : mesure renforcée, client 42,", N_ROUNDS_READ, "tours en alternance")
    renforcee = phase_mesure_renforcee(42, ("slide", "api", "api_alias", "curseur"))
    print("== Phase 3 : écriture,", N_ROUNDS_WRITE, "tours en alternance")
    ecriture = phase_ecriture()
    print("== Phase 4 : visibilité / Heap Fetches")
    visibilite = phase_visibilite()
    print("== Phase 5 : client très actif")
    nb_actif, actif, tailles_actif = phase_client_actif()

    print("== Nettoyage et contrôle de l'état final")
    psql(["DROP SCHEMA a3_tmp CASCADE"])
    after = lab_state()
    restaure = (after["index"] == before["index"]
                and after["statistiques_etendues"] == before["statistiques_etendues"])
    print("Etat final du labo :", after, "| identique :", restaure)

    data = {"env": env, "etat_avant": before, "etat_apres": after, "labo_restaure": restaure,
            "clients": CLIENTS, "lecture_reelle": lecture, "tailles_index_octets": tailles,
            "controle_table_de_travail": {"buffers_table_de_travail": ctrl["buffers_hit"],
                                          "buffers_vraie_table": ctrl_reel},
            "tailles_index_table_de_travail": tailles_tmp,
            "mesure_renforcee_client42": renforcee, "ecriture": ecriture, "visibilite": visibilite,
            "client_actif": {"client": HOT_CLIENT, "commandes": nb_actif, "mesures": actif,
                             "tailles_index_octets": tailles_actif}}
    with open(os.path.join(OUT, "resultats.json"), "w") as f:
        json.dump(data, f, indent=1, default=str)
    print("Résultats écrits dans", os.path.join(OUT, "resultats.json"))
    if not restaure:
        sys.exit("ATTENTION : le labo n'a pas retrouvé son état initial")


if __name__ == "__main__":
    main()
