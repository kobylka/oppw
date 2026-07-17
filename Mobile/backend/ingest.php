<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json(262144);
$db = pdo();
$accountKey = trim((string)($data['accountKey'] ?? $data['strategyKey'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'accountKey required'], 400);

$accountStmt = $db->prepare('SELECT account_key FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 400);
if (!isset($data['snapshot']) || !is_array($data['snapshot'])) json_response(['ok' => false, 'error' => 'snapshot object required'], 400);

$capturedAt = normalize_datetime($data['capturedAt'] ?? null);
$capturedMinute = substr($capturedAt, 0, 16) . ':00';
$snapshot = $data['snapshot'];
$payload = json_encode($snapshot, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
$events = isset($data['events']) && is_array($data['events']) ? $data['events'] : [];

$previousStmt = $db->prepare('SELECT payload FROM strategy_snapshots WHERE strategy_key = ? ORDER BY id DESC LIMIT 1');
$previousStmt->execute([$accountKey]);
$previousRaw = $previousStmt->fetchColumn();
$previousSnapshot = [];
if (is_string($previousRaw) && $previousRaw !== '') {
    try { $previousSnapshot = json_decode($previousRaw, true, 512, JSON_THROW_ON_ERROR); } catch (Throwable) { $previousSnapshot = []; }
}

$number = static function (mixed $value, float $default = 0.0): float {
    return is_numeric($value) ? (float)$value : $default;
};
$positionOf = static function (array $value): ?array {
    $position = $value['position'] ?? null;
    return is_array($position) && (!array_key_exists('open', $position) || (bool)$position['open']) ? $position : null;
};
$currentPosition = $positionOf($snapshot);
$previousPosition = $positionOf($previousSnapshot);
$account = is_array($snapshot['account'] ?? null) ? $snapshot['account'] : [];
$market = is_array($snapshot['market'] ?? null) ? $snapshot['market'] : [];
$metrics = is_array($snapshot['metrics'] ?? null) ? $snapshot['metrics'] : [];
$connection = is_array($snapshot['connection'] ?? null) ? $snapshot['connection'] : [];
$currentM1 = is_array($market['currentM1'] ?? null) ? $market['currentM1'] : [];
$balance = $number($account['balance'] ?? $metrics['balance'] ?? 0);
$equity = $number($account['equity'] ?? $metrics['equity'] ?? 0);
$deposit = $number($account['deposit'] ?? $metrics['deposit'] ?? 0);
$currentProfit = $number($metrics['currentProfit'] ?? $currentPosition['profit'] ?? 0);
$positionTicket = $currentPosition !== null ? (int)($currentPosition['ticket'] ?? 0) : null;

$closedEvent = null;
$hasTradeEvent = false;
foreach ($events as $event) {
    if (!is_array($event)) continue;
    $name = strtoupper((string)($event['name'] ?? ''));
    if (str_starts_with($name, 'BUY') || str_starts_with($name, 'SELL') || in_array($name, ['POSITION_OPEN', 'POSITION_CLOSED'], true)) $hasTradeEvent = true;
    if ($name === 'POSITION_CLOSED') $closedEvent = $event;
}

$db->beginTransaction();
try {
    $snapshotStmt = $db->prepare('INSERT INTO strategy_snapshots(strategy_key, captured_at, payload) VALUES (?, ?, ?)');
    $snapshotStmt->execute([$accountKey, $capturedAt, $payload]);

    $equityStmt = $db->prepare(
        'INSERT INTO strategy_equity_points(strategy_key, captured_minute, balance, equity, deposit, current_profit, position_ticket)
         VALUES (?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE balance = VALUES(balance), equity = VALUES(equity), deposit = VALUES(deposit), current_profit = VALUES(current_profit), position_ticket = VALUES(position_ticket)'
    );
    $equityStmt->execute([$accountKey, $capturedMinute, $balance, $equity, $deposit, $currentProfit, $positionTicket]);

    $marketStmt = $db->prepare(
        'INSERT INTO strategy_market_points(strategy_key, captured_minute, current_price, bid, ask, m1_open, m1_high, m1_low, m1_close, phase)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
         ON DUPLICATE KEY UPDATE current_price = VALUES(current_price), bid = VALUES(bid), ask = VALUES(ask), m1_open = VALUES(m1_open), m1_high = VALUES(m1_high), m1_low = VALUES(m1_low), m1_close = VALUES(m1_close), phase = VALUES(phase)'
    );
    $marketStmt->execute([
        $accountKey,
        $capturedMinute,
        $number($market['currentPrice'] ?? $metrics['currentPrice'] ?? 0) ?: null,
        $number($market['bid'] ?? 0) ?: null,
        $number($market['ask'] ?? 0) ?: null,
        $number($currentM1['open'] ?? 0) ?: null,
        $number($currentM1['high'] ?? 0) ?: null,
        $number($currentM1['low'] ?? 0) ?: null,
        $number($currentM1['close'] ?? 0) ?: null,
        substr((string)($connection['phase'] ?? ''), 0, 64),
    ]);

    $initialCheck = $db->prepare("SELECT 1 FROM account_cash_flows WHERE strategy_key = ? AND flow_type = 'INITIAL' LIMIT 1");
    $initialCheck->execute([$accountKey]);
    if (!$initialCheck->fetchColumn() && $balance != 0.0) {
        $initialFlow = $db->prepare("INSERT INTO account_cash_flows(strategy_key, occurred_at, flow_type, amount, balance_after, source, reference_key, note) VALUES (?, ?, 'INITIAL', ?, ?, 'AUTO', ?, 'Initial balance observed by publisher')");
        $initialFlow->execute([$accountKey, $capturedAt, $balance, $balance, 'initial:' . $accountKey]);
    }

    if ($currentPosition !== null) {
        $openedAt = normalize_datetime((string)($currentPosition['openedAt'] ?? $capturedAt));
        $tradeStmt = $db->prepare(
            'INSERT INTO strategy_trades(strategy_key, position_ticket, symbol, side, volume, opened_at, open_price, balance_before)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE symbol = VALUES(symbol), side = VALUES(side), volume = VALUES(volume), open_price = VALUES(open_price), balance_before = COALESCE(balance_before, VALUES(balance_before))'
        );
        $tradeStmt->execute([
            $accountKey,
            (int)($currentPosition['ticket'] ?? 0),
            substr((string)($currentPosition['symbol'] ?? ''), 0, 32),
            substr((string)($currentPosition['side'] ?? 'BUY'), 0, 8),
            $number($currentPosition['volume'] ?? 0),
            $openedAt,
            $number($currentPosition['openPrice'] ?? 0),
            $balance,
        ]);
    }

    if ($previousPosition !== null && $currentPosition === null) {
        $details = is_array($closedEvent['details'] ?? null) ? $closedEvent['details'] : [];
        $ticket = (int)($previousPosition['ticket'] ?? 0);
        $closePrice = $number($details['exit'] ?? $market['currentPrice'] ?? $previousPosition['bid'] ?? 0);
        $change = $number($details['change'] ?? 0);
        $reason = substr((string)($details['reason'] ?? 'POSITION_CLOSED'), 0, 100);
        $lookup = $db->prepare('SELECT balance_before FROM strategy_trades WHERE strategy_key = ? AND position_ticket = ? LIMIT 1');
        $lookup->execute([$accountKey, $ticket]);
        $balanceBefore = $lookup->fetchColumn();
        $profit = is_numeric($balanceBefore) ? $balance - (float)$balanceBefore : null;
        $closeTrade = $db->prepare(
            'UPDATE strategy_trades SET closed_at = ?, close_price = ?, profit = ?, profit_percent = ?, exit_reason = ?, balance_after = ? WHERE strategy_key = ? AND position_ticket = ?'
        );
        $closeTrade->execute([$capturedAt, $closePrice ?: null, $profit, $change * 100.0, $reason, $balance, $accountKey, $ticket]);
    }

    $previousAccount = is_array($previousSnapshot['account'] ?? null) ? $previousSnapshot['account'] : [];
    $previousBalance = $number($previousAccount['balance'] ?? 0);
    $balanceDelta = $balance - $previousBalance;
    if ($previousSnapshot && abs($balanceDelta) >= 0.01 && !$hasTradeEvent && $previousPosition === null && $currentPosition === null) {
        $flowType = $balanceDelta > 0 ? 'TOP_UP' : 'WITHDRAWAL';
        $reference = 'auto:' . $accountKey . ':' . str_replace([' ', ':', '.'], '', $capturedAt);
        $autoFlow = $db->prepare('INSERT IGNORE INTO account_cash_flows(strategy_key, occurred_at, flow_type, amount, balance_after, source, reference_key, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
        $autoFlow->execute([$accountKey, $capturedAt, $flowType, $balanceDelta, $balance, 'AUTO_DETECTED', $reference, 'Balance changed while account was flat and no trade event was received']);
    }

    $eventStmt = $db->prepare('INSERT INTO strategy_events(strategy_key, event_time, level, name, result, message, details) VALUES (?, ?, ?, ?, ?, ?, ?)');
    foreach ($events as $event) {
        if (!is_array($event)) continue;
        $result = array_key_exists('result', $event) && $event['result'] !== null ? (int)(bool)$event['result'] : null;
        $details = isset($event['details']) ? json_encode($event['details'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) : null;
        $eventStmt->execute([
            $accountKey,
            normalize_datetime($event['time'] ?? null),
            substr((string)($event['level'] ?? 'INFO'), 0, 16),
            substr((string)($event['name'] ?? 'EVENT'), 0, 100),
            $result,
            substr((string)($event['message'] ?? ''), 0, 1000),
            $details,
        ]);
    }
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    error_log('OPPW ingest failed: ' . $e->getMessage());
    json_response(['ok' => false, 'error' => 'Database write failed'], 500);
}

json_response(['ok' => true, 'accountKey' => $accountKey, 'storedEvents' => count($events)], 201);
