#!/usr/bin/env python3
"""Deux versions de la présentation orale de 5 minutes (Atelier 10, partie 8 de la fiche), chacune en PDF :
  V1 = structure de la fiche (besoin → mécanisme → mesures → correction/fraîcheur → décision) ;
  V2 = la même matière racontée avec un fil rouge (une problématique, cinq actes, une question par acte).
Chaque diapositive porte, à droite, le texte À DIRE (à lire) ; à gauche, un schéma ou un graphique construit avec les mesures réelles du projet
(aucun chiffre saisi à la main : tout est lu dans les fichiers de mesures). Usage : python3 presentation/build_presentations.py"""
import json, os, re, statistics
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.lib.fonts import addMapping

F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", F + "DejaVuSans.ttf")); pdfmetrics.registerFont(TTFont("Sans-Bold", F + "DejaVuSans-Bold.ttf"))
pdfmetrics.registerFont(TTFont("Mono", F + "DejaVuSansMono.ttf"))
addMapping("Sans", 0, 0, "Sans"); addMapping("Sans", 1, 0, "Sans-Bold"); addMapping("Sans", 0, 1, "Sans"); addMapping("Sans", 1, 1, "Sans-Bold")

ROOT = "/home/youssef/école"
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
P2, P1, P8 = J("atelier9/resultats/p2_charge.json"), J("atelier9/resultats/p1_diagnostics.json"), J("atelier8/resultats/mesure_persistante.json")
A7, A8 = J("atelier7/resultats/resultats_partie_a.json"), J("atelier8/resultats/resultats_atelier8.json")
B, C = P2["B_http_n1_groupe"], P2["C_pool_api"]
n1, gr = B["20"]["n1"]["mediane"], B["20"]["groupe"]["mediane"]
n1e, gre = B["20"]["n1"]["essais"], B["20"]["groupe"]["essais"]
LV = ["1", "5", "10", "20"]
pg_n1 = [r for r in P1["pgss_top"] if "commande_id" in r["requete"] and int(r["appels"]) == 20000][0]
sql_page = A7["2_repetition"]["20"]["n1"]["sqlMs_mediane"]
per_q = sql_page / 21
fr = lambda v, d=1: f"{v:.{d}f}".replace(".", ",")
th = lambda v: f"{int(round(v)):,}".replace(",", " ")
rng = lambda es, k: f"{fr(min(e[k] for e in es), 0)} à {fr(max(e[k] for e in es), 0)}"
pool20 = statistics.median(e["debit_termine"] for e in C["20"]["essais"])
price_stale, price_db = A8["3_update_direct"]["apres_update_avant_del"]["prix"], A8["3_update_direct"]["postgres_prix"]
miss_ms, hit_ms = P8["miss"]["http_ms"]["mediane"], P8["hit"]["http_ms"]["mediane"]
pool_wait = n1e[1]["machine"]["pool_attente_max"]

NAVY = colors.HexColor("#173a4d"); ACCENT = colors.HexColor("#b4532a"); LIGHT = colors.HexColor("#fdf3ec"); GRID = colors.HexColor("#c9cfd6")
RED = colors.HexColor("#c4472b"); GREEN = colors.HexColor("#2f8f5b"); TEAL = colors.HexColor("#1f8a99"); INK = colors.HexColor("#1b2530")
PALE_RED = colors.HexColor("#f8dcd3"); PALE_GREEN = colors.HexColor("#d6eee0"); PALE = colors.HexColor("#e7ebef"); CYAN = colors.HexColor("#7fd6e0")
W, H = landscape(A4)
WPM = 130
VX0, VX1 = 28, 478          # zone visuelle
SX0 = 494                   # zone « à dire »


