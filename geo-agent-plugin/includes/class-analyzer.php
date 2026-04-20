<?php
defined('ABSPATH') || exit;

class GEO_Agent_Analyzer {

    private string $api_key;

    public function __construct() {
        $this->api_key = (string) get_option('geo_agent_api_key', '');
    }

    /**
     * Täydellinen analyysi: SEO-signaalit paikallisesti + GEO Claudella.
     * Palauttaa OptimizationStrategy-rakenteen.
     */
    public function analyze(int $post_id, string $content_html, string $title): array {
        $seo    = $this->check_seo_signals($post_id, $content_html, $title);
        $geo    = $this->analyze_geo($content_html, $title);
        $geo_score = (int) ($geo['geo_score'] ?? 0);

        $strategy = $this->decide_strategy($geo_score, $seo);

        return [
            'strategy'   => $strategy,
            'geo_score'  => $geo_score,
            'geo_issues' => $geo['top_issues'] ?? [],
            'seo'        => $seo,
            'reasoning'  => $this->build_reasoning($strategy, $geo_score, $seo),
        ];
    }

    /**
     * Kevyt SEO-tarkistus ilman ulkoisia API-kutsuja.
     */
    public function check_seo_signals(int $post_id, string $content_html, string $title): array {
        $text = wp_strip_all_tags($content_html);

        // Sanamäärä
        $word_count = str_word_count($text);

        // H2-otsikot
        preg_match_all('/<h2[^>]*>(.*?)<\/h2>/is', $content_html, $h2_matches);
        $h2_texts = array_map(fn($h) => strtolower(wp_strip_all_tags($h)), $h2_matches[1] ?? []);

        // Focus keyword: ensimmäinen merkittävä sana otsikosta
        $title_words = array_filter(
            explode(' ', strtolower($title)),
            fn($w) => mb_strlen($w) > 3
        );
        $focus_keyword     = reset($title_words) ?: '';
        $keyword_in_h2     = $focus_keyword && array_filter($h2_texts, fn($h) => str_contains($h, $focus_keyword));

        // Rank Math focus keyword (jos saatavilla)
        $rm_keyword = get_post_meta($post_id, 'rank_math_focus_keyword', true);
        if ($rm_keyword) {
            $focus_keyword = strtolower(trim(explode(',', $rm_keyword)[0]));
            $keyword_in_h2 = array_filter($h2_texts, fn($h) => str_contains($h, $focus_keyword));
        }

        // Sisäiset linkit
        $site_host = wp_parse_url(home_url(), PHP_URL_HOST);
        preg_match_all('/href=["\']([^"\']+)["\']/i', $content_html, $link_matches);
        $internal_links = array_filter($link_matches[1] ?? [], function ($url) use ($site_host) {
            if (str_starts_with($url, '/') && !str_starts_with($url, '//')) return true;
            $host = wp_parse_url($url, PHP_URL_HOST);
            return $host && str_contains($host, $site_host);
        });
        // Poistetaan wp-content-linkit
        $internal_links = array_filter($internal_links, fn($l) => !str_contains($l, 'wp-content'));
        $internal_link_count = count($internal_links);

        // Meta description — Rank Math ensin, sen jälkeen ensimmäinen kappale
        $rm_desc       = get_post_meta($post_id, 'rank_math_description', true);
        if ($rm_desc) {
            $has_meta_desc = true;
        } else {
            preg_match('/<p[^>]*>(.*?)<\/p>/is', $content_html, $para_match);
            $first_para    = wp_strip_all_tags($para_match[1] ?? '');
            $para_length   = mb_strlen($first_para);
            $has_meta_desc = $para_length >= 120 && $para_length <= 320;
        }

        // Puutteet
        $fixes = [];
        if ($word_count < 600) {
            $fixes[] = "Sanamäärä liian pieni ({$word_count} sanaa, suositus ≥ 600)";
        }
        if (!$keyword_in_h2) {
            $fixes[] = "Focus keyword '{$focus_keyword}' ei löydy H2-otsikoista";
        }
        if ($internal_link_count < 2) {
            $fixes[] = "Sisäisiä linkkejä liian vähän ({$internal_link_count}, suositus ≥ 2)";
        }
        if (!$has_meta_desc) {
            $fixes[] = "Ensimmäinen kappale ei sovellu meta descriptioniksi ({$para_length} merkkiä, suositus 120–320)";
        }

        return [
            'word_count'          => $word_count,
            'h2_count'            => count($h2_texts),
            'focus_keyword'       => $focus_keyword,
            'keyword_in_h2'       => (bool) $keyword_in_h2,
            'internal_link_count' => $internal_link_count,
            'has_meta_desc'       => $has_meta_desc,
            'fixes'               => $fixes,
        ];
    }

