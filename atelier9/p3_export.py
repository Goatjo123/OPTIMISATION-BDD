#!/usr/bin/env python3
"""Jour 5, slides 24 à 29 : export minimal vers l'analytique et contrat de données.

Exécute la requête de la slide 28 (lecture seule) sur le laboratoire, écrit le CSV (atelier9/export/commandes_journalieres.csv) et vérifie le contrat :
granularité (une ligne par jour UTC), invariants (somme des nb_commandes = commandes payées ; somme des montants = somme de commandes.total des payées),
reproductibilité (deux exécutions, même empreinte), piège de la jointure aux lignes (montant multiplié), règle de fuseau (jour UTC contre jour Paris),
et correction d'une journée déjà publiée (sur la copie jetable, dans une transaction annulée).
Usage : python3 atelier9/p3_export.py (quelques secondes)."""
import csv, hashlib, io, os, subprocess, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

EXPORT = ("SELECT (created_at AT TIME ZONE 'UTC')::date AS jour, count(*) AS nb_commandes, sum(total) AS montant FROM shopflow.commandes "
          "WHERE statut = 'payee' GROUP BY 1 ORDER BY 1")


def copy_csv():
    r = subprocess.run(["docker", "exec", "-i", LAB, "psql", "-U", "cours", "-d", "shopflow", "-X", "-q", "-c", f"COPY ({EXPORT}) TO STDOUT WITH CSV HEADER"], capture_output=True, text=True, check=True)
    return r.stdout


R = {"debut": time.strftime("%Y-%m-%d %H:%M:%S"), "requete": EXPORT}
os.makedirs(os.path.join(ROOT, "atelier9", "export"), exist_ok=True)
c1, c2 = copy_csv(), copy_csv()
open(os.path.join(ROOT, "atelier9", "export", "commandes_journalieres.csv"), "w", encoding="utf-8", newline="").write(c1)
rows = list(csv.DictReader(io.StringIO(c1)))
R["lignes_export"] = len(rows)
R["premier_jour"], R["dernier_jour"] = rows[0]["jour"], rows[-1]["jour"]
R["md5_export_1"], R["md5_export_2"] = hashlib.md5(c1.encode()).hexdigest()[:12], hashlib.md5(c2.encode()).hexdigest()[:12]
R["reproductible"] = c1 == c2
R["jours_distincts"] = len({r["jour"] for r in rows})
R["somme_nb_commandes"] = sum(int(r["nb_commandes"]) for r in rows)
R["somme_montant_csv"] = str(sum(__import__("decimal").Decimal(r["montant"]) for r in rows))
R["commandes_payees_table"] = int(q("SELECT count(*) FROM shopflow.commandes WHERE statut='payee'", container=LAB))
R["somme_total_payees_table"] = q("SELECT sum(total) FROM shopflow.commandes WHERE statut='payee'", container=LAB)
R["invariant_nb"] = R["somme_nb_commandes"] == R["commandes_payees_table"]
R["invariant_montant"] = R["somme_montant_csv"] == R["somme_total_payees_table"]
R["valeurs_nulles_ou_negatives"] = sum(1 for r in rows if not r["montant"] or float(r["montant"]) <= 0)
R["statuts"] = q("SELECT statut||' '||count(*) FROM shopflow.commandes GROUP BY statut ORDER BY 1", container=LAB).splitlines()
R["date_max_commande"] = q("SELECT max(created_at)::text FROM shopflow.commandes", container=LAB)
R["date_min_commande"] = q("SELECT min(created_at)::text FROM shopflow.commandes", container=LAB)
# piège : jointure aux lignes avant l'agrégation
R["somme_montant_avec_jointure_lignes"] = q("SELECT sum(c.total) FROM shopflow.commandes c JOIN shopflow.lignes l ON l.commande_id=c.id WHERE c.statut='payee'", container=LAB)
R["nb_commandes_avec_jointure_lignes"] = int(q("SELECT count(*) FROM shopflow.commandes c JOIN shopflow.lignes l ON l.commande_id=c.id WHERE c.statut='payee'", container=LAB))
# fuseau
R["commandes_jour_UTC_different_jour_Paris"] = int(q("SELECT count(*) FROM shopflow.commandes WHERE statut='payee' AND (created_at AT TIME ZONE 'UTC')::date <> (created_at AT TIME ZONE 'Europe/Paris')::date", container=LAB))
# plan de la requête d'export (lecture seule)
plan = q("EXPLAIN (ANALYZE, BUFFERS) " + EXPORT, container=LAB)
R["plan_export"] = plan.splitlines()
# correction d'une journée déjà publiée : copie jetable, transaction annulée
S = Sess("corr")
S.send("BEGIN;")
jour = rows[len(rows) // 2]["jour"]    # une journée déjà publiée ; une de ses commandes payées est annulée APRÈS publication
cid = [l.strip() for l in S.send(f"SELECT id FROM shopflow.commandes WHERE statut='payee' AND (created_at AT TIME ZONE 'UTC')::date = DATE '{jour}' ORDER BY id LIMIT 1;").splitlines() if l.strip().isdigit()][0]
fmt_jour = lambda out: [l.strip() for l in out.strip().splitlines() if "/" in l]
sel = f"SELECT nb_commandes||' / '||montant FROM ({EXPORT}) e WHERE jour = DATE '{jour}';"
avant = fmt_jour(S.send(sel))
S.send(f"UPDATE shopflow.commandes SET statut='annulee' WHERE id={cid};")
apres = fmt_jour(S.send(sel))
S.send("ROLLBACK;")
rev = fmt_jour(S.send(sel)); S.close()
R["correction_jour"] = {"jour": jour, "commande_modifiee": cid, "avant": avant, "apres_annulation_tardive": apres, "apres_rollback": rev}
R["fin"] = time.strftime("%Y-%m-%d %H:%M:%S")
save("p3_export.json", R)
print({k: v for k, v in R.items() if k not in ("plan_export", "requete")})
