"""
GEO-agentti WordPress-sivustoille
Optimoi sisältöä AI-hakukoneita varten (Perplexity, ChatGPT Search, Google AI Overviews)
Hybridimalli: analysoi SEO- ja GEO-signaalit ennen optimointia ja valitsee strategian.
"""

import os
import anthropic
import requests
import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


# ─── ASETUKSET ────────────────────────────────────────────────────────────────

WP_URL      = os.getenv("WP_URL", "")
WP_USER     = os.getenv("WP_USER", "")
WP_PASSWORD = os.getenv("WP_PASSWORD", "")   # WP Application Password
# Luo Application Password: WP Admin → Käyttäjät → Profiili → Application Passwords

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_POSTS    = 5       # Kuinka monta kohdetta käsitellään kerralla
CONTENT_TYPE = "pages" # "posts" = blogipostaukset, "pages" = sivut
TARGET_SLUG  = ""      # Tietty sivu slugin perusteella, esim. "etusivu" tai "" = kaikki

# Suojatut slugit — agentti ei koskaan muokkaa näitä sivuja
PROTECTED_SLUGS = [
    "etusivu",
    "saavutettavuusseloste",
    "tietosuojaseloste",
    "kaytto-ja-tilausehdot",
    "yhteystiedot",
    "kirjaudu",
    "rekisteroidy",
]

# ──────────────────────────────────────────────────────────────────────────────


def extract_slug(url: str) -> str:
    try:
        path = urlparse(url).path
        parts = [p for p in path.strip("/").split("/") if p]
        return parts[-1] if parts else ""
    except Exception:
        return ""


@dataclass
class WPPost:
    id: int
    title: str
    content: str      # tekstisisältö (HTML poistettu) — käytetään analyysiin
    slug: str
    link: str
    raw_content: str = field(default="")   # Gutenberg-raakaversio — backupiin ja julkaisuun
    rendered_html: str = field(default="") # rendered HTML — SEO-signaalien tarkistukseen


@dataclass
class SEOSignals:
    """Kevyt SEO-tarkistus ennen optimointia."""
    word_count: int
    h2_count: int
    focus_keyword_in_h2: bool  # onko sivun otsikosta johdettu avainsana H2:ssa
    internal_link_count: int
    has_meta_description: bool  # arvio: onko yli 120 merkkiä ensimmäisessä kappaleessa
    fixes_needed: list[str]     # lista puuttuvista SEO-elementeistä

    @property
    def needs_seo_work(self) -> bool:
        return len(self.fixes_needed) > 0


@dataclass
class OptimizationStrategy:
    """Optimointistrategia analyysin perusteella."""
    strategy: str        # "seo" | "geo" | "hybrid"
    geo_score: int       # 1–10
    seo_fixes: list[str] # lista SEO-korjauksista
    reasoning: str       # perustelu strategialle


