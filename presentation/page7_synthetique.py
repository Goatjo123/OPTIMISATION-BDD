"""Remplace la page 7 de Support_Presentation_5min.pdf par une version plus synthétique (original conservé)."""
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

buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(W, HT))
def t(x, y, s, size, bold=False, color=INK, anchor="l"):
    c.setFont("Sans-Bold" if bold else "Sans", size); c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)

c.setFillColor(NAVY); c.rect(0, HT - 78, W, 78, stroke=0, fill=1)
t(36, HT - 24, "DÉCISION, VARIANTE REJETÉE, RISQUE RESTANT", 11, True, CYAN)
t(36, HT - 56, "Je retiens le chargement groupé", 28, True, colors.white)
t(W - 36, HT - 24, "4:00 – 5:00", 11, False, H("#e8d9cc"), "r"); t(W - 36, HT - 44, "6 / 7", 11, False, colors.white, "r")

t(36, 418, "PAGES SERVIES PAR SECONDE À 20 CLIENTS", 11, True, ACCENT)
rows = [("N+1 (avant)", 247, "247", RED), ("Pool agrandi (rejeté)", 287, "≈ 287", MUTED), ("Groupé (retenu)", 1032, "1 032", TEAL)]
for k, (lab, v, s, col) in enumerate(rows):
    y = 350 - k * 72
    t(36, y + 12, lab, 12, False, INK)
    w = 290 * v / 1032
    c.setFillColor(col); c.roundRect(215, y, w, 38, 5, stroke=0, fill=1)
    t(215 + w + 10, y + 12, s, 14, True, col)
t(36, 118, "Agrandir le pool supprime l'attente, pas les 21 trajets par page.", 11, False, MUTED)

def card(y, h, title, body, fill, stroke, tcol):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(1.4); c.roundRect(600, y, 324, h, 7, stroke=1, fill=1)
    t(616, y + h - 22, title, 11, True, tcol)
    for i, line in enumerate(body): t(616, y + h - 44 - i * 18, line, 13, False, INK)
card(332, 86, "RETENU", ["Groupé : 21 → 2 requêtes,", "débit ×4,2, 0 erreur"], PALE_GREEN, GREEN, GREEN)
card(226, 88, "REJETÉ", ["Pool 5 → 20 (≈ 287 req/s)", "PgBouncer (261 → 94 tps)"], PALE_RED, RED, RED)
card(138, 70, "RISQUE", ["Cache périmé jusqu'à 60 s"], LIGHT, ACCENT, ACCENT)

c.setFillColor(PALE); c.setStrokeColor(NAVY); c.roundRect(36, 36, W - 72, 52, 7, stroke=1, fill=1)
t(54, 66, "PORTÉE", 10, True, NAVY)
t(54, 46, "Cette machine, ce jeu de données, 1 à 20 clients. Pas encore testé en production.", 13, True, INK)
c.showPage(); c.save(); buf.seek(0)

src = pypdf.PdfReader(os.path.join(ROOT, "Support_Presentation_5min.pdf")); new = pypdf.PdfReader(buf); out = pypdf.PdfWriter()
for i, p in enumerate(src.pages): out.add_page(new.pages[0] if i == 6 else p)
out.add_metadata({"/Title": "Support présentation 5 min (page 7 synthétique)"})
with open(os.path.join(ROOT, "Support_Presentation_5min_synthetique.pdf"), "wb") as f: out.write(f)
