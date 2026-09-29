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

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.lib.colors import CMYKColor
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from PIL import Image, ImageDraw

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
LOGO_PATH = os.path.join(BASE_DIR, "vekra_logo.pdf")   # vektorové logo v křivkách
ICC_PATH = os.path.join(BASE_DIR, "icc", "FOGRA39L_coated.icc")

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

# Logo: šířka 29,7 mm, levá hrana 5,16 mm a horní hrana 5,38 mm od ořezu
LOGO_W = 29.7 * mm
LOGO_X_MM = 5.16
LOGO_TOP_MM = 5.38

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
    """QR kód vykreslený přímo jako černé (K100) obdélníky.

    Nepoužívá renderPDF, který do PDF přidává nevložený font Times-Roman
    (neprojde kontrolou PDF/X-1a). Sousední moduly v řádku se slévají
    do jednoho obdélníku, aby PDF zůstalo malé.
    """
    qr = QrCodeWidget(vcard_text, barLevel="M")
    qr.draw()                                # inicializuje matici
    modules = qr.qr.modules
    n = qr.qr.moduleCount
    m = size / n                             # velikost jednoho modulu
    c.saveState()
    c.setFillColor(TEXT_BLACK)
    for r in range(n):
        col = 0
        while col < n:
            if modules[r][col]:
                s = col
                while col < n and modules[r][col]:
                    col += 1
                c.rect(x + s * m, y + size - (r + 1) * m,
                       (col - s) * m, m, fill=1, stroke=0)
            else:
                col += 1
    c.restoreState()


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


_LOGO_BBOX_CACHE = None


def _logo_bbox():
    """Zjistí rozsah samotné kresby uvnitř PDF s logem.

    Logo je uložené na velké stránce s bílým okolím; potřebujeme vědět, kde
    kresba doopravdy začíná a končí, aby šla do vizitky umístit přesně.
    Spočítá se z vykreslovacích operátorů a výsledek se cachuje.
    """
    global _LOGO_BBOX_CACHE
    if _LOGO_BBOX_CACHE is not None:
        return _LOGO_BBOX_CACHE

    import pikepdf

    with pikepdf.open(LOGO_PATH) as doc:
        page = doc.pages[0]
        obsah = page.Contents
        data = b"".join(
            s.read_bytes() for s in
            (obsah if isinstance(obsah, pikepdf.Array) else [obsah])
        ).decode("latin-1")

    def nasob(m1, m2):
        a1, b1, c1, d1, e1, f1 = m1
        a2, b2, c2, d2, e2, f2 = m2
        return (a1 * a2 + b1 * c2, a1 * b2 + b1 * d2,
                c1 * a2 + d1 * c2, c1 * b2 + d1 * d2,
                e1 * a2 + f1 * c2 + e2, e1 * b2 + f1 * d2 + f2)

    def bod(m, x, y):
        a, b, c, d, e, f = m
        return (a * x + c * y + e, b * x + d * y + f)

    xs, ys = [], []
    ctm = (1, 0, 0, 1, 0, 0)
    zasobnik, cisla = [], []

    for token in data.split():
        if re.fullmatch(r"-?\d*\.?\d+", token):
            cisla.append(float(token))
            continue
        if token == "cm" and len(cisla) >= 6:
            ctm = nasob(tuple(cisla[-6:]), ctm)
        elif token == "q":
            zasobnik.append(ctm)
        elif token == "Q" and zasobnik:
            ctm = zasobnik.pop()
        elif token in ("m", "l") and len(cisla) >= 2:
            xy = bod(ctm, cisla[-2], cisla[-1])
            xs.append(xy[0]); ys.append(xy[1])
        elif token == "c" and len(cisla) >= 6:
            for i in (0, 2, 4):
                xy = bod(ctm, cisla[-6 + i], cisla[-5 + i])
                xs.append(xy[0]); ys.append(xy[1])
        elif token == "re" and len(cisla) >= 4:
            rx, ry, rw, rh = cisla[-4:]
            # obdélník přes celou stránku je ořezová oblast, ne kresba
            if not (rw > 500 and rh > 400):
                for px, py in ((rx, ry), (rx + rw, ry),
                               (rx, ry + rh), (rx + rw, ry + rh)):
                    xy = bod(ctm, px, py)
                    xs.append(xy[0]); ys.append(xy[1])
        cisla = []

    if not xs:
        raise RuntimeError("V logu se nepodařilo najít žádnou kresbu.")

    _LOGO_BBOX_CACHE = (min(xs), min(ys), max(xs), max(ys))
    return _LOGO_BBOX_CACHE


