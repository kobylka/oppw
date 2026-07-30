<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    @ini_set('display_errors', '0');
    @ini_set('log_errors', '1');
}

function config(): array
{
    static $config;
    if ($config !== null) return $config;
    $path = (string)(getenv('OPPW_MONITOR_CONFIG') ?: (__DIR__ . '/config.php'));
    if (!is_file($path)) json_response(['ok' => false, 'error' => 'Server configuration missing'], 500);
    $config = require $path;
    foreach (['dsn', 'db_user', 'db_password', 'write_token', 'token_hmac_secret', 'pairing_hmac_secret', 'rate_limit_hmac_secret'] as $key) {
        $value = trim((string)($config[$key] ?? ''));
        if ($value === '' || str_contains($value, 'replace-with-')) {
            if (PHP_SAPI === 'cli') throw new RuntimeException("Server configuration value is missing: $key");
            json_response(['ok' => false, 'error' => 'Server configuration is incomplete'], 500);
        }
    }
    return $config;
}

function pdo(): PDO
{
    static $pdo;
    if ($pdo instanceof PDO) return $pdo;
    $cfg = config();
    $pdo = new PDO($cfg['dsn'], $cfg['db_user'], $cfg['db_password'], [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
        PDO::ATTR_EMULATE_PREPARES => false,
    ]);
    return $pdo;
}

function json_response(array $payload, int $status = 200): never
{
    json_encoded_response(
        json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR),
        $status
    );
}

function json_encoded_response(string $payload, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    header('Pragma: no-cache');
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    echo $payload;
    exit;
}

function require_method(string $method): void
{
    if (PHP_SAPI === 'cli') return;
    if (strcasecmp($_SERVER['REQUEST_METHOD'] ?? '', $method) !== 0) {
        header('Allow: ' . strtoupper($method));
        json_response(['ok' => false, 'error' => 'Method not allowed'], 405);
    }
}

function is_https_request(): bool
{
    if (PHP_SAPI === 'cli') return true;
    if (!empty($_SERVER['HTTPS']) && strtolower((string)$_SERVER['HTTPS']) !== 'off') return true;
    if ((int)($_SERVER['SERVER_PORT'] ?? 0) === 443) return true;
    $cfg = config();
    if (!empty($cfg['trust_forwarded_proto'])) {
        return strtolower(trim(explode(',', (string)($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? ''))[0])) === 'https';
    }
    return false;
}

function require_https(): void
{
    if (!((bool)(config()['require_https'] ?? true))) return;
    if (!is_https_request()) json_response(['ok' => false, 'error' => 'HTTPS required'], 426);
}

function request_json(int $maxBytes = 65536): array
{
    $length = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($length > $maxBytes) json_response(['ok' => false, 'error' => 'Request body too large'], 413);
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') json_response(['ok' => false, 'error' => 'Empty JSON body'], 400);
    if (strlen($raw) > $maxBytes) json_response(['ok' => false, 'error' => 'Request body too large'], 413);
    try {
        $data = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException $e) {
        json_response(['ok' => false, 'error' => 'Invalid JSON: ' . $e->getMessage()], 400);
    }
    if (!is_array($data)) json_response(['ok' => false, 'error' => 'JSON object required'], 400);
    return $data;
}

function bearer_token(): string
{
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? $_SERVER['REDIRECT_HTTP_AUTHORIZATION'] ?? '';
    if (!preg_match('/^Bearer\s+(.+)$/i', trim((string)$header), $matches)) return '';
    return trim($matches[1]);
}

function base64url_encode(string $bytes): string
{
    return rtrim(strtr(base64_encode($bytes), '+/', '-_'), '=');
}

function random_token(int $bytes = 32): string
{
    return base64url_encode(random_bytes($bytes));
}

function token_hash(string $token): string
{
    return hash_hmac('sha256', $token, (string)config()['token_hmac_secret']);
}

