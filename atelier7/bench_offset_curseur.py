#!/usr/bin/env python3
"""Atelier 7, ajout : OFFSET contre curseur à grande profondeur (ancienne requête -> nouvelle requête, même page).

La fiche étudiant le dit : avec 100 commandes pour le client 42, on vérifie le CONTRAT de la pagination mais on ne peut pas
annoncer de gain sur de grands décalages (un OFFSET qui dépasse le nombre de résultats ne mesure rien). Pour voir ce que
change le curseur quand le décalage est grand, je construis une table de travail JETABLE (schéma a7_tmp) :
  - 1 000 000 commandes pour un même client, avec des DATES EN DOUBLE (2 commandes par date, comme dans la slide 7) ;
  - le même index que l'atelier 3 : (client_id, created_at DESC, id DESC).

ATTENTION (piège déjà rencontré à l'atelier 3) : les alias de sortie id et created_at sont du TEXTE ; l'ORDER BY doit donc
qualifier les colonnes (commandes.created_at, commandes.id), comme le fait l'API.
Les colonnes lues sont celles de l'API (id, created_at, statut, total) : l'index ne les contient pas toutes, la table est donc lue.
Pour chaque profondeur k, on compare la MÊME page de 20 commandes (LIMIT 21 pour hasNextPage) :
  ancienne : ... ORDER BY created_at DESC, id DESC LIMIT 21 OFFSET k
  nouvelle : ... AND (created_at, id) < (date, id de la ligne k-1) ORDER BY created_at DESC, id DESC LIMIT 21
On vérifie d'abord que les deux pages sont identiques (empreinte md5), puis on mesure : 3 échauffements, 7 mesures
EXPLAIN (ANALYZE, BUFFERS), médiane, pages lues (hit + read).

Le laboratoire ShopFlow n'est pas modifié ; le schéma a7_tmp est supprimé à la fin et l'état du laboratoire est comparé.

Usage : python3 atelier7/bench_offset_curseur.py      (environ 1 minute)
"""
import hashlib
import json
import os
import re
import statistics
import subprocess
import time

CONT = "api-postgres-1"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resultats")
os.makedirs(OUT, exist_ok=True)
N = 1_000_000
DEPTHS = [0, 20, 1000, 20000, 100000, 500000, 900000, 999000]
LIMIT = 21


def psql(*statements):
    cmd = ["docker", "exec", "-i", CONT, "psql", "-U", "cours", "-d", "shopflow", "-X", "-At", "-q", "-v", "ON_ERROR_STOP=1"]
    for s in statements:
        cmd += ["-c", s]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def state():
    return [psql("SELECT count(*) FROM pg_indexes WHERE schemaname='shopflow'"), psql("SELECT count(*) FROM pg_statistic_ext"),
            psql("SELECT string_agg(tablename,',' ORDER BY tablename) FROM pg_tables WHERE schemaname='shopflow'"),
            psql("SELECT md5(string_agg(id||'|'||created_at::text, ',' ORDER BY id)) FROM shopflow.commandes")[:12]]


def explain(sql):
    out = psql("EXPLAIN (ANALYZE, BUFFERS) " + sql)
    ms = float(re.search(r"Execution Time: ([\d.]+) ms", out).group(1))
    m = re.search(r"Buffers: shared (?:hit=(\d+))?(?: ?read=(\d+))?", out)
    buf = int(m.group(1) or 0) + int(m.group(2) or 0) if m else None
    nodes = re.findall(r"(Index Only Scan|Index Scan|Bitmap Heap Scan|Seq Scan|Sort|Limit)", out)
    return ms, buf, nodes, out


