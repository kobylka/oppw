<?php
declare(strict_types=1);

const OPPW_DRAWDOWN_EPSILON = 1.0e-12;
const OPPW_DRAWDOWN_SERIES_MAXIMUM = 2000;

function oppw_drawdown_iso(string $value): string
{
    if ($value === '') return '';
    try {
        return (new DateTimeImmutable($value, new DateTimeZone('UTC')))
            ->setTimezone(new DateTimeZone('UTC'))
            ->format('Y-m-d\\TH:i:s.u\\Z');
    } catch (Throwable) {
        return $value;
    }
}

function oppw_drawdown_epoch(string $value): ?int
{
    if ($value === '') return null;
    try {
        return (new DateTimeImmutable($value, new DateTimeZone('UTC')))->getTimestamp();
    } catch (Throwable) {
        return null;
    }
}

function oppw_drawdown_time_value(string $value): ?float
{
    if ($value === '') return null;
    try {
        return (float)(new DateTimeImmutable($value, new DateTimeZone('UTC')))->format('U.u');
    } catch (Throwable) {
        return null;
    }
}

function oppw_drawdown_trade_key(string $strategyKey, mixed $positionTicket): string
{
    $ticket = is_numeric($positionTicket) ? (int)$positionTicket : 0;
    return $strategyKey !== '' && $ticket > 0 ? $strategyKey . ':' . $ticket : '';
}

/**
 * Combines time-ordered account samples into a portfolio curve without holding
 * the complete minute history in PHP memory.
 */
function oppw_portfolio_equity_rows(iterable $equityRows): Generator
{
    $latestEquity = [];
    $latestTradeKey = [];
    $latestSource = [];
    $capturedAt = '';
    $group = [];
    $portfolioStarted = false;
    $emit = static function (string $time, array $rows) use (&$latestEquity, &$latestTradeKey, &$latestSource, &$portfolioStarted): ?array {
        if ($time === '') return null;
        $accountEntryFlow = 0.0;
        foreach ($rows as $row) {
            $strategyKey = (string)($row['strategy_key'] ?? '');
            if ($strategyKey === '' || !is_numeric($row['equity'] ?? null)) continue;
            if ($portfolioStarted && !array_key_exists($strategyKey, $latestEquity)) $accountEntryFlow += (float)$row['equity'];
            $latestEquity[$strategyKey] = (float)$row['equity'];
            $latestTradeKey[$strategyKey] = oppw_drawdown_trade_key($strategyKey, $row['position_ticket'] ?? null);
            $latestSource[$strategyKey] = strtoupper((string)($row['source_granularity'] ?? 'MINUTE'));
        }
        if (!$latestEquity) return null;
        $hasMinuteSample = in_array('MINUTE', $latestSource, true);
        $hasDailyFallback = in_array('DAILY_FALLBACK', $latestSource, true);
        $portfolioStarted = true;
        return [
            'capturedAt' => oppw_drawdown_iso($time),
            'equity' => array_sum($latestEquity),
            'tradeKeys' => array_values(array_unique(array_filter($latestTradeKey))),
            'sourceGranularity' => $hasMinuteSample
                ? ($hasDailyFallback ? 'MINUTE_WITH_DAILY_FALLBACK' : 'MINUTE')
                : 'DAILY_FALLBACK',
            'accountEntryFlow' => $accountEntryFlow,
        ];
    };

    foreach ($equityRows as $row) {
        $rowTime = (string)($row['captured_minute'] ?? '');
        if ($rowTime === '') continue;
        if ($capturedAt !== '' && $rowTime !== $capturedAt) {
            $point = $emit($capturedAt, $group);
            if ($point !== null) yield $point;
            $group = [];
        }
        $capturedAt = $rowTime;
        $group[] = $row;
    }
    $point = $emit($capturedAt, $group);
    if ($point !== null) yield $point;
}

function oppw_external_flow_amount(array $flow): float
{
    $amount = is_numeric($flow['amount'] ?? null) ? (float)$flow['amount'] : 0.0;
    return match (strtoupper((string)($flow['flow_type'] ?? ''))) {
        'TOP_UP' => abs($amount),
        'WITHDRAWAL' => -abs($amount),
        'ADJUSTMENT' => $amount,
        default => 0.0,
    };
}