# ------------------------------------------------------------------ primitives de dessin
def txt(c, x, y, s, size=9, bold=False, color=INK, anchor="l"):
    c.setFillColor(color); c.setFont("Sans-Bold" if bold else "Sans", size)
    {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[anchor](x, y, s)


def box(c, x, y, w, h, title, sub=None, fill=PALE, stroke=GRID, tcolor=INK, tsize=10, ssize=8):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(1.2); c.roundRect(x, y, w, h, 6, stroke=1, fill=1)
    if not title:
        return
    ty = y + h / 2 + (4 if sub else -3)
    txt(c, x + w / 2, ty, title, tsize, True, tcolor, "c")
    if sub:
        txt(c, x + w / 2, ty - 13, sub, ssize, False, INK, "c")


def arrow(c, x1, y1, x2, y2, color=NAVY, w=1.6, label=None, dash=False):
    import math
    c.setStrokeColor(color); c.setFillColor(color); c.setLineWidth(w)
    c.setDash(3, 2) if dash else c.setDash()
    c.line(x1, y1, x2, y2); c.setDash()
    a = math.atan2(y2 - y1, x2 - x1); L = 6
    p = c.beginPath(); p.moveTo(x2, y2); p.lineTo(x2 - L * math.cos(a - 0.4), y2 - L * math.sin(a - 0.4)); p.lineTo(x2 - L * math.cos(a + 0.4), y2 - L * math.sin(a + 0.4)); p.close()
    c.drawPath(p, stroke=0, fill=1)
    if label:
        txt(c, (x1 + x2) / 2, (y1 + y2) / 2 + 5, label, 7.5, True, color, "c")


def title_v(c, x, y, s):
    txt(c, x, y, s.upper(), 9.5, True, ACCENT)


def code(c, x, y, w, h, lines, head, headcol):
    c.setFillColor(headcol); c.rect(x, y + h - 16, w, 16, stroke=0, fill=1); txt(c, x + 6, y + h - 12, head, 8.5, True, colors.white)
    c.setFillColor(colors.HexColor("#f3f4f6")); c.rect(x, y, w, h - 16, stroke=0, fill=1)
    c.setFont("Mono", 7.2); c.setFillColor(INK)
    for i, l in enumerate(lines):
        c.drawString(x + 6, y + h - 28 - i * 9.2, l)


def chart(c, x, y, w, h, title, series, yfmt):
    """Courbes à 4 niveaux de charge (1, 5, 10, 20 clients)."""
    txt(c, x, y + h - 8, title, 8.5, True, NAVY)
    px0, py0, pw, ph = x + 36, y + 22, w - 44, h - 52
    ymax = max(max(v) for _, v, _ in series) * 1.12
    for k in range(5):
        yy = py0 + ph * k / 4
        c.setStrokeColor(GRID); c.setLineWidth(0.4); c.line(px0, yy, px0 + pw, yy)
        txt(c, px0 - 4, yy - 2.5, yfmt(ymax * k / 4), 6.5, False, colors.HexColor("#6b7280"), "r")
    xs = [px0 + pw * i / 3 for i in range(4)]
    for i, lab in enumerate(("1", "5", "10", "20")):
        txt(c, xs[i], py0 - 11, lab, 7.5, False, INK, "c")
    txt(c, px0 + pw / 2, y + 2, "clients simultanés", 7, False, colors.HexColor("#6b7280"), "c")
    for li, (lab, vals, col) in enumerate(series):
        pts = [(xs[i], py0 + ph * vals[i] / ymax) for i in range(4)]
        c.setStrokeColor(col); c.setLineWidth(2)
        for a, b2 in zip(pts, pts[1:]):
            c.line(a[0], a[1], b2[0], b2[1])
        c.setFillColor(col)
        for p in pts:
            c.circle(p[0], p[1], 2.4, stroke=0, fill=1)
        c.rect(px0 + li * 90, y + h - 24, 7, 7, stroke=0, fill=1); txt(c, px0 + 11 + li * 90, y + h - 23, lab, 7.5)
        txt(c, pts[-1][0] + 2, pts[-1][1] + 5, yfmt(vals[-1]), 7.5, True, col, "r")


def table(c, x, ytop, w, rows, colw, size=8.6, head=NAVY):
    st = ParagraphStyle("c", fontName="Sans", fontSize=size, leading=size * 1.25)
    sb = ParagraphStyle("b", parent=st, fontName="Sans-Bold", textColor=colors.white)
    data = [[Paragraph(str(v), sb) for v in rows[0]]] + [[Paragraph(str(v), st) for v in r] for r in rows[1:]]
    t = Table(data, colWidths=colw)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), head), ("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)] +
                          [("BACKGROUND", (0, k), (-1, k), colors.HexColor("#f4f6f8")) for k in range(2, len(data), 2)]))
    tw, th_ = t.wrapOn(c, w, 400); t.drawOn(c, x, ytop - th_)
    return th_


def say(c, text, y0=40):
    bx, by, bw, bh = SX0, y0, W - SX0 - 24, H - 78 - y0 - 18
    c.setFillColor(LIGHT); c.setStrokeColor(ACCENT); c.setLineWidth(1.2); c.roundRect(bx, by, bw, bh, 6, stroke=1, fill=1)
    txt(c, bx + 12, by + bh - 17, "À DIRE", 10, True, ACCENT)
    ts = 13.5
    while True:
        p = Paragraph(text, ParagraphStyle("t", fontName="Sans", fontSize=ts, leading=ts * 1.38, textColor=INK))
        pw, ph = p.wrapOn(c, bw - 24, bh)
        if ph <= bh - 38 or ts <= 9.5:
            break
        ts -= 0.5
    assert ph <= bh - 34, (ph, bh, text[:40])
    p.drawOn(c, bx + 12, by + bh - 28 - ph)


