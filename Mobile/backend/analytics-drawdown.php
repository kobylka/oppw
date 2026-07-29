<?php
declare(strict_types=1);

const OPPW_DRAWDOWN_EPSILON = 1.0e-12;
const OPPW_DRAWDOWN_SERIES_MAXIMUM = 2000;
const OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS = 86400;

function oppw_drawdown_iso(string $value): string
{
    if ($value === '') return '';
    if (preg_match('/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,6}))?Z?$/', $value, $matches)) {
        $micros = str_pad((string)($matches[3] ?? ''), 6, '0');
        return $matches[1] . 'T' . $matches[2] . '.' . $micros . 'Z';
    }
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

function oppw_closed_trade_key(array $trade): string
{
    $explicit = trim((string)($trade['tradeKey'] ?? ''));
    if ($explicit !== '') return $explicit;
    $strategyKey = trim((string)($trade['strategyKey'] ?? ''));
    $ticket = is_numeric($trade['ticket'] ?? null) ? (int)$trade['ticket'] : 0;
    return $strategyKey !== '' && $ticket > 0 ? $strategyKey . ':' . $ticket : '';
}

/**
 * Closed trades define episode membership and recovery. Minute equity later
 * refines each seed's trough without changing those trade-defined boundaries.
 */
function oppw_closed_trade_drawdown_episode_seeds(array $closedTrades): array
{
    if (!$closedTrades) return [];
    usort($closedTrades, static fn(array $left, array $right): int =>
        strcmp((string)($left['closedAt'] ?? ''), (string)($right['closedAt'] ?? ''))
    );

    $equityIndex = 100.0;
    $peakIndex = 100.0;
    $latestPeakAt = (string)($closedTrades[0]['openedAt'] ?? $closedTrades[0]['closedAt'] ?? '');
    $latestPeakTradeKey = '';
    $active = null;
    $episodes = [];

    foreach ($closedTrades as $trade) {
        $closedAt = (string)($trade['closedAt'] ?? '');
        if ($closedAt === '') continue;
        $return = is_numeric($trade['tradeReturn'] ?? null) ? (float)$trade['tradeReturn'] : 0.0;
        if (!is_finite($return)) $return = 0.0;
        $equityIndex *= max(OPPW_DRAWDOWN_EPSILON, 1.0 + $return);
        $peakIndex = max($peakIndex, $equityIndex);
        $drawdownPercent = $peakIndex > OPPW_DRAWDOWN_EPSILON
            ? min(0.0, ($equityIndex / $peakIndex - 1.0) * 100.0)
            : 0.0;
        $tradeKey = oppw_closed_trade_key($trade);
        $point = [
            'capturedAt' => $closedAt,
            'drawdownPercent' => $drawdownPercent,
            'tradeKey' => $tradeKey,
        ];

        if ($drawdownPercent < -OPPW_DRAWDOWN_EPSILON) {
            if ($active === null) {
                $keys = array_filter([$latestPeakTradeKey, $tradeKey]);
                $openedAt = (string)($trade['openedAt'] ?? '');
                $startAt = $latestPeakAt !== '' ? $latestPeakAt : ($openedAt !== '' ? $openedAt : $closedAt);
                if ($openedAt !== '' && oppw_drawdown_iso($openedAt) > oppw_drawdown_iso($startAt)) {
                    $startAt = $openedAt;
                }
                $active = [
                    'startAt' => $startAt,
                    'trough' => $point,
                    'tradeKeys' => array_fill_keys($keys, true),
                ];
            } else {
                if ($tradeKey !== '') $active['tradeKeys'][$tradeKey] = true;
                if ($drawdownPercent < (float)$active['trough']['drawdownPercent']) $active['trough'] = $point;
            }
        } else {
            if ($active !== null) {
                if ($tradeKey !== '') $active['tradeKeys'][$tradeKey] = true;
                $episodes[] = [
                    'number' => count($episodes) + 1,
                    'startAt' => (string)$active['startAt'],
                    'tradeTroughAt' => (string)$active['trough']['capturedAt'],
                    'tradeEndAt' => $closedAt,
                    'tradeDepthPercent' => abs((float)$active['trough']['drawdownPercent']),
                    'recovered' => true,
                    'tradeKeys' => array_keys($active['tradeKeys']),
                ];
                $active = null;
            }
            $latestPeakAt = $closedAt;
            $latestPeakTradeKey = $tradeKey;
        }
    }

    if ($active !== null) {
        $lastClosedAt = (string)($closedTrades[count($closedTrades) - 1]['closedAt'] ?? $active['trough']['capturedAt']);
        $episodes[] = [
            'number' => count($episodes) + 1,
            'startAt' => (string)$active['startAt'],
            'tradeTroughAt' => (string)$active['trough']['capturedAt'],
            'tradeEndAt' => $lastClosedAt,
            'tradeDepthPercent' => abs((float)$active['trough']['drawdownPercent']),
            'recovered' => false,
            'tradeKeys' => array_keys($active['tradeKeys']),
        ];
    }
    return $episodes;
}

function oppw_prepare_trade_episode_states(array $episodes): array
{
    return array_values(array_map(static function (array $episode): array {
        $episode['_startEpoch'] = oppw_drawdown_time_value((string)$episode['startAt']);
        $episode['_endEpoch'] = oppw_drawdown_time_value((string)$episode['tradeEndAt']);
        $episode['_startSort'] = oppw_drawdown_iso((string)$episode['startAt']);
        $episode['_endSort'] = oppw_drawdown_iso((string)$episode['tradeEndAt']);
        $episode['_baselineIndex'] = null;
        $episode['_baselineAt'] = '';
        $episode['_troughPercent'] = 0.0;
        $episode['_troughAt'] = '';
        $episode['_latestAt'] = '';
        return $episode;
    }, $episodes));
}

/**
 * Equivalent to oppw_update_trade_episode_states() for canonical UTC strings,
 * avoiding a DateTime allocation for every minute in long episodes.
 */
function oppw_update_trade_episode_states_by_time(
    array &$states,
    int &$stateIndex,
    ?array $previousPoint,
    array $point
): void {
    $pointAt = (string)$point['capturedAt'];
    $pointSort = (string)$point['_sortAt'];
    while ($stateIndex < count($states)) {
        $state =& $states[$stateIndex];
        $startAt = (string)$state['_startSort'];
        if ($state['_startEpoch'] === null || $pointSort < $startAt) {
            unset($state);
            return;
        }
        $endAt = (string)$state['_endSort'];
        if ($state['recovered'] && $state['_endEpoch'] !== null && $pointSort > $endAt) {
            $stateIndex++;
            unset($state);
            continue;
        }
        $state['_latestAt'] = $pointAt;
        if (!str_contains((string)$point['sourceGranularity'], 'MINUTE')) {
            unset($state);
            return;
        }
        if ($state['_baselineIndex'] === null) {
            $baselinePoint = $point;
            if ($previousPoint !== null
                && str_contains((string)$previousPoint['sourceGranularity'], 'MINUTE')
                && (string)$previousPoint['_sortAt'] <= $startAt
                && (float)$previousPoint['equityIndex'] > (float)$baselinePoint['equityIndex']) {
                $baselinePoint = $previousPoint;
            }
            $state['_baselineIndex'] = (float)$baselinePoint['equityIndex'];
            $state['_baselineAt'] = (string)$state['startAt'];
        }
        $baselineIndex = (float)$state['_baselineIndex'];
        if ($baselineIndex > OPPW_DRAWDOWN_EPSILON) {
            $relativePercent = min(0.0, ((float)$point['equityIndex'] / $baselineIndex - 1.0) * 100.0);
            if ($relativePercent < (float)$state['_troughPercent']) {
                $state['_troughPercent'] = $relativePercent;
                $state['_troughAt'] = $pointAt;
            }
        }
        unset($state);
        return;
    }
}

function oppw_update_trade_episode_states(
    array &$states,
    int &$stateIndex,
    ?array $previousPoint,
    array $point
): void {
    $pointEpoch = (float)$point['_epoch'];
    while ($stateIndex < count($states)) {
        $state =& $states[$stateIndex];
        $startEpoch = $state['_startEpoch'];
        if ($startEpoch === null || $pointEpoch < (float)$startEpoch) {
            unset($state);
            return;
        }
        $endEpoch = $state['_endEpoch'];
        if ($state['recovered'] && $endEpoch !== null && $pointEpoch > (float)$endEpoch) {
            $stateIndex++;
            unset($state);
            continue;
        }
        $state['_latestAt'] = (string)$point['capturedAt'];
        if (!str_contains((string)$point['sourceGranularity'], 'MINUTE')) {
            unset($state);
            return;
        }
        if ($state['_baselineIndex'] === null) {
            $baselinePoint = $point;
            if ($previousPoint !== null
                && str_contains((string)$previousPoint['sourceGranularity'], 'MINUTE')
                && (float)$previousPoint['_epoch'] <= (float)$startEpoch
                && (float)$previousPoint['equityIndex'] > (float)$baselinePoint['equityIndex']) {
                $baselinePoint = $previousPoint;
            }
            $state['_baselineIndex'] = (float)$baselinePoint['equityIndex'];
            $state['_baselineAt'] = (string)$state['startAt'];
        }
        $baselineIndex = (float)$state['_baselineIndex'];
        if ($baselineIndex > OPPW_DRAWDOWN_EPSILON) {
            $relativePercent = min(0.0, ((float)$point['equityIndex'] / $baselineIndex - 1.0) * 100.0);
            if ($relativePercent < (float)$state['_troughPercent']) {
                $state['_troughPercent'] = $relativePercent;
                $state['_troughAt'] = (string)$point['capturedAt'];
            }
        }
        unset($state);
        return;
    }
}

function oppw_finalize_trade_episode_states(array $states): array
{
    $episodes = [];
    foreach ($states as $state) {
        $minuteRefined = (string)$state['_troughAt'] !== '' && (float)$state['_troughPercent'] < -OPPW_DRAWDOWN_EPSILON;
        $troughAt = $minuteRefined ? (string)$state['_troughAt'] : (string)$state['tradeTroughAt'];
        $depthPercent = $minuteRefined ? abs((float)$state['_troughPercent']) : (float)$state['tradeDepthPercent'];
        $endAt = $state['recovered']
            ? (string)$state['tradeEndAt']
            : ((string)$state['_latestAt'] !== '' ? (string)$state['_latestAt'] : (string)$state['tradeEndAt']);
        $startAt = (string)$state['_baselineAt'] !== '' ? (string)$state['_baselineAt'] : (string)$state['startAt'];
        $startEpoch = oppw_drawdown_epoch($startAt);
        $troughEpoch = oppw_drawdown_epoch($troughAt);
        $endEpoch = oppw_drawdown_epoch($endAt);
        $episodes[] = [
            'number' => (int)$state['number'],
            'startAt' => $startAt,
            'troughAt' => $troughAt,
            'endAt' => $endAt,
            'depthPercent' => $depthPercent,
            'recovered' => (bool)$state['recovered'],
            'elapsedSeconds' => $startEpoch !== null && $endEpoch !== null ? max(0, $endEpoch - $startEpoch) : 0,
            'recoverySeconds' => $state['recovered'] && $troughEpoch !== null && $endEpoch !== null
                ? max(0, $endEpoch - $troughEpoch)
                : null,
            'tradeKeys' => array_values($state['tradeKeys']),
            'troughSource' => $minuteRefined ? 'MINUTE_EQUITY' : 'CLOSED_TRADES',
        ];
    }
    return $episodes;
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
        'episodeCount' => 0, 'episodeMinimumSeconds' => OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS,
        'seriesDownsampled' => false, 'maxDrawdownPercent' => 0.0, 'maxDrawdownCurrency' => 0.0,
        'averageDepthPercent' => 0.0, 'averageLengthSeconds' => 0.0,
        'longestLengthSeconds' => 0, 'averageTroughRecoverySeconds' => 0.0,
        'timeUnderwaterPercent' => 0.0, 'ulcerIndexPercent' => 0.0,
        'series' => [], 'episodes' => [], 'tradeKeys' => [], 'episodeAuthority' => 'NONE',
        '_dailyEquity' => [], '_portfolioEntryFlowsByDay' => [], '_dailyDrawdownRows' => [],
        '_refinedTradeEpisodes' => [],
    ];
}

