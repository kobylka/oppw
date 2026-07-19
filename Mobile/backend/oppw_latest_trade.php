<?php

declare(strict_types=1);

require dirname(__DIR__) . '/lib.php';

require_method('GET');
require_write_token();

$accountKey = trim((string)($_GET['accountKey'] ?? $_GET['strategyKey'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'accountKey required'], 400);

$db = pdo();
$accountStmt = $db->prepare('SELECT account_key FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE LIMIT 1');
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);

$stmt = $db->prepare(
    'SELECT id, strategy_key, position_ticket, symbol, side, volume, opened_at, closed_at,
            open_price, close_price, profit, profit_percent, exit_reason, balance_before, balance_after,
            preleverage_return_percent, trade_class
     FROM strategy_trades
     WHERE strategy_key = ? AND closed_at IS NOT NULL
     ORDER BY closed_at DESC, id DESC
     LIMIT 1'
);
$stmt->execute([$accountKey]);
$row = $stmt->fetch();

if (!$row) json_response(['ok' => true, 'accountKey' => $accountKey, 'trade' => null]);

$openPrice = is_numeric($row['open_price'] ?? null) ? (float)$row['open_price'] : 0.0;
$closePrice = is_numeric($row['close_price'] ?? null) ? (float)$row['close_price'] : 0.0;
$preleverageReturnPercent = is_numeric($row['preleverage_return_percent'] ?? null)
    ? (float)$row['preleverage_return_percent']
    : ($openPrice > 0.0 && $closePrice > 0.0 ? ($closePrice / $openPrice - 1.0) * 100.0 : null);
$preleverageReturn = $preleverageReturnPercent !== null ? $preleverageReturnPercent / 100.0 : null;

$closedAt = (string)($row['closed_at'] ?? '');
if ($closedAt !== '') {
    try {
        $closedAt = (new DateTimeImmutable($closedAt, new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format(DATE_ATOM);
    } catch (Throwable) {
        // Preserve the database value if an old row contains a non-standard timestamp.
    }
}
$openedAt = (string)($row['opened_at'] ?? '');
if ($openedAt !== '') {
    try {
        $openedAt = (new DateTimeImmutable($openedAt, new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format(DATE_ATOM);
    } catch (Throwable) {
    }
}

json_response([
    'ok' => true,
    'accountKey' => $accountKey,
    'trade' => [
        'id' => (int)$row['id'],
        'positionTicket' => (int)($row['position_ticket'] ?? 0),
        'symbol' => (string)($row['symbol'] ?? ''),
        'side' => (string)($row['side'] ?? ''),
        'volume' => is_numeric($row['volume'] ?? null) ? (float)$row['volume'] : 0.0,
        'openedAt' => $openedAt,
        'closedAt' => $closedAt,
        'openPrice' => $openPrice,
        'closePrice' => $closePrice,
        'profit' => is_numeric($row['profit'] ?? null) ? (float)$row['profit'] : null,
        'profitPercent' => is_numeric($row['profit_percent'] ?? null) ? (float)$row['profit_percent'] : null,
        'preleverageReturn' => $preleverageReturn,
        'preleverageReturnPercent' => $preleverageReturnPercent,
        'exitReason' => (string)($row['exit_reason'] ?? ''),
        'tradeClass' => (string)($row['trade_class'] ?? ''),
        'balanceBefore' => is_numeric($row['balance_before'] ?? null) ? (float)$row['balance_before'] : null,
        'balanceAfter' => is_numeric($row['balance_after'] ?? null) ? (float)$row['balance_after'] : null,
    ],
]);
