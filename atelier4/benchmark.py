#!/usr/bin/env python3
"""Atelier 4 : index spécialisés (Jour 2, slide 26).

Trois familles, chacune sur une requête distincte (slide 44 : « chaque hypothèse répond à une requête ») :

  A. INDEX PARTIEL  : la file des commandes `en_attente` (10 % de la table).
  B. GIN            : le filtre JSONB sur `produits.attributs`, sur la vraie table (200 lignes, un Seq Scan peut rester
                      rationnel) puis à plus grand volume (200 000 lignes), comparé à un index d'expression et à une
                      colonne typée (slide 17).
  C. GiST           : les réservations `tstzrange` et l'opérateur de chevauchement `&&` (slide 18).

Protocole (identique à l'atelier 3)
  - vraie table du laboratoire : variantes créées puis SUPPRIMÉES une à une (jamais deux ensemble), 3 échauffements
    puis 5 mesures EXPLAIN (ANALYZE, BUFFERS), médiane, empreinte md5 du résultat, usage de l'index (idx_scan) ;
  - mesure renforcée : une table de travail par variante, 51 tours en alternance (ordre tournant), SANS parallélisme
    (max_parallel_workers_per_gather = 0) : PostgreSQL peut choisir un Parallel Seq Scan sur une table et un Seq Scan
    simple sur une autre de taille voisine, ce qui fausserait la comparaison de plans de même forme ;
  - écriture : lots annulés (ROLLBACK), 15 tours en alternance, avec le volume de WAL ;
  - TOUTES les valeurs brutes de chaque série sont conservées dans resultats.json.

La base du laboratoire est comparée avant et après : elle doit retrouver exactement son état initial.
Les tables de travail vivent dans le schéma a4_tmp, supprimé à la fin.

Usage : python3 atelier4/benchmark.py     (conteneur Docker api-postgres-1 démarré, environ 15 minutes)
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

COMMANDES = "shopflow.commandes"
PRODUITS = "shopflow.produits"
N_WARM, N_RUNS = 3, 5
N_ROUNDS_READ, N_ROUNDS_WRITE = 51, 15
N_GROS = 200_000


# ----------------------------------------------------------------------------- outils
def psql(statements, db=DB):
    """Exécute des instructions dans UNE session psql ; renvoie la sortie brute."""
    cmd = ["docker", "exec", "-i", CONT, "psql", "-U", USER, "-d", db, "-X", "-A", "-t", "-q",
           "-v", "ON_ERROR_STOP=1"]
    for s in statements:
        cmd += ["-c", s]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql a échoué : {r.stderr.strip()}\nSQL : {statements}")
    return r.stdout


def p95(values):
    """Convention : rang le plus proche (nearest-rank), ceil(0,95 n)-ième valeur triée."""
    v = sorted(values)
    return v[math.ceil(0.95 * len(v)) - 1]


def rotate(lst, k):
    k %= len(lst)
    return lst[k:] + lst[:k]


def md5_of(text):
    return hashlib.md5(text.encode()).hexdigest()[:12]


def parse_plan(text):
    t = re.search(r"Execution Time: ([\d.]+) ms", text)
    nodes = re.findall(r"(Index Only Scan|Index Scan|Bitmap Heap Scan|Bitmap Index Scan|Seq Scan|Sort)", text)
    using = re.findall(r"(?:Index Only Scan|Index Scan)(?: Backward)? using (\S+)", text)
    using += re.findall(r"Bitmap Index Scan on (\S+)", text)
    buf = re.search(r"Buffers: shared (?:hit=(\d+))?(?: ?read=(\d+))?", text)
    cost = re.search(r"cost=([\d.]+)\.\.([\d.]+)", text)
    rows = re.search(r"actual time=[\d.]+\.\.[\d.]+ rows=([\d.]+)", text)
    return {"ms": float(t.group(1)) if t else None, "noeuds": nodes, "index_utilises": using,
            "buffers_hit": int(buf.group(1) or 0) if buf else None,
            "buffers_read": int(buf.group(2) or 0) if buf else None,
            "buffers_total": (int(buf.group(1) or 0) + int(buf.group(2) or 0)) if buf else None,
            "cout_estime": float(cost.group(2)) if cost else None,
            "lignes": float(rows.group(1)) if rows else None}


def save_plan(name, sql, text):
    with open(os.path.join(PLANS, f"{name}.txt"), "w") as f:
        f.write(f"-- {sql}\n{text}")


def lab_state():
    idx = psql(["SELECT indexname FROM pg_indexes WHERE schemaname='shopflow' ORDER BY 1"]).split()
    stats = int(psql(["SELECT count(*) FROM pg_statistic_ext"]).strip())
    return {"index": idx, "statistiques_etendues": stats,
            "lignes": {t: int(psql([f"SELECT count(*) FROM shopflow.{t}"]).strip())
                       for t in ("clients", "produits", "commandes", "lignes")}}


def size_of(name, schema):
    return int(psql([f"SELECT pg_relation_size('{schema}.{name}')"]).strip())


def idx_scan(name):
    return int(psql([f"SELECT coalesce(sum(idx_scan),0) FROM pg_stat_user_indexes WHERE indexrelname='{name}'"]).strip())


def measure(label, sql, reference_md5=None, pre=None):
    """Protocole du cours : 3 échauffements, 5 mesures, médiane, empreinte du résultat. Toutes les durées conservées."""
    pre = pre or []
    for _ in range(N_WARM):
        psql(pre + [sql])
    res = psql(pre + [sql])
    md5 = md5_of("\n".join(l for l in res.splitlines() if l not in ("SET",)))
    runs, last = [], None
    for _ in range(N_RUNS):
        last = psql(pre + [f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
        runs.append(parse_plan(last))
    save_plan(label, sql, last)
    ms = [r["ms"] for r in runs]
    p = runs[-1]
    return {"label": label, "lignes_resultat": len([l for l in res.splitlines() if l.strip() and l != "SET"]),
            "md5": md5, "identique_a_la_reference": (md5 == reference_md5) if reference_md5 else None,
            "ms": ms, "mediane_ms": statistics.median(ms), "noeuds": p["noeuds"],
            "index_utilises": p["index_utilises"], "buffers_hit": p["buffers_hit"],
            "buffers_read": p["buffers_read"], "buffers_total": p["buffers_total"],
            "cout_estime": p["cout_estime"],
            "plan_identique_5_fois": len({(tuple(r["noeuds"]), tuple(r["index_utilises"])) for r in runs}) == 1}


NO_PARALLEL = ["SET max_parallel_workers_per_gather = 0"]


def alternate(items, rounds, prefix, warm=N_WARM, keep_plans=True, pre=None):
    """items : {(variante, requête): sql}. `rounds` tours en alternance (ordre tournant des variantes).
    Retourne, par clé, toutes les durées brutes, médiane, p95, minimum, plan et empreinte du résultat."""
    keys = list(items)
    variants = []
    for v, _ in keys:
        if v not in variants:
            variants.append(v)
    pre = pre or []
    ms = {k: [] for k in keys}
    last = {}
    for k in keys:
        for _ in range(warm):
            psql(pre + [items[k]])
    md5 = {k: md5_of("\n".join(l for l in psql(pre + [items[k]]).splitlines() if l != "SET")) for k in keys}
    for r in range(rounds):
        for v in rotate(variants, r):
            for k in [k for k in keys if k[0] == v]:
                txt = psql(pre + [f"EXPLAIN (ANALYZE, BUFFERS) {items[k]}"])
                p = parse_plan(txt)
                ms[k].append(p["ms"])
                last[k] = (p, txt)
    out = {}
    for k in keys:
        p, txt = last[k]
        if keep_plans:
            save_plan(f"{prefix}_{k[0]}_{k[1]}", items[k], txt)
        out[k] = {"ms": ms[k], "mediane_ms": statistics.median(ms[k]), "p95_ms": p95(ms[k]), "min_ms": min(ms[k]),
                  "n": len(ms[k]), "noeuds": p["noeuds"], "index_utilises": p["index_utilises"],
                  "buffers_hit": p["buffers_hit"], "buffers_read": p["buffers_read"],
                  "buffers_total": p["buffers_total"], "lignes": p["lignes"], "md5": md5[k]}
    return out


def tag(res):
    """{(variante, requête): ...} -> {variante: {requête: ...}} pour le JSON."""
    out = {}
    for (v, q), val in res.items():
        out.setdefault(v, {})[q] = val
    return out


def ref_check(res, ref_variant="initiale"):
    """Ajoute l'indicateur « résultat identique à la variante de référence » pour chaque requête."""
    for (v, q), val in res.items():
        val["identique_a_la_reference"] = val["md5"] == res[(ref_variant, q)]["md5"]
    return res


