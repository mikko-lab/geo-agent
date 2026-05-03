# Muutosloki

Kaikki merkittävät muutokset dokumentoidaan tähän tiedostoon.

Formaatti perustuu [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) -käytäntöön,
ja projekti noudattaa [semanttista versiointia](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] — 2026-05-03

### Lisätty
- CLI-versio human-in-the-loop -hyväksynnällä (`run_geo.sh`)
- Streamlit-dashboard visuaaliseen hallintaan (`geo_dashboard.py`)
- WordPress REST API -integraatio sivujen ja postausten hakuun ja päivitykseen
- Claude-pohjainen GEO-pisteytys ja sisältöehdotukset
- Suojatut slugit (`PROTECTED_SLUGS`) kriittisten sivujen suojaamiseen
- Automaattinen varmuuskopio ennen jokaista julkaisua (`context=edit`)
- Tyylitarkistus ja automaattinen rollback jos `<style>`-tagit katoavat
- WordPress Application Password -tuki (ei tavallinen salasana)
- Ympäristömuuttujapohja (`.geo.env.example`)
- WordPress-laskeutumissivu (`geo-agent-landing.html`)
- GitHub Actions CI (ruff lint)

[Unreleased]: https://github.com/mikko-lab/geo-agent/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/mikko-lab/geo-agent/releases/tag/v1.0.0