function normalize_pairing_code(string $code): string
{
    return strtoupper((string)preg_replace('/[^A-Z0-9]/', '', $code));
}

function pairing_code_hash(string $code): string
{
    return hash_hmac('sha256', normalize_pairing_code($code), (string)config()['pairing_hmac_secret']);
}

function utc_now(): DateTimeImmutable
{
    return new DateTimeImmutable('now', new DateTimeZone('UTC'));
}

function mysql_datetime(DateTimeImmutable $value): string
{
    return $value->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.v');
}

function atom_datetime(DateTimeImmutable $value): string
{
    return $value->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d\\TH:i:s.vP');
}

function normalize_datetime(?string $value): string
{
    try {
        $dt = $value ? new DateTimeImmutable($value) : utc_now();
    } catch (Throwable) {
        $dt = utc_now();
    }
    return mysql_datetime($dt);
}

function client_ip(): string
{
    return substr((string)($_SERVER['REMOTE_ADDR'] ?? 'unknown'), 0, 64);
}

function enforce_rate_limit(string $bucket, int $limit, int $windowSeconds): void
{
    if (PHP_SAPI === 'cli') return;
    $db = pdo();
    $key = hash_hmac('sha256', $bucket . '|' . client_ip(), (string)config()['rate_limit_hmac_secret']);
    $now = utc_now();
    $windowStart = $now->setTimestamp(intdiv($now->getTimestamp(), $windowSeconds) * $windowSeconds);

    $db->beginTransaction();
    try {
        $stmt = $db->prepare('SELECT window_start, attempts FROM auth_rate_limits WHERE rate_key = ? FOR UPDATE');
        $stmt->execute([$key]);
        $row = $stmt->fetch();
        if (!$row || (string)$row['window_start'] !== mysql_datetime($windowStart)) {
            $upsert = $db->prepare('INSERT INTO auth_rate_limits(rate_key, window_start, attempts) VALUES (?, ?, 1) ON DUPLICATE KEY UPDATE window_start = VALUES(window_start), attempts = 1');
            $upsert->execute([$key, mysql_datetime($windowStart)]);
            $attempts = 1;
        } else {
            $attempts = (int)$row['attempts'] + 1;
            $update = $db->prepare('UPDATE auth_rate_limits SET attempts = ? WHERE rate_key = ?');
            $update->execute([$attempts, $key]);
        }
        $db->commit();
    } catch (Throwable $e) {
        if ($db->inTransaction()) $db->rollBack();
        throw $e;
    }

    if ($attempts > $limit) {
        header('Retry-After: ' . $windowSeconds);
        json_response(['ok' => false, 'error' => 'Too many requests'], 429);
    }
}

function enforce_single_flight(PDO $db, string $bucket, string $subject): void
{
    if (PHP_SAPI === 'cli') return;
    $lockName = 'oppw-' . substr(hash_hmac(
        'sha256',
        $bucket . '|' . $subject,
        (string)config()['rate_limit_hmac_secret']
    ), 0, 48);
    $stmt = $db->prepare('SELECT GET_LOCK(?, 0)');
    $stmt->execute([$lockName]);
    if ((int)$stmt->fetchColumn() !== 1) {
        header('Retry-After: 2');
        json_response(['ok' => false, 'error' => 'A request for this resource is already running'], 429);
    }
    register_shutdown_function(static function () use ($db, $lockName): void {
        try {
            $release = $db->prepare('SELECT RELEASE_LOCK(?)');
            $release->execute([$lockName]);
        } catch (Throwable) {
        }
    });
}

function requested_analytics_rolling_weeks(mixed $value): int
{
    $validated = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
    if ($validated === false) return 4;
    return (int)$validated;
}

function independent_manual_admin_token(array $cfg): string
{
    if (!(bool)($cfg['manual_admin_enabled'] ?? false)) return '';
    $manual = trim((string)($cfg['manual_admin_token'] ?? ''));
    if ($manual === '' || str_contains($manual, 'replace-with-')) return '';
    $pairing = trim((string)($cfg['pairing_admin_token'] ?? ''));
    if ($pairing !== '' && hash_equals($pairing, $manual)) return '';
    return $manual;
}

