<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
$db = pdo();
$accountKey = trim((string)($_GET['account'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'account required'], 400);
require_mobile_session($accountKey);

$stmt = $db->prepare(
    'SELECT position_ticket, symbol, side, volume, opened_at, closed_at, open_price, close_price, profit, profit_percent,
            exit_reason, entry_slippage_points, exit_slippage_points, mfe_points, mfe_percent, mae_points, mae_percent,
            max_profit, max_drawdown, balance_before, balance_after
       FROM strategy_trades
      WHERE strategy_key = ?
      ORDER BY opened_at'
);
$stmt->execute([$accountKey]);
$rows = $stmt->fetchAll();
$closed = array_values(array_filter($rows, static fn(array $row): bool => $row['closed_at'] !== null));

$flowStmt = $db->prepare(
    "SELECT
        COALESCE(SUM(CASE WHEN flow_type = 'INITIAL' THEN amount ELSE 0 END), 0) AS initial_balance,
        COALESCE(SUM(CASE WHEN flow_type = 'TOP_UP' THEN ABS(amount) ELSE 0 END), 0) AS top_ups,
        COALESCE(SUM(CASE WHEN flow_type = 'WITHDRAWAL' THEN ABS(amount) ELSE 0 END), 0) AS withdrawals
       FROM account_cash_flows
      WHERE strategy_key = ?"
);
$flowStmt->execute([$accountKey]);
$flowRow = $flowStmt->fetch() ?: [];

$float = static fn(mixed $value): float => is_numeric($value) ? (float)$value : 0.0;
$profits = array_map(static fn(array $row): float => $float($row['profit']), $closed);
$wins = array_values(array_filter($profits, static fn(float $value): bool => $value > 0));
$losses = array_values(array_filter($profits, static fn(float $value): bool => $value < 0));
$sum = static fn(array $values): float => array_sum($values);
$avg = static fn(array $values): float => $values ? array_sum($values) / count($values) : 0.0;
$median = static function (array $values): float {
    if (!$values) return 0.0;
    sort($values, SORT_NUMERIC);
    $count = count($values);
    $middle = intdiv($count, 2);
    return $count % 2 ? (float)$values[$middle] : ((float)$values[$middle - 1] + (float)$values[$middle]) / 2.0;
};
$stddev = static function (array $values, float $mean): float {
    if (count($values) < 2) return 0.0;
    $variance = array_sum(array_map(static fn(float $value): float => ($value - $mean) ** 2, $values)) / (count($values) - 1);
    return sqrt(max(0.0, $variance));
};
$percentile = static function (array $values, float $probability): float {
    if (!$values) return 0.0;
    sort($values, SORT_NUMERIC);
    $position = max(0.0, min(1.0, $probability)) * (count($values) - 1);
    $lower = (int)floor($position);
    $upper = (int)ceil($position);
    if ($lower === $upper) return (float)$values[$lower];
    $weight = $position - $lower;
    return (float)$values[$lower] * (1.0 - $weight) + (float)$values[$upper] * $weight;
};
$duration = static function (array $row): int {
    if ($row['closed_at'] === null) return 0;
    return max(0, (new DateTimeImmutable((string)$row['closed_at'], new DateTimeZone('UTC')))->getTimestamp() - (new DateTimeImmutable((string)$row['opened_at'], new DateTimeZone('UTC')))->getTimestamp());
};

$netProfit = $sum($profits);
$grossProfit = $sum($wins);
$grossLoss = abs($sum($losses));
$avgWin = $avg($wins);
$avgLoss = $avg($losses);
$mean = $avg($profits);
$deviation = $stddev($profits, $mean);
$durations = array_map($duration, $closed);
$mfe = array_map(static fn(array $row): float => $float($row['mfe_points']), $closed);
$mae = array_map(static fn(array $row): float => abs($float($row['mae_points'])), $closed);
$entrySlip = array_map(static fn(array $row): float => $float($row['entry_slippage_points']), $closed);
$exitSlip = array_map(static fn(array $row): float => $float($row['exit_slippage_points']), $closed);
$initialBalance = $float($flowRow['initial_balance'] ?? 0);
$topUps = $float($flowRow['top_ups'] ?? 0);
$withdrawals = $float($flowRow['withdrawals'] ?? 0);
$capitalBase = $initialBalance + $topUps;
$netContributions = $capitalBase - $withdrawals;
$totalSlippagePoints = $sum($entrySlip) + $sum($exitSlip);

// Daily capital-adjusted returns for risk metrics. External cash flows are removed
// from the corresponding day's equity change so deposits and withdrawals do not
// masquerade as strategy performance.
$dailyEquityStmt = $db->prepare(
    'SELECT p.captured_minute, p.equity
       FROM strategy_equity_points p
       JOIN (
            SELECT DATE(captured_minute) AS day_key, MAX(captured_minute) AS last_time
              FROM strategy_equity_points
             WHERE strategy_key = ?
             GROUP BY DATE(captured_minute)
       ) daily ON daily.last_time = p.captured_minute
      WHERE p.strategy_key = ?
      ORDER BY p.captured_minute'
);
$dailyEquityStmt->execute([$accountKey, $accountKey]);
$dailyEquityRows = $dailyEquityStmt->fetchAll();
$dailyFlowStmt = $db->prepare("SELECT occurred_at, flow_type, amount FROM account_cash_flows WHERE strategy_key = ? AND flow_type <> 'INITIAL' ORDER BY occurred_at, id");
$dailyFlowStmt->execute([$accountKey]);
$flowsByDay = [];
foreach ($dailyFlowStmt->fetchAll() as $flow) {
    $day = substr((string)$flow['occurred_at'], 0, 10);
    $type = strtoupper((string)$flow['flow_type']);
    $amount = (float)$flow['amount'];
    $signed = $type === 'TOP_UP' ? abs($amount) : ($type === 'WITHDRAWAL' ? -abs($amount) : $amount);
    $flowsByDay[$day] = ($flowsByDay[$day] ?? 0.0) + $signed;
}
$dailyReturns = [];
$previousEquity = null;
foreach ($dailyEquityRows as $dailyRow) {
    $equityValue = (float)$dailyRow['equity'];
    $day = substr((string)$dailyRow['captured_minute'], 0, 10);
    if ($previousEquity !== null && $previousEquity > 0) {
        $adjustedClosingEquity = $equityValue - ($flowsByDay[$day] ?? 0.0);
        $dailyReturns[] = $adjustedClosingEquity / $previousEquity - 1.0;
    }
    $previousEquity = $equityValue;
}
$dailyMean = $avg($dailyReturns);
$dailyDeviation = $stddev($dailyReturns, $dailyMean);
$downsideSquares = array_map(static fn(float $value): float => min(0.0, $value) ** 2, $dailyReturns);
$downsideDeviation = $downsideSquares ? sqrt(array_sum($downsideSquares) / count($downsideSquares)) : 0.0;
$sharpeRatio = $dailyDeviation > 0 ? $dailyMean / $dailyDeviation * sqrt(252.0) : 0.0;
$sortinoRatio = $downsideDeviation > 0 ? $dailyMean / $downsideDeviation * sqrt(252.0) : 0.0;
$positiveReturnSum = array_sum(array_filter($dailyReturns, static fn(float $value): bool => $value > 0));
$negativeReturnSum = abs(array_sum(array_filter($dailyReturns, static fn(float $value): bool => $value < 0)));
$omegaRatio = $negativeReturnSum > 0 ? $positiveReturnSum / $negativeReturnSum : 0.0;
$growthIndex = 1.0;
$growthPeak = 1.0;
$drawdownPercents = [];
foreach ($dailyReturns as $returnValue) {
    $growthIndex *= max(0.000001, 1.0 + $returnValue);
    $growthPeak = max($growthPeak, $growthIndex);
    $drawdownPercents[] = $growthPeak > 0 ? ($growthPeak - $growthIndex) / $growthPeak * 100.0 : 0.0;
}
$maxDrawdownPercent = $drawdownPercents ? max($drawdownPercents) : 0.0;
$ulcerIndexPercent = $drawdownPercents ? sqrt(array_sum(array_map(static fn(float $value): float => $value ** 2, $drawdownPercents)) / count($drawdownPercents)) : 0.0;
$annualizedReturn = $dailyReturns && $growthIndex > 0 ? pow($growthIndex, 252.0 / count($dailyReturns)) - 1.0 : 0.0;
$calmarRatio = $maxDrawdownPercent > 0 ? ($annualizedReturn * 100.0) / $maxDrawdownPercent : 0.0;
$varThreshold = $percentile($dailyReturns, 0.05);
$tailReturns = array_values(array_filter($dailyReturns, static fn(float $value): bool => $value <= $varThreshold));
$valueAtRisk95Percent = max(0.0, -$varThreshold * 100.0);
$expectedShortfall95Percent = $tailReturns ? max(0.0, -$avg($tailReturns) * 100.0) : 0.0;

$peak = 0.0;
$curve = 0.0;
$maxDrawdown = 0.0;
$winStreak = $lossStreak = $maxWinStreak = $maxLossStreak = 0;
foreach ($profits as $profit) {
    $curve += $profit;
    $peak = max($peak, $curve);
    $maxDrawdown = max($maxDrawdown, $peak - $curve);
    if ($profit > 0) {
        $winStreak++;
        $lossStreak = 0;
        $maxWinStreak = max($maxWinStreak, $winStreak);
    } elseif ($profit < 0) {
        $lossStreak++;
        $winStreak = 0;
        $maxLossStreak = max($maxLossStreak, $lossStreak);
    }
}

$firstOpen = $rows ? new DateTimeImmutable((string)$rows[0]['opened_at'], new DateTimeZone('UTC')) : null;
$lastTime = $rows ? new DateTimeImmutable((string)(end($rows)['closed_at'] ?: end($rows)['opened_at']), new DateTimeZone('UTC')) : null;
$totalSpan = $firstOpen && $lastTime ? max(1, $lastTime->getTimestamp() - $firstOpen->getTimestamp()) : 1;
$timeInMarket = min(100.0, array_sum($durations) / $totalSpan * 100.0);
$realizedPoints = array_map(static fn(array $row): float => $float($row['close_price']) - $float($row['open_price']), $closed);
$positiveMfe = array_values(array_filter($mfe, static fn(float $value): bool => $value > 0));
$captureEfficiency = $sum($positiveMfe) > 0 ? $sum($realizedPoints) / $sum($positiveMfe) * 100.0 : 0.0;
$edgeRatio = $avg($mae) > 0 ? $avg($mfe) / $avg($mae) : 0.0;
$consistencyScore = $deviation > 0 ? $mean / $deviation * sqrt(max(1, count($profits))) : 0.0;

$exitReasons = [];
$weekly = [];
foreach ($closed as $row) {
    $reason = trim((string)$row['exit_reason']) ?: 'UNKNOWN';
    if (!isset($exitReasons[$reason])) $exitReasons[$reason] = ['reason' => $reason, 'trades' => 0, 'wins' => 0, 'profit' => 0.0, 'mfe' => 0.0, 'mae' => 0.0];
    $exitReasons[$reason]['trades']++;
    $exitReasons[$reason]['wins'] += $float($row['profit']) > 0 ? 1 : 0;
    $exitReasons[$reason]['profit'] += $float($row['profit']);
    $exitReasons[$reason]['mfe'] += $float($row['mfe_points']);
    $exitReasons[$reason]['mae'] += abs($float($row['mae_points']));

    $opened = new DateTimeImmutable((string)$row['opened_at'], new DateTimeZone('UTC'));
    $weekKey = $opened->format('o-\WW');
    if (!isset($weekly[$weekKey])) $weekly[$weekKey] = ['week' => $weekKey, 'trades' => 0, 'wins' => 0, 'profit' => 0.0, 'best' => null, 'worst' => null, 'duration' => 0];
    $profit = $float($row['profit']);
    $weekly[$weekKey]['trades']++;
    $weekly[$weekKey]['wins'] += $profit > 0 ? 1 : 0;
    $weekly[$weekKey]['profit'] += $profit;
    $weekly[$weekKey]['best'] = $weekly[$weekKey]['best'] === null ? $profit : max($weekly[$weekKey]['best'], $profit);
    $weekly[$weekKey]['worst'] = $weekly[$weekKey]['worst'] === null ? $profit : min($weekly[$weekKey]['worst'], $profit);
    $weekly[$weekKey]['duration'] += $duration($row);
}

$exitReasonRows = array_values(array_map(static function (array $item): array {
    $count = max(1, (int)$item['trades']);
    return [
        'reason' => $item['reason'],
        'trades' => $item['trades'],
        'winRate' => $item['wins'] / $count * 100.0,
        'profit' => $item['profit'],
        'averageProfit' => $item['profit'] / $count,
        'averageMfePoints' => $item['mfe'] / $count,
        'averageMaePoints' => $item['mae'] / $count,
    ];
}, $exitReasons));
usort($exitReasonRows, static fn(array $a, array $b): int => $b['profit'] <=> $a['profit']);

$weeklyRows = array_values(array_map(static function (array $item): array {
    $count = max(1, (int)$item['trades']);
    return [
        'week' => $item['week'],
        'trades' => $item['trades'],
        'winRate' => $item['wins'] / $count * 100.0,
        'profit' => $item['profit'],
        'bestTrade' => $item['best'] ?? 0.0,
        'worstTrade' => $item['worst'] ?? 0.0,
        'averageDurationSeconds' => $item['duration'] / $count,
    ];
}, $weekly));
usort($weeklyRows, static fn(array $a, array $b): int => strcmp($b['week'], $a['week']));
$weeklyProfits = array_map(static fn(array $item): float => (float)$item['profit'], $weeklyRows);
$positiveWeeks = count(array_filter($weeklyProfits, static fn(float $value): bool => $value > 0));
$positiveWeeksPercent = $weeklyProfits ? $positiveWeeks / count($weeklyProfits) * 100.0 : 0.0;
$averageWeeklyProfit = $avg($weeklyProfits);

$recent = array_reverse(array_slice($rows, -100));
$recentRows = array_map(static function (array $row) use ($float, $duration): array {
    return [
        'ticket' => (int)$row['position_ticket'],
        'symbol' => (string)$row['symbol'],
        'side' => (string)$row['side'],
        'volume' => $float($row['volume']),
        'openedAt' => atom_datetime(new DateTimeImmutable((string)$row['opened_at'], new DateTimeZone('UTC'))),
        'closedAt' => $row['closed_at'] ? atom_datetime(new DateTimeImmutable((string)$row['closed_at'], new DateTimeZone('UTC'))) : '',
        'openPrice' => $float($row['open_price']),
        'closePrice' => $float($row['close_price']),
        'profit' => $float($row['profit']),
        'profitPercent' => $float($row['profit_percent']),
        'exitReason' => (string)$row['exit_reason'],
        'durationSeconds' => $duration($row),
        'mfePoints' => $float($row['mfe_points']),
        'maePoints' => $float($row['mae_points']),
        'entrySlippagePoints' => $float($row['entry_slippage_points']),
        'exitSlippagePoints' => $float($row['exit_slippage_points']),
        'maxProfit' => $float($row['max_profit']),
        'maxDrawdown' => $float($row['max_drawdown']),
        'closed' => $row['closed_at'] !== null,
    ];
}, $recent);

json_response([
    'ok' => true,
    'generatedAt' => atom_datetime(utc_now()),
    'summary' => [
        'totalTrades' => count($rows),
        'closedTrades' => count($closed),
        'openTrades' => count($rows) - count($closed),
        'wins' => count($wins),
        'losses' => count($losses),
        'winRate' => $closed ? count($wins) / count($closed) * 100.0 : 0.0,
        'netProfit' => $netProfit,
        'initialBalance' => $initialBalance,
        'topUps' => $topUps,
        'withdrawals' => $withdrawals,
        'netContributions' => $netContributions,
        'capitalAdjustedReturnPercent' => $capitalBase > 0 ? $netProfit / $capitalBase * 100.0 : 0.0,
        'positiveWeeksPercent' => $positiveWeeksPercent,
        'averageWeeklyProfit' => $averageWeeklyProfit,
        'totalSlippagePoints' => $totalSlippagePoints,
        'grossProfit' => $grossProfit,
        'grossLoss' => $grossLoss,
        'profitFactor' => $grossLoss > 0 ? $grossProfit / $grossLoss : 0.0,
        'expectancy' => $mean,
        'medianProfit' => $median($profits),
        'averageWin' => $avgWin,
        'averageLoss' => $avgLoss,
        'payoffRatio' => abs($avgLoss) > 0 ? $avgWin / abs($avgLoss) : 0.0,
        'averageDurationSeconds' => $avg($durations),
        'averageMfePoints' => $avg($mfe),
        'averageMaePoints' => $avg($mae),
        'averageEntrySlippagePoints' => $avg($entrySlip),
        'averageExitSlippagePoints' => $avg($exitSlip),
        'captureEfficiencyPercent' => $captureEfficiency,
        'edgeRatio' => $edgeRatio,
        'maxDrawdown' => $maxDrawdown,
        'recoveryFactor' => $maxDrawdown > 0 ? $netProfit / $maxDrawdown : 0.0,
        'consistencyScore' => $consistencyScore,
        'maxWinStreak' => $maxWinStreak,
        'maxLossStreak' => $maxLossStreak,
        'timeInMarketPercent' => $timeInMarket,
        'bestTrade' => $profits ? max($profits) : 0.0,
        'worstTrade' => $profits ? min($profits) : 0.0,
        'sharpeRatio' => $sharpeRatio,
        'sortinoRatio' => $sortinoRatio,
        'calmarRatio' => $calmarRatio,
        'omegaRatio' => $omegaRatio,
        'ulcerIndexPercent' => $ulcerIndexPercent,
        'valueAtRisk95Percent' => $valueAtRisk95Percent,
        'expectedShortfall95Percent' => $expectedShortfall95Percent,
        'riskSampleDays' => count($dailyReturns),
    ],
    'exitReasons' => $exitReasonRows,
    'weekly' => array_slice($weeklyRows, 0, 52),
    'recentTrades' => $recentRows,
]);
