<?php
declare(strict_types=1);

function oppw_equity_parse_local_datetime(mixed $value, DateTimeZone $timezone): ?DateTimeImmutable
{
    $text = trim((string)$value);
    if ($text === '') return null;
    try {
        return (new DateTimeImmutable($text))->setTimezone($timezone);
    } catch (Throwable) {
        return null;
    }
}

function oppw_equity_week_start(DateTimeImmutable $local): DateTimeImmutable
{
    $day = $local->setTime(0, 0, 0);
    return $day->modify('-' . ((int)$local->format('N') - 1) . ' days');
}

function oppw_equity_previous_weekday(DateTimeImmutable $localDay): DateTimeImmutable
{
    $candidate = $localDay->modify('-1 day');
    while ((int)$candidate->format('N') > 5) $candidate = $candidate->modify('-1 day');
    return $candidate;
}

function oppw_equity_previous_trading_day(array $session, DateTimeImmutable $today, DateTimeZone $timezone): DateTimeImmutable
{
    $value = trim((string)($session['previousTradingDay'] ?? ''));
    if (preg_match('/^\d{4}-\d{2}-\d{2}$/', $value)) {
        $parsed = DateTimeImmutable::createFromFormat('!Y-m-d', $value, $timezone);
        if ($parsed && $parsed->format('Y-m-d') === $value) return $parsed;
    }
    return oppw_equity_previous_weekday($today);
}

function oppw_equity_manual_preopen_start(
    array $snapshot,
    DateTimeImmutable $marketOpen,
    DateTimeZone $timezone
): DateTimeImmutable {
    $position = is_array($snapshot['position'] ?? null) ? $snapshot['position'] : [];
    if (($position['manual'] ?? false) !== true) return $marketOpen;
    $opened = oppw_equity_parse_local_datetime($position['openedAt'] ?? '', $timezone);
    if ($opened === null || $opened >= $marketOpen) return $marketOpen;
    if ($opened->format('Y-m-d') !== $marketOpen->format('Y-m-d')) return $marketOpen;
    return $opened;
}

function oppw_equity_period_boundaries(
    array $snapshot,
    DateTimeImmutable $localNow,
    DateTimeZone $timezone,
    ?DateTimeImmutable $currentWeekMarketOpen = null,
    ?DateTimeImmutable $previousWeekMarketOpen = null
): array {
    $localNow = $localNow->setTimezone($timezone);
    $today = $localNow->setTime(0, 0, 0);
    $currentWeek = oppw_equity_week_start($today);
    $previousWeek = $currentWeek->modify('-7 days');
    $session = is_array($snapshot['market']['session'] ?? null) ? $snapshot['market']['session'] : [];
    $isTradingDay = array_key_exists('isTradingDay', $session)
        ? (bool)$session['isTradingDay']
        : ((int)$localNow->format('N') <= 5 && strtoupper((string)($snapshot['connection']['phase'] ?? '')) !== 'WEEKEND');

    $publishedWeekOpen = oppw_equity_parse_local_datetime($session['weekCashOpen'] ?? '', $timezone);
    if ($currentWeekMarketOpen === null) $currentWeekMarketOpen = $publishedWeekOpen;
    $currentWeekMarketOpen = $currentWeekMarketOpen?->setTimezone($timezone);
    if ($currentWeekMarketOpen === null
        || oppw_equity_week_start($currentWeekMarketOpen) != $currentWeek) {
        $currentWeekMarketOpen = $currentWeek->setTime(15, 30, 0);
    }
    $previousWeekMarketOpen = $previousWeekMarketOpen?->setTimezone($timezone);
    if ($previousWeekMarketOpen === null
        || oppw_equity_week_start($previousWeekMarketOpen) != $previousWeek) {
        $previousWeekMarketOpen = $previousWeek->setTime(15, 30, 0);
    }

    if ($isTradingDay) {
        $weeklyStart = oppw_equity_manual_preopen_start($snapshot, $currentWeekMarketOpen, $timezone);
        $dailyStart = $today->format('Y-m-d') === $currentWeekMarketOpen->format('Y-m-d')
            ? $weeklyStart
            : $today;
        return ['dailyStart' => $dailyStart, 'dailyEnd' => $localNow, 'weeklyStart' => $weeklyStart, 'weeklyEnd' => $localNow];
    }

    $previousTradingDay = oppw_equity_previous_trading_day($session, $today, $timezone);
    $weeklyStart = oppw_equity_manual_preopen_start($snapshot, $previousWeekMarketOpen, $timezone);
    $dailyStart = $previousTradingDay->format('Y-m-d') === $previousWeekMarketOpen->format('Y-m-d')
        ? $weeklyStart
        : $previousTradingDay;
    return [
        'dailyStart' => $dailyStart,
        'dailyEnd' => $previousTradingDay->modify('+1 day'),
        'weeklyStart' => $weeklyStart,
        'weeklyEnd' => $currentWeek,
    ];
}
