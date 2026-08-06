<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/analytics-window.php';

$assert = static function (bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
};
$utc = new DateTimeZone('UTC');
$first = new DateTimeImmutable('2026-01-01T10:00:00.000Z', $utc);
$latest = new DateTimeImmutable('2026-03-31T12:00:00.000Z', $utc);

$latestWindow = oppw_analytics_window_bounds($first, $latest, 4, false);
$assert(
    $latestWindow['windowEndUtc']->format('Y-m-d\TH:i:s.v\Z') === '2026-03-31T12:00:00.001Z',
    'default rolling window did not end at the latest observation'
);
$assert(
    $latestWindow['windowStartUtc']->format('Y-m-d\TH:i:s.v\Z') === '2026-03-03T12:00:00.001Z',
    'default rolling window was not the latest four exact weeks'
);

$historical = oppw_analytics_window_bounds($first, $latest, 4, false, '2026-02-15');
$assert(
    $historical['windowEndUtc']->format('Y-m-d\TH:i:s.v\Z') === '2026-02-15T23:00:00.000Z',
    'historical window did not end after its inclusive Warsaw date'
);
$assert(
    $historical['windowStartUtc']->format('Y-m-d\TH:i:s.v\Z') === '2026-01-18T23:00:00.000Z',
    'historical window did not preserve its four-week duration'
);

$summer = oppw_analytics_window_bounds($first, new DateTimeImmutable('2026-08-01T12:00:00Z'), 1, false, '2026-07-15');
$assert(
    $summer['windowEndUtc']->format('Y-m-d\TH:i:s.v\Z') === '2026-07-15T22:00:00.000Z',
    'historical window ignored Warsaw daylight-saving time'
);

$allHistory = oppw_analytics_window_bounds($first, $latest, 4, true, '2026-02-15');
$assert(
    $allHistory['windowStartUtc'] == $first && $allHistory['effectiveRollingWeeks'] === $allHistory['availableWeeks'],
    'all-history mode was narrowed by a movable rolling-window date'
);

foreach (['2026-02-30', '15-02-2026', '2026-2-15'] as $invalid) {
    try {
        oppw_analytics_window_end_date($invalid);
        throw new RuntimeException('invalid rolling-window date was accepted: ' . $invalid);
    } catch (InvalidArgumentException) {
    }
}

try {
    oppw_analytics_window_bounds($first, $latest, 4, false, '2025-12-31');
    throw new RuntimeException('rolling-window date outside retained history was accepted');
} catch (OutOfRangeException) {
}

echo "ANALYTICS WINDOW TESTS PASSED cases=8\n";