class WordPressClient:
    """Kommunikoi WordPress REST API:n kanssa."""

    def __init__(self, base_url: str, user: str, password: str):
        self.base = base_url.rstrip("/") + "/wp-json/wp/v2"
        self.auth = (user, password)

    def get_posts(self, count: int = 5, content_type: str = "posts", slug: str = "") -> list[WPPost]:
        # context=edit palauttaa content.raw (Gutenberg-lohkokommentteineen)
        params = {"per_page": count, "status": "publish", "context": "edit"}
        if slug:
            params["slug"] = slug
        resp = requests.get(
            f"{self.base}/{content_type}",
            params=params,
            auth=self.auth,
            timeout=15,
        )
        resp.raise_for_status()
        posts = []
        for p in resp.json():
            raw = p["content"].get("raw", "") or p["content"].get("rendered", "")
            rendered = p["content"].get("rendered", "")
            posts.append(WPPost(
                id=p["id"],
                title=p["title"]["rendered"],
                content=self._strip_html(rendered),
                slug=p["slug"],
                link=p["link"],
                raw_content=raw,
                rendered_html=rendered,
            ))
        return posts

    def get_raw_content(self, post_id: int, content_type: str = "pages") -> str | None:
        """Hakee sivun raakasisällön (context=edit) varmuuskopiota varten."""
        resp = requests.get(
            f"{self.base}/{content_type}/{post_id}?context=edit",
            auth=self.auth,
            timeout=15,
        )
        if not resp.ok:
            return None
        data = resp.json()
        return data.get("content", {}).get("raw") or None

    def update_post(
        self,
        post: WPPost,
        new_content: str,
        content_type: str = "pages",
    ) -> bool:
        """
        Julkaisee optimoidun sisällön WordPressiin.

        Turvallisuustarkistukset:
        1. Suojatut slugit estetään
        2. Varmuuskopio otetaan ennen kirjoitusta (context=edit → raw)
        3. Julkaisun jälkeen tarkistetaan että <style>-tagit säilyivät;
           jos eivät, rollback tehdään automaattisesti
        """
        slug = extract_slug(post.link) or post.slug
        if slug in PROTECTED_SLUGS:
            print(f"  🔒 Sivu '{slug}' on suojattu — ohitetaan automaattisesti.")
            return False

        # Varmuuskopio raakana Gutenberg-sisältönä ennen ylikirjoitusta.
        # TÄRKEÄÄ: context=edit on pakollinen — ilman sitä WP palauttaa vain
        # sanitoidun rendered-HTML:n josta <style>-tagit on poistettu.
        backup = self.get_raw_content(post.id, content_type)
        backup_has_style_block = backup is not None and "<!-- wp:html -->" in backup

        resp = requests.post(
            f"{self.base}/{content_type}/{post.id}",
            json={"content": new_content},
            auth=self.auth,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  ⚠️  WP-virhe {resp.status_code}: {resp.text[:200]}")
            return False

        # Style-tarkistus: jos alkuperäisessä oli <!-- wp:html --> (inline CSS),
        # varmistetaan että <style löytyy julkaistulta sivulta.
        if backup_has_style_block and backup:
            try:
                check = requests.get(post.link, timeout=10)
                if "<style" not in check.text:
                    print("  ⚠️  Tyylitarkistus epäonnistui — WordPress poisti <style>-tagit.")
                    print("  🔄 Palautetaan varmuuskopio automaattisesti...")
                    rollback = requests.post(
                        f"{self.base}/{content_type}/{post.id}",
                        json={"content": backup},
                        auth=self.auth,
                        timeout=15,
                    )
                    if rollback.status_code == 200:
                        print("  ✅ Varmuuskopio palautettu. Tarkista että sisältö on <!-- wp:html --> -lohkossa.")
                    else:
                        print("  ❌ Rollback epäonnistui! Tarkista sivu manuaalisesti.")
                    return False
            except Exception as e:
                print(f"  ⚠️  Tyylitarkistus ohitettu (verkkovirhe: {e})")

        return True

    @staticmethod
    def _strip_html(html: str) -> str:
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", "", html).strip()
        return text


def check_seo_signals(post: WPPost) -> SEOSignals:
    """
    Kevyt SEO-tarkistus rendered HTML:stä ja tekstisisällöstä.
    Ei vaadi ulkoisia API-kutsuja — perustuu paikalliseen analyysiin.
    """
    html = post.rendered_html
    text = post.content
    title = post.title.lower()

    # Sanamäärä
    words = text.split()
    word_count = len(words)

    # H2-otsikot rendered HTML:stä
    h2_tags = re.findall(r"<h2[^>]*>(.*?)</h2>", html, re.DOTALL | re.IGNORECASE)
    h2_texts = [re.sub(r"<[^>]+>", "", h).lower().strip() for h in h2_tags]
    h2_count = len(h2_texts)

    # Focus keyword: johdetaan sivun otsikosta (ensimmäinen merkittävä sana/pari)
    title_words = [w for w in title.split() if len(w) > 3]
    focus_keyword = title_words[0] if title_words else ""
    focus_keyword_in_h2 = any(focus_keyword in h2 for h2 in h2_texts) if focus_keyword else False

    # Sisäiset linkit (linkit samaan domainiin tai relatiiviset)
    wp_domain = urlparse(post.link).netloc
    all_links = re.findall(r'href=["\']([^"\']+)["\']', html)
    internal_links = [
        l for l in all_links
        if l.startswith("/") or wp_domain in l
    ]
    # Poistetaan ankkurilinkit ja tiedostolinkit
    internal_links = [l for l in internal_links if not l.startswith("/#") and "wp-content" not in l]
    internal_link_count = len(internal_links)

    # Meta description -arvio: onko ensimmäinen kappale 120–160 merkkiä
    first_para_match = re.search(r"<p[^>]*>(.*?)</p>", html, re.DOTALL | re.IGNORECASE)
    first_para = re.sub(r"<[^>]+>", "", first_para_match.group(1)).strip() if first_para_match else ""
    has_meta_description = 120 <= len(first_para) <= 320

    # Puutteet
    fixes: list[str] = []
    if word_count < 600:
        fixes.append(f"Sanamäärä liian pieni ({word_count} sanaa, suositus ≥ 600)")
    if not focus_keyword_in_h2:
        fixes.append(f"Focus keyword '{focus_keyword}' ei löydy H2-otsikoista")
    if internal_link_count < 2:
        fixes.append(f"Sisäisiä linkkejä liian vähän ({internal_link_count}, suositus ≥ 2)")
    if not has_meta_description:
        fixes.append("Ensimmäinen kappale ei sovellu meta descriptioniksi (120–320 merkkiä)")

    return SEOSignals(
        word_count=word_count,
        h2_count=h2_count,
        focus_keyword_in_h2=focus_keyword_in_h2,
        internal_link_count=internal_link_count,
        has_meta_description=has_meta_description,
        fixes_needed=fixes,
    )


class GEOAgent:
    """
    GEO-optimointiagentti hybridimallilla.

    Ennen optimointia:
    1. Tarkistaa SEO-signaalit paikallisesti (sanamäärä, H2, sisäiset linkit)
    2. Analysoi GEO-pisteet Claude-mallilla
    3. Päättää strategian: seo | geo | hybrid
    4. Syöttää SEO-puutteet kontekstina optimointiprompttiin
    """

    SYSTEM_PROMPT = """Olet sisältöstrategisti, joka hallitsee sekä SEO- että GEO-optimoinnin
(Generative Engine Optimization).

GEO-optimoinnin periaatteet:
1. KYSYMYS-VASTAUS-RAKENNE: Lisää eksplisiittisiä kysymyksiä ja suoria vastauksia.
2. FAKTAT JA LUVUT: Lisää konkreettisia tilastoja, prosentteja ja vuosilukuja.
3. AUKTORITEETTI: Mainitse asiantuntijuus ja kokemus selkeästi.
4. MÄÄRITELMÄT: Määrittele keskeiset käsitteet yksinkertaisesti.
5. TIIVISTETYT VÄITTEET: Jokaisen kappaleen ensimmäinen lause = pääväite.
6. RAKENNE: Käytä lyhyitä kappaleita (2–4 lausetta). Lisää väliotsikoita.
7. SCHEMA-YSTÄVÄLLISYYS: Kirjoita kuin täyttäisit FAQ- tai HowTo-skeemaa.

SEO-periaatteet (jos strategia vaatii):
- Focus keyword esiintyy H1:ssä, ensimmäisessä kappaleessa ja vähintään yhdessä H2:ssa
- Sanamäärä ≥ 600
- Ensimmäinen kappale toimii meta descriptionina (120–320 merkkiä)
- Sisäiset linkit muihin sivuston sivuihin

Palauta VAIN optimoitu sisältö ilman selityksiä tai kommentteja."""

    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(self, post: WPPost) -> dict:
        """Analysoi postauksen GEO-pisteet ennen optimointia."""
        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            messages=[{
                "role": "user",
                "content": f"""Analysoi tämä sisältö GEO-näkökulmasta ja anna pisteet 1–10 seuraaville:
- Kysymys-vastaus-rakenne
- Faktojen ja lukujen määrä
- Kappaleiden selkeys
- AI-siteerattavuus (kokonaisarvio)

Vastaa JSON-muodossa:
{{"qa_score": X, "facts_score": X, "clarity_score": X, "geo_score": X, "top_issues": ["...", "..."]}}

Sisältö:
OTSIKKO: {post.title}
{post.content[:2000]}"""
            }],
        )
        try:
            text = response.content[0].text
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
            return json.loads(text)
        except Exception:
            return {"geo_score": 0, "top_issues": ["Analyysi epäonnistui"]}

    def decide_strategy(self, geo_score: int, seo: SEOSignals) -> OptimizationStrategy:
        """
        Päättää optimointistrategian GEO-pisteiden ja SEO-signaalien perusteella.

        Logiikka:
        - geo_score < 5 JA SEO-puutteita → hybrid (molemmat tarvitsevat työtä)
        - geo_score < 5 JA ei SEO-puutteita → geo
        - geo_score ≥ 5 JA SEO-puutteita → seo
        - geo_score ≥ 5 JA ei SEO-puutteita → ohitetaan (jo kunnossa)
        """
        has_geo_issues = geo_score < 5
        has_seo_issues = seo.needs_seo_work

        if has_geo_issues and has_seo_issues:
            strategy = "hybrid"
            reasoning = f"GEO-pisteet matalat ({geo_score}/10) ja {len(seo.fixes_needed)} SEO-puutetta — optimoidaan molemmat."
        elif has_geo_issues:
            strategy = "geo"
            reasoning = f"GEO-pisteet matalat ({geo_score}/10), SEO kunnossa — keskitytään AI-siteerattavuuteen."
        elif has_seo_issues:
            strategy = "seo"
            reasoning = f"GEO riittävä ({geo_score}/10), mutta {len(seo.fixes_needed)} SEO-puutetta — korjataan hakukonenäkyvyys."
        else:
            strategy = "none"
            reasoning = f"GEO ({geo_score}/10) ja SEO kunnossa — ei optimointitarvetta."

        return OptimizationStrategy(
            strategy=strategy,
            geo_score=geo_score,
            seo_fixes=seo.fixes_needed,
            reasoning=reasoning,
        )

    def optimize(self, post: WPPost, strategy: OptimizationStrategy) -> str:
        """Optimoi postauksen sisällön valitun strategian mukaan."""
        seo_context = ""
        if strategy.seo_fixes:
            seo_context = "\n\nSEO-PUUTTEET JOTKA TULEE KORJATA:\n" + "\n".join(
                f"- {fix}" for fix in strategy.seo_fixes
            )

        strategy_instruction = {
            "geo": "Optimoi GEO-periaatteiden mukaan. Paranna AI-siteerattavuutta kysymys-vastaus-rakenteella ja faktoilla.",
            "seo": "Korjaa SEO-puutteet säilyttäen olemassa oleva GEO-rakenne. Älä heikennä AI-siteerattavuutta.",
            "hybrid": "Optimoi sekä GEO- että SEO-näkökulmasta. Korjaa SEO-puutteet ja paranna AI-siteerattavuutta samanaikaisesti.",
        }.get(strategy.strategy, "Optimoi GEO-periaatteiden mukaan.")

        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4000,
            system=self.SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Strategia: {strategy_instruction}{seo_context}