def write_lots(variants, lots, rounds, vacuum_every=5):
    """lots : {nom: fonction(variante) -> instruction SQL}. Chaque lot est exécuté dans BEGIN ... ROLLBACK
    avec EXPLAIN (ANALYZE, BUFFERS, WAL). `variants` : {variante: table}."""
    names = list(variants)
    for v in names:
        for lot, make in lots.items():
            psql(["BEGIN", make(v), "ROLLBACK"])  # échauffement
    runs = {(v, lot): [] for v in names for lot in lots}
    for r in range(rounds):
        for v in rotate(names, r):
            for lot, make in lots.items():
                txt = psql(["BEGIN", f"EXPLAIN (ANALYZE, BUFFERS, WAL) {make(v)}", "ROLLBACK"])
                ms = float(re.search(r"Execution Time: ([\d.]+) ms", txt).group(1))
                wal = re.search(r"WAL: records=(\d+)(?: fpi=(\d+))? bytes=(\d+)", txt)
                runs[(v, lot)].append({"ms": ms, "wal_records": int(wal.group(1)) if wal else 0,
                                       "wal_bytes": int(wal.group(3)) if wal else 0})
        if r % vacuum_every == vacuum_every - 1:
            for v in names:
                psql([f"VACUUM {variants[v]}"])
    out = {}
    for (v, lot), rs in runs.items():
        ms = [x["ms"] for x in rs]
        out.setdefault(v, {})[lot] = {
            "ms": ms, "mediane_ms": statistics.median(ms), "min_ms": min(ms), "p95_ms": p95(ms), "n": len(ms),
            "wal_bytes": [x["wal_bytes"] for x in rs], "wal_records": [x["wal_records"] for x in rs],
            "wal_bytes_mediane": int(statistics.median(x["wal_bytes"] for x in rs)),
            "wal_records_mediane": int(statistics.median(x["wal_records"] for x in rs))}
    return out


