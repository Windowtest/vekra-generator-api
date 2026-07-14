"""
Generátor PDF vizitek VEKRA s QR kódem (vCard).
Standalone verze pro lokální použití.
"""

import io
import os
import re

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.colors import HexColor, white
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

PAGE_W = 302.126
PAGE_H = 188.74
BLEED = 8.5

VEKRA_RED = HexColor("#E30613")
TEXT_BLACK = HexColor("#1A1A1A")
TEXT_GRAY = HexColor("#333333")


def build_vcard(jmeno, pozice, telefon, email, adresa,
                web="https://www.vekra.cz"):
    cleaned = re.sub(r"\s+", " ", jmeno).strip()
    parts = cleaned.split(" ")
    titles = [p for p in parts if "." in p]
    name_parts = [p for p in parts if "." not in p]
    given = name_parts[0] if name_parts else ""
    family = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""
    title_str = " ".join(titles)

    tel = re.sub(r"\s+", "", telefon)
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
    c.setStrokeColor(TEXT_BLACK)
    c.setLineWidth(0.25)
    GAP = 2
    corners = [
        (BLEED, BLEED),
        (PAGE_W - BLEED, BLEED),
        (BLEED, PAGE_H - BLEED),
        (PAGE_W - BLEED, PAGE_H - BLEED),
    ]
    for (x, y) in corners:
        if x == BLEED:
            c.line(x - BLEED, y, x - GAP, y)
        else:
            c.line(x + GAP, y, x + BLEED, y)
        if y == BLEED:
            c.line(x, y - BLEED, x, y - GAP)
        else:
            c.line(x, y + GAP, x, y + BLEED)


def _draw_qr(c, vcard_text, x, y, size):
    qr = QrCodeWidget(vcard_text, barLevel="M")
    bounds = qr.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]
    d = Drawing(size, size, transform=[size / qr_w, 0, 0, size / qr_h, 0, 0])
    d.add(qr)
    renderPDF.draw(d, c, x, y)


def _draw_red_strip(c):
    strip_w = 17
    strip_x = PAGE_W - BLEED - strip_w
    c.setFillColor(VEKRA_RED)
    c.rect(strip_x, 0, strip_w + BLEED, PAGE_H, fill=1, stroke=0)
    c.saveState()
    c.setFillColor(white)
    c.setFont("VekraSans-Bold", 8)
    text_x = strip_x + strip_w / 2 + 3
    text_y = PAGE_H / 2 - 28
    c.translate(text_x, text_y)
    c.rotate(90)
    c.drawString(0, 0, "www.vekra.cz")
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
    import re
    if "\n" in adresa:
        return adresa
    adresa = adresa.replace(" | ", "\n")
    if "\n" in adresa:
        return adresa
    # PSČ (XXX XX) automaticky na nový řádek
    s_psz = re.sub(r',?\s*(\d{3}\s\d{2}\b)', r'\n\1', adresa)
    if "\n" in s_psz:
        radky = [r.strip() for r in s_psz.split('\n') if r.strip()]
        if len(radky[0]) > 35:
            casti = [c.strip() for c in radky[0].split(',')]
            mid = max(1, len(casti) // 2)
            radky = [', '.join(casti[:mid]), ', '.join(casti[mid:])] + radky[1:]
        return '\n'.join(radky[:3])
    # Rozděl na max 3 části po čárce
    casti = [c.strip() for c in adresa.split(',')]
    if len(casti) <= 3:
        return '\n'.join(casti)
    return '\n'.join([casti[0], ', '.join(casti[1:-1]), casti[-1]])


def generate_business_card_bytes(data: dict) -> bytes:
    """Vyrobí PDF vizitku a vrátí ji jako bytes."""
    # Zalamení adresy na max 3 řádky (pro různé formáty vstupu)
    data = dict(data)
    data["adresa"] = wrap_adresa(data.get("adresa", ""))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Vizitka VEKRA - {data['jmeno']}")

    _draw_red_strip(c)
    _draw_crop_marks(c)

    logo_x = BLEED + 18
    logo_h = 50
    logo_w = logo_h * (759 / 241)
    logo_y = PAGE_H - BLEED - logo_h - 17
    c.drawImage(LOGO_PATH, logo_x, logo_y, width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto")

    vcard = build_vcard(
        data["jmeno"], data["pozice"], data["telefon"],
        data["email"], data["adresa"]
    )
    qr_size = 60
    qr_x = PAGE_W - BLEED - 17 - qr_size - 14
    qr_y = PAGE_H - BLEED - qr_size - 12
    _draw_qr(c, vcard, qr_x, qr_y, qr_size)

    name_y = logo_y - 21
    c.setFillColor(TEXT_BLACK)
    c.setFont("VekraSans-Bold", 11.5)
    parts = data["jmeno"].strip().split()
    formatted = " ".join(p if "." in p else p.upper() for p in parts)
    c.drawString(logo_x, name_y, formatted)

    c.setFont("VekraSans", 7.5)
    c.setFillColor(TEXT_GRAY)
    c.drawString(logo_x, name_y - 10, data["pozice"])

    line_y = name_y - 25
    c.setStrokeColor(VEKRA_RED)
    c.setLineWidth(0.6)
    c.line(logo_x, line_y, PAGE_W - BLEED - 17 - 6, line_y)

    col_y = line_y - 14
    c.setFillColor(TEXT_BLACK)
    c.setFont("VekraSans-Bold", 9)
    c.drawString(logo_x, col_y, data["telefon"])
    c.setFont("VekraSans", 7)
    c.setFillColor(TEXT_GRAY)
    c.drawString(logo_x, col_y - 10, data["email"])
    c.drawString(logo_x, col_y - 20, "www.vekra.cz")

    addr_lines = [l.strip() for l in data["adresa"].split("\n") if l.strip()]
    addr_x = logo_x + 130
    c.setFont("VekraSans", 7)
    for i, line in enumerate(addr_lines[:3]):
        c.drawString(addr_x, col_y - i * 10, line)

    c.showPage()
    c.save()
    return buf.getvalue()
