#!/usr/bin/env python3
"""Assemble PRINCIPAL_PLUS_complet.pdf = dossier final (D-1 à D-8, PRINCIPAL_PLUS.pdf) + page D-9 « pièces jointes »
+ annexes (test.pdf : PRINCIPAL, pages 1 à 59, et chapitre / annexe 11 du Jour 5, pages 60 à 71) + signets.
Aucun contenu n'est modifié : les pages D-1 à D-8 et les annexes sont reprises telles quelles."""
import io, os
import pypdf
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Table, TableStyle, SimpleDocTemplate, Spacer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("S", F + "DejaVuSans.ttf")); pdfmetrics.registerFont(TTFont("SB", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "DejaVuSansMono.ttf"))
pdfmetrics.registerFontFamily("S", normal="S", bold="SB")
NAVY, ACC, GRID = colors.HexColor("#173a4d"), colors.HexColor("#b4532a"), colors.HexColor("#c9cfd6")
P = lambda t, **k: Paragraph(t, ParagraphStyle("p", fontName=k.pop("f", "S"), fontSize=k.pop("s", 8.4), leading=k.pop("l", 11), **k))
ANN0 = 11  # pages avant l'annexe : contexte + D-1 à D-9 ; page N de l'annexe = page N + 11 de ce fichier

rows = [("Preuve", "Sortie brute dans ce fichier (page de l'annexe)", "Fichiers sources (dépôt, non joints)"),
        ("P-01 P-05 P-06 P-12", "p. 63-64 (courbes, séries C et D) ; p. 70-71 (11.7 : chaque essai)", "atelier9/resultats/p2_charge.json, p2_run.log"),
        ("P-02", "p. 68 (11.2 pg_stat_statements, 11.3 journal lent) ; p. 20 et 53 (sqlMs par TraceId)", "atelier9/resultats/p1_diagnostics.json ; atelier7/resultats/api_journal.log"),
        ("P-03 P-04", "p. 19-20 (comptage, droits) ; p. 53-54 (9.3 à 9.6)", "atelier7/resultats/resultats_partie_a.json, api_journal.log"),
        ("P-07", "p. 21 ; p. 55 (9.8 campagnes brutes)", "atelier7/resultats/pgbouncer/, b_compare40.log"),
        ("P-08", "p. 23 ; p. 57-58 (10.3, 10.6)", "atelier8/resultats/mesure_persistante.json"),
        ("P-09 P-10", "p. 22-23 ; p. 58 (10.4, 10.5)", "atelier8/resultats/resultats_atelier8.json, api_extraits_par_traceid.txt"),
        ("P-11", "p. 23 ; p. 59 (10.7 rafale)", "atelier8/resultats/resultats_atelier8.json"),
        ("P-13", "p. 7-18 (ateliers 3 et 4, 4 bis) ; p. 48-52 (annexe 8)", "atelier3/, atelier4bis/resultats/"),
        ("P-14", "p. 68 (11.1 environnement) ; p. 71 (11.8 rejouer)", "atelier9/README.md, common.py, p1/p2/p3 *.py")]
data = [[P(c, f="SB" if i == 0 else "S", textColor=colors.white if i == 0 else colors.black, s=8) for c in r] for i, r in enumerate(rows)]
t = Table(data, colWidths=[78, 232, 165], repeatRows=1, hAlign="LEFT")
t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                       ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)] +
                      [("BACKGROUND", (0, k), (-1, k), colors.HexColor("#f4f6f8")) for k in range(2, len(rows), 2)]))
buf = io.BytesIO()


def deco(c, doc, label="D-9"):
    c.setFillColor(NAVY); c.rect(0, A4[1] - 31, A4[0], 31, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("SB", 8.6); c.drawString(45, A4[1] - 19, "Optimisation BDD · ShopFlow · Dossier final (Atelier 10)")
    c.setFont("S", 8.6); c.drawRightString(A4[0] - 45, A4[1] - 19, label)


doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=39, rightMargin=39, topMargin=58, bottomMargin=40)
doc.build([P("Pièces jointes : où trouver la sortie brute de chaque preuve", f="SB", s=11.5, l=15, textColor=ACC), Spacer(1, 6),
           P("Ce fichier contient la couverture, la page de contexte, le dossier (D-1 à D-9), puis l'annexe complète : PRINCIPAL (pages 1 à 59), le chapitre du Jour 5 (60 à 67) et l'annexe 11 (68 à 71). "
             "<b>« PRINCIPAL p. N »</b> désigne la page <b>N</b> de l'annexe, numérotée en haut de la page ; elle se trouve à la page <b>N + 11</b> de ce fichier.", s=8.8, l=12), Spacer(1, 8),
           t, Spacer(1, 10),
           P("Ce qui n'est pas dans les pièces", f="SB", s=9.4, textColor=ACC), Spacer(1, 2),
           P("Réplication, partitionnement et sharding : aucune preuve produite. Journaux de latence par transaction de pgbench (séries SQL) : non conservés, seules leurs statistiques le sont (p. 68). "
             "Les fichiers du dépôt cités ci-dessus sont les sorties d'origine ; les valeurs du dossier se retrouvent dans l'annexe, aux arrondis près (voir dossier/audit_chiffres.py).", s=8.6, l=11.5)],
          onFirstPage=deco)
