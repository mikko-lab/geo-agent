<?php
/**
 * Plugin Name: GEO Agent
 * Description: GEO+SEO-hybridioptimointi WordPress-sisällölle. Analysoi sivun GEO-pisteet ja SEO-signaalit, ehdottaa parannettua sisältöä Claudella ja julkaisee hyväksynnän jälkeen.
 * Version: 1.0.3
 * Author: Mikko Tarkiainen / WP Saavutettavuus
 * Requires at least: 6.0
 * Requires PHP: 8.0
 * Text Domain: geo-agent
 */

defined('ABSPATH') || exit;

define('GEO_AGENT_VERSION', '1.0.3');
define('GEO_AGENT_DIR', plugin_dir_path(__FILE__));
define('GEO_AGENT_URL', plugin_dir_url(__FILE__));

// PHP-versiotarkistus — vaatii 8.0+ (union types, match, str_contains)
if (version_compare(PHP_VERSION, '8.0.0', '<')) {
    add_action('admin_notices', function () {
        echo '<div class="notice notice-error"><p>'
            . '<strong>GEO Agent</strong> vaatii PHP 8.0+. '
            . 'Palvelimellasi on PHP <strong>' . PHP_VERSION . '</strong>. '
            . 'Ota yhteyttä hosting-palveluntarjoajaasi PHP-version päivittämiseksi.'
            . '</p></div>';
    });
    return;
}

require_once GEO_AGENT_DIR . 'includes/class-analyzer.php';
require_once GEO_AGENT_DIR . 'includes/class-optimizer.php';
require_once GEO_AGENT_DIR . 'includes/class-api.php';

// ── REST API ──────────────────────────────────────────────────────────────────

add_action('rest_api_init', function () {
    $api = new GEO_Agent_API();
    $api->register_routes();
});

// ── Gutenberg-sivupaneeli ─────────────────────────────────────────────────────

add_action('enqueue_block_editor_assets', function () {
    $screen = get_current_screen();
    if (!$screen || !in_array($screen->post_type, ['page', 'post'], true)) {
        return;
    }

    wp_enqueue_script(
        'geo-agent-sidebar',
        GEO_AGENT_URL . 'admin/sidebar.js',
        ['wp-plugins', 'wp-edit-post', 'wp-element', 'wp-components', 'wp-data', 'wp-api-fetch', 'wp-i18n'],
        GEO_AGENT_VERSION,
        true
    );

    wp_localize_script('geo-agent-sidebar', 'geoAgentData', [
        'nonce'           => wp_create_nonce('wp_rest'),
        'apiBase'         => rest_url('geo-agent/v1'),
        'defaultStrategy' => get_option('geo_agent_default_strategy', 'auto'),
        'hasApiKey'       => !empty(get_option('geo_agent_api_key')),
    ]);

    wp_enqueue_style(
        'geo-agent-panel',
        GEO_AGENT_URL . 'assets/panel.css',
        [],
        GEO_AGENT_VERSION
    );
});

// ── Asetussivu ────────────────────────────────────────────────────────────────

add_action('admin_menu', function () {
    add_options_page(
        'GEO Agent',
        'GEO Agent',
        'manage_options',
        'geo-agent-settings',
        'geo_agent_settings_page'
    );
});

add_action('admin_init', function () {
    register_setting('geo_agent', 'geo_agent_api_key', [
        'sanitize_callback' => 'sanitize_text_field',
    ]);
    register_setting('geo_agent', 'geo_agent_protected_slugs', [
        'sanitize_callback' => 'sanitize_textarea_field',
    ]);
    register_setting('geo_agent', 'geo_agent_default_strategy', [
        'sanitize_callback' => 'sanitize_text_field',
    ]);
    register_setting('geo_agent', 'geo_agent_max_tokens', [
        'sanitize_callback' => 'absint',
    ]);
});

function geo_agent_settings_page(): void {
    ?>
    <div class="wrap">
        <h1>GEO Agent — Asetukset</h1>
        <form method="post" action="options.php">
            <?php settings_fields('geo_agent'); ?>
            <table class="form-table">
                <tr>
                    <th>Anthropic API Key</th>
                    <td>
                        <input type="password" name="geo_agent_api_key"
                            value="<?php echo esc_attr(get_option('geo_agent_api_key')); ?>"
                            class="regular-text" autocomplete="off" />
                        <p class="description">Tallennetaan salattuna wp_options-tauluun.</p>
                    </td>
                </tr>
                <tr>
                    <th>Suojatut slugit</th>
                    <td>
                        <textarea name="geo_agent_protected_slugs" rows="6" class="large-text"><?php
                            echo esc_textarea(get_option('geo_agent_protected_slugs',
                                "etusivu\nsaavutettavuusseloste\ntietosuojaseloste\nkaytto-ja-tilausehdot\nyhteystiedot\nkirjaudu\nrekisteroidy"
                            ));
                        ?></textarea>
                        <p class="description">Yksi slug per rivi. Agentti ei koskaan muokkaa näitä sivuja.</p>
                    </td>
                </tr>
                <tr>
                    <th>Oletusstrategia</th>
                    <td>
                        <select name="geo_agent_default_strategy">
                            <?php
                            $current = get_option('geo_agent_default_strategy', 'auto');
                            foreach (['auto' => 'Auto (Claude päättää)', 'geo' => 'GEO', 'seo' => 'SEO', 'hybrid' => 'Hybrid'] as $val => $label) {
                                printf(
                                    '<option value="%s"%s>%s</option>',
                                    esc_attr($val),
                                    selected($current, $val, false),
                                    esc_html($label)
                                );
                            }
                            ?>
                        </select>
                    </td>
                </tr>
                <tr>
                    <th>Max tokens</th>
                    <td>
                        <input type="number" name="geo_agent_max_tokens"
                            value="<?php echo esc_attr(get_option('geo_agent_max_tokens', 8000)); ?>"
                            min="500" max="8000" class="small-text" />
                    </td>
                </tr>
            </table>
            <?php submit_button('Tallenna asetukset'); ?>
        </form>
    </div>
    <?php
}
