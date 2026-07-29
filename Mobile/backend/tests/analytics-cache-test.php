<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/analytics-cache.php';

$assert = static function (bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
};

$directory = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'oppw-analytics-cache-test-' . bin2hex(random_bytes(8));
$cfg = [
    'analytics_cache_ttl_seconds' => 30,
    'analytics_cache_dir' => $directory,
    'rate_limit_hmac_secret' => str_repeat('r', 64),
];

try {
    $context = [
        'deviceId' => 'device-a',
        'accountKeys' => ['DEMO'],
        'filters' => ['scope' => 'SELECTED', 'rollingWeeks' => 82],
    ];
    $sameContextDifferentKeyOrder = [
        'filters' => ['rollingWeeks' => 82, 'scope' => 'SELECTED'],
        'accountKeys' => ['DEMO'],
        'deviceId' => 'device-a',
    ];
    $first = oppw_analytics_cache_identifiers($context, 'watermark-a');
    $same = oppw_analytics_cache_identifiers($sameContextDifferentKeyOrder, 'watermark-a');
    $newData = oppw_analytics_cache_identifiers($context, 'watermark-b');
    $differentGrant = oppw_analytics_cache_identifiers($context + ['allowedAccounts' => ['DEMO', 'REAL']], 'watermark-a');

    $assert($first === $same, 'cache identity depends on associative key order');
    $assert($first['slot'] === $newData['slot'], 'data watermark changed the bounded request slot');
    $assert($first['key'] !== $newData['key'], 'data watermark did not invalidate the cache key');
    $assert($first['slot'] !== $differentGrant['slot'], 'authorization context did not isolate cache entries');
    $assert(oppw_analytics_cache_read($cfg, $first['slot'], $first['key']) === null, 'missing cache entry was treated as a hit');

    $payload = '{"ok":true,"generatedAt":"fixed"}';
    $assert(oppw_analytics_cache_write($cfg, $first['slot'], $first['key'], $payload), 'cache write failed');
    $assert(oppw_analytics_cache_read($cfg, $first['slot'], $first['key']) === $payload, 'cache hit changed the encoded response');
    $assert(oppw_analytics_cache_read($cfg, $newData['slot'], $newData['key']) === null, 'stale data watermark reused a response');

    $path = oppw_analytics_cache_entry_path($cfg, $first['slot']);
    $assert(is_string($path) && is_file($path), 'cache entry path was not created');
    $assert(touch($path, time() - 31), 'cache expiry timestamp could not be set');
    clearstatcache(true, $path);
    $assert(oppw_analytics_cache_read($cfg, $first['slot'], $first['key']) === null, 'expired cache entry was reused');

    $assert(oppw_analytics_cache_ttl_seconds(['analytics_cache_ttl_seconds' => 120]) === 120, 'valid cache TTL changed');
    $assert(oppw_analytics_cache_ttl_seconds(['analytics_cache_ttl_seconds' => 121]) === 30, 'cache TTL escaped the short-lived bound');
    $assert(oppw_analytics_cache_directory(['analytics_cache_dir' => 'relative-cache']) === null, 'relative cache directory was accepted');
} finally {
    if (is_dir($directory)) {
        foreach (glob($directory . DIRECTORY_SEPARATOR . 'analytics-v1-*.cache') ?: [] as $path) @unlink($path);
        @rmdir($directory);
    }
}

echo "ANALYTICS CACHE TESTS PASSED cases=11\n";
