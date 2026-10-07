#!/usr/bin/env python3
"""Atelier 4 bis, mesure à plus grand volume : ANCIENNE version de la migration -> NOUVELLE version.

Le résultat final est le même (colonne newsletter_ok NOT NULL, défaut false, toutes les lignes à false).
Ce qui change, c'est le COÛT pour les autres utilisateurs de la table : combien de temps une lecture ou une écriture
concurrente reste bloquée pendant la migration.

  ANCIENNE (naïve)                                   NOUVELLE (atelier 4 bis)
  1. ADD COLUMN newsletter_ok boolean                1. ADD COLUMN newsletter_ok boolean
  2. un seul UPDATE sur toutes les lignes            2. UPDATE par lots (chacun validé)
  3. SET NOT NULL (la table est LUE en entier,       3. CHECK ... NOT VALID (instantané), VALIDATE (verrou léger),
     sous verrou ACCESS EXCLUSIVE)                      puis SET NOT NULL qui SAUTE le scan (le CHECK valide suffit)

Mesures par variante, sur une table de travail de N lignes (schéma a4b_tmp, supprimé à la fin) :
  - durée de chaque étape, WAL produit, taille de la table avant/après ;
  - « sonde » : une connexion séparée qui, en boucle, fait une lecture (SELECT ... WHERE id = x) ou un verrouillage
    de ligne (SELECT ... FOR UPDATE) et note la plus longue attente observée pendant l'étape ;
  - équivalence finale : empreinte md5 du contenu, nullabilité, défaut.

Usage : python3 atelier4bis/bench_volume.py [N]     (N = 3 000 000 par défaut ; environ 1 à 2 minutes)
"""
import json
import os
import re
import statistics
import subprocess
import sys
import threading
import time

CONT, DB, USER = "api-postgres-1", "shopflow", "cours"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "resultats")
os.makedirs(OUT, exist_ok=True)
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3_000_000
LOT = 50_000
SENT = "__FIN__"
SCH = "a4b_tmp"