# ============================================================================= A. INDEX PARTIEL
STATUTS = ("en_attente", "payee", "annulee")


def q_partiel(table, statut):
    return (f"SELECT id FROM {table} WHERE statut = '{statut}' ORDER BY created_at, id LIMIT 100")


A_VARIANTS = {  # variante -> (DDL, nom de l'index)
    "initiale": (None, None),
    "partiel": ("CREATE INDEX a4_idx_partiel ON {t} (created_at, id) WHERE statut = 'en_attente'", "a4_idx_partiel"),
    "complet": ("CREATE INDEX a4_idx_complet ON {t} (statut, created_at, id)", "a4_idx_complet"),
}


def phase_partiel_reel():
    """Vraie table : variantes créées puis supprimées. 3 requêtes (1 qui correspond au prédicat, 2 qui n'y correspondent pas)."""
    res, sizes, usage, refs = {}, {}, {}, {}
    for var, (ddl, name) in A_VARIANTS.items():
        if ddl:
            psql([ddl.format(t=COMMANDES)])
            sizes[var] = size_of(name, "shopflow")
        res[var] = {}
        for st in STATUTS:
            m = measure(f"partiel_reel_{var}_{st}", q_partiel(COMMANDES, st), refs.get(st))
            if var == "initiale":
                refs[st] = m["md5"]
                m["identique_a_la_reference"] = True
            res[var][st] = m
        if ddl:
            usage[var] = idx_scan(name)
            psql([f"DROP INDEX shopflow.{name}"])
    return res, sizes, usage


