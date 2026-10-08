#!/usr/bin/env python3
"""Atelier 8, ajout : miss contre hit mesurés avec UNE connexion HTTP persistante (keep-alive).

L'aide du kit lance un processus Node par appel : son coût fixe (≈ 40 ms) noie la différence entre hit et miss dans HttpMs.
Ici une seule connexion HTTP est réutilisée (http.client) : on voit la durée réelle de la requête, et le journal de l'API
(durationMs, sqlMs, rattaché par X-Trace-Id) donne le temps passé dans l'API.
100 paires miss/hit (clé supprimée avant chaque paire), après 5 paires d'échauffement. Le prix n'est jamais modifié.

Usage : python3 atelier8/mesure_persistante.py      (environ 1 minute)
"""
import http.client
import json
import math
import os
import statistics
import subprocess
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = os.path.join(ROOT, "01_server", "api")
OUT = os.path.join(ROOT, "atelier8", "resultats")
LOG = os.path.join(OUT, "api_journal_persistante.log")
KEY = "shopflow:produit:v1:42"
env_file = {}
for line in open(os.path.join(API, ".env"), encoding="utf-8"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        env_file[k] = v
TOKEN, PORT = env_file["LAB_TOKEN"], int(env_file.get("PORT", 3000))


def redis(*a):
    return subprocess.run(["docker", "exec", "api-redis-1", "redis-cli", *a], capture_output=True, text=True).stdout.strip()


def stats(v):
    s = sorted(v)
    return {"tours": len(v), "mediane": round(statistics.median(v), 3), "p95": round(s[math.ceil(0.95 * len(s)) - 1], 3), "min": round(min(v), 3), "max": round(max(v), 3)}


def main():
    prix = subprocess.run(["docker", "exec", "api-postgres-1", "psql", "-U", "cours", "-d", "shopflow", "-Atc", "SELECT prix::text FROM shopflow.produits WHERE id=42"], capture_output=True, text=True).stdout.strip()
    open(LOG, "w").close()
    logf = open(LOG, "a", encoding="utf-8")
    api = subprocess.Popen(["node", "--env-file=.env", "server.mjs"], cwd=API, stdout=logf, stderr=subprocess.STDOUT, env=dict(os.environ, CACHE_TTL_SECONDS="60"))
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=1)
            except urllib.error.HTTPError:
                break
            except Exception:
                time.sleep(0.25)
        conn = http.client.HTTPConnection("127.0.0.1", PORT)

        def get():
            t = time.perf_counter()
            conn.request("GET", "/produits/42", headers={"Authorization": f"Bearer {TOKEN}"})
            r = conn.getresponse()
            body = r.read()
            ms = (time.perf_counter() - t) * 1000
            return {"ms": ms, "cache": r.getheader("X-Cache"), "sql": int(r.getheader("X-SQL-Count")), "trace": r.getheader("X-Trace-Id"), "prix": json.loads(body)["data"]["prix"]}

        for _ in range(5):
            redis("DEL", KEY); get(); get()
        res = {"miss": [], "hit": []}
        for _ in range(100):
            redis("DEL", KEY)
            m, h = get(), get()
            assert (m["cache"], m["sql"], h["cache"], h["sql"]) == ("miss", 1, "hit", 0) and m["prix"] == h["prix"] == prix
            res["miss"].append(m); res["hit"].append(h)
        time.sleep(0.3)
        lines = {}
        for l in open(LOG, encoding="utf-8"):
            if l.startswith("{"):
                d = json.loads(l); lines[d["trace"]] = d
        out = {"prix_produit": prix, "paires": 100}
        for k in ("miss", "hit"):
            out[k] = {"http_ms": stats([x["ms"] for x in res[k]]), "durationMs_api": stats([lines[x["trace"]]["durationMs"] for x in res[k]]),
                      "sqlMs_api": stats([lines[x["trace"]]["sqlMs"] for x in res[k]]), "http_brut": [round(x["ms"], 3) for x in res[k]]}
        out["rapport_http_mediane"] = round(out["miss"]["http_ms"]["mediane"] / out["hit"]["http_ms"]["mediane"], 2)
        out["rapport_api_mediane"] = round(out["miss"]["durationMs_api"]["mediane"] / out["hit"]["durationMs_api"]["mediane"], 2)
        out["date"] = time.strftime("%Y-%m-%d %H:%M:%S")
        out["prix_inchange"] = subprocess.run(["docker", "exec", "api-postgres-1", "psql", "-U", "cours", "-d", "shopflow", "-Atc", "SELECT prix::text FROM shopflow.produits WHERE id=42"], capture_output=True, text=True).stdout.strip() == prix
        json.dump(out, open(os.path.join(OUT, "mesure_persistante.json"), "w"), ensure_ascii=False, indent=2)
        print(json.dumps({k: (v if k not in ("miss", "hit") else {a: b for a, b in v.items() if a != "http_brut"}) for k, v in out.items()}, ensure_ascii=False, indent=1))
    finally:
        redis("DEL", KEY)
        api.terminate()
        try:
            api.wait(timeout=10)
        except Exception:
            api.kill()
        logf.close()


if __name__ == "__main__":
    main()
