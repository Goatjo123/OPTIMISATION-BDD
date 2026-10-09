"""Pages D-1 à D-9 du dossier final (Atelier 10), autonomes : chaque renvoi pointe une page des annexes jointes
(« annexe p. N » = page N numérotée en haut de l'annexe = page N + 11 du fichier). Aucun fichier extérieur n'est cité.
Les chiffres du tableau D-4 sont relus dans atelier9/resultats/p2_charge.json au moment de la construction."""
import io, json, os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = "/usr/share/fonts/truetype/dejavu/"
for n, f in (("S", "DejaVuSans"), ("SB", "DejaVuSans-Bold"), ("Mono", "DejaVuSansMono")):
    try: pdfmetrics.getFont(n)
    except KeyError: pdfmetrics.registerFont(TTFont(n, F + f + ".ttf"))
pdfmetrics.registerFontFamily("S", normal="S", bold="SB")
NAVY, ACC, GRID = colors.HexColor("#173a4d"), colors.HexColor("#b4532a"), colors.HexColor("#c9cfd6")
TEAL, RED, GREEN, GREY = colors.HexColor("#1f8a99"), colors.HexColor("#c4472b"), colors.HexColor("#2f8f5b"), colors.HexColor("#5b6670")
PRED, PGREEN, PALE = colors.HexColor("#f8dcd3"), colors.HexColor("#d6eee0"), colors.HexColor("#f4f6f8")
W, H = A4
fr = lambda x, n=1: f"{x:.{n}f}".replace(".", ",")


def P(t, s=8.4, l=None, f="S", color=colors.black, **k):
    return Paragraph(t, ParagraphStyle("p", fontName=f, fontSize=s, leading=l or s * 1.3, textColor=color, **k))


def H2(t): return P(t, s=11.5, l=15, f="SB", color=ACC, spaceBefore=6, spaceAfter=3)
def H3(t): return P(t, s=9.2, l=12, f="SB", color=NAVY, spaceBefore=5, spaceAfter=2)


def T(rows, widths, size=7.9, head=True, zebra=True, bold_first=False, pad=2.6):
    data = [[P(c, s=size, f="SB" if (head and i == 0) or (bold_first and j == 0) else "S", color=colors.white if head and i == 0 else colors.black) if isinstance(c, str) else c
             for j, c in enumerate(r)] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0, hAlign="LEFT")
    st = [("GRID", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad)]
    if head: st.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra: st += [("BACKGROUND", (0, k), (-1, k), PALE) for k in range(2 if head else 1, len(rows), 2)]
    t.setStyle(TableStyle(st)); return t


class Lines(Flowable):
    """Courbe à abscisses catégorielles (1, 5, 10, 20 clients), deux séries."""
    def __init__(self, title, xs, a, b, ymax, step, w=232, h=118, unit=""):
        super().__init__(); self.t, self.xs, self.a, self.b, self.ymax, self.step, self.w, self.h = title, xs, a, b, ymax, step, w, h
    def wrap(self, aw, ah): return self.w, self.h + 28
    def draw(self):
        c = self.canv; L, B, w, h = 30, 22, self.w - 40, self.h - 22
        c.setFont("SB", 8.4); c.setFillColor(NAVY); c.drawString(0, self.h + 16, self.t)
        c.setFont("S", 6.8); c.setStrokeColor(GRID); c.setLineWidth(.4)
        v = 0
        while v <= self.ymax + 1e-9:
            y = B + v / self.ymax * h; c.line(L, y, L + w, y); c.setFillColor(GREY); c.drawRightString(L - 4, y - 2, f"{v:,.0f}".replace(",", " ")); v += self.step
        px = [L + 8 + i * (w - 16) / (len(self.xs) - 1) for i in range(len(self.xs))]
        for i, x in enumerate(self.xs): c.setFillColor(GREY); c.drawCentredString(px[i], B - 11, str(x))
        c.drawCentredString(L + w / 2, B - 20, "clients simultanés")
        for ser, col, lab in ((self.a, RED, "N+1"), (self.b, TEAL, "groupé")):
            c.setStrokeColor(col); c.setFillColor(col); c.setLineWidth(1.6)
            pts = [(px[i], B + ser[i] / self.ymax * h) for i in range(len(ser))]
            for i in range(len(pts) - 1): c.line(*pts[i], *pts[i + 1])
            for x, y in pts: c.circle(x, y, 2, stroke=0, fill=1)
            c.setFont("SB", 7.6); c.drawRightString(pts[-1][0] + 8, pts[-1][1] + 5, f"{ser[-1]:,.0f}".replace(",", " "))
        c.setFont("S", 7); c.setFillColor(RED); c.rect(L + 6, self.h + 3, 6, 6, stroke=0, fill=1); c.setFillColor(colors.black); c.drawString(L + 15, self.h + 4, "N+1")
        c.setFillColor(TEAL); c.rect(L + 48, self.h + 3, 6, 6, stroke=0, fill=1); c.setFillColor(colors.black); c.drawString(L + 57, self.h + 4, "groupé")


