<?php
defined('ABSPATH') || exit;

class GEO_Agent_Optimizer {

    private GEO_Agent_Analyzer $analyzer;

    private const SYSTEM_PROMPT = "Olet sisältöstrategisti, joka hallitsee sekä SEO- että GEO-optimoinnin (Generative Engine Optimization).\n\n"
        . "GEO-optimoinnin periaatteet:\n"
        . "1. KYSYMYS-VASTAUS-RAKENNE: Lisää eksplisiittisiä kysymyksiä ja suoria vastauksia.\n"
        . "2. FAKTAT JA LUVUT: Lisää konkreettisia tilastoja, prosentteja ja vuosilukuja.\n"
        . "3. AUKTORITEETTI: Mainitse asiantuntijuus ja kokemus selkeästi.\n"
        . "4. MÄÄRITELMÄT: Määrittele keskeiset käsitteet yksinkertaisesti.\n"
        . "5. TIIVISTETYT VÄITTEET: Jokaisen kappaleen ensimmäinen lause = pääväite.\n"
        . "6. RAKENNE: Käytä lyhyitä kappaleita (2–4 lausetta). Lisää väliotsikoita.\n"
        . "7. SCHEMA-YSTÄVÄLLISYYS: Kirjoita kuin täyttäisit FAQ- tai HowTo-skeemaa.\n\n"
        . "SEO-periaatteet (jos strategia vaatii):\n"
        . "- Focus keyword esiintyy H1:ssä, ensimmäisessä kappaleessa ja vähintään yhdessä H2:ssa\n"
        . "- Sanamäärä ≥ 600\n"
        . "- Ensimmäinen kappale toimii meta descriptionina (120–320 merkkiä)\n"
        . "- Sisäiset linkit muihin sivuston sivuihin\n\n"
        . "TÄRKEÄÄ — MUOTOILU:\n"
        . "- Käytä HTML-tageja, EI markdownia. Otsikot: <h2>, <h3>. Kappaleet: <p>. Listat: <ul><li>.\n"
        . "- Älä käytä #, ##, **, _ tai muita markdown-merkkejä.\n"
        . "- Sisältö voi sisältää [[BLOCK_N]]-merkkejä (esim. [[BLOCK_0]]). "
        . "Säilytä ne TÄSMÄLLEEN paikoillaan — ne ovat sivun rakenteellisia elementtejä (kuvia, linkkejä jne.).\n"
        . "- Palauta VAIN sisältö ilman selityksiä, kommentteja tai ```-koodilohkoja.";

    public function __construct() {
        $this->analyzer = new GEO_Agent_Analyzer();
    }

    /**
     * Optimoi sisältö strategian mukaan.
     */
    public function optimize(string $content_html, string $title, string $strategy, array $seo_fixes): string|\WP_Error {
        // Korvataan kaikki ei-tekstilohkot [[BLOCK_N]]-merkeillä jotka Claude säilyttää.
        // Tekstilohkot (paragraph, heading, list, quote) lähetetään optimoitaviksi.
        $preserved = [];
        $counter   = 0;

        // Container-lohkot: <!-- wp:X --> ... <!-- /wp:X -->
        $working = preg_replace_callback(
            '/<!-- wp:((?!paragraph\b|heading\b|list\b|list-item\b|quote\b|verse\b)[a-z][a-z0-9-]*(?:\/[a-z][a-z0-9-]*)?)(\s[^>]*)? -->[\s\S]*?<!-- \/wp:\1 -->/',
            function ($m) use (&$preserved, &$counter) {
                $key = "[[BLOCK_{$counter}]]";
                $preserved[$counter] = $m[0];
                $counter++;
                return $key;
            },
            $content_html
        );

        // Self-closing lohkot: <!-- wp:X ... /-->
        $working = preg_replace_callback(
            '/<!-- wp:((?!paragraph\b|heading\b|list\b|list-item\b|quote\b|verse\b)[a-z][a-z0-9-]*(?:\/[a-z][a-z0-9-]*)?)(\s[^>]*)?\s*\/-->/',
            function ($m) use (&$preserved, &$counter) {
                $key = "[[BLOCK_{$counter}]]";
                $preserved[$counter] = $m[0];
                $counter++;
                return $key;
            },
            $working
        );

        // Poistetaan Gutenberg-kommentit tekstilohkoista mutta säilytetään [[BLOCK_N]] merkit
        $text = preg_replace('/<!-- \/?wp:[^>]+ -->/', '', $working);
        $text = wp_strip_all_tags($text);
        // wp_strip_all_tags poistaa tagit mutta jättää [[BLOCK_N]] merkit paikoilleen

        $strategy_instruction = match ($strategy) {
            'geo'    => 'Optimoi GEO-periaatteiden mukaan. Paranna AI-siteerattavuutta kysymys-vastaus-rakenteella ja faktoilla.',
            'seo'    => 'Korjaa SEO-puutteet säilyttäen olemassa oleva GEO-rakenne. Älä heikennä AI-siteerattavuutta.',
            'hybrid' => 'Optimoi sekä GEO- että SEO-näkökulmasta. Korjaa SEO-puutteet ja paranna AI-siteerattavuutta samanaikaisesti.',
            default  => 'Optimoi GEO-periaatteiden mukaan.',
        };

        $seo_context = '';
        if (!empty($seo_fixes)) {
            $seo_context = "\n\nSEO-PUUTTEET JOTKA TULEE KORJATA:\n"
                . implode("\n", array_map(fn($f) => "- {$f}", $seo_fixes));
        }

        $prompt = "Strategia: {$strategy_instruction}{$seo_context}\n\n"
            . "Säilytä alkuperäinen asiasisältö ja kieli (suomi/englanti).\n"
            . "TÄRKEÄÄ: Säilytä kaikki [[BLOCK_N]]-merkit (esim. [[BLOCK_0]]) TÄSMÄLLEEN paikoillaan tekstissä.\n\n"
            . "OTSIKKO: {$title}\n\n"
            . "SISÄLTÖ:\n{$text}";

        $optimized = $this->analyzer->call_claude($prompt, self::SYSTEM_PROMPT, (int) get_option('geo_agent_max_tokens', 8000));
        if (is_wp_error($optimized)) return $optimized;

        // Palautetaan alkuperäiset lohkot merkkien tilalle
        $result = preg_replace_callback(
            '/\[\[BLOCK_(\d+)\]\]/',
            function ($m) use ($preserved) {
                return $preserved[(int) $m[1]] ?? $m[0];
            },
            $optimized
        );

        // Fallback: jos Claude poisti merkit, liitetään säilytetyt lohkot alkuun
        if (!empty($preserved)) {
            $missing = array_filter(
                array_keys($preserved),
                fn($i) => !str_contains($result, $preserved[$i])
            );
            if (!empty($missing)) {
                $fallback = implode("\n\n", array_map(fn($i) => $preserved[$i], $missing));
                $result   = $fallback . "\n\n" . $result;
            }
        }

        return $result;
    }

