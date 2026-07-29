<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/analytics-cache.php';

$assert = static function (bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
};

$directory = sys_get_temp_dir() . DIRECTORY_SEPARATOR . 'oppw-analytics-segment-test-' . bin2hex(random_bytes(8));
$cfg = [
    'analytics_cache_dir' => $directory,
    'analytics_segment_cache_ttl_seconds' => 86400,
    'rate_limit_hmac_secret' => str_repeat('s', 64),
    'dsn' => 'mysql:host=contract;dbname=oppw_monitor',
];
$warsaw = new DateTimeZone('Europe/Warsaw');
$utc = new DateTimeZone('UTC');
$windowStart = (new DateTimeImmutable('2026-03-16 00:00:00', $warsaw))->setTimezone($utc);
$windowEnd = (new DateTimeImmutable('2026-04-06 00:00:00', $warsaw))->setTimezone($utc);
$now = new DateTimeImmutable('2026-04-01 12:00:00', $warsaw);
$context = ['dataset' => 'test-v1', 'database' => hash('sha256', $cfg['dsn']), 'accounts' => ['DEMO']];

try {
    $ranges = oppw_analytics_week_segments($windowStart, $windowEnd, $now);
    $assert(count($ranges['completed']) === 2, 'completed Warsaw weeks were not split independently');
    $assert($ranges['completed'][0]['start']->format('Y-m-d H:i:s') === '2026-03-15 23:00:00', 'winter week UTC boundary changed');
    $assert($ranges['completed'][1]['end']->format('Y-m-d H:i:s') === '2026-03-29 22:00:00', 'DST week UTC boundary changed');
    $assert($ranges['live']['start']->format('Y-m-d H:i:s') === '2026-03-29 22:00:00', 'current Warsaw week was cached as historical');

    $loaderCalls = [];
    $loader = static function (DateTimeImmutable $start, DateTimeImmutable $end, int $limit) use (&$loaderCalls): iterable {
        $loaderCalls[] = [$start->format('c'), $end->format('c'), $limit];
        yield ['captured_at' => $start->format('c'), 'value' => count($loaderCalls)];
    };
    $firstStats = oppw_analytics_segment_stats();
    $firstRows = iterator_to_array(oppw_analytics_segmented_rows(
        $cfg, $context, $windowStart, $windowEnd, $loader, $firstStats, 10, $now
    ), false);
    $assert(count($loaderCalls) === 3, 'cold segmented read did not query two completed weeks and one live range');
    $assert($firstStats['misses'] === 2 && $firstStats['hits'] === 0 && $firstStats['liveQueries'] === 1, 'cold segment statistics are incorrect');

    $loaderCalls = [];
    $secondStats = oppw_analytics_segment_stats();
    $secondRows = iterator_to_array(oppw_analytics_segmented_rows(
        $cfg, $context, $windowStart, $windowEnd, $loader, $secondStats, 10, $now
    ), false);
    $assert(count($loaderCalls) === 1, 'warm segmented read queried completed historical weeks again');
    $assert($secondStats['hits'] === 2 && $secondStats['misses'] === 0 && $secondStats['liveQueries'] === 1, 'warm segment statistics are incorrect');
    $assert(array_column($firstRows, 'captured_at') === array_column($secondRows, 'captured_at'), 'warm and cold segmented rows differ');
    $assert($secondStats['cacheRows'] === 2 && $secondStats['databaseRows'] === 1, 'warm row-source accounting is incorrect');

    $limitLoader = static function (DateTimeImmutable $start, DateTimeImmutable $end, int $limit): iterable {
        for ($index = 0; $index < 6; $index++) yield ['captured_at' => $start->format('c'), 'index' => $index];
    };
    $limitStats = oppw_analytics_segment_stats();
    $totalLimitRejected = false;
    try {
        iterator_to_array(oppw_analytics_segmented_rows(
            $cfg, array_merge($context, ['dataset' => 'total-limit-v1']), $windowStart, $windowEnd,
            $limitLoader, $limitStats, 10, $now, 10
        ), false);
    } catch (OppwAnalyticsSegmentLimitException) {
        $totalLimitRejected = true;
    }
    $assert($totalLimitRejected, 'weekly segmentation escaped the request-wide result limit');

    $firstRange = $ranges['completed'][0];
    $identity = oppw_analytics_segment_identifiers($cfg, $context + [
        'segmentStart' => $firstRange['start']->format('Y-m-d\TH:i:s.uP'),
        'segmentEnd' => $firstRange['end']->format('Y-m-d\TH:i:s.uP'),
    ]);
    $path = oppw_analytics_segment_entry_path($cfg, $identity['slot']);
    $assert(is_string($path) && is_file($path), 'completed segment file was not created');
    $assert(touch($path, time() - 86401), 'segment expiry timestamp could not be set');
    clearstatcache(true, $path);
    $assert(oppw_analytics_segment_read($cfg, $identity['slot'], $identity['key'], 10) === null, 'expired historical segment was reused');
    $assert(oppw_analytics_segment_ttl_seconds(['analytics_segment_cache_ttl_seconds' => 2592000]) === 2592000, '30-day segment TTL was rejected');
    $assert(oppw_analytics_segment_ttl_seconds(['analytics_segment_cache_ttl_seconds' => 2592001]) === 86400, 'segment TTL escaped its maximum');
} finally {
    if (is_dir($directory)) {
        foreach (glob($directory . DIRECTORY_SEPARATOR . 'analytics-segment-v1-*.cache') ?: [] as $path) @unlink($path);
        @rmdir($directory);
    }
}

echo "ANALYTICS SEGMENT TESTS PASSED cases=15\n";
