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

    'access_token_ttl_seconds' => 900,
    'refresh_token_ttl_days' => 90,
    'pairing_code_ttl_minutes' => 10,
    'default_account_key' => 'REAL',
    'event_limit' => 50,

    // Leave true in production. Enable forwarded proto only behind a trusted proxy
    // that overwrites X-Forwarded-Proto itself.
    'require_https' => true,
    'trust_forwarded_proto' => false,
];
