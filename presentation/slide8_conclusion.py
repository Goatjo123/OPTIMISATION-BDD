"""Slides finales : slide 8 = conclusion de la problématique ; slides 1 à 6 sans commentaires de chrono ni de réserve ; numérotation n / 8.
Entrée : SLIDES_slide7_logique.pdf (slide 7 refaite par slide7_logique.py). Sortie : SLIDES_v2.pdf. Originaux conservés."""
import io, os
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
import pypdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
F = "/usr/share/fonts/truetype/dejavu/"
pdfmetrics.registerFont(TTFont("Sans", F + "DejaVuSans.ttf")); pdfmetrics.registerFont(TTFont("Sans-Bold", F + "DejaVuSans-Bold.ttf"))
H = colors.HexColor
NAVY, CYAN, ACCENT, INK, MUTED = H("#173a4d"), H("#7fd6e0"), H("#b4532a"), H("#1b2530"), H("#6b7280")
RED, GREEN, TEAL = H("#c4472b"), H("#2f8f5b"), H("#1f8a99")
PALE_RED, PALE_GREEN, LIGHT, PALE = H("#f8dcd3"), H("#d6eee0"), H("#fdf3ec"), H("#e7ebef")
W, HT = 960, 540


def new_canvas():
    buf = io.BytesIO(); return buf, canvas.Canvas(buf, pagesize=(W, HT))


def t(c, x, y, s, size, bold=False, color=INK, anchor="l"):
    c.setFont("Sans-Bold" if bold else "Sans", size); c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)


def wrap(c, x, y, text, size, width, lead, bold=False, color=INK):
    font = "Sans-Bold" if bold else "Sans"; line = ""
    for wd in text.split():
        if c.stringWidth((line + " " + wd).strip(), font, size) > width: t(c, x, y, line, size, bold, color); y -= lead; line = wd
        else: line = (line + " " + wd).strip()
    t(c, x, y, line, size, bold, color); return y - lead


# --- slide 8 : conclusion de la problématique
b8, c = new_canvas()
c.setFillColor(NAVY); c.rect(0, HT - 78, W, 78, stroke=0, fill=1)
t(c, 36, HT - 24, "CONCLUSION", 11, True, CYAN); t(c, 36, HT - 56, "Ce que je retiens", 28, True, colors.white); t(c, W - 36, HT - 28, "8 / 8", 11, False, colors.white, "r")
c.setFillColor(PALE); c.setStrokeColor(NAVY); c.setLineWidth(1.2); c.roundRect(36, 372, W - 72, 56, 8, stroke=1, fill=1)
t(c, 52, 410, "PROBLÉMATIQUE", 9.5, True, NAVY); t(c, 52, 389, "D'où vient ce coût, comment le supprimer sans changer le résultat, et à quel prix ?", 14.5, True, INK)
cols = [("D'où vient ce coût ?", "Des allers-retours", "21 requêtes par page : ≈ 0,68 ms chacune vue par l'API, contre 0,018 ms pour PostgreSQL. Ce n'est ni la requête SQL, ni la taille du pool.", PALE_RED, RED),
        ("Comment le supprimer sans changer le résultat ?", "21 → 2 requêtes", "Une seule requête pour toutes les lignes de la page. Même réponse, mêmes droits. Débit ×4,2, p95 −73 %, 0 erreur.", PALE_GREEN, GREEN),
        ("À quel prix ?", "La fraîcheur", "Le groupé ne coûte ni index ni écriture. Le cache peut servir une valeur périmée jusqu'à 60 s : jamais pour l'achat. Valable ici, pas encore en production.", LIGHT, ACCENT)]
cw, gap = 280, 24
for i, (q, big, body, fill, col) in enumerate(cols):
    x = 36 + i * (cw + gap)
    c.setFillColor(fill); c.setStrokeColor(col); c.setLineWidth(1.6); c.roundRect(x, 130, cw, 224, 8, stroke=1, fill=1)
    wrap(c, x + 16, 330, q, 11.5, cw - 32, 15, True, col)
    t(c, x + 16, 268, big, 22 if len(big) < 14 else 20, True, INK)
    wrap(c, x + 16, 238, body, 12, cw - 32, 17)
c.setFillColor(NAVY); c.roundRect(36, 40, W - 72, 70, 8, stroke=0, fill=1)
wrap(c, 54, 82, "Je retiens : corriger la cause d'abord, ici les allers-retours. Le cache va plus loin, mais sa fraîcheur est son prix.", 14.5, W - 108, 21, True, colors.white)
c.showPage(); c.save(); b8.seek(0)

# --- nettoyage des slides 1 à 6 (chronos, mentions de réserve) et numérotation
bo, o = new_canvas()
o.setFillColor(NAVY); o.rect(40, 40, 560, 28, stroke=0, fill=1)
t(o, 48, 49, "Youssef · Optimisation BDD · Atelier 10", 11, False, H("#e8d9cc"))
o.showPage()
for n in range(2, 7):
    o.setFillColor(NAVY); o.rect(800, HT - 78, 160, 78, stroke=0, fill=1)
    t(o, W - 36, HT - 28, f"{n} / 8", 11, False, colors.white, "r"); o.showPage()
o.save(); bo.seek(0)

src = pypdf.PdfReader(os.path.join(ROOT, "SLIDES_slide7_logique.pdf")); ov = pypdf.PdfReader(bo); out = pypdf.PdfWriter()
for i, p in enumerate(src.pages):
    if i == 7: p = pypdf.PdfReader(b8).pages[0]
    elif i < 6: p.merge_page(ov.pages[i])
    out.add_page(p)
out.add_metadata({"/Title": "Slides : présentation (v2)"})
with open(os.path.join(ROOT, "SLIDES_v2.pdf"), "wb") as f: out.write(f)
