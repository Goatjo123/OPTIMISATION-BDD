#!/usr/bin/env python3
"""Atelier 4 bis : migration de schéma compatible (Jour 2, slides 33 à 43).

Rejoue, dans l'ordre, les fichiers 01 à 09 du dossier Atelier_4bis sur la base de laboratoire (PostgreSQL 18, Docker),
et conserve TOUTES les traces demandées par la slide 43 :
  01 SQL exécuté / 02 volumes et NULL (avant, pendant, après ; nombre, durée et WAL de chaque lot)
  03 compatibilité des lecteurs, défaut, rejet de NULL, 0 écart historique / 04 état de la contrainte avant et après
  05 verrou : erreur de B (55P03), COMMIT de A, réussite de B, chronologie / 06 retour arrière et contrôles.

Le SQL des fichiers du cours n'est PAS réécrit : il est relu tel quel dans Atelier_4bis/ et envoyé à psql, commande par
commande (comme « sélectionner puis exécuter » dans pgAdmin). Les sessions A, B (et C) sont de vraies connexions
distinctes (trois processus psql, application_name A / B / C).

Ajouts de ma part (hors cours, signalés comme tels dans le README) :
  - test « remplissage ne touche pas une valeur explicite » (annulé par ROLLBACK) ;
  - test « le CHECK NOT VALID refuse déjà une écriture NULL » (annulé) ;
  - preuve que SET NOT NULL ne rescanne pas la table (message DEBUG1 de PostgreSQL) ;
  - instantané de pg_stat_activity / pg_locks pendant l'attente de B ;
  - scénario « C derrière B » de la slide 31 (une lecture simple attend derrière l'ALTER en attente).

À la fin, les deux tables de travail sont supprimées : le laboratoire retrouve son état initial (comparé avant/après).

Usage : python3 atelier4bis/run_atelier.py      (conteneur api-postgres-1 démarré ; environ 30 secondes)
"""
import hashlib
import json
import os
import re
import subprocess
import threading
import time

CONT, DB, USER = "api-postgres-1", "shopflow", "cours"
HERE = os.path.dirname(os.path.abspath(__file__))
COURS = os.path.join(os.path.dirname(HERE), "Atelier_4bis")
OUT = os.path.join(HERE, "resultats")
os.makedirs(OUT, exist_ok=True)

TP, REF = "shopflow.clients_migration_tp", "shopflow.clients_migration_reference_tp"
SENT = "__FIN__"
TRANSCRIPT = []
R = {}  # résultats structurés


