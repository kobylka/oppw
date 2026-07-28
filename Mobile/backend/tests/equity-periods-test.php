<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/equity-periods.php';

$timezone = new DateTimeZone('Europe/Warsaw');
$at = static fn(string $value): DateTimeImmutable => new DateTimeImmutable($value, $timezone);
$assertTime = static function (string $expected, DateTimeImmutable $actual, string $label): void {
    if ($actual->format('Y-m-d H:i:s') !== $expected) {
        throw new RuntimeException("$label expected $expected, got " . $actual->format('Y-m-d H:i:s'));
    }
};
$snapshot = static function (string $weekOpen, bool $tradingDay, ?array $position = null, string $previousDay = ''): array {
    return [
        'connection' => ['phase' => $tradingDay ? 'REGULAR' : 'WEEKEND'],
        'position' => $position,
        'market' => ['session' => [
            'isTradingDay' => $tradingDay,
            'weekCashOpen' => $weekOpen,
            'previousTradingDay' => $previousDay,
        ]],
    ];
};

$monday = oppw_equity_period_boundaries(
    $snapshot('2026-07-27T15:30:00+02:00', true), $at('2026-07-27 16:00:00'), $timezone
);
$assertTime('2026-07-27 15:30:00', $monday['dailyStart'], 'first-session daily');
$assertTime('2026-07-27 15:30:00', $monday['weeklyStart'], 'first-session weekly');

$holidayFirstDay = oppw_equity_period_boundaries(
    $snapshot('2026-09-08T15:30:00+02:00', true), $at('2026-09-08 16:00:00'), $timezone
);
$assertTime('2026-09-08 15:30:00', $holidayFirstDay['dailyStart'], 'holiday-first-session daily');
$assertTime('2026-09-08 15:30:00', $holidayFirstDay['weeklyStart'], 'holiday-first-session weekly');

$manual = ['manual' => true, 'openedAt' => '2026-07-27T14:45:12+02:00'];
$manualPreopen = oppw_equity_period_boundaries(
    $snapshot('2026-07-27T15:30:00+02:00', true, $manual), $at('2026-07-27 16:00:00'), $timezone
);
$assertTime('2026-07-27 14:45:12', $manualPreopen['dailyStart'], 'manual-preopen daily');
$assertTime('2026-07-27 14:45:12', $manualPreopen['weeklyStart'], 'manual-preopen weekly');

$strategyPreopen = oppw_equity_period_boundaries(
    $snapshot('2026-07-27T15:30:00+02:00', true, ['manual' => false, 'openedAt' => '2026-07-27T14:45:12+02:00']),
    $at('2026-07-27 16:00:00'), $timezone
);
$assertTime('2026-07-27 15:30:00', $strategyPreopen['dailyStart'], 'strategy-preopen daily');

$manualAfterOpen = oppw_equity_period_boundaries(
    $snapshot('2026-07-27T15:30:00+02:00', true, ['manual' => true, 'openedAt' => '2026-07-27T16:15:00+02:00']),
    $at('2026-07-27 17:00:00'), $timezone
);
$assertTime('2026-07-27 15:30:00', $manualAfterOpen['weeklyStart'], 'manual-after-open weekly');

$tuesday = oppw_equity_period_boundaries(
    $snapshot('2026-07-27T15:30:00+02:00', true), $at('2026-07-28 12:00:00'), $timezone
);
$assertTime('2026-07-28 00:00:00', $tuesday['dailyStart'], 'following-day daily');
$assertTime('2026-07-27 15:30:00', $tuesday['weeklyStart'], 'following-day weekly');

$weekend = oppw_equity_period_boundaries(
    $snapshot('2026-08-03T15:30:00+02:00', false, null, '2026-07-31'),
    $at('2026-08-08 12:00:00'), $timezone, null, $at('2026-07-27 15:30:00')
);
$assertTime('2026-07-31 00:00:00', $weekend['dailyStart'], 'weekend latest-day daily');
$assertTime('2026-07-27 15:30:00', $weekend['weeklyStart'], 'completed-week weekly');

echo "EQUITY PERIOD TESTS PASSED cases=7\n";
