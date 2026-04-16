"""
GEO-agentti Dashboard
Streamlit-pohjainen käyttöliittymä WordPress-sisällön optimointiin
"""

import os
import re
import json
import requests
import anthropic
import streamlit as st
from dataclasses import dataclass

# ─── SIVU-ASETUKSET ───────────────────────────────────────────────────────────

st.set_page_config(
    page_title="GEO-agentti",
    page_icon="🤖",
    layout="wide",
)

# ─── DATALUOKKA ───────────────────────────────────────────────────────────────

@dataclass
class WPPost:
    id: int
    title: str
    content: str
    slug: str
    link: str


# ─── WORDPRESS-ASIAKAS ────────────────────────────────────────────────────────

class WordPressClient:
    def __init__(self, base_url, user, password):
        if base_url and not base_url.startswith(("http://", "https://")):
            base_url = "https://" + base_url
        self.base = base_url.rstrip("/") + "/wp-json/wp/v2"
        self.auth = (user, password)

    def get_posts(self, count=5, content_type="posts", slug=""):
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

    def fetch_rendered_content(self, url: str) -> str:
        """Hakee renderöidyn sisällön suoraan URL:sta (fallback PHP-sivuille)."""
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return self._strip_html(resp.text)

    def update_post(self, post_id, new_content, content_type="posts"):
        resp = requests.post(
            f"{self.base}/{content_type}/{post_id}",
            json={"content": new_content},
            auth=self.auth,
            timeout=15,
        )
        return resp.status_code == 200, resp.text[:200]

    @staticmethod
    def _strip_html(html):
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL)
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
        return re.sub(r"<[^>]+>", "", html).strip()


# ─── GEO-AGENTTI ──────────────────────────────────────────────────────────────

