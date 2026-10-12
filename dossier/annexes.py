"""Prépare les pages d'annexe à joindre : reprend test.pdf (PRINCIPAL + Jour 5) sans les notes de compréhension.
 - pages retirées : 15, 24 (seulement « Ce que j'ai compris »), 25 (questions de compréhension du cours), 67 (auto-relecture, qui cite un ancien document) ;
 - blocs « Ce que j'ai compris » effacés sur les pages 2, 5, 6, 10, 18, 21 ; tableaux « pièces du dossier / auto-relecture » effacés en bas de la page 66.
Les pages modifiées sont reconverties en image (200 dpi) pour que le texte effacé ne reste pas dans le fichier."""
import io, os
import pypdf, pypdfium2 as pdfium
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DROP = {15, 24, 25, 67}
BOX = (2, 5, 6, 10, 18, 21)          # blocs « Ce que j'ai compris » à effacer
SCALE = 200 / 72


def find(page, needle):
    tp = page.get_textpage(); s = tp.search(needle); hit = s.get_next()
    if not hit: return None
    l, b, r, t = tp.get_charbox(hit[0]); return l, b, r, t


def near(c, ref, tol=9): return all(abs(a - b) <= tol for a, b in zip(c, ref))


def erase_box(img, page, hl):
    """Efface le bloc rose qui contient l'en-tête repéré (hl = boîte du caractère de départ, en points)."""
    H = page.get_height(); px = img.load()
    y0 = int((H - hl[3]) * SCALE); xref = int((hl[0] + 260) * SCALE)
    ref = px[xref, y0 + 6]
    cols = [int(x * SCALE) for x in (528, 531, 534, 537)]
    ok = lambda y: sum(near(px[x, y][:3], ref[:3]) for x in cols) >= 3
    top = y0
    while top > 0 and ok(top - 1): top -= 1
    bot = y0
    while bot < img.height - 1 and ok(bot + 1): bot += 1
    d = ImageDraw.Draw(img); d.rectangle([int(40 * SCALE), top - int(5 * SCALE), int(img.width - 30 * SCALE), bot + int(5 * SCALE)], fill="white")
    return img


def build():
    """Retourne la liste [(numéro d'origine, pypdf.PageObject)] des pages d'annexe à joindre, dans l'ordre."""
    src_path = os.path.join(ROOT, "test.pdf"); rd = pypdf.PdfReader(src_path); pdf = pdfium.PdfDocument(src_path); out = []
    for n in range(1, len(rd.pages) + 1):
        if n in DROP: continue
        if n in BOX or n == 66:
            pg = pdf[n - 1]; img = pg.render(scale=SCALE).to_pil().convert("RGB")
            if n in BOX:
                hl = find(pg, "Ce que j"); assert hl, n; img = erase_box(img, pg, hl)
            else:
                hl = find(pg, "Pièce du dossier"); assert hl, n
                ImageDraw.Draw(img).rectangle([int(40 * SCALE), int((pg.get_height() - hl[3] - 8) * SCALE), img.width, int((pg.get_height() - 62) * SCALE)], fill="white")
            b = io.BytesIO(); img.save(b, "PDF", resolution=200); b.seek(0); out.append((n, pypdf.PdfReader(b).pages[0]))
        else:
            out.append((n, rd.pages[n - 1]))
    return out


if __name__ == "__main__":
    print([n for n, _ in build()][:20], "...")
