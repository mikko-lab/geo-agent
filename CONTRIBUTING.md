# Osallistumisohjeet

Kiitos kiinnostuksestasi GEO-agenttia kohtaan!

## Kehitysympäristön pystytys

### Vaatimukset

- Python 3.11+
- WordPress-sivusto REST API:lla
- Anthropic API -avain

### Asennus

```bash
git clone https://github.com/mikko-lab/geo-agent.git
cd geo-agent
pip install -r requirements.txt
cp .geo.env.example ~/.geo.env
chmod 600 ~/.geo.env
# täytä ~/.geo.env omilla arvoillasi
```

### Ajaminen

```bash
# CLI
./run_geo.sh

# Dashboard
source ~/.geo.env
streamlit run geo_dashboard.py
```

## Miten voin osallistua?

### Bugiraportit

Avaa [Issue](https://github.com/mikko-lab/geo-agent/issues) ja kuvaile:

- Mitä teit
- Mitä odotit tapahtuvan
- Mitä oikeasti tapahtui
- Python-versio ja käyttöjärjestelmä

### Ominaisuusehdotukset

Avaa Issue otsikolla `[feat]: ominaisuuden nimi`.

### Pull requestit

1. Forkkaa repositorio
2. Luo uusi haara: `git checkout -b feat/ominaisuuden-nimi`
3. Tee muutoksesi
4. Tarkista lint: `ruff check geo_agent.py geo_dashboard.py`
5. Commitoi selkeällä viestillä (ks. alla)
6. Avaa Pull Request `main`-haaraan

## Commit-viestikäytäntö

| Etuliite | Käyttötapaus |
|----------|-------------|
| `feat:`  | Uusi ominaisuus |
| `fix:`   | Bugikorjaus |
| `ci:`    | CI/CD-muutokset |
| `docs:`  | Dokumentaatiomuutokset |
| `refactor:` | Rakenteellinen muutos ilman toiminnallisia muutoksia |
| `chore:` | Ylläpitotehtävät |

## Tietoturva

- Älä koskaan lisää API-avaimia tai salasanoja koodiin tai committeihin
- `~/.geo.env` pysyy aina paikallisena (`chmod 600`)
- Testaa aina `PROTECTED_SLUGS`-lista ennen laajoja ajoja

## Lisenssi

Osallistumalla hyväksyt, että muutoksesi julkaistaan [MIT-lisenssillä](LICENSE).