def main():
    R = {"N": N, "limite": LIMIT, "debut": time.strftime("%Y-%m-%d %H:%M:%S"), "version": psql("SELECT version()")}
    before = state()
    psql("DROP SCHEMA IF EXISTS a7_tmp CASCADE", "CREATE SCHEMA a7_tmp")
    psql("CREATE TABLE a7_tmp.commandes (id bigint PRIMARY KEY, client_id int NOT NULL, created_at timestamptz NOT NULL, statut text NOT NULL, total numeric(10,2) NOT NULL)")
    psql(f"INSERT INTO a7_tmp.commandes SELECT g, 42, TIMESTAMPTZ '2026-01-01 00:00+00' + (g % {N // 2}) * INTERVAL '1 minute', 'payee', (g % 1000) / 10.0 FROM generate_series(1,{N}) g")
    psql("CREATE INDEX idx_hist ON a7_tmp.commandes (client_id, created_at DESC, id DESC)", "VACUUM (ANALYZE) a7_tmp.commandes")
    R["taille_table_octets"] = int(psql("SELECT pg_relation_size('a7_tmp.commandes')"))
    R["taille_index_octets"] = int(psql("SELECT pg_relation_size('a7_tmp.idx_hist')"))
    R["dates_distinctes"] = int(psql("SELECT count(DISTINCT created_at) FROM a7_tmp.commandes"))
    rows = []
    for k in DEPTHS:
        q_off = (f"SELECT id::text AS id, to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS.US') AS created_at, statut, total::text AS total FROM a7_tmp.commandes WHERE client_id = 42 "
                 f"ORDER BY commandes.created_at DESC, commandes.id DESC LIMIT {LIMIT} OFFSET {k}")
        if k == 0:
            q_cur = (f"SELECT id::text AS id, to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS.US') AS created_at, statut, total::text AS total FROM a7_tmp.commandes WHERE client_id = 42 "
                     f"ORDER BY commandes.created_at DESC, commandes.id DESC LIMIT {LIMIT}")
            repere = "(première page : pas de repère)"
        else:
            d, i = psql(f"SELECT created_at::text, id FROM a7_tmp.commandes WHERE client_id = 42 ORDER BY created_at DESC, id DESC OFFSET {k - 1} LIMIT 1").split("|")
            repere = f"({d}, {i})"
            q_cur = (f"SELECT id::text AS id, to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS.US') AS created_at, statut, total::text AS total FROM a7_tmp.commandes WHERE client_id = 42 "
                     f"AND (created_at, id) < (TIMESTAMPTZ '{d}', {i}::bigint) ORDER BY commandes.created_at DESC, commandes.id DESC LIMIT {LIMIT}")
        res_off, res_cur = psql(q_off), psql(q_cur)
        md5_off, md5_cur = hashlib.md5(res_off.encode()).hexdigest()[:12], hashlib.md5(res_cur.encode()).hexdigest()[:12]
        assert md5_off == md5_cur and len(res_off.splitlines()) == LIMIT, f"pages différentes pour k={k}"
        entry = {"decalage": k, "repere": repere, "md5": md5_off, "lignes": LIMIT}
        for nom, q in (("offset", q_off), ("curseur", q_cur)):
            for _ in range(3):
                explain(q)
            runs = [explain(q) for _ in range(7)]
            ms = [r[0] for r in runs]
            entry[nom] = {"ms": ms, "mediane_ms": statistics.median(ms), "min_ms": min(ms), "buffers": runs[-1][1], "noeuds": runs[-1][2]}
            if k in (100000,):
                with open(os.path.join(OUT, f"plan_{nom}_{k}.txt"), "w") as f:
                    f.write("-- " + q + "\n" + runs[-1][3])
        rows.append(entry)
        print(f"k={k:>7} pages identiques ({md5_off}) | OFFSET {entry['offset']['mediane_ms']:.3f} ms / {entry['offset']['buffers']} pages"
              f" | curseur {entry['curseur']['mediane_ms']:.3f} ms / {entry['curseur']['buffers']} pages")
    R["profondeurs"] = rows
    psql("DROP SCHEMA a7_tmp CASCADE")
    R["laboratoire_identique"] = state() == before
    R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    assert R["laboratoire_identique"]
    with open(os.path.join(OUT, "offset_curseur_volume.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print("laboratoire identique :", R["laboratoire_identique"])


if __name__ == "__main__":
    main()
