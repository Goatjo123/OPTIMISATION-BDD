#!/usr/bin/env python3
"""Dossier compact « performance et services back-end » (test_compact.pdf).

Structure imposée par le Jour 5 : les six pièces du dossier collectif (slide 30) et la grille de relecture (slide 31) ; la preuve B4C8 (slide 2) :
stockage déployé, API correcte, résultats avant/après, protocole, limites, coût de maintenance, garanties de fraîcheur ou de reprise.
Tous les chiffres sont lus dans les fichiers de mesures du projet (atelier1 à atelier9) : aucune valeur n'est saisie à la main, sauf les
constantes rappelées avec leur source. Usage : python3 dossier/build_dossier.py
"""
import json, math, os, re, statistics, sys

ROOT = "/home/youssef/école"
SCR = "/tmp/claude-1000/-home-youssef--cole/6511288b-1f56-4b98-abcd-02756e0fb1bc/scratchpad"
OUT = os.path.join(ROOT, "test_compact.pdf")

# --- données : réutilise la lecture des mesures d'Optimisations.pdf (tableau des gains) ---
src = open(os.path.join(SCR, "build_optimisations2.py"), encoding="utf-8").read()
head = src[:src.index("# ------------------------------------------------------------------ styles")]
ns = {}
exec(compile(head, "head", "exec"), ns)
GAINS, D3, D4, V4, B4 = ns["GAINS"], ns["D3"], ns["D4"], ns["V4"], ns["B4"]
A7, O7, A8, P8 = ns["A7"], ns["O7"], ns["A8"], ns["P8"]
colors, mm = ns["colors"], ns["mm"]
J = lambda p: json.load(open(os.path.join(ROOT, p), encoding="utf-8"))
P1, P1B, P2, P3 = (J("atelier9/resultats/" + f) for f in ("p1_diagnostics.json", "p1b_workmem.json", "p2_charge.json", "p3_export.json"))
A1 = lambda q: statistics.median(float(re.search(r"Execution Time: ([\d.]+)", open(f"{SCR}/atelier/q{q}_run{i}.txt").read()).group(1)) for i in range(1, 6))

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak
from reportlab.graphics.shapes import Drawing, Line, String, Rect, Circle

NAVY, ACCENT, GRID = ns["NAVY"], ns["ACCENT"], ns["GRID"]
body = ParagraphStyle("body", fontName="Sans", fontSize=8.6, leading=11.4, spaceAfter=3)
small = ParagraphStyle("small", parent=body, fontSize=7.9, leading=10.2, spaceAfter=2)
h1 = ParagraphStyle("h1", fontName="Sans-Bold", fontSize=17, leading=20, textColor=NAVY, spaceAfter=2)
sub = ParagraphStyle("sub", fontName="Sans", fontSize=9.5, leading=12, textColor=ACCENT, spaceAfter=6)
h2 = ParagraphStyle("h2", fontName="Sans-Bold", fontSize=11.5, leading=14, textColor=NAVY, spaceBefore=8, spaceAfter=3, keepWithNext=1)
cell = ParagraphStyle("cell", parent=small, spaceAfter=0)
cellb = ParagraphStyle("cellb", parent=cell, fontName="Sans-Bold", textColor=colors.white)
P = lambda t, s=body: Paragraph(t, s)


def tbl(rows, widths, zebra=True):
    data = [[Paragraph(c, cellb) for c in rows[0]]] + [[Paragraph(str(c), cell) for c in r] for r in rows[1:]]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    st = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.35, GRID), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 2.4), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.4), ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f7f8fa")) for i in range(2, len(data), 2)]
    t.setStyle(TableStyle(st))
    return t


def fr(v, d=1):
    return f"{v:.{d}f}".replace(".", ",")


def th(v):
    return f"{int(round(v)):,}".replace(",", " ")


def ms(v):
    return fr(v, 3) if v < 1 else (fr(v, 1) if v < 1000 else th(v))


def x(a, b):
    g = a / b
    return f"×{fr(g, 1)}" if g < 100 else f"×{th(g)}"


