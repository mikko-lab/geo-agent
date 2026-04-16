<?php
/**
 * Template Name: GEO Agent Full
 */
// Tyhjennä mahdollinen WordPress-output ennen tiedostoa
if (ob_get_length()) ob_clean();
$file = get_template_directory() . '/geo-agent-landing.html';
if (file_exists($file)) {
    readfile($file);
} else {
    wp_redirect(home_url());
}
exit;
