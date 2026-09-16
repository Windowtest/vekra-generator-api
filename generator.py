"""
Generátor PDF vizitek VEKRA s QR kódem (vCard).

Rozměry, barvy a rozmístění odpovídají tiskové předloze
VEKRA_vizitky_lKiss_tisk.pdf (InDesign):
  - čistý formát 90 x 50 mm, spad 3 mm, stránka 106,58 x 66,58 mm
  - barvy v CMYK (červená C0 M100 Y71 K8, text K100)
  - ořezové značky 0,25 pt na skutečných ořezových liniích
"""

import io
import os
import re

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import CMYKColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
LOGO_PATH = os.path.join(BASE_DIR, "vekra_logo.png")

# Geograph - oficiální firemní font VEKRA (převedený z OTF na TTF kvůli reportlabu)
FONT_REGULAR = os.path.join(FONTS_DIR, "Geograph-Regular.ttf")
FONT_BOLD = os.path.join(FONTS_DIR, "Geograph-Bold.ttf")

pdfmetrics.registerFont(TTFont("VekraSans", FONT_REGULAR))
pdfmetrics.registerFont(TTFont("VekraSans-Bold", FONT_BOLD))

# --------------------------------------------------------------------------
# Geometrie (naměřeno z předlohy)
# --------------------------------------------------------------------------
TRIM_W = 90 * mm            # čistý formát
TRIM_H = 50 * mm
BLEED = 3 * mm              # spad
MARGIN = 8.29 * mm          # okraj stránky kolem čistého formátu
PAGE_W = TRIM_W + 2 * MARGIN    # 302.126 pt
PAGE_H = TRIM_H + 2 * MARGIN    # 188.74 pt

MARK_LEN = 5 * mm           # délka ořezové značky
MARK_W = 0.25               # tloušťka ořezové značky v pt
STRIP_W = 10 * mm           # červený pruh: 7 mm v čistém formátu + 3 mm spad

# --------------------------------------------------------------------------
# Barvy - CMYK jako v tiskové předloze
# --------------------------------------------------------------------------
VEKRA_RED = CMYKColor(0, 1, 0.71, 0.08)
TEXT_BLACK = CMYKColor(0, 0, 0, 1)
WHITE = CMYKColor(0, 0, 0, 0)


def x_(mm_from_left):
    """Vodorovná souřadnice: mm od levé ořezové linie -> body PDF."""
    return MARGIN + mm_from_left * mm


def y_(mm_from_top):
    """Svislá souřadnice: mm od horní ořezové linie -> body PDF."""
    return MARGIN + TRIM_H - mm_from_top * mm


