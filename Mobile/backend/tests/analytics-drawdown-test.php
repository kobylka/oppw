<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/analytics-drawdown.php';

$assertClose = static function (float $expected, float $actual, string $label, float $epsilon = 1.0e-9): void {
    if (abs($expected - $actual) > $epsilon) {
        throw new RuntimeException("$label expected $expected, got $actual");
    }
};
$row = static fn(string $time, float $equity, ?int $ticket = null): array => [
    'capturedAt' => $time,
    'equity' => $equity,
    'tradeKeys' => $ticket === null ? [] : ['DEMO:' . $ticket],
    'sourceGranularity' => 'MINUTE',
];

$intraday = oppw_drawdown_analyze([
    $row('2026-07-27T10:00:00Z', 100.0, 1),
    $row('2026-07-27T10:01:00Z', 90.0, 1),
    $row('2026-07-27T10:02:00Z', 105.0, 1),
    $row('2026-07-27T10:03:00Z', 100.0, 2),
], []);
$assertClose(10.0, $intraday['maxDrawdownPercent'], 'minute maximum drawdown');
$assertClose(10.0, $intraday['maxDrawdownCurrency'], 'minute maximum drawdown currency');
$assertClose(sqrt((100.0 + (100.0 / 21.0) ** 2) / 4.0), $intraday['ulcerIndexPercent'], 'minute ulcer index');
if ($intraday['sampleCount'] !== 4 || $intraday['minuteSampleCount'] !== 4) {
    throw new RuntimeException('minute samples were not used as the drawdown authority');
}
if (count($intraday['episodes']) !== 2) throw new RuntimeException('expected recovered and ongoing minute drawdowns');
$first = $intraday['episodes'][0];
if (!$first['recovered'] || $first['elapsedSeconds'] !== 120 || $first['recoverySeconds'] !== 60) {
    throw new RuntimeException('minute episode timing was not reconstructed exactly');
}
if ($first['troughAt'] !== '2026-07-27T10:01:00Z') throw new RuntimeException('minute trough timestamp was lost');
if ($intraday['episodes'][1]['recovered'] || $intraday['episodes'][1]['elapsedSeconds'] !== 60) {
    throw new RuntimeException('ongoing minute drawdown was not measured to the latest sample');
}

$cashFlowAdjusted = oppw_drawdown_analyze([
    $row('2026-07-27T10:00:00Z', 100.0),
    $row('2026-07-27T10:01:00Z', 150.0),
    $row('2026-07-27T10:02:00Z', 120.0),
    $row('2026-07-27T10:03:00Z', 108.0),
], [
    ['occurred_at' => '2026-07-27T10:01:00Z', 'flow_type' => 'TOP_UP', 'amount' => 50.0],
    ['occurred_at' => '2026-07-27T10:02:00Z', 'flow_type' => 'WITHDRAWAL', 'amount' => -30.0],
]);
$assertClose(10.0, $cashFlowAdjusted['maxDrawdownPercent'], 'cash-flow-adjusted drawdown percent');
$assertClose(12.0, $cashFlowAdjusted['maxDrawdownCurrency'], 'cash-flow-adjusted drawdown currency');

$portfolio = iterator_to_array(oppw_portfolio_equity_rows([
    ['strategy_key' => 'REAL', 'captured_minute' => '2026-07-27 10:00:00', 'equity' => 200.0, 'position_ticket' => null, 'source_granularity' => 'MINUTE'],
    ['strategy_key' => 'DEMO', 'captured_minute' => '2026-07-27 10:00:00', 'equity' => 100.0, 'position_ticket' => 7, 'source_granularity' => 'MINUTE'],
    ['strategy_key' => 'DEMO', 'captured_minute' => '2026-07-27 10:01:00', 'equity' => 90.0, 'position_ticket' => 7, 'source_granularity' => 'MINUTE'],
]));
$assertClose(300.0, $portfolio[0]['equity'], 'same-minute account portfolio aggregation');
$assertClose(290.0, $portfolio[1]['equity'], 'stale account carry-forward');
if ($portfolio[0]['tradeKeys'] !== ['DEMO:7']) throw new RuntimeException('portfolio minute trade keys were not retained');

$joiningAccount = iterator_to_array(oppw_portfolio_equity_rows([
    ['strategy_key' => 'DEMO', 'captured_minute' => '2026-07-27 10:00:00', 'equity' => 100.0, 'position_ticket' => null, 'source_granularity' => 'MINUTE'],
    ['strategy_key' => 'REAL', 'captured_minute' => '2026-07-27 10:01:00', 'equity' => 200.0, 'position_ticket' => null, 'source_granularity' => 'MINUTE'],
]));
$joiningAnalysis = oppw_drawdown_analyze($joiningAccount, []);
$assertClose(100.0, $joiningAnalysis['series'][1]['equityIndex'], 'new account capital excluded from portfolio return');

$mixedHistory = iterator_to_array(oppw_portfolio_equity_rows([
    ['strategy_key' => 'DEMO', 'captured_minute' => '2025-01-01 21:00:00', 'equity' => 100.0, 'position_ticket' => null, 'source_granularity' => 'DAILY_FALLBACK'],
    ['strategy_key' => 'REAL', 'captured_minute' => '2025-01-01 21:01:00', 'equity' => 200.0, 'position_ticket' => null, 'source_granularity' => 'MINUTE'],
]));
if ($mixedHistory[1]['sourceGranularity'] !== 'MINUTE_WITH_DAILY_FALLBACK') {
    throw new RuntimeException('carried-forward daily history lost its fallback label');
}

$bounded = oppw_drawdown_analyze(array_map(
    static fn(int $minute): array => $row(sprintf('2026-07-27T10:%02d:00Z', $minute), 100.0 - ($minute % 3)),
    range(0, 9),
), [], 6);
if (!$bounded['seriesDownsampled'] || count($bounded['series']) > 6) {
    throw new RuntimeException('drawdown chart series was not bounded');
}

echo "ANALYTICS DRAWDOWN TESTS PASSED cases=4\n";