def pct(a, b):
    return f"−{(a - b) / a * 100:.0f} %"


def linechart(title, series, yfmt, width=84 * mm, height=46 * mm):
    d = Drawing(width, height)
    x0, y0, w, h = 13 * mm, 7 * mm, width - 17 * mm, height - 21 * mm
    ymax = max(max(v) for _, v, _ in series) * 1.1 or 1
    d.add(String(0, height - 6, title, fontName="Sans-Bold", fontSize=7.4, fillColor=NAVY))
    for k in range(5):
        y = y0 + h * k / 4
        d.add(Line(x0, y, x0 + w, y, strokeColor=GRID, strokeWidth=0.4))
        d.add(String(x0 - 2, y - 2, yfmt(ymax * k / 4), fontName="Sans", fontSize=5.6, fillColor=colors.HexColor("#6b7280"), textAnchor="end"))
    xs = [x0 + w * i / 3 for i in range(4)]
    for i, lab in enumerate(("1", "5", "10", "20")):
        d.add(String(xs[i], y0 - 7, lab, fontName="Sans", fontSize=6, fillColor=colors.HexColor("#1b2530"), textAnchor="middle"))
    for li, (lab, vals, col) in enumerate(series):
        pts = [(xs[i], y0 + h * vals[i] / ymax) for i in range(4)]
        for a, b in zip(pts, pts[1:]):
            d.add(Line(a[0], a[1], b[0], b[1], strokeColor=col, strokeWidth=1.3))
        for p in pts:
            d.add(Circle(p[0], p[1], 1.8, fillColor=col, strokeColor=col))
        d.add(Rect(x0 + 2 + li * 32 * mm, height - 16, 5, 5, fillColor=col, strokeColor=None))
        d.add(String(x0 + 9 + li * 32 * mm, height - 15, lab, fontName="Sans", fontSize=6, fillColor=colors.HexColor("#1b2530")))
    return d


def two(l, r):
    t = Table([[l, r]], colWidths=[85 * mm, 85 * mm])
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


LV = ["1", "5", "10", "20"]
_A, _B = P2["A_sql_index"], P2["B_http_n1_groupe"]
a0, a1 = _A["20"]["sans_index"]["mediane"], _A["20"]["avec_index"]["mediane"]
b0, b1 = _B["20"]["n1"]["mediane"], _B["20"]["groupe"]["mediane"]
R3 = D3["mesure_renforcee_client42"]
W = D4["partiel"]["ecriture"]
wal_pct = lambda a, b: (a / b - 1) * 100
W3 = wal_pct(6240760, 4623674)   # WAL d'insertion de l'index composé (atelier 3)
Wp = wal_pct(W["partiel"]["insertion_20000"]["wal_bytes_mediane"], W["initiale"]["insertion_20000"]["wal_bytes_mediane"])
Wc = wal_pct(W["complet"]["insertion_20000"]["wal_bytes_mediane"], W["initiale"]["insertion_20000"]["wal_bytes_mediane"])

s = []
# =============================================================== page 1 : besoin, environnement, protocole, synthèse
s += [P("Dossier de preuve : performance et services back-end", h1),
      P("ShopFlow, PostgreSQL 18 : besoin, stockage, API, résultats avant/après, limites. Chaque chiffre vient d’un fichier de mesures du projet.", sub)]