function oppw_drawdown_analyze(
    iterable $portfolioRows,
    array $cashFlows,
    int $seriesMaximum = OPPW_DRAWDOWN_SERIES_MAXIMUM,
    array $tradeEpisodeSeeds = []
): array {
    usort($cashFlows, static fn(array $left, array $right): int =>
        strcmp((string)($left['occurred_at'] ?? ''), (string)($right['occurred_at'] ?? ''))
    );

    $series = [];
    $episodes = [];
    $episodeCount = 0;
    $episodeDepthSum = 0.0;
    $episodeLengthSum = 0.0;
    $longestLengthSeconds = 0;
    $recoveryCount = 0;
    $recoverySum = 0.0;
    $underwaterSeconds = 0;
    $allTradeKeys = [];
    $sampleCount = 0;
    $minuteSampleCount = 0;
    $dailyFallbackSampleCount = 0;
    $underwaterSampleCount = 0;
    $dailyEquity = [];
    $dailyDrawdownByDay = [];
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
    $tradeEpisodeStates = oppw_prepare_trade_episode_states($tradeEpisodeSeeds);
    $tradeEpisodeStateIndex = 0;
    $previousAdjustedPoint = null;
    $recordEpisode = static function (array $episode) use (
        &$episodes,
        &$episodeDepthSum,
        &$episodeLengthSum,
        &$longestLengthSeconds,
        &$recoveryCount,
        &$recoverySum,
        &$underwaterSeconds
    ): void {
        $elapsedSeconds = (int)$episode['elapsedSeconds'];
        $episodeDepthSum += (float)$episode['depthPercent'];
        $episodeLengthSum += $elapsedSeconds;
        $longestLengthSeconds = max($longestLengthSeconds, $elapsedSeconds);
        $underwaterSeconds += $elapsedSeconds;
        if ($episode['recoverySeconds'] !== null) {
            $recoveryCount++;
            $recoverySum += (int)$episode['recoverySeconds'];
        }
        if ($elapsedSeconds >= OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS) $episodes[] = $episode;
    };

    foreach ($portfolioRows as $row) {
        $capturedAt = (string)($row['capturedAt'] ?? '');
        $capturedEpoch = oppw_drawdown_time_value($capturedAt);
        $equity = is_numeric($row['equity'] ?? null) ? (float)$row['equity'] : 0.0;
        if ($capturedAt === '' || $capturedEpoch === null || !is_finite($equity) || $equity <= 0.0) continue;

        $hasPreAdjustedValues = is_numeric($row['adjustedEquityIndex'] ?? null)
            && is_numeric($row['adjustedEquity'] ?? null);
        if ($hasPreAdjustedValues) {
            $equityIndex = (float)$row['adjustedEquityIndex'];
            $flowAdjustedEquity = (float)$row['adjustedEquity'];
        } elseif ($previousEquity === null) {
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
        $adjustedPoint = $point + [
            'adjustedEquityIndex' => $equityIndex,
            'adjustedEquity' => $flowAdjustedEquity,
            '_epoch' => $capturedEpoch,
        ];
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
                $dailyRow = [
                    'capturedAt' => $capturedAt,
                    'equity' => $equity,
                    'tradeKeys' => $point['tradeKeys'],
                    'sourceGranularity' => $point['sourceGranularity'],
                    'adjustedEquityIndex' => $equityIndex,
                    'adjustedEquity' => $flowAdjustedEquity,
                ];
                if (!isset($dailyDrawdownByDay[$day])) {
                    $dailyDrawdownByDay[$day] = ['first' => $dailyRow, 'low' => $dailyRow, 'close' => $dailyRow];
                } else {
                    if ((float)$equityIndex < (float)$dailyDrawdownByDay[$day]['low']['adjustedEquityIndex']) {
                        $dailyDrawdownByDay[$day]['low'] = $dailyRow;
                    }
                    $dailyDrawdownByDay[$day]['close'] = $dailyRow;
                }
                $entryFlow = (float)($row['accountEntryFlow'] ?? 0.0);
                if ($entryFlow !== 0.0) $portfolioEntryFlowsByDay[$day] = ($portfolioEntryFlowsByDay[$day] ?? 0.0) + $entryFlow;
            }
        } catch (Throwable) {
        }

        if ($tradeEpisodeStates) {
            oppw_update_trade_episode_states(
                $tradeEpisodeStates,
                $tradeEpisodeStateIndex,
                $previousAdjustedPoint,
                $adjustedPoint
            );
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
                $episodeCount++;
                $recordEpisode(oppw_close_drawdown_episode($activeEpisode, $point, true, $episodeCount));
                $activeEpisode = null;
            }
            $latestPeakPoint = $point;
        }

        $previousEpoch = $capturedEpoch;
        $previousEquity = $equity;
        $previousAdjustedPoint = $adjustedPoint;
    }

    if ($sampleCount === 0 || $firstPoint === null || $lastPoint === null) return oppw_empty_drawdown_result();
    if ($activeEpisode !== null) {
        $episodeCount++;
        $recordEpisode(oppw_close_drawdown_episode($activeEpisode, $lastPoint, false, $episodeCount));
    }

    $firstEpoch = oppw_drawdown_epoch((string)$firstPoint['capturedAt']);
    $lastEpoch = oppw_drawdown_epoch((string)$lastPoint['capturedAt']);
    $observedSeconds = $firstEpoch !== null && $lastEpoch !== null ? max(0, $lastEpoch - $firstEpoch) : 0;
    $timeUnderwaterPercent = $observedSeconds > 0
        ? min(100.0, $underwaterSeconds / $observedSeconds * 100.0)
        : ($underwaterSampleCount / $sampleCount * 100.0);
    $boundedSeries = oppw_downsample_drawdown_series($series, $seriesMaximum);
    $sourceGranularity = $minuteSampleCount > 0
        ? ($dailyFallbackSampleCount > 0 ? 'MINUTE_WITH_DAILY_FALLBACK' : 'MINUTE')
        : 'DAILY_FALLBACK';
    ksort($dailyDrawdownByDay);
    $dailyDrawdownRows = [];
    foreach ($dailyDrawdownByDay as $dayPoints) {
        $unique = [];
        foreach (['first', 'low', 'close'] as $kind) {
            $candidate = $dayPoints[$kind];
            $unique[(string)$candidate['capturedAt']] = $candidate;
        }
        uasort($unique, static fn(array $left, array $right): int =>
            strcmp((string)$left['capturedAt'], (string)$right['capturedAt'])
        );
        foreach ($unique as $candidate) $dailyDrawdownRows[] = $candidate;
    }

    return [
        'sourceGranularity' => $sourceGranularity,
        'cashFlowAdjusted' => true,
        'statisticsExact' => true,
        'sampleCount' => $sampleCount,
        'minuteSampleCount' => $minuteSampleCount,
        'dailyFallbackSampleCount' => $dailyFallbackSampleCount,
        'episodeCount' => $episodeCount,
        'episodeMinimumSeconds' => OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS,
        'seriesDownsampled' => count($boundedSeries) < $sampleCount,
        'maxDrawdownPercent' => abs($maximumDrawdownPercent),
        'maxDrawdownCurrency' => abs($maximumDrawdownCurrency),
        'averageDepthPercent' => $episodeCount > 0 ? $episodeDepthSum / $episodeCount : 0.0,
        'averageLengthSeconds' => $episodeCount > 0 ? $episodeLengthSum / $episodeCount : 0.0,
        'longestLengthSeconds' => $longestLengthSeconds,
        'averageTroughRecoverySeconds' => $recoveryCount > 0 ? $recoverySum / $recoveryCount : 0.0,
        'timeUnderwaterPercent' => $timeUnderwaterPercent,
        'ulcerIndexPercent' => sqrt($ulcerSquares / $sampleCount),
        'series' => $boundedSeries,
        'episodes' => $episodes,
        'tradeKeys' => array_keys($allTradeKeys),
        'episodeAuthority' => 'EQUITY_SERIES',
        '_dailyEquity' => $dailyEquity,
        '_portfolioEntryFlowsByDay' => $portfolioEntryFlowsByDay,
        '_dailyDrawdownRows' => $dailyDrawdownRows,
        '_refinedTradeEpisodes' => oppw_finalize_trade_episode_states($tradeEpisodeStates),
    ];
}

