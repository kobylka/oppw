<?php
declare(strict_types=1);

return [
    'dsn' => 'mysql:host=127.0.0.1;dbname=oppw_monitor;charset=utf8mb4',
    'db_user' => 'oppw_monitor',
    'db_password' => 'replace-with-database-password',

    // Used only by the MT5 publisher. Never put this token in the Android app.
    'write_token' => 'replace-with-a-long-random-write-token',

    // Generate three independent 32-byte values. Keep them private.
    'token_hmac_secret' => 'replace-with-random-token-hmac-secret',
    'pairing_hmac_secret' => 'replace-with-random-pairing-hmac-secret',
    'rate_limit_hmac_secret' => 'replace-with-random-rate-limit-hmac-secret',

    // Optional browser-only pairing-code administration. Keep disabled except while pairing.
    'pairing_admin_enabled' => false,
    'pairing_admin_token' => 'replace-with-a-separate-browser-admin-token',

    // Optional browser forms for manually adding weekly US100 O/H/L/C and historical trades.
    // This token is mandatory while enabled and must differ from pairing_admin_token.
    'manual_admin_enabled' => false,
    'manual_admin_token' => 'replace-with-a-separate-manual-admin-token',

    'access_token_ttl_seconds' => 900,
    'refresh_token_ttl_days' => 90,
    'pairing_code_ttl_minutes' => 10,
    'default_account_key' => 'REAL',
    'event_limit' => 50,
    'monitor_heartbeat_stale_seconds' => 180,
    'monitor_price_warning_seconds' => 60,
    'service_supervisor_stale_seconds' => 20,

    // Authenticated analytics responses are reused briefly when their account data watermark is unchanged.
    // Completed Warsaw-week input segments are reused longer; the latest requested week is always queried live.
    // Leave the directory empty to use PHP's system temp directory, or set a protected path outside the web root.
    'analytics_cache_ttl_seconds' => 30,
    'analytics_segment_cache_ttl_seconds' => 86400,
    'analytics_cache_dir' => '',

    // Leave true in production. Enable forwarded values only behind a trusted proxy
    // that overwrites X-Forwarded-Proto and X-Forwarded-Host itself.
    'require_https' => true,
    'trust_forwarded_proto' => false,

    // Optional Firebase Cloud Messaging. Keep the service-account JSON outside the web root.
    'push_enabled' => false,
    'firebase_project_id' => '',
    'firebase_service_account_file' => '/etc/oppw-firebase-service-account.json',

    // Required only for retention --apply. Keep this encrypted location outside the web root.
    'retention_archive_dir' => '',
];
