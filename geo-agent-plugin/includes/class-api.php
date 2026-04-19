<?php
defined('ABSPATH') || exit;

class GEO_Agent_API {

    private GEO_Agent_Analyzer $analyzer;
    private GEO_Agent_Optimizer $optimizer;

    public function __construct() {
        $this->analyzer  = new GEO_Agent_Analyzer();
        $this->optimizer = new GEO_Agent_Optimizer();
    }

    public function register_routes(): void {
        $namespace = 'geo-agent/v1';

        // Analysoi sivu
        register_rest_route($namespace, '/analyze', [
            'methods'             => 'POST',
            'callback'            => [$this, 'handle_analyze'],
            'permission_callback' => [$this, 'check_permission'],
            'args'                => [
                'post_id' => ['required' => true, 'type' => 'integer'],
                'content' => ['required' => true, 'type' => 'string'],
                'title'   => ['required' => true, 'type' => 'string'],
            ],
        ]);

        // Optimoi sisältö
        register_rest_route($namespace, '/optimize', [
            'methods'             => 'POST',
            'callback'            => [$this, 'handle_optimize'],
            'permission_callback' => [$this, 'check_permission'],
            'args'                => [
                'post_id'   => ['required' => true, 'type' => 'integer'],
                'content'   => ['required' => true, 'type' => 'string'],
                'title'     => ['required' => true, 'type' => 'string'],
                'strategy'  => ['required' => true, 'type' => 'string'],
                'seo_fixes' => ['required' => false, 'type' => 'array', 'default' => []],
            ],
        ]);

        // Julkaise optimoitu sisältö
        register_rest_route($namespace, '/publish', [
            'methods'             => 'POST',
            'callback'            => [$this, 'handle_publish'],
            'permission_callback' => [$this, 'check_permission'],
            'args'                => [
                'post_id'           => ['required' => true, 'type' => 'integer'],
                'optimized_content' => ['required' => true, 'type' => 'string'],
            ],
        ]);

        // Rollback
        register_rest_route($namespace, '/rollback', [
            'methods'             => 'POST',
            'callback'            => [$this, 'handle_rollback'],
            'permission_callback' => [$this, 'check_permission'],
            'args'                => [
                'post_id' => ['required' => true, 'type' => 'integer'],
            ],
        ]);

        // Varmuuskopion tila
        register_rest_route($namespace, '/backup-status', [
            'methods'             => 'GET',
            'callback'            => [$this, 'handle_backup_status'],
            'permission_callback' => [$this, 'check_permission'],
            'args'                => [
                'post_id' => ['required' => true, 'type' => 'integer'],
            ],
        ]);
    }

    public function check_permission(\WP_REST_Request $request): bool {
        return current_user_can('edit_posts');
    }

    public function handle_analyze(\WP_REST_Request $request): \WP_REST_Response|\WP_Error {
        $post_id = $request->get_param('post_id');
        $content = $request->get_param('content');
        $title   = $request->get_param('title');

        if (GEO_Agent_Optimizer::is_protected($post_id)) {
            return new \WP_Error('protected', 'Tämä sivu on suojattu — GEO-agentti ei voi muokata sitä.', ['status' => 403]);
        }

        $result = $this->analyzer->analyze($post_id, $content, $title);

        return rest_ensure_response($result);
    }

    public function handle_optimize(\WP_REST_Request $request): \WP_REST_Response|\WP_Error {
        $post_id   = $request->get_param('post_id');
        $content   = $request->get_param('content');
        $title     = $request->get_param('title');
        $strategy  = $request->get_param('strategy');
        $seo_fixes = $request->get_param('seo_fixes') ?? [];

        if (GEO_Agent_Optimizer::is_protected($post_id)) {
            return new \WP_Error('protected', 'Tämä sivu on suojattu.', ['status' => 403]);
        }

        $result = $this->optimizer->optimize($content, $title, $strategy, $seo_fixes);

        if (is_wp_error($result)) {
            return new \WP_Error($result->get_error_code(), $result->get_error_message(), ['status' => 500]);
        }

        return rest_ensure_response(['optimized_content' => $result]);
    }

    public function handle_publish(\WP_REST_Request $request): \WP_REST_Response|\WP_Error {
        $post_id           = $request->get_param('post_id');
        $optimized_content = $request->get_param('optimized_content');

        if (GEO_Agent_Optimizer::is_protected($post_id)) {
            return new \WP_Error('protected', 'Tämä sivu on suojattu.', ['status' => 403]);
        }

        if (!current_user_can('edit_post', $post_id)) {
            return new \WP_Error('forbidden', 'Ei oikeuksia muokata tätä sivua.', ['status' => 403]);
        }

        $result = $this->optimizer->publish($post_id, $optimized_content);

        if (is_wp_error($result)) {
            return new \WP_Error($result->get_error_code(), $result->get_error_message(), ['status' => 500]);
        }

        return rest_ensure_response(['ok' => true, 'message' => 'Sivu julkaistu onnistuneesti.']);
    }

    public function handle_rollback(\WP_REST_Request $request): \WP_REST_Response|\WP_Error {
        $post_id = $request->get_param('post_id');

        if (!current_user_can('edit_post', $post_id)) {
            return new \WP_Error('forbidden', 'Ei oikeuksia.', ['status' => 403]);
        }

        $result = $this->optimizer->rollback($post_id);

        if (is_wp_error($result)) {
            return new \WP_Error($result->get_error_code(), $result->get_error_message(), ['status' => 400]);
        }

        return rest_ensure_response(['ok' => true, 'message' => 'Sivu palautettu varmuuskopiosta.']);
    }

    public function handle_backup_status(\WP_REST_Request $request): \WP_REST_Response {
        $post_id     = $request->get_param('post_id');
        $backup      = get_post_meta($post_id, '_geo_agent_backup_content', true);
        $backup_date = get_post_meta($post_id, '_geo_agent_backup_date', true);

        return rest_ensure_response([
            'has_backup'  => !empty($backup),
            'backup_date' => $backup_date ?: null,
        ]);
    }
}