# ------------------------------------------------------------------ visuels communs
def v_flow_problem(c, y0):
    """Client → API → pool (5) → PostgreSQL, avec les 21 allers-retours d'une page."""
    title_v(c, VX0, y0 + 190, "Ce que fait une page de 20 commandes")
    box(c, VX0, y0 + 110, 80, 46, "Client", "GET /commandes", PALE)
    box(c, VX0 + 118, y0 + 110, 90, 46, "API Node", "construit la page", PALE)
    box(c, VX0 + 246, y0 + 110, 88, 46, "Pool", "5 connexions", PALE_RED, RED)
    box(c, VX0 + 372, y0 + 110, 78, 46, "PostgreSQL", "commandes, lignes", PALE)
    arrow(c, VX0 + 80, y0 + 133, VX0 + 118, y0 + 133); arrow(c, VX0 + 208, y0 + 133, VX0 + 246, y0 + 133)
    for k in range(7):
        arrow(c, VX0 + 334, y0 + 118 + k * 5.3, VX0 + 372, y0 + 118 + k * 5.3, RED, 1.0)
    txt(c, VX0 + 353, y0 + 160, "21 requêtes", 8.5, True, RED, "c")
    txt(c, VX0 + 353, y0 + 99, "1 liste + 1 par commande", 7.5, False, RED, "c")


def v_measure_table(c, ytop):
    return table(c, VX0, ytop, 430, [["Mesure initiale (20 clients, N+1)", "Valeur"],
                                    ["Débit terminé (plafonne dès 5 clients)", f"≈ {fr(n1['debit_termine'], 0)} requêtes/s"],
                                    ["Latence p95", f"{fr(n1['p95_ms'], 0)} ms"],
                                    ["File d'attente du pool (max)", f"{pool_wait} requêtes"],
                                    ["Erreurs", "0"]], [250, 180])


def v_code_before_after(c, y0):
    code(c, VX0, y0 + 96, 215, 100, ["rows = SELECT … commandes", "        LIMIT 20;", "POUR CHAQUE commande :", "  SELECT … FROM lignes", "   WHERE commande_id = $1;", "", "-- 1 + 20 = 21 requêtes"], "ANCIENNE VERSION", RED)
    code(c, VX0 + 235, y0 + 96, 215, 100, ["rows = SELECT … commandes", "        LIMIT 20;", "SELECT … FROM lignes", " WHERE commande_id =", "   ANY($1::bigint[]);", "-- $1 = les 20 ids", "-- 2 requêtes, toujours"], "NOUVELLE VERSION", GREEN)
    arrow(c, VX0 + 218, y0 + 146, VX0 + 233, y0 + 146, NAVY, 2)


def v_bars_cost(c, y0):
    title_v(c, VX0, y0 + 74, "Où est le coût ? (temps par requête de lignes)")
    mx = per_q
    for i, (lab, v, col) in enumerate((("vu par PostgreSQL", float(pg_n1["moyenne_ms"]), TEAL), ("vu par l'API (aller-retour)", per_q, RED))):
        yy = y0 + 46 - i * 26
        txt(c, VX0, yy + 3, lab, 8.5)
        wbar = max(3, v / mx * 230)
        c.setFillColor(col); c.rect(VX0 + 150, yy, wbar, 14, stroke=0, fill=1)
        txt(c, VX0 + 150 + wbar + 5, yy + 3, f"{fr(v, 3 if v < 0.1 else 2)} ms", 8.5, True, col)
    txt(c, VX0 + 150, y0 - 4, f"×{fr(per_q / float(pg_n1['moyenne_ms']), 0)} : le coût est dans les allers-retours", 8, True, ACCENT)


def v_curves(c, y0):
    chart(c, VX0, y0 + 96, 215, 118, "Requêtes terminées par seconde", [("N+1", [B[l]["n1"]["mediane"]["debit_termine"] for l in LV], RED), ("groupé", [B[l]["groupe"]["mediane"]["debit_termine"] for l in LV], TEAL)], lambda v: th(v))
    chart(c, VX0 + 235, y0 + 96, 215, 118, "Latence p95 (ms)", [("N+1", [B[l]["n1"]["mediane"]["p95_ms"] for l in LV], RED), ("groupé", [B[l]["groupe"]["mediane"]["p95_ms"] for l in LV], TEAL)], lambda v: fr(v, 0))


def v_results_table(c, ytop):
    return table(c, VX0, ytop, 450, [["20 clients, médiane de 3 essais", "Avant (N+1)", "Après (groupé)", "Gain"],
                                    ["Débit (req/s)", fr(n1["debit_termine"]), fr(gr["debit_termine"]), f"×{fr(gr['debit_termine'] / n1['debit_termine'])}"],
                                    ["p95 (ms)", fr(n1["p95_ms"]), fr(gr["p95_ms"]), f"−{(n1['p95_ms'] - gr['p95_ms']) / n1['p95_ms'] * 100:.0f} %"],
                                    ["Erreurs", "0", "0", "="],
                                    ["Les 3 essais (req/s)", rng(n1e, "debit_termine"), rng(gre, "debit_termine"), "intervalles disjoints"]], [150, 100, 100, 100])


