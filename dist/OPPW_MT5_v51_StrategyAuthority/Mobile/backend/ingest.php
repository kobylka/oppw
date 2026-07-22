<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require __DIR__ . '/authority.php';
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
require_coordination_actor($db, $accountKey, $data['coordination'] ?? null, 'snapshot');
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
        'result' => oppw_nullable_bool($event['result'] ?? null),
        'message' => $message,
        'details' => $details,
        'hash' => hash('sha256', $accountKey . '|' . $eventTime . '|' . $name . '|' . $message),
    ];
}

$insertedCriticalEvents = [];
$closedTradeProfit = null;
$closedTradeReason = "closed";
// OPPW_V47_4_DECISION_ACK_INIT_BEGIN
$strategyDecisionStored = false;
$strategyDecisionId = '';
$strategySpecificationStored = false;
$strategySpecificationId = '';
$strategySpecificationHash = '';
// OPPW_V47_4_DECISION_ACK_INIT_END

$db->beginTransaction();
try {
    $coordination = is_array($data['coordination'] ?? null) ? $data['coordination'] : [];
    $specification = is_array($data['strategySpecification'] ?? null) ? $data['strategySpecification'] : null;
    if ($specification !== null) {
        $specResult = oppw_store_strategy_specification($db, $accountKey, $specification, $coordination, $capturedAt);
        $strategySpecificationStored = (bool)$specResult['stored'];
        $strategySpecificationId = (string)$specResult['specId'];
        $strategySpecificationHash = (string)$specResult['specHash'];
    }
    $snapshotStmt = $db->prepare('INSERT INTO strategy_snapshots(strategy_key, captured_at, payload) VALUES (?, ?, ?)');
    $snapshotStmt->execute([$accountKey, $capturedAt, $payload]);
  // OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_BEGIN
  // OPPW_V47_6_EXPLICIT_DECISION_PERSISTENCE_BEGIN
  // snapshot.strategyDecision remains available to status.php/Android. Only
  // the explicit top-level strategyDecision key requests a MySQL upsert.
  $decision = is_array($data['strategyDecision'] ?? null) ? $data['strategyDecision'] : null;
  // OPPW_V47_6_EXPLICIT_DECISION_PERSISTENCE_END
  if ($decision !== null && trim((string)($decision['decisionId'] ?? '')) !== '') {
      $inputs = is_array($decision['inputs'] ?? null) ? $decision['inputs'] : [];
      $sizing = is_array($decision['sizing'] ?? null) ? $decision['sizing'] : [];
      $risk = is_array($decision['risk'] ?? null) ? $decision['risk'] : [];
      $strategyDecisionId = substr(trim((string)$decision['decisionId']), 0, 32);
      $decisionPayload = oppw_canonical_json($decision);
      $decisionPayloadHash = hash('sha256', $decisionPayload);
      $decisionRecordedAt = normalize_datetime($decision['recordedAt'] ?? $capturedAt);
      $decisionSpecId = substr((string)($decision['strategySpecId'] ?? $strategySpecificationId), 0, 32);
      $decisionSpecHash = substr((string)($decision['strategySpecHash'] ?? $strategySpecificationHash), 0, 64);
      if ($decisionSpecId === '') $decisionSpecId = (string)(oppw_current_spec_id($db, $accountKey) ?? '');
      if ($decisionSpecId === '') throw new RuntimeException('strategy decision has no canonical specification');
      if ($decisionSpecHash === '') {
          $specHashStmt = $db->prepare('SELECT spec_hash FROM strategy_specifications WHERE spec_id=?');
          $specHashStmt->execute([$decisionSpecId]);
          $decisionSpecHash = (string)($specHashStmt->fetchColumn() ?: '');
      }
      $decisionStmt = $db->prepare(
          'INSERT IGNORE INTO strategy_decisions(
              strategy_key, decision_id, strategy_spec_id, strategy_spec_hash, decision_week, recorded_at, first_received_at, last_received_at,
              strategy_build, parameter_hash, decision_type, outcome, selected_leverage, leverage_reason,
              previous_full_week_change, previous_full_week_source, previous_trade_change, previous_trade_source,
              symbol, side, proposed_price, proposed_volume, required_deposit, required_balance,
              required_balance_multiplier, balance_multiplier_profile, effective_leverage,
              position_notional, sizing_units, margin_usage_percent, margin_level_after_percent,
              stop_loss_percent, stop_loss_price, stop_loss_cash, account_return_at_stop_percent,
              account_loss_cap_applied, error_text, payload, payload_hash
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
      );
      $decisionStmt->execute([
          $accountKey, $strategyDecisionId, $decisionSpecId, $decisionSpecHash,
          substr((string)($decision['decisionWeek'] ?? ''), 0, 10),
          $decisionRecordedAt, $capturedAt, $capturedAt,
          substr((string)($decision['build'] ?? ''), 0, 160), substr((string)($decision['parameterHash'] ?? ''), 0, 64),
          substr((string)($decision['decision'] ?? ''), 0, 64), substr((string)($decision['outcome'] ?? ''), 0, 32),
          $number($decision['selectedLeverage'] ?? 0), substr((string)($decision['leverageReason'] ?? ''), 0, 1000),
          $number($inputs['previousFullWeekChange'] ?? 0), substr((string)($inputs['previousFullWeekSource'] ?? ''), 0, 100),
          $number($inputs['previousTradeChange'] ?? 0), substr((string)($inputs['previousTradeSource'] ?? ''), 0, 100),
          substr((string)($sizing['symbol'] ?? ''), 0, 32), substr((string)($sizing['side'] ?? ''), 0, 8),
          is_numeric($sizing['price'] ?? null) ? (float)$sizing['price'] : null,
          is_numeric($sizing['volume'] ?? null) ? (float)$sizing['volume'] : null,
          is_numeric($sizing['requiredDeposit'] ?? null) ? (float)$sizing['requiredDeposit'] : null,
          is_numeric($sizing['requiredBalance'] ?? null) ? (float)$sizing['requiredBalance'] : null,
          is_numeric($sizing['requiredBalanceMultiplier'] ?? null) ? (float)$sizing['requiredBalanceMultiplier'] : null,
          substr((string)($sizing['balanceMultiplierProfile'] ?? ''), 0, 40),
          is_numeric($sizing['effectiveLeverage'] ?? null) ? (float)$sizing['effectiveLeverage'] : null,
          is_numeric($sizing['positionNotional'] ?? null) ? (float)$sizing['positionNotional'] : null,
          is_numeric($sizing['sizingUnits'] ?? null) ? (int)$sizing['sizingUnits'] : null,
          is_numeric($sizing['marginUsagePercent'] ?? null) ? (float)$sizing['marginUsagePercent'] : null,
          is_numeric($sizing['marginLevelAfterPercent'] ?? null) ? (float)$sizing['marginLevelAfterPercent'] : null,
          is_numeric($risk['potentialStopLossPercent'] ?? null) ? (float)$risk['potentialStopLossPercent'] : null,
          is_numeric($risk['potentialStopLossPrice'] ?? null) ? (float)$risk['potentialStopLossPrice'] : null,
          is_numeric($risk['potentialStopLossCash'] ?? null) ? (float)$risk['potentialStopLossCash'] : null,
          is_numeric($risk['accountLossPercentAtStop'] ?? null) ? (float)$risk['accountLossPercentAtStop'] : null,
          !empty($risk['accountLossCapApplied']) ? 1 : 0,
          substr((string)($decision['error'] ?? ''), 0, 1000), $decisionPayload, $decisionPayloadHash,
      ]);
      $decisionVerify = $db->prepare(
          'SELECT strategy_spec_id,strategy_spec_hash,payload_hash FROM strategy_decisions
            WHERE strategy_key=? AND decision_id=?'
      );
      $decisionVerify->execute([$accountKey, $strategyDecisionId]);
      $storedDecision = $decisionVerify->fetch();
      if (!is_array($storedDecision)
          || !hash_equals($decisionSpecId, (string)$storedDecision['strategy_spec_id'])
          || !hash_equals($decisionSpecHash, (string)$storedDecision['strategy_spec_hash'])
          || !hash_equals($decisionPayloadHash, (string)$storedDecision['payload_hash'])) {
          throw new RuntimeException('immutable strategy decision conflict');
      }
      $strategyDecisionStored = true;
  }
  // OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_END


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
        $initialReference = 'initial:' . $accountKey;
        $initialHash = hash('sha256', implode('|', [$accountKey,$capturedAt,'INITIAL',(string)$balance,(string)$balance,'AUTO',$initialReference]));
        $initialFlow = $db->prepare("INSERT INTO account_cash_flows(strategy_key,occurred_at,flow_type,amount,balance_after,source,reference_key,note,payload_hash) VALUES (?,?,'INITIAL',?,?,'AUTO',?,'Initial balance observed by publisher',?)");
        $initialFlow->execute([$accountKey,$capturedAt,$balance,$balance,$initialReference,$initialHash]);
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

      // OPPW_V47_4_TRADE_DECISION_LINK_BEGIN
  $execution = is_array($snapshot['execution'] ?? null) ? $snapshot['execution'] : [];
  $linkedDecisionId = substr(trim((string)(($decision['decisionId'] ?? null) ?: ($execution['decisionId'] ?? ''))), 0, 32);
  if ($linkedDecisionId !== '') {
      $linkedBuild = substr((string)($decision['build'] ?? ''), 0, 160);
      $linkedParameterHash = substr((string)($decision['parameterHash'] ?? ''), 0, 64);
      $linkedLeverage = is_numeric($decision['selectedLeverage'] ?? null) ? (float)$decision['selectedLeverage'] : null;
      $linkedSpecId = substr((string)($decision['strategySpecId'] ?? $strategySpecificationId), 0, 32);
      $linkedSpecHash = substr((string)($decision['strategySpecHash'] ?? $strategySpecificationHash), 0, 64);
      if ($decision === null || $linkedBuild === '' || $linkedParameterHash === '' || $linkedLeverage === null) {
          $linkedDecisionStmt = $db->prepare('SELECT strategy_build,parameter_hash,selected_leverage,strategy_spec_id,strategy_spec_hash FROM strategy_decisions WHERE strategy_key=? AND decision_id=? LIMIT 1');
          $linkedDecisionStmt->execute([$accountKey, $linkedDecisionId]);
          $linkedDecisionRow = $linkedDecisionStmt->fetch();
          if (is_array($linkedDecisionRow)) {
              if ($linkedBuild === '') $linkedBuild = substr((string)($linkedDecisionRow['strategy_build'] ?? ''), 0, 160);
              if ($linkedParameterHash === '') $linkedParameterHash = substr((string)($linkedDecisionRow['parameter_hash'] ?? ''), 0, 64);
              if ($linkedLeverage === null && is_numeric($linkedDecisionRow['selected_leverage'] ?? null)) $linkedLeverage = (float)$linkedDecisionRow['selected_leverage'];
              if ($linkedSpecId === '') $linkedSpecId = substr((string)($linkedDecisionRow['strategy_spec_id'] ?? ''), 0, 32);
              if ($linkedSpecHash === '') $linkedSpecHash = substr((string)($linkedDecisionRow['strategy_spec_hash'] ?? ''), 0, 64);
          }
      }
      $tradePosition = $currentPosition ?? $previousPosition;
      $tradeTicket = is_array($tradePosition) ? (int)($tradePosition['ticket'] ?? 0) : 0;
      if ($tradeTicket > 0) {
          $tradeDecisionStmt = $db->prepare('UPDATE strategy_trades SET decision_id=?,strategy_spec_id=?,strategy_spec_hash=?,strategy_build=?,parameter_hash=?,entry_leverage=? WHERE strategy_key=? AND position_ticket=?');
          $tradeDecisionStmt->execute([$linkedDecisionId, $linkedSpecId ?: null, $linkedSpecHash, $linkedBuild, $linkedParameterHash, $linkedLeverage, $accountKey, $tradeTicket]);
      }
  }
  // OPPW_V47_4_TRADE_DECISION_LINK_END

$previousAccount = is_array($previousSnapshot['account'] ?? null) ? $previousSnapshot['account'] : [];
    $previousBalance = $number($previousAccount['balance'] ?? 0);
    $balanceDelta = $balance - $previousBalance;
    $samePositionAcrossSnapshots = (
        $previousPosition === null && $currentPosition === null
    ) || (
        $previousPosition !== null && $currentPosition !== null
        && (int)($previousPosition['ticket'] ?? 0) === (int)($currentPosition['ticket'] ?? 0)
    );
    if ($previousSnapshot && abs($balanceDelta) >= 0.01 && !$hasTradeEvent && $samePositionAcrossSnapshots) {
        $flowType = $balanceDelta > 0 ? 'TOP_UP' : 'WITHDRAWAL';
        $reference = 'auto:' . $accountKey . ':' . str_replace([' ', ':', '.'], '', $capturedAt);
        $cashPayloadHash = hash('sha256', implode('|', [$accountKey,$capturedAt,$flowType,(string)$balanceDelta,(string)$balance,'AUTO_DETECTED',$reference]));
        $autoFlow = $db->prepare('INSERT IGNORE INTO account_cash_flows(strategy_key,occurred_at,flow_type,amount,balance_after,source,reference_key,note,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)');
        $autoFlow->execute([$accountKey,$capturedAt,$flowType,$balanceDelta,$balance,'AUTO_DETECTED',$reference,'Balance changed without a trade transition',$cashPayloadHash]);
    }

    $eventStmt = $db->prepare('INSERT IGNORE INTO strategy_events(strategy_key, event_time, level, name, result, message, details, event_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
    foreach ($normalizedEvents as $event) {
      // OPPW_V47_4_DECISION_EVENT_SKIP_BEGIN
      if (in_array($event['name'], ['STRATEGY_DECISION_RECORDED', 'STRATEGY_DECISION_CALCULATED', 'STRATEGY_DECISION_PERSISTED'], true)) continue;
      // OPPW_V47_4_DECISION_EVENT_SKIP_END

        $detailsJson = $event['details'] ? json_encode($event['details'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR) : null;
        oppw_authority_event($db, $accountKey, $event, $event['hash'], $capturedAt);
        $eventStmt->execute([$accountKey, $event['time'], $event['level'], $event['name'], $event['result'], $event['message'], $detailsJson, $event['hash']]);
        if ($eventStmt->rowCount() > 0 && (
            in_array($event['name'], ['CONNECTION_LOST', 'STRATEGY_CYCLE_FAILED', 'POSITION_DISAPPEARED', 'SLTP_REJECTED'], true)
            || str_starts_with($event['name'], 'PROTECTION_')
        )) $insertedCriticalEvents[] = $event;
    }
    if ($previousPosition === null && $currentPosition !== null) {
        oppw_store_trade_transition($db, $accountKey, 'OPENED', $currentPosition, $snapshot, $capturedAt);
    }
    if ($previousPosition !== null && $currentPosition === null) {
        oppw_store_trade_transition($db, $accountKey, 'CLOSED', $previousPosition, $snapshot, $capturedAt, $closedTradeReason);
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

// OPPW_V47_4_DECISION_ACK_RESPONSE_BEGIN
json_response([
    'ok' => true,
    'accountKey' => $accountKey,
    'storedEvents' => count($normalizedEvents),
    'strategyDecisionStored' => $strategyDecisionStored,
    'strategyDecisionId' => $strategyDecisionId,
    'strategySpecificationStored' => $strategySpecificationStored,
    'strategySpecificationId' => $strategySpecificationId,
    'strategySpecificationHash' => $strategySpecificationHash,
], 201);
// OPPW_V47_4_DECISION_ACK_RESPONSE_END