def phase_partiel_parametre():
    """Slide 13 : « certains plans génériques paramétrés ne permettent pas cette preuve ». Requête préparée,
    plan générique forcé puis plan spécifique forcé, pour l'index partiel et pour l'index complet."""
    out = {}
    prep = ("PREPARE q_attente(text) AS SELECT id FROM shopflow.commandes WHERE statut = $1 "
            "ORDER BY created_at, id LIMIT 100")
    for var in ("partiel", "complet"):
        ddl, name = A_VARIANTS[var]
        psql([ddl.format(t=COMMANDES)])
        out[var] = {}
        for mode in ("force_generic_plan", "force_custom_plan"):
            txt = psql([f"SET plan_cache_mode = {mode}", prep,
                        "EXPLAIN (ANALYZE, BUFFERS) EXECUTE q_attente('en_attente')"])
            p = parse_plan(txt)
            save_plan(f"partiel_parametre_{var}_{mode}", "EXECUTE q_attente('en_attente') ; " + prep, txt)
            out[var][mode] = {"noeuds": p["noeuds"], "index_utilises": p["index_utilises"],
                              "buffers_total": p["buffers_total"]}
        psql([f"DROP INDEX shopflow.{name}"])
    return out


def phase_predicat_now():
    """Slide 14 : un prédicat avec now() n'est pas un prédicat d'index valide (immuabilité)."""
    try:
        psql(["CREATE INDEX a4_idx_now ON shopflow.commandes (created_at) "
              "WHERE created_at >= now() - interval '7 days'"])
        psql(["DROP INDEX shopflow.a4_idx_now"])
        return {"refuse": False, "message": None}
    except RuntimeError as e:
        m = re.search(r"ERROR:\s*(.+)", str(e))
        return {"refuse": True, "message": m.group(1).strip() if m else str(e)}


def build_commandes_tables():
    psql(["DROP SCHEMA IF EXISTS a4_tmp CASCADE", "CREATE SCHEMA a4_tmp"])
    tables, sizes = {}, {}
    for var, (ddl, name) in A_VARIANTS.items():
        t = f"a4_tmp.t_{var}"
        psql([f"CREATE TABLE {t} (LIKE {COMMANDES} INCLUDING ALL)", f"INSERT INTO {t} SELECT * FROM {COMMANDES}"])
        if ddl:
            psql([ddl.format(t=t)])
        psql([f"VACUUM ANALYZE {t}"])
        tables[var] = t
        if ddl:
            sizes[var] = size_of(name, "a4_tmp")
    return tables, sizes


def phase_partiel_renforce(tables):
    items = {(v, st): q_partiel(t, st) for v, t in tables.items() for st in ("en_attente", "payee")}
    return ref_check(alternate(items, N_ROUNDS_READ, "partiel_renforce", pre=NO_PARALLEL))


def phase_partiel_ecriture(tables):
    """Lot d'insertions (mélange de statuts) et lot de changements de statut (en_attente -> payee), annulés."""
    ref = tables["initiale"]
    compo = {r.split("|")[0]: int(r.split("|")[1]) for r in psql(
        [f"SELECT statut, count(*) FROM {ref} WHERE id <= 20000 GROUP BY 1 ORDER BY 1"]).split()}
    lots = {
        "insertion_20000": lambda v: (f"INSERT INTO {tables[v]} SELECT id + 1000000, client_id, created_at, statut, "
                                      f"total, NULL FROM {tables[v]} WHERE id <= 20000"),
        "statut_en_attente_vers_payee": lambda v: (f"UPDATE {tables[v]} SET statut = 'payee' "
                                                   f"WHERE statut = 'en_attente' AND id <= 20000"),
        "statut_payee_vers_en_attente": lambda v: (f"UPDATE {tables[v]} SET statut = 'en_attente' "
                                                   f"WHERE statut = 'payee' AND id <= 2500"),
    }
    n_maj = int(psql([f"SELECT count(*) FROM {ref} WHERE statut = 'en_attente' AND id <= 20000"]).strip())
    n_maj2 = int(psql([f"SELECT count(*) FROM {ref} WHERE statut = 'payee' AND id <= 2500"]).strip())
    return write_lots(tables, lots, N_ROUNDS_WRITE), {"composition_du_lot": compo,
                                                      "lignes_changees_par_le_lot_en_attente_vers_payee": n_maj,
                                                      "lignes_changees_par_le_lot_payee_vers_en_attente": n_maj2}


