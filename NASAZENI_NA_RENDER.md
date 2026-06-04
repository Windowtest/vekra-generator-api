# Krok 1: Nasazení generátoru na Render.com

Tahle služba je „generátor vizitek" – webové API, které Power Automate zavolá
pokaždé, když přijde nová objednávka. Vrátí hotové PDF.

Budeš potřebovat **GitHub účet** (už ho máš z prototypu) a **Render účet** (zdarma).

---

## A) Nahraj soubory na GitHub

1. Na **github.com** klikni **+ → New repository**.
2. Název např. `vekra-generator-api`, zvol **Public**, **Create repository**.
3. Klikni **uploading an existing file** a nahraj VŠECHNY tyto soubory:
   - `api.py`
   - `generator.py`
   - `requirements.txt`
   - `render.yaml`
   - `vekra_logo.png`
   - složku `fonts` (s `Geograph-Regular.ttf` a `Geograph-Bold.ttf`)
4. **Commit changes**.

> Strukturu složky `fonts` zachovej – přetáhni celou složku.

## B) Vytvoř službu na Render

1. Jdi na **render.com** → **Sign up** → přihlas se přes **GitHub**.
2. Na dashboardu klikni **New +** → **Web Service**.
3. Vyber repozitář `vekra-generator-api` → **Connect**.
4. Render si přečte `render.yaml` a předvyplní nastavení:
   - **Name:** vekra-generator
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn api:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** Free
5. Klikni **Create Web Service** (nebo **Apply**).
6. Render službu sestaví (2–4 minuty). Až nahoře svítí zeleně **Live**, je hotovo.

## C) Zjisti adresu a API klíč

1. **Adresa služby** je nahoře na stránce služby, např.
   `https://vekra-generator.onrender.com`. Tu si poznamenej.
2. **API klíč** vygeneroval Render automaticky. Najdeš ho:
   - V levém menu služby klikni **Environment**.
   - U položky `API_KEY` klikni na oko 👁 / **Reveal** → zkopíruj hodnotu.
   - Tu si taky poznamenej – budeš ji potřebovat v Power Automate.

## D) Ověř, že to žije

Otevři v prohlížeči adresu služby (z bodu C1). Měl bys vidět:
```json
{"status": "ok", "service": "VEKRA generátor vizitek"}
```
Pokud ano – generátor běží. 🎉

---

## Důležité: bezplatný tier „usíná"

Render na free plánu službu po ~15 minutách nečinnosti **uspí**. První požadavek
po probuzení pak trvá ~30–50 sekund (služba se nahazuje), další jsou rychlé.

Pro výrobu vizitek to nevadí – pár sekund čekání u občasné objednávky nikoho netrápí.
Power Automate má ve výchozím stavu dost dlouhý timeout, takže probuzení v pohodě počká.
(Kdyby to později vadilo, dá se přejít na placený plán ~7 USD/měs, kde služba neusíná.)

## Co dál

Až budeš mít **adresu služby** a **API klíč**, ozvi se – postavíme Power Automate flow,
který tohle API zavolá a pošle hotovou vizitku e-mailem do tiskárny.

## Jak otestovat ručně (volitelné, pro zvídavé)

Adresu a klíč můžeš vyzkoušet i bez Power Automate – např. nástrojem na
testování API. POST na `https://…onrender.com/generuj`, hlavička
`X-API-Key: tvůj-klíč`, tělo JSON s údaji vizitky. Vrátí JSON s `pdf_base64`.
Ale tohle není nutné – ověření v bodě D stačí.