def format_phone(raw: str) -> str:
    """Sjednotí telefon na tvar '+420 702 186 890'.

    Přijme cokoliv: '702186890', '+420702186890', '00420 702 186 890'.
    Co nerozpozná, vrátí beze změny.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 9:                      # zadáno bez předvolby
        digits = "420" + digits
    if digits.startswith("420") and len(digits) == 12:
        body = digits[3:]
        return "+420 " + " ".join(body[i:i + 3] for i in range(0, 9, 3))
    return (raw or "").strip()


def _fit_size(text, font, size, max_w):
    """Zmenší velikost písma, dokud se text nevejde do max_w."""
    while size > 4 and pdfmetrics.stringWidth(text, font, size) > max_w:
        size -= 0.25
    return size


def build_vcard(jmeno, pozice, telefon, email, adresa,
                web="https://www.vekra.cz"):
    cleaned = re.sub(r"\s+", " ", jmeno).strip()
    parts = cleaned.split(" ")
    titles = [p for p in parts if "." in p]
    name_parts = [p for p in parts if "." not in p]
    given = name_parts[0] if name_parts else ""
    family = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    title_str = " ".join(titles)

    tel = re.sub(r"\s+", "", format_phone(telefon))
    adr_oneline = re.sub(r"\s*\n\s*", ", ", adresa.strip())

    return (
        "BEGIN:VCARD\r\n"
        "VERSION:3.0\r\n"
        f"N:{family};{given};;{title_str};\r\n"
        f"FN:{cleaned}\r\n"
        "ORG:VEKRA\r\n"
        f"TITLE:{pozice}\r\n"
        f"TEL;TYPE=CELL:{tel}\r\n"
        f"EMAIL:{email}\r\n"
        f"ADR;TYPE=WORK:;;{adr_oneline};;;;\r\n"
        f"URL:{web}\r\n"
        "END:VCARD\r\n"
    )


def render_qr_png(vcard_text: str, size_px: int = 300) -> bytes:
    """Vykreslí QR kód jako samostatný PNG (pro náhled, scan z mobilu)."""
    qr = QrCodeWidget(vcard_text, barLevel="M")
    qr.draw()  # inicializuje matrix
    matrix = qr.qr.modules
    n = qr.qr.moduleCount

    margin = 4
    scale = max(1, size_px // (n + 2 * margin))
    img_size = (n + 2 * margin) * scale
    img = Image.new("RGB", (img_size, img_size), "white")
    d = ImageDraw.Draw(img)
    for r in range(n):
        for col in range(n):
            if matrix[r][col]:
                x0 = (col + margin) * scale
                y0 = (r + margin) * scale
                d.rectangle([x0, y0, x0 + scale, y0 + scale], fill="black")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _draw_crop_marks(c):
    """Ořezové značky na skutečných ořezových liniích (90 x 50 mm).

    Vedou od okraje stránky dovnitř, končí kousek před spadem - proto se
    nikdy nekříží s červeným pruhem.
    """
    c.saveState()
    c.setStrokeColor(TEXT_BLACK)
    c.setLineWidth(MARK_W)
    for x in (MARGIN, MARGIN + TRIM_W):                 # svislé značky
        c.line(x, 0, x, MARK_LEN)
        c.line(x, PAGE_H, x, PAGE_H - MARK_LEN)
    for y in (MARGIN, MARGIN + TRIM_H):                 # vodorovné značky
        c.line(0, y, MARK_LEN, y)
        c.line(PAGE_W, y, PAGE_W - MARK_LEN, y)
    c.restoreState()


def _draw_qr(c, vcard_text, x, y, size):
    qr = QrCodeWidget(vcard_text, barLevel="M")
    qr.barBorder = 0          # bez vlastního okraje - klidová zóna je bílá plocha vizitky
    bounds = qr.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]
    d = Drawing(size, size, transform=[size / qr_w, 0, 0, size / qr_h, 0, 0])
    d.add(qr)
    renderPDF.draw(d, c, x, y)


def _draw_red_strip(c):
    """Červený pruh vpravo - jen do spadu, ne přes celou stránku."""
    c.saveState()
    c.setFillColor(VEKRA_RED)
    c.rect(
        MARGIN + TRIM_W + BLEED - STRIP_W,    # levá hrana pruhu
        MARGIN - BLEED,                       # spodní hrana = spad
        STRIP_W,
        TRIM_H + 2 * BLEED,                   # výška = jen spad
        fill=1, stroke=0,
    )
    # svislý nápis www.vekra.cz, čte se zdola nahoru, vystředěný na výšku
    c.setFillColor(WHITE)
    c.setFont("VekraSans-Bold", 12)
    label = "www.vekra.cz"
    label_w = pdfmetrics.stringWidth(label, "VekraSans-Bold", 12)
    c.translate(x_(88.13), y_(25) - label_w / 2)
    c.rotate(90)
    c.drawString(0, 0, label)
    c.restoreState()


def pdf_na_png(pdf_bytes: bytes, scale: float = 3.0) -> bytes:
    """Převede první stránku PDF na PNG (pro náhled v prohlížeči).

    Náhled přes obrázek funguje i v přísně nastaveném Edge / firemních
    prohlížečích, které blokují vkládání PDF přes data: URL.
    """
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    page = doc[0]
    pil_image = page.render(scale=scale).to_pil()
    buf = io.BytesIO()
    pil_image.save(buf, format="PNG")
    return buf.getvalue()


def wrap_adresa(adresa: str) -> str:
    """Zalamí adresu na max 3 řádky.
    Funguje pro formáty: newlines, svislítka, nebo čárkami oddělený jednořádkový string.
    """
    if "\n" in adresa:
        return adresa
    adresa = adresa.replace(" | ", "\n")
    if "\n" in adresa:
        return adresa
    # PSČ (XXX XX) automaticky na nový řádek
    s_psz = re.sub(r',?\s*(\d{3}\s\d{2}\b)', r'\n\1', adresa)
    if "\n" in s_psz:
        radky = [r.strip() for r in s_psz.split('\n') if r.strip()]
        # Pokud první řádek (před PSČ) obsahuje čárku a ještě nemáme 3 řádky,
        # rozděl ho na první čárce (typicky "Obchodní zastoupení, Ulice").
        if len(radky) < 3 and ',' in radky[0]:
            prvni, zbytek = radky[0].split(',', 1)
            radky = [prvni.strip(), zbytek.strip()] + radky[1:]
        return '\n'.join(radky[:3])
    # Rozděl na max 3 části po čárce
    casti = [c.strip() for c in adresa.split(',')]
    if len(casti) <= 3:
        return '\n'.join(casti)
    return '\n'.join([casti[0], ', '.join(casti[1:-1]), casti[-1]])


def generate_business_card_bytes(data: dict) -> bytes:
    """Vyrobí PDF vizitku a vrátí ji jako bytes."""
    data = dict(data)
    data["adresa"] = wrap_adresa(data.get("adresa", ""))
    telefon = format_phone(data.get("telefon", ""))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Vizitka VEKRA - {data['jmeno']}")

    _draw_red_strip(c)
    _draw_crop_marks(c)

    # --- logo: šířka 29,7 mm, horní hrana 5,38 mm od ořezu -----------------
    logo_w = 29.7 * mm
    logo_h = logo_w * (241 / 759)
    c.drawImage(LOGO_PATH, x_(5.16), y_(5.38) - logo_h,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, anchor="nw", mask="auto")

    # --- QR kód: 17,9 mm, pravá hrana 77,51 mm od levého ořezu -------------
    vcard = build_vcard(
        data["jmeno"], data["pozice"], telefon,
        data["email"], data["adresa"]
    )
    qr_size = 17.9 * mm
    _draw_qr(c, vcard, x_(77.51) - qr_size, y_(5.29) - qr_size, qr_size)

    # --- jméno -------------------------------------------------------------
    c.setFillColor(TEXT_BLACK)
    parts = data["jmeno"].strip().split()
    formatted = " ".join(p if "." in p else p.upper() for p in parts)
    size = _fit_size(formatted, "VekraSans-Bold", 12, 52 * mm)
    c.setFont("VekraSans-Bold", size)
    c.drawString(x_(5.44), y_(24.83), formatted)

    # --- pozice ------------------------------------------------------------
    size = _fit_size(data["pozice"], "VekraSans", 7, 76 * mm)
    c.setFont("VekraSans", size)
    c.drawString(x_(5.25), y_(28.33), data["pozice"])

    # --- červená dělicí linka ---------------------------------------------
    c.setStrokeColor(VEKRA_RED)
    c.setLineWidth(0.96)                      # 0,34 mm
    c.line(x_(5.2), y_(33.76), x_(82.5), y_(33.76))

    # --- levý sloupec: telefon, e-mail, web --------------------------------
    c.setFillColor(TEXT_BLACK)
    c.setFont("VekraSans-Bold", 9.5)
    c.drawString(x_(5.33), y_(39.94), telefon)
    c.setFont("VekraSans", 7)
    c.drawString(x_(5.42), y_(42.85), data["email"])
    c.drawString(x_(5.25), y_(45.64), "www.vekra.cz")

    # --- pravý sloupec: adresa (řádky zarovnané na levý sloupec) -----------
    addr_lines = [l.strip() for l in data["adresa"].split("\n") if l.strip()]
    for line, base in zip(addr_lines[:3], (40.01, 42.74, 45.57)):
        size = _fit_size(line, "VekraSans", 7, 38 * mm)
        c.setFont("VekraSans", size)
        c.drawString(x_(43.72), y_(base), line)

    c.showPage()
    c.save()
    return buf.getvalue()