    /**
     * GEO-analyysi Claudella.
     */
    private function analyze_geo(string $content_html, string $title): array {
        $text = mb_substr(wp_strip_all_tags($content_html), 0, 2000);

        $prompt = "Analysoi tämä sisältö GEO-näkökulmasta ja anna pisteet 1–10 seuraaville:\n"
            . "- Kysymys-vastaus-rakenne\n"
            . "- Faktojen ja lukujen määrä\n"
            . "- Kappaleiden selkeys\n"
            . "- AI-siteerattavuus (kokonaisarvio)\n\n"
            . "Vastaa VAIN JSON-muodossa:\n"
            . '{"qa_score": X, "facts_score": X, "clarity_score": X, "geo_score": X, "top_issues": ["...", "..."]}'
            . "\n\nSisältö:\nOTSIKKO: {$title}\n{$text}";

        $result = $this->call_claude($prompt, null, 800);
        if (is_wp_error($result)) {
            return ['geo_score' => 0, 'top_issues' => ['Claude-analyysi epäonnistui: ' . $result->get_error_message()]];
        }

        // Poistetaan mahdolliset markdown-koodilohkot (```json ... ```)
        $clean = preg_replace('/```(?:json)?\s*([\s\S]*?)```/', '$1', $result);
        preg_match('/\{[\s\S]*\}/', $clean ?? $result, $m);
        $decoded = json_decode($m[0] ?? '', true);
        return is_array($decoded) ? $decoded : ['geo_score' => 0, 'top_issues' => ['JSON-parsinta epäonnistui']];
    }

    /**
     * Päätä optimointistrategia.
     */
    private function decide_strategy(int $geo_score, array $seo): string {
        $forced = get_option('geo_agent_default_strategy', 'auto');
        if ($forced !== 'auto') return $forced;

        $has_geo_issues = $geo_score < 5;
        $has_seo_issues = !empty($seo['fixes']);

        if ($has_geo_issues && $has_seo_issues) return 'hybrid';
        if ($has_geo_issues)                    return 'geo';
        if ($has_seo_issues)                    return 'seo';
        return 'none';
    }

    private function build_reasoning(string $strategy, int $geo_score, array $seo): string {
        $seo_count = count($seo['fixes'] ?? []);
        return match ($strategy) {
            'hybrid' => "GEO-pisteet matalat ({$geo_score}/10) ja {$seo_count} SEO-puutetta — optimoidaan molemmat.",
            'geo'    => "GEO-pisteet matalat ({$geo_score}/10), SEO kunnossa — fokus AI-siteerattavuuteen.",
            'seo'    => "GEO riittävä ({$geo_score}/10), mutta {$seo_count} SEO-puutetta — korjataan hakukonenäkyvyys.",
            'none'   => "GEO ({$geo_score}/10) ja SEO kunnossa — ei optimointitarvetta.",
            default  => '',
        };
    }

    /**
     * Kutsu Anthropic API:a.
     */
    public function call_claude(string $prompt, ?string $system = null, int $max_tokens = 4000): string|\WP_Error {
        if (empty($this->api_key)) {
            return new \WP_Error('no_api_key', 'Anthropic API key puuttuu. Lisää se GEO Agent -asetuksiin.');
        }

        $body = [
            'model'      => 'claude-sonnet-4-6',
            'max_tokens' => min($max_tokens, (int) get_option('geo_agent_max_tokens', 4000)),
            'messages'   => [['role' => 'user', 'content' => $prompt]],
        ];
        if ($system) {
            $body['system'] = $system;
        }

        $response = wp_remote_post('https://api.anthropic.com/v1/messages', [
            'headers' => [
                'x-api-key'         => $this->api_key,
                'anthropic-version' => '2023-06-01',
                'content-type'      => 'application/json',
            ],
            'body'    => wp_json_encode($body),
            'timeout' => 90,
        ]);

        if (is_wp_error($response)) return $response;

        $code = wp_remote_retrieve_response_code($response);
        $data = json_decode(wp_remote_retrieve_body($response), true);

        if ($code !== 200) {
            $msg = $data['error']['message'] ?? "HTTP {$code}";
            return new \WP_Error('claude_error', $msg);
        }

        return $data['content'][0]['text'] ?? '';
    }
}
