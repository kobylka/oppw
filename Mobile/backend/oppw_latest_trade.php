<?php

declare(strict_types=1);

require_once __DIR__ . '/lib.php';

/*
 * v45.3.1
 *
 * One canonical file is used both as:
 *   1. the MT5 writer-token endpoint; and
 *   2. the library included by status.php.
 *
 * This helper deliberately reads only strategy_trades. The earlier event-history
 * recovery query was optional metadata enrichment, but an SQL/runtime failure in
 * that query could corrupt status.php with an HTML PHP error before its JSON body.
 */
function oppw_authoritative_last_trade(PDO $db, string $accountKey): ?array
{
    $stmt = $db->prepare(
        'SELECT id, position_ticket, symbol, side, volume, opened_at, closed_at,
                open_price, close_price, profit, profit_percent, exit_reason,
                balance_before, balance_after, preleverage_return_percent, trade_class
         FROM strategy_trades
         WHERE strategy_key = ? AND closed_at IS NOT NULL
         ORDER BY closed_at DESC, id DESC
         LIMIT 1'
    );
    $stmt->execute([$accountKey]);
    $row = $stmt->fetch();
    if (!$row) return null;

    $number = static fn(mixed $value, ?float $default = null): ?float => is_numeric($value) ? (float)$value : $default;
    $validClass = static function (mixed $value): string {
        $class = strtoupper(trim((string)$value));
        return in_array($class, ['A', 'B', 'C', 'D'], true) ? $class : '';
    };
    $normalizeReason = static function (mixed $value): string {
        $reason = trim((string)$value, " \t\n\r\0\x0B\"'");
        if ($reason === '' || strtoupper($reason) === 'POSITION_CLOSED' || strtolower($reason) === 'closed') return '';
        return substr($reason, 0, 100);
    };
    $formatUtc = static function (mixed $value): string {
        $text = trim((string)$value);
        if ($text === '') return '';
        try {
            return (new DateTimeImmutable($text, new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format(DATE_ATOM);
        } catch (Throwable) {
            return $text;
        }
    };

    $openPrice = $number($row['open_price'], 0.0) ?? 0.0;
    $closePrice = $number($row['close_price'], 0.0) ?? 0.0;
    $returnPercent = $number($row['preleverage_return_percent']);
    if ($returnPercent === null && $openPrice > 0.0 && $closePrice > 0.0) {
        $returnPercent = ($closePrice / $openPrice - 1.0) * 100.0;
    }
    $returnDecimal = $returnPercent !== null ? $returnPercent / 100.0 : null;

    // strategy_trades.trade_class is the same persistent value used by Analytics.
    $tradeClass = $validClass($row['trade_class'] ?? '');
    $tradeClassSource = $tradeClass !== '' ? 'strategy_trades.trade_class' : '';

    $exitReason = $normalizeReason($row['exit_reason'] ?? '');
    $exitReasonSource = $exitReason !== '' ? 'strategy_trades.exit_reason' : '';

    // Do not invent D merely because an old row lacks exit_reason. A stored C is
    // authoritative; the exact TSL-vs-BE mechanism is honestly unknown.
    if ($exitReason === '' && $tradeClass === 'C') {
        $exitReason = 'TSL/BE';
        $exitReasonSource = 'trade_class_fallback';
    }
    if ($exitReason === '') {
        $exitReason = 'UNKNOWN';
        $exitReasonSource = 'fallback';
    }

    if ($tradeClass === '' && $returnDecimal !== null) {
        $normalizedReason = strtoupper(str_replace('-', '_', $exitReason));
        if ($returnDecimal >= 0.007) $tradeClass = 'A';
        elseif ($returnDecimal >= 0.0) $tradeClass = 'B';
        elseif (str_starts_with($normalizedReason, 'TSL') || str_contains($normalizedReason, 'BREAK_EVEN') || in_array($normalizedReason, ['BE', 'BH', 'BEO', 'BEPRE', 'TSL/BE'], true)) $tradeClass = 'C';
        else $tradeClass = 'D';
        $tradeClassSource = 'derived_missing_database_class';
    }

    return [
        'id' => (int)$row['id'],
        'positionIdentifier' => (int)($row['position_ticket'] ?? 0),
        'positionTicket' => (int)($row['position_ticket'] ?? 0),
        'symbol' => (string)($row['symbol'] ?? ''),
        'side' => (string)($row['side'] ?? ''),
        'volume' => $number($row['volume'], 0.0),
        'openedAt' => $formatUtc($row['opened_at'] ?? ''),
        'closedAt' => $formatUtc($row['closed_at'] ?? ''),
        'openPrice' => $openPrice,
        'closePrice' => $closePrice,
        'profit' => $number($row['profit']),
        'profitPercent' => $number($row['profit_percent']),
        'preleverageReturn' => $returnDecimal,
        'preleverageReturnPercent' => $returnPercent,
        'exitReason' => $exitReason,
        'exitReasonSource' => $exitReasonSource,
        'tradeClass' => $tradeClass,
        'tradeClassSource' => $tradeClassSource,
        'returnSource' => 'MySQL strategy_trades',
        'balanceBefore' => $number($row['balance_before']),
        'balanceAfter' => $number($row['balance_after']),
    ];
}

function oppw_latest_trade_is_direct_request(): bool
{
    $script = realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? ''));
    $current = realpath(__FILE__);
    return $script !== false && $current !== false && $script === $current;
}

if (oppw_latest_trade_is_direct_request()) {
    // API endpoints must never leak PHP warnings/notices as HTML before JSON.
    @ini_set('display_errors', '0');
    require_method('GET');
    require_write_token();

    try {
        $accountKey = trim((string)($_GET['accountKey'] ?? $_GET['strategyKey'] ?? ''));
        if ($accountKey === '') json_response(['ok' => false, 'error' => 'accountKey required'], 400);

        $db = pdo();
        $accountStmt = $db->prepare('SELECT account_key FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE LIMIT 1');
        $accountStmt->execute([$accountKey]);
        if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);

        json_response([
            'ok' => true,
            'accountKey' => $accountKey,
            'trade' => oppw_authoritative_last_trade($db, $accountKey),
        ]);
    } catch (Throwable $error) {
        error_log('OPPW latest-trade failed: ' . $error->getMessage());
        json_response(['ok' => false, 'error' => 'Unable to load trade history'], 500);
    }
}