buf.seek(0)

from reportlab.pdfgen import canvas as _cv
CYAN, PALE_O, PALE_B, TEAL, RED, GREEN = (colors.HexColor(x) for x in ("#7fd6e0", "#fdf3ec", "#e7ebef", "#1f8a99", "#c4472b", "#2f8f5b"))
W, H = A4
GREY = colors.HexColor("#5b6670")


def para(c, text, x, ytop, w, size=9, lead=None, font="S", color=colors.black):
    p = Paragraph(text, ParagraphStyle("q", fontName=font, fontSize=size, leading=lead or size * 1.35, textColor=color))
    _, h = p.wrapOn(c, w, 400); p.drawOn(c, x, ytop - h); return h


def box(c, x, y, w, h, fill, stroke=None, r=5):
    c.setFillColor(fill); c.setStrokeColor(stroke or fill); c.setLineWidth(1); c.roundRect(x, y, w, h, r, stroke=1, fill=1)


def arrow(c, x1, y1, x2, y2, color=NAVY, dash=False):
    c.setStrokeColor(color); c.setFillColor(color); c.setLineWidth(1.4); c.setDash(3, 3) if dash else c.setDash()
    c.line(x1, y1, x2, y2); c.setDash()
    import math
    a = math.atan2(y2 - y1, x2 - x1); s = 5
    pth = c.beginPath(); pth.moveTo(x2, y2); pth.lineTo(x2 - s * math.cos(a - .4), y2 - s * math.sin(a - .4)); pth.lineTo(x2 - s * math.cos(a + .4), y2 - s * math.sin(a + .4)); pth.close()
    c.drawPath(pth, fill=1, stroke=0)


def bar(c, label):
    c.setFillColor(NAVY); c.rect(0, H - 31, W, 31, stroke=0, fill=1)
    c.setFillColor(colors.white); c.setFont("SB", 8.6); c.drawString(45, H - 19, "Optimisation BDD · ShopFlow · Dossier final (Atelier 10)")
    c.setFont("S", 8.6); c.drawRightString(W - 45, H - 19, label)