class Sess:
    def __init__(self, name):
        self.p = subprocess.Popen(
            ["docker", "exec", "-i", "-e", f"PGAPPNAME={name}", CONT, "psql", "-U", USER, "-d", DB, "-X", "-q"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.send("\\set VERBOSITY verbose\n\\timing on")

    def send(self, sql):
        # sentinelle sur stdout ET sur stderr : les erreurs de psql (stderr) peuvent arriver après la commande suivante
        self.p.stdin.write(sql.rstrip() + f"\n\\echo {SENT}\n\\warn {SENT}\n")
        self.p.stdin.flush()
        lines, vues = [], 0
        while vues < 2:
            line = self.p.stdout.readline()
            if line == "":
                raise RuntimeError("psql arrêté")
            if line.strip() == SENT:
                vues += 1
                continue
            lines.append(line.rstrip("\n"))
        return "\n".join(lines)

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def q(sql):
    r = subprocess.run(["docker", "exec", "-i", CONT, "psql", "-U", USER, "-d", DB, "-X", "-At", "-q",
                        "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def ms_of(text):
    t = re.findall(r"Time: ([\d.]+) ms", text)
    return float(t[-1]) if t else None


def wal():
    return q("SELECT pg_current_wal_lsn()")


def wal_diff(a, b):
    return int(q(f"SELECT pg_wal_lsn_diff('{b}','{a}')"))


class Sonde:
    """Connexion séparée qui rejoue en boucle une requête et mémorise la plus longue attente (hors 1re mesure)."""

    def __init__(self, nom, sql):
        self.s, self.sql, self.vals, self.stop = Sess(nom), sql, [], False
        self.th = threading.Thread(target=self.run)

    def run(self):
        while not self.stop:
            self.vals.append(ms_of(self.s.send(self.sql)))
            time.sleep(0.002)

    def start(self):
        self.th.start()
        time.sleep(0.3)  # quelques mesures « à vide » avant l'étape
        return self

    def end(self):
        self.stop = True
        self.th.join()
        self.s.close()
        v = [x for x in self.vals if x is not None]
        return {"mesures": len(v), "max_ms": round(max(v), 1), "mediane_ms": round(statistics.median(v), 2)}


def build(name):
    q(f"CREATE TABLE {SCH}.{name} (id bigint PRIMARY KEY, email text NOT NULL UNIQUE, nom text NOT NULL)")
    q(f"INSERT INTO {SCH}.{name} SELECT g, 'etudiant'||g||'@example.test', 'Client '||g FROM generate_series(1,{N}) g")
    q(f"VACUUM (ANALYZE) {SCH}.{name}")  # états de visibilité et statistiques identiques pour les deux variantes
    return int(q(f"SELECT pg_relation_size('{SCH}.{name}')"))


def timed(S, sql, sonde_sql=None, nom_sonde="P"):
    sonde = Sonde(nom_sonde, sonde_sql).start() if sonde_sql else None
    w0 = wal()
    out = S.send(sql)
    w1 = wal()
    r = {"ms": ms_of(out), "wal_octets": wal_diff(w0, w1)}
    if "ERROR" in out:
        r["erreur"] = out
    if sonde:
        r["sonde"] = sonde.end()
    return r


def main():
    R = {"N": N, "lot": LOT, "version": q("SHOW server_version"), "debut": time.strftime("%Y-%m-%d %H:%M:%S")}
    avant = [q("SELECT count(*) FROM pg_indexes WHERE schemaname='shopflow'"), q("SELECT count(*) FROM pg_statistic_ext")]
    q(f"DROP SCHEMA IF EXISTS {SCH} CASCADE")
    q(f"CREATE SCHEMA {SCH}")
    mid = N // 2
    lecture = f"SELECT id FROM {SCH}.{{t}} WHERE id = 1;"
    verrou = f"SELECT 1 FROM {SCH}.{{t}} WHERE id = {mid} FOR UPDATE;"

    # ------------------------------------------------------------------ ANCIENNE
    t = "t_ancienne"
    R["taille_initiale_octets"] = build(t)
    S = Sess("M")
    a = {}
    a["add_column"] = timed(S, f"ALTER TABLE {SCH}.{t} ADD COLUMN newsletter_ok boolean;")
    a["default"] = timed(S, f"ALTER TABLE {SCH}.{t} ALTER COLUMN newsletter_ok SET DEFAULT false;")
    s0 = int(q(f"SELECT pg_relation_size('{SCH}.{t}')"))
    a["update_unique"] = timed(S, f"UPDATE {SCH}.{t} SET newsletter_ok = false WHERE newsletter_ok IS NULL;",
                               sonde_sql=verrou.format(t=t))
    a["update_unique"]["taille_apres_octets"] = int(q(f"SELECT pg_relation_size('{SCH}.{t}')"))
    a["update_unique"]["taille_avant_octets"] = s0
    a["set_not_null"] = timed(S, f"ALTER TABLE {SCH}.{t} ALTER COLUMN newsletter_ok SET NOT NULL;",
                              sonde_sql=lecture.format(t=t))
    S.close()
    R["ancienne"] = a
    R["ancienne_final"] = final(t)

    # ------------------------------------------------------------------ NOUVELLE
    t = "t_nouvelle"
    build(t)
    S = Sess("M")
    n = {}
    n["add_column"] = timed(S, f"ALTER TABLE {SCH}.{t} ADD COLUMN newsletter_ok boolean;")
    n["default"] = timed(S, f"ALTER TABLE {SCH}.{t} ALTER COLUMN newsletter_ok SET DEFAULT false;")
    s0 = int(q(f"SELECT pg_relation_size('{SCH}.{t}')"))
    lot_sql = (f"WITH lot AS (SELECT id FROM {SCH}.{t} WHERE newsletter_ok IS NULL ORDER BY id LIMIT {LOT}), "
               f"maj AS (UPDATE {SCH}.{t} c SET newsletter_ok = false FROM lot WHERE c.id = lot.id "
               f"AND c.newsletter_ok IS NULL RETURNING c.id) SELECT count(*) AS nb FROM maj;")
    sonde = Sonde("P", verrou.format(t=t)).start()
    w0, lots, t0 = wal(), [], time.monotonic()
    while True:
        out = S.send(lot_sql)
        nb = int(re.search(r"\n\s*(\d+)\s*\n", out).group(1))
        lots.append({"lignes": nb, "ms": ms_of(out)})
        if nb == 0:
            break
    duree_totale = (time.monotonic() - t0) * 1000
    w1 = wal()
    n["lots"] = {"nombre_de_lots_utiles": len([l for l in lots if l["lignes"] > 0]),
                 "lots": lots, "ms_total_mur": round(duree_totale, 1),
                 "ms_lot_max": max(l["ms"] for l in lots), "ms_lot_mediane": statistics.median(l["ms"] for l in lots if l["lignes"]),
                 "wal_octets": wal_diff(w0, w1), "sonde": sonde.end(),
                 "taille_avant_octets": s0, "taille_apres_octets": int(q(f"SELECT pg_relation_size('{SCH}.{t}')"))}
    n["check_not_valid"] = timed(
        S, f"ALTER TABLE {SCH}.{t} ADD CONSTRAINT nn_ck CHECK (newsletter_ok IS NOT NULL) NOT VALID;")
    n["validate"] = timed(S, f"ALTER TABLE {SCH}.{t} VALIDATE CONSTRAINT nn_ck;",
                          sonde_sql=lecture.format(t=t))
    # la sonde « écriture » sur VALIDATE : validate est court, on la rejoue sur une transaction maintenue ouverte (voir plus bas)
    S.send("SET client_min_messages = debug1;")
    n["set_not_null"] = timed(S, f"ALTER TABLE {SCH}.{t} ALTER COLUMN newsletter_ok SET NOT NULL;")
    S.send("SET client_min_messages = notice;")
    S.close()
    R["nouvelle"] = n
    R["nouvelle_final"] = final(t)

    # ------------------------------------------------------------------ preuve de verrouillage (déterministe)
    # On MAINTIENT chaque ALTER dans une transaction ouverte et on regarde si une lecture / une écriture concurrente passe.
    S = Sess("M")
    C = Sess("C")
    C.send("SET lock_timeout = '500ms';")
    p = {}
    # a) VALIDATE CONSTRAINT : verrou SHARE UPDATE EXCLUSIVE
    t = "t_preuve"
    q(f"CREATE TABLE {SCH}.{t} (id bigint PRIMARY KEY, nom text, v boolean DEFAULT false NOT NULL)")
    q(f"INSERT INTO {SCH}.{t} SELECT g, 'x', false FROM generate_series(1,1000) g")
    q(f"ALTER TABLE {SCH}.{t} ADD CONSTRAINT nn2 CHECK (v IS NOT NULL) NOT VALID")
    S.send("BEGIN;")
    S.send(f"ALTER TABLE {SCH}.{t} VALIDATE CONSTRAINT nn2;")
    p["verrou_validate"] = q(f"SELECT string_agg(mode, ',') FROM pg_locks WHERE relation = '{SCH}.{t}'::regclass AND granted")
    p["validate_lecture_concurrente"] = ms_ok(C.send(f"SELECT count(*) FROM {SCH}.{t};"))
    p["validate_ecriture_concurrente"] = ms_ok(C.send(f"UPDATE {SCH}.{t} SET nom = 'y' WHERE id = 1;"))
    p["validate_insertion_concurrente"] = ms_ok(C.send(f"INSERT INTO {SCH}.{t} VALUES (5000,'z',false);"))
    S.send("ROLLBACK;")
    # b) SET NOT NULL : verrou ACCESS EXCLUSIVE
    S.send("BEGIN;")
    S.send(f"ALTER TABLE {SCH}.{t} ALTER COLUMN v SET NOT NULL;")
    p["verrou_set_not_null"] = q(f"SELECT string_agg(mode, ',') FROM pg_locks WHERE relation = '{SCH}.{t}'::regclass AND granted")
    p["set_not_null_lecture_concurrente"] = ms_ok(C.send(f"SELECT count(*) FROM {SCH}.{t};"))
    S.send("ROLLBACK;")
    # c) ADD CONSTRAINT ... CHECK (valide) : verrou ACCESS EXCLUSIVE ET scan complet ; NOT VALID : verrou bref sans scan
    S.close()
    C.close()
    R["preuve_verrous"] = p

    q(f"DROP SCHEMA {SCH} CASCADE")
    R["laboratoire_intact"] = [q("SELECT count(*) FROM pg_indexes WHERE schemaname='shopflow'"),
                              q("SELECT count(*) FROM pg_statistic_ext")] == avant and \
        q("SELECT string_agg(tablename, ',' ORDER BY tablename) FROM pg_tables WHERE schemaname='shopflow'") == "clients,commandes,lignes,produits"
    R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(os.path.join(OUT, "volume.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: v for k, v in R.items() if k not in ("ancienne", "nouvelle")}, ensure_ascii=False, indent=1))
    print(json.dumps(R["ancienne"], ensure_ascii=False, indent=1)[:2500])
    nn = dict(R["nouvelle"])
    nn["lots"] = {k: v for k, v in nn["lots"].items() if k != "lots"}
    print(json.dumps(nn, ensure_ascii=False, indent=1)[:3500])


def ms_ok(out):
    """'ok (x ms)' si la commande concurrente est passée, sinon le code d'erreur (55P03 = verrou refusé après 500 ms)."""
    m = re.search(r"ERROR:\s+([0-9A-Z]{5}):", out)
    return {"resultat": "bloquée (55P03 après 500 ms)" if m and m.group(1) == "55P03" else ("erreur " + m.group(1) if m else "passe"),
            "ms": ms_of(out)}


def final(t):
    return {"md5": q(f"SELECT md5(string_agg(id||'|'||email||'|'||nom||'|'||newsletter_ok::text, ',' ORDER BY id)) FROM {SCH}.{t}")[:12],
            "lignes": int(q(f"SELECT count(*) FROM {SCH}.{t}")),
            "nb_false": int(q(f"SELECT count(*) FROM {SCH}.{t} WHERE newsletter_ok = false")),
            "nb_null": int(q(f"SELECT count(*) FROM {SCH}.{t} WHERE newsletter_ok IS NULL")),
            "is_nullable": q(f"SELECT is_nullable FROM information_schema.columns WHERE table_schema='{SCH}' AND table_name='{t}' AND column_name='newsletter_ok'"),
            "defaut": q(f"SELECT column_default FROM information_schema.columns WHERE table_schema='{SCH}' AND table_name='{t}' AND column_name='newsletter_ok'")}


if __name__ == "__main__":
    main()
