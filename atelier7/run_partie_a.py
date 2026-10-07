#!/usr/bin/env python3
"""Atelier 7, partie A : la page et ses relations (Jour 4, slides 12, 13 et fiche étudiant, étapes 1 à 6).

Rejoue la fiche étudiant du kit sur l'API ShopFlow fournie (01_server/api, démarrée par ce script) :
  - les appels HTTP passent par l'aide du kit (Kit_Jour4_Windows_Linux/02_Laboratoire/Jour4/jour4_http.mjs : « sf »),
    qui lit le jeton dans .env, mesure HttpMs, lit X-SQL-Count et X-Trace-Id et enregistre un CSV ;
  - les scripts SQL du kit (07_dates_identiques.sql, 07_restaurer_dates.sql) sont envoyés tels quels à PostgreSQL ;
  - les journaux de l'API (une ligne JSON par appel : sqlCount, sqlMs, durationMs) sont conservés et rattachés aux appels
    par TraceId.

Chaque étape vérifie son résultat attendu : le script s'arrête sur un écart. Ajouts de ma part (hors fiche, signalés) :
égalité de réponses sur plusieurs tailles de page, page vide, ordre vérifié contre PostgreSQL, curseur falsifié,
mesure répétée N+1 / groupé (30 tours alternés), vérification de la restauration par empreinte md5.

À la fin : dates restaurées (vérifié par empreinte), table de sauvegarde du kit supprimée, API arrêtée, et le laboratoire
ShopFlow est comparé à son état initial.

Usage : python3 atelier7/run_partie_a.py     (conteneurs api-postgres-1 et api-redis-1 démarrés ; environ 2 minutes)
"""
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "01_server", "api")
KIT = os.path.join(ROOT, "Kit_Jour4_Windows_Linux", "02_Laboratoire", "Jour4")
HELPER = os.path.join(KIT, "jour4_http.mjs")
OUT = os.path.join(ROOT, "atelier7", "resultats")
os.makedirs(OUT, exist_ok=True)
CSV = os.path.join(OUT, "mesures_partie_a.csv")
APILOG = os.path.join(OUT, "api_journal.log")
CONT = "api-postgres-1"
R = {}


# ----------------------------------------------------------------------------- outils
def psql(sql, stdin=None, flags=("-At",)):
    cmd = ["docker", "exec", "-i", CONT, "psql", "-U", "cours", "-d", "shopflow", "-X", "-q", "-v", "ON_ERROR_STOP=1", *flags]
    if stdin is None:
        cmd += ["-c", sql]
    r = subprocess.run(cmd, input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"psql : {r.stderr.strip()}")
    return r.stdout.strip()


def lab_state():
    return {
        "index": psql("SELECT indexname FROM pg_indexes WHERE schemaname='shopflow' ORDER BY 1").split(),
        "statistiques_etendues": int(psql("SELECT count(*) FROM pg_statistic_ext")),
        "tables": psql("SELECT tablename FROM pg_tables WHERE schemaname='shopflow' ORDER BY 1").split(),
        "lignes": {t: int(psql(f"SELECT count(*) FROM shopflow.{t}")) for t in ("clients", "produits", "commandes", "lignes")},
        "md5_dates_commandes": psql("SELECT md5(string_agg(id||'|'||created_at::text, ',' ORDER BY id)) FROM shopflow.commandes")[:12],
        "md5_lignes": psql("SELECT md5(string_agg(commande_id||'|'||produit_id||'|'||qte||'|'||prix_unitaire, ',' ORDER BY commande_id, produit_id)) FROM shopflow.lignes")[:12],
    }


def helper(*args, extra_env=None):
    env = dict(os.environ, J4_CSV=CSV)
    r = subprocess.run(["node", HELPER, *args], cwd=API, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"helper {args[:2]} : {r.stderr.strip()}")
    return r.stdout.strip()


def sf(label, path, method="GET", body=None):
    """Équivalent de la fonction `sf` de la fiche : renvoie Status, SqlCount, HttpMs, TraceId, Body."""
    a = ["request", label, path, method] + ([body] if body is not None else [])
    res = json.loads(helper(*a))
    time.sleep(0.01)
    res["journal"] = journal(res["TraceId"])
    return res


def code(path, sans_jeton=False):
    return int(helper("code", path, *(["sans-jeton"] if sans_jeton else [])))


