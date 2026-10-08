"""Outils communs de l'atelier 9 (Jour 5) : sessions psql persistantes (sentinelle sur stdout ET stderr), mesures, machine."""
import json
import math
import os
import re
import statistics
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "atelier9", "resultats")
os.makedirs(OUT, exist_ok=True)
LAB = "api-postgres-1"      # laboratoire ShopFlow (jamais modifié par l'atelier 9)
COPIE = "a9-pg"             # copie jetable : même image, mêmes données (md5 vérifiés), pg_stat_statements actif
SENT = "__FIN__"


class Sess:
    def __init__(self, name, container=COPIE, db="shopflow"):
        self.name = name
        self.p = subprocess.Popen(["docker", "exec", "-i", "-e", f"PGAPPNAME={name}", container, "psql", "-U", "cours", "-d", db, "-X", "-q"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

    def send(self, sql):
        self.p.stdin.write(sql.rstrip() + f"\n\\echo {SENT}\n\\warn {SENT}\n")
        self.p.stdin.flush()
        lines, vues = [], 0
        while vues < 2:
            line = self.p.stdout.readline()
            if line == "":
                raise RuntimeError(f"[{self.name}] psql arrêté")
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


def q(sql, container=COPIE, flags=("-At",)):
    r = subprocess.run(["docker", "exec", "-i", container, "psql", "-U", "cours", "-d", "shopflow", "-X", "-q", "-v", "ON_ERROR_STOP=1", *flags, "-c", sql],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("psql : " + r.stderr.strip())
    return r.stdout.strip()


def med(v):
    return round(statistics.median(v), 3)


def pct(v, p):
    s = sorted(v)
    return round(s[min(len(s) - 1, math.ceil(p / 100 * len(s)) - 1)], 3)


def machine():
    cpu = subprocess.run(["bash", "-c", "grep -m1 'model name' /proc/cpuinfo | cut -d: -f2"], capture_output=True, text=True).stdout.strip()
    mem = subprocess.run(["bash", "-c", "free -m | awk 'NR==2{print $2}'"], capture_output=True, text=True).stdout.strip()
    return {"cpu": cpu, "coeurs": os.cpu_count(), "memoire_mo": int(mem or 0), "noyau": subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()}


def save(name, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
