<?php
declare(strict_types=1);

function config(): array
{
    static $config;
    if ($config !== null) return $config;
    $path = __DIR__ . '/config.php';
    if (!is_file($path)) json_response(['ok' => false, 'error' => 'Server configuration missing'], 500);
    $config = require $path;
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
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    exit;
}

function bearer_token(): string
{
    $header = $_SERVER['HTTP_AUTHORIZATION'] ?? '';
    if (!preg_match('/^Bearer\s+(.+)$/i', trim($header), $matches)) return '';
    return trim($matches[1]);
}

function require_token(string $type): void
{
    $cfg = config();
    $expected = $type === 'write' ? (string)$cfg['write_token'] : (string)$cfg['read_token'];
    $provided = bearer_token();
    if ($expected === '' || $provided === '' || !hash_equals($expected, $provided)) {
        json_response(['ok' => false, 'error' => 'Unauthorized'], 401);
    }
}

function request_json(): array
{
    $raw = file_get_contents('php://input');
    if ($raw === false || trim($raw) === '') json_response(['ok' => false, 'error' => 'Empty JSON body'], 400);
    try {
        $data = json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    } catch (JsonException $e) {
        json_response(['ok' => false, 'error' => 'Invalid JSON: ' . $e->getMessage()], 400);
    }
    if (!is_array($data)) json_response(['ok' => false, 'error' => 'JSON object required'], 400);
    return $data;
}

function normalize_datetime(?string $value): string
{
    try {
        $dt = $value ? new DateTimeImmutable($value) : new DateTimeImmutable('now', new DateTimeZone('UTC'));
    } catch (Throwable) {
        $dt = new DateTimeImmutable('now', new DateTimeZone('UTC'));
    }
    return $dt->setTimezone(new DateTimeZone('UTC'))->format('Y-m-d H:i:s.v');
}
