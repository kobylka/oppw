<?php
declare(strict_types=1);

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
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');
    header('Pragma: no-cache');
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
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
    return $value->setTimezone(new DateTimeZone('UTC'))->format(DATE_ATOM);
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

function require_write_token(): void
{
    require_https();
    $expected = (string)(config()['write_token'] ?? '');
    $provided = bearer_token();
    if ($expected === '' || $provided === '' || !hash_equals($expected, $provided)) {
        json_response(['ok' => false, 'error' => 'Unauthorized'], 401);
    }
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
        'SELECT a.account_key, a.display_name, a.account_type, a.broker_account_id, a.is_default
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