def v_checks_and_cache(c, y0, compact=False):
    th_ = table(c, VX0, y0 + 205, 450, [["Correction (même résultat, mêmes droits)", "Résultat"],
                                        ["JSON complet N+1 = groupé (5, 20, 50, 100 commandes)", "identique"],
                                        ["Sans jeton / client_id dans l'URL / curseur falsifié", "401 / 400 / 400"]], [330, 120], size=8.4)
    yb = y0 + 205 - th_ - 18
    title_v(c, VX0, yb, "Fraîcheur : le cache peut mentir")
    box(c, VX0, yb - 60, 100, 44, "Base", f"{price_stale} → {price_db}", PALE_GREEN, GREEN)
    box(c, VX0 + 125, yb - 60, 100, 44, "Redis (TTL 60 s)", f"copie : {price_stale}", PALE_RED, RED)
    box(c, VX0 + 250, yb - 60, 100, 44, "API sert", f"{price_stale}  ✗", PALE_RED, RED)
    box(c, VX0 + 375, yb - 60, 75, 44, "PATCH + DEL", f"{price_db}  ✓", PALE_GREEN, GREEN)
    arrow(c, VX0 + 100, yb - 38, VX0 + 125, yb - 38, RED, 1.4, dash=True); arrow(c, VX0 + 225, yb - 38, VX0 + 250, yb - 38, RED); arrow(c, VX0 + 350, yb - 38, VX0 + 375, yb - 38, GREEN)
    txt(c, VX0 + 50, yb - 74, "UPDATE direct en SQL", 7.5, False, RED, "c")
    txt(c, VX0 + 300, yb - 74, "la copie n'a pas été invalidée", 7.5, False, RED, "c")
    txt(c, VX0 + 412, yb - 74, "chemin prévu", 7.5, False, GREEN, "c")
    txt(c, VX0, yb - 92, f"Cache : miss {fr(miss_ms)} ms (1 SELECT) → hit {fr(hit_ms, 2)} ms (0 SQL) ; fraîcheur acceptée ≤ 60 s ; jamais de cache sur l'achat.", 8, False, INK)


def v_decision(c, y0):
    th_ = table(c, VX0, y0 + 205, 450, [["", "Décision et raison mesurée"],
                                        ["Retenu", f"chargement groupé : 21 → 2 requêtes, ×{fr(gr['debit_termine'] / n1['debit_termine'])} de débit, p95 −{(n1['p95_ms'] - gr['p95_ms']) / n1['p95_ms'] * 100:.0f} %, 0 erreur"],
                                        ["Rejeté", f"agrandir le pool 5 → 20 : ≈ {fr(pool20, 0)} req/s contre {fr(gr['debit_termine'], 0)} en groupé (2 essais, indicatif) ; PgBouncer : 40 → 5 connexions mais 261 → 94 tps"],
                                        ["Risque restant", "copie périmée jusqu'à 60 s ; course entre une lecture lente et une invalidation (reproduite à la main)"],
                                        ["Portée", "cette machine (8 cœurs, WSL2), ce jeu (100 000 commandes), 1 à 20 clients ; non testé en production ni avec plusieurs instances"]], [92, 358], size=8.8)
    return th_


def v_qa(c, y0):
    th_ = table(c, VX0, y0 + 205, 450, [["Question probable", "Réponse courte"],
                                        ["Comment reproduire sur un autre poste ?", "même base (01_schema.sql, 02_donnees.sql, md5 comparés), PostgreSQL 18.6, Node 22, pool 5 ; charge fermée 1/5/10/20 clients, 3 essais alternés N+1 / groupé ; python3 atelier9/p2_charge.py (≈ 16 min) ; on compare l'ordre de grandeur"],
                                        ["Que change la décision pour l'API ?", "contrat inchangé (même JSON, mêmes droits) ; 21 → 2 requêtes donc moins de connexions occupées ; tableau d'ids borné à 100 ; avec le cache : copie ≤ 60 s et repli sur PostgreSQL si Redis tombe"],
                                        ["Et si le gain disparaît ?", "je le dirais : les séries pool et charge ouverte étaient instables, je les ai présentées essai par essai"],
                                        ["Écart de protocole ?", "ma mesure : 3 s d'échauffement et 10 s par essai ; la fiche cite 10 s et 30 s en exemple"]], [130, 320], size=8.6)


