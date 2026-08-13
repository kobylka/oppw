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
$trade = static fn(int $ticket, string $openedAt, string $closedAt, float $return): array => [
    'strategyKey' => 'DEMO',
    'ticket' => $ticket,
    'openedAt' => $openedAt,
    'closedAt' => $closedAt,
    'tradeReturn' => $return,
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
if ($intraday['episodeCount'] !== 2 || count($intraday['episodes']) !== 0) {
    throw new RuntimeException('short drawdowns were not counted exactly and omitted from the response');
}
$assertClose((10.0 + 100.0 / 21.0) / 2.0, $intraday['averageDepthPercent'], 'all-episode average depth');
$assertClose(90.0, $intraday['averageLengthSeconds'], 'all-episode average length');
$assertClose(60.0, $intraday['averageTroughRecoverySeconds'], 'all-episode average recovery');
if ($intraday['longestLengthSeconds'] !== 120 || $intraday['episodeMinimumSeconds'] !== 86400) {
    throw new RuntimeException('short episodes stopped contributing to exact aggregate metrics');
}

$minimumDuration = oppw_drawdown_analyze([
    $row('2026-07-25T00:00:00Z', 100.0),
    $row('2026-07-25T01:00:00Z', 90.0, 11),
    $row('2026-07-26T00:00:00Z', 100.0),
    $row('2026-07-26T01:00:00Z', 100.0),
    $row('2026-07-26T02:00:00Z', 90.0, 12),
    $row('2026-07-26T03:00:00Z', 100.0),
], []);
if ($minimumDuration['episodeCount'] !== 2 || count($minimumDuration['episodes']) !== 1) {
    throw new RuntimeException('drawdown response did not retain only episodes lasting at least 24 hours');
}
$visibleEpisode = $minimumDuration['episodes'][0];
if ($visibleEpisode['elapsedSeconds'] !== 86400 || !$visibleEpisode['recovered'] || $visibleEpisode['recoverySeconds'] !== 82800) {
    throw new RuntimeException('the inclusive 24-hour drawdown boundary was not preserved exactly');
}
if ($visibleEpisode['troughAt'] !== '2026-07-25T01:00:00Z' || $visibleEpisode['tradeKeys'] !== ['DEMO:11']) {
    throw new RuntimeException('visible drawdown timing or trade links were lost');
}

$dailyHybrid = oppw_daily_equity_drawdown_analyze([
    $row('2026-07-20T09:00:00Z', 100.0),
    $row('2026-07-20T11:00:00Z', 110.0, 1),
    $row('2026-07-20T13:00:00Z', 110.0),
    $row('2026-07-21T09:00:00Z', 110.0),
    $row('2026-07-21T10:00:00Z', 200.0),
    $row('2026-07-21T11:00:00Z', 80.0, 2),
    $row('2026-07-21T21:00:00Z', 110.0),
    $row('2026-07-23T12:00:00Z', 120.0, 3),
], [], [
    $trade(1, '2026-07-20T10:00:00Z', '2026-07-20T12:00:00Z', 0.10),
    $trade(2, '2026-07-21T10:00:00Z', '2026-07-22T12:00:00Z', -0.10),
    $trade(3, '2026-07-23T10:00:00Z', '2026-07-23T12:00:00Z', 0.20),
]);
$assertClose((1.0 - 80.0 / 110.0) * 100.0, $dailyHybrid['maxDrawdownPercent'], 'daily curve with minute low');
$assertClose(30.0, $dailyHybrid['maxDrawdownCurrency'], 'daily currency drawdown with minute low');
if ($dailyHybrid['sourceGranularity'] !== 'DAILY_CLOSE_WITH_MINUTE_LOW'
    || $dailyHybrid['sampleCount'] !== 6
    || $dailyHybrid['minuteSampleCount'] !== 8) {
    throw new RuntimeException('daily first/low/close curve did not retain its raw minute provenance');
}
if (count(array_filter($dailyHybrid['series'], static fn(array $point): bool => (float)$point['equity'] === 200.0)) !== 0) {
    throw new RuntimeException('intraday highs incorrectly changed the daily drawdown curve');
}
if ($dailyHybrid['episodeAuthority'] !== 'CLOSED_TRADES_WITH_MINUTE_EQUITY_REFINEMENT'
    || $dailyHybrid['episodeCount'] !== 1
    || count($dailyHybrid['episodes']) !== 1) {
    throw new RuntimeException('episode cards were not defined by closed-trade drawdowns');
}
$tradeEpisode = $dailyHybrid['episodes'][0];
$assertClose(60.0, $tradeEpisode['depthPercent'], 'minute-refined trade drawdown depth');
if ($tradeEpisode['troughAt'] !== '2026-07-21T11:00:00Z'
    || $tradeEpisode['troughSource'] !== 'MINUTE_EQUITY'
    || $tradeEpisode['startAt'] !== '2026-07-21T10:00:00Z'
    || $tradeEpisode['elapsedSeconds'] !== 180000
    || $tradeEpisode['recoverySeconds'] !== 176400
    || $tradeEpisode['tradeKeys'] !== ['DEMO:1', 'DEMO:2', 'DEMO:3']) {
    throw new RuntimeException('minute trough and timing did not refine the closed-trade episode');
}

$ongoingTradeDrawdown = oppw_daily_equity_drawdown_analyze([
    $row('2026-07-20T12:00:00Z', 110.0, 21),
    $row('2026-07-21T12:00:00Z', 99.0, 22),
    $row('2026-07-24T12:00:00Z', 80.0, 22),
], [], [
    $trade(21, '2026-07-20T10:00:00Z', '2026-07-20T12:00:00Z', 0.10),
    $trade(22, '2026-07-21T10:00:00Z', '2026-07-21T12:00:00Z', -0.10),
]);
$ongoingEpisode = $ongoingTradeDrawdown['episodes'][0];
if ($ongoingEpisode['recovered']
    || $ongoingEpisode['endAt'] !== '2026-07-24T12:00:00Z'
    || $ongoingEpisode['startAt'] !== '2026-07-21T10:00:00Z'
    || $ongoingEpisode['elapsedSeconds'] !== 266400
    || $ongoingEpisode['recoverySeconds'] !== null
    || $ongoingEpisode['troughSource'] !== 'MINUTE_EQUITY') {
    throw new RuntimeException('ongoing closed-trade drawdown did not extend to the latest minute-equity point');
}

$lateMinuteHistory = oppw_daily_equity_drawdown_analyze([
    $row('2026-05-10T22:00:00Z', 110.0, 42),
    $row('2026-05-11T13:30:00Z', 110.0, 42),
    $row('2026-05-12T20:00:00Z', 90.0, 42),
    $row('2026-05-14T20:00:00Z', 80.0, 42),
], [], [
    $trade(41, '2026-05-04T13:30:00Z', '2026-05-08T20:00:00Z', 0.10),
    $trade(42, '2026-05-11T13:30:00Z', '2026-05-12T20:00:00Z', -0.10),
]);
$lateMinuteEpisode = $lateMinuteHistory['episodes'][0];
if ($lateMinuteEpisode['startAt'] !== '2026-05-11T13:30:00Z'
    || $lateMinuteEpisode['endAt'] !== '2026-05-14T20:00:00Z'
    || $lateMinuteEpisode['elapsedSeconds'] !== 282600
    || $lateMinuteEpisode['troughSource'] !== 'MINUTE_EQUITY') {
    throw new RuntimeException('drawdown did not start when its first losing trade opened');
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
$assertClose(0.0, oppw_external_flow_amount(['flow_type' => 'TAX', 'amount' => -25.0]), 'tax accounting entry drawdown adjustment');

$equivalenceRows = [
    $row('2026-03-27T08:00:00Z', 100.0, 31),
    $row('2026-03-27T09:00:00Z', 150.0, 31),
    $row('2026-03-27T10:00:00Z', 130.0),
    $row('2026-03-28T10:00:00Z', 120.0, 32),
    array_replace($row('2026-03-30T08:00:00Z', 310.0, 32), ['accountEntryFlow' => 200.0]),
    array_replace($row('2026-03-30T20:00:00Z', 115.0), ['sourceGranularity' => 'DAILY_FALLBACK']),
];
$equivalenceFlows = [
    ['occurred_at' => '2026-03-27T09:00:00Z', 'flow_type' => 'TOP_UP', 'amount' => 50.0],
];
$equivalenceTrades = [
    $trade(31, '2026-03-27T07:00:00Z', '2026-03-27T08:30:00Z', 0.10),
    $trade(32, '2026-03-30T07:00:00Z', '2026-03-30T08:30:00Z', -0.20),
];
$equivalenceSeeds = oppw_closed_trade_drawdown_episode_seeds($equivalenceTrades);
$legacyReduction = oppw_drawdown_analyze($equivalenceRows, $equivalenceFlows, 2000, $equivalenceSeeds);
$optimizedReduction = oppw_reduce_daily_equity_history($equivalenceRows, $equivalenceFlows, $equivalenceSeeds);
$legacyComparable = [
    'dailyRows' => $legacyReduction['_dailyDrawdownRows'],
    'dailyEquity' => $legacyReduction['_dailyEquity'],
    'portfolioEntryFlowsByDay' => $legacyReduction['_portfolioEntryFlowsByDay'],
    'refinedTradeEpisodes' => $legacyReduction['_refinedTradeEpisodes'],
    'minuteSampleCount' => $legacyReduction['minuteSampleCount'],
    'dailyFallbackSampleCount' => $legacyReduction['dailyFallbackSampleCount'],
    'tradeKeys' => $legacyReduction['tradeKeys'],
];
if ($optimizedReduction !== $legacyComparable) {
    throw new RuntimeException('optimized daily reduction changed the canonical minute-derived state');
}

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

echo "ANALYTICS DRAWDOWN TESTS PASSED cases=11\n";