class Flow(Flowable):
    """Chaîne de cases fléchées : [(titre, sous-titre, fond, contour)]."""
    def __init__(self, boxes, w=480, h=44): super().__init__(); self.boxes, self.w, self.h = boxes, w, h
    def wrap(self, aw, ah): return self.w, self.h
    def draw(self):
        c = self.canv; n = len(self.boxes); g = 22; bw = (self.w - g * (n - 1)) / n
        for i, (a, b, f, s) in enumerate(self.boxes):
            x = i * (bw + g); c.setFillColor(f); c.setStrokeColor(s); c.setLineWidth(1); c.roundRect(x, 0, bw, self.h, 5, stroke=1, fill=1)
            c.setFillColor(colors.black); c.setFont("SB", 8.4); c.drawCentredString(x + bw / 2, self.h - 16, a)
            c.setFillColor(GREY); c.setFont("S", 7); 
            for k, line in enumerate(b.split("|")): c.drawCentredString(x + bw / 2, self.h - 27 - k * 8.5, line)
            if i < n - 1:
                c.setStrokeColor(NAVY); c.setFillColor(NAVY); c.setLineWidth(1.3); c.line(x + bw + 3, self.h / 2, x + bw + g - 6, self.h / 2)
                p = c.beginPath(); p.moveTo(x + bw + g - 3, self.h / 2); p.lineTo(x + bw + g - 9, self.h / 2 + 3); p.lineTo(x + bw + g - 9, self.h / 2 - 3); p.close(); c.drawPath(p, fill=1, stroke=0)


class Bars(Flowable):
    def __init__(self, items, w=480): super().__init__(); self.items, self.w = items, w
    def wrap(self, aw, ah): return self.w, 14 * len(self.items) + 2
    def draw(self):
        c = self.canv; mx = max(v for _, v, _ in self.items)
        for i, (lab, v, col) in enumerate(self.items):
            y = (len(self.items) - 1 - i) * 14
            c.setFillColor(colors.black); c.setFont("S", 7.8); c.drawString(0, y + 2, lab)
            bw = max(3, v / mx * 150); c.setFillColor(col); c.rect(150, y, bw, 10, stroke=0, fill=1)
            c.setFillColor(col); c.setFont("SB", 8); c.drawString(156 + bw, y + 2, f"{fr(v, 3 if v < 0.1 else 2)} ms")


def page(label, story):
    buf = io.BytesIO()
    def deco(c, d):
        c.setFillColor(NAVY); c.rect(0, H - 31, W, 31, stroke=0, fill=1); c.setFillColor(colors.white)
        c.setFont("SB", 8.6); c.drawString(45, H - 19, "Optimisation BDD · ShopFlow · Dossier final (Atelier 10)"); c.setFont("S", 8.6); c.drawRightString(W - 45, H - 19, label)
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=39, rightMargin=39, topMargin=50, bottomMargin=36).build(story, onFirstPage=deco)
    buf.seek(0); return buf


d = json.load(open(os.path.join(ROOT, "atelier9/resultats/p2_charge.json")))["B_http_n1_groupe"]
M = {c: (d[c]["n1"]["mediane"], d[c]["groupe"]["mediane"]) for c in d}
CL = ["1", "5", "10", "20"]
SP = Spacer(1, 5)
pages = []

# ---------------------------------------------------------------- D-1
pages.append(("D-1", [
    H2("Inventaire des preuves déjà produites et choix de l'optimisation"),
    P("Chaque chiffre du dossier renvoie à une preuve <b>P-xx</b> (fiches en D-7) et à une page des annexes jointes (« annexe p. N », numéro en haut de la page ; voir D-9)."), SP,
    T([["Famille", "Résultat mesuré (preuve déjà réalisée)", "Où", "Rôle ici"],
       ["Plans et index", "Atelier 3 : index composé (client_id, created_at DESC, id DESC) : ×2,5 sur la requête de l'API, ×91 pour un client à 20 100 commandes, WAL +35 % ; retenu, migration écrite et non appliquée au laboratoire. Atelier 4 : index partiel 10,1 → 0,070 ms (×144,6, 1 680 → 3 buffers), inutile hors de son prédicat", "annexe p. 7-15", "contexte"],
       ["Réécriture et tuning", "Atelier 2 : EXISTS 11,3 ms contre jointure 27,6 ms (la jointure répète le client 42 cent fois). Agrégation mensuelle sur copie : 84,6 → 50,2 ms (work_mem 32 MB) ou 45,5 ms (statistique), même résultat (md5)", "annexe p. 1-6, 62", "contexte"],
       ["Migration", "Atelier 4 bis : NOT NULL direct = 3 324,1 ms sous verrou exclusif, migration progressive = 46,3 ms ; remplissage 2,7 fois plus long ; retour arrière vérifié", "annexe p. 16-18", "contexte"],
       ["API", "Atelier 7 : <b>N+1 21 → 2 requêtes</b> ; curseur contre OFFSET à 1 000 000 de commandes : 944,3 → 0,177 ms, identique à petite profondeur", "annexe p. 19-20", "<b>principal</b>"],
       ["Pooling", "Atelier 7 : PgBouncer 40 → 5 connexions mais 261 → 94 transactions/s ; Jour 5 : pool 5 / 10 / 20", "annexe p. 21, 63 ; P-06, P-07", "variante rejetée"],
       ["Cache", "Atelier 8 : miss 2,7 ms, hit 0,988 ms ; 57.50 servi pour 19.90 ; invalidation, expiration, repli, course", "annexe p. 22-24", "<b>fraîcheur</b>"],
       ["Charge", "Jour 5 : courbe 1/5/10/20 clients (N+1 ×4,2), charge ouverte (503 à 130 %), rapport concurrent p95 +64 %", "annexe p. 63-64 ; P-05, P-12", "<b>principal</b>"],
       ["Donnée moderne", "Jour 5 : export journalier CSV (240 lignes, 80 000 commandes payées, montant exact), contrat de données ; Lakehouse et Data Mesh conçus, non déployés", "annexe p. 65, 71", "contexte"],
       ["Non réalisé", "Réplication, partitionnement, sharding : aucune preuve produite", "—", "absent"]],
      [74, 262, 76, 68], 7.7), SP,
    P("<b>Choix.</b> Une optimisation forte plutôt que plusieurs gains isolés : le chargement groupé de GET /commandes (problème → mécanisme → mesure → limite complets), avec le cache Redis comme preuve de fraîcheur. Les autres familles sont des preuves de contexte ; elles ne sont pas redéfendues ici.")]))