def cover(c):
    c.setFillColor(NAVY); c.rect(0, H - 330, W, 330, stroke=0, fill=1)
    c.setFillColor(CYAN); c.setFont("SB", 9); c.drawString(45, H - 64, "OPTIMISATION BDD  ·  SHOPFLOW  ·  SUP DE VINCI M2")
    c.setFillColor(colors.white); c.setFont("SB", 27)
    for i, l in enumerate(("Le chargement groupé", "de GET /commandes,", "et le prix d'un cache")): c.drawString(45, H - 118 - i * 36, l)
    c.setFont("S", 11.5); c.setFillColor(colors.HexColor("#d5e6ec"))
    c.drawString(45, H - 248, "Atelier 10 · Dossier final et restitution")
    c.drawString(45, H - 266, "Compétence B4C8 : API et services back-end avec gestion optimisée des données")
    c.setFillColor(CYAN); c.setFont("S", 9.5); c.drawString(45, H - 300, "Octobre 2026  ·  PostgreSQL 18.6  ·  Node 22.14  ·  Redis 8.10.2")
    # schéma avant / après : une page = 21 allers-retours, puis 2
    c.setFillColor(CYAN); c.setFont("SB", 8); c.drawString(425, H - 74, "UNE PAGE DE 20 COMMANDES")
    for k in range(21):
        c.setStrokeColor(colors.HexColor("#f08a6c")); c.setLineWidth(1.2); c.line(427, H - 92 - k * 5.2, 467, H - 92 - k * 5.2)
    for k in range(2):
        c.setStrokeColor(CYAN); c.setLineWidth(2.4); c.line(510, H - 150 - k * 14, 550, H - 150 - k * 14)
    c.setFillColor(colors.white); c.setFont("SB", 20); c.drawString(427, H - 218, "21"); c.drawString(510, H - 218, "2")
    c.setFillColor(colors.HexColor("#d5e6ec")); c.setFont("S", 7.6); c.drawString(427, H - 232, "requêtes SQL, avant"); c.drawString(510, H - 232, "après")
    c.setStrokeColor(CYAN); c.setLineWidth(1.4); c.line(474, H - 150, 499, H - 150)
    c.setFillColor(CYAN); pth = c.beginPath(); pth.moveTo(503, H - 150); pth.lineTo(496, H - 146); pth.lineTo(496, H - 154); pth.close(); c.drawPath(pth, fill=1, stroke=0)
    # résultats
    tiles = [("21 → 2", "requêtes SQL par page de 20 commandes", RED), ("×4,2", "débit à 20 clients (246,9 → 1032,1 req/s)", TEAL),
             ("−73 %", "latence p95 (98,0 → 26,8 ms)", TEAL), ("0", "erreur, résultat identique", GREEN)]
    for i, (big, cap, col) in enumerate(tiles):
        x = 45 + i * 130
        box(c, x, H - 430, 120, 74, colors.white, GRID, 6)
        c.setFillColor(col); c.setFont("SB", 22); c.drawCentredString(x + 60, H - 396, big)
        para(c, cap, x + 8, H - 405, 104, 7.8, 9.6, "S", GREY)
    c.setFillColor(GREY); c.setFont("S", 7.6); c.drawString(45, H - 444, "Médianes de 3 essais alternés, GET /commandes?limit=20, 20 clients simultanés, même machine, un seul changement (pièces : P-05).")
    # question
    box(c, 45, H - 530, W - 90, 66, PALE_O, ACC, 6)
    c.setFillColor(ACC); c.setFont("SB", 8.6); c.drawString(58, H - 482, "QUESTION DU DOSSIER")
    para(c, "Une page de 20 commandes paraît simple, mais devient lente quand plusieurs clients arrivent. <b>D'où vient ce coût, comment le supprimer sans changer le résultat, et à quel prix ?</b>", 58, H - 489, W - 116, 10.2, 13.4)
    # plan
    c.setFillColor(NAVY); c.setFont("SB", 10.5); c.drawString(45, H - 568, "Dans ce dossier")
    plan = [("Contexte du projet", "2"), ("Inventaire des preuves et choix de l'optimisation", "3"), ("A. Besoin et état initial · B. Architecture et stockage", "4"),
            ("C. Intervention principale : 21 requêtes → 2", "5"), ("D. Benchmark avant / après, courbe 1 à 20 clients", "6"), ("E. Correction et fiabilité : résultat identique, cache Redis", "7"),
            ("F. Décision, variantes rejetées, limites", "8"), ("Fiches d'identité des preuves P-01 à P-14", "9"), ("Auto-évaluation B4C8 · questions · checklist · formulation finale", "10"),
            ("Pièces jointes, puis annexes : sorties brutes (pages 12 à 82)", "11")]
    for i, (t, p) in enumerate(plan):
        y = H - 590 - i * 19
        c.setFillColor(colors.black); c.setFont("S", 9.2); c.drawString(45, y, t)
        c.setFillColor(ACC); c.setFont("SB", 9.2); c.drawRightString(W - 45, y, p)
        c.setStrokeColor(GRID); c.setLineWidth(.4); c.line(45, y - 5, W - 45, y - 5)
    c.setFillColor(GREY); c.setFont("S", 7.8)
    c.drawString(45, 40, "Règle suivie : aucun chiffre sans sortie réelle derrière (sortie brute, plan, trace ou test réellement exécuté).")