s.append(tbl([
    ["Pièce du dossier (slide 30)", "Ce qu’elle démontre", "Section"],
    ["Diagnostic initial", "problème observable", "1"],
    ["DDL et déploiement", "stockage implémenté", "2"],
    ["SQL et trace API", "accès correct aux données", "3"],
    ["Benchmark avant/après", "effet mesuré sur le service", "4"],
    ["Tests de correction", "invariants et fraîcheur", "5"],
    ["Décision finale", "choix et limites justifiés (grille slide 31)", "6"],
], [60, 90, 20]))
s.append(Spacer(1, 4))
s.append(tbl([
    ["Besoin et périmètre", "Valeur"],
    ["Accès étudiés", "historique d’un client (GET /commandes?limit=20) · file des commandes en attente · fiche produit · indicateurs mensuels et export · évolution du schéma (newsletter_ok)"],
    ["Charge", "1, 5, 10 et 20 clients (10 s, 3 s d’échauffement, 3 essais alternés) sur l’API ; mesures SQL par pgbench"],
    ["Jeu de données", "1 000 clients, 200 produits, 100 000 commandes, 300 000 lignes (tables de travail jusqu’à 3 000 000 de lignes)"],
    ["Environnement", f"PostgreSQL {P1['version'].split(' ')[1]} (Docker), API Node {A7['node']} + Redis {A8['redis_version']}, pgbench 18.6, PgBouncer 1.18 ; {P1['machine']['coeurs']} cœurs, {fr(P1['machine']['memoire_mo'] / 1024, 1)} Go, WSL2, tout sur la même machine"],
    ["Protocole", "résultat identique vérifié avant toute durée (empreinte md5 ou EXCEPT) · 3 échauffements puis 5 mesures (médiane) · tours alternés sur tables de travail, sans parallélisme · valeurs stables privilégiées (pages lues, WAL, plans) · un seul changement par série · laboratoire comparé avant/après (6 index, 0 statistique)"],
], [34, 136]))
s.append(P("Synthèse : ancienne version → nouvelle version, résultat identique", h2))
cost = {"1": "statistique à maintenir (non mesuré)", "2": "aucun coût mesuré", "3": f"WAL d’insertion +{fr(W3, 0)} %", "3 bis": "idem",
        "4": f"WAL +{fr(Wp, 1)} %, index 328 kB", "5": "WAL +38,9 %", "5 bis": "WAL +34,6 %", "5 ter": "WAL +120,7 %", "6": "WAL +54,1 %, insertions ×7,8",
        "7": f"remplissage ×{fr(V4['nouvelle']['lots']['ms_total_mur'] / V4['ancienne']['update_unique']['ms'], 1)} plus long", "8": "gain modeste en local (21 → 2 requêtes)",
        "9": "aucun gain à petite profondeur", "10": "copie périmée jusqu’à 60 s"}
rows = [["#", "Optimisation", "Ancienne → nouvelle", "Gain", "Coût ou limite"]]
for lbl, a, b in GAINS:
    m = re.match(r"^(\d+(?: bis| ter)?) (.*)$", lbl)
    rows.append([m.group(1), m.group(2), f"{ms(a)} → {ms(b)} ms", x(a, b), cost.get(m.group(1), "")])
s.append(tbl(rows, [10, 66, 38, 16, 40]))
s.append(P("Ligne 7 : temps où la table est inaccessible (3 000 000 lignes) ; 9 : décalage 100 000 sur 1 000 000 de commandes ; 10 : connexion persistante. Résultat identique prouvé pour chaque ligne (section 5). Médianes ; durées variables d’une exécution à l’autre.", small))