# ------------------------------------------------------------------ textes à dire
T1 = [
    ("Besoin et problème initial", "0:00 – 0:45",
     f"Bonjour. Mon cas, c'est ShopFlow, une boutique en ligne : une base PostgreSQL 18 avec 100 000 commandes et 300 000 lignes de commande. Je m'intéresse à un endpoint très simple, GET /commandes, qui renvoie une page de 20 commandes avec leurs lignes. "
     f"Sur le schéma : le client appelle l'API, l'API passe par un pool de 5 connexions, puis interroge PostgreSQL. Le problème observé : pour construire une seule page, l'API envoie <b>21 requêtes SQL</b>, une pour la liste puis une par commande. "
     f"Ma mesure de départ, avec 20 clients simultanés : le débit plafonne à environ <b>{fr(n1['debit_termine'], 0)} requêtes par seconde</b> dès 5 clients, le p95 est de <b>{fr(n1['p95_ms'], 0)} millisecondes</b>, et jusqu'à {pool_wait} requêtes attendent une connexion. Zéro erreur, mais le service est saturé."),
    ("Mécanisme et intervention", "0:45 – 1:45",
     f"Première question : où est le coût ? J'ai regardé pg_stat_statements. La requête de lignes apparaît avec {th(int(pg_n1['appels']))} appels de {fr(float(pg_n1['moyenne_ms']), 3)} milliseconde : {th(float(pg_n1['total_ms']))} millisecondes cumulées, elle passe inaperçue, et elle ne figure pas non plus dans le journal des requêtes lentes. "
     f"Mais l'API, elle, mesure {fr(sql_page)} millisecondes de SQL par page : environ {fr(per_q, 2)} milliseconde par requête, soit <b>{fr(per_q / float(pg_n1['moyenne_ms']), 0)} fois plus</b> que ce que voit PostgreSQL. Donc le coût n'est pas dans la requête, il est dans les <b>allers-retours</b>. "
     f"Mon hypothèse causale : si je charge toutes les lignes de la page en une seule requête, avec ANY et la liste des identifiants, je passe de 21 à 2 requêtes. C'est <b>la seule chose que je change</b>, comme on le voit sur le code à gauche."),
    ("Mesures avant / après", "1:45 – 3:00",
     f"Pour mesurer, je garde les mêmes conditions : même machine, même jeu de données, 1, 5, 10 et 20 clients, trois essais alternés. Sur la courbe de gauche, le débit du N+1 reste plat autour de 250 dès 5 clients : ajouter des clients n'ajoute que de l'attente. Le groupé monte et se stabilise bien plus haut. "
     f"À 20 clients, le débit passe de {fr(n1['debit_termine'], 0)} à <b>{fr(gr['debit_termine'], 0)} requêtes par seconde</b>, soit fois {fr(gr['debit_termine'] / n1['debit_termine'])}. Sur la courbe de droite, le p95 passe de {fr(n1['p95_ms'], 0)} à <b>{fr(gr['p95_ms'], 1)} millisecondes</b>, moins {(n1['p95_ms'] - gr['p95_ms']) / n1['p95_ms'] * 100:.0f} pour cent. "
     f"Zéro erreur. Les trois essais ne se chevauchent pas : c'est reproductible. Et le processeur reste à 50 pour cent dans les deux cas : le gain vient du travail évité, pas d'une ressource en plus."),
    ("Correction et fraîcheur", "3:00 – 4:00",
     f"Je ne regarde pas que la vitesse : un résultat plus rapide mais faux ne sert à rien. Le JSON complet, commandes et lignes, est <b>identique</b> en N+1 et en groupé, pour 5, 20, 50 et 100 commandes, et les droits sont conservés : 401 sans jeton, 400 si on injecte un client dans l'URL. "
     f"Ensuite, la fraîcheur, avec le cache Redis sur la fiche produit : un hit ne fait aucune requête SQL, un miss en fait une. Mais regardez : après une modification faite directement dans la base, l'API a continué de servir <b>{price_stale} alors que la base disait {price_db}</b>. "
     f"Le TTL de 60 secondes borne la copie périmée, il ne la corrige pas. Quand on passe par l'API avec un PATCH, la copie est invalidée et la valeur redevient juste. Et l'achat ne passe jamais par le cache."),
    ("Décision, variante rejetée, risque", "4:00 – 5:00",
     f"Ma décision : je retiens le chargement groupé. Une variante rejetée : agrandir le pool de 5 à 20 connexions. Cela supprime l'attente, mais n'atteint que {fr(pool20, 0)} requêtes par seconde, contre {fr(gr['debit_termine'], 0)} avec le groupé, sur deux essais seulement, donc à titre indicatif. J'ai aussi testé PgBouncer : il fait passer les connexions de 40 à 5, mais le débit tombe de 261 à 94 transactions par seconde. Il limite les connexions, il n'accélère rien. "
     f"Risque restant : la copie du cache peut être périmée jusqu'à 60 secondes, et il existe une course entre une lecture lente et une invalidation, que j'ai reproduite à la main. "
     f"Pour conclure en trois phrases : j'ai observé 21 requêtes par page et un débit plafonné ; en les ramenant à 2, le débit est multiplié par {fr(gr['debit_termine'] / n1['debit_termine'])} sans erreur ; c'est valable sur cette machine, ce jeu et 1 à 20 clients, et pas encore démontré en production."),
]
PROBLEM = "Une page de 20 commandes paraît simple, mais devient lente quand plusieurs clients arrivent. D'où vient ce coût, comment le supprimer sans changer le résultat, et à quel prix ?"
ACTS = ["1 Symptôme", "2 Enquête", "3 Remède", "4 Charge", "5 Prix"]
T2 = [
    ("Pourquoi ça plafonne ?", "0:00 – 0:45", "Le symptôme",
     f"Bonjour. Je vais vous raconter une enquête, avec une seule question : <b>pourquoi une page de 20 commandes devient-elle lente quand les clients arrivent ?</b> Imaginez une boutique en ligne : pour afficher une page de 20 commandes, le serveur fait <b>21 allers-retours</b> vers la base, un pour la liste, puis un par commande. "
     f"Ça marche, mais sous charge ça coince : avec 20 clients, le débit plafonne à environ <b>{fr(n1['debit_termine'], 0)} requêtes par seconde</b> dès 5 clients, le p95 monte à <b>{fr(n1['p95_ms'], 0)} millisecondes</b>, et {pool_wait} requêtes attendent une connexion. "
     f"Aucune erreur : le service est simplement saturé. Le symptôme est clair. Reste à trouver d'où vient ce coût, et c'est l'objet de l'enquête.",
     "→ Le symptôme est clair. Mais où se cache le coût ?"),
    ("Où est le coupable ?", "0:45 – 1:30", "L'enquête",
     f"Premier suspect : la requête elle-même. Elle est <b>innocente</b> : PostgreSQL la voit à {fr(float(pg_n1['moyenne_ms']), 3)} milliseconde, elle ne ressort pas en tête de pg_stat_statements, et elle n'apparaît pas dans le journal des requêtes lentes. "
     f"Deuxième suspect : le pool de connexions. Sa file d'attente est une <b>conséquence</b>, pas la cause : même avec un pool de 20, on n'atteint que {fr(pool20, 0)} requêtes par seconde. "
     f"Le vrai coupable, ce sont <b>les allers-retours</b> : côté API, chaque requête coûte {fr(per_q, 2)} milliseconde, soit <b>{fr(per_q / float(pg_n1['moyenne_ms']), 0)} fois plus</b> que ce que voit PostgreSQL. Multipliez ce prix par 21 pour chaque page, et vous obtenez le plafond.",
     "→ Si le coût est dans les allers-retours, je n'ai besoin de changer qu'une seule chose."),
    ("Peut-on le supprimer sans rien casser ?", "1:30 – 2:15", "Le remède",
     f"Le remède tient en une idée : au lieu d'une requête par commande, <b>une seule requête pour toutes les lignes de la page</b>, avec ANY et la liste des identifiants. On passe de 21 à <b>2 requêtes</b>, quelle que soit la taille de la page. C'est un seul changement : je ne touche ni à l'index, ni au pool, ni à la base. "
     "Mais un remède qui casse le résultat ne vaut rien. Je vérifie donc : le JSON complet, commandes et lignes, est <b>identique</b> avec 5, 20, 50 et 100 commandes, et les droits sont conservés : 401 sans jeton, 400 si on injecte un client dans l'URL. Même résultat, moins de travail.",
     "→ Le résultat est identique. Mais est-ce que ça tient quand la concurrence monte ?"),
    ("Le gain tient-il sous charge ?", "2:15 – 3:30", "La preuve à la charge",
     f"Pour le savoir, je mesure avec 1, 5, 10 et 20 clients, trois essais alternés, un seul changement. Regardez la courbe de gauche : le débit de l'ancienne version reste plat autour de 250 ; celui de la nouvelle monte et se stabilise bien plus haut. À 20 clients, on passe de {fr(n1['debit_termine'], 0)} à <b>{fr(gr['debit_termine'], 0)} requêtes par seconde</b>, fois {fr(gr['debit_termine'] / n1['debit_termine'])}. "
     f"À droite, le p95 passe de {fr(n1['p95_ms'], 0)} à <b>{fr(gr['p95_ms'], 1)} millisecondes</b>. Zéro erreur. Le processeur ne bouge pas, autour de 50 pour cent : le gain vient du <b>travail évité</b>, pas d'une machine plus puissante. "
     "Et les trois essais de chaque version ne se chevauchent pas : c'est reproductible, pas un hasard de mesure.",
     "→ Le gain est réel. Alors qu'est-ce qu'il me coûte, et qu'est-ce que je ne sais pas ?"),
    ("Quel est le prix, et quelles limites ?", "3:30 – 5:00", "Le prix du remède",
     f"Premier prix, la fraîcheur. Si je mets un cache Redis devant, un hit ne fait aucune requête, mais la copie peut <b>mentir</b> : après une modification faite directement dans la base, l'API a servi <b>{price_stale} alors que la base disait {price_db}</b>. Je borne la copie à 60 secondes, je l'invalide à chaque écriture par l'API, et je ne cache jamais l'achat. "
     f"Deuxième prix, ce que j'ai écarté : agrandir le pool n'atteint que {fr(pool20, 0)} requêtes par seconde, sur deux essais, donc indicatif ; PgBouncer limite les connexions de 40 à 5 mais fait tomber le débit de 261 à 94. Il limite, il n'accélère pas. Risque restant : une lecture lente peut remettre une copie ancienne après l'invalidation. "
     f"Réponse à ma question : le coût venait des allers-retours ; en les supprimant, le débit est multiplié par {fr(gr['debit_termine'] / n1['debit_termine'])} sans erreur, mesuré sur cette machine, ce jeu et 1 à 20 clients, et pas encore en production.",
     "Conclusion : mesuré ici ; à tester avant toute généralisation."),
]