def contexte(c):
    bar(c, "Contexte")
    c.setFillColor(ACC); c.setFont("SB", 13); c.drawString(45, H - 62, "Contexte du projet")
    h = para(c, "<b>ShopFlow</b> est une boutique en ligne de laboratoire (clients, produits, commandes, lignes). Son API expose l'historique des commandes d'un client "
                "(<font name='Mono'>GET /commandes?limit=20</font>) et la fiche d'un produit. Le module Optimisation BDD (RNCP 40166, bloc 4, B4C8) demande de mesurer, "
                "corriger et défendre une optimisation sur cette API.", 45, H - 72, W - 90, 9.4, 12.6)
    y0 = H - 72 - h - 16
    c.setFillColor(NAVY); c.setFont("SB", 9.6); c.drawString(45, y0, "ARCHITECTURE RÉELLEMENT UTILISÉE")
    by = y0 - 78
    box(c, 40, by, 122, 56, PALE_B, GRID); box(c, 200, by, 130, 56, PALE_B, GRID); box(c, 392, by + 30, 158, 46, colors.HexColor("#d6eee0"), GREEN); box(c, 392, by - 20, 158, 46, colors.HexColor("#f8dcd3"), RED)
    for (x, y, w, a, b) in ((45, by, 112, "Générateur de charge", "1 à 20 clients simultanés"), (200, by, 130, "API Node 22.14", "server.mjs · pool de 5 connexions"),
                            (392, by + 30, 158, "PostgreSQL 18.6", "source de vérité · schéma shopflow"), (392, by - 20, 158, "Redis 8.10.2", "cache fiche produit · TTL 60 s")):
        c.setFillColor(colors.black); c.setFont("SB", 9); c.drawCentredString(x + w / 2, y + (28 if h else 0) + 6 if False else y + (w and 0) + (34 if y == by else 20) + (0 if y == by else 0), a) if False else None
    for (x, y, w, hh, a, b) in ((40, by, 122, 56, "Générateur de charge", "1 à 20 clients simultanés"), (200, by, 130, 56, "API Node 22.14", "pool de 5 connexions"),
                                (392, by + 30, 158, 46, "PostgreSQL 18.6", "source de vérité · schéma shopflow"), (392, by - 20, 158, 46, "Redis 8.10.2", "cache de la fiche produit · TTL 60 s")):
        c.setFillColor(colors.black); c.setFont("SB", 9); c.drawCentredString(x + w / 2, y + hh / 2 + 3, a)
        c.setFillColor(GREY); c.setFont("S", 7.4); c.drawCentredString(x + w / 2, y + hh / 2 - 9, b)
    arrow(c, 162, by + 28, 200, by + 28); arrow(c, 330, by + 38, 392, by + 53); arrow(c, 330, by + 20, 392, by + 3)
    c.setFillColor(GREY); c.setFont("S", 7.4); c.drawString(166, by + 33, "HTTP")
    c.drawString(341, by + 54, "SQL"); c.drawString(344, by - 10, "lecture, PATCH")
    para(c, "PgBouncer : testé dans un laboratoire séparé (atelier 7), hors du chemin ci-dessus. Tout tourne sur un portable : i5-10310U, 8 cœurs, 7,6 Go, WSL2 sous Docker.", 45, by - 30, W - 90, 7.6, 9.4, "S", GREY)
    # données
    y1 = by - 62
    c.setFillColor(NAVY); c.setFont("SB", 9.6); c.drawString(45, y1, "LES DONNÉES")
    data = [("1 000", "clients"), ("200", "produits"), ("100 000", "commandes"), ("300 000", "lignes"), ("100", "commandes du client 42")]
    for i, (n, l) in enumerate(data):
        x = 45 + i * 102
        box(c, x, y1 - 54, 96, 42, colors.white, GRID); c.setFillColor(NAVY); c.setFont("SB", 14); c.drawCentredString(x + 48, y1 - 32, n)
        c.setFillColor(GREY); c.setFont("S", 7.6); c.drawCentredString(x + 48, y1 - 45, l)
    para(c, "Commandes du 1er janvier au 27 octobre 2026, 3 lignes chacune. Base contrôlée avant et après les tests ; copie jetable pour les mesures lourdes.", 45, y1 - 62, W - 90, 7.8, 9.6, "S", GREY)
    # parcours
    y2 = y1 - 96
    c.setFillColor(NAVY); c.setFont("SB", 9.6); c.drawString(45, y2, "LE PARCOURS : CE QUE CHAQUE ATELIER A PROUVÉ")
    steps = [("Atelier 1", "diagnostic initial des requêtes", PALE_B), ("Atelier 2", "EXISTS 11,3 ms contre jointure 27,6 ms", PALE_B),
             ("Atelier 3", "index composé : ×2,5 sur la requête de l'API, WAL +35 %", PALE_B), ("Atelier 4", "index partiel : 10,1 → 0,070 ms, utile à son seul prédicat", PALE_B),
             ("Atelier 4 bis", "migration : 46,3 ms contre 3 324,1 ms sous verrou", PALE_B), ("Atelier 7", "N+1 : 21 → 2 requêtes ; curseur 944,3 → 0,177 ms", PALE_O),
             ("Atelier 8", "cache Redis : 2,7 → 0,988 ms, copie périmée possible", colors.HexColor("#d6eee0")), ("Jour 5", "courbe de charge 1 à 20 clients : ×4,2", PALE_O)]
    for i, (a, b, f) in enumerate(steps):
        x, y = 45 + (i % 2) * 255, y2 - 40 - (i // 2) * 44
        box(c, x, y, 247, 36, f, GRID); c.setFillColor(ACC if f == PALE_O else NAVY); c.setFont("SB", 8.6); c.drawString(x + 8, y + 22, a)
        para(c, b, x + 8, y + 19, 231, 7.9, 9.4)
    ys = y2 - 40 - 3 * 44 - 40
    c.setFillColor(NAVY); c.setFont("SB", 9.6); c.drawString(45, ys, "L'HISTOIRE EN QUATRE TEMPS")
    story = [("1  Le symptôme", "À 20 clients le débit plafonne à 246,9 req/s dès 5 clients, p95 98,0 ms, sans aucune erreur.", colors.HexColor("#f8dcd3"), RED),
             ("2  La cause", "21 allers-retours par page : 0,018 ms vus par PostgreSQL, 0,68 ms vus par l'API.", PALE_B, NAVY),
             ("3  Le remède", "Une requête pour toutes les lignes : 2 requêtes, même JSON, 1032,1 req/s.", colors.HexColor("#d6eee0"), GREEN),
             ("4  Le prix", "Le cache évite des lectures mais peut servir 57.50 quand la base dit 19.90, jusqu'à 60 s.", PALE_O, ACC)]
    for i, (a, b, f, col) in enumerate(story):
        x = 45 + i * 128
        box(c, x, ys - 98, 122, 86, f, GRID); c.setFillColor(col); c.setFont("SB", 8.8); c.drawString(x + 8, ys - 28, a)
        para(c, b, x + 8, ys - 35, 106, 7.9, 10)
        if i < 3: arrow(c, x + 122, ys - 55, x + 128, ys - 55, NAVY)
    c.setFillColor(GREY); c.setFont("S", 7.8)
    para(c, "Orange : l'optimisation défendue dans ce dossier (ateliers 7 et Jour 5). Vert : la preuve de fraîcheur (atelier 8). Gris : preuves de contexte.", 45, y2 - 40 - 3 * 44 - 4, W - 90, 7.8, 9.6, "S", GREY)


cbuf = io.BytesIO()
cc = _cv.Canvas(cbuf, pagesize=A4); cc.setTitle("PRINCIPAL+ : dossier final Atelier 10, ShopFlow")
cover(cc); cc.showPage(); contexte(cc); cc.showPage(); cc.save(); cbuf.seek(0)

w = pypdf.PdfWriter()
import sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pages_dossier import build
w.append(cbuf, import_outline=False)
for b in build(): w.append(b, import_outline=False)
w.append(os.path.join(ROOT, "test.pdf"), import_outline=False)
w.add_outline_item("Couverture", 0); w.add_outline_item("Contexte du projet", 1)
for title, idx in (("A. Besoin et état initial · B. Architecture et stockage", 3), ("C. Intervention principale", 4), ("D. Benchmark avant / après", 5), ("E. Correction et fiabilité", 6),
                   ("F. Décision et limites", 7), ("Fiches d'identité des preuves (P-01 à P-14)", 8), ("Auto-évaluation · deux questions · checklist · formulation finale", 9), ("Pièces jointes", 10)):
    w.add_outline_item(title, idx)
root = w.add_outline_item("Annexes : preuves brutes (PRINCIPAL et Jour 5)", ANN0)
for title, n in (("Ateliers 1 à 4 (p. 1)", 1), ("Atelier 4 bis (p. 16)", 16), ("Atelier 7 : N+1, curseur, PgBouncer (p. 19)", 19), ("Atelier 8 : cache Redis (p. 22)", 22),
                 ("Annexe 8 : preuves atelier 4 bis (p. 48)", 48), ("Annexe 9 : preuves atelier 7 (p. 53)", 53), ("Annexe 10 : preuves atelier 8 (p. 57)", 57),
                 ("Jour 5 : chapitre (p. 60)", 60), ("Annexe 11 : preuves du Jour 5 (p. 68)", 68)):
    w.add_outline_item(title, ANN0 + n - 1, parent=root)
w.add_metadata({"/Title": "PRINCIPAL+ : dossier final Atelier 10, ShopFlow", "/Author": "Optimisation BDD, SUP DE VINCI M2"})
out = os.path.join(ROOT, "PRINCIPAL_PLUS_complet.pdf")
with open(out, "wb") as f:
    w.write(f)
print(out, len(w.pages), "pages")
