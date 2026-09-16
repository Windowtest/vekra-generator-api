"""
VEKRA – API pro generování vizitek.

Webová služba, kterou volá Power Automate. Přijme údaje zaměstnance,
vrátí hotové PDF vizitky (s QR kódem) zakódované v base64.

Endpointy:
    GET  /          – kontrola, že služba běží (health check)
    POST /generuj   – vygeneruje vizitku

POST /generuj očekává JSON:
{
  "jmeno":   "Mgr. Jakub Červík",
  "pozice":  "Business Development Manager B2B",
  "telefon": "+420 728 449 422",
  "email":   "jakub.cervik@vekra.cz",
  "adresa":  "Obchodní zastoupení | České Vrbné 2393 | 370 11 České Budějovice",
  "pocet_kusu": 200
}
(adresu lze psát na jeden řádek se svislítky "|" – převede se na zalomení)

Hlavička požadavku musí obsahovat:  X-API-Key: <tajný klíč>

Odpověď (JSON):
{
  "filename":   "vizitka_Mgr_Jakub_Cervik.pdf",
  "pdf_base64": "JVBERi0xLjMK...",
  "pocet_kusu": 200,
  "jmeno":      "Mgr. Jakub Červík"
}
"""

import base64
import os
import re
import unicodedata

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from generator import generate_business_card_bytes


def _bez_diakritiky(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if not unicodedata.combining(c))


API_KEY = os.environ.get("API_KEY", "")

app = FastAPI(title="VEKRA – generátor vizitek", version="1.0")

# CORS – povolí volání z prohlížeče (formulář otevřený lokálně i na webu)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class VizitkaData(BaseModel):
    jmeno: str
    pozice: str
    telefon: str
    email: str
    adresa: str
    pocet_kusu: int = 0


@app.get("/")
def health():
    """Health check – Render i ty si ověříš, že služba žije."""
    return {"status": "ok", "service": "VEKRA generátor vizitek"}


@app.post("/generuj")
def generuj(data: VizitkaData, x_api_key: str = Header(default="")):
    # Ověření klíče
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Neplatný nebo chybějící API klíč.")

    d = data.model_dump()

    # Adresu lze poslat jednořádkově se svislítky – převedeme na zalomení řádků
    d["adresa"] = d["adresa"].replace(" | ", "\n").replace("|", "\n").strip()

    # Validace – musí být vyplněno vše podstatné
    chybi = [k for k in ["jmeno", "pozice", "telefon", "email", "adresa"]
             if not (d.get(k) or "").strip()]
    if chybi:
        raise HTTPException(
            status_code=400,
            detail=f"Chybí povinná pole: {', '.join(chybi)}",
        )

    try:
        pdf = generate_business_card_bytes(d)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chyba generování: {e}")

    safe = _bez_diakritiky(d["jmeno"])
    safe = re.sub(r"[^\w\s-]", "", safe)
    safe = re.sub(r"\s+", "_", safe.strip())

    return {
        "filename": f"vizitka_{safe}.pdf",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pocet_kusu": d["pocet_kusu"],
        "jmeno": d["jmeno"],
    }


class VizitkaData(BaseModel):
    jmeno: str
    pozice: str
    telefon: str
    email: str
    adresa: str
    pocet_kusu: int = 0


def _zpracuj(data: VizitkaData, api_key: str):
    if API_KEY and api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Neplatný nebo chybějící API klíč.")
    d = data.model_dump()
    d["adresa"] = d["adresa"].replace(" | ", "\n").replace("|", "\n").strip()
    chybi = [k for k in ["jmeno", "pozice", "telefon", "email", "adresa"]
             if not (d.get(k) or "").strip()]
    if chybi:
        raise HTTPException(status_code=400,
                            detail=f"Chybí povinná pole: {', '.join(chybi)}")
    try:
        return generate_business_card_bytes(d), d
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chyba generování: {e}")


@app.get("/")
def health():
    return {"status": "ok", "service": "VEKRA generátor vizitek"}


@app.post("/generuj")
def generuj(data: VizitkaData, x_api_key: str = Header(default="")):
    """Vrátí JSON s PDF zakódovaným v base64 (pro Power Automate / Make.com)."""
    pdf, d = _zpracuj(data, x_api_key)
    safe = re.sub(r"\s+", "_", re.sub(r"[^\w\s-]", "", _bez_diakritiky(d["jmeno"])).strip())
    return {
        "filename": f"vizitka_{safe}.pdf",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pocet_kusu": d["pocet_kusu"],
        "jmeno": d["jmeno"],
    }


@app.post("/pdf")
def generuj_pdf(data: VizitkaData, x_api_key: str = Header(default="")):
    """Vrátí PDF přímo jako binární soubor (pro Make.com přílohu a webový formulář)."""
    pdf, d = _zpracuj(data, x_api_key)
    safe = re.sub(r"\s+", "_", re.sub(r"[^\w\s-]", "", _bez_diakritiky(d["jmeno"])).strip())
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="vizitka_{safe}.pdf"'},
    )