# ------------------------------------------------------------------ rendu
def banner(c, kicker, title, i, n, secs, cumul, accent_txt):
    c.setFillColor(NAVY); c.rect(0, H - 70, W, 70, stroke=0, fill=1)
    txt(c, 28, H - 24, kicker.upper(), 9.5, True, CYAN)
    txt(c, 28, H - 52, title, 21, True, colors.white)
    txt(c, W - 28, H - 24, f"{i + 1} / {n}", 10, False, colors.white, "r")
    txt(c, W - 28, H - 40, accent_txt, 9, False, colors.HexColor("#f2c9b3"), "r")
    txt(c, W - 28, H - 54, f"à lire : environ {secs} s · cumul ≈ {cumul // 60} min {cumul % 60:02d} s", 8.5, False, colors.HexColor("#f2c9b3"), "r")


def footer(c, label):
    txt(c, 28, 20, f"{label} · ShopFlow, PostgreSQL 18 · mesures des 06 et 08/10/2026 · copie jetable, 3 essais alternés", 7.5, False, colors.HexColor("#6b7280"))


def deck_v1(path):
    c = canvas.Canvas(path, pagesize=(W, H)); c.setTitle("Présentation 5 min : version 1, structure de la fiche"); c.setAuthor("ShopFlow, Optimisation BDD")
    cum = 0; n = len(T1) + 1
    for i, (title, tm, text) in enumerate(T1):
        secs = round(len(re.sub("<[^>]+>", "", text).split()) / WPM * 60); cum += secs
        banner(c, f"Version 1 · structure de la fiche · {tm}", title, i, n, secs, cum, "problème → mécanisme → mesure → décision")
        if i == 0:
            v_flow_problem(c, 300); v_measure_table(c, 270)
        elif i == 1:
            v_code_before_after(c, 300); v_bars_cost(c, 235)
        elif i == 2:
            v_curves(c, 290); v_results_table(c, 360)
        elif i == 3:
            v_checks_and_cache(c, 300)
        else:
            v_decision(c, 300)
            box(c, VX0, 52, 450, 62, None, None, LIGHT, ACCENT)
            txt(c, VX0 + 12, 99, "3 CONCLUSIONS", 8.4, True, ACCENT)
            txt(c, VX0 + 12, 84, "1. J'ai observé 21 requêtes par page et un débit plafonné.", 8.4)
            txt(c, VX0 + 12, 71, f"2. En les ramenant à 2, le débit est ×{fr(gr['debit_termine'] / n1['debit_termine'])}, sans erreur.", 8.4)
            txt(c, VX0 + 12, 58, "3. Valable ici (machine, jeu, 1–20 clients) ; non testé en production.", 8.4)
        say(c, text); footer(c, "Version 1"); c.showPage()
    banner(c, "Version 1 · en réserve (non comptée dans les 5 minutes)", "Si on me pose la question", n - 1, n, 0, cum, "reproductibilité · conséquence pour l'API")
    v_qa(c, 300)
    say(c, "<b>Reproductibilité :</b> même base, mêmes versions, même protocole ; je compare l'ordre de grandeur, pas la valeur exacte.<br/><br/><b>Conséquence pour l'API :</b> contrat inchangé, moins de connexions occupées, fraîcheur bornée si cache, repli sur PostgreSQL si Redis tombe.<br/><br/><b>Variante rejetée :</b> agrandir le pool ou PgBouncer pour accélérer. <b>Risque restant :</b> la copie périmée du cache.")
    footer(c, "Version 1"); c.showPage(); c.save()
    return cum