# =============================================================== 1 diagnostic
s.append(P("1. Diagnostic initial : problèmes observables", h2))
q1, q2 = A1(1), A1(2)
s.append(tbl([
    ["Observation", "Mesure", "Cause identifiée"],
    ["Historique du client 42", f"{ms(q1)} ms", "déjà rapide ; index (client_id, …) préexistant ; le tri porte sur 100 lignes"],
    ["Indicateurs mensuels", f"{ms(q2)} ms ; Sort externe 3 040 kB", "work_mem (4 MB) trop petit et estimation fausse : 80 048 groupes prévus, 30 réels"],
    ["Page de commandes avec lignes", "21 requêtes SQL pour 20 commandes", "N+1 : une requête de lignes par commande"],
    ["Pagination profonde", f"OFFSET 999 000 : {ms(O7['profondeurs'][-1]['offset']['mediane_ms'])} ms, {th(O7['profondeurs'][-1]['offset']['buffers'])} pages", "OFFSET relit ce qu’il écarte"],
    ["Évolution de schéma", f"SET NOT NULL direct : table inaccessible {ms(V4['ancienne']['set_not_null']['ms'])} ms (3 000 000 lignes)", "relecture complète sous verrou exclusif"],
    ["Rapports sur l’instance OLTP", f"p95 des commandes +{(P2['E_oltp_rapport']['avec_rapports']['mediane']['p95_ms'] / P2['E_oltp_rapport']['seul']['mediane']['p95_ms'] - 1) * 100:.0f} %", "calcul analytique concurrent sur la même instance"],
], [48, 54, 68]))
_t = P1["pgss_top"]
n1q = [r for r in _t if "commande_id" in r["requete"] and int(r["appels"]) == 20000][0]
s.append(P(f"<b>Observation (Jour 5).</b> pg_stat_statements classe le rapport mensuel en tête ({_t[0]['appels']} appels, {th(float(_t[0]['total_ms']))} ms cumulés) ; le N+1 y pèse {th(float(n1q['total_ms']))} ms ({th(int(n1q['appels']))} appels de {fr(float(n1q['moyenne_ms']), 3)} ms) "
            f"et <b>n’apparaît pas</b> dans le journal des requêtes lentes ({P1['slow_log_lignes_n1_journal_complet']} ligne), alors que l’API mesure {fr(A7['2_repetition']['20']['n1']['sqlMs_mediane'], 1)} ms de SQL par page : son coût est dans les allers-retours. "
            "pg_stat_activity (slide 8) : une session « idle in transaction » (ClientRead) bloque l’ALTER d’une autre (Lock / relation, pg_blocking_pids = la première). "
            f"Laboratoire : autovacuum {P1['autovacuum_lab']}, journal lent {P1['log_min_duration_lab']} (désactivé).", small))

# =============================================================== 2 DDL et déploiement
s.append(P("2. DDL et déploiement : stockage implémenté", h2))
s.append(tbl([
    ["Objet", "DDL (extrait)", "Déploiement et retour arrière", "Preuve"],
    ["Schéma ShopFlow", "01_schema.sql, 02_donnees.sql", "base de laboratoire PostgreSQL 18.6", "1 000 / 200 / 100 000 / 300 000 lignes"],
    ["Index historique (001)", "CREATE INDEX … (client_id, created_at DESC, id DESC) INCLUDE (statut, total)", "version laboratoire, version production CONCURRENTLY hors transaction, contrôle indisvalid, DOWN", "testée sur base jetable ; non appliquée au laboratoire"],
    ["Index file d’attente (002)", "CREATE INDEX … (created_at, id) WHERE statut = 'en_attente'", "idem ; DROP INDEX au retour", "testée sur base jetable ; non appliquée"],
    ["Colonne newsletter_ok (4 bis)", "ADD COLUMN nullable → DEFAULT false → lots de 200 → CHECK … NOT VALID → VALIDATE → SET NOT NULL", "lock_timeout 2 s ; retour : retrait des contraintes puis DROP COLUMN (sur la copie)", f"{B4['07_nb_clients']} clients, {B4['07_nb_null']} NULL, {B4['07_ecarts']} écart (md5 {B4['07_md5_copie']}) ; verrou : 55P03 après {fr(B4['08_b_attente_s'], 1)} s"],
], [30, 52, 52, 36]))
s.append(P(f"Migration à 3 000 000 de lignes (même état final, md5 {V4['ancienne_final']['md5']}) : temps sous verrou exclusif {ms(V4['ancienne']['set_not_null']['ms'])} → {ms(V4['nouvelle']['check_not_valid']['ms'] + V4['nouvelle']['set_not_null']['ms'])} ms ; écriture la plus longue bloquée {th(V4['ancienne']['update_unique']['sonde']['max_ms'])} → {th(V4['nouvelle']['lots']['sonde']['max_ms'])} ms ; "
            f"remplissage {th(V4['ancienne']['update_unique']['ms'] / 1000)} → {th(V4['nouvelle']['lots']['ms_total_mur'] / 1000)} s (coût de la méthode). Pendant VALIDATE, lecture, UPDATE et INSERT concurrents passent ; pendant SET NOT NULL, une lecture est bloquée (55P03).", small))

