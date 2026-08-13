<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/analytics-cashflow.php';

$assertClose = static function (float $expected, float $actual, string $label): void {
    if (abs($expected - $actual) > 1.0e-9) throw new RuntimeException("$label expected $expected, got $actual");
};
$rows = [
    ['strategy_key' => 'DEMO', 'occurred_at' => '2026-01-01T10:00:00Z', 'flow_type' => 'INITIAL', 'amount' => 1000.0],
    ['strategy_key' => 'DEMO', 'occurred_at' => '2026-01-02T10:00:00Z', 'flow_type' => 'TOP_UP', 'amount' => 200.0],
    ['strategy_key' => 'DEMO', 'occurred_at' => '2026-01-03T10:00:00Z', 'flow_type' => 'WITHDRAWAL', 'amount' => -50.0],
    ['strategy_key' => 'DEMO', 'occurred_at' => '2026-01-04T10:00:00Z', 'flow_type' => 'TAX', 'amount' => -25.0],
];
$summary = oppw_analytics_cash_flow_summary($rows, static fn(string $value): string => substr($value, 0, 10));
$assertClose(1000.0, array_sum($summary['initialByAccount']), 'initial balance');
$assertClose(200.0, $summary['topUps'], 'top-ups');
$assertClose(50.0, $summary['withdrawals'], 'withdrawals');
$assertClose(25.0, $summary['taxes'], 'taxes');
if (array_key_exists('2026-01-04', $summary['cashByDay'])) {
    throw new RuntimeException('accounting-only tax changed the broker-equity cash-flow adjustment');
}
$performance = oppw_after_tax_performance(100.0, $summary['taxes'], 1150.0);
$assertClose(75.0, $performance['afterTaxNetProfit'], 'after-tax net profit');
$assertClose(75.0 / 1150.0 * 100.0, $performance['afterTaxCapitalAdjustedReturnPercent'], 'after-tax return');

echo "ANALYTICS CASH-FLOW TESTS PASSED cases=1\n";