/**
 * Reduces the minute portfolio stream to the exact state consumed by the
 * daily-equity authority. Unlike oppw_drawdown_analyze(), this prepass does
 * not build and repeatedly downsample a minute chart or calculate minute
 * drawdown episodes that the daily result immediately discards.
 */
function oppw_reduce_daily_equity_history(
    iterable $portfolioRows,
    array $cashFlows,
    array $tradeEpisodeSeeds
): array {
    usort($cashFlows, static fn(array $left, array $right): int =>
        strcmp((string)($left['occurred_at'] ?? ''), (string)($right['occurred_at'] ?? ''))
    );
    foreach ($cashFlows as &$cashFlow) {
        $cashFlow['_sortAt'] = oppw_drawdown_iso((string)($cashFlow['occurred_at'] ?? ''));
    }
    unset($cashFlow);

    $dailyEquity = [];
    $dailyDrawdownByDay = [];
    $portfolioEntryFlowsByDay = [];
    $allTradeKeys = [];
    $minuteSampleCount = 0;
    $dailyFallbackSampleCount = 0;
    $flowIndex = 0;
    $flowCount = count($cashFlows);
    $previousSort = '';
    $previousEquity = null;
    $cumulativeExternalFlow = 0.0;
    $equityIndex = 100.0;
    $tradeEpisodeStates = oppw_prepare_trade_episode_states($tradeEpisodeSeeds);
    $tradeEpisodeStateIndex = 0;
    $previousAdjustedPoint = null;
    $utc = new DateTimeZone('UTC');
    $warsaw = new DateTimeZone('Europe/Warsaw');
    $currentDay = '';
    $currentWeekday = 0;
    $nextDaySort = '';

    foreach ($portfolioRows as $row) {
        $capturedAt = (string)($row['capturedAt'] ?? '');
        $equity = is_numeric($row['equity'] ?? null) ? (float)$row['equity'] : 0.0;
        if ($capturedAt === '' || !is_finite($equity) || $equity <= 0.0) continue;
        $capturedSort = oppw_drawdown_iso($capturedAt);
        if ($capturedSort === '') continue;

        $hasPreAdjustedValues = is_numeric($row['adjustedEquityIndex'] ?? null)
            && is_numeric($row['adjustedEquity'] ?? null);
        if ($hasPreAdjustedValues) {
            $equityIndex = (float)$row['adjustedEquityIndex'];
            $flowAdjustedEquity = (float)$row['adjustedEquity'];
        } elseif ($previousEquity === null) {
            $flowAdjustedEquity = $equity;
        } else {
            $externalFlow = (float)($row['accountEntryFlow'] ?? 0.0);
            while ($flowIndex < $flowCount) {
                $flowSort = (string)$cashFlows[$flowIndex]['_sortAt'];
                if ($flowSort === '' || $flowSort <= $previousSort) {
                    $flowIndex++;
                    continue;
                }
                if ($flowSort > $capturedSort) break;
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

        $tradeKeys = array_values(array_unique(array_filter($row['tradeKeys'] ?? [])));
        $sourceGranularity = (string)($row['sourceGranularity'] ?? 'MINUTE');
        foreach ($tradeKeys as $key) $allTradeKeys[$key] = true;
        if (str_contains($sourceGranularity, 'MINUTE')) $minuteSampleCount++;
        if (str_contains($sourceGranularity, 'DAILY_FALLBACK')) $dailyFallbackSampleCount++;

        $adjustedPoint = [
            'capturedAt' => $capturedAt,
            'equityIndex' => $equityIndex,
            'sourceGranularity' => $sourceGranularity,
            '_sortAt' => $capturedSort,
        ];
        if ($tradeEpisodeStates) {
            oppw_update_trade_episode_states_by_time(
                $tradeEpisodeStates,
                $tradeEpisodeStateIndex,
                $previousAdjustedPoint,
                $adjustedPoint
            );
        }

        if ($nextDaySort === '' || $capturedSort >= $nextDaySort) {
            try {
                $local = (new DateTimeImmutable($capturedAt, $utc))->setTimezone($warsaw);
                $currentDay = $local->format('Y-m-d');
                $currentWeekday = (int)$local->format('N');
                $nextDaySort = $local->modify('tomorrow')->setTime(0, 0, 0, 0)
                    ->setTimezone($utc)->format('Y-m-d\TH:i:s.u\Z');
            } catch (Throwable) {
                $currentDay = '';
                $currentWeekday = 0;
                $nextDaySort = '';
            }
        }
        if ($currentDay !== '' && $currentWeekday <= 5) {
            $dailyEquity[$currentDay] = $equity;
            $dailyRow = [
                'capturedAt' => $capturedAt,
                'equity' => $equity,
                'tradeKeys' => $tradeKeys,
                'sourceGranularity' => $sourceGranularity,
                'adjustedEquityIndex' => $equityIndex,
                'adjustedEquity' => $flowAdjustedEquity,
            ];
            if (!isset($dailyDrawdownByDay[$currentDay])) {
                $dailyDrawdownByDay[$currentDay] = ['first' => $dailyRow, 'low' => $dailyRow, 'close' => $dailyRow];
            } else {
                if ((float)$equityIndex < (float)$dailyDrawdownByDay[$currentDay]['low']['adjustedEquityIndex']) {
                    $dailyDrawdownByDay[$currentDay]['low'] = $dailyRow;
                }
                $dailyDrawdownByDay[$currentDay]['close'] = $dailyRow;
            }
            $entryFlow = (float)($row['accountEntryFlow'] ?? 0.0);
            if ($entryFlow !== 0.0) {
                $portfolioEntryFlowsByDay[$currentDay] = ($portfolioEntryFlowsByDay[$currentDay] ?? 0.0) + $entryFlow;
            }
        }

        $previousSort = $capturedSort;
        $previousEquity = $equity;
        $previousAdjustedPoint = $adjustedPoint;
    }

    ksort($dailyDrawdownByDay);
    $dailyRows = [];
    foreach ($dailyDrawdownByDay as $dayPoints) {
        $unique = [];
        foreach (['first', 'low', 'close'] as $kind) {
            $candidate = $dayPoints[$kind];
            $unique[(string)$candidate['capturedAt']] = $candidate;
        }
        uasort($unique, static fn(array $left, array $right): int =>
            strcmp((string)$left['capturedAt'], (string)$right['capturedAt'])
        );
        foreach ($unique as $candidate) $dailyRows[] = $candidate;
    }

    return [
        'dailyRows' => $dailyRows,
        'dailyEquity' => $dailyEquity,
        'portfolioEntryFlowsByDay' => $portfolioEntryFlowsByDay,
        'refinedTradeEpisodes' => oppw_finalize_trade_episode_states($tradeEpisodeStates),
        'minuteSampleCount' => $minuteSampleCount,
        'dailyFallbackSampleCount' => $dailyFallbackSampleCount,
        'tradeKeys' => array_keys($allTradeKeys),
    ];
}

/**
 * Portfolio risk uses a daily curve containing the first, lowest-minute and
 * closing equity point for each Warsaw weekday. Episode cards remain defined
 * by closed-trade returns and use the minute stream to refine the starting
 * equity sample, trough, and ongoing elapsed time.
 */
function oppw_daily_equity_drawdown_analyze(
    iterable $portfolioRows,
    array $cashFlows,
    array $closedTrades,
    int $seriesMaximum = OPPW_DRAWDOWN_SERIES_MAXIMUM
): array {
    $tradeEpisodeSeeds = oppw_closed_trade_drawdown_episode_seeds($closedTrades);
    $reduced = oppw_reduce_daily_equity_history($portfolioRows, $cashFlows, $tradeEpisodeSeeds);
    $dailyRows = $reduced['dailyRows'];
    if (!$dailyRows) {
        $empty = oppw_empty_drawdown_result();
        $empty['episodeAuthority'] = 'CLOSED_TRADES_WITH_MINUTE_EQUITY_REFINEMENT';
        $empty['_dailyEquity'] = $reduced['dailyEquity'];
        $empty['_portfolioEntryFlowsByDay'] = $reduced['portfolioEntryFlowsByDay'];
        unset($empty['_dailyDrawdownRows'], $empty['_refinedTradeEpisodes']);
        return $empty;
    }

    $dailyAnalysis = oppw_drawdown_analyze($dailyRows, [], $seriesMaximum);
    $refinedTradeEpisodes = $reduced['refinedTradeEpisodes'];
    $dailyAnalysis['episodes'] = array_values(array_filter(
        $refinedTradeEpisodes,
        static fn(array $episode): bool =>
            (int)$episode['elapsedSeconds'] >= OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS
    ));
    $dailyAnalysis['episodeCount'] = count($refinedTradeEpisodes);
    $dailyAnalysis['episodeMinimumSeconds'] = OPPW_DRAWDOWN_EPISODE_MINIMUM_SECONDS;
    $dailyAnalysis['episodeAuthority'] = 'CLOSED_TRADES_WITH_MINUTE_EQUITY_REFINEMENT';
    $dailyAnalysis['sourceGranularity'] = (int)$reduced['minuteSampleCount'] > 0
        ? ((int)$reduced['dailyFallbackSampleCount'] > 0
            ? 'DAILY_CLOSE_WITH_MINUTE_LOW_AND_DAILY_FALLBACK'
            : 'DAILY_CLOSE_WITH_MINUTE_LOW')
        : 'DAILY_FALLBACK';
    $dailyAnalysis['minuteSampleCount'] = (int)$reduced['minuteSampleCount'];
    $dailyAnalysis['dailyFallbackSampleCount'] = (int)$reduced['dailyFallbackSampleCount'];
    $dailyAnalysis['tradeKeys'] = $reduced['tradeKeys'];
    $dailyAnalysis['_dailyEquity'] = $reduced['dailyEquity'];
    $dailyAnalysis['_portfolioEntryFlowsByDay'] = $reduced['portfolioEntryFlowsByDay'];
    unset(
        $dailyAnalysis['_dailyDrawdownRows'],
        $dailyAnalysis['_refinedTradeEpisodes']
    );
    return $dailyAnalysis;
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