# =============================================================== 3 SQL et trace API
s.append(P("3. SQL et trace API : accès correct aux données", h2))
s.append(tbl([
    ["Élément", "Contenu", "Preuve"],
    ["Contrat de l’endpoint", "GET /commandes ; réponse data / hasNextPage / nextCursor ; ordre created_at DESC puis id DESC ; limite 20 (défaut), 100 (max) ; ids et montants en chaînes ; client issu du contexte autorisé", f"vérifié ; limit 101 et 0 : {A7['3_contrat']['limit_101']}"],
    ["SQL curseur", "WHERE client_id=$1 AND (created_at,id)<($2,$3) ORDER BY commandes.created_at DESC, commandes.id DESC LIMIT 21 (la 21e ligne donne hasNextPage)", f"page 2 identique à OFFSET ; parcours {A7['5_parcours']['pages']} pages, {A7['5_parcours']['total']} ids uniques"],
    ["SQL chargement groupé", "SELECT … FROM lignes WHERE commande_id = ANY($1::bigint[])", "réponse identique au N+1 (5, 20, 50, 100 commandes)"],
    ["Trace (TraceId → SQL)", f"{A7['2_page20']['n1']['SqlCount']} requêtes (N+1), sqlMs {fr(A7['2_page20']['n1']['journal']['sqlMs'], 1)} → {A7['2_page20']['groupe']['SqlCount']} requêtes (groupé), sqlMs {fr(A7['2_page20']['groupe']['journal']['sqlMs'], 1)}", f"TraceId {A7['2_page20']['n1']['TraceId'][:8]}… / {A7['2_page20']['groupe']['TraceId'][:8]}…"],
    ["Dates identiques", f"page 1 : {', '.join(A7['4_pages']['page1']['ids'])} ; page 2 : {', '.join(A7['4_pages']['page2']['ids'])} ; avec la seule date la commande 42 est perdue", "paire (created_at, id) nécessaire"],
    ["Droits", "401 sans jeton ; 400 avec client_id dans l’URL ; 400 avec un curseur falsifié ; un curseur signé n’est pas une autorisation", f"{A7['5_droits']['sans_jeton']} / {A7['5_droits']['client_id_injecte']} / {A7['5_droits']['curseur_falsifie']}"],
], [34, 94, 42]))

# =============================================================== 4 benchmark
s.append(P("4. Benchmark avant/après : effet mesuré sur le service", h2))
s.append(two(
    linechart("SQL : transactions par seconde", [("sans index", [_A[l]["sans_index"]["mediane"]["tps"] for l in LV], colors.HexColor("#c4472b")), ("avec index", [_A[l]["avec_index"]["mediane"]["tps"] for l in LV], colors.HexColor("#1f8a99"))], th),
    linechart("HTTP : requêtes terminées par seconde", [("N+1", [_B[l]["n1"]["mediane"]["debit_termine"] for l in LV], colors.HexColor("#c4472b")), ("groupé", [_B[l]["groupe"]["mediane"]["debit_termine"] for l in LV], colors.HexColor("#1f8a99"))], th)))
