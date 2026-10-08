#!/usr/bin/env python3
"""Atelier 8 : cache Redis et fraîcheur (Jour 4, slides 23 à 35 et fiche étudiant).

Rejoue la fiche étudiant du kit sur l'API ShopFlow (01_server/api, démarrée par ce script) avec le produit 42 et la clé
shopflow:produit:v1:42. PostgreSQL reste la source de vérité. Les appels HTTP passent par l'aide du kit (jour4_http.mjs : « sf »),
le journal de l'API (une ligne JSON par appel : sqlCount, sqlMs, durationMs) est rattaché aux appels par TraceId.

Écart volontaire avec la fiche : le TTL de 60 s est passé à l'API par variable d'environnement (Node donne la priorité à
l'environnement sur --env-file) au lieu de modifier .env, qui reste intact (empreinte vérifiée avant/après).

Ajouts de ma part (hors fiche, signalés) : 30 paires miss/hit mesurées, 30 appels pendant la panne de Redis, échec d'invalidation
(PATCH pendant la panne de Redis), reproduction manuelle de la course de la slide 30 (psql + redis-cli), stampede (20 lectures
simultanées, clé absente).

À la fin : prix restauré (57,50), Redis démarré, clé supprimée, API arrêtée ; le laboratoire est comparé à son état initial.

Usage : python3 atelier8/run_atelier8.py    (conteneurs api-postgres-1 et api-redis-1 démarrés ; environ 5 minutes)
"""
import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "01_server", "api")
KIT = os.path.join(ROOT, "Kit_Jour4_Windows_Linux", "02_Laboratoire", "Jour4")
HELPER = os.path.join(KIT, "jour4_http.mjs")
OUT = os.path.join(ROOT, "atelier8", "resultats")
os.makedirs(OUT, exist_ok=True)
CSV = os.path.join(OUT, "mesures_atelier8.csv")
APILOG = os.path.join(OUT, "api_journal.log")
PG, RD = "api-postgres-1", "api-redis-1"
KEY = "shopflow:produit:v1:42"
TTL = 60
R = {}