Säilytä alkuperäinen asiasisältö ja kieli (suomi/englanti).

OTSIKKO: {post.title}

SISÄLTÖ:
{post.content}"""
            }],
        )
        return response.content[0].text


def show_strategy(strategy: OptimizationStrategy, seo: SEOSignals):
    """Tulostaa strategia-analyysin käyttäjälle."""
    icons = {"geo": "🌐", "seo": "🔍", "hybrid": "⚡", "none": "✅"}
    icon = icons.get(strategy.strategy, "?")
    print(f"\n  {icon} Strategia: {strategy.strategy.upper()}")
    print(f"     {strategy.reasoning}")
    print(f"\n  📊 SEO-signaalit:")
    print(f"     Sanamäärä: {seo.word_count} {'✅' if seo.word_count >= 600 else '❌'}")
    print(f"     H2-otsikot: {seo.h2_count} kpl, focus keyword H2:ssa: {'✅' if seo.focus_keyword_in_h2 else '❌'}")
    print(f"     Sisäiset linkit: {seo.internal_link_count} {'✅' if seo.internal_link_count >= 2 else '❌'}")
    print(f"     Meta description -arvio: {'✅' if seo.has_meta_description else '❌'}")
    if strategy.seo_fixes:
        print(f"\n  🔧 SEO-korjaukset:")
        for fix in strategy.seo_fixes:
            print(f"     • {fix}")


def show_diff(original: str, optimized: str, preview_lines: int = 20):
    """Näyttää alkuperäisen ja optimoidun sisällön rinnakkain."""
    orig_lines = original.splitlines()
    opti_lines = optimized.splitlines()

    print("\n    ┌─ ALKUPERÄINEN " + "─" * 50)
    for line in orig_lines[:preview_lines]:
        print(f"    │ {line}")
    if len(orig_lines) > preview_lines:
        print(f"    │ ... ({len(orig_lines) - preview_lines} riviä lisää)")

    print("\n    ┌─ OPTIMOITU " + "─" * 53)
    for line in opti_lines[:preview_lines]:
        print(f"    │ {line}")
    if len(opti_lines) > preview_lines:
        print(f"    │ ... ({len(opti_lines) - preview_lines} riviä lisää)")
    print()


def ask_approval(post_title: str) -> str:
    while True:
        answer = input(
            f"    ❓ Päivitetäänkö \"{post_title}\" WordPressiin?\n"
            "       [y] Kyllä, päivitä  [n] Ei, ohita  [q] Lopeta kaikki: "
        ).strip().lower()
        if answer in ("y", "n", "q"):
            return answer
        print("    Kirjoita y, n tai q.")


def run_agent():
    """
    Käynnistää GEO-agentin human-in-the-loop -tilassa.
    Hybridimalli analysoi SEO- ja GEO-signaalit ennen jokaista optimointia.
    """
    print("🤖 GEO-agentti käynnistyy (hybridimalli, human-in-the-loop)\n")

    wp = WordPressClient(WP_URL, WP_USER, WP_PASSWORD)
    agent = GEOAgent(ANTHROPIC_API_KEY)

    print(f"📥 Haetaan {MAX_POSTS} postausta WordPressistä...")
    posts = wp.get_posts(count=MAX_POSTS, content_type=CONTENT_TYPE, slug=TARGET_SLUG)
    print(f"✅ Löydettiin {len(posts)} postausta.\n")

    results = []

    for i, post in enumerate(posts, 1):
        print(f"══════════════════════════════════════════════════════")
        print(f"  Postaus {i}/{len(posts)}: {post.title}")
        print(f"  URL: {post.link}")
        print(f"══════════════════════════════════════════════════════")

        # 0. Suojattu slug
        slug = extract_slug(post.link) or post.slug
        if slug in PROTECTED_SLUGS:
            print(f"  🔒 Suojattu sivu — ohitetaan.\n")
            results.append({"post": post.title, "strategy": "–", "action": "suojattu"})
            continue

        # 1. Tarkista minimisisältö
        if len(post.content.strip()) < 100:
            print("  ⚠️  Sivu sisältää liian vähän tekstiä — ohitetaan.\n")
            results.append({"post": post.title, "strategy": "–", "action": "ohitettu"})
            continue

        # 2. SEO-signaalit (paikallinen, ei API-kutsuja)
        print("  🔍 Tarkistetaan SEO-signaalit...")
        seo = check_seo_signals(post)

        # 3. GEO-analyysi
        print("  🌐 Analysoidaan GEO-pisteet...")
        analysis = agent.analyze(post)
        geo_score = analysis.get("geo_score", 0)
        geo_issues = analysis.get("top_issues", [])
        print(f"  📊 GEO-pisteet: {geo_score}/10")
        if geo_issues:
            for issue in geo_issues:
                print(f"     • {issue}")

        # 4. Päätä strategia
        strategy = agent.decide_strategy(geo_score, seo)
        show_strategy(strategy, seo)

        if strategy.strategy == "none":
            print("  ✅ Sivu on kunnossa — ei optimointitarvetta.\n")
            results.append({"post": post.title, "strategy": "none", "action": "ohitettu"})
            continue

        # 5. Optimoi valitulla strategialla
        print(f"\n  ✍️  Optimoidaan ({strategy.strategy.upper()}) Claude-mallilla...")
        optimized = agent.optimize(post, strategy)

        # 6. GEO-pisteet optimoinnin jälkeen
        print("  🔍 Analysoidaan optimoitu sisältö...")
        opt_post = WPPost(post.id, post.title, optimized, post.slug, post.link)
        new_analysis = agent.analyze(opt_post)
        new_score = new_analysis.get("geo_score", "?")
        print(f"  📈 GEO: {geo_score}/10 → {new_score}/10\n")

        # 7. Näytä diff
        show_diff(post.content, optimized)

        # 8. Hyväksyntä
        decision = ask_approval(post.title)

        if decision == "y":
            print("  💾 Päivitetään WordPressiin...")
            success = wp.update_post(post, optimized, content_type=CONTENT_TYPE)
            if success:
                print("  ✅ Päivitetty onnistuneesti!\n")
                results.append({"post": post.title, "strategy": strategy.strategy, "action": "päivitetty"})
            else:
                print("  ❌ Päivitys epäonnistui tai peruttu.\n")
                results.append({"post": post.title, "strategy": strategy.strategy, "action": "virhe"})
        elif decision == "n":
            print("  ⏭️  Ohitettu.\n")
            results.append({"post": post.title, "strategy": strategy.strategy, "action": "hylätty"})
        elif decision == "q":
            print("\n  🛑 Lopetetaan käyttäjän pyynnöstä.\n")
            results.append({"post": post.title, "strategy": strategy.strategy, "action": "keskeytetty"})
            break

    # Yhteenveto
    print("\n═══ YHTEENVETO ═══")
    emojit = {"ohitettu": "⏭️", "päivitetty": "✅", "hylätty": "🚫", "virhe": "❌", "keskeytetty": "🛑", "suojattu": "🔒"}
    for r in results:
        emoji = emojit.get(r["action"], "?")
        print(f"  {emoji} {r['post']} [{r['strategy']}] → {r['action']}")

    paivitetty = sum(1 for r in results if r["action"] == "päivitetty")
    print(f"\n  Yhteensä päivitetty: {paivitetty}/{len(results)} postausta")
    print("\n🏁 Agentti valmis!")


if __name__ == "__main__":
    run_agent()
