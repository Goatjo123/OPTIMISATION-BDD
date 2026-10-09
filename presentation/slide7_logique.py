"""Remplace la slide 7 de SLIDES.pdf par une version à logique de décision : trois options, même question, verdict (original conservé)."""
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
PALE_RED, PALE_GREEN, LIGHT, PALE, GRID = H("#f8dcd3"), H("#d6eee0"), H("#fdf3ec"), H("#e7ebef"), H("#c9cfd6")
W, HT = 960, 540
buf = io.BytesIO(); c = canvas.Canvas(buf, pagesize=(W, HT))


def t(x, y, s, size, bold=False, color=INK, anchor="l"):
    c.setFont("Sans-Bold" if bold else "Sans", size); c.setFillColor(color)
    {"l": c.drawString, "r": c.drawRightString, "c": c.drawCentredString}[anchor](x, y, s)


c.setFillColor(NAVY); c.rect(0, HT - 78, W, 78, stroke=0, fill=1)
t(36, HT - 24, "DÉCISION, VARIANTE REJETÉE, RISQUE RESTANT", 11, True, CYAN)
t(36, HT - 56, "Je retiens le chargement groupé", 28, True, colors.white)
t(W - 36, HT - 28, "7 / 8", 11, False, colors.white, "r")
t(36, 418, "Trois façons de lever le plafond de 247 pages/s à 20 clients. Laquelle supprime vraiment les 21 trajets ?", 13, True, NAVY)

cards = [("OPTION 1", "Agrandir le pool", "5 → 20 connexions", "≈ 287", "pages/s (2 essais)", "Supprime l'attente, mais les 21 trajets par page restent.", "REJETÉ", PALE_RED, RED, 287),
         ("OPTION 2", "Ajouter PgBouncer", "40 → 5 connexions", "261 → 94", "transactions/s (autre mesure)", "Borne les connexions, n'accélère rien : le débit baisse.", "REJETÉ", PALE_RED, RED, None),
         ("OPTION 3", "Chargement groupé", "21 → 2 requêtes", "1 032", "pages/s, 0 erreur", "Supprime les trajets : ×4,2, résultat identique.", "RETENU", PALE_GREEN, GREEN, 1032)]
cw, gap, y, h = 280, 24, 175, 220
for i, (tag, name, sub, big, unit, why, verdict, fill, stroke, v) in enumerate(cards):
    x = 36 + i * (cw + gap)
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(2.4 if verdict == "RETENU" else 1.2); c.roundRect(x, y, cw, h, 8, stroke=1, fill=1)
    t(x + 16, y + h - 24, tag, 9.5, True, stroke); t(x + 16, y + h - 46, name, 16, True, INK); t(x + 16, y + h - 64, sub, 11, False, MUTED)
    t(x + 16, y + h - 112, big, 30, True, stroke if verdict == "RETENU" else INK); t(x + 16, y + h - 130, unit, 10, False, MUTED)
    if v:   # barre à l'échelle 1 032, repère « avant » = 247
        c.setFillColor(colors.white); c.rect(x + 16, y + 74, 248, 9, stroke=0, fill=1)
        c.setFillColor(stroke if verdict == "RETENU" else MUTED); c.rect(x + 16, y + 74, 248 * v / 1032, 9, stroke=0, fill=1)
        c.setStrokeColor(INK); c.setLineWidth(1.2); c.line(x + 16 + 248 * 247 / 1032, y + 70, x + 16 + 248 * 247 / 1032, y + 87)
        t(x + 16 + 248 * 247 / 1032, y + 60, "avant : 247", 8, False, INK, "c")
    else:
        t(x + 16, y + 74, "autre unité : pas de barre comparable", 8.5, False, MUTED)
    c.setFillColor(INK); c.setFont("Sans", 10.5)
    words, line, ly = why.split(), "", y + 38
    for wd in words:
        if c.stringWidth(line + " " + wd, "Sans", 10.5) > cw - 32: t(x + 16, ly, line.strip(), 10.5); ly -= 14; line = wd
        else: line += " " + wd
    t(x + 16, ly, line.strip(), 10.5)
    c.setFillColor(stroke); c.roundRect(x + cw - 92, y + h - 124, 76, 20, 10, stroke=0, fill=1); t(x + cw - 54, y + h - 118, verdict, 9.5, True, colors.white, "c")

for x0, w0, title, body, fill, stroke in ((36, 436, "RISQUE RESTANT", "Cache de la fiche produit : copie périmée jusqu'à 60 s. Jamais sur l'achat.", LIGHT, ACCENT),
                                          (488, 436, "PORTÉE", "Cette machine, ce jeu de données, 1 à 20 clients. Pas testé en production.", PALE, NAVY)):
    c.setFillColor(fill); c.setStrokeColor(stroke); c.setLineWidth(1.2); c.roundRect(x0, 40, w0, 108, 7, stroke=1, fill=1)
    t(x0 + 16, 148 - 24, title, 10, True, stroke)
    words, line, ly = body.split(), "", 148 - 50
    for wd in words:
        if c.stringWidth(line + " " + wd, "Sans-Bold", 13) > w0 - 32: t(x0 + 16, ly, line.strip(), 13, True); ly -= 19; line = wd
        else: line += " " + wd
    t(x0 + 16, ly, line.strip(), 13, True)
c.showPage(); c.save(); buf.seek(0)

src = pypdf.PdfReader(os.path.join(ROOT, "SLIDES.pdf")); new = pypdf.PdfReader(buf); out = pypdf.PdfWriter()
for i, p in enumerate(src.pages): out.add_page(new.pages[0] if i == 6 else p)
out.add_metadata({"/Title": "Slides : présentation de 5 minutes (slide 7 logique)"})
with open(os.path.join(ROOT, "SLIDES_slide7_logique.pdf"), "wb") as f: out.write(f)