# ----------------------------------------------------------------------------- outils
class Sess:
    """Une connexion psql persistante (une vraie session : transaction ouverte, SET, verrous conservés)."""

    def __init__(self, name):
        self.name = name
        self.p = subprocess.Popen(
            ["docker", "exec", "-i", "-e", f"PGAPPNAME={name}", CONT, "psql", "-U", USER, "-d", DB, "-X", "-q"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        self.send("\\set VERBOSITY verbose\n\\timing on", log=False)

    def send(self, sql, log=True, title=None):
        # Deux sentinelles, une sur stdout (\echo) et une sur stderr (\warn) : psql écrit ses erreurs sur stderr, qui peut
        # arriver APRÈS la sortie standard de la commande suivante dans le tube. On lit donc jusqu'à avoir vu les deux.
        self.p.stdin.write(sql.rstrip() + f"\n\\echo {SENT}\n\\warn {SENT}\n")
        self.p.stdin.flush()
        lines, vues = [], 0
        while vues < 2:
            line = self.p.stdout.readline()
            if line == "":
                raise RuntimeError(f"[{self.name}] psql s'est arrêté")
            if line.strip() == SENT:
                vues += 1
                continue
            lines.append(line.rstrip("\n"))
        out = "\n".join(lines)
        if log:
            TRANSCRIPT.append((self.name, title, sql.strip(), out))
        return out

    def close(self):
        try:
            self.p.stdin.close()
            self.p.wait(timeout=10)
        except Exception:
            self.p.kill()


def q(sql):
    """Requête isolée, sortie brute sans mise en forme (-At)."""
    r = subprocess.run(["docker", "exec", "-i", CONT, "psql", "-U", USER, "-d", DB, "-X", "-At", "-q",
                        "-v", "ON_ERROR_STOP=1", "-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


def ms_of(text):
    """Durée serveur affichée par \\timing ('Time: 12.345 ms' ; plusieurs lignes -> la dernière)."""
    t = re.findall(r"Time: ([\d.]+) ms", text)
    return float(t[-1]) if t else None


def sqlstate(text):
    m = re.search(r"ERROR:\s+([0-9A-Z]{5}):", text)
    return m.group(1) if m else None


def step(title):
    TRANSCRIPT.append(("--", None, title, ""))
    print(f"\n== {title}")


def read_sql_blocks(fname):
    """Découpe un fichier du cours en commandes (séparées par ';'), en ignorant les commentaires seuls.
    BEGIN ... COMMIT/ROLLBACK reste découpé commande par commande (même chose qu'en pgAdmin)."""
    txt = open(os.path.join(COURS, fname), encoding="utf-8").read()
    body = "\n".join(l for l in txt.splitlines() if not l.strip().startswith("--"))
    return [s.strip() + ";" for s in body.split(";") if s.strip()]


def run_file_commands(sess, fname, only=None, title=None):
    """Exécute les commandes d'un fichier du cours ; renvoie [(sql, sortie)]."""
    res = []
    for sql in read_sql_blocks(fname):
        if only and not only(sql):
            continue
        out = sess.send(sql, title=title or fname)
        res.append((sql, out))
    return res


def lab_state():
    return {
        "index": q("SELECT indexname FROM pg_indexes WHERE schemaname='shopflow' ORDER BY 1").split(),
        "statistiques_etendues": int(q("SELECT count(*) FROM pg_statistic_ext")),
        "tables": q("SELECT tablename FROM pg_tables WHERE schemaname='shopflow' ORDER BY 1").split(),
        "lignes": {t: int(q(f"SELECT count(*) FROM shopflow.{t}")) for t in ("clients", "produits", "commandes", "lignes")},
        "md5_clients": q("SELECT md5(string_agg(id||'|'||email||'|'||nom, ',' ORDER BY id)) FROM shopflow.clients")[:12],
    }


def wal_lsn():
    return q("SELECT pg_current_wal_lsn()")


def wal_diff(a, b):
    return int(q(f"SELECT pg_wal_lsn_diff('{b}','{a}')"))


# ----------------------------------------------------------------------------- déroulement
def main():
    R["debut"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R["avant"] = lab_state()
    assert not any("migration" in t for t in R["avant"]["tables"]), "tables de migration déjà présentes"
    assert R["avant"]["lignes"]["clients"] == 1000
    print("état initial :", R["avant"])
    M = Sess("M")  # session de migration, autocommit

    # ---------------------------------------------------------------- 01
    step("01 : préparation (01_preparation.sql)")
    out = run_file_commands(M, "01_preparation.sql")
    R["version"] = q("SELECT version()")
    R["01_nb_clients"] = int(q(f"SELECT count(*) FROM {TP}"))
    R["01_nb_reference"] = int(q(f"SELECT count(*) FROM {REF}"))
    R["01_taille_copie_octets"] = int(q(f"SELECT pg_relation_size('{TP}')"))
    print("version / copie / référence :", R["01_nb_clients"], R["01_nb_reference"])
    assert R["01_nb_clients"] == 1000 == R["01_nb_reference"]
    # La copie conserve-t-elle clés et contraintes (LIKE ... INCLUDING ALL) ?
    R["01_contraintes_copie"] = q(
        f"SELECT string_agg(contype::text||':'||conname, ', ' ORDER BY conname) FROM pg_constraint WHERE conrelid='{TP}'::regclass")
    R["01_index_copie"] = q(
        "SELECT string_agg(indexname, ', ' ORDER BY indexname) FROM pg_indexes WHERE tablename='clients_migration_tp'")

    # ---------------------------------------------------------------- 02
    step("02 : ajout compatible de la colonne (02_ajout_colonne.sql)")
    t0 = time.monotonic()
    res = run_file_commands(M, "02_ajout_colonne.sql")
    R["02_alter_ms"] = ms_of(res[1][1])
    R["02_nb_null"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok IS NULL"))
    R["02_clients_originale_intacte"] = q(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' AND table_name='clients' "
        "AND column_name='newsletter_ok'") == "0"
    R["02_taille_apres_octets"] = int(q(f"SELECT pg_relation_size('{TP}')"))
    print("NULL :", R["02_nb_null"], "ALTER :", R["02_alter_ms"], "ms")
    assert R["02_nb_null"] == 1000

    # ---------------------------------------------------------------- 03
    step("03 : compatibilité des deux versions (03_compatibilite.sql)")
    res = run_file_commands(M, "03_compatibilite.sql")
    # contrôle : les lignes de test n'ont pas persisté
    R["03_lignes_test_persistantes"] = int(q(f"SELECT count(*) FROM {TP} WHERE id IN (1001,1002)"))
    R["03_nb_null_apres_defaut"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok IS NULL"))
    R["03_defaut"] = q("SELECT column_default FROM information_schema.columns WHERE table_schema='shopflow' "
                       "AND table_name='clients_migration_tp' AND column_name='newsletter_ok'")
    ins_out = [o for s, o in res if s.startswith("SELECT id,newsletter_ok")][0]
    R["03_insertions_test"] = ins_out
    print("lignes de test restantes :", R["03_lignes_test_persistantes"], "NULL :", R["03_nb_null_apres_defaut"])
    assert R["03_lignes_test_persistantes"] == 0 and R["03_nb_null_apres_defaut"] == 1000

    # Ajout : une valeur explicite déjà renseignée survit au remplissage (tout est annulé ensuite)
    step("03 bis (ajout) : une valeur explicite survit au remplissage (BEGIN ... ROLLBACK)")
    M.send("BEGIN;", title="test valeur explicite")
    M.send(f"UPDATE {TP} SET newsletter_ok = true WHERE id = 7;", title="test valeur explicite")
    lots_test = []
    for _ in range(7):
        o = M.send(
            f"WITH lot AS (SELECT id FROM {TP} WHERE newsletter_ok IS NULL ORDER BY id LIMIT 200), "
            f"maj AS (UPDATE {TP} c SET newsletter_ok = false FROM lot WHERE c.id = lot.id AND c.newsletter_ok IS NULL "
            f"RETURNING c.id) SELECT count(*) AS nb_mises_a_jour FROM maj;", title="test valeur explicite")
        lots_test.append(int(re.search(r"\n\s*(\d+)\s*\n", o).group(1)))
    o = M.send(f"SELECT id, newsletter_ok FROM {TP} WHERE id = 7;", title="test valeur explicite")
    R["03bis_lots_test"] = lots_test
    R["03bis_valeur_id7"] = "t" in o.split("\n")[2] if len(o.split("\n")) > 2 else None
    R["03bis_sortie"] = o
    M.send("ROLLBACK;", title="test valeur explicite")
    R["03bis_apres_rollback_null"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok IS NULL"))
    print("lots du test :", lots_test, "id 7 reste true :", R["03bis_valeur_id7"], "| NULL après ROLLBACK :", R["03bis_apres_rollback_null"])
    assert R["03bis_apres_rollback_null"] == 1000

    # ---------------------------------------------------------------- 04
    step("04 : remplissage par lots (04_remplissage_lot.sql)")
    lot_sql = [s for s in read_sql_blocks("04_remplissage_lot.sql") if s.startswith("WITH lot")][0]
    suivi_sql = [s for s in read_sql_blocks("04_remplissage_lot.sql") if "nb_null_restants" in s][0]
    lots = []
    R["04_taille_avant_octets"] = int(q(f"SELECT pg_relation_size('{TP}')"))
    w_all0 = wal_lsn()
    for i in range(1, 8):  # 5 lots de 200, puis 0, puis un relancement après 0 (idempotence)
        l0 = wal_lsn()
        out = M.send(lot_sql, title=f"lot {i}")
        l1 = wal_lsn()
        n = int(re.search(r"\n\s*(\d+)\s*\n", out).group(1))
        restants = int(re.search(r"\n\s*(\d+)\s*\n", M.send(suivi_sql, title=f"suivi après lot {i}")).group(1))
        lots.append({"lot": i, "lignes_modifiees": n, "duree_ms": ms_of(out), "wal_octets": wal_diff(l0, l1),
                     "null_restants": restants})
        print(" ", lots[-1])
        if n == 0 and i >= 6:
            break
    R["04_lots"] = lots
    R["04_wal_total_octets"] = wal_diff(w_all0, wal_lsn())
    R["04_taille_apres_octets"] = int(q(f"SELECT pg_relation_size('{TP}')"))
    R["04_nb_false"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok = false"))
    assert [l["lignes_modifiees"] for l in lots][:6] == [200] * 5 + [0], lots
    assert lots[-1]["lignes_modifiees"] == 0 and R["04_nb_false"] == 1000

    # ---------------------------------------------------------------- 05
    step("05 : contrainte progressive (05_contrainte_progressive.sql)")
    res = run_file_commands(M, "05_contrainte_progressive.sql")
    R["05_etat"] = res[-1][1]
    R["05_convalidated"] = q("SELECT convalidated FROM pg_constraint WHERE conname='clients_newsletter_nn_tp'")
    assert R["05_convalidated"] == "f"
    # Ajout : le CHECK NOT VALID refuse déjà les nouvelles écritures NULL
    M.send("BEGIN;", title="NOT VALID refuse un NULL")
    o = M.send(f"INSERT INTO {TP} (id,email,nom,newsletter_ok) VALUES (1001,'t@example.test','t',NULL);", title="NOT VALID refuse un NULL")
    R["05_not_valid_refuse_null"] = {"sqlstate": sqlstate(o), "sortie": o}
    M.send("ROLLBACK;", title="NOT VALID refuse un NULL")
    print("NOT VALID + insertion NULL ->", sqlstate(o))

    # ---------------------------------------------------------------- 06
    step("06 : validation (06_validation.sql)")
    cmds = read_sql_blocks("06_validation.sql")
    o_val = M.send(cmds[0], title="VALIDATE CONSTRAINT")
    R["06_validate_ms"] = ms_of(o_val)
    # preuve que SET NOT NULL ne rescanne pas : message DEBUG1 (le comportement n'est pas modifié)
    M.send("SET client_min_messages = debug1;", title="SET NOT NULL (avec traces DEBUG1)")
    o_nn = M.send(cmds[1], title="SET NOT NULL (avec traces DEBUG1)")
    M.send("SET client_min_messages = notice;", title="retour des messages")
    R["06_set_not_null_ms"] = ms_of(o_nn)
    R["06_set_not_null_debug"] = o_nn
    R["06_sans_scan"] = "sufficient to prove that it does not contain nulls" in o_nn
    R["06_etat_contrainte"] = M.send(cmds[2], title="état de la contrainte")
    R["06_colonne"] = M.send(cmds[3], title="état de la colonne")
    R["06_convalidated"] = q("SELECT convalidated FROM pg_constraint WHERE conname='clients_newsletter_nn_tp'")
    R["06_is_nullable"] = q("SELECT is_nullable FROM information_schema.columns WHERE table_schema='shopflow' "
                            "AND table_name='clients_migration_tp' AND column_name='newsletter_ok'")
    print("convalidated :", R["06_convalidated"], "| is_nullable :", R["06_is_nullable"], "| sans second scan :", R["06_sans_scan"])
    assert R["06_convalidated"] == "t" and R["06_is_nullable"] == "NO" and R["06_sans_scan"]

    # ---------------------------------------------------------------- 07
    step("07 : contrôles finaux (07_controles.sql)")
    cmds = read_sql_blocks("07_controles.sql")
    # bloc 1 : BEGIN / INSERT RETURNING / ROLLBACK
    M.send(cmds[0], title="défaut")
    o = M.send(cmds[1], title="défaut")
    R["07_defaut_insert"] = o
    M.send(cmds[2], title="défaut")
    # bloc 2 : le rejet de NULL (autocommit, hors transaction)
    o = M.send(cmds[3], title="rejet de NULL (erreur attendue 23502)")
    R["07_rejet_null"] = {"sqlstate": sqlstate(o), "sortie": o}
    o = M.send(cmds[4], title="comptages")
    R["07_comptage"] = o
    o = M.send(cmds[5], title="comparaison historique (EXCEPT ALL dans les deux sens)")
    R["07_ecarts_sortie"] = o
    R["07_nb_clients"] = int(q(f"SELECT count(*) FROM {TP}"))
    R["07_nb_null"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok IS NULL"))
    R["07_nb_false"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok = false"))
    R["07_ecarts"] = int(q(
        f"WITH d AS ((SELECT id,email,nom FROM {TP} EXCEPT ALL SELECT id,email,nom FROM {REF}) UNION ALL "
        f"(SELECT id,email,nom FROM {REF} EXCEPT ALL SELECT id,email,nom FROM {TP})) SELECT count(*) FROM d"))
    R["07_md5_copie"] = q(f"SELECT md5(string_agg(id||'|'||email||'|'||nom, ',' ORDER BY id)) FROM {TP}")[:12]
    R["07_md5_reference"] = q(f"SELECT md5(string_agg(id||'|'||email||'|'||nom, ',' ORDER BY id)) FROM {REF}")[:12]
    R["07_md5_clients"] = R["avant"]["md5_clients"]
    print("rejet NULL :", R["07_rejet_null"]["sqlstate"], "| clients/NULL/false :", R["07_nb_clients"], R["07_nb_null"], R["07_nb_false"],
          "| écarts :", R["07_ecarts"], "| md5 copie/réf/originale :", R["07_md5_copie"], R["07_md5_reference"], R["07_md5_clients"])
    assert R["07_rejet_null"]["sqlstate"] == "23502"
    assert (R["07_nb_clients"], R["07_nb_null"], R["07_nb_false"], R["07_ecarts"]) == (1000, 0, 1000, 0)

    # ---------------------------------------------------------------- 08 : verrous, trois vraies connexions
    step("08 : attente de verrou en deux sessions (08_verrous_session_A / B.sql)")
    sA = read_sql_blocks("08_verrous_session_A.sql")  # BEGIN ; SELECT ; COMMIT
    sB = read_sql_blocks("08_verrous_session_B.sql")  # SET ; ALTER ; DROP COLUMN ; RESET
    A, B = Sess("A"), Sess("B")
    chrono = []
    T0 = time.monotonic()

    def mark(who, what):
        chrono.append({"t_s": round(time.monotonic() - T0, 3), "session": who, "evenement": what})

    A.send(sA[0], title="A : transaction ouverte")
    A.send(sA[1], title="A : SELECT (ACCESS SHARE détenu)")
    mark("A", "BEGIN + SELECT : ACCESS SHARE détenu, transaction laissée ouverte")
    B.send(sB[0], title="B : SET lock_timeout")
    box = {}

    def b_alter():
        mark("B", "ALTER TABLE ... ADD COLUMN test_verrou : lancé (demande ACCESS EXCLUSIVE)")
        box["out"] = B.send(sB[1], title="B : ALTER TABLE (1re tentative)")
        mark("B", "retour de l'ALTER : " + (sqlstate(box["out"]) or "réussi"))

    th = threading.Thread(target=b_alter)
    tb0 = time.monotonic()
    th.start()
    time.sleep(1.0)
    snap_act = q("SELECT application_name AS session, state, wait_event_type, wait_event, left(query, 52) AS requete "
                 "FROM pg_stat_activity WHERE datname='shopflow' AND application_name IN ('A','B') ORDER BY application_name")
    snap_lock = q(f"SELECT a.application_name, l.mode, l.granted FROM pg_locks l JOIN pg_stat_activity a USING (pid) "
                  f"WHERE l.relation = '{TP}'::regclass AND a.application_name IN ('A','B') ORDER BY a.application_name, l.mode")
    mark("-", "instantané pg_stat_activity / pg_locks pris pendant l'attente de B (B attend toujours)")
    th.join()
    R["08_b_attente_s"] = round(time.monotonic() - tb0, 3)
    R["08_b_erreur_sqlstate"] = sqlstate(box["out"])
    R["08_b_erreur_sortie"] = box["out"]
    R["08_b_duree_serveur_ms"] = ms_of(box["out"])
    R["08_snapshot_activite"] = snap_act
    R["08_snapshot_verrous"] = snap_lock
    print("B :", R["08_b_erreur_sqlstate"], "après", R["08_b_attente_s"], "s | instantané :\n", snap_act, "\n", snap_lock)
    assert R["08_b_erreur_sqlstate"] == "55P03"
    R["08_colonne_test_apres_echec"] = q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                         "AND table_name='clients_migration_tp' AND column_name='test_verrou'")
    A.send(sA[2], title="A : COMMIT")
    mark("A", "COMMIT : verrou ACCESS SHARE libéré")
    tb1 = time.monotonic()
    o = B.send(sB[1], title="B : le même ALTER TABLE (2e tentative)")
    R["08_b_2e_tentative_ms"] = ms_of(o)
    R["08_b_2e_tentative_sortie"] = o
    mark("B", "même ALTER relancé : " + ("réussi" if "ERROR" not in o else sqlstate(o)))
    R["08_b_2e_tentative_ok"] = "ERROR" not in o
    R["08_colonne_test_apres_succes"] = q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                          "AND table_name='clients_migration_tp' AND column_name='test_verrou'")
    B.send(sB[2], title="B : nettoyage de test_verrou")
    B.send(sB[3], title="B : RESET lock_timeout")
    mark("B", "DROP COLUMN test_verrou + RESET lock_timeout : nettoyage")
    R["08_colonne_test_apres_nettoyage"] = q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                             "AND table_name='clients_migration_tp' AND column_name='test_verrou'")
    R["08_chronologie"] = chrono
    assert R["08_b_2e_tentative_ok"] and R["08_colonne_test_apres_succes"] == "1" and R["08_colonne_test_apres_nettoyage"] == "0"
    A.close()
    B.close()

    # ---------------------------------------------------------------- 08 bis (ajout) : C derrière B (slide 31)
    step("08 bis (ajout) : la lecture C attend derrière l'ALTER de B (slide 31)")
    A, B, C = Sess("A"), Sess("B"), Sess("C")
    chrono2 = []
    T0 = time.monotonic()

    def mark2(who, what):
        chrono2.append({"t_s": round(time.monotonic() - T0, 3), "session": who, "evenement": what})

    A.send(sA[0], title="A : BEGIN")
    A.send(sA[1], title="A : SELECT")
    mark2("A", "BEGIN + SELECT : ACCESS SHARE détenu")
    B.send("SET lock_timeout = '4s';", title="B : lock_timeout 4 s")
    boxb, boxc = {}, {}

    def b2():
        mark2("B", "ALTER TABLE lancé (attend ACCESS EXCLUSIVE derrière A)")
        boxb["out"] = B.send(sB[1], title="B : ALTER (attend 4 s)")
        mark2("B", "ALTER abandonné : " + (sqlstate(boxb["out"]) or "réussi"))

    def c2():
        mark2("C", "SELECT lancé (simple lecture, arrivée après B)")
        boxc["out"] = C.send(f"SELECT count(*) FROM {TP};", title="C : SELECT simple")
        mark2("C", "SELECT terminé")

    tb = threading.Thread(target=b2)
    tc = threading.Thread(target=c2)
    tb.start()
    time.sleep(1.0)
    tc.start()
    time.sleep(1.0)
    R["08bis_snapshot"] = q("SELECT a.application_name AS session, a.wait_event_type, a.wait_event, "
                            "pg_blocking_pids(a.pid) <> '{}' AS bloquee, left(a.query, 44) AS requete "
                            "FROM pg_stat_activity a WHERE a.datname='shopflow' AND a.application_name IN ('A','B','C') "
                            "ORDER BY a.application_name")
    mark2("-", "instantané pendant l'attente : B et C attendent, A non")
    tb.join()
    tc.join()
    A.send(sA[2], title="A : COMMIT")
    mark2("A", "COMMIT")
    c_ms = ms_of(boxc["out"])
    c_start = [e for e in chrono2 if e["session"] == "C" and "lancé" in e["evenement"]][0]["t_s"]
    c_end = [e for e in chrono2 if e["session"] == "C" and "terminé" in e["evenement"]][0]["t_s"]
    R["08bis_c_attente_s"] = round(c_end - c_start, 3)
    R["08bis_c_duree_serveur_ms"] = c_ms
    R["08bis_b_sqlstate"] = sqlstate(boxb["out"])
    R["08bis_chronologie"] = chrono2
    R["08bis_colonne_test"] = q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                "AND table_name='clients_migration_tp' AND column_name='test_verrou'")
    print("C a attendu", R["08bis_c_attente_s"], "s ; B :", R["08bis_b_sqlstate"], "| colonne test :", R["08bis_colonne_test"])
    print(R["08bis_snapshot"])
    assert R["08bis_colonne_test"] == "0"
    for s in (A, B, C):
        s.close()

    # ---------------------------------------------------------------- 09
    step("09 : retour arrière (09_retour_arriere.sql)")
    cmds = read_sql_blocks("09_retour_arriere.sql")
    for c in cmds[:6]:  # SET lock_timeout ; BEGIN ; DROP CONSTRAINT ; ALTER (2 sous-commandes) ; COMMIT ; (voir ci-dessous)
        pass
    o = []
    for c in cmds:
        o.append((c, M.send(c, title="09 retour arrière")))
        if c.startswith("COMMIT"):
            # « À ce stade, la colonne et ses valeurs existent encore » : on le constate avant le DROP COLUMN
            R["09_colonne_encore_la"] = q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                          "AND table_name='clients_migration_tp' AND column_name='newsletter_ok'")
            R["09_valeurs_encore_la"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok = false"))
            R["09_contraintes_restantes"] = q(f"SELECT count(*) FROM pg_constraint WHERE conname='clients_newsletter_nn_tp'")
            R["09_is_nullable_apres_retrait"] = q("SELECT is_nullable FROM information_schema.columns WHERE table_schema='shopflow' "
                                                  "AND table_name='clients_migration_tp' AND column_name='newsletter_ok'")
            R["09_defaut_apres_retrait"] = q("SELECT coalesce(column_default,'(aucun)') FROM information_schema.columns "
                                             "WHERE table_schema='shopflow' AND table_name='clients_migration_tp' "
                                             "AND column_name='newsletter_ok'")
    R["09_sortie_colonne_restante"] = [x for s, x in o if "colonne_restante" in s][0]
    R["09_sortie_ecarts"] = [x for s, x in o if "ecarts_historiques" in s][0]
    R["09_colonne_restante"] = int(q("SELECT count(*) FROM information_schema.columns WHERE table_schema='shopflow' "
                                     "AND table_name='clients_migration_tp' AND column_name='newsletter_ok'"))
    R["09_ecarts"] = int(q(
        f"WITH d AS ((SELECT id,email,nom FROM {TP} EXCEPT ALL SELECT id,email,nom FROM {REF}) UNION ALL "
        f"(SELECT id,email,nom FROM {REF} EXCEPT ALL SELECT id,email,nom FROM {TP})) SELECT count(*) FROM d"))
    R["09_md5_copie"] = q(f"SELECT md5(string_agg(id||'|'||email||'|'||nom, ',' ORDER BY id)) FROM {TP}")[:12]
    print("après retour : colonne restante", R["09_colonne_restante"], "| écarts", R["09_ecarts"], "| md5", R["09_md5_copie"])
    assert R["09_colonne_restante"] == 0 and R["09_ecarts"] == 0

    # ---------------------------------------------------------------- rejouabilité (LIRE_EN_PREMIER : « reprendre à 02 »)
    step("Rejouabilité : 02 relancé sur la copie conservée après le retour arrière")
    o = M.send(read_sql_blocks("02_ajout_colonne.sql")[1], title="rejeu de 02")
    R["rejeu_02_ok"] = "ERROR" not in o
    R["rejeu_02_nb_null"] = int(q(f"SELECT count(*) FROM {TP} WHERE newsletter_ok IS NULL"))
    o1 = M.send(read_sql_blocks("01_preparation.sql")[0], title="rejeu de 01 (doit échouer : la table existe)")
    R["rejeu_01_sqlstate"] = sqlstate(o1)
    print("rejeu 02 :", R["rejeu_02_ok"], "NULL", R["rejeu_02_nb_null"], "| rejeu 01 ->", R["rejeu_01_sqlstate"])

    # ---------------------------------------------------------------- nettoyage + état final
    step("Nettoyage : suppression des deux tables de travail, retour à l'état initial du laboratoire")
    M.send("RESET lock_timeout;", log=False)
    M.close()
    q(f"DROP TABLE {TP}")
    q(f"DROP TABLE {REF}")
    R["apres"] = lab_state()
    R["laboratoire_identique"] = R["avant"] == R["apres"]
    R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print("laboratoire identique à l'état initial :", R["laboratoire_identique"])
    assert R["laboratoire_identique"]

    with open(os.path.join(OUT, "resultats.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    with open(os.path.join(OUT, "transcript.txt"), "w", encoding="utf-8") as f:
        f.write("TRANSCRIPT BRUT de l'atelier 4 bis (sortie psql avec \\timing et VERBOSITY verbose)\n")
        f.write(f"Exécuté le {R['debut']} sur {R['version'][:30]}\n")
        for sess, title, sql, out in TRANSCRIPT:
            if sess == "--":
                f.write(f"\n{'=' * 100}\n{sql}\n{'=' * 100}\n")
                continue
            f.write(f"\n[{sess}] {title or ''}\n{sql}\n--> {out}\n")
    print("\nRésultats écrits dans", OUT)


if __name__ == "__main__":
    main()