def v2_tracker(c, act):
    x = VX0
    for k, a in enumerate(ACTS):
        on = k == act
        c.setFillColor(ACCENT if on else PALE); c.setStrokeColor(ACCENT if on else GRID); c.roundRect(x, H - 106, 86, 18, 4, stroke=1, fill=1)
        txt(c, x + 43, H - 100, a, 8, on, colors.white if on else INK, "c")
        x += 91
    cut = PROBLEM.index("D'où")
    txt(c, VX0, H - 120, "Fil rouge : " + PROBLEM[:cut].strip(), 7.2, False, colors.HexColor("#6b7280"))
    txt(c, VX0, H - 129, PROBLEM[cut:], 7.2, False, colors.HexColor("#6b7280"))


def deck_v2(path):
    c = canvas.Canvas(path, pagesize=(W, H)); c.setTitle("Présentation 5 min : version 2, avec fil rouge"); c.setAuthor("ShopFlow, Optimisation BDD")
    cum = 0; n = len(T2) + 1
    for i, (title, tm, act, text, trans) in enumerate(T2):
        secs = round(len(re.sub("<[^>]+>", "", text).split()) / WPM * 60); cum += secs
        banner(c, f"Version 2 · l'histoire · acte {i + 1} · {tm}", title, i, n, secs, cum, f"acte {i + 1} : {act.lower()}")
        v2_tracker(c, i)
        y0 = 22
        if i == 0:
            title_v(c, VX0, H - 142, "Une page de 20 commandes = 21 allers-retours")
            # 20 cartes + 1 liste vers la base
            for k in range(20):
                cx, cy = VX0 + (k % 10) * 22, H - 192 - (k // 10) * 26
                c.setFillColor(PALE); c.setStrokeColor(GRID); c.roundRect(cx, cy, 18, 20, 3, stroke=1, fill=1); txt(c, cx + 9, cy + 6, str(k + 1), 6.5, False, INK, "c")
            txt(c, VX0, H - 150 - 26 * 2 - 24, "20 commandes", 7.5, False, INK)
            box(c, VX0 + 270, H - 214, 90, 46, "Base", "PostgreSQL", PALE)
            for k in range(7):
                arrow(c, VX0 + 222, H - 198 + k * 4.6, VX0 + 270, H - 198 + k * 4.6, RED, 1.0)
            txt(c, VX0 + 246, H - 162, "21 requêtes", 8.5, True, RED, "c")
            txt(c, VX0 + 246, H - 238, "1 liste + 1 par commande", 7.5, False, RED, "c")
            tiles = [(f"≈ {fr(n1['debit_termine'], 0)}", "req/s : plafond dès 5 clients"), (f"{fr(n1['p95_ms'], 0)} ms", "latence p95 à 20 clients"), (f"{pool_wait}", "requêtes en attente d'une connexion")]
            for k, (big, small) in enumerate(tiles):
                bx = VX0 + k * 152
                box(c, bx, 250, 144, 64, big, small, PALE_RED, RED, RED, 20, 7.4)
        elif i == 1:
            title_v(c, VX0, H - 142, "Les suspects")
            th_ = table(c, VX0, H - 150, 450, [["Suspect", "Verdict", "Preuve"],
                                                ["La requête SQL", "<b>innocente</b>", f"{fr(float(pg_n1['moyenne_ms']), 3)} ms vue par PostgreSQL ; absente du journal des requêtes lentes"],
                                                ["Le pool de connexions", "conséquence", f"file jusqu'à {pool_wait} ; pool 20 : ≈ {fr(pool20, 0)} req/s seulement"],
                                                ["Les allers-retours", "<b>coupable</b>", f"21 par page ; {fr(per_q, 2)} ms chacun côté API"]], [100, 80, 270], size=8.6)
            v_bars_cost(c, 150)
        elif i == 2:
            v_code_before_after(c, H - 340)
            box(c, VX0, 170, 450, 62, None, None, PALE_GREEN, GREEN)
            txt(c, VX0 + 12, 214, "MÊME RÉSULTAT ✓", 9.5, True, GREEN)
            txt(c, VX0 + 12, 190, "JSON complet identique à 5, 20, 50 et 100 commandes · droits conservés (401 / 400 / 400)", 8.4)
            txt(c, VX0 + 12, 178, "21 requêtes → 2, quelle que soit la page ; un seul changement.", 8.4)
        elif i == 3:
            v_curves(c, H - 410); v_results_table(c, 205)
        else:
            v_checks_and_cache(c, 190)
            th_ = table(c, VX0, 150, 450, [["Variante rejetée", "Pourquoi"],
                                           ["Agrandir le pool 5 → 20", f"≈ {fr(pool20, 0)} req/s contre {fr(gr['debit_termine'], 0)} (2 essais, indicatif)"],
                                           ["PgBouncer pour accélérer", "40 → 5 connexions mais 261 → 94 transactions/s"]], [140, 310], size=8.2)
        # transition
        c.setFillColor(NAVY); c.roundRect(SX0, 14, W - SX0 - 24, 22, 4, stroke=0, fill=1); fs = 7.8
        while stringWidth(trans, "Sans-Bold", fs) > W - SX0 - 40 and fs > 5.5:
            fs -= 0.2
        txt(c, SX0 + 8, 21, trans, fs, True, colors.white)
        say(c, text, y0=44); footer(c, "Version 2 · fil rouge"); c.showPage()
    banner(c, "Version 2 · en réserve (non comptée dans les 5 minutes)", "Si on me pose la question", n - 1, n, 0, cum, "reproductibilité · conséquence pour l'API")
    v_qa(c, 300)
    say(c, "<b>Reproductibilité :</b> même base, mêmes versions, même protocole ; je compare l'ordre de grandeur.<br/><br/><b>Conséquence pour l'API :</b> contrat inchangé, moins de connexions occupées, fraîcheur bornée si cache, repli sur PostgreSQL si Redis tombe.<br/><br/><b>Phrase finale :</b> « le coût venait des allers-retours ; mesuré ici, pas encore en production. »")
    footer(c, "Version 2 · fil rouge"); c.showPage(); c.save()
    return cum


c1 = deck_v1(os.path.join(ROOT, "Presentation_V1_structure.pdf"))
c2 = deck_v2(os.path.join(ROOT, "Presentation_V2_histoire.pdf"))
print("V1 durée estimée à", WPM, "mots/min :", c1 // 60, "min", c1 % 60, "s | V2 :", c2 // 60, "min", c2 % 60, "s")