function oppw_drawdown_series_point(
    int $index,
    array $row,
    float $equityIndex,
    float $drawdownPercent,
    float $drawdownCurrency
): array {
    $capturedAt = (string)$row['capturedAt'];
    $tradeKeys = array_values(array_unique(array_filter($row['tradeKeys'] ?? [])));
    return [
        'index' => $index,
        'capturedAt' => $capturedAt,
        'equity' => (float)$row['equity'],
        'equityIndex' => $equityIndex,
        'drawdownPercent' => $drawdownPercent,
        'drawdownCurrency' => $drawdownCurrency,
        'tradeKeys' => $tradeKeys,
        'sourceGranularity' => (string)($row['sourceGranularity'] ?? 'MINUTE'),
        // Compatibility fields for Android clients predating the minute-equity contract.
        'tradeKey' => $tradeKeys[0] ?? '',
        'closedAt' => $capturedAt,
        'maePercent' => 0.0,
    ];
}

function oppw_downsample_drawdown_series(array $series, int $maximum = OPPW_DRAWDOWN_SERIES_MAXIMUM): array
{
    $count = count($series);
    if ($count <= $maximum || $maximum < 4) return $series;

    $bucketCount = max(1, intdiv($maximum - 2, 2));
    $interiorCount = max(0, $count - 2);
    $selected = [0 => $series[0], $count - 1 => $series[$count - 1]];
    for ($bucket = 0; $bucket < $bucketCount; $bucket++) {
        $start = 1 + (int)floor($interiorCount * $bucket / $bucketCount);
        $end = min($count - 1, 1 + (int)floor($interiorCount * ($bucket + 1) / $bucketCount));
        if ($start >= $end) continue;
        $minimumIndex = $start;
        $maximumIndex = $start;
        for ($index = $start + 1; $index < $end; $index++) {
            if ((float)$series[$index]['drawdownPercent'] < (float)$series[$minimumIndex]['drawdownPercent']) $minimumIndex = $index;
            if ((float)$series[$index]['drawdownPercent'] > (float)$series[$maximumIndex]['drawdownPercent']) $maximumIndex = $index;
        }
        $selected[$minimumIndex] = $series[$minimumIndex];
        $selected[$maximumIndex] = $series[$maximumIndex];
    }
    ksort($selected, SORT_NUMERIC);
    return array_values($selected);
}

function oppw_empty_drawdown_result(): array
{
    return [
        'sourceGranularity' => 'NONE', 'cashFlowAdjusted' => true, 'statisticsExact' => true,
        'sampleCount' => 0, 'minuteSampleCount' => 0, 'dailyFallbackSampleCount' => 0,
        'seriesDownsampled' => false, 'maxDrawdownPercent' => 0.0, 'maxDrawdownCurrency' => 0.0,
        'averageDepthPercent' => 0.0, 'averageLengthSeconds' => 0.0,
        'longestLengthSeconds' => 0, 'averageTroughRecoverySeconds' => 0.0,
        'timeUnderwaterPercent' => 0.0, 'ulcerIndexPercent' => 0.0,
        'series' => [], 'episodes' => [], 'tradeKeys' => [],
        '_dailyEquity' => [], '_portfolioEntryFlowsByDay' => [],
    ];
}