function browser_admin_headers(): void
{
    header('Cache-Control: no-store, max-age=0');
    header('Pragma: no-cache');
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    header('X-Frame-Options: DENY');
    header('Permissions-Policy: camera=(), microphone=(), geolocation=()');
    header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");
}

function normalized_request_origin(string $value): string
{
    $parts = parse_url(trim($value));
    if (!is_array($parts)) return '';
    $scheme = strtolower((string)($parts['scheme'] ?? ''));
    $host = strtolower((string)($parts['host'] ?? ''));
    if (!in_array($scheme, ['http', 'https'], true) || $host === '') return '';
    $port = isset($parts['port']) ? (int)$parts['port'] : ($scheme === 'https' ? 443 : 80);
    return $scheme . '://' . $host . ':' . $port;
}

function browser_form_is_same_origin(
    array $server,
    ?bool $httpsRequest = null,
    bool $trustForwardedHost = false
): bool
{
    $fetchSite = strtolower(trim((string)($server['HTTP_SEC_FETCH_SITE'] ?? '')));
    if ($fetchSite !== '' && $fetchSite !== 'same-origin') return false;
    if ($fetchSite === 'same-origin') return true;

    $httpsRequest ??= (!empty($server['HTTPS']) && strtolower((string)$server['HTTPS']) !== 'off')
        || (int)($server['SERVER_PORT'] ?? 0) === 443;
    $scheme = $httpsRequest ? 'https' : 'http';
    $host = trim((string)($server['HTTP_HOST'] ?? ''));
    if ($trustForwardedHost) {
        $forwardedHost = trim(explode(',', (string)($server['HTTP_X_FORWARDED_HOST'] ?? ''))[0]);
        if ($forwardedHost !== '') $host = $forwardedHost;
    }
    $expected = normalized_request_origin($scheme . '://' . $host);
    if ($expected === '') return false;

    $origin = trim((string)($server['HTTP_ORIGIN'] ?? ''));
    if ($origin !== '') return hash_equals($expected, normalized_request_origin($origin));

    $referer = trim((string)($server['HTTP_REFERER'] ?? ''));
    if ($referer !== '') return hash_equals($expected, normalized_request_origin($referer));

    return false;
}

function require_same_origin_browser_post(): void
{
    if (PHP_SAPI === 'cli') return;
    if (strcasecmp((string)($_SERVER['REQUEST_METHOD'] ?? ''), 'POST') !== 0) return;
    if (!browser_form_is_same_origin(
        $_SERVER,
        is_https_request(),
        !empty(config()['trust_forwarded_proto'])
    )) {
        json_response(['ok' => false, 'error' => 'Cross-site form submission rejected'], 403);
    }
}

function require_write_token(): void
{
    require_https();
    $expected = (string)(config()['write_token'] ?? '');
    $provided = bearer_token();
    if ($expected === '' || $provided === '' || !hash_equals($expected, $provided)) {
        json_response(['ok' => false, 'error' => 'Unauthorized'], 401);
    }
}

