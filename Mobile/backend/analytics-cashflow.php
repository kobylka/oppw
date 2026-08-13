<?php
declare(strict_types=1);

/**
 * Reduce authoritative cash-flow rows for analytics presentation.
 *
 * TAX is an accounting charge. It reduces after-tax performance, but it is
 * not investor capital and does not assert that broker equity moved. Actual
 * broker balance movements continue to be represented by TOP_UP,
 * WITHDRAWAL, or ADJUSTMENT rows.
 */
function oppw_analytics_cash_flow_summary(iterable $cashFlows, callable $dayResolver): array
{
    $initialByAccount = [];
    $topUps = 0.0;
    $withdrawals = 0.0;
    $taxes = 0.0;
    $cashByDay = [];

    foreach ($cashFlows as $row) {
        $key = (string)($row['strategy_key'] ?? '');
        $type = strtoupper((string)($row['flow_type'] ?? ''));
        $amount = is_numeric($row['amount'] ?? null) ? (float)$row['amount'] : 0.0;
        $day = (string)$dayResolver((string)($row['occurred_at'] ?? ''));

        if ($type === 'INITIAL' && !isset($initialByAccount[$key])) {
            $initialByAccount[$key] = abs($amount);
            continue;
        }
        if ($type === 'TOP_UP') {
            $value = abs($amount);
            $topUps += $value;
            $cashByDay[$day] = ($cashByDay[$day] ?? 0.0) + $value;
        } elseif ($type === 'WITHDRAWAL') {
            $value = abs($amount);
            $withdrawals += $value;
            $cashByDay[$day] = ($cashByDay[$day] ?? 0.0) - $value;
        } elseif ($type === 'TAX') {
            $taxes += abs($amount);
        } elseif ($type === 'ADJUSTMENT') {
            $cashByDay[$day] = ($cashByDay[$day] ?? 0.0) + $amount;
        }
    }

    return [
        'initialByAccount' => $initialByAccount,
        'topUps' => $topUps,
        'withdrawals' => $withdrawals,
        'taxes' => $taxes,
        'cashByDay' => $cashByDay,
    ];
}

function oppw_after_tax_performance(float $netProfit, float $taxes, float $netContributions): array
{
    $afterTaxNetProfit = $netProfit - abs($taxes);
    return [
        'afterTaxNetProfit' => $afterTaxNetProfit,
        'afterTaxCapitalAdjustedReturnPercent' => abs($netContributions) > 1.0e-15
            ? $afterTaxNetProfit / $netContributions * 100.0
            : 0.0,
    ];
}