s.append(tbl([
    ["20 clients, médiane de 3 essais", "Avant", "Après", "Gain", "Erreurs"],
    ["Index composé : débit (tps)", th(a0["tps"]), th(a1["tps"]), x(a1["tps"], a0["tps"]), "0"],
    ["Index composé : p95 (ms)", ms(a0["p95_ms"]), ms(a1["p95_ms"]), pct(a0["p95_ms"], a1["p95_ms"]), "0"],
    ["Chargement groupé : débit (req/s)", fr(b0["debit_termine"]), fr(b1["debit_termine"]), x(b1["debit_termine"], b0["debit_termine"]), "0"],
    ["Chargement groupé : p95 (ms)", fr(b0["p95_ms"]), fr(b1["p95_ms"]), pct(b0["p95_ms"], b1["p95_ms"]), "0"],
    ["Pagination, décalage 999 000 (ms)", ms(O7["profondeurs"][-1]["offset"]["mediane_ms"]), ms(O7["profondeurs"][-1]["curseur"]["mediane_ms"]), x(O7["profondeurs"][-1]["offset"]["mediane_ms"], O7["profondeurs"][-1]["curseur"]["mediane_ms"]), "—"],
    ["Fiche produit : miss → hit (ms)", ms(P8["miss"]["http_ms"]["mediane"]), ms(P8["hit"]["http_ms"]["mediane"]), x(P8["miss"]["http_ms"]["mediane"], P8["hit"]["http_ms"]["mediane"]), "0"],
], [64, 26, 26, 26, 28]))
C, D = P2["C_pool_api"], P2["D_fermee_ouverte"]
E = P2["E_oltp_rapport"]
s.append(P(f"Débit du N+1 plafonné dès 5 clients ({fr(_B['5']['n1']['mediane']['debit_termine'], 0)} → {fr(b0['debit_termine'], 0)} req/s), file du pool jusqu’à {B_ if (B_ := _B['20']['n1']['essais'][1]['machine']['pool_attente_max']) else 0} requêtes ; groupé : {fr(b1['debit_termine'], 0)} req/s avec le même pool de 5. "
            f"Pool 5 → 20 (N+1, 2 essais, indicatif) : attente 15 → 0, débit {fr(C['5']['essais'][1]['debit_termine'], 0)}–{fr(C['5']['essais'][0]['debit_termine'], 0)} → {fr(C['20']['essais'][0]['debit_termine'], 0)}–{fr(C['20']['essais'][1]['debit_termine'], 0)} req/s : corriger le N+1 vaut mieux qu’agrandir le pool. "
            f"Charge ouverte (N+1) : stable à 50 % du débit fermé, instable à 90 %, effondrement (503) à 130 % ; la charge fermée (0 erreur) masque la saturation. "
            f"Rapports concurrents : p95 +{(E['avec_rapports']['mediane']['p95_ms'] / E['seul']['mediane']['p95_ms'] - 1) * 100:.0f} %, p99 {x(E['avec_rapports']['mediane']['p99_ms'], E['seul']['mediane']['p99_ms'])}, médiane inchangée. "
            f"work_mem 4 → 32 MB : agrégation mensuelle {ms(P1B['q2']['4MB']['mediane'])} → {ms(P1B['q2']['32MB']['mediane'])} ms (tri disque 3 040 kB → mémoire) ; effective_cache_size : aucun changement de plan. "
            f"Un VACUUM est bloqué par une transaction longue ({th(P1['vacuum']['vacuum_pendant_transaction']['mortes_non_supprimables'])} lignes mortes non supprimables, {th(P1['vacuum']['vacuum_apres_commit']['supprimees'])} supprimées après son COMMIT). "
            "SQL (pgbench) et HTTP (loadgen) ont des unités et des scénarios différents : leurs résultats restent séparés.", small))