function require_coordination_actor(PDO $db, string $accountKey, mixed $rawActor, string $purpose): array
{
    if (!is_array($rawActor)) {
        json_response(['ok' => false, 'error' => 'coordination object required'], 409);
    }
    $role = strtoupper(trim((string)($rawActor['role'] ?? '')));
    $ownerId = strtolower(trim((string)($rawActor['ownerId'] ?? '')));
    $fencingToken = (int)($rawActor['fencingToken'] ?? 0);
    if (!in_array($role, ['EXECUTOR', 'PUBLISHER'], true)
        || !preg_match('/^[a-f0-9]{32}$/', $ownerId)
        || $fencingToken <= 0) {
        json_response(['ok' => false, 'error' => 'invalid coordination actor'], 409);
    }

    try {
        $stmt = $db->prepare(
            'SELECT owner_id, fencing_token, expires_at > UTC_TIMESTAMP(3) AS active
               FROM strategy_runtime_leases
              WHERE strategy_key = ? AND lease_name = ?
              LIMIT 1'
        );
        $stmt->execute([$accountKey, $role]);
        $lease = $stmt->fetch();
        $valid = is_array($lease)
            && (int)($lease['active'] ?? 0) === 1
            && hash_equals((string)$lease['owner_id'], $ownerId)
            && (int)$lease['fencing_token'] === $fencingToken;
        if (!$valid) {
            json_response(['ok' => false, 'error' => 'stale or invalid global role lease'], 409);
        }

        if ($purpose === 'snapshot' && $role === 'EXECUTOR') {
            $publisherStmt = $db->prepare(
                "SELECT 1 FROM strategy_runtime_leases
                  WHERE strategy_key = ? AND lease_name = 'PUBLISHER'
                    AND expires_at > UTC_TIMESTAMP(3)
                  LIMIT 1"
            );
            $publisherStmt->execute([$accountKey]);
            if ($publisherStmt->fetchColumn()) {
                json_response(['ok' => false, 'error' => 'dedicated publisher lease is active'], 409);
            }
        }
    } catch (Throwable $e) {
        error_log('OPPW coordination validation failed: ' . $e->getMessage());
        json_response(['ok' => false, 'error' => 'Global coordination unavailable'], 503);
    }

    return ['role' => $role, 'ownerId' => $ownerId, 'fencingToken' => $fencingToken];
}

function create_access_token(PDO $db, string $deviceId): array
{
    $raw = random_token(32);
    $expires = utc_now()->modify('+' . max(60, (int)config()['access_token_ttl_seconds']) . ' seconds');
    $stmt = $db->prepare('INSERT INTO monitor_access_tokens(token_hash, device_id, expires_at) VALUES (?, ?, ?)');
    $stmt->execute([token_hash($raw), $deviceId, mysql_datetime($expires)]);
    return ['token' => $raw, 'expiresAt' => atom_datetime($expires)];
}

function allowed_accounts(PDO $db, string $deviceId): array
{
    $stmt = $db->prepare(
        'SELECT a.account_key, a.display_name, a.account_type, a.broker_account_id, a.is_default,
                da.can_control_service
           FROM monitor_device_accounts da
           JOIN monitor_accounts a ON a.account_key = da.account_key
          WHERE da.device_id = ? AND a.enabled = TRUE
          ORDER BY a.sort_order, a.display_name'
    );
    $stmt->execute([$deviceId]);
    return array_map(static fn(array $row): array => [
        'key' => (string)$row['account_key'],
        'displayName' => (string)$row['display_name'],
        'accountType' => (string)$row['account_type'],
        'brokerAccountId' => (string)$row['broker_account_id'],
        'isDefault' => (bool)$row['is_default'],
        'canControlService' => (bool)$row['can_control_service'],
    ], $stmt->fetchAll());
}

function session_payload(PDO $db, array $device, string $accessToken, string $accessExpiresAt, string $refreshToken, string $refreshExpiresAt): array
{
    return [
        'accessToken' => $accessToken,
        'accessTokenExpiresAt' => $accessExpiresAt,
        'refreshToken' => $refreshToken,
        'refreshTokenExpiresAt' => $refreshExpiresAt,
        'device' => [
            'id' => (string)$device['device_id'],
            'name' => (string)$device['device_name'],
        ],
        'allowedAccounts' => allowed_accounts($db, (string)$device['device_id']),
    ];
}