def journal(trace):
    for _ in range(40):
        with open(APILOG, encoding="utf-8") as f:
            for line in f:
                if trace in line and line.startswith("{"):
                    return json.loads(line)
        time.sleep(0.05)
    return None


def pick(res):
    d = {k: res[k] for k in ("Status", "SqlCount", "HttpMs", "TraceId")}
    d["journal"] = res["journal"]
    return d


def enc(s):
    return urllib.parse.quote(s, safe="")


def ids(res):
    return [row["id"] for row in res["Body"]["data"]]


def med(v):
    return round(statistics.median(v), 3)


def p95(v):
    v = sorted(v)
    import math
    return round(v[math.ceil(0.95 * len(v)) - 1], 3)


def step(t):
    print(f"\n== {t}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


# ----------------------------------------------------------------------------- déroulement
def main():
    R["debut"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R["node"] = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip()
    R["version_pg"] = psql("SELECT version()")
    R["avant"] = lab_state()
    state = {"modifiees": False, "restaurees": False}
    check(R["avant"]["index"].__len__() == 6 and R["avant"]["statistiques_etendues"] == 0 and "sauvegarde_dates_atelier07" not in R["avant"]["tables"],
          "laboratoire pas dans l'état initial : " + str(R["avant"]))
    print("état initial :", R["avant"])
    header = ["Date", "Label", "Method", "Path", "Status", "SqlCount", "Cache", "HttpMs", "TraceId", "Prix", "Ids"]
    with open(CSV, "w", encoding="utf-8") as f:
        f.write(",".join('"' + h + '"' for h in header) + "\n")
    open(APILOG, "w").close()

    # ------------------------------------------------------------ 1. mise en route
    step("1. Mise en route : API démarrée, client 42, 100 commandes")
    logf = open(APILOG, "a", encoding="utf-8")
    api = subprocess.Popen(["node", "--env-file=.env", "server.mjs"], cwd=API, stdout=logf, stderr=subprocess.STDOUT)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:3000/", timeout=1)
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.25)
        etat = sf("demarrage", "/observations")
        check(etat["Status"] == 200, "API : /observations n'a pas répondu 200")
        R["1_observations"] = etat["Body"]
        R["1_nb_commandes_client42"] = int(psql("SELECT count(*) FROM shopflow.commandes WHERE client_id=42"))
        R["1_lignes_par_commande_min_max"] = psql(
            "SELECT min(n)||'-'||max(n) FROM (SELECT count(*) n FROM shopflow.lignes l JOIN shopflow.commandes c ON c.id=l.commande_id WHERE c.client_id=42 GROUP BY c.id) t")
        check(R["1_nb_commandes_client42"] == 100 and R["1_lignes_par_commande_min_max"] == "3-3", "jeu du client 42 inattendu")
        print("client 42 :", R["1_nb_commandes_client42"], "commandes, lignes par commande", R["1_lignes_par_commande_min_max"])

        # -------------------------------------------------------- 2. N+1 contre groupé
        step("2. N+1 contre chargement groupé")
        page = "/commandes?limit=20&pagination=curseur"
        n1 = sf("n1_20", page + "&relations=n1")
        groupe = sf("groupe_20", page + "&relations=groupe")
        check(n1["Status"] == groupe["Status"] == 200, "statut")
        check(len(n1["Body"]["data"]) == 20 and all(len(r["lignes"]) == 3 for r in n1["Body"]["data"]), "20 commandes de 3 lignes attendues")
        check(n1["Body"] == groupe["Body"], "réponses N+1 et groupé différentes")
        check((n1["SqlCount"], groupe["SqlCount"]) == (21, 2), f"SQL attendus 21/2, obtenus {n1['SqlCount']}/{groupe['SqlCount']}")
        R["2_page20"] = {"n1": pick(n1),
                         "groupe": pick(groupe),
                         "reponses_identiques": True}
        print("page de 20 : N+1", n1["SqlCount"], "SQL ; groupé", groupe["SqlCount"], "SQL ; réponses identiques")
        # ajout : plusieurs tailles de page + page vide
        tailles = {}
        for lim in (5, 20, 50, 100):
            a = sf(f"n1_{lim}", f"/commandes?limit={lim}&pagination=curseur&relations=n1")
            b = sf(f"groupe_{lim}", f"/commandes?limit={lim}&pagination=curseur&relations=groupe")
            check(a["Body"] == b["Body"], f"réponses différentes pour limit={lim}")
            tailles[lim] = {"n1_sql": a["SqlCount"], "groupe_sql": b["SqlCount"], "commandes": len(a["Body"]["data"])}
            check(tailles[lim]["n1_sql"] == lim + 1 and tailles[lim]["groupe_sql"] == 2, f"comptage limit={lim}")
        vide_n1 = sf("vide_n1", "/commandes?limit=20&pagination=offset&offset=100&relations=n1")
        vide_g = sf("vide_groupe", "/commandes?limit=20&pagination=offset&offset=100&relations=groupe")
        check(vide_n1["Body"]["data"] == [] and vide_n1["SqlCount"] == 1 and vide_g["SqlCount"] == 1, "page vide : 1 requête attendue")
        R["2_tailles"] = tailles
        R["2_page_vide"] = {"n1_sql": vide_n1["SqlCount"], "groupe_sql": vide_g["SqlCount"]}
        print("tailles :", tailles, "| page vide :", R["2_page_vide"])
        # ajout : mesure répétée, alternée, 5 échauffements puis 30 tours
        rep = {}
        for lim in (20, 50):
            for _ in range(5):
                sf("chauffe", f"/commandes?limit={lim}&relations=n1")
                sf("chauffe", f"/commandes?limit={lim}&relations=groupe")
            vals = {"n1": {"http": [], "sql": [], "duree": []}, "groupe": {"http": [], "sql": [], "duree": []}}
            for i in range(30):
                for mode in (("n1", "groupe") if i % 2 == 0 else ("groupe", "n1")):
                    r = sf(f"rep_{mode}_{lim}", f"/commandes?limit={lim}&relations={mode}")
                    vals[mode]["http"].append(r["HttpMs"])
                    vals[mode]["sql"].append(r["journal"]["sqlMs"])
                    vals[mode]["duree"].append(r["journal"]["durationMs"])
            rep[lim] = {m: {"tours": 30, "http_mediane": med(v["http"]), "http_p95": p95(v["http"]), "http_min": round(min(v["http"]), 3),
                            "sqlMs_mediane": med(v["sql"]), "duree_serveur_mediane": med(v["duree"]),
                            "http_brut": v["http"]} for m, v in vals.items()}
            print(f"limit={lim} médianes HttpMs : n1 {rep[lim]['n1']['http_mediane']} / groupé {rep[lim]['groupe']['http_mediane']}")
        R["2_repetition"] = rep

        # -------------------------------------------------------- 3. OFFSET contre curseur
        step("3. OFFSET contre curseur (deuxième page)")
        p1 = sf("curseur_p1", "/commandes?limit=20&relations=groupe")
        cur = enc(p1["Body"]["nextCursor"])
        p2c = sf("curseur_p2", f"/commandes?limit=20&cursor={cur}&relations=groupe")
        p2o = sf("offset_p2", "/commandes?limit=20&pagination=offset&offset=20&relations=groupe")
        check(p2c["Body"] == p2o["Body"], "page 2 : curseur et OFFSET différents")
        check(len(p2c["Body"]["data"]) == 20 and p2c["SqlCount"] == 2 and p2o["SqlCount"] == 2, "page 2 : 20 commandes et 2 SQL attendus")
        R["3_page2"] = {"curseur": pick(p2c),
                        "offset": pick(p2o),
                        "reponses_identiques": True, "nextCursor_p1": p1["Body"]["nextCursor"], "premiers_ids": ids(p2c)[:3]}
        print("page 2 identique ; SQL", p2c["SqlCount"], p2o["SqlCount"])
        # contrat de l'endpoint
        defaut = sf("defaut", "/commandes")
        gros = sf("limit100", "/commandes?limit=100")
        check(len(defaut["Body"]["data"]) == 20 and len(gros["Body"]["data"]) == 100 and gros["Body"]["hasNextPage"] is False
              and gros["Body"]["nextCursor"] is None, "contrat : limite par défaut 20, maximum 100")
        row = defaut["Body"]["data"][0]
        check(set(defaut["Body"]) == {"data", "hasNextPage", "nextCursor"} and isinstance(row["id"], str) and isinstance(row["total"], str)
              and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", row["created_at"]), "contrat : formats")
        cmp_ok = [(a["created_at"], int(a["id"])) for a in gros["Body"]["data"]]
        check(cmp_ok == sorted(cmp_ok, reverse=True), "ordre created_at DESC, id DESC non respecté")
        R["3_contrat"] = {"cles": sorted(defaut["Body"]), "limite_defaut": len(defaut["Body"]["data"]), "limite_max": len(gros["Body"]["data"]),
                          "exemple_ligne": row, "ordre_ok": True,
                          "limit_101": code("/commandes?limit=101"), "limit_0": code("/commandes?limit=0")}
        check(R["3_contrat"]["limit_101"] == 400 and R["3_contrat"]["limit_0"] == 400, "limites hors bornes attendues en 400")
        print("contrat vérifié :", R["3_contrat"])

        # -------------------------------------------------------- 4. dates identiques
        step("4. Dates identiques (07_dates_identiques.sql, tel quel)")
        sql4 = open(os.path.join(KIT, "07_dates_identiques.sql"), encoding="utf-8").read()
        out4 = psql("", stdin=sql4, flags=("-A", "-t"))
        state["modifiees"] = True
        R["4_sortie_sql"] = out4
        print(out4)
        lignes = [l for l in out4.splitlines() if "|" in l]
        check([l.split("|")[0] for l in lignes][-3:] == ["2042", "1042", "42"] and len({l.split("|")[1] for l in lignes[-3:]}) == 1,
              "attendu : 2042, 1042, 42 avec la même date")
        e1 = sf("dates_p1", "/commandes?limit=2")
        cur2 = enc(e1["Body"]["nextCursor"])
        e2 = sf("dates_p2", f"/commandes?limit=2&cursor={cur2}")
        check(ids(e1) == ["2042", "1042"] and e1["Body"]["hasNextPage"] is True, f"page 1 des égalités : {ids(e1)}")
        check(ids(e2)[0] == "42" and len(ids(e2)) == 2, f"page 2 des égalités : {ids(e2)}")
        # ajout : même page par OFFSET
        e2o = sf("dates_p2_offset", "/commandes?limit=2&pagination=offset&offset=2")
        check(e2["Body"] == e2o["Body"], "égalités : curseur et OFFSET différents")
        # le défaut d'une condition limitée à la date (explication demandée)
        date_commune = psql("SELECT to_char(created_at AT TIME ZONE 'UTC','YYYY-MM-DD HH24:MI:SS.US') FROM shopflow.commandes WHERE id=1042")
        seul_date = psql(f"SELECT string_agg(id::text, ',' ORDER BY created_at DESC, id DESC) FROM (SELECT id, created_at FROM shopflow.commandes "
                         f"WHERE client_id=42 AND created_at < TIMESTAMPTZ '{date_commune}+00' ORDER BY created_at DESC, id DESC LIMIT 2) t")
        tuple_ = psql(f"SELECT string_agg(id::text, ',' ORDER BY created_at DESC, id DESC) FROM (SELECT id, created_at FROM shopflow.commandes "
                      f"WHERE client_id=42 AND (created_at,id) < (TIMESTAMPTZ '{date_commune}+00', 1042::bigint) ORDER BY created_at DESC, id DESC LIMIT 2) t")
        check("42" not in seul_date.split(",") and tuple_.split(",")[0] == "42", "démonstration du défaut de la comparaison sur la seule date")
        R["4_pages"] = {"page1": {"ids": ids(e1), "hasNextPage": e1["Body"]["hasNextPage"], "nextCursor": e1["Body"]["nextCursor"], "TraceId": e1["TraceId"]},
                        "page2": {"ids": ids(e2), "nextCursor": e2["Body"]["nextCursor"], "TraceId": e2["TraceId"]},
                        "page2_par_offset_identique": True, "date_commune": date_commune}
        R["4_defaut_date_seule"] = {"created_at_<_date_seule_page_suivante": seul_date, "tuple_(created_at,id)_page_suivante": tuple_}
        print("pages :", ids(e1), ids(e2), "| date seule :", seul_date, "| tuple :", tuple_)

        # -------------------------------------------------------- 5. parcours et droits
        step("5. Parcours des 5 pages, droits, restauration des dates")
        parcours, cursor, pages = [], "", 0
        while True:
            path = "/commandes?limit=20&relations=groupe" + (f"&cursor={enc(cursor)}" if cursor else "")
            pg = sf(f"parcours_{pages}", path)
            parcours += ids(pg)
            cursor = pg["Body"]["nextCursor"] or ""
            pages += 1
            if not cursor or pages >= 10:
                break
        attendu_bd = psql("SELECT string_agg(id::text, ',' ORDER BY created_at DESC, id DESC) FROM shopflow.commandes WHERE client_id=42").split(",")
        R["5_parcours"] = {"pages": pages, "total": len(parcours), "uniques": len(set(parcours)),
                           "meme_ordre_que_postgresql": parcours == attendu_bd,
                           "trois_egalites_une_fois": [parcours.count(x) for x in ("2042", "1042", "42")]}
        check((pages, len(parcours), len(set(parcours))) == (5, 100, 100) and parcours == attendu_bd, f"parcours : {R['5_parcours']}")
        print("parcours :", R["5_parcours"])
        R["5_droits"] = {"sans_jeton": code("/commandes", sans_jeton=True), "client_id_injecte": code("/commandes?client_id=43")}
        # ajout : curseur falsifié
        faux = p1["Body"]["nextCursor"][:-2] + ("AA" if not p1["Body"]["nextCursor"].endswith("AA") else "BB")
        R["5_droits"]["curseur_falsifie"] = code(f"/commandes?limit=20&cursor={enc(faux)}")
        R["5_droits"]["mode_inconnu"] = code("/commandes?pagination=inconnu")
        check((R["5_droits"]["sans_jeton"], R["5_droits"]["client_id_injecte"], R["5_droits"]["curseur_falsifie"]) == (401, 400, 400),
              f"droits : {R['5_droits']}")
        print("droits :", R["5_droits"])
        sql5 = open(os.path.join(KIT, "07_restaurer_dates.sql"), encoding="utf-8").read()
        out5 = psql("", stdin=sql5, flags=("-A", "-t"))
        R["5_sortie_restauration"] = out5
        print(out5)
        state["restaurees"] = True
        check(out5.splitlines()[0] == "3", "dates_restaurees = 3 attendu")
        # nettoyage de la table de sauvegarde créée par le script du kit (vide après la restauration)
        R["5_sauvegarde_vide"] = psql("SELECT count(*) FROM shopflow.sauvegarde_dates_atelier07") == "0"
        psql("DROP TABLE shopflow.sauvegarde_dates_atelier07")
    finally:
        if state["modifiees"] and not state["restaurees"]:  # filet de sécurité : ne jamais laisser les dates modifiées
            psql("", stdin=open(os.path.join(KIT, "07_restaurer_dates.sql"), encoding="utf-8").read(), flags=("-A", "-t"))
            print("Filet de sécurité : dates restaurées après un échec.")
        api.terminate()
        try:
            api.wait(timeout=10)
        except Exception:
            api.kill()
        logf.close()

    # ------------------------------------------------------------ état final
    step("Contrôle final du laboratoire")
    R["apres"] = lab_state()
    R["laboratoire_identique"] = R["avant"] == R["apres"]
    R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print("laboratoire identique :", R["laboratoire_identique"])
    check(R["laboratoire_identique"], "le laboratoire a changé : " + json.dumps({"avant": R["avant"], "apres": R["apres"]}))
    # extraits du journal de l'API par TraceId
    traces = {}
    for k in ("2_page20", "3_page2"):
        for m, v in R[k].items():
            if isinstance(v, dict) and "TraceId" in v:
                traces[f"{k}.{m}"] = v["TraceId"]
    traces["4_pages.page1"], traces["4_pages.page2"] = R["4_pages"]["page1"]["TraceId"], R["4_pages"]["page2"]["TraceId"]
    with open(os.path.join(OUT, "api_extraits_par_traceid.txt"), "w", encoding="utf-8") as f:
        lines = open(APILOG, encoding="utf-8").read().splitlines()
        for nom, t in traces.items():
            f.write(f"{nom} (TraceId {t})\n")
            for l in lines:
                if t in l:
                    f.write("  " + l + "\n")
    with open(os.path.join(OUT, "resultats_partie_a.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print("Résultats écrits dans", OUT)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # si le script s'arrête en cours de route, ne pas laisser les dates modifiées sans le dire
        print("\nÉCHEC. Vérifier l'état : dates de 42, 1042, 2042 et table shopflow.sauvegarde_dates_atelier07.", file=sys.stderr)
        raise