# ---------------------------------------------------------------- D-2
a20, b20 = M["20"]
pages.append(("D-2", [
    H2("A. Besoin et état initial"),
    T([["Élément", "Contenu", "Preuve"],
       ["Endpoint", "GET /commandes?limit=20 : écran « mes commandes » du client 42, 20 commandes avec leurs lignes (3 lignes par commande)", "P-03"],
       ["Volume", "100 000 commandes, 1 000 clients, 300 000 lignes ; client 42 : 100 commandes (5 pages de 20)", "P-03, P-14"],
       ["Charge", "1, 5, 10 et 20 clients simultanés (charge fermée), 10 s de mesure après 3 s d'échauffement, 3 essais alternés", "P-05"],
       ["Problème observable", f"À 20 clients : {fr(a20['debit_termine'])} req/s, p95 {fr(a20['p95_ms'])} ms, file du pool jusqu'à 15 requêtes, CPU ≈ 50 %, 0 erreur. Le débit plafonne dès 5 clients ({fr(M['5'][0]['debit_termine'],0)} → {fr(M['10'][0]['debit_termine'],0)} → {fr(a20['debit_termine'],0)} req/s) : le service est saturé sans erreur.", "P-01"],
       ["Métrique de référence", f"Débit terminé et p95 de GET /commandes à 20 clients, N+1, pool de 5 connexions : {fr(a20['debit_termine'])} req/s ; {fr(a20['p95_ms'])} ms", "P-01"]],
      [92, 330, 58], 8, bold_first=True),
    H2("B. Architecture et stockage"),
    P("Chaîne réellement utilisée (schéma en page 2) : générateur de charge → API Node 22.14 (pool de 5 connexions) → PostgreSQL 18.6, avec Redis 8.10.2 pour la fiche produit.", s=8.4), SP,
    T([["Composant réellement utilisé", "Détail", "Preuve"],
       ["PostgreSQL 18.6", "Laboratoire : schéma shopflow (100 000 commandes, 300 000 lignes, 6 index issus des contraintes). L'index composé de l'atelier 3 a été testé puis supprimé, sa migration est écrite mais non appliquée au laboratoire ; la migration progressive de l'atelier 4 bis a été rejouée sur une copie", "P-13"],
       ["Redis 8.10.2", "Cache-aside de la fiche produit : miss = 1 SELECT, puis copie avec TTL 60 s ; l'écriture (PATCH) supprime la clé ; politique allkeys-lru", "P-08"],
       ["Pool de l'API", "POOL_MAX = 5 sauf série pool ; abandon après 1 s d'attente (connectionTimeoutMillis = 1000, réponse 503)", "P-06, P-12"],
       ["Hors périmètre", "Réplication, partitionnement, sharding : non réalisés ; Lakehouse et Data Mesh : conçus, non déployés", "—"]],
      [92, 330, 58], 8, bold_first=True)]))