class GEOAgent:
    SYSTEM_PROMPT = """Olet GEO-optimointiasiantuntija (Generative Engine Optimization).
Tehtäväsi on muokata verkkosivuston sisältöä niin, että tekoälypohjaiset
hakukoneet (Perplexity, ChatGPT Search, Google AI Overviews) siteeraavat
ja suosittelevat sitä mielellään.

GEO-optimoinnin periaatteet:
1. KYSYMYS-VASTAUS-RAKENNE: Lisää eksplisiittisiä kysymyksiä ja suoria vastauksia.
2. FAKTAT JA LUVUT: Lisää konkreettisia tilastoja, prosentteja ja vuosilukuja.
3. AUKTORITEETTI: Mainitse asiantuntijuus ja kokemus selkeästi.
4. MÄÄRITELMÄT: Määrittele keskeiset käsitteet yksinkertaisesti.
5. TIIVISTETYT VÄITTEET: Jokaisen kappaleen ensimmäinen lause = pääväite.
6. RAKENNE: Käytä lyhyitä kappaleita (2–4 lausetta). Lisää väliotsikoita.
7. SCHEMA-YSTÄVÄLLISYYS: Kirjoita kuin täyttäisit FAQ- tai HowTo-skeemaa.

Palauta VAIN optimoitu sisältö ilman selityksiä tai kommentteja."""

    def __init__(self, api_key):
        self.client = anthropic.Anthropic(api_key=api_key)

    def analyze(self, post):
        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"""Analysoi tämä sisältö GEO-näkökulmasta ja anna pisteet 1–10:

Vastaa JSON-muodossa:
{{"qa_score": X, "facts_score": X, "clarity_score": X, "geo_score": X, "top_issues": ["...", "..."]}}

OTSIKKO: {post.title}
{post.content[:2000]}"""}],
        )
        try:
            text = response.content[0].text
            match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass
        return {"geo_score": 0, "qa_score": 0, "facts_score": 0, "clarity_score": 0, "top_issues": ["Analyysi epäonnistui"]}

    def optimize(self, post):
        response = self.client.messages.create(
            model="claude-opus-4-6",
            max_tokens=4000,
            system=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": f"""Optimoi seuraava WordPress-sivu GEO-periaatteiden mukaan.
Säilytä alkuperäinen asiasisältö ja kieli.

OTSIKKO: {post.title}

SISÄLTÖ:
{post.content}"""}],
        )
        return response.content[0].text


# ─── SESSIOTILA ───────────────────────────────────────────────────────────────

if "posts" not in st.session_state:
    st.session_state.posts = []
if "results" not in st.session_state:
    st.session_state.results = {}  # post_id → {analysis, optimized, new_analysis}


# ─── KÄYTTÖLIITTYMÄ ───────────────────────────────────────────────────────────

st.title("🤖 GEO-agentti")
st.caption("Optimoi WordPress-sisältöä AI-hakukoneita varten")

# Sivupalkki — asetukset
with st.sidebar:
    st.header("⚙️ Asetukset")

    api_key = st.text_input(
        "Anthropic API-avain",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        type="password",
    )
    wp_url = st.text_input(
        "WordPress URL",
        value=os.getenv("WP_URL", "https://sinun-sivustosi.fi"),
    )
    wp_user = st.text_input(
        "WP-käyttäjänimi",
        value=os.getenv("WP_USER", ""),
    )
    wp_password = st.text_input(
        "WP Application Password",
        value=os.getenv("WP_PASSWORD", ""),
        type="password",
    )

    st.divider()

    content_type = st.selectbox(
        "Sisältötyyppi",
        ["pages", "posts"],
        format_func=lambda x: "Sivut" if x == "pages" else "Blogipostaukset",
    )
    max_items = st.slider("Haettavien määrä", 1, 20, 5)
    target_slug = st.text_input("Tietty slug (tyhjä = kaikki)", value="")
    geo_threshold = st.slider("Ohita jos pisteet ≥", 1, 10, 7)

    fetch_btn = st.button("📥 Hae sisällöt", use_container_width=True, type="primary")

# Hae sisällöt
if fetch_btn:
    if not all([api_key, wp_url, wp_user, wp_password]):
        st.error("Täytä kaikki asetukset sivupalkissa.")
    else:
        with st.spinner("Haetaan sisältöjä WordPressistä..."):
            try:
                wp = WordPressClient(wp_url, wp_user, wp_password)
                posts = wp.get_posts(count=max_items, content_type=content_type, slug=target_slug)
                st.session_state.posts = posts
                st.session_state.results = {}
                st.success(f"Löydettiin {len(posts)} sisältöä.")
            except Exception as e:
                st.error(f"Virhe: {e}")

# Näytä sisällöt
if st.session_state.posts:
    agent = GEOAgent(api_key) if api_key else None

    for post in st.session_state.posts:
        with st.expander(f"📄 {post.title} — {post.link}", expanded=False):

            if len(post.content.strip()) < 100:
                st.info("REST API palautti vähän sisältöä — haetaan renderöity HTML sivulta...")
                try:
                    wp_tmp = WordPressClient(wp_url, wp_user, wp_password)
                    post.content = wp_tmp.fetch_rendered_content(post.link)
                except Exception as e:
                    st.warning(f"Sisällön haku epäonnistui: {e}")
                    continue
                if len(post.content.strip()) < 100:
                    st.warning("Sivu sisältää liian vähän tekstiä — ei optimoitavaa.")
                    continue

            col1, col2 = st.columns([2, 1])

            with col1:
                st.markdown(f"**URL:** {post.link}")

            with col2:
                analyze_btn = st.button("🔍 Analysoi", key=f"analyze_{post.id}")
                optimize_btn = st.button("✍️ Optimoi", key=f"optimize_{post.id}")

            result = st.session_state.results.get(post.id, {})

            # Analyysi
            if analyze_btn and agent:
                with st.spinner("Analysoidaan..."):
                    analysis = agent.analyze(post)
                    result["analysis"] = analysis
                    st.session_state.results[post.id] = result

            if "analysis" in result:
                a = result["analysis"]
                score = a.get("geo_score", 0)
                color = "green" if score >= 7 else "orange" if score >= 4 else "red"
                st.markdown(f"**GEO-pisteet:** :{color}[{score}/10]")

                cols = st.columns(3)
                cols[0].metric("Kysymys-vastaus", f"{a.get('qa_score', '?')}/10")
                cols[1].metric("Faktat", f"{a.get('facts_score', '?')}/10")
                cols[2].metric("Selkeys", f"{a.get('clarity_score', '?')}/10")

                if a.get("top_issues"):
                    st.markdown("**Parannettavaa:**")
                    for issue in a["top_issues"]:
                        st.markdown(f"- {issue}")

            # Optimointi
            if optimize_btn and agent:
                if score if "analysis" in result else True >= geo_threshold:
                    with st.spinner("Optimoidaan Claude-mallilla..."):
                        optimized = agent.optimize(post)
                        result["optimized"] = optimized
                    with st.spinner("Analysoidaan optimoitu sisältö..."):
                        optimized_post = WPPost(post.id, post.title, optimized, post.slug, post.link)
                        new_analysis = agent.analyze(optimized_post)
                        result["new_analysis"] = new_analysis
                    st.session_state.results[post.id] = result

            if "optimized" in result:
                new_score = result.get("new_analysis", {}).get("geo_score", None)
                old_score = result.get("analysis", {}).get("geo_score", "?")
                if new_score:
                    st.success(f"📈 Pisteet: {old_score}/10 → {new_score}/10")
                else:
                    st.success(f"Optimointi valmis (pisteet ennen: {old_score}/10 — uuden analyysin parsinta epäonnistui)")

                tab1, tab2 = st.tabs(["Optimoitu sisältö", "Alkuperäinen"])
                with tab1:
                    st.text_area("", value=result["optimized"], height=300, key=f"opt_{post.id}")
                with tab2:
                    st.text_area("", value=post.content, height=300, key=f"orig_{post.id}")

                if st.button("💾 Päivitä WordPressiin", key=f"update_{post.id}", type="primary"):
                    wp = WordPressClient(wp_url, wp_user, wp_password)
                    success, msg = wp.update_post(post.id, result["optimized"], content_type)
                    if success:
                        st.success("✅ Päivitetty WordPressiin!")
                    else:
                        st.error(f"❌ Virhe: {msg}")
