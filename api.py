"""
VEKRA – API pro generování vizitek.
Endpointy: GET / (health check), POST /generuj (JSON+base64), POST /pdf (binární PDF)
Hlavička: X-API-Key: <klíč z Render Environment>
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


def _safe_filename(jmeno: str) -> str:
    return re.sub(r"\s+", "_", re.sub(r"[^\w\s-]", "", _bez_diakritiky(jmeno)).strip())


API_KEY = os.environ.get("API_KEY", "")

app = FastAPI(title="VEKRA – generátor vizitek", version="1.0")

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
    """JSON s PDF v base64 – pro Make.com a Power Automate."""
    pdf, d = _zpracuj(data, x_api_key)
    return {
        "filename": f"vizitka_{_safe_filename(d['jmeno'])}.pdf",
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pocet_kusu": d["pocet_kusu"],
        "jmeno": d["jmeno"],
    }


@app.post("/pdf")
def generuj_pdf(data: VizitkaData, x_api_key: str = Header(default="")):
    """PDF přímo jako soubor – pro webový formulář."""
    pdf, d = _zpracuj(data, x_api_key)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f'attachment; filename="vizitka_{_safe_filename(d["jmeno"])}.pdf"'},
    )