function oppw_drawdown_analyze(
    iterable $portfolioRows,
    array $cashFlows,
    int $seriesMaximum = OPPW_DRAWDOWN_SERIES_MAXIMUM
): array {
    usort($cashFlows, static fn(array $left, array $right): int =>
        strcmp((string)($left['occurred_at'] ?? ''), (string)($right['occurred_at'] ?? ''))
    );

    $series = [];
    $episodes = [];
    $allTradeKeys = [];
    $sampleCount = 0;
    $minuteSampleCount = 0;
    $dailyFallbackSampleCount = 0;
    $underwaterSampleCount = 0;
    $dailyEquity = [];
    $portfolioEntryFlowsByDay = [];
    $flowIndex = 0;
    $previousEpoch = null;
    $previousEquity = null;
    $cumulativeExternalFlow = 0.0;
    $flowAdjustedEquity = null;
    $equityIndex = 100.0;
    $peakEquity = null;
    $peakIndex = 100.0;
    $maximumDrawdownPercent = 0.0;
    $maximumDrawdownCurrency = 0.0;
    $ulcerSquares = 0.0;
    $activeEpisode = null;
    $latestPeakPoint = null;
    $firstPoint = null;
    $lastPoint = null;

    foreach ($portfolioRows as $row) {
        $capturedAt = (string)($row['capturedAt'] ?? '');
        $capturedEpoch = oppw_drawdown_time_value($capturedAt);
        $equity = is_numeric($row['equity'] ?? null) ? (float)$row['equity'] : 0.0;
        if ($capturedAt === '' || $capturedEpoch === null || !is_finite($equity) || $equity <= 0.0) continue;

        if ($previousEquity === null) {
            $flowAdjustedEquity = $equity;
        } else {
            $externalFlow = (float)($row['accountEntryFlow'] ?? 0.0);
            while ($flowIndex < count($cashFlows)) {
                $flowEpoch = oppw_drawdown_time_value((string)($cashFlows[$flowIndex]['occurred_at'] ?? ''));
                if ($flowEpoch === null || $flowEpoch <= (float)$previousEpoch) {
                    $flowIndex++;
                    continue;
                }
                if ($flowEpoch > $capturedEpoch) break;
                $externalFlow += oppw_external_flow_amount($cashFlows[$flowIndex++]);
            }
            $cumulativeExternalFlow += $externalFlow;
            $factor = $previousEquity > OPPW_DRAWDOWN_EPSILON
                ? ($equity - $externalFlow) / $previousEquity
                : 1.0;
            if (!is_finite($factor) || $factor <= OPPW_DRAWDOWN_EPSILON) $factor = OPPW_DRAWDOWN_EPSILON;
            $equityIndex *= $factor;
            $flowAdjustedEquity = $equity - $cumulativeExternalFlow;
        }

        $peakEquity = $peakEquity === null ? $flowAdjustedEquity : max($peakEquity, $flowAdjustedEquity);
        $peakIndex = max($peakIndex, $equityIndex);
        $drawdownPercent = $peakIndex > OPPW_DRAWDOWN_EPSILON ? min(0.0, ($equityIndex / $peakIndex - 1.0) * 100.0) : 0.0;
        $drawdownCurrency = min(0.0, $flowAdjustedEquity - $peakEquity);
        $sampleCount++;
        $point = oppw_drawdown_series_point($sampleCount, $row, $equityIndex, $drawdownPercent, $drawdownCurrency);
        $series[] = $point;
        if (count($series) > $seriesMaximum * 2) $series = oppw_downsample_drawdown_series($series, $seriesMaximum);
        $firstPoint ??= $point;
        $lastPoint = $point;
        foreach ($point['tradeKeys'] as $key) $allTradeKeys[$key] = true;
        if (str_contains($point['sourceGranularity'], 'MINUTE')) $minuteSampleCount++;
        if (str_contains($point['sourceGranularity'], 'DAILY_FALLBACK')) $dailyFallbackSampleCount++;
        $maximumDrawdownPercent = min($maximumDrawdownPercent, $drawdownPercent);
        $maximumDrawdownCurrency = min($maximumDrawdownCurrency, $drawdownCurrency);
        $ulcerSquares += $drawdownPercent * $drawdownPercent;
        if ($drawdownPercent < -OPPW_DRAWDOWN_EPSILON) $underwaterSampleCount++;
        try {
            $local = (new DateTimeImmutable($capturedAt))->setTimezone(new DateTimeZone('Europe/Warsaw'));
            if ((int)$local->format('N') <= 5) {
                $day = $local->format('Y-m-d');
                $dailyEquity[$day] = $equity;
                $entryFlow = (float)($row['accountEntryFlow'] ?? 0.0);
                if ($entryFlow !== 0.0) $portfolioEntryFlowsByDay[$day] = ($portfolioEntryFlowsByDay[$day] ?? 0.0) + $entryFlow;
            }
        } catch (Throwable) {
        }

        if ($drawdownPercent < -OPPW_DRAWDOWN_EPSILON) {
            if ($activeEpisode === null) {
                $start = $latestPeakPoint ?? $point;
                $activeEpisode = [
                    'start' => $start,
                    'trough' => $point,
                    'tradeKeys' => array_fill_keys(array_merge($start['tradeKeys'], $point['tradeKeys']), true),
                ];
            } else {
                foreach ($point['tradeKeys'] as $key) $activeEpisode['tradeKeys'][$key] = true;
                if ($drawdownPercent < (float)$activeEpisode['trough']['drawdownPercent']) $activeEpisode['trough'] = $point;
            }
        } else {
            if ($activeEpisode !== null) {
                foreach ($point['tradeKeys'] as $key) $activeEpisode['tradeKeys'][$key] = true;
                $episodes[] = oppw_close_drawdown_episode($activeEpisode, $point, true, count($episodes) + 1);
                $activeEpisode = null;
            }
            $latestPeakPoint = $point;
        }

        $previousEpoch = $capturedEpoch;
        $previousEquity = $equity;
    }

    if ($sampleCount === 0 || $firstPoint === null || $lastPoint === null) return oppw_empty_drawdown_result();
    if ($activeEpisode !== null) {
        $episodes[] = oppw_close_drawdown_episode($activeEpisode, $lastPoint, false, count($episodes) + 1);
    }

    $depths = array_column($episodes, 'depthPercent');
    $lengths = array_column($episodes, 'elapsedSeconds');
    $recoveries = array_values(array_filter(array_column($episodes, 'recoverySeconds'), static fn(mixed $value): bool => $value !== null));
    $firstEpoch = oppw_drawdown_epoch((string)$firstPoint['capturedAt']);
    $lastEpoch = oppw_drawdown_epoch((string)$lastPoint['capturedAt']);
    $observedSeconds = $firstEpoch !== null && $lastEpoch !== null ? max(0, $lastEpoch - $firstEpoch) : 0;
    $underwaterSeconds = array_sum($lengths);
    $timeUnderwaterPercent = $observedSeconds > 0
        ? min(100.0, $underwaterSeconds / $observedSeconds * 100.0)
        : ($underwaterSampleCount / $sampleCount * 100.0);
    $boundedSeries = oppw_downsample_drawdown_series($series, $seriesMaximum);
    $sourceGranularity = $minuteSampleCount > 0
        ? ($dailyFallbackSampleCount > 0 ? 'MINUTE_WITH_DAILY_FALLBACK' : 'MINUTE')
        : 'DAILY_FALLBACK';

    return [
        'sourceGranularity' => $sourceGranularity,
        'cashFlowAdjusted' => true,
        'statisticsExact' => true,
        'sampleCount' => $sampleCount,
        'minuteSampleCount' => $minuteSampleCount,
        'dailyFallbackSampleCount' => $dailyFallbackSampleCount,
        'seriesDownsampled' => count($boundedSeries) < $sampleCount,
        'maxDrawdownPercent' => abs($maximumDrawdownPercent),
        'maxDrawdownCurrency' => abs($maximumDrawdownCurrency),
        'averageDepthPercent' => $depths ? array_sum($depths) / count($depths) : 0.0,
        'averageLengthSeconds' => $lengths ? array_sum($lengths) / count($lengths) : 0.0,
        'longestLengthSeconds' => $lengths ? max($lengths) : 0,
        'averageTroughRecoverySeconds' => $recoveries ? array_sum($recoveries) / count($recoveries) : 0.0,
        'timeUnderwaterPercent' => $timeUnderwaterPercent,
        'ulcerIndexPercent' => sqrt($ulcerSquares / $sampleCount),
        'series' => $boundedSeries,
        'episodes' => $episodes,
        'tradeKeys' => array_keys($allTradeKeys),
        '_dailyEquity' => $dailyEquity,
        '_portfolioEntryFlowsByDay' => $portfolioEntryFlowsByDay,
    ];
}

function oppw_close_drawdown_episode(array $active, array $end, bool $recovered, int $number): array
{
    $start = $active['start'];
    $trough = $active['trough'];
    $startEpoch = oppw_drawdown_epoch((string)$start['capturedAt']);
    $troughEpoch = oppw_drawdown_epoch((string)$trough['capturedAt']);
    $endEpoch = oppw_drawdown_epoch((string)$end['capturedAt']);
    $elapsed = $startEpoch !== null && $endEpoch !== null ? max(0, $endEpoch - $startEpoch) : 0;
    $recovery = $recovered && $troughEpoch !== null && $endEpoch !== null ? max(0, $endEpoch - $troughEpoch) : null;
    return [
        'number' => $number,
        'startAt' => (string)$start['capturedAt'],
        'troughAt' => (string)$trough['capturedAt'],
        'endAt' => (string)$end['capturedAt'],
        'depthPercent' => abs((float)$trough['drawdownPercent']),
        'recovered' => $recovered,
        'elapsedSeconds' => $elapsed,
        'recoverySeconds' => $recovery,
        'tradeKeys' => array_keys($active['tradeKeys']),
    ];
}
