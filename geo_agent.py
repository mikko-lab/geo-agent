"""
GEO-agentti WordPress-sivustoille
Optimoi sisältöä AI-hakukoneita varten (Perplexity, ChatGPT Search, Google AI Overviews)
"""

import os
import anthropic
import requests
import json
import re
from dataclasses import dataclass


# ─── ASETUKSET ────────────────────────────────────────────────────────────────

WP_URL      = os.getenv("WP_URL", "https://wpsaavutettavuus.fi.fi")
WP_USER     = os.getenv("WP_USER", "mikkotark")
WP_PASSWORD = os.getenv("WP_PASSWORD", "")   # WP Application Password
# Luo Application Password: WP Admin → Käyttäjät → Profiili → Application Passwords

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MAX_POSTS   = 5                              # Kuinka monta kohdetta käsitellään kerralla
CONTENT_TYPE = "pages"                       # "posts" = blogipostaukset, "pages" = sivut
TARGET_SLUG  = ""                            # Tietty sivu slugin perusteella, esim. "etusivu" tai "" = kaikki

# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class WPPost:
    id: int
    title: str
    content: str
    slug: str
    link: str


class WordPressClient:
    """Kommunikoi WordPress REST API:n kanssa."""

    def __init__(self, base_url: str, user: str, password: str):
        self.base = base_url.rstrip("/") + "/wp-json/wp/v2"
        self.auth = (user, password)

    def get_posts(self, count: int = 5, content_type: str = "posts", slug: str = "") -> list[WPPost]:
        params = {"per_page": count, "status": "publish"}
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
            posts.append(WPPost(
                id=p["id"],
                title=p["title"]["rendered"],
                content=self._strip_html(p["content"]["rendered"]),
                slug=p["slug"],
                link=p["link"],
            ))
        return posts

    def update_post(self, post_id: int, new_content: str, new_title: str = None, content_type: str = "posts") -> bool:
        payload: dict = {"content": new_content}
        if new_title:
            payload["title"] = new_title
        resp = requests.post(
            f"{self.base}/{content_type}/{post_id}",
            json=payload,
            auth=self.auth,
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"  ⚠️  WP-virhe {resp.status_code}: {resp.text[:200]}")
        return resp.status_code == 200

    @staticmethod
    def _strip_html(html: str) -> str:
        # Poistetaan style- ja script-lohkot kokonaan
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        # Poistetaan loput HTML-tagit
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
            # Etsitään JSON-objekti tekstistä
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

        # 0. Tarkista onko sisältöä
        if len(post.content.strip()) < 100:
            print("  ⚠️  Sivu sisältää liian vähän tekstiä — ohitetaan.\n")
            results.append({"post": post.title, "score": "–", "action": "ohitettu"})
            continue

        # 1. Analysoi
        print("  🔍 Analysoidaan GEO-pisteet...")
        analysis = agent.analyze(post)
        geo_score = analysis.get("geo_score", "?")
        issues = analysis.get("top_issues", [])
        print(f"  📊 GEO-pisteet: {geo_score}/10")
        if issues:
            for issue in issues:
                print(f"     • {issue}")

        # 2. Ohita jos jo hyvä
        if isinstance(geo_score, (int, float)) and geo_score >= 7:
            print("  ✅ Sisältö on jo hyvin optimoitu, ohitetaan.\n")
            results.append({"post": post.title, "score": geo_score, "action": "ohitettu"})
            continue

        # 3. Optimoi
        print("\n  ✍️  Optimoidaan sisältöä Claude-mallilla...")
        optimized = agent.optimize(post)

        # 4. Analysoi optimoitu sisältö
        print("  🔍 Analysoidaan optimoitu sisältö...")
        optimized_post = WPPost(post.id, post.title, optimized, post.slug, post.link)
        new_analysis = agent.analyze(optimized_post)
        new_score = new_analysis.get("geo_score", "?")
        print(f"  📈 GEO-pisteet optimoinnin jälkeen: {geo_score}/10 → {new_score}/10\n")

        # 5. Näytä diff käyttäjälle
        show_diff(post.content, optimized)

        # 5. Kysy hyväksyntä
        decision = ask_approval(post.title)

        if decision == "y":
            print("  💾 Päivitetään WordPressiin...")
            success = wp.update_post(post.id, optimized, content_type=CONTENT_TYPE)
            if success:
                print("  ✅ Päivitetty onnistuneesti!\n")
                results.append({"post": post.title, "score": geo_score, "action": "päivitetty"})
            else:
                print("  ❌ Päivitys epäonnistui.\n")
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
    emojit = {"ohitettu": "⏭️", "päivitetty": "✅", "hylätty": "🚫", "virhe": "❌", "keskeytetty": "🛑"}
    for r in results:
        emoji = emojit.get(r["action"], "?")
        print(f"  {emoji} {r['post']} (GEO: {r['score']}/10) → {r['action']}")

    paivitetty = sum(1 for r in results if r["action"] == "päivitetty")
    print(f"\n  Yhteensä päivitetty: {paivitetty}/{len(results)} postausta")
    print("\n🏁 Agentti valmis!")


if __name__ == "__main__":
    run_agent()