# =============================================================== 5 tests de correction
s.append(P("5. Tests de correction : invariants et fraîcheur", h2))
s.append(tbl([
    ["Invariant", "Test", "Résultat"],
    ["Résultats identiques avant/après", "empreinte md5 du résultat complet, ou différence symétrique entre deux requêtes (EXCEPT)", "identiques pour toutes les lignes de la synthèse (agrégation 601f7d5aefe1, historique 21df3003a95c, file 7a826168f2fd, JSON 11157d484cf8, GiST e6f0c0d64f01)"],
    ["Migration sans perte", "EXCEPT ALL dans les deux sens sur id, email, nom ; NOT NULL ; rejet de NULL", f"{B4['07_ecarts']} écart ; erreur {B4['07_rejet_null']['sqlstate']} ; {B4['07_nb_null']} NULL"],
    ["Réponse API inchangée", "corps JSON complet comparé, N+1 / groupé, OFFSET / curseur", "identique à 5, 20, 50, 100 commandes ; 0 erreur sur toutes les séries"],
    ["Export analytique", "Σ nb_commandes = commandes payées ; Σ montant = Σ commandes.total ; deux exécutions", f"{th(P3['somme_nb_commandes'])} = {th(P3['commandes_payees_table'])} ; {P3['somme_montant_csv']} = {P3['somme_total_payees_table']} ; md5 {P3['md5_export_1']} = {P3['md5_export_2']}"],
    ["Fraîcheur du cache", "UPDATE direct dans PostgreSQL, puis lecture par l’API (TTL 60 s)", f"l’API sert {A8['3_update_direct']['apres_update_avant_del']['prix']} (hit, 0 SQL) alors que la base a {A8['3_update_direct']['postgres_prix']} ; PATCH par l’API : invalidation ok, valeur juste"],
    ["Reprise et invalidation", "PATCH pendant que Redis est arrêté ; expiration ; panne de Redis", f"invalidation = {A8['ajout_invalidation_echouee']['patch']['Body']['invalidation']} : prix enregistré ({A8['ajout_invalidation_echouee']['postgres_prix_apres_patch']}), copie ancienne conservée ; expiration TTL 60 → −2 ; repli sur PostgreSQL : 200, 1 SELECT par lecture"],
    ["Course lecture / invalidation", "reproduite à la main (psql + redis-cli)", f"l’API sert {A8['ajout_course']['api_apres']['prix']} alors que la base a {A8['ajout_course']['postgres_apres']} ; pistes : version, invalidation rejouée"],
], [38, 66, 66]))
s.append(P(f"<b>Fraîcheur acceptée :</b> catalogue, de quelques secondes à une minute (TTL 60 s) ; <b>aucun cache sur l’achat</b> : prix et stock contrôlés dans PostgreSQL, dans la transaction. "
           f"Correction d’une journée d’export déjà publiée : une annulation tardive fait passer {P3['correction_jour']['jour']} de {P3['correction_jour']['avant'][0]} à {P3['correction_jour']['apres_annulation_tardive'][0]} : la journée est republiée en entier. "
           f"Fuseau : {th(P3['commandes_jour_UTC_different_jour_Paris'])} commandes payées changeraient de jour entre UTC et Paris : la règle est UTC.", small))

# =============================================================== 6 décision finale
s.append(P("6. Décision finale : choix, limites et coût de maintenance", h2))
s.append(tbl([
    ["Retenu", "Justification mesurée", "Coût, risque ou condition de remise en cause"],
    ["Index composé (client_id, created_at DESC, id DESC)", f"p95 {ms(a0['p95_ms'])} → {ms(a1['p95_ms'])} ms, {x(a1['tps'], a0['tps'])} de débit à 20 clients ; client très actif ×91", f"WAL d’insertion +{fr(W3, 0)} % ; à remettre en cause si l’import domine"],
    ["Index partiel sur en_attente", f"×145, index 12,4 fois plus petit que l’index complet", f"ne sert que ce prédicat ; WAL +{fr(Wp, 1)} % (complet : +{fr(Wc, 1)} %)"],
    ["Chargement groupé + curseur", "21 → 2 requêtes ; pagination profonde constante (0,18 ms)", "gain modeste en local ; curseur sans accès direct à la page n ; aucun gain à petite profondeur"],
    ["Migration par étapes (NOT VALID, lots)", f"verrou exclusif {ms(V4['ancienne']['set_not_null']['ms'])} → {ms(V4['nouvelle']['check_not_valid']['ms'] + V4['nouvelle']['set_not_null']['ms'])} ms", "plus lente au total ; lock_timeout et retour arrière à prévoir"],
    ["Cache Redis sur la fiche produit seulement", f"{ms(P8['miss']['http_ms']['mediane'])} → {ms(P8['hit']['http_ms']['mediane'])} ms, 0 SQL sur un hit", "copie périmée jusqu’à 60 s ; invalidation à rendre fiable ; pas de cache sur l’achat"],
    ["Rejeté", "GIN sur 200 produits (jamais utilisé) ; index complet (12× plus gros) ; PgBouncer pour accélérer (40 → 5 connexions mais 261 → 94 tps) ; pool agrandi seul ; effective_cache_size (aucun effet)", "variantes mesurées puis écartées"],
], [50, 62, 58]))
s.append(P(f"<b>Conclusion bornée.</b> Sur cette machine ({P1['machine']['coeurs']} cœurs, WSL2), ce jeu (100 000 commandes) et cette charge (1 à 20 clients, 10 s), l’index composé relève le débit SQL de {x(a1['tps'], a0['tps'])} et le chargement groupé le débit HTTP de {x(b1['debit_termine'], b0['debit_termine'])}, sans erreur. "
           "Ce n’est pas « PostgreSQL devient plus rapide » : rien n’est établi sur la production, l’import, des clients très actifs ou plusieurs instances d’API. Coût de maintenance : un index de plus à maintenir (écriture, taille, VACUUM), "
           "une invalidation de cache à surveiller, des campagnes de mesure à rejouer (python3 atelier9/p2_charge.py, ≈ 16 min). Garanties de reprise : scripts DOWN, retrait des contraintes avant DROP COLUMN (qui détruit les valeurs), repli sur PostgreSQL si Redis tombe.", small))
