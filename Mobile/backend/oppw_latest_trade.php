<?php

declare(strict_types=1);

require __DIR__ . '/lib.php';

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

$number = static fn(mixed $value, ?float $default = null): ?float => is_numeric($value) ? (float)$value : $default;
$normalizeReason = static function (mixed $value): string {
    $reason = trim((string)$value, " \t\n\r\0\x0B\"'");
    if ($reason === '' || strtoupper($reason) === 'POSITION_CLOSED' || strtolower($reason) === 'closed') return '';
    return substr($reason, 0, 100);
};
$validClass = static function (mixed $value): string {
    $class = strtoupper(trim((string)$value));
    return in_array($class, ['A', 'B', 'C', 'D'], true) ? $class : '';
};
$reasonFromDetails = static function (array $details) use ($normalizeReason): string {
    foreach (['reason', 'exitReason', 'exit_reason', 'activeSlReason', 'active_sl_reason', 'activeTpReason', 'active_tp_reason'] as $key) {
        $reason = $normalizeReason($details[$key] ?? '');
        if ($reason !== '') return $reason;
    }
    return '';
};
$classFromDetails = static function (array $details) use ($validClass): string {
    foreach (['tradeClass', 'trade_class'] as $key) {
        $class = $validClass($details[$key] ?? '');
        if ($class !== '') return $class;
    }
    return '';
};
$ticketFromDetails = static function (array $details): int {
    foreach (['positionIdentifier', 'position_identifier', 'positionTicket', 'position_ticket', 'ticket'] as $key) {
        if (is_numeric($details[$key] ?? null)) return (int)$details[$key];
    }
    return 0;
};

$openPrice = $number($row['open_price'], 0.0) ?? 0.0;
$closePrice = $number($row['close_price'], 0.0) ?? 0.0;
$preleverageReturnPercent = $number($row['preleverage_return_percent']);
if ($preleverageReturnPercent === null && $openPrice > 0.0 && $closePrice > 0.0) {
    $preleverageReturnPercent = ($closePrice / $openPrice - 1.0) * 100.0;
}
$preleverageReturn = $preleverageReturnPercent !== null ? $preleverageReturnPercent / 100.0 : null;

$exitReason = $normalizeReason($row['exit_reason'] ?? '');
$tradeClass = $validClass($row['trade_class'] ?? '');
$exitReasonSource = $exitReason !== '' ? 'strategy_trades.exit_reason' : '';
$tradeClassSource = $tradeClass !== '' ? 'strategy_trades.trade_class' : '';

// Older/transition rows may have a correct persistent class but an empty
// strategy_trades.exit_reason. Recover the reason from the MySQL event history,
// preferring a matching position ticket and then the closest close timestamp.
if ($exitReason === '' || $tradeClass === '') {
    $eventStmt = $db->prepare(
        "SELECT id, event_time, message, details
         FROM strategy_events
         WHERE strategy_key = ? AND name = 'POSITION_CLOSED'
           AND event_time BETWEEN DATE_SUB(?, INTERVAL 7 DAY) AND DATE_ADD(?, INTERVAL 1 DAY)
         ORDER BY ABS(TIMESTAMPDIFF(SECOND, event_time, ?)), id DESC
         LIMIT 100"
    );
    $closedAtQuery = (string)($row['closed_at'] ?? '');
    $eventStmt->execute([$accountKey, $closedAtQuery, $closedAtQuery, $closedAtQuery]);
    $events = $eventStmt->fetchAll();
    $positionTicket = (int)($row['position_ticket'] ?? 0);
    $chosen = null;
    foreach ($events as $event) {
        $details = [];
        if (is_string($event['details'] ?? null) && $event['details'] !== '') {
            try { $decoded = json_decode($event['details'], true, 512, JSON_THROW_ON_ERROR); if (is_array($decoded)) $details = $decoded; } catch (Throwable) {}
        }
        $eventTicket = $ticketFromDetails($details);
        if ($eventTicket !== 0 && $positionTicket !== 0 && $eventTicket === $positionTicket) {
            $chosen = [$event, $details];
            break;
        }
        if ($chosen === null) $chosen = [$event, $details];
    }
    if ($chosen !== null) {
        [$event, $details] = $chosen;
        if ($exitReason === '') {
            $exitReason = $reasonFromDetails($details);
            if ($exitReason === '' && preg_match('/(?:^|\s)reason=("[^"]*"|\'[^\']*\'|\S+)/i', (string)($event['message'] ?? ''), $match)) {
                $exitReason = $normalizeReason($match[1]);
            }
            if ($exitReason !== '') $exitReasonSource = 'strategy_events.POSITION_CLOSED';
        }
        if ($tradeClass === '') {
            $tradeClass = $classFromDetails($details);
            if ($tradeClass !== '') $tradeClassSource = 'strategy_events.POSITION_CLOSED';
        }
    }
}

// The database class is authoritative and must match Analytics. When no exact
// legacy exit reason can be recovered, display an honest class-derived label
// instead of an empty field.
if ($exitReason === '' && $tradeClass === 'C') {
    $exitReason = 'TSL/BE (legacy C-class)';
    $exitReasonSource = 'trade_class_fallback';
}
if ($exitReason === '') {
    $exitReason = 'UNKNOWN';
    $exitReasonSource = 'fallback';
}
if ($tradeClass === '' && $preleverageReturn !== null) {
    if ($preleverageReturn >= 0.007) $tradeClass = 'A';
    elseif ($preleverageReturn >= 0.0) $tradeClass = 'B';
    elseif (str_starts_with(strtoupper(str_replace('-', '_', $exitReason)), 'TSL') || str_contains(strtoupper(str_replace('-', '_', $exitReason)), 'BREAK_EVEN') || in_array(strtoupper(str_replace('-', '_', $exitReason)), ['BE', 'BH', 'BEO', 'BEPRE'], true)) $tradeClass = 'C';
    else $tradeClass = 'D';
    $tradeClassSource = 'derived';
}

$formatUtc = static function (mixed $value): string {
    $text = (string)$value;
    if ($text === '') return '';
    try { return (new DateTimeImmutable($text, new DateTimeZone('UTC')))->setTimezone(new DateTimeZone('UTC'))->format(DATE_ATOM); }
    catch (Throwable) { return $text; }
};

json_response([
    'ok' => true,
    'accountKey' => $accountKey,
    'trade' => [
        'id' => (int)$row['id'],
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
        'preleverageReturn' => $preleverageReturn,
        'preleverageReturnPercent' => $preleverageReturnPercent,
        'exitReason' => $exitReason,
        'exitReasonSource' => $exitReasonSource,
        'tradeClass' => $tradeClass,
        'tradeClassSource' => $tradeClassSource,
        'balanceBefore' => $number($row['balance_before']),
        'balanceAfter' => $number($row['balance_after']),
    ],
]);