function require_mobile_session(?string $accountKey = null): array
{
    require_https();
    $provided = bearer_token();
    if ($provided === '') json_response(['ok' => false, 'error' => 'Unauthorized'], 401);

    $db = pdo();
    $stmt = $db->prepare(
        'SELECT t.device_id, d.device_name
           FROM monitor_access_tokens t
           JOIN monitor_devices d ON d.device_id = t.device_id
          WHERE t.token_hash = ?
            AND t.revoked_at IS NULL
            AND t.expires_at > UTC_TIMESTAMP(3)
            AND d.enabled = TRUE
            AND d.refresh_expires_at > UTC_TIMESTAMP(3)
          LIMIT 1'
    );
    $stmt->execute([token_hash($provided)]);
    $session = $stmt->fetch();
    if (!$session) json_response(['ok' => false, 'error' => 'Unauthorized'], 401);

    $deviceId = (string)$session['device_id'];
    if ($accountKey !== null && $accountKey !== '') {
        $allowed = $db->prepare(
            'SELECT 1
               FROM monitor_device_accounts da
               JOIN monitor_accounts a ON a.account_key = da.account_key
              WHERE da.device_id = ? AND da.account_key = ? AND a.enabled = TRUE'
        );
        $allowed->execute([$deviceId, $accountKey]);
        if (!$allowed->fetchColumn()) json_response(['ok' => false, 'error' => 'Forbidden for selected account'], 403);
    }

    $touchToken = $db->prepare('UPDATE monitor_access_tokens SET last_used_at = UTC_TIMESTAMP(3) WHERE token_hash = ?');
    $touchToken->execute([token_hash($provided)]);
    $touchDevice = $db->prepare('UPDATE monitor_devices SET last_seen_at = UTC_TIMESTAMP(3) WHERE device_id = ?');
    $touchDevice->execute([$deviceId]);
    return ['device_id' => $deviceId, 'device_name' => (string)$session['device_name']];
}

function push_enabled(): bool
{
    $cfg = config();
    return (bool)($cfg['push_enabled'] ?? false)
        && trim((string)($cfg['firebase_project_id'] ?? '')) !== ''
        && is_file((string)($cfg['firebase_service_account_file'] ?? ''));
}

