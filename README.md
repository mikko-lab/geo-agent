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
git clone https://github.com/mikko-lab/geo-agent.git
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
| `PROTECTED_SLUGS` | *(lista)* | Slugit joita agentti ei koskaan muokkaa |

---

## Turvallisuusominaisuudet

### Suojatut slugit

Tiedostossa `geo_agent.py` on lista `PROTECTED_SLUGS`, joka estää agentin muokkaamasta kriittisiä sivuja automaattisesti:

```python
PROTECTED_SLUGS = [
    "etusivu",
    "saavutettavuusseloste",
    "tietosuojaseloste",
    "kaytto-ja-tilausehdot",
    "yhteystiedot",
    # lisää omat suojatut sivusi tähän
]
```

### Automaattinen varmuuskopio

Ennen jokaista julkaisua agentti hakee sivun nykyisen sisällön `context=edit`-parametrilla, joka palauttaa Gutenberg-raakasisällön `<!-- wp:html -->`-lohkokommentteineen. Tämä on tärkeää: ilman `context=edit` WordPress palauttaa sanitoidun HTML-version josta inline `<style>`-tagit on poistettu.

### Tyylitarkistus ja automaattinen rollback

Jos sivu käyttää `<!-- wp:html -->`-lohkoa (eli sisältää inline CSS:ää), agentti tarkistaa julkaisun jälkeen että `<style>`-tagit löytyvät renderöidystä sivusta. Jos tagit puuttuvat, agentti:

1. Palauttaa varmuuskopion automaattisesti WordPressiin
2. Ilmoittaa virheestä selkeästi
3. Merkitsee julkaisun epäonnistuneeksi

---

## Hybridimalli

Ennen jokaista optimointia agentti tekee kaksivaiheen analyysin:

**1. SEO-signaalit (paikallinen, ei API-kutsuja)**

| Signaali | Vaatimus |
|---|---|
| Sanamäärä | ≥ 600 sanaa |
| Focus keyword H2:ssa | Otsikosta johdettu avainsana löytyy H2-otsikosta |
| Sisäiset linkit | ≥ 2 linkkiä sivuston muille sivuille |
| Meta description | Ensimmäinen kappale 120–320 merkkiä |

**2. GEO-pisteet (Claude-analyysi, 1–10)**

Strategia valitaan näiden perusteella:

| GEO-pisteet | SEO-puutteita | Strategia |
|---|---|---|
| < 5 | Kyllä | **hybrid** — molemmat optimoidaan |
| < 5 | Ei | **geo** — fokus AI-siteerattavuuteen |
| ≥ 5 | Kyllä | **seo** — hakukonenäkyvyys korjataan |
| ≥ 5 | Ei | *(ohitetaan — sivu on jo kunnossa)* |

SEO-puutteet syötetään Claudelle kontekstina optimointipromptin yhteydessä — Claude korjaa ne osana optimointia ilman erillistä ajovaihetta.

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
- Käytä aina WordPress Application Passwordia — ei tavallista salasanaa
