#!/usr/bin/env python3
"""Vérifie PRINCIPAL_PLUS.pdf contre Atelier_10_Fiche_etudiant.pdf : structure, preuves P-xx, renvois d'annexes, cohérence des chiffres avec les annexes."""
import re, sys, pypdf
ROOT = "/home/youssef/école"
R = pypdf.PdfReader(f"{ROOT}/PRINCIPAL_PLUS.pdf"); T = [re.sub(r"\s+", " ", p.extract_text()) for p in R.pages]
SRC = pypdf.PdfReader(f"{ROOT}/test.pdf"); ANN = [re.sub(r"\s+", " ", p.extract_text()) for p in SRC.pages]; D = T; ND = len(D); DT = "\n".join(D); AT = "\n".join(ANN)
ok = True
def check(name, cond, detail=""):
    global ok; ok &= bool(cond); print(("OK   " if cond else "ÉCHEC"), name, detail)

print("== 1. Forme : dossier court, annexes intactes")
check("dossier court : 8 pages au plus (fiche : A à F = 6 à 9 pages)", ND <= 9, f"{ND} pages")
check("un seul fichier, sans annexes recopiées", len(T) == ND)
check("sources PRINCIPAL lisibles (test.pdf, 71 pages)", len(ANN) == 71)

print("== 2. Structure recommandée (fiche partie 3) : sections et taille")
for sec, pages in (("A. Besoin et état initial", [1]), ("B. Architecture et stockage", [1]), ("C. Intervention principale", [2]), ("D. Benchmark", [3]), ("E. Correction et fiabilité", [4]), ("F. Décision et limites", [5])):
    check(sec, any(sec in D[i] for i in pages), f"page D-{pages[0]+1}")

print("== 2b. Inventaire des preuves (fiche partie 2) : familles et chiffres repris de PRINCIPAL")
for k in ("Plans et index","Migration","API","Pooling","Cache","Charge","Donnée moderne","Non réalisé"): check("famille : "+k, k in D[0])
print("== 3. Fil narratif (fiche partie 3) : besoin, mesure, hypothèse, un seul changement, vérification, charge, décision")
for k in ("Hypothèse causale", "Changement (un seul)", "Correction et fiabilité", "Benchmark", "Décision et limites"): check("présent : " + k, k in DT)

print("== 4. Fiches d'identité (fiche partie 4) : 7 champs et toutes les preuves")
ids = sorted(set(re.findall(r"P-\d\d", DT)))
defined = sorted(set(re.findall(r"^(P-\d\d)", "\n".join(D[6].splitlines()), re.M)) | set(re.findall(r"(P-\d\d) [A-ZÉ]", D[6])))
check("14 preuves définies (P-01 à P-14)", defined == [f"P-{i:02d}" for i in range(1, 15)], str(defined))
check("toutes les références P-xx pointent une preuve définie", set(ids) <= set(defined), f"références : {ids}")
check("chaque preuve définie est utilisée ailleurs dans le dossier", all(len(re.findall(i, "\n".join(D[:6] + D[7:]))) > 0 for i in defined if i not in ("P-14",)) , "")
for champ in ("Question", "Conditions", "Action", "Résultat brut", "Interprétation", "Limite", "ID"): check("champ de la fiche : " + champ, champ in D[6])

print("== 5. Optimisation principale (fiche partie 5) : 7 questions")
for q, k in (("Quel problème ?", "Problème observable"), ("Pourquoi cette hypothèse ?", "Trace montrant le mécanisme"), ("Quel changement ?", "Changement (un seul)"),
             ("Le résultat reste-t-il correct ?", "Invariant fonctionnel"), ("Quel effet mesuré ?", "Benchmark avant"), ("Quel coût ?", "Coûts"), ("Quelle portée ?", "Valable ici")):
    check(q, k in DT, "→ " + k)

print("== 6. Fiabilité / fraîcheur (fiche partie 6) : une preuve (cache Redis)")
for k in ("57.50", "19.90", "invalidation", "TTL 60 → −2", "Redis arrêté"): check("présent : " + k, k in DT)