# ---------------------------------------------------------------- D-3
pages.append(("D-3", [
    H2("C. Intervention principale : un seul changement, 21 requêtes → 2"),
    T([["Question de la fiche", "Réponse"],
       ["Hypothèse causale", "Le plafond vient du <b>nombre d'allers-retours</b> (une requête de lignes par commande : 1 + N = 21), pas de la requête SQL ni de la taille du pool."],
       ["Changement (un seul)", "relations=n1 → relations=groupe : une requête de lignes pour toute la page, <font name='Mono'>WHERE commande_id = ANY($1::bigint[])</font> ; ni index, ni pool, ni base modifiés."]],
      [105, 375], 8, bold_first=True), SP,
    Table([[P("<b>Avant (N+1)</b>", s=8, color=colors.white), P("<b>Après (groupé)</b>", s=8, color=colors.white)],
           [P("rows = SELECT … commandes LIMIT 20;<br/>POUR CHAQUE commande :<br/>&nbsp;&nbsp;SELECT … FROM lignes<br/>&nbsp;&nbsp;WHERE commande_id = $1;<br/>-- 1 + 20 = 21 requêtes", f="Mono", s=7.4),
            P("rows = SELECT … commandes LIMIT 20;<br/>SELECT … FROM lignes<br/>&nbsp;&nbsp;WHERE commande_id =<br/>&nbsp;&nbsp;&nbsp;&nbsp;ANY($1::bigint[]);<br/>-- 2 requêtes, toujours", f="Mono", s=7.4)]],
          colWidths=[240, 240], hAlign="LEFT", style=TableStyle([("BACKGROUND", (0, 0), (0, 0), RED), ("BACKGROUND", (1, 0), (1, 0), GREEN), ("BACKGROUND", (0, 1), (0, 1), PRED), ("BACKGROUND", (1, 1), (1, 1), PGREEN),
                                                    ("GRID", (0, 0), (-1, -1), .4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP")])),
    H3("Trace montrant le mécanisme (P-02, P-03)"),
    T([["Observation", "N+1", "Groupé", "Lecture"],
       ["Requêtes SQL par page de 20 / 50 / 100 commandes", "21 / 51 / 101", "2 / 2 / 2", "croît avec N, contre constant"],
       ["pg_stat_statements : appels de la requête de lignes (1 200 pages)", "20 000 × 0,018 ms", "200 × 0,186 ms", "le signal est le nombre d'appels"],
       ["Journal des requêtes lentes (seuil 20 ms)", "requête de lignes absente", "absente", "0 ligne sur 1 249"],
       ["Temps dans l'API (sqlMs, page de 20)", "14,2 ms (≈ 0,68 ms × 21)", "2,2 ms", "environ 38 fois le temps vu par PostgreSQL (0,018 ms)"]],
      [150, 100, 80, 150], 7.8), SP,
    Bars([("vu par PostgreSQL (1 requête)", 0.018, GREEN), ("vu par l'API (1 requête, aller-retour)", 0.68, RED)]),
    H3("Suspects écartés"),
    T([["Suspect", "Verdict", "Preuve"],
       ["La requête SQL", "innocente", "0,018 ms vue par PostgreSQL ; absente du journal lent ; non classée par temps cumulé (P-02)"],
       ["Le pool de connexions", "conséquence", "file jusqu'à 15 ; pool de 20 : 276 à 299 req/s, loin de 1 032 (P-06)"],
       ["Les allers-retours", "<b>cause retenue</b>", "21 par page, chacun environ 38 fois plus cher côté API que côté PostgreSQL (P-02)"]],
      [95, 75, 310], 7.9), SP,
    P("<b>Limite du mécanisme.</b> Sur une page isolée le gain de durée est modeste (HTTP 55,3 → 43,9 ms, base locale, aucun autre client) : il devient grand sous concurrence, parce que chaque page occupe une connexion du pool pendant 21 allers-retours (P-03, P-05).", s=8, color=GREY)]))

# ---------------------------------------------------------------- D-4
rows = [["Clients", "N+1 req/s", "p50 ms", "p95 ms", "Err.", "Groupé req/s", "p50 ms", "p95 ms", "Err."]]
for c in CL:
    n, g = M[c]
    rows.append([c, fr(n["debit_termine"]), fr(n["mediane_ms"]), fr(n["p95_ms"]), "0", fr(g["debit_termine"]), fr(g["mediane_ms"]), fr(g["p95_ms"]), "0"])
fa = [e["debit_termine"] for e in d["20"]["n1"]["essais"]]; fb = [e["debit_termine"] for e in d["20"]["groupe"]["essais"]]
pages.append(("D-4", [
    H2("D. Benchmark avant / après (même protocole, un seul changement)"),
    P("<b>Protocole.</b> Charge fermée sur GET /commandes?limit=20 (mêmes 20 commandes), 1/5/10/20 clients, <b>10 s de mesure après 3 s d'échauffement</b>, 3 essais en ordre alterné (N+1, groupé, N+1…), médiane retenue ; API, PostgreSQL et générateur sur la même machine (i5-10310U, 8 cœurs, 7,6 Go, WSL2). Sorties brutes de chaque essai : annexe p. 70-71 (P-05)."), SP,
    T(rows, [48, 70, 46, 50, 38, 80, 46, 50, 38], 8), P("Médiane de 3 essais par ligne ; erreurs = réponses non 200 (0 partout).", s=7.4, color=GREY), SP,
    Table([[Lines("Requêtes terminées par seconde", CL, [M[c][0]["debit_termine"] for c in CL], [M[c][1]["debit_termine"] for c in CL], 1200, 300),
            Lines("Latence p95 (ms)", CL, [M[c][0]["p95_ms"] for c in CL], [M[c][1]["p95_ms"] for c in CL], 120, 30)]], colWidths=[245, 235]),
    H3("Lecture de la saturation et reproductibilité"),
    T([["Constat à 20 clients", "N+1", "Groupé", "Effet"],
       ["Débit médian", f"{fr(a20['debit_termine'])} req/s", f"{fr(b20['debit_termine'])} req/s", f"<b>×{fr(b20['debit_termine']/a20['debit_termine'])}</b>"],
       ["p95 médian", f"{fr(a20['p95_ms'])} ms", f"{fr(b20['p95_ms'])} ms", f"<b>−{round((1-b20['p95_ms']/a20['p95_ms'])*100)} %</b>"],
       ["3 essais (req/s)", f"{fr(min(fa),0)} à {fr(max(fa),0)}", f"{fr(min(fb),0)} à 1 082", "intervalles disjoints : reproductible"],
       ["CPU moyen de la machine / erreurs", "50,2 % / 0", "50,1 % / 0", "le gain vient du travail évité, pas d'une ressource en plus"]],
      [130, 80, 80, 190], 8), SP,
    P("<b>Saturation.</b> Le N+1 plafonne dès 5 clients : les clients supplémentaires n'ajoutent que de l'attente (file du pool jusqu'à 15). Le groupé plafonne plus haut (≈ 1 032 req/s) avec 5 connexions seulement ; à 20 clients pour 5 connexions une file subsiste (jusqu'à 14), mais chaque page garde sa connexion moins longtemps. La charge fermée masque l'effondrement : en charge ouverte à 90 % du débit fermé le comportement est instable (un essai p95 359 ms, l'autre 503), à 130 % presque tout échoue en 503 (P-12, annexe p. 64) ; ces essais sont présentés un par un, sans médiane.")]))

# ---------------------------------------------------------------- D-5
pages.append(("D-5", [
    H2("E. Correction et fiabilité"),
    H3("1. Invariant fonctionnel : le résultat est identique (P-03, P-04)"),
    T([["Contrôle", "Obtenu", "Attendu"],
       ["JSON complet (commandes et lignes) N+1 = groupé, pages de 5 / 20 / 50 / 100", "identique ; 6 / 21 / 51 / 101 SQL contre 2", "même contenu"],
       ["Sans jeton / client_id injecté dans l'URL / curseur falsifié", "401 / 400 / 400", "refus"],
       ["Laboratoire après les tests (P-14)", "6 index, 0 statistique étendue, md5 des commandes inchangé", "inchangé"]],
      [235, 165, 80], 8), 
    H3("2. Fraîcheur du cache Redis : ce qu'il gagne, ce qu'il peut faire mentir (P-08 à P-11)"),
    Flow([("Base", "prix 57.50 → 19.90|(UPDATE direct en SQL)", PGREEN, GREEN), ("Redis (TTL 60 s)", "copie : 57.50|jamais prévenu", PRED, RED),
          ("API sert", "57.50 (hit, 0 SQL)|la base dit 19.90", PRED, RED), ("PATCH par l'API", "UPDATE puis DEL|GET suivant : nouveau prix", PGREEN, GREEN)]), SP,
    T([["Scénario", "Résultat mesuré", "Ce que ça établit"],
       ["Miss puis hit (100 paires, connexion persistante)", "miss : 1 SELECT, 2,7 ms ; hit : 0 SQL, 0,988 ms (×2,7)", "gain petit (base locale, clé primaire) ; le vrai gain est la charge évitée"],
       ["UPDATE direct en SQL, puis lecture API", "l'API sert 57.50 (hit, 0 SQL), la base a 19.90 ; après DEL : 19.90", "le TTL n'actualise pas la copie : elle reste périmée jusqu'au DEL ou à l'expiration"],
       ["PATCH par l'API (29.90), puis 2 lectures", "invalidation = ok ; 1er GET : 29.90 (miss) ; 2e GET : hit, 0 SQL", "le chemin d'écriture prévu invalide la copie"],
       ["Expiration", "TTL 60 → −2 après 61 s ; relecture : miss, 1 SELECT", "le TTL borne la copie périmée à 60 s"],
       ["Redis arrêté", "200, Cache = indisponible, 1 SELECT par lecture", "repli correct, mais toute la charge revient à PostgreSQL"],
       ["PATCH avec Redis arrêté", "invalidation = échouée ; base 34.90 ; copie 29.90 servie au retour de Redis", "l'écriture est valide, la copie reste ancienne"],
       ["Course lecture lente / invalidation (à la main)", "A lit 34.90 ; B écrit 39.90 puis supprime la clé ; A range 34.90 : l'API sert 34.90, la base a 39.90", "supprimer la clé ne supprime pas toutes les courses (pistes : version, invalidation rejouée)"],
       ["Rafale : 20 lectures simultanées, clé absente", "6 miss, 6 SELECT au lieu d'un ; clé présente : 20 hit, 0 SQL", "une mesure, non répétée ; chiffre non reproductible à l'unité près"]],
      [118, 192, 170], 7.8), SP,
    P("<b>Garantie retenue.</b> Redis n'est pas la source de vérité : fraîcheur acceptée de quelques secondes à 60 s pour la fiche catalogue ; la validation d'un achat lit prix et stock dans PostgreSQL, jamais dans le cache.")]))

# ---------------------------------------------------------------- D-6
pages.append(("D-6", [
    H2("F. Décision et limites"),
    T([["", "Contenu", "Preuve"],
       ["Retenu", "Chargement groupé : 21 → 2 requêtes, débit ×4,2, p95 −73 %, 0 erreur, réponse identique. Cache de la fiche produit avec TTL 60 s et invalidation par PATCH.", "P-02 à P-05, P-08"],
       ["Variante rejetée n° 1 : agrandir le pool 5 → 20", "Supprime l'attente (0 au lieu de 15) mais seulement 276 à 299 req/s contre 1 032 avec le groupé et 5 connexions ; 2 essais, indicatif.", "P-06"],
       ["Variante rejetée n° 2 : PgBouncer (mode transaction)", "Connexions 40 → 5 mais débit 260,7 → 93,8 transactions/s, latence 153 → 422 ms : il borne les connexions, il n'accélère rien.", "P-07"],
       ["Coûts", "Groupé : aucun index ni écriture en plus ; liste de 100 identifiants au plus par requête (limite de page de l'API) ; regroupement des lignes en mémoire. Cache : copie périmée jusqu'à 60 s, plus de SELECT si Redis tombe.", "P-03, P-09, P-10"],
       ["Risques restants", "Course entre lecture lente et invalidation (reproduite à la main, non corrigée) ; rafale de rechargements sur clé absente ; invalidation échouée = copie ancienne jusqu'au TTL.", "P-10, P-11"],
       ["Tests encore nécessaires", "Plusieurs instances d'API ; réseau réel (le gain devrait croître avec la latence, non mesuré) ; plus de 20 clients ; mesures de 30 s ; production.", "—"],
       ["Conclusion testable", "<b>Valable ici</b> : cette machine (8 cœurs, 7,6 Go, WSL2), ce jeu (100 000 commandes, 1 000 clients), GET /commandes?limit=20, 1 à 20 clients, 10 s après 3 s d'échauffement. <b>Non établi</b> : un gain en production ; le comportement avec plusieurs instances d'API ; que l'index composé (atelier 3) ou le cache accélèrent « tout PostgreSQL ». La fiche cite 10 s d'échauffement et 30 s de mesure comme exemple : mon protocole est plus court, l'écart entre séries (×4) dépasse l'écart entre essais d'une même série.", "—"]],
      [112, 305, 63], 8, head=True, bold_first=True)]))

# ---------------------------------------------------------------- D-7
FI = [("P-01 ÉTAT-INITIAL", "Quel problème observe-t-on sur GET /commandes ?", "N+1, pool 5, 20 clients fermés, 10 s après 3 s, médiane de 3", "annexe p. 63, 70", f"{fr(a20['debit_termine'])} req/s, p95 {fr(a20['p95_ms'])} ms, file du pool 15, 0 erreur : saturé sans erreur", "charge fermée, une machine"),
      ("P-02 PGSS-N1", "Le coût du N+1 est-il dans le SQL ?", "copie jetable (PostgreSQL 18.6, md5 identiques au laboratoire), pg_stat_statements ; 1 000 pages N+1 + 200 groupées", "annexe p. 68, 20", "20 000 appels × 0,018 ms, absente du journal lent ; API : 14,2 ms pour 21 requêtes (≈ ×38 par requête)", "le signal est le nombre d'appels, pas la durée"),
      ("P-03 COMPTAGE-ÉQUIV", "Le groupé donne-t-il le même résultat avec moins de requêtes ?", "client 42, 100 commandes ; mêmes commandes en relations=n1 puis groupe ; comptage par TraceId", "annexe p. 19-20, 53", "6/21/51/101 SQL contre 2 ; JSON identique ; HTTP 55,3 → 43,9 ms (page isolée)", "base locale : gain de durée modeste hors concurrence"),
      ("P-04 DROITS", "Les droits sont-ils conservés ?", "appels sans jeton, avec client_id dans l'URL, avec curseur falsifié", "annexe p. 19, 54", "401 / 400 / 400", "testé sur cet endpoint seulement"),
      ("P-05 BENCH-COURBE", "Le gain tient-il quand la concurrence augmente ?", "1/5/10/20 clients, 10 s après 3 s, 3 essais alternés, un seul changement", "annexe p. 63, 70-71", "N+1 ≈ 250 req/s dès 5 clients ; groupé ≈ 1 032 ; à 20 clients ×4,2, p95 −73 %, essais disjoints (238 à 253 contre 978 à 1 082)", "générateur et API sur la même machine ; 10 s (fiche : 30 s en exemple)"),
      ("P-06 POOL", "Agrandir le pool suffit-il ?", "N+1, 20 clients, POOL_MAX 5 / 10 / 20, 2 essais par taille", "annexe p. 63, 70", "pool 20 : attente 0, 276 à 299 req/s contre 137 à 216 à pool 5 ; loin de 1 032", "2 essais, pool 5 instable : indicatif"),
      ("P-07 PGBOUNCER", "PgBouncer accélère-t-il ?", "laboratoire séparé, 5 connexions serveur, mode transaction, 40 clients persistants, médiane de 3", "annexe p. 21, 55", "connexions 40 → 5 ; 260,7 → 93,8 tps ; latence 153 → 422 ms", "campagnes de 20 s ; test à 10 clients instable (ordre inversé)"),
      ("P-08 CACHE-HITMISS", "Combien de travail le cache évite-t-il ?", "produit 42, clé shopflow:produit:v1:42, TTL 60 s, 100 paires miss/hit, connexion persistante", "annexe p. 23, 57-58", "miss : 1 SELECT, 2,7 ms ; hit : 0 SQL, 0,988 ms (×2,7)", "gain absolu petit : base locale, accès par clé primaire"),
      ("P-09 CACHE-STALE", "Que sert l'API après une modification SQL directe ?", "UPDATE prix = 19.90 en SQL sans passer par l'API, puis lecture", "annexe p. 22-23, 58", "l'API sert 57.50 (hit, 0 SQL) alors que la base a 19.90 ; après DEL : 19.90", "un produit, un processus API"),
      ("P-10 CACHE-INVALID", "Invalidation, expiration et repli fonctionnent-ils ?", "PATCH 29.90 ; attente 61 s ; Redis arrêté ; PATCH 34.90 avec Redis arrêté", "annexe p. 22-23, 58", "invalidation ok puis miss ; TTL 60 → −2 ; Redis arrêté : 200 et 1 SELECT ; invalidation échouée : base 34.90, copie 29.90", "seul TTL testé : 60 s"),
      ("P-11 CACHE-COURSE", "Supprimer la clé après l'écriture suffit-il ?", "course lecture lente / invalidation reproduite à la main ; rafale de 20 lectures", "annexe p. 23, 59", "course : l'API sert 34.90, la base a 39.90 ; rafale : 6 miss et 6 SELECT", "course non reproduite sous charge ; rafale non répétée"),
      ("P-12 CHARGE-OUVERTE", "La charge fermée masque-t-elle la saturation ?", "N+1, pool 5, arrivées à cadence fixe : 50 %, 90 %, 130 % du débit fermé, 2 essais", "annexe p. 64, 71", "50 % : tient ; 90 % : un essai p95 359 ms, l'autre 503 ; 130 % : presque tout en 503 (pool 1 s)", "comportement bimodal : pas de médiane"),
      ("P-13 STOCKAGE", "Quels éléments de gestion de la donnée sont réellement déployés ?", "ateliers 3, 4 bis, 8 : DDL, index testés, migration progressive, Redis ; état du laboratoire vérifié avant et après chaque test", "annexe p. 7-18, 48-52", "laboratoire : 6 index de contraintes, cache Redis en service (P-08) ; index composé et migration par lots testés, non appliqués au laboratoire", "pas de réplication, partitionnement ni sharding"),
      ("P-14 MÉTHODE-ENV", "Un autre poste peut-il reproduire la mesure ?", "versions, copie jetable, empreintes md5, scripts de charge", "annexe p. 68, 71", "PostgreSQL 18.6, Node 22.14, md5 commandes 7505112bb794 et lignes e989d5bec39b identiques laboratoire / copie ; campagne : 16 min", "WSL2, 8 cœurs ; journaux pgbench par transaction non conservés")]
head = [["ID · Question", "Conditions · Action", "Résultat brut (où)", "Interprétation", "Limite"]]
body = [[f"<b>{a.split(' ')[0]}</b> {' '.join(a.split(' ')[1:])}<br/>{q}", c, w, i, l] for a, q, c, w, i, l in FI]
pages.append(("D-7", [H2("Fiches d'identité des preuves"),
                      P("Chaque fiche donne : identifiant · question · conditions et action · résultat brut (page de l'annexe) · interprétation · limite.", s=8, color=GREY), SP,
                      T(head + body, [92, 112, 56, 128, 92], 7.0)]))

# ---------------------------------------------------------------- D-8
EV = [["Besoin", "endpoint, volume et problème définis", "directe", "P-01, P-03"],
      ["Stockage", "un élément de gestion de la donnée réellement déployé", "directe (PostgreSQL, Redis en service ; index testés, non appliqués)", "P-13, P-08"],
      ["Correction", "résultat, droits et invariants valides après l'intervention", "directe", "P-03, P-04"],
      ["Méthode", "protocole reproductible : versions, jeu, charge, durée, commandes", "directe ; 10 s après 3 s, plus court que l'exemple de la fiche", "P-14, P-05"],
      ["Intervention", "le mécanisme explique le gain", "directe (appels, temps par requête)", "P-02, P-03"],
      ["Mesure", "avant/après comparable, p95/débit/erreurs, sorties brutes", "directe ; journaux pgbench non conservés (séries SQL)", "P-05"],
      ["Fiabilité / fraîcheur", "panne, reprise, cache ou migration vérifié", "directe (cache : stale, invalidation, expiration, panne, course)", "P-09, P-10, P-11"],
      ["Limites", "coûts, risques et conditions de généralisation exposés", "directe", "P-06, P-07, P-12 · section F"]]
CK = ["Besoin et état initial compréhensibles sans explication orale|A", "Architecture et stockage réellement déployés visibles|B, P-13", "Chaque chiffre annoncé renvoie à une mesure réelle et à son protocole|P-01 à P-14",
      "Benchmark avant/après aux mêmes conditions sauf le changement étudié|D, P-05", "p95, débit et erreurs présents ; unités indiquées|D", "Résultat fonctionnel vérifié, pas seulement la vitesse|E, P-03, P-04",
      "Preuve de fiabilité ou de fraîcheur documentée|E, P-09 à P-11", "Variante rejetée et risque restant expliqués|F, P-06, P-07", "Conclusion limitée à la machine, au jeu et à la charge testés|F",
      "Sorties brutes, plans, traces ou TraceId conservés|annexes, D-9"]
pages.append(("D-8", [
    H2("Auto-évaluation B4C8 avant remise"),
    T([["Critère", "Preuve suffisante si…", "Statut", "Référence"]] + EV, [70, 170, 150, 90], 7.2, bold_first=True, pad=1.6),
    H3("Les deux questions"),
    P("<b>Reproductibilité : « Si je vous donne un autre poste, comment reproduisez-vous exactement votre mesure ? »</b>", s=8.2),
    T([["1", "Créer la base avec 01_schema.sql et 02_donnees.sql (PostgreSQL 18.6) et vérifier les empreintes md5 : commandes 7505112bb794…, lignes e989d5bec39b… (P-14)."],
       ["2", "Démarrer l'API (Node 22.14, pool de 5 connexions, port 3001) puis lancer la campagne de charge décrite en annexe p. 68 et 71 (≈ 16 min : 1/5/10/20 clients, 10 s après 3 s, 3 essais alternés)."],
       ["3", "Comparer l'ordre de grandeur et les intervalles, pas la valeur exacte : plafond du N+1 ≈ 250 req/s et du groupé ≈ 1 030 req/s, essais disjoints. Un autre matériel donne d'autres valeurs absolues."]],
      [16, 464], 7.4, head=False, zebra=False, pad=1.6),
    P("<b>Conséquence pour l'API : « Qu'est-ce que votre décision change ? »</b>", s=8.2, spaceBefore=4),
    T([["Contrat", "inchangé : même JSON, mêmes droits (401 / 400 / 400) (P-03, P-04)"],
       ["Disponibilité", "2 allers-retours par page au lieu de 21 : à 5 connexions le débit est ×4,2 ; Redis arrêté : l'API répond 200 en repli sur PostgreSQL (P-10)"],
       ["Fraîcheur", "fiche produit : copie jusqu'à 60 s, périmée après une modification SQL directe (57.50 pour 19.90) ; l'achat lit PostgreSQL (P-09)"],
       ["Ressources", "aucun index ni écriture en plus ; au plus 100 identifiants par requête de lignes ; en cas de repli, une lecture SQL par appel (P-10)"]],
      [70, 410], 7.4, head=False, zebra=False, bold_first=True, pad=1.6),
    H3("Checklist de remise"),
    T([["Vérification", "OK", "Où"]] + [[x.split("|")[0], "✔", x.split("|")[1]] for x in CK], [330, 30, 120], 7.2, pad=1.5),
    H3("Formulation finale"),
    P(f"<b>1. Observé.</b> À 20 clients, GET /commandes?limit=20 en N+1 plafonne à {fr(a20['debit_termine'])} req/s (p95 {fr(a20['p95_ms'])} ms, file du pool jusqu'à 15, CPU 50 %, 0 erreur) pour 21 requêtes SQL par page.", s=7.6, spaceAfter=1),
    P(f"<b>2. Pourquoi.</b> Chaque page paie 21 allers-retours, environ 0,68 ms chacun côté API contre 0,018 ms côté PostgreSQL ; le chargement groupé les ramène à 2 sans changer la réponse, d'où {fr(b20['debit_termine'])} req/s et un p95 de {fr(b20['p95_ms'])} ms (3 essais disjoints). Agrandir le pool ou ajouter PgBouncer ne produit pas cet effet.", s=7.6, spaceAfter=1),
    P("<b>3. Conditions.</b> Je recommande le chargement groupé sur cette machine, ce jeu et 1 à 20 clients ; le cache de la fiche produit est acceptable avec un TTL de 60 s car il peut servir une valeur périmée (57.50 pour 19.90) ; il reste à tester plusieurs instances d'API, un réseau réel, des mesures de 30 s et la production.", s=7.6)]))

# ---------------------------------------------------------------- D-9
PJ = [["Preuve", "Sortie brute dans ce fichier (page de l'annexe)"],
      ["P-01 P-05 P-06 P-12", "p. 63-64 (courbes, séries C et D) ; p. 70-71 (11.7 : chaque essai)"],
      ["P-02", "p. 68 (11.2 pg_stat_statements, 11.3 journal lent) ; p. 20 et 53 (sqlMs par TraceId)"],
      ["P-03 P-04", "p. 19-20 (comptage, droits) ; p. 53-54 (9.3 à 9.6)"], ["P-07", "p. 21 ; p. 55 (9.8 campagnes brutes)"],
      ["P-08", "p. 23 ; p. 57-58 (10.3, 10.6)"], ["P-09 P-10", "p. 22-23 ; p. 58 (10.4, 10.5)"], ["P-11", "p. 23 ; p. 59 (10.7 rafale)"],
      ["P-13", "p. 7-18 (ateliers 3 et 4, 4 bis) ; p. 48-52 (annexe 8)"], ["P-14", "p. 68 (11.1 environnement) ; p. 71 (11.8 rejouer)"]]
pages.append(("D-9", [
    H2("Pièces jointes : où trouver la sortie brute de chaque preuve"),
    P("Ce fichier contient la couverture, la page de contexte, le dossier (D-1 à D-9), puis l'annexe complète : pages 1 à 59 (ateliers 1 à 8 et leurs preuves), 60 à 67 (chapitre du Jour 5) et 68 à 71 (annexe 11). "
      "<b>« annexe p. N »</b> désigne la page <b>N</b> de l'annexe, numérotée en haut de la page ; elle se trouve à la page <b>N + 11</b> de ce fichier.", s=8.8, l=12), SP,
    T(PJ, [110, 370], 8), SP,
    H3("Ce qui n'est pas dans les pièces"),
    P("Réplication, partitionnement et sharding : aucune preuve produite. Journaux de latence par transaction de pgbench (séries SQL) : non conservés, seules leurs statistiques le sont (annexe p. 68).", s=8.6, l=11.5)]))


def build():
    return [page(lbl, story) for lbl, story in pages]
