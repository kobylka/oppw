<?php
declare(strict_types=1);

if (PHP_SAPI !== 'cli') {
    http_response_code(404);
    exit;
}
if ($argc !== 4) {
    fwrite(STDERR, "Usage: php write_mysql_client_config.php CONFIG_PATH OUTPUT_PATH HOST_OVERRIDE\n");
    exit(2);
}

$configPath = (string)$argv[1];
$outputPath = (string)$argv[2];
$hostOverride = trim((string)$argv[3]);
if (!is_file($configPath)) throw new RuntimeException('Backend configuration file is missing');
$config = require $configPath;
if (!is_array($config)) throw new RuntimeException('Backend configuration must return an array');

$dsn = trim((string)($config['dsn'] ?? ''));
if (!str_starts_with(strtolower($dsn), 'mysql:')) throw new RuntimeException('Backend DSN must use MySQL');
$dsnValues = [];
foreach (explode(';', substr($dsn, 6)) as $part) {
    if (!str_contains($part, '=')) continue;
    [$key, $value] = explode('=', $part, 2);
    $dsnValues[strtolower(trim($key))] = trim($value);
}
$host = $hostOverride !== '' ? $hostOverride : (string)($dsnValues['host'] ?? '');
$port = (int)($dsnValues['port'] ?? 3306);
$database = (string)($dsnValues['dbname'] ?? '');
$user = (string)($config['db_user'] ?? '');
$password = (string)($config['db_password'] ?? '');
if (!preg_match('/^[A-Za-z0-9.-]+$/', $host)) throw new RuntimeException('Database host is invalid');
if ($port < 1 || $port > 65535) throw new RuntimeException('Database port is invalid');
if (!preg_match('/^[A-Za-z0-9_]+$/', $database)) throw new RuntimeException('Database name is invalid');
if ($user === '' || $password === '') throw new RuntimeException('Database credentials are incomplete');

$quote = static function (string $value): string {
    if (str_contains($value, "\r") || str_contains($value, "\n")) {
        throw new RuntimeException('MySQL option values cannot contain newlines');
    }
    return '"' . str_replace(['\\', '"'], ['\\\\', '\\"'], $value) . '"';
};
$contents = implode("\r\n", [
    '[client]',
    'protocol=TCP',
    'host=' . $quote($host),
    'port=' . $port,
    'user=' . $quote($user),
    'password=' . $quote($password),
    'ssl-mode=REQUIRED',
    '',
]);
if (file_put_contents($outputPath, $contents, LOCK_EX) === false) {
    throw new RuntimeException('Could not write the temporary MySQL client configuration');
}
@chmod($outputPath, 0600);
echo json_encode([
    'host' => $host,
    'port' => $port,
    'database' => $database,
], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