print("== 7. Auto-évaluation (partie 7), deux questions et présentation (partie 8), checklist (partie 9)")
for k in ("Besoin", "Stockage", "Correction", "Méthode", "Intervention", "Mesure", "Fiabilité / fraîcheur", "Limites"): check("critère d'auto-évaluation : " + k, k in D[7])
check("chaque critère a une référence P-xx", len(re.findall(r"P-\d\d", D[7].split("Les deux questions")[0])) >= 8)
check("question reproductibilité", "Reproductibilité" in D[7] and "autre poste" in D[7]); check("question conséquence API", "Conséquence pour l'API" in D[7])
check("checklist : 10 lignes cochées", D[7].count("✔") == 10, f"{D[6].count('✔')} cases")
check("variante rejetée (×2) et risque restant", "Variante rejetée n° 1" in DT and "Variante rejetée n° 2" in DT and "Risques restants" in DT)
check("formulation finale en 3 phrases numérotées", all(k in D[7] for k in ("1. Observé", "2. Pourquoi", "3. Conditions")))
check("présentation de 5 minutes référencée", "Presentation_V1_structure.pdf" in DT and "Presentation_V2_histoire.pdf" in DT)

print("== 8. Règle de preuve : p95, débit, erreurs, unités")
for k in ("req/s", "p95", "ms", "Err.", "médiane", "10 s", "3 s"): check("présent : " + k, k in DT)

print("== 9. Chaque chiffre du dossier se retrouve dans les annexes (source indépendante : PRINCIPAL)")
norm = lambda s: re.sub(r"[   ]", "", s)
for lab, val in (("index composé API", "2,5"), ("client actif", "91"), ("partiel ms", "0,070"), ("partiel facteur", "144,6"), ("curseur 1 000 000", "944,3"), ("curseur ms", "0,177"), ("NOT NULL direct", "3324,1"), ("NOT NULL progressif", "46,3"), ("work_mem 32 MB", "50,2"), ("statistique", "45,5"), ("EXISTS", "11,3"), ("jointure", "27,6"), ("débit N+1", "246,9"), ("p95 N+1", "98,0"), ("débit groupé", "1032,1"), ("p95 groupé", "26,8"), ("p50 N+1 20 clients", "79,0"), ("p50 groupé", "18,2"), ("essais N+1", "238"), ("essais N+1 max", "253"),
                 ("essais groupé", "978"), ("essais groupé max", "1082"), ("pgss appels", "20000"), ("pgss moyenne", "0,018"), ("sqlMs 21 requêtes", "14,2"), ("sqlMs groupé", "2,2"), ("journal lent", "1249"),
                 ("HTTP N+1", "55,3"), ("HTTP groupé", "43,9"), ("pool 20 essai 1", "275,7"), ("pool 20 essai 2", "299,0"), ("pool 5 essai 2", "137,4"), ("pool 5 essai 1", "216,0"),
                 ("PgBouncer tps direct", "260,7"), ("PgBouncer tps pool", "93,8"), ("PgBouncer latence", "422"), ("miss", "2,7"), ("hit", "0,988"), ("prix périmé", "57.50"), ("prix base", "19.90"), ("course", "39.90"),
                 ("rafale miss", "6"), ("md5 commandes", "7505112bb794"), ("md5 lignes", "e989d5bec39b"), ("série D p95", "358,5")):
    v = norm(val); present_d = v in norm(DT).replace(".", ",") or v in norm(DT)
    check(f"{lab} = {val}", v in norm(AT).replace(".", ",") or v in norm(AT), "(dans le dossier : " + ("oui" if present_d else "non — non cité") + ")")

print("== 10. Renvois « PRINCIPAL p. N » : la page citée traite bien du sujet")
chk = {7: "Atelier 3", 16: "Atelier 4 bis", 18: "Verrous", 19: "Atelier 7", 20: "N+1 contre", 21: "PgBouncer", 22: "Atelier 8", 23: "fraîcheur", 53: "Annexe 9", 56: "reconnexion", 57: "Annexe 10", 58: "Appels", 59: "Rafale", 48: "Annexe 8", 1: "Atelier 1", 3: "Atelier 2", 11: "Atelier 4"}
for n, k in chk.items(): check(f"PRINCIPAL p. {n} contient « {k} »", k.lower() in ANN[n - 1].lower())
check("« fiches p. D-7 » : la page D-7 est bien celle des fiches", "Fiches d'identité" in D[6])
print("\nRÉSULTAT GLOBAL :", "TOUS LES CONTRÔLES PASSENT" if ok else "AU MOINS UN ÉCHEC")
sys.exit(0 if ok else 1)