    /**
     * Tallenna varmuuskopio ennen julkaisua.
     * Käyttää post metaa jotta data säilyy WP:n omassa tietokannassa.
     */
    public function backup(int $post_id): bool {
        $post = get_post($post_id);
        if (!$post) return false;

        // Haetaan raakasisältö REST API:n kautta (context=edit) jotta
        // Gutenberg-lohkokommentit säilyvät — ilman tätä <style>-tagit katoavat
        $request  = new \WP_REST_Request('GET', "/wp/v2/pages/{$post_id}");
        $request->set_param('context', 'edit');
        $response = rest_do_request($request);

        if ($response->is_error()) {
            // Fallback: tallennetaan post_content suoraan
            $raw = $post->post_content;
        } else {
            $raw = $response->get_data()['content']['raw'] ?? $post->post_content;
        }

        update_post_meta($post_id, '_geo_agent_backup_content', $raw);
        update_post_meta($post_id, '_geo_agent_backup_date', current_time('mysql'));
        return true;
    }

    /**
     * Palauta sivu varmuuskopiosta.
     */
    public function rollback(int $post_id): bool|\WP_Error {
        $backup = get_post_meta($post_id, '_geo_agent_backup_content', true);
        if (empty($backup)) {
            return new \WP_Error('no_backup', 'Varmuuskopiota ei löydy tälle sivulle.');
        }

        $result = wp_update_post([
            'ID'           => $post_id,
            'post_content' => $backup,
        ], true);

        if (is_wp_error($result)) return $result;

        delete_post_meta($post_id, '_geo_agent_backup_content');
        delete_post_meta($post_id, '_geo_agent_backup_date');
        return true;
    }

    /**
     * Tarkista että <style>-tagit säilyivät julkaisun jälkeen.
     * Jos wp:html-lohko katoaa, WordPress sanitoi inline CSS:n pois.
     */
    public function verify_styles(int $post_id, string $published_raw): bool {
        $backup = get_post_meta($post_id, '_geo_agent_backup_content', true);
        if (!$backup || !str_contains($backup, '<!-- wp:html -->')) {
            return true; // Alkuperäisessä ei ollut wp:html — ei tarkisteta
        }

        // Tarkistetaan renderöidystä HTML:stä
        $permalink = get_permalink($post_id);
        if (!$permalink) return true;

        $response = wp_remote_get($permalink, ['timeout' => 10]);
        if (is_wp_error($response)) return true; // Verkkovirhe — hyväksytään

        return str_contains(wp_remote_retrieve_body($response), '<style');
    }

    /**
     * Julkaise optimoitu sisältö ja tee turvallisuustarkistukset.
     */
    public function publish(int $post_id, string $optimized_content): bool|\WP_Error {
        // Varmuuskopio ennen kirjoitusta
        $this->backup($post_id);

        $result = wp_update_post([
            'ID'           => $post_id,
            'post_content' => $optimized_content,
        ], true);

        if (is_wp_error($result)) return $result;

        // Style-tarkistus
        if (!$this->verify_styles($post_id, $optimized_content)) {
            // Rollback automaattisesti
            $this->rollback($post_id);
            return new \WP_Error(
                'style_check_failed',
                'Julkaisu peruttu: WordPress poisti &lt;style&gt;-tagit sisällöstä. Sivu palautettu varmuuskopiosta. Tarkista että sisältö on <!-- wp:html --> -lohkossa.'
            );
        }

        return true;
    }

    /**
     * Tarkista onko slug suojattu.
     */
    public static function is_protected(int $post_id): bool {
        $slug = get_post_field('post_name', $post_id);
        $protected_raw = get_option('geo_agent_protected_slugs', '');
        $protected = array_filter(array_map('trim', explode("\n", $protected_raw)));
        return in_array($slug, $protected, true);
    }
}
