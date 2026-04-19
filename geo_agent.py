"""
GEO-agentti WordPress-sivustoille
Optimoi sisältöä AI-hakukoneita varten (Perplexity, ChatGPT Search, Google AI Overviews)
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
    raw_content: str = field(default="")  # Gutenberg-raakaversio — käytetään backupiin ja julkaisuun


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


class GEOAgent:
    """
    GEO-optimointiagentti — parantaa sisällön näkyvyyttä
    AI-pohjaisissa hakukoneissa (Perplexity, ChatGPT, Google SGE).
    """

    SYSTEM_PROMPT = """Olet GEO-optimointiasiantuntija (Generative Engine Optimization).
Tehtäväsi on muokata verkkosivuston sisältöä niin, että tekoälypohjaiset
hakukoneet (Perplexity, ChatGPT Search, Google AI Overviews) siteeraavat
ja suosittelevat sitä mielellään.

GEO-optimoinnin periaatteet:
1. KYSYMYS-VASTAUS-RAKENNE: Lisää eksplisiittisiä kysymyksiä ja suoria vastauksia.
   AI-hakukoneet poimivat mielellään "Mikä on X? X on..." -rakenteita.
2. FAKTAT JA LUVUT: Lisää konkreettisia tilastoja, prosentteja ja vuosilukuja.
3. AUKTORITEETTI: Mainitse asiantuntijuus ja kokemus selkeästi.
4. MÄÄRITELMÄT: Määrittele keskeiset käsitteet yksinkertaisesti.
5. TIIVISTETYT VÄITTEET: Jokaisen kappaleen ensimmäinen lause = pääväite.
6. RAKENNE: Käytä lyhyitä kappaleita (2–4 lausetta). Lisää väliotsikoita.
7. SCHEMA-YSTÄVÄLLISYYS: Kirjoita kuin täyttäisit FAQ- tai HowTo-skeemaa.

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

    def optimize(self, post: WPPost) -> str:
        """Optimoi postauksen sisällön GEO:a varten."""
        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4000,
            system=self.SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"""Optimoi seuraava WordPress-postaus GEO-periaatteiden mukaan.
Säilytä alkuperäinen asiasisältö ja kieli (suomi/englanti).
Paranna rakennetta, lisää kysymys-vastaus-pareja ja konkreettisia väitteitä.

OTSIKKO: {post.title}

SISÄLTÖ:
{post.content}"""
            }],
        )
        return response.content[0].text


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
    """
    Pyytää käyttäjältä hyväksynnän. Palauttaa:
      'y' = hyväksy ja päivitä
      'n' = hylkää
      'q' = lopeta kaikki
    """
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
    Jokainen muutos näytetään sinulle ennen WordPressiin päivitystä.
    """
    print("🤖 GEO-agentti käynnistyy (human-in-the-loop -tila)\n")

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

        # 0. Tarkista suojattu slug
        slug = extract_slug(post.link) or post.slug
        if slug in PROTECTED_SLUGS:
            print(f"  🔒 Suojattu sivu — ohitetaan.\n")
            results.append({"post": post.title, "score": "–", "action": "suojattu"})
            continue

        # 1. Tarkista onko sisältöä
        if len(post.content.strip()) < 100:
            print("  ⚠️  Sivu sisältää liian vähän tekstiä — ohitetaan.\n")
            results.append({"post": post.title, "score": "–", "action": "ohitettu"})
            continue

        # 2. Analysoi
        print("  🔍 Analysoidaan GEO-pisteet...")
        analysis = agent.analyze(post)
        geo_score = analysis.get("geo_score", "?")
        issues = analysis.get("top_issues", [])
        print(f"  📊 GEO-pisteet: {geo_score}/10")
        if issues:
            for issue in issues:
                print(f"     • {issue}")

        # 3. Ohita jos jo hyvä
        if isinstance(geo_score, (int, float)) and geo_score >= 7:
            print("  ✅ Sisältö on jo hyvin optimoitu, ohitetaan.\n")
            results.append({"post": post.title, "score": geo_score, "action": "ohitettu"})
            continue

        # 4. Optimoi
        print("\n  ✍️  Optimoidaan sisältöä Claude-mallilla...")
        optimized = agent.optimize(post)

        # 5. Analysoi optimoitu sisältö
        print("  🔍 Analysoidaan optimoitu sisältö...")
        optimized_post = WPPost(post.id, post.title, optimized, post.slug, post.link)
        new_analysis = agent.analyze(optimized_post)
        new_score = new_analysis.get("geo_score", "?")
        print(f"  📈 GEO-pisteet optimoinnin jälkeen: {geo_score}/10 → {new_score}/10\n")

        # 6. Näytä diff käyttäjälle
        show_diff(post.content, optimized)

        # 7. Kysy hyväksyntä
        decision = ask_approval(post.title)

        if decision == "y":
            print("  💾 Päivitetään WordPressiin...")
            success = wp.update_post(post, optimized, content_type=CONTENT_TYPE)
            if success:
                print("  ✅ Päivitetty onnistuneesti!\n")
                results.append({"post": post.title, "score": geo_score, "action": "päivitetty"})
            else:
                print("  ❌ Päivitys epäonnistui tai peruttu.\n")
                results.append({"post": post.title, "score": geo_score, "action": "virhe"})

        elif decision == "n":
            print("  ⏭️  Ohitettu.\n")
            results.append({"post": post.title, "score": geo_score, "action": "hylätty"})

        elif decision == "q":
            print("\n  🛑 Lopetetaan käyttäjän pyynnöstä.\n")
            results.append({"post": post.title, "score": geo_score, "action": "keskeytetty"})
            break

    # Yhteenveto
    print("\n═══ YHTEENVETO ═══")
    emojit = {"ohitettu": "⏭️", "päivitetty": "✅", "hylätty": "🚫", "virhe": "❌", "keskeytetty": "🛑", "suojattu": "🔒"}
    for r in results:
        emoji = emojit.get(r["action"], "?")
        print(f"  {emoji} {r['post']} (GEO: {r['score']}/10) → {r['action']}")

    paivitetty = sum(1 for r in results if r["action"] == "päivitetty")
    print(f"\n  Yhteensä päivitetty: {paivitetty}/{len(results)} postausta")
    print("\n🏁 Agentti valmis!")


if __name__ == "__main__":
    run_agent()