function fcm_service_account(): array
{
    static $account;
    if ($account !== null) return $account;
    $path = (string)(config()['firebase_service_account_file'] ?? '');
    if ($path === '' || !is_file($path)) throw new RuntimeException('Firebase service account file is missing');
    $decoded = json_decode((string)file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
    foreach (['client_email', 'private_key', 'token_uri'] as $key) {
        if (trim((string)($decoded[$key] ?? '')) === '') throw new RuntimeException("Firebase service account field is missing: $key");
    }
    return $account = $decoded;
}

function fcm_access_token(): string
{
    $cfg = config();
    $cacheFile = fcm_token_cache_path($cfg);
    if (is_link($cacheFile)) throw new RuntimeException('Firebase token cache file cannot be a symbolic link');
    $handle = @fopen($cacheFile, 'c+b');
    if ($handle === false) throw new RuntimeException('Firebase token cache file could not be opened');
    try {
        if (!flock($handle, LOCK_EX)) throw new RuntimeException('Firebase token cache could not be locked');
        $stat = fstat($handle);
        if (!is_array($stat) || (((int)$stat['mode'] & 0170000) !== 0100000)) {
            throw new RuntimeException('Firebase token cache is not a regular file');
        }
        if (!@chmod($cacheFile, 0600)) throw new RuntimeException('Firebase token cache permissions could not be restricted');
        if (DIRECTORY_SEPARATOR === '/' && (((int)fileperms($cacheFile) & 0077) !== 0)) {
            throw new RuntimeException('Firebase token cache permissions are too broad');
        }
        rewind($handle);
        $rawCache = stream_get_contents($handle, 65537);
        if (is_string($rawCache) && strlen($rawCache) <= 65536 && trim($rawCache) !== '') {
            try {
                $cached = json_decode($rawCache, true, 32, JSON_THROW_ON_ERROR);
                if (is_string($cached['token'] ?? null) && (int)($cached['expires_at'] ?? 0) > time() + 60) {
                    return $cached['token'];
                }
            } catch (Throwable) {
            }
        }

        $service = fcm_service_account();
        $now = time();
        $header = base64url_encode(json_encode(['alg' => 'RS256', 'typ' => 'JWT'], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
        $claims = base64url_encode(json_encode([
            'iss' => $service['client_email'],
            'scope' => 'https://www.googleapis.com/auth/firebase.messaging',
            'aud' => $service['token_uri'],
            'iat' => $now,
            'exp' => $now + 3600,
        ], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
        $unsigned = $header . '.' . $claims;
        if (!openssl_sign($unsigned, $signature, (string)$service['private_key'], OPENSSL_ALGO_SHA256)) {
            throw new RuntimeException('Unable to sign Firebase service-account JWT');
        }
        $assertion = $unsigned . '.' . base64url_encode($signature);
        $body = http_build_query([
            'grant_type' => 'urn:ietf:params:oauth:grant-type:jwt-bearer',
            'assertion' => $assertion,
        ]);
        $response = http_request_json((string)$service['token_uri'], 'POST', $body, ['Content-Type: application/x-www-form-urlencoded']);
        $token = trim((string)($response['body']['access_token'] ?? ''));
        if ($token === '') throw new RuntimeException('Firebase OAuth token response did not contain access_token');
        $expiresAt = $now + max(300, (int)($response['body']['expires_in'] ?? 3600));
        $encoded = json_encode(['token' => $token, 'expires_at' => $expiresAt], JSON_THROW_ON_ERROR);
        if (!ftruncate($handle, 0) || !rewind($handle) || fwrite($handle, $encoded) !== strlen($encoded) || !fflush($handle)) {
            throw new RuntimeException('Firebase token cache could not be updated');
        }
        return $token;
    } finally {
        @flock($handle, LOCK_UN);
        fclose($handle);
    }
}

function fcm_token_cache_path(array $cfg): string
{
    $configured = trim((string)($cfg['fcm_cache_dir'] ?? ''));
    if ($configured === '' || str_contains($configured, "\0")
        || !preg_match('/^(?:[A-Za-z]:[\\\\\/]|\\\\\\\\|\/)/', $configured)) {
        throw new RuntimeException('push_enabled requires an absolute fcm_cache_dir outside the web root');
    }
    if (is_link($configured)) throw new RuntimeException('Firebase token cache directory cannot be a symbolic link');
    if (!is_dir($configured) && !@mkdir($configured, 0700, true) && !is_dir($configured)) {
        throw new RuntimeException('Firebase token cache directory could not be created');
    }
    $directory = realpath($configured);
    $webRoot = realpath(__DIR__);
    if ($directory === false || $webRoot === false) throw new RuntimeException('Firebase token cache directory could not be resolved');
    $normalize = static function (string $path): string {
        $value = rtrim(str_replace('\\', '/', $path), '/');
        return DIRECTORY_SEPARATOR === '\\' ? strtolower($value) : $value;
    };
    $normalizedDirectory = $normalize($directory);
    $normalizedWebRoot = $normalize($webRoot);
    if ($normalizedDirectory === $normalizedWebRoot || str_starts_with($normalizedDirectory . '/', $normalizedWebRoot . '/')) {
        throw new RuntimeException('Firebase token cache directory must be outside the web root');
    }
    if (!@chmod($directory, 0700) || !is_writable($directory)) {
        throw new RuntimeException('Firebase token cache directory is not private and writable');
    }
    if (DIRECTORY_SEPARATOR === '/' && (((int)fileperms($directory) & 0077) !== 0)) {
        throw new RuntimeException('Firebase token cache directory permissions are too broad');
    }
    return $directory . DIRECTORY_SEPARATOR . 'fcm-oauth-' . hash('sha256', (string)($cfg['firebase_project_id'] ?? '')) . '.json';
}

function http_request_json(string $url, string $method, string $body, array $headers = []): array
{
    if (!function_exists('curl_init')) throw new RuntimeException('PHP cURL extension is required');
    $handle = curl_init($url);
    curl_setopt_array($handle, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_POSTFIELDS => $body,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT => 10,
        CURLOPT_HEADER => false,
    ]);
    $raw = curl_exec($handle);
    $status = (int)curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
    $error = curl_error($handle);
    if ($raw === false) throw new RuntimeException('HTTP request failed: ' . $error);
    $decoded = [];
    if (trim((string)$raw) !== '') {
        try { $decoded = json_decode((string)$raw, true, 512, JSON_THROW_ON_ERROR); } catch (Throwable) { $decoded = ['raw' => substr((string)$raw, 0, 1000)]; }
    }
    if ($status < 200 || $status >= 300) throw new RuntimeException("HTTP $status: " . substr((string)$raw, 0, 500));
    return ['status' => $status, 'body' => $decoded];
}

function fcm_send_to_token(string $token, string $title, string $body, array $data = []): void
{
    if (!push_enabled()) return;
    $project = rawurlencode((string)config()['firebase_project_id']);
    $type = strtoupper((string)($data['type'] ?? ''));
    $channelId = in_array($type, ['POSITION_OPENED', 'POSITION_CLOSED'], true) ? 'oppw_trade' : 'oppw_critical';
    $payload = [
        'message' => [
            'token' => $token,
            'notification' => ['title' => $title, 'body' => $body],
            'data' => array_map(static fn(mixed $value): string => (string)$value, $data),
            'android' => [
                'priority' => 'HIGH',
                'notification' => [
                    'channel_id' => $channelId,
                    'sound' => 'default',
                    'default_vibrate_timings' => true,
                    'visibility' => 'PRIVATE',
                ],
            ],
        ],
    ];
    http_request_json(
        "https://fcm.googleapis.com/v1/projects/$project/messages:send",
        'POST',
        json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR),
        ['Authorization: Bearer ' . fcm_access_token(), 'Content-Type: application/json; charset=utf-8']
    );
}

function send_account_push(PDO $db, string $accountKey, string $dedupKey, string $title, string $body, array $data = []): void
{
    if (!push_enabled()) return;
    $hash = hash('sha256', $accountKey . '|' . $dedupKey);
    $insert = $db->prepare('INSERT IGNORE INTO monitor_push_deliveries(delivery_hash, strategy_key, title, body, created_at) VALUES (?, ?, ?, ?, UTC_TIMESTAMP(3))');
    $insert->execute([$hash, $accountKey, substr($title, 0, 120), substr($body, 0, 500)]);
    if ($insert->rowCount() === 0) return;

    $stmt = $db->prepare(
        'SELECT DISTINCT t.fcm_token
           FROM monitor_push_tokens t
           JOIN monitor_devices d ON d.device_id = t.device_id AND d.enabled = TRUE
           JOIN monitor_device_accounts a ON a.device_id = t.device_id AND a.account_key = ?
          WHERE t.enabled = TRUE'
    );
    $stmt->execute([$accountKey]);
    foreach ($stmt->fetchAll() as $row) {
        try {
            fcm_send_to_token((string)$row['fcm_token'], $title, $body, $data + ['accountKey' => $accountKey]);
            $touch = $db->prepare('UPDATE monitor_push_tokens SET last_success_at = UTC_TIMESTAMP(3), last_error = NULL WHERE fcm_token_hash = ?');
            $touch->execute([hash('sha256', (string)$row['fcm_token'])]);
        } catch (Throwable $error) {
            error_log('OPPW push failed: ' . $error->getMessage());
            $message = substr($error->getMessage(), 0, 500);
            $disable = str_contains(strtoupper($message), 'UNREGISTERED') || str_contains($message, 'HTTP 404');
            $fail = $db->prepare('UPDATE monitor_push_tokens SET last_error = ?, enabled = IF(?, FALSE, enabled) WHERE fcm_token_hash = ?');
            $fail->execute([$message, $disable ? 1 : 0, hash('sha256', (string)$row['fcm_token'])]);
        }
    }
}
