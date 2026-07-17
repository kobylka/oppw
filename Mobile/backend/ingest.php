<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json(524288);
$db = pdo();
$accountKey = trim((string)($data['accountKey'] ?? $data['strategyKey'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'accountKey required'], 400);

$accountStmt = $db->prepare('SELECT account_key, display_name FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
$monitorAccount = $accountStmt->fetch();
if (!$monitorAccount) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 400);
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

$number = static fn(mixed $value, float $default = 0.0): float => is_numeric($value) ? (float)$value : $default;
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
$currentPrice = $number($market['currentPrice'] ?? $metrics['currentPrice'] ?? $currentPosition['bid'] ?? 0);
$currentBid = $number($market['bid'] ?? $currentPosition['bid'] ?? $currentPrice);
$positionTicket = $currentPosition !== null ? (int)($currentPosition['ticket'] ?? 0) : null;

$closedEvent = null;
$buyReference = null;
$sellReference = null;
$hasTradeEvent = false;
$normalizedEvents = [];
foreach ($events as $event) {
    if (!is_array($event)) continue;
    $name = strtoupper(trim((string)($event['name'] ?? 'EVENT')));
    $eventTime = normalize_datetime($event['time'] ?? null);
    $message = substr((string)($event['message'] ?? ''), 0, 1000);
    $details = is_array($event['details'] ?? null) ? $event['details'] : [];
    if (str_starts_with($name, 'BUY') || str_starts_with($name, 'SELL') || $name === 'POSITION_CLOSED') $hasTradeEvent = true;
    if ($name === 'POSITION_CLOSED') $closedEvent = $event;
    if ($name === 'BUY_REQUEST' && is_numeric($details['ask'] ?? null)) $buyReference = (float)$details['ask'];
    if ($name === 'SELL_REQUEST' && is_numeric($details['bid'] ?? null)) $sellReference = (float)$details['bid'];
    $normalizedEvents[] = [
        'time' => $eventTime,
        'level' => substr((string)($event['level'] ?? 'INFO'), 0, 16),
        'name' => substr($name, 0, 100),
        'result' => array_key_exists('result', $event) && $event['result'] !== null ? (int)(bool)$event['result'] : null,
        'message' => $message,
        'details' => $details,
        'hash' => hash('sha256', $accountKey . '|' . $eventTime . '|' . $name . '|' . $message),
    ];
}

$insertedCriticalEvents = [];
$closedTradeProfit = null;
$closedTradeReason = "closed";
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
        $currentPrice ?: null,
        $currentBid ?: null,
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
        $openPrice = $number($currentPosition['openPrice'] ?? 0);
        $tradePrice = $currentBid > 0 ? $currentBid : $currentPrice;
        $mfePoints = $openPrice > 0 && $tradePrice > 0 ? max(0.0, $tradePrice - $openPrice) : 0.0;
        $maePoints = $openPrice > 0 && $tradePrice > 0 ? min(0.0, $tradePrice - $openPrice) : 0.0;
        $entrySlippage = $buyReference !== null && $openPrice > 0 ? $openPrice - $buyReference : null;
        $entrySlippagePercent = $entrySlippage !== null && $buyReference > 0 ? $entrySlippage / $buyReference * 100.0 : null;
        $tradeStmt = $db->prepare(
            'INSERT INTO strategy_trades(
                strategy_key, position_ticket, symbol, side, volume, opened_at, open_price,
                entry_reference_price, entry_slippage_points, entry_slippage_percent,
                best_price, worst_price, mfe_points, mfe_percent, mae_points, mae_percent,
                max_profit, max_drawdown, balance_before
             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
             ON DUPLICATE KEY UPDATE
                symbol = VALUES(symbol), side = VALUES(side), volume = VALUES(volume), open_price = VALUES(open_price),
                entry_reference_price = COALESCE(entry_reference_price, VALUES(entry_reference_price)),
                entry_slippage_points = COALESCE(entry_slippage_points, VALUES(entry_slippage_points)),
                entry_slippage_percent = COALESCE(entry_slippage_percent, VALUES(entry_slippage_percent)),
                best_price = GREATEST(COALESCE(best_price, VALUES(best_price)), VALUES(best_price)),
                worst_price = LEAST(COALESCE(worst_price, VALUES(worst_price)), VALUES(worst_price)),
                mfe_points = GREATEST(COALESCE(mfe_points, VALUES(mfe_points)), VALUES(mfe_points)),
                mfe_percent = GREATEST(COALESCE(mfe_percent, VALUES(mfe_percent)), VALUES(mfe_percent)),
                mae_points = LEAST(COALESCE(mae_points, VALUES(mae_points)), VALUES(mae_points)),
                mae_percent = LEAST(COALESCE(mae_percent, VALUES(mae_percent)), VALUES(mae_percent)),
                max_profit = GREATEST(COALESCE(max_profit, VALUES(max_profit)), VALUES(max_profit)),
                max_drawdown = LEAST(COALESCE(max_drawdown, VALUES(max_drawdown)), VALUES(max_drawdown)),
                balance_before = COALESCE(balance_before, VALUES(balance_before))'
        );
        $tradeStmt->execute([
            $accountKey,
            (int)($currentPosition['ticket'] ?? 0),
            substr((string)($currentPosition['symbol'] ?? ''), 0, 32),
            substr((string)($currentPosition['side'] ?? 'BUY'), 0, 8),
            $number($currentPosition['volume'] ?? 0),
            $openedAt,
            $openPrice,
            $buyReference,
            $entrySlippage,
            $entrySlippagePercent,
            $tradePrice ?: $openPrice,
            $tradePrice ?: $openPrice,
            $mfePoints,
            $openPrice > 0 ? $mfePoints / $openPrice * 100.0 : 0.0,
            $maePoints,
            $openPrice > 0 ? $maePoints / $openPrice * 100.0 : 0.0,
            $currentProfit,
            $currentProfit,
            $balance,
        ]);
    }

    if ($previousPosition !== null && $currentPosition === null) {
        $details = is_array($closedEvent['details'] ?? null) ? $closedEvent['details'] : [];
        $ticket = (int)($previousPosition['ticket'] ?? 0);
        $closePrice = $number($details['exit'] ?? $currentPrice ?? $previousPosition['bid'] ?? 0);
        $change = $number($details['change'] ?? 0);
        $reason = substr((string)($details['reason'] ?? $closedEvent['name'] ?? 'POSITION_CLOSED'), 0, 100);
        $lookup = $db->prepare('SELECT balance_before, open_price FROM strategy_trades WHERE strategy_key = ? AND position_ticket = ? LIMIT 1');
        $lookup->execute([$accountKey, $ticket]);
        $existingTrade = $lookup->fetch();
        $balanceBefore = $existingTrade['balance_before'] ?? null;
        $openPrice = $number($existingTrade['open_price'] ?? $previousPosition['openPrice'] ?? 0);
        $profit = is_numeric($balanceBefore) ? $balance - (float)$balanceBefore : null;
        $closedTradeProfit = $profit;
        $closedTradeReason = $reason;
        $exitSlippage = $sellReference !== null && $closePrice > 0 ? $sellReference - $closePrice : null;
        $exitSlippagePercent = $exitSlippage !== null && $sellReference > 0 ? $exitSlippage / $sellReference * 100.0 : null;
        $closeTrade = $db->prepare(
            'UPDATE strategy_trades
                SET closed_at = ?, close_price = ?, exit_reference_price = ?, exit_slippage_points = ?, exit_slippage_percent = ?,
                    profit = ?, profit_percent = ?, exit_reason = ?, balance_after = ?,
                    best_price = GREATEST(COALESCE(best_price, ?), ?),
                    worst_price = LEAST(COALESCE(worst_price, ?), ?),
                    mfe_points = GREATEST(COALESCE(mfe_points, 0), GREATEST(0, ? - open_price)),
                    mfe_percent = GREATEST(COALESCE(mfe_percent, 0), GREATEST(0, ? / open_price - 1) * 100),
                    mae_points = LEAST(COALESCE(mae_points, 0), LEAST(0, ? - open_price)),
                    mae_percent = LEAST(COALESCE(mae_percent, 0), LEAST(0, ? / open_price - 1) * 100)
              WHERE strategy_key = ? AND position_ticket = ?'
        );
        $closeTrade->execute([
            $capturedAt, $closePrice ?: null, $sellReference, $exitSlippage, $exitSlippagePercent,
            $profit, $change * 100.0, $reason, $balance,
            $closePrice, $closePrice, $closePrice, $closePrice,
            $closePrice, $closePrice, $closePrice, $closePrice,
            $accountKey, $ticket,
        ]);
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

    $eventStmt = $db->prepare('INSERT IGNORE INTO strategy_events(strategy_key, event_time, level, name, result, message, details, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    foreach ($normalizedEvents as $event) {
        $detailsJson = $event['details'] ? json_encode($event['details'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) : null;
        $eventStmt->execute([$accountKey, $event['time'], $event['level'], $event['name'], $event['result'], $event['message'], $detailsJson, $event['hash']]);
        if ($eventStmt->rowCount() > 0 && (
            in_array($event['name'], ['CONNECTION_LOST', 'STRATEGY_CYCLE_FAILED', 'POSITION_DISAPPEARED', 'SLTP_REJECTED'], true)
            || str_starts_with($event['name'], 'PROTECTION_')
        )) $insertedCriticalEvents[] = $event;
    }
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    error_log('OPPW ingest failed: ' . $e->getMessage());
    json_response(['ok' => false, 'error' => 'Database write failed'], 500);
}

$displayName = (string)$monitorAccount['display_name'];
if ($previousPosition === null && $currentPosition !== null) {
    $ticket = (int)($currentPosition['ticket'] ?? 0);
    send_account_push($db, $accountKey, "position-open:$ticket", "$displayName position opened", sprintf('%s %s %.2f lot @ %.2f', (string)($currentPosition['side'] ?? 'BUY'), (string)($currentPosition['symbol'] ?? ''), $number($currentPosition['volume'] ?? 0), $number($currentPosition['openPrice'] ?? 0)), ['type' => 'POSITION_OPENED', 'ticket' => (string)$ticket]);
}
if ($previousPosition !== null && $currentPosition === null) {
    $ticket = (int)($previousPosition['ticket'] ?? 0);
    $profitForPush = is_numeric($closedTradeProfit) ? (float)$closedTradeProfit : 0.0;
    send_account_push($db, $accountKey, "position-close:$ticket:$capturedAt", "$displayName position closed", sprintf('Ticket %d · %s · P/L %.2f', $ticket, $closedTradeReason, $profitForPush), ['type' => 'POSITION_CLOSED', 'ticket' => (string)$ticket]);
}
$previousConnected = (bool)(is_array($previousSnapshot['connection'] ?? null) ? ($previousSnapshot['connection']['connected'] ?? true) : true);
$currentConnected = (bool)($connection['connected'] ?? false);
if ($previousConnected && !$currentConnected) {
    send_account_push($db, $accountKey, 'mt5-disconnected:' . substr($capturedAt, 0, 16), "$displayName MT5 disconnected", 'The publisher reports that the MT5 terminal is disconnected.', ['type' => 'MT5_DISCONNECTED']);
}
$previousSl = $number($previousPosition['stopLoss'] ?? 0);
$currentSl = $number($currentPosition['stopLoss'] ?? 0);
if ($currentPosition !== null && $previousSl > 0 && $currentSl <= 0) {
    send_account_push($db, $accountKey, 'protection-lost:' . (string)$positionTicket . ':' . substr($capturedAt, 0, 16), "$displayName protection lost", 'The open position no longer has a broker-side stop loss.', ['type' => 'PROTECTION_LOST', 'ticket' => (string)$positionTicket]);
}
foreach ($insertedCriticalEvents as $event) {
    send_account_push($db, $accountKey, 'event:' . $event['hash'], "$displayName: {$event['name']}", $event['message'], ['type' => $event['name']]);
}

json_response(['ok' => true, 'accountKey' => $accountKey, 'storedEvents' => count($normalizedEvents)], 201);
