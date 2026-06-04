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
from pydantic import BaseModel

from generator import generate_business_card_bytes


def _bez_diakritiky(s: str) -> str:
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if not unicodedata.combining(c))

# Tajný klíč – nastaví se na Renderu jako proměnná prostředí API_KEY.
# Když není nastaven, kontrola se přeskočí (jen pro lokální testování).
API_KEY = os.environ.get("API_KEY", "")

app = FastAPI(title="VEKRA – generátor vizitek", version="1.0")


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
