#!/usr/bin/env python3
"""Audit de la règle de preuve (fiche Atelier 10) : chaque nombre du dossier doit se retrouver dans une source réelle
(fichiers de mesures atelier*/resultats, README, ou texte de test.pdf = PRINCIPAL + chapitre Jour 5), ou être un calcul
vérifié (facteur, pourcentage). Les nombres non retrouvés sont listés pour contrôle manuel.
Usage : python3 dossier/audit_chiffres.py [dossier.pdf]"""
import glob, json, os, re, sys
import pypdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "PRINCIPAL_PLUS_complet.pdf")  # D-1 à D-8 = pages 3 à 10
NUM = re.compile(r"\d{1,3}(?:[   ]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?")


def val(tok):
    return float(re.sub(r"[   ]", "", tok).replace(",", "."))


def nums(text):
    return {val(t) for t in NUM.findall(text)}


def leaves(o, out):
    if isinstance(o, dict):
        for v in o.values(): leaves(v, out)
    elif isinstance(o, list):
        for v in o: leaves(v, out)
    elif isinstance(o, bool) or o is None:
        pass
    elif isinstance(o, (int, float)):
        out.add(float(o))
    else:
        out.update(nums(str(o)))


src = set()
for f in glob.glob(os.path.join(ROOT, "atelier*/resultats/**/*"), recursive=True):
    if os.path.isfile(f) and f.endswith((".json", ".log", ".txt", ".csv")):
        txt = open(f, encoding="utf-8", errors="ignore").read()
        if f.endswith(".json"):
            leaves(json.loads(txt), src)
        src |= nums(txt)
for f in glob.glob(os.path.join(ROOT, "atelier*/README*")) + glob.glob(os.path.join(ROOT, "atelier*/*.py")):
    src |= nums(open(f, encoding="utf-8", errors="ignore").read())
for p in pypdf.PdfReader(os.path.join(ROOT, "test.pdf")).pages:
    src |= nums(p.extract_text())


def decimals(tok):
    m = re.search(r"[.,](\d+)$", tok)
    return len(m.group(1)) if m else 0


def found(tok):
    v, d = val(tok), decimals(tok)
    return any(abs(round(s, d) - v) < 1e-9 or abs(s - v) < 1e-9 for s in src)


reader = pypdf.PdfReader(PDF)
PAGES = reader.pages[2:10]
ANNEXE = set()
for p in pypdf.PdfReader(os.path.join(ROOT, "test.pdf")).pages:
    ANNEXE |= nums(p.extract_text())
STRIP = r"\bP-\d+\b|\bD-\d+\b|PRINCIPAL p\.? ?[\d\-, ]+|p\.? ?\d+(?:-\d+)?|\b20\d\d-\d\d-\d\d\b|\bB4C8\b|PostgreSQL 18\.6|Node 22\.14|Redis 8\.10\.2"
pages = [re.sub(STRIP, " ", p.extract_text()) for p in PAGES]
toks = sorted({tk for t in pages for tk in NUM.findall(t)})
nontriv = [tk for tk in toks if decimals(tk) > 0 or len(re.sub(r"\D", "", tk)) >= 3]
print(f"{PDF}: {len(PAGES)} pages du dossier (D-1 à D-8), {len(toks)} nombres distincts, dont {len(nontriv)} non triviaux (décimale ou 3 chiffres et plus)")
ok_src = [tk for tk in nontriv if found(tk)]
print(f"1. retrouvés dans les fichiers de mesures ou les annexes : {len(ok_src)}/{len(nontriv)} ; à contrôler : {[tk for tk in nontriv if not found(tk)]}")
SRC_ANN = src
src = ANNEXE
ok_ann = [tk for tk in nontriv if found(tk)]
print(f"2. retrouvés dans le texte des annexes jointes seul : {len(ok_ann)}/{len(nontriv)} ; autres (arrondis, graduations) : {[tk for tk in nontriv if not found(tk)]}")

# 3. recalcul du tableau D-4 depuis p2_charge.json
d = json.load(open(os.path.join(ROOT, "atelier9/resultats/p2_charge.json")))["B_http_n1_groupe"]
fr = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")
txt4 = re.sub(r"\s+", " ", PAGES[3].extract_text())
bad = 0
for c in ("1", "5", "10", "20"):
    a, b = d[c]["n1"]["mediane"], d[c]["groupe"]["mediane"]
    row = f"{c} {fr(a['debit_termine'])} {fr(a['mediane_ms'])} {fr(a['p95_ms'])} 0 {fr(b['debit_termine'])} {fr(b['mediane_ms'])} {fr(b['p95_ms'])} 0"
    good = row in txt4; bad += not good
    print(f"3. ligne {c:>2} clients recalculée depuis p2_charge.json : {'identique' if good else 'ÉCART : ' + row}")
a, b = d["20"]["n1"], d["20"]["groupe"]
fa = [e["debit_termine"] for e in a["essais"]]; fb = [e["debit_termine"] for e in b["essais"]]
checks = {"facteur ×4,2": f"{b['mediane']['debit_termine'] / a['mediane']['debit_termine']:.1f}" == "4.2",
          "p95 −73 %": round((1 - b["mediane"]["p95_ms"] / a["mediane"]["p95_ms"]) * 100) == 73,
          "essais N+1 238 à 253": (round(min(fa)), round(max(fa))) == (238, 253),
          "essais groupé 978 à 1 082": (round(min(fb)), round(max(fb))) == (978, 1082),
          "intervalles disjoints": min(fb) > max(fa),
          "erreurs 0 partout": all(e["erreurs"] == 0 for c in d for m in d[c] for e in d[c][m]["essais"])}
for k, v in checks.items():
    print(f"3. {k} : {'vérifié' if v else 'ÉCART'}"); bad += not v

front = [reader.pages[i].extract_text() for i in range(11)]
alltxt = "\n".join(front)
pat = re.compile(r"PRINCIPAL\.pdf|Presentation_|\.json|\.py\b|\.mjs|\.log|\.csv|atelier\d/|dossier/|test\.pdf")
ext = [m.group(0) for m in pat.finditer(alltxt)]
print(f"4. renvois à des documents extérieurs dans les 11 premières pages : {len(ext)} {ext}"); bad += bool(ext)
for k in ("A. Besoin et état initial", "B. Architecture et stockage", "C. Intervention principale", "D. Benchmark", "E. Correction et fiabilité", "F. Décision et limites",
          "Fiches d'identité", "Auto-évaluation", "Checklist de remise", "Formulation finale", "Reproductibilité", "Conséquence pour l'API", "Variante rejetée n° 1", "Risques restants"):
    ok = k in alltxt; print(f"5. fiche : {k} : {'présent' if ok else 'ABSENT'}"); bad += not ok
d7 = reader.pages[8].extract_text(); defined = set(re.findall(r"P-\d\d(?=\s[A-ZÉ])", d7)); used = set(re.findall(r"P-\d\d", alltxt))
print(f"5. preuves définies : {len(defined)} ; références non définies : {sorted(used - defined)}"); bad += (len(defined) != 14 or bool(used - defined))
sys.exit(1 if bad else 0)

