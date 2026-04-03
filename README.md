# GEO-agentti

WordPress-sisällön optimointi AI-hakukoneita varten (Generative Engine Optimization).

Agentti hakee sivustosi WordPress-sivut tai -postaukset, analysoi niiden GEO-pisteet Claude-mallilla ja ehdottaa parannettua sisältöä. Muutokset päivitetään WordPressiin vasta hyväksyntäsi jälkeen.

**Tuetut AI-hakukoneet:** Perplexity, ChatGPT Search, Google AI Overviews

---

## Vaatimukset

- Python 3.11+
- Anthropic API -avain
- WordPress-sivusto, jossa REST API käytössä
- WordPress Application Password (ei tavallinen salasana)

```bash
pip install anthropic requests streamlit
```

---

## Asennus

**1. Kloonaa repo**

```bash
git clone <repo-url>
cd geo-agent
```

**2. Luo ympäristömuuttujatiedosto**

```bash
cp .geo.env.example ~/.geo.env
chmod 600 ~/.geo.env
```

Muokkaa `~/.geo.env` omilla arvoillasi:

```env
ANTHROPIC_API_KEY="sk-ant-..."
WP_URL="https://sinun-sivustosi.fi"
WP_USER="kayttajatunnus"
WP_PASSWORD="xxxx xxxx xxxx xxxx"
```

> WordPress Application Password luodaan: WP Admin → Käyttäjät → Profiili → Application Passwords

**3. Tarkista `run_geo.sh`**

```bash
chmod +x run_geo.sh
```

---

## Käyttö

### CLI-versio (human-in-the-loop)

```bash
./run_geo.sh
```

Agentti käy sivut läpi yksi kerrallaan, näyttää muutosehdotuksen ja kysyy:
- `y` — päivitä WordPressiin
- `n` — ohita
- `q` — lopeta

### Dashboard (Streamlit)

```bash
source ~/.geo.env
streamlit run geo_dashboard.py
```

Avaa selaimessa `http://localhost:8501`. Syötä asetukset sivupalkissa ja hallinnoi optimointeja visuaalisesti.

---

## Asetukset (`geo_agent.py`)

| Muuttuja | Oletusarvo | Kuvaus |
|---|---|---|
| `MAX_POSTS` | `5` | Kuinka monta kohdetta käsitellään kerralla |
| `CONTENT_TYPE` | `"pages"` | `"pages"` = sivut, `"posts"` = blogipostaukset |
| `TARGET_SLUG` | `""` | Tietyn sivun slug, tyhjä = kaikki |

---

## GEO-optimoinnin periaatteet

1. **Kysymys-vastaus-rakenne** — AI-hakukoneet poimivat "Mikä on X? X on..." -rakenteita
2. **Faktat ja luvut** — konkreettiset tilastot ja prosentit lisäävät siteerattavuutta
3. **Auktoriteetti** — asiantuntijuus ja kokemus tulee mainita selkeästi
4. **Määritelmät** — keskeiset käsitteet selitetään yksinkertaisesti
5. **Tiivistetyt väitteet** — kappaleen ensimmäinen lause = pääväite
6. **Rakenne** — lyhyet kappaleet (2–4 lausetta), selkeät väliotsikot
7. **Schema-ystävällisyys** — sisältö kirjoitetaan kuin FAQ- tai HowTo-skeemaa täyttäen

---

## Tietoturva

- Älä koskaan tallenna API-avaimia tai salasanoja koodiin tai git-repoon
- `~/.geo.env` on rajattu vain omistajan luettavaksi (`chmod 600`)
- `.gitignore` estää ympäristömuuttujatiedostojen päätymisen repoon