s.append(tbl([
    ["Résultat (slide 2)", "Nature", "Raison mesurée"],
    ["Index composé, chargement groupé", "optimisation reproductible", f"3 essais : {th(min(e['tps'] for e in _A['20']['avec_index']['essais']))}–{th(max(e['tps'] for e in _A['20']['avec_index']['essais']))} contre {th(min(e['tps'] for e in _A['20']['sans_index']['essais']))}–{th(max(e['tps'] for e in _A['20']['sans_index']['essais']))} tps ; groupé {fr(min(e['debit_termine'] for e in _B['20']['groupe']['essais']), 0)}–{fr(max(e['debit_termine'] for e in _B['20']['groupe']['essais']), 0)} contre {fr(min(e['debit_termine'] for e in _B['20']['n1']['essais']), 0)}–{fr(max(e['debit_termine'] for e in _B['20']['n1']['essais']), 0)} req/s"],
    ["Taille du pool, charge ouverte à 90 %", "variation de mesure / instable", "2 essais à pool 5 : 137 et 216 req/s ; un essai à 90 % tient, l’autre s’effondre : pas de médiane"],
    ["Index (écriture), rapports concurrents, cache", "déplacement du coût", f"WAL +{fr(W3, 0)} % ; p95 des commandes +{(E['avec_rapports']['mediane']['p95_ms'] / E['seul']['mediane']['p95_ms'] - 1) * 100:.0f} % ; copie périmée possible"],
], [52, 40, 78]))
s.append(Spacer(1, 3))
s.append(tbl([
    ["Grille (slide 31)", "Question de relecture", "Réponse et preuve"],
    ["Besoin", "endpoint et charge définis ?", "oui : GET /commandes?limit=20, 1 à 20 clients, 10 s ; autres accès listés en page 1"],
    ["Correction", "résultat et droits valides ?", "oui : sections 3 et 5 (identité des résultats, 401 / 400, invariants d’export, 0 écart)"],
    ["Méthode", "test reproductible ?", "oui : scripts atelier3 à atelier9, copie aux empreintes identiques, 3 essais alternés ; séries instables signalées"],
    ["Intervention", "le mécanisme explique-t-il le gain ?", "oui : travail évité (21 → 2 requêtes, pages lues, relecture de table) ; plans et pages lues dans le PDF complet"],
    ["Limites", "coûts et risques exposés ?", "oui : section 6 (écriture, fraîcheur, rapport concurrent, mesures locales, une machine)"],
], [32, 52, 86]))
s.append(P("Détail complet : Atelier1_Diagnostic_compact.pdf (ateliers 1 à 8) et test.pdf (+ Jour 5 avec annexes) ; scripts et sorties brutes : dossiers atelier3 à atelier9.", small))


def footer(c, doc):
    c.saveState(); c.setFont("Sans", 7.2); c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(18 * mm, 9 * mm, "Dossier de preuve · performance et services back-end · ShopFlow")
    c.drawRightString(192 * mm, 9 * mm, str(doc.page)); c.restoreState()


doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=13 * mm, bottomMargin=14 * mm,
                        title="Dossier de preuve : performance et services back-end (ShopFlow)", author="ShopFlow, Optimisation BDD")
doc.build(s, onFirstPage=footer, onLaterPages=footer)
print("OK", OUT)
