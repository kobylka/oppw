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
    'manual_admin_enabled' => false,
    'manual_admin_token' => 'replace-with-a-separate-manual-admin-token',

    'access_token_ttl_seconds' => 900,
    'refresh_token_ttl_days' => 90,
    'pairing_code_ttl_minutes' => 10,
    'default_account_key' => 'REAL',
    'event_limit' => 50,

    // Leave true in production. Enable forwarded proto only behind a trusted proxy
    // that overwrites X-Forwarded-Proto itself.
    'require_https' => true,
    'trust_forwarded_proto' => false,

    // Optional Firebase Cloud Messaging. Keep the service-account JSON outside the web root.
    'push_enabled' => false,
    'firebase_project_id' => '',
    'firebase_service_account_file' => '/etc/oppw-firebase-service-account.json',
];