def _vloz_vektorove_logo(pdf_bytes: bytes) -> bytes:
    """Vloží firemní logo jako VEKTOR (křivky) místo bitmapy.

    Logo je samostatné PDF v křivkách a v CMYK. Vezmeme z něj stránku jako
    Form XObject, spočítáme měřítko podle skutečného rozsahu kresby a umístíme
    ho do vizitky. Tiskárna tak dostane ostrou vektorovou kresbu, ne rastr.
    """
    import pikepdf

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))
    logo_pdf = pikepdf.open(LOGO_PATH)

    xobj = pdf.copy_foreign(pikepdf.Page(logo_pdf.pages[0]).as_form_xobject())

    # Rozsah samotné kresby uvnitř stránky loga (bez okolní bílé plochy)
    x0, y0, x1, y1 = _logo_bbox()
    scale = LOGO_W / (x1 - x0)

    page = pdf.pages[0]
    if "/Resources" not in page:
        page.Resources = pikepdf.Dictionary()
    if "/XObject" not in page.Resources:
        page.Resources.XObject = pikepdf.Dictionary()
    page.Resources.XObject["/VekraLogo"] = xobj

    # Posun tak, aby levá hrana kresby byla na LOGO_X_MM
    # a horní hrana na LOGO_TOP_MM od ořezu.
    tx = x_(LOGO_X_MM) - scale * x0
    ty = y_(LOGO_TOP_MM) - scale * y1
    vlozeni = (f"\nq {scale:.6f} 0 0 {scale:.6f} {tx:.4f} {ty:.4f} cm "
               f"/VekraLogo Do Q\n").encode("ascii")

    page.contents_add(pikepdf.Stream(pdf, vlozeni), prepend=False)

    out = io.BytesIO()
    pdf.save(out)
    return out.getvalue()


def _na_pdfx(pdf_bytes: bytes, title: str) -> bytes:
    """Doplní do PDF náležitosti standardu PDF/X-1a:2003 pro tiskárnu:
      - výstupní záměr (OutputIntent) s tiskovým profilem FOGRA39 Coated,
      - klíč verze GTS_PDFXVersion a Trapped v informacích dokumentu.
    TrimBox/BleedBox a CMYK barvy nastavuje už samotné generování.
    """
    import pikepdf
    pdf = pikepdf.open(io.BytesIO(pdf_bytes))

    with open(ICC_PATH, "rb") as f:
        icc = pikepdf.Stream(pdf, f.read())
    icc.N = 4                                # CMYK profil = 4 kanály

    pdf.Root.OutputIntents = pikepdf.Array([pikepdf.Dictionary(
        Type=pikepdf.Name.OutputIntent,
        S=pikepdf.Name.GTS_PDFX,
        OutputConditionIdentifier="FOGRA39",
        OutputCondition="Coated FOGRA39 (ISO 12647-2:2004)",
        Info="Coated FOGRA39 (ISO 12647-2:2004)",
        RegistryName="http://www.color.org",
        DestOutputProfile=icc,
    )])

    pdf.docinfo["/Title"] = title
    pdf.docinfo["/GTS_PDFXVersion"] = "PDF/X-1a:2003"
    pdf.docinfo["/Trapped"] = pikepdf.Name("/False")

    out = io.BytesIO()
    pdf.save(out, force_version="1.4")
    return out.getvalue()


def generate_business_card_bytes(data: dict) -> bytes:
    """Vyrobí PDF vizitku a vrátí ji jako bytes."""
    data = dict(data)
    data["adresa"] = wrap_adresa(data.get("adresa", ""))
    telefon = format_phone(data.get("telefon", ""))

    buf = io.BytesIO()
    c = canvas.Canvas(
        buf,
        pagesize=(PAGE_W, PAGE_H),
        # Ořezové rámečky pro tiskárnu:
        #   TrimBox  = čistý formát 90 x 50 mm (kde se řeže)
        #   BleedBox = čistý formát + 3 mm spad
        trimBox=(MARGIN, MARGIN, MARGIN + TRIM_W, MARGIN + TRIM_H),
        bleedBox=(MARGIN - BLEED, MARGIN - BLEED,
                  MARGIN + TRIM_W + BLEED, MARGIN + TRIM_H + BLEED),
        # Vynutí CMYK u všech barev – žádné RGB v tiskovém PDF
        enforceColorSpace="cmyk",
        initialFontName="VekraSans",
    )
    c.setTitle(f"Vizitka VEKRA - {data['jmeno']}")

    _draw_red_strip(c)
    _draw_crop_marks(c)

    # --- logo se vkládá jako vektor až po uložení (viz _vloz_vektorove_logo) ---

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
    c.drawString(x_(5.25), y_(24.83), formatted)

    # --- pozice ------------------------------------------------------------
    size = _fit_size(data["pozice"], "VekraSans", 7, 76 * mm)
    c.setFont("VekraSans", size)
    c.drawString(x_(5.25), y_(28.33), data["pozice"])

    # --- červená dělicí linka ---------------------------------------------
    c.setStrokeColor(VEKRA_RED)
    c.setLineWidth(0.96)                      # 0,34 mm
    c.line(x_(5.2), y_(33.76), x_(84), y_(33.76))

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
    s_logem = _vloz_vektorove_logo(buf.getvalue())
    return _na_pdfx(s_logem, f"Vizitka VEKRA - {data['jmeno']}")