# ============================================================================= B. GIN
G_QUERIES_REEL = {
    "contient_livre": "SELECT id, nom FROM {t} WHERE attributs @> '{{\"categorie\":\"livre\"}}'::jsonb ORDER BY id",
    "contient_materiel": "SELECT id, nom FROM {t} WHERE attributs @> '{{\"categorie\":\"materiel\"}}'::jsonb ORDER BY id",
    "contient_absent": "SELECT id, nom FROM {t} WHERE attributs @> '{{\"categorie\":\"inexistant\"}}'::jsonb ORDER BY id",
    "extrait_livre": "SELECT id, nom FROM {t} WHERE attributs->>'categorie' = 'livre' ORDER BY id",
}
G_VARIANTS_REEL = {
    "initiale": (None, None),
    "gin": ("CREATE INDEX a4_idx_gin ON {t} USING gin (attributs)", "a4_idx_gin"),
    "expression": ("CREATE INDEX a4_idx_expr ON {t} ((attributs->>'categorie'))", "a4_idx_expr"),
}


def phase_gin_reel():
    """Vraie table `produits` (200 lignes, 3 pages) : un Seq Scan peut rester rationnel (slide 26)."""
    res, sizes, usage, refs, diag = {}, {}, {}, {}, {}
    for var, (ddl, name) in G_VARIANTS_REEL.items():
        if ddl:
            psql([ddl.format(t=PRODUITS)])
            sizes[var] = size_of(name, "shopflow")
        res[var] = {}
        for qn, tpl in G_QUERIES_REEL.items():
            sql = tpl.format(t=PRODUITS)
            m = measure(f"gin_reel_{var}_{qn}", sql, refs.get(qn))
            if var == "initiale":
                refs[qn] = m["md5"]
                m["identique_a_la_reference"] = True
            res[var][qn] = m
        if ddl:
            usage[var] = idx_scan(name)  # lu AVANT le diagnostic, pour ne compter que le protocole normal
            # Diagnostic (session seulement) : l'index PEUT-IL servir la requête si on interdit le Seq Scan ?
            diag[var] = {}
            for qn, tpl in G_QUERIES_REEL.items():
                sql = tpl.format(t=PRODUITS)
                txt_on = psql([f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
                txt_off = psql(["SET enable_seqscan = off", f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
                pon, poff = parse_plan(txt_on), parse_plan(txt_off)
                save_plan(f"gin_reel_{var}_{qn}_seqscan_interdit", "SET enable_seqscan = off ; " + sql, txt_off)
                diag[var][qn] = {"cout_avec_seqscan": pon["cout_estime"], "noeuds_avec_seqscan": pon["noeuds"],
                                 "cout_sans_seqscan": poff["cout_estime"], "noeuds_sans_seqscan": poff["noeuds"],
                                 "index_utilises_sans_seqscan": poff["index_utilises"]}
            psql([f"DROP INDEX shopflow.{name}"])
    taille_table = size_of("produits", "shopflow")
    return res, sizes, usage, diag, taille_table


def q_gros(table, kind):
    base = f"SELECT count(*), sum(id) FROM {table} WHERE "
    return {"contient_livre": base + "attributs @> '{\"categorie\":\"livre\"}'::jsonb",
            "contient_rare": base + "attributs @> '{\"categorie\":\"rare\"}'::jsonb",
            "extrait_rare": base + "attributs->>'categorie' = 'rare'",
            "colonne_rare": base + "categorie = 'rare'"}[kind]


GROS_VARIANTS = {  # variante -> (colonne typée ?, DDL de l'index, nom)
    "initiale": (False, None, None),
    "gin": (False, "CREATE INDEX a4_idx_gin ON {t} USING gin (attributs)", "a4_idx_gin"),
    "expression": (False, "CREATE INDEX a4_idx_expr ON {t} ((attributs->>'categorie'))", "a4_idx_expr"),
    "colonne_typee": (True, "CREATE INDEX a4_idx_typee ON {t} (categorie)", "a4_idx_typee"),
}


def build_gros_tables():
    """Une table de 200 000 produits par variante : mêmes lignes, même forme d'attributs que `produits`.
    categorie : 50 % materiel, 25 % accessoire, 24,9 % livre, 0,1 % rare (200 lignes)."""
    tables, sizes, table_sizes = {}, {}, {}
    for var, (typed, ddl, name) in GROS_VARIANTS.items():
        t = f"a4_tmp.g_{var}"
        extra = ", categorie text GENERATED ALWAYS AS (attributs->>'categorie') STORED" if typed else ""
        psql([f"CREATE TABLE {t} (id bigint PRIMARY KEY, nom text NOT NULL, prix numeric(12,2) NOT NULL, "
              f"stock integer NOT NULL, attributs jsonb NOT NULL DEFAULT '{{}}'::jsonb{extra})",
              f"INSERT INTO {t} (id, nom, prix, stock, attributs) "
              f"SELECT i, 'Produit ' || i, (i % 500) + 0.99, i % 100, "
              f"jsonb_build_object('couleur', (ARRAY['noir','bleu','rouge'])[1 + i % 3], "
              f"'categorie', CASE WHEN i % 1000 < 500 THEN 'materiel' WHEN i % 1000 < 750 THEN 'accessoire' "
              f"WHEN i % 1000 < 999 THEN 'livre' ELSE 'rare' END) FROM generate_series(1, {N_GROS}) i"])
        if ddl:
            psql([ddl.format(t=t)])
        psql([f"VACUUM ANALYZE {t}"])
        tables[var] = t
        table_sizes[var] = size_of(f"g_{var}", "a4_tmp")
        if ddl:
            sizes[var] = size_of(name, "a4_tmp")
    return tables, sizes, table_sizes


def phase_gin_gros(tables):
    items = {}
    for v, t in tables.items():
        for kind in ("contient_livre", "contient_rare", "extrait_rare"):
            items[(v, kind)] = q_gros(t, kind)
    items[("colonne_typee", "colonne_rare")] = q_gros(tables["colonne_typee"], "colonne_rare")
    res = alternate(items, N_ROUNDS_READ, "gin_gros", pre=NO_PARALLEL)
    # équivalence : chaque requête == initiale ; la requête sur la colonne typée == extrait_rare de la référence
    for (v, q), val in res.items():
        ref_q = "extrait_rare" if q == "colonne_rare" else q
        val["identique_a_la_reference"] = val["md5"] == res[("initiale", ref_q)]["md5"]
    return res


def phase_gin_ecriture(tables):
    lots = {
        "insertion_20000": lambda v: (f"INSERT INTO {tables[v]} (id, nom, prix, stock, attributs) "
                                      f"SELECT id + 10000000, nom, prix, stock, attributs FROM {tables[v]} WHERE id <= 20000"),
        "maj_attributs_20000": lambda v: (f"UPDATE {tables[v]} SET attributs = attributs || '{{\"couleur\":\"vert\"}}'::jsonb "
                                          f"WHERE id <= 20000"),
    }
    return write_lots(tables, lots, N_ROUNDS_WRITE)


# ============================================================================= C. GiST
PERIODES_TEST = [  # (id, début, fin) : deux périodes qui se chevauchent, une disjointe, une contiguë (hors du chevauchement)
    (1, "2026-10-10 14:00+02", "2026-10-10 16:00+02"),
    (2, "2026-10-10 15:00+02", "2026-10-10 17:00+02"),
    (3, "2026-10-10 18:00+02", "2026-10-10 19:00+02"),
    (4, "2026-10-10 16:00+02", "2026-10-10 17:00+02"),
]
FENETRE = "tstzrange('2026-10-10 14:00+02', '2026-10-10 16:00+02')"


def phase_gist_petite():
    """Slide 18 / 26 : deux périodes qui se chevauchent, une disjointe (+ une contiguë, car l'intervalle est [) )."""
    psql(["CREATE TABLE a4_tmp.reservations (id bigint PRIMARY KEY, periode tstzrange NOT NULL)",
          "CREATE INDEX idx_periode ON a4_tmp.reservations USING gist (periode)"])
    for i, d, f in PERIODES_TEST:
        psql([f"INSERT INTO a4_tmp.reservations (id, periode) VALUES ({i}, tstzrange('{d}', '{f}', '[)'))"])
    psql(["VACUUM ANALYZE a4_tmp.reservations"])
    sql = f"SELECT id FROM a4_tmp.reservations WHERE periode && {FENETRE} ORDER BY id"
    ids = [int(x) for x in psql([sql]).split()]
    txt = psql([f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
    txt_off = psql(["SET enable_seqscan = off", f"EXPLAIN (ANALYZE, BUFFERS) {sql}"])
    save_plan("gist_petite", sql, txt)
    save_plan("gist_petite_seqscan_interdit", "SET enable_seqscan = off ; " + sql, txt_off)
    # preuve de la sémantique [) : la période contiguë (16h-17h) ne chevauche pas la fenêtre 14h-16h
    n_contigue = int(psql([f"SELECT count(*) FROM a4_tmp.reservations WHERE id = 4 AND periode && {FENETRE}"]).strip())
    p, poff = parse_plan(txt), parse_plan(txt_off)
    return {"ids_qui_chevauchent": ids, "periode_contigue_chevauche": bool(n_contigue),
            "avec_seqscan": {"noeuds": p["noeuds"], "cout": p["cout_estime"]},
            "seqscan_interdit": {"noeuds": poff["noeuds"], "index_utilises": poff["index_utilises"],
                                 "cout": poff["cout_estime"]},
            "periodes": PERIODES_TEST}


def phase_gist_gros():
    """Même contenu avec et sans GiST : 200 000 périodes d'une heure, une toutes les 10 minutes."""
    tables = {"sans_index": "a4_tmp.r_sans", "gist": "a4_tmp.r_gist"}
    sizes = {}
    for v, t in tables.items():
        psql([f"CREATE TABLE {t} (id bigint PRIMARY KEY, periode tstzrange NOT NULL)",
              f"INSERT INTO {t} SELECT i, tstzrange(timestamptz '2026-01-01 00:00+00' + i * interval '10 minutes', "
              f"timestamptz '2026-01-01 00:00+00' + i * interval '10 minutes' + interval '1 hour', '[)') "
              f"FROM generate_series(1, 200000) i"])
        if v == "gist":
            psql([f"CREATE INDEX a4_idx_gist ON {t} USING gist (periode)"])
            sizes["gist"] = size_of("a4_idx_gist", "a4_tmp")
        psql([f"VACUUM ANALYZE {t}"])
    fen = "tstzrange('2026-03-01 14:00+00', '2026-03-01 16:00+00')"
    items = {(v, "chevauchement"): f"SELECT id FROM {t} WHERE periode && {fen} ORDER BY id" for v, t in tables.items()}
    res = alternate(items, N_ROUNDS_READ, "gist_gros", pre=NO_PARALLEL)
    ref_check(res, "sans_index")
    nb = int(psql([f"SELECT count(*) FROM {tables['sans_index']} WHERE periode && {fen}"]).strip())
    lots = {"insertion_20000": lambda v: (f"INSERT INTO {tables[v]} SELECT id + 10000000, periode FROM {tables[v]} "
                                          f"WHERE id <= 20000")}
    ecriture = write_lots(tables, lots, N_ROUNDS_WRITE)
    return {"lecture": tag(res), "tailles_index_octets": sizes, "lignes_chevauchantes": nb,
            "table_octets": size_of("r_sans", "a4_tmp"), "ecriture": ecriture}


# ============================================================================= principal
def cleanup():
    """Supprime tout ce que le script a pu laisser dans le laboratoire (utilisé aussi en cas d'erreur)."""
    psql(["DROP SCHEMA IF EXISTS a4_tmp CASCADE"])
    for name in ("a4_idx_partiel", "a4_idx_complet", "a4_idx_now", "a4_idx_gin", "a4_idx_expr"):
        psql([f"DROP INDEX IF EXISTS shopflow.{name}"])


def main():
    env = {
        "version": psql(["SELECT version()"]).strip(),
        "work_mem": psql(["SHOW work_mem"]).strip(),
        "shared_buffers": psql(["SHOW shared_buffers"]).strip(),
        "commandes_octets": size_of("commandes", "shopflow"),
        "produits_octets": size_of("produits", "shopflow"),
        "repartition_statuts": {r.split("|")[0]: int(r.split("|")[1]) for r in psql(
            ["SELECT statut, count(*) FROM shopflow.commandes GROUP BY 1 ORDER BY 1"]).split()},
        "repartition_categories": {r.split("|")[0]: int(r.split("|")[1]) for r in psql(
            ["SELECT attributs->>'categorie', count(*) FROM shopflow.produits GROUP BY 1 ORDER BY 1"]).split()},
    }
    before = lab_state()
    print("Etat initial du labo :", before)
    assert not any(i.startswith("a4_") for i in before["index"]), "des index a4_ traînent déjà"

    print("== A. Index partiel : vraie table")
    a_reel, a_tailles, a_usage = phase_partiel_reel()
    print("== A. Requête paramétrée (plan générique / spécifique)")
    a_param = phase_partiel_parametre()
    print("== A. Prédicat avec now()")
    a_now = phase_predicat_now()

    print("== A. Tables de travail (commandes) et mesure renforcée")
    tables_c, a_tailles_tmp = build_commandes_tables()
    a_renf = phase_partiel_renforce(tables_c)
    print("== A. Écriture (insertions, changements de statut)")
    a_ecr, a_lot = phase_partiel_ecriture(tables_c)

    print("== B. GIN : vraie table produits")
    b_reel, b_tailles, b_usage, b_diag, b_table = phase_gin_reel()
    print("== B. GIN : 200 000 produits, une table par variante")
    tables_g, b_tailles_gros, b_tables_octets = build_gros_tables()
    b_comptes = {r.split("|")[0]: int(r.split("|")[1]) for r in psql(
        ["SELECT attributs->>'categorie', count(*) FROM a4_tmp.g_initiale GROUP BY 1 ORDER BY 1"]).split()}
    b_gros = phase_gin_gros(tables_g)
    print("== B. GIN : écriture")
    b_ecr = phase_gin_ecriture(tables_g)

    print("== C. GiST")
    c_petite = phase_gist_petite()
    c_gros = phase_gist_gros()

    print("== Nettoyage et contrôle de l'état final")
    psql(["DROP SCHEMA a4_tmp CASCADE"])
    after = lab_state()
    restaure = after == before
    print("Etat final du labo :", after, "| identique :", restaure)

    data = {
        "env": env, "etat_avant": before, "etat_apres": after, "labo_restaure": restaure,
        "partiel": {"reel": a_reel, "tailles_index_octets": a_tailles, "idx_scan": a_usage,
                    "parametre": a_param, "predicat_now": a_now,
                    "tailles_index_table_de_travail": a_tailles_tmp,
                    "renforce": tag(a_renf), "ecriture": a_ecr, "lots": a_lot},
        "gin": {"reel": b_reel, "tailles_index_octets": b_tailles, "idx_scan": b_usage, "diagnostic_seqscan": b_diag,
                "table_produits_octets": b_table,
                "gros": {"lignes": N_GROS, "repartition_categories": b_comptes,
                         "tailles_index_octets": b_tailles_gros, "tailles_table_octets": b_tables_octets,
                         "lecture": tag(b_gros), "ecriture": b_ecr}},
        "gist": {"petite": c_petite, "gros": c_gros},
    }
    with open(os.path.join(OUT, "resultats.json"), "w") as f:
        json.dump(data, f, indent=1, default=str)
    print("Résultats écrits dans", os.path.join(OUT, "resultats.json"))
    if not restaure:
        sys.exit("ATTENTION : le labo n'a pas retrouvé son état initial")


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        print("Erreur : nettoyage du laboratoire avant de quitter", file=sys.stderr)
        cleanup()
        raise