# ----------------------------------------------------------------------------- outils
def psql(sql):
    r = subprocess.run(["docker", "exec", "-i", PG, "psql", "-U", "cours", "-d", "shopflow", "-X", "-At", "-q", "-v", "ON_ERROR_STOP=1", "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("psql : " + r.stderr.strip())
    return r.stdout.strip()


def redis(*args):
    r = subprocess.run(["docker", "exec", RD, "redis-cli", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("redis-cli : " + r.stderr.strip())
    return r.stdout.strip()


def docker(*args):
    r = subprocess.run(["docker", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("docker : " + r.stderr.strip())
    return r.stdout.strip()


def lab_state():
    return {
        "index": psql("SELECT indexname FROM pg_indexes WHERE schemaname='shopflow' ORDER BY 1").split(),
        "statistiques_etendues": int(psql("SELECT count(*) FROM pg_statistic_ext")),
        "tables": psql("SELECT tablename FROM pg_tables WHERE schemaname='shopflow' ORDER BY 1").split(),
        "lignes": {t: int(psql(f"SELECT count(*) FROM shopflow.{t}")) for t in ("clients", "produits", "commandes", "lignes")},
        "md5_produits": psql("SELECT md5(string_agg(p::text, ',' ORDER BY id)) FROM shopflow.produits p")[:12],
        "md5_dates_commandes": psql("SELECT md5(string_agg(id||'|'||created_at::text, ',' ORDER BY id)) FROM shopflow.commandes")[:12],
        "produit42": psql("SELECT prix::text||' / stock '||stock FROM shopflow.produits WHERE id=42"),
        "cle_redis_presente": redis("EXISTS", KEY) == "1",
    }


def helper(*args):
    env = dict(os.environ, J4_CSV=CSV)
    r = subprocess.run(["node", HELPER, *args], cwd=API, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"helper {args[:2]} : {r.stderr.strip()}")
    return r.stdout.strip()


def journal(trace):
    for _ in range(40):
        with open(APILOG, encoding="utf-8") as f:
            for line in f:
                if trace in line and line.startswith("{"):
                    return json.loads(line)
        time.sleep(0.05)
    return None


def sf(label, path, method="GET", body=None):
    a = ["request", label, path, method] + ([body] if body is not None else [])
    res = json.loads(helper(*a))
    res["journal"] = journal(res["TraceId"])
    return res


def attendre_redis(etat):
    helper("wait", "true" if etat else "false")


def pick(res):
    d = {k: res[k] for k in ("Status", "Cache", "SqlCount", "HttpMs", "TraceId")}
    d["prix"] = (res["Body"].get("data") or {}).get("prix") if isinstance(res["Body"], dict) else None
    d["journal"] = res["journal"]
    return d


def med(v):
    return round(statistics.median(v), 3)


def p95(v):
    v = sorted(v)
    return round(v[math.ceil(0.95 * len(v)) - 1], 3)


def stats(vals):
    return {"tours": len(vals), "mediane": med(vals), "p95": p95(vals), "min": round(min(vals), 3), "max": round(max(vals), 3)}


def step(t):
    print(f"\n== {t}")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()[:12]


# ----------------------------------------------------------------------------- déroulement
def main():
    R["debut"] = time.strftime("%Y-%m-%d %H:%M:%S")
    R["node"] = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip()
    R["version_pg"] = psql("SELECT version()")
    R["redis_version"] = redis("INFO", "server").split("redis_version:")[1].split()[0]
    R["redis_politique"] = redis("CONFIG", "GET", "maxmemory-policy").split()[-1]
    R["redis_save"] = redis("CONFIG", "GET", "save").split("\n", 1)[-1]
    R["env_empreinte_avant"] = sha(os.path.join(API, ".env"))
    R["avant"] = lab_state()
    prix_depart = psql("SELECT prix::text FROM shopflow.produits WHERE id=42")
    state = {"api_demarree": False}
    check(len(R["avant"]["index"]) == 6 and R["avant"]["statistiques_etendues"] == 0 and not R["avant"]["cle_redis_presente"],
          "état initial inattendu : " + str(R["avant"]))
    print("état initial :", R["avant"])
    header = ["Date", "Label", "Method", "Path", "Status", "SqlCount", "Cache", "HttpMs", "TraceId", "Prix", "Ids"]
    with open(CSV, "w", encoding="utf-8") as f:
        f.write(",".join('"' + h + '"' for h in header) + "\n")
    open(APILOG, "w").close()
    logf = open(APILOG, "a", encoding="utf-8")
    env = dict(os.environ, CACHE_TTL_SECONDS=str(TTL))
    api = subprocess.Popen(["node", "--env-file=.env", "server.mjs"], cwd=API, stdout=logf, stderr=subprocess.STDOUT, env=env)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen("http://127.0.0.1:3000/", timeout=1)
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.25)
        # ------------------------------------------------------------ 1. préparation
        step("1. Préparation : TTL 60, prix initial, prix cible")
        attendre_redis(True)
        redis("DEL", KEY)
        initial = sf("prix_initial", "/produits/42")
        prix_initial = initial["Body"]["data"]["prix"]
        prix_cible = "24.90" if prix_initial == "19.90" else "19.90"
        ttl_apres_chargement = int(redis("TTL", KEY))
        check(prix_initial == prix_depart, "prix initial différent de PostgreSQL")
        check(0 < ttl_apres_chargement <= TTL and ttl_apres_chargement > 5, f"TTL de la clé = {ttl_apres_chargement} : le TTL de 60 s n'est pas pris en compte")
        R["1_preparation"] = {"prix_initial": prix_initial, "prix_cible_sql": prix_cible, "ttl_clef_apres_chargement": ttl_apres_chargement,
                              "premier_appel": pick(initial), "cle": KEY, "ttl_configure": TTL}
        print(f"prix initial {prix_initial}, cible {prix_cible}, TTL de la clé après chargement : {ttl_apres_chargement} s")

        # ------------------------------------------------------------ 2. miss / hit
        step("2. Chemins miss et hit")
        redis("DEL", KEY)
        miss = sf("cache_miss", "/produits/42")
        hit = sf("cache_hit", "/produits/42")
        check((miss["Status"], miss["Cache"], miss["SqlCount"]) == (200, "miss", 1), f"miss : {pick(miss)}")
        check((hit["Status"], hit["Cache"], hit["SqlCount"]) == (200, "hit", 0), f"hit : {pick(hit)}")
        check(miss["Body"]["data"] == hit["Body"]["data"], "les contenus data diffèrent")
        ttl_hit = int(redis("TTL", KEY))
        check(0 <= ttl_hit <= TTL, f"TTL = {ttl_hit}")
        R["2_miss_hit"] = {"miss": pick(miss), "hit": pick(hit), "data_identique": True, "ttl_apres": ttl_hit, "data": hit["Body"]["data"]}
        paires = []
        for i in range(1, 6):
            redis("DEL", KEY)
            m = sf(f"miss_{i}", "/produits/42")
            h = sf(f"hit_{i}", "/produits/42")
            check((m["Cache"], m["SqlCount"], h["Cache"], h["SqlCount"]) == ("miss", 1, "hit", 0), f"paire {i}")
            paires.append({"paire": i, "miss": pick(m), "hit": pick(h)})
        R["2_cinq_paires"] = paires
        print("miss 1 SELECT, hit 0 SQL ; 5 paires vérifiées ; TTL après :", ttl_hit)

        # ------------------------------------------------------------ 3. UPDATE SQL direct
        step("3. UPDATE SQL direct : la copie reste ancienne")
        redis("DEL", KEY)
        avant = sf("sql_avant", "/produits/42")
        sortie_update = psql(f"UPDATE shopflow.produits SET prix={prix_cible} WHERE id=42 RETURNING id,prix;")
        ancien = sf("sql_cache_ancien", "/produits/42")
        check(ancien["Cache"] == "hit" and ancien["SqlCount"] == 0 and ancien["Body"]["data"]["prix"] == prix_initial,
              f"après UPDATE direct : {pick(ancien)}")
        redis("DEL", KEY)
        nouveau = sf("sql_apres_del", "/produits/42")
        check(nouveau["Cache"] == "miss" and nouveau["SqlCount"] == 1 and nouveau["Body"]["data"]["prix"] == prix_cible,
              f"après DEL : {pick(nouveau)}")
        R["3_update_direct"] = {"avant": pick(avant), "sortie_update": sortie_update, "apres_update_avant_del": pick(ancien), "apres_del": pick(nouveau),
                                "postgres_prix": psql("SELECT prix::text FROM shopflow.produits WHERE id=42")}
        print(f"UPDATE -> {sortie_update} ; cache : {ancien['Body']['data']['prix']} (hit, 0 SQL) ; après DEL : {nouveau['Body']['data']['prix']} (miss)")

        # ------------------------------------------------------------ 4. PATCH
        step("4. PATCH par l'API : invalidation automatique")
        patch = sf("patch_prix", "/produits/42", "PATCH", '{"prix":"29.90"}')
        ap = sf("patch_miss", "/produits/42")
        hp = sf("patch_hit", "/produits/42")
        check(patch["Body"]["invalidation"] == "ok" and patch["Body"]["data"]["prix"] == "29.90" and patch["SqlCount"] == 1, f"PATCH : {patch['Body']}")
        check((ap["Cache"], ap["SqlCount"], ap["Body"]["data"]["prix"]) == ("miss", 1, "29.90"), f"GET après PATCH : {pick(ap)}")
        check((hp["Cache"], hp["SqlCount"], hp["Body"]["data"]["prix"]) == ("hit", 0, "29.90"), f"2e GET : {pick(hp)}")
        R["4_patch"] = {"patch": {"Status": patch["Status"], "SqlCount": patch["SqlCount"], "HttpMs": patch["HttpMs"], "TraceId": patch["TraceId"],
                                  "Body": patch["Body"], "journal": patch["journal"]},
                        "get_apres": pick(ap), "get_hit": pick(hp)}
        print("PATCH :", patch["Body"], "| GET :", ap["Cache"], hp["Cache"])

        # ------------------------------------------------------------ 5. expiration et panne
        step("5. Expiration (61 s) et panne de Redis")
        redis("DEL", KEY)
        charge = sf("ttl_chargement", "/produits/42")
        ttl1 = int(redis("TTL", KEY))
        check(charge["Cache"] == "miss" and 0 < ttl1 <= TTL, f"chargement : {pick(charge)} TTL {ttl1}")
        time.sleep(TTL + 1)
        ttl2 = int(redis("TTL", KEY))
        expire = sf("ttl_expire", "/produits/42")
        check(ttl2 == -2 and expire["Cache"] == "miss" and expire["SqlCount"] == 1 and expire["Body"]["data"]["prix"] == "29.90", f"expiration : TTL {ttl2} {pick(expire)}")
        R["5_expiration"] = {"charge": pick(charge), "ttl_apres_chargement": ttl1, "ttl_apres_attente": ttl2, "apres_expiration": pick(expire), "attente_s": TTL + 1}
        print(f"TTL {ttl1} -> {ttl2} ; relecture : {expire['Cache']}, {expire['SqlCount']} SELECT")

        docker("stop", RD)
        attendre_redis(False)
        panne = sf("redis_indisponible", "/produits/42")
        check(panne["Status"] == 200 and panne["Cache"] == "indisponible" and panne["SqlCount"] == 1 and panne["Body"]["data"]["prix"] == "29.90", f"panne : {pick(panne)}")
        R["5_panne"] = pick(panne)
        # ajout : 30 appels pendant la panne (repli sur PostgreSQL)
        for _ in range(5):
            sf("chauffe_panne", "/produits/42")
        rep_panne = {"http": [], "sql": [], "duree": []}
        for i in range(30):
            r = sf(f"repli_{i}", "/produits/42")
            check(r["Cache"] == "indisponible" and r["SqlCount"] == 1, "repli")
            rep_panne["http"].append(r["HttpMs"]); rep_panne["sql"].append(r["journal"]["sqlMs"]); rep_panne["duree"].append(r["journal"]["durationMs"])
        R["5_repli_30"] = {"http": stats(rep_panne["http"]), "sqlMs": stats(rep_panne["sql"]), "durationMs": stats(rep_panne["duree"]), "http_brut": rep_panne["http"]}
        print("panne :", panne["Cache"], "| repli 30 appels HttpMs médiane", R["5_repli_30"]["http"]["mediane"])

        # ------------------------------------------------------------ ajout : échec d'invalidation (Redis arrêté pendant un PATCH)
        step("Ajout : PATCH pendant la panne de Redis (invalidation échouée)")
        docker("start", RD)
        attendre_redis(True)
        redis("DEL", KEY)
        copie = sf("copie_avant_panne", "/produits/42")      # la copie (29.90) est dans Redis
        check(copie["Cache"] == "miss" and redis("EXISTS", KEY) == "1", "copie absente avant la panne")
        docker("stop", RD)
        attendre_redis(False)
        patch_panne = sf("patch_redis_arrete", "/produits/42", "PATCH", '{"prix":"34.90"}')
        pg_apres = psql("SELECT prix::text FROM shopflow.produits WHERE id=42")
        check(patch_panne["Body"]["invalidation"] == "echouee" and pg_apres == "34.90", f"PATCH en panne : {patch_panne['Body']} / PG {pg_apres}")
        docker("start", RD)
        attendre_redis(True)
        cle_survit = redis("EXISTS", KEY) == "1"
        relecture = sf("relecture_apres_retour", "/produits/42")
        R["ajout_invalidation_echouee"] = {"patch": {"Body": patch_panne["Body"], "SqlCount": patch_panne["SqlCount"], "TraceId": patch_panne["TraceId"]},
                                          "postgres_prix_apres_patch": pg_apres, "cle_redis_survit_au_redemarrage": cle_survit,
                                          "relecture": pick(relecture), "copie_ancienne_servie": relecture["Cache"] == "hit" and relecture["Body"]["data"]["prix"] == "29.90"}
        print(f"invalidation={patch_panne['Body']['invalidation']}, PostgreSQL={pg_apres}, clé survit={cle_survit}, relecture={relecture['Cache']} {relecture['Body']['data']['prix']}")

        # ------------------------------------------------------------ ajout : course de la slide 30 (reproduction manuelle)
        step("Ajout : course entre lecture et invalidation (slide 30)")
        redis("DEL", KEY)
        prix_a = psql("SELECT prix::text FROM shopflow.produits WHERE id=42")                     # t1 : A lit l'ancienne valeur dans PostgreSQL
        copie_a = psql("SELECT json_build_object('id',id::text,'nom',nom,'prix',prix::text,'stock',stock,'attributs',attributs)::text FROM shopflow.produits WHERE id=42")
        psql("UPDATE shopflow.produits SET prix=39.90 WHERE id=42")                                 # t2 : B valide la nouvelle valeur
        redis("DEL", KEY)                                                                           # t3 : B invalide la clé
        redis("SET", KEY, copie_a, "EX", str(TTL))                                                  # t4 : A remet l'ancienne copie
        course = sf("course_apres_t4", "/produits/42")
        pg_prix = psql("SELECT prix::text FROM shopflow.produits WHERE id=42")
        check(course["Cache"] == "hit" and course["Body"]["data"]["prix"] == prix_a and pg_prix == "39.90", f"course : {pick(course)} PG {pg_prix}")
        R["ajout_course"] = {"t1_A_lit": prix_a, "t2_B_ecrit": "39.90", "t3_B_supprime_la_cle": True, "t4_A_remet_la_copie": prix_a,
                             "api_apres": pick(course), "postgres_apres": pg_prix}
        print(f"A avait lu {prix_a} ; PostgreSQL {pg_prix} ; l'API sert {course['Body']['data']['prix']} ({course['Cache']})")
        redis("DEL", KEY)

        # ------------------------------------------------------------ ajout : stampede
        step("Ajout : stampede (20 lectures simultanées, clé absente)")
        redis("DEL", KEY)
        burst = json.loads(subprocess.run(["node", os.path.join(ROOT, "atelier8", "stampede.mjs"), "20"], capture_output=True, text=True, check=True).stdout)
        burst2 = json.loads(subprocess.run(["node", os.path.join(ROOT, "atelier8", "stampede.mjs"), "20"], capture_output=True, text=True, check=True).stdout)
        R["ajout_stampede"] = {"rafale_cle_absente": {"requetes": len(burst), "miss": sum(1 for b in burst if b["cache"] == "miss"), "hit": sum(1 for b in burst if b["cache"] == "hit"),
                                                       "select_total": sum(b["sql"] for b in burst), "statuts": sorted({b["status"] for b in burst}),
                                                       "ms_mediane": med([b["ms"] for b in burst]), "ms_max": max(b["ms"] for b in burst)},
                               "rafale_cle_presente": {"requetes": len(burst2), "miss": sum(1 for b in burst2 if b["cache"] == "miss"), "hit": sum(1 for b in burst2 if b["cache"] == "hit"),
                                                       "select_total": sum(b["sql"] for b in burst2), "ms_mediane": med([b["ms"] for b in burst2])}}
        print("stampede :", R["ajout_stampede"])

        # ------------------------------------------------------------ ajout : 30 paires miss / hit
        step("Ajout : 30 paires miss / hit (mesures)")
        for _ in range(5):
            redis("DEL", KEY); sf("chauffe_m", "/produits/42"); sf("chauffe_h", "/produits/42")
        mv = {"http": [], "sql": [], "duree": []}; hv = {"http": [], "sql": [], "duree": []}
        for i in range(30):
            redis("DEL", KEY)
            m = sf(f"mesure_miss_{i}", "/produits/42")
            h = sf(f"mesure_hit_{i}", "/produits/42")
            check((m["Cache"], m["SqlCount"], h["Cache"], h["SqlCount"]) == ("miss", 1, "hit", 0), "paire de mesure")
            for dct, r in ((mv, m), (hv, h)):
                dct["http"].append(r["HttpMs"]); dct["sql"].append(r["journal"]["sqlMs"]); dct["duree"].append(r["journal"]["durationMs"])
        R["ajout_30_paires"] = {"miss": {"http": stats(mv["http"]), "sqlMs": stats(mv["sql"]), "durationMs": stats(mv["duree"]), "http_brut": mv["http"]},
                                "hit": {"http": stats(hv["http"]), "sqlMs": stats(hv["sql"]), "durationMs": stats(hv["duree"]), "http_brut": hv["http"]}}
        print("HttpMs médiane : miss", R["ajout_30_paires"]["miss"]["http"]["mediane"], "/ hit", R["ajout_30_paires"]["hit"]["http"]["mediane"],
              "| durationMs : miss", R["ajout_30_paires"]["miss"]["durationMs"]["mediane"], "/ hit", R["ajout_30_paires"]["hit"]["durationMs"]["mediane"])

        # ------------------------------------------------------------ 6. restauration
        step("6. Restauration du prix initial")
        docker("start", RD) if redis_arrete() else None
        attendre_redis(True)
        retour = sf("restauration_prix", "/produits/42", "PATCH", json.dumps({"prix": prix_initial}))
        controle = sf("prix_restaure", "/produits/42")
        check(controle["Body"]["data"]["prix"] == prix_initial and retour["Body"]["invalidation"] == "ok", f"restauration : {retour['Body']} / {pick(controle)}")
        redis("DEL", KEY)
        R["6_restauration"] = {"patch": {"Body": retour["Body"], "TraceId": retour["TraceId"]}, "controle": pick(controle), "message": "Prix restauré"}
        print("Prix restauré :", controle["Body"]["data"]["prix"], "| invalidation :", retour["Body"]["invalidation"])
    finally:
        # filet de sécurité : Redis démarré, prix restauré, clé supprimée, API arrêtée
        try:
            if redis_arrete():
                docker("start", RD)
                time.sleep(2)
            if psql("SELECT prix::text FROM shopflow.produits WHERE id=42") != prix_depart:
                psql(f"UPDATE shopflow.produits SET prix={prix_depart} WHERE id=42")
                print("Filet de sécurité : prix restauré par SQL.")
            redis("DEL", KEY)
        except Exception as e:  # noqa
            print("Filet de sécurité : échec :", e, file=sys.stderr)
        api.terminate()
        try:
            api.wait(timeout=10)
        except Exception:
            api.kill()
        logf.close()

    step("Contrôle final")
    R["apres"] = lab_state()
    R["env_empreinte_apres"] = sha(os.path.join(API, ".env"))
    R["env_inchange"] = R["env_empreinte_avant"] == R["env_empreinte_apres"]
    R["redis_demarre"] = not redis_arrete()
    R["laboratoire_identique"] = R["avant"] == R["apres"]
    R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
    print("laboratoire identique :", R["laboratoire_identique"], "| .env inchangé :", R["env_inchange"], "| Redis démarré :", R["redis_demarre"])
    check(R["laboratoire_identique"] and R["env_inchange"] and R["redis_demarre"], "état final inattendu : " + json.dumps({"avant": R["avant"], "apres": R["apres"]}))
    traces = {}
    for nom, d in (("2_miss", R["2_miss_hit"]["miss"]), ("2_hit", R["2_miss_hit"]["hit"]), ("3_apres_update_direct", R["3_update_direct"]["apres_update_avant_del"]),
                   ("3_apres_del", R["3_update_direct"]["apres_del"]), ("4_patch", R["4_patch"]["patch"]), ("4_get_miss", R["4_patch"]["get_apres"]),
                   ("4_get_hit", R["4_patch"]["get_hit"]), ("5_apres_expiration", R["5_expiration"]["apres_expiration"]), ("5_panne", R["5_panne"]),
                   ("ajout_patch_en_panne", R["ajout_invalidation_echouee"]["patch"]), ("ajout_course", R["ajout_course"]["api_apres"])):
        traces[nom] = d["TraceId"]
    with open(os.path.join(OUT, "api_extraits_par_traceid.txt"), "w", encoding="utf-8") as f:
        lines = open(APILOG, encoding="utf-8").read().splitlines()
        for nom, t in traces.items():
            f.write(f"{nom} (TraceId {t})\n")
            for l in lines:
                if t in l:
                    f.write("  " + l + "\n")
    with open(os.path.join(OUT, "resultats_atelier8.json"), "w", encoding="utf-8") as f:
        json.dump(R, f, ensure_ascii=False, indent=2)
    print("Résultats écrits dans", OUT)


def redis_arrete():
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", RD], capture_output=True, text=True)
    return r.stdout.strip() != "true"


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nÉCHEC. Vérifier : prix du produit 42, clé Redis, conteneur api-redis-1.", file=sys.stderr)
        raise
