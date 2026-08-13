<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';

$db = pdo();
$method = strtoupper((string)($_SERVER['REQUEST_METHOD'] ?? 'GET'));
$ruleColumns = [
    'ARITHMETIC_LAST_TWO' => 'arithmetic_last_two_enabled',
    'GAP_MOMENTUM' => 'gap_momentum_enabled',
    'TUESDAY_NORMALIZATION' => 'tuesday_normalization_enabled',
    'PREMARKET_LOW' => 'premarket_low_enabled',
];
$ruleMetadata = [
    'ARITHMETIC_LAST_TWO' => ['label' => 'Last two weeks ≤ −2.00%', 'description' => 'Skip when the arithmetic sum of the last two weekly outcomes is −2.00% or lower.'],
    'GAP_MOMENTUM' => ['label' => 'Gap ≥ 1.00% + momentum 20 ≤ −0.50%', 'description' => 'Treat the gap and 20-session momentum conditions as one rule; Monday defers to Tuesday.'],
    'TUESDAY_NORMALIZATION' => ['label' => 'Tuesday within ±0.50% of Friday', 'description' => 'After a Monday gap-momentum defer, re-enter only when Tuesday opens within ±0.50% of Friday.'],
    'PREMARKET_LOW' => ['label' => 'Premarket range ≥ 0.80% + close in bottom 15%', 'description' => 'Skip only when the premarket range is at least 0.80% and its close is in the bottom 15% of that range.'],
];
$finalSkipStatuses = [
    'SKIP_ARITHMETIC',
    'SKIP_GAP_MOMENTUM',
    'SKIP_PREMARKET_LOW',
    'SKIP_TUESDAY_NOT_NORMALIZED',
];
$validWeekStatuses = array_merge($finalSkipStatuses, ['ENTRY_APPROVED', 'DEFER_TUESDAY', 'TUESDAY_REENTRY']);

$validAccount = static function (mixed $value): string {
    $account = strtoupper(trim((string)$value));
    if ($account === '' || !preg_match('/^[A-Z0-9_:-]{1,64}$/', $account)) {
        json_response(['ok' => false, 'error' => 'valid accountKey required'], 400);
    }
    return $account;
};
$validWeek = static function (mixed $value, bool $required = false): string {
    $week = strtoupper(trim((string)$value));
    if ($week === '' && !$required) return '';
    if (!preg_match('/^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$/', $week)) {
        json_response(['ok' => false, 'error' => 'valid ISO weekKey required'], 400);
    }
    return $week;
};
$ensureAccount = static function (PDO $db, string $account): void {
    $statement = $db->prepare('SELECT 1 FROM monitor_accounts WHERE account_key=? AND enabled=TRUE LIMIT 1');
    $statement->execute([$account]);
    if (!$statement->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);
};
$ensureControls = static function (PDO $db, string $account): void {
    $statement = $db->prepare('INSERT IGNORE INTO strategy_entry_rule_controls(strategy_key) VALUES (?)');
    $statement->execute([$account]);
};
$loadControls = static function (PDO $db, string $account) use ($ruleColumns, $ruleMetadata): array {
    $statement = $db->prepare('SELECT * FROM strategy_entry_rule_controls WHERE strategy_key=? LIMIT 1');
    $statement->execute([$account]);
    $row = $statement->fetch();
    if (!is_array($row)) throw new RuntimeException('Entry-rule controls are unavailable');
    $rules = [];
    foreach ($ruleColumns as $key => $column) {
        $rules[] = [
            'key' => $key,
            'label' => $ruleMetadata[$key]['label'],
            'description' => $ruleMetadata[$key]['description'],
            'enabled' => (bool)$row[$column],
        ];
    }
    return [
        'revision' => (int)$row['revision'],
        'changedAt' => (string)$row['changed_at'],
        'rules' => $rules,
    ];
};
$loadWeekState = static function (PDO $db, string $account, string $week): ?array {
    if ($week === '') return null;
    $statement = $db->prepare(
        'SELECT week_key,status,revision,controls_revision,decision_id,inputs,changed_at
           FROM strategy_entry_rule_week_state WHERE strategy_key=? AND week_key=? LIMIT 1'
    );
    $statement->execute([$account, $week]);
    $row = $statement->fetch();
    if (!is_array($row)) return null;
    try {
        $inputs = json_decode((string)$row['inputs'], true, 64, JSON_THROW_ON_ERROR);
    } catch (Throwable) {
        $inputs = [];
    }
    return [
        'weekKey' => (string)$row['week_key'],
        'status' => (string)$row['status'],
        'revision' => (int)$row['revision'],
        'controlsRevision' => (int)$row['controls_revision'],
        'decisionId' => (string)$row['decision_id'],
        'inputs' => is_array($inputs) ? $inputs : [],
        'changedAt' => (string)$row['changed_at'],
    ];
};
$recentOutcomes = static function (PDO $db, string $account, string $beforeWeek) use ($finalSkipStatuses): array {
    $outcomes = [];
    $skipStatement = $db->prepare(
        'SELECT week_key,status FROM strategy_entry_rule_week_state
          WHERE strategy_key=? AND week_key<? AND status IN (?,?,?,?)
          ORDER BY week_key DESC LIMIT 12'
    );
    $skipStatement->execute([$account, $beforeWeek, ...$finalSkipStatuses]);
    foreach ($skipStatement->fetchAll() as $row) {
        $week = (string)$row['week_key'];
        $outcomes[$week] = [
            'weekKey' => $week,
            'return' => 0.0,
            'source' => (string)$row['status'],
        ];
    }

    $tradeStatement = $db->prepare(
        'SELECT opened_at,open_price,close_price,preleverage_return_percent
           FROM strategy_trades
          WHERE strategy_key=? AND closed_at IS NOT NULL
          ORDER BY opened_at DESC,id DESC LIMIT 24'
    );
    $tradeStatement->execute([$account]);
    $warsaw = new DateTimeZone('Europe/Warsaw');
    $utc = new DateTimeZone('UTC');
    foreach ($tradeStatement->fetchAll() as $row) {
        try {
            $opened = new DateTimeImmutable((string)$row['opened_at'], $utc);
        } catch (Throwable) {
            continue;
        }
        $week = $opened->setTimezone($warsaw)->format('o-\WW');
        if ($week >= $beforeWeek || isset($outcomes[$week])) continue;
        $return = is_numeric($row['preleverage_return_percent'] ?? null)
            ? (float)$row['preleverage_return_percent'] / 100.0
            : null;
        $open = is_numeric($row['open_price'] ?? null) ? (float)$row['open_price'] : 0.0;
        $close = is_numeric($row['close_price'] ?? null) ? (float)$row['close_price'] : 0.0;
        if ($return === null && $open > 0.0 && $close > 0.0) $return = $close / $open - 1.0;
        if ($return === null) continue;
        $outcomes[$week] = [
            'weekKey' => $week,
            'return' => $return,
            'source' => 'strategy_trades.preleverage_return',
        ];
    }
    krsort($outcomes, SORT_STRING);
    return array_slice(array_values($outcomes), 0, 2);
};
$response = static function (
    PDO $db,
    string $account,
    bool $canControl,
    string $week
) use ($loadControls, $loadWeekState, $recentOutcomes): never {
    $controls = $loadControls($db, $account);
    json_response([
        'ok' => true,
        'generatedAt' => atom_datetime(utc_now()),
        'accountKey' => $account,
        'canControl' => $canControl,
        ...$controls,
        'weekState' => $loadWeekState($db, $account, $week),
        'recentOutcomes' => $week !== '' ? $recentOutcomes($db, $account, $week) : [],
    ]);
};

if ($method === 'GET') {
    $account = $validAccount($_GET['accountKey'] ?? $_GET['account'] ?? '');
    $week = $validWeek($_GET['weekKey'] ?? '');
    $provided = bearer_token();
    $writeToken = (string)(config()['write_token'] ?? '');
    if ($provided !== '' && $writeToken !== '' && hash_equals($writeToken, $provided)) {
        require_write_token();
        $ensureAccount($db, $account);
        $ensureControls($db, $account);
        $actor = require_coordination_actor($db, $account, [
            'role' => $_GET['role'] ?? '',
            'ownerId' => $_GET['ownerId'] ?? '',
            'fencingToken' => $_GET['fencingToken'] ?? 0,
        ], 'entry-rules');
        if (!in_array($actor['role'], ['EXECUTOR', 'PUBLISHER'], true)) {
            json_response(['ok' => false, 'error' => 'Executor or publisher lease required'], 409);
        }
        $response($db, $account, false, $week);
    }
    $session = require_mobile_session($account);
    $ensureControls($db, $account);
    $permission = $db->prepare('SELECT can_control_service FROM monitor_device_accounts WHERE device_id=? AND account_key=?');
    $permission->execute([$session['device_id'], $account]);
    $response($db, $account, (bool)$permission->fetchColumn(), $week);
}

if ($method !== 'POST') {
    header('Allow: GET, POST');
    json_response(['ok' => false, 'error' => 'Method not allowed'], 405);
}

$data = request_json(65536);
$action = trim((string)($data['action'] ?? ''));

if ($action === 'setRule') {
    $account = $validAccount($data['accountKey'] ?? '');
    $ruleKey = strtoupper(trim((string)($data['ruleKey'] ?? '')));
    $requestId = strtolower(trim((string)($data['requestId'] ?? '')));
    if (!isset($ruleColumns[$ruleKey])
        || !preg_match('/^[a-f0-9]{32}$/', $requestId)
        || !array_key_exists('enabled', $data)
        || !is_bool($data['enabled'])) {
        json_response(['ok' => false, 'error' => 'valid requestId, ruleKey and boolean enabled required'], 400);
    }
    $session = require_mobile_session($account);
    $ensureControls($db, $account);
    $permission = $db->prepare('SELECT can_control_service FROM monitor_device_accounts WHERE device_id=? AND account_key=?');
    $permission->execute([$session['device_id'], $account]);
    if (!(bool)$permission->fetchColumn()) {
        json_response(['ok' => false, 'error' => 'This device is not permitted to control strategy entry rules'], 403);
    }
    $enabled = (bool)$data['enabled'];
    $column = $ruleColumns[$ruleKey];
    $db->beginTransaction();
    try {
        $now = utc_now();
        $event = $db->prepare(
            'INSERT IGNORE INTO strategy_entry_rule_control_events(request_id,strategy_key,rule_key,enabled,device_id,requested_at)
             VALUES (?,?,?,?,?,?)'
        );
        $event->execute([$requestId, $account, $ruleKey, $enabled ? 1 : 0, $session['device_id'], mysql_datetime($now)]);
        $newRequest = $event->rowCount() === 1;
        if (!$newRequest) {
            $existing = $db->prepare('SELECT strategy_key,rule_key,enabled,device_id FROM strategy_entry_rule_control_events WHERE request_id=? FOR UPDATE');
            $existing->execute([$requestId]);
            $recorded = $existing->fetch();
            if (!is_array($recorded)
                || !hash_equals((string)$recorded['strategy_key'], $account)
                || !hash_equals((string)$recorded['rule_key'], $ruleKey)
                || (bool)$recorded['enabled'] !== $enabled
                || !hash_equals((string)$recorded['device_id'], (string)$session['device_id'])) {
                $db->rollBack();
                json_response(['ok' => false, 'error' => 'requestId was already used for different strategy-control content'], 409);
            }
        }
        if ($newRequest) {
            $update = $db->prepare(
                "UPDATE strategy_entry_rule_controls
                    SET $column=?,revision=revision+1,changed_by_device_id=?,changed_at=?
                  WHERE strategy_key=?"
            );
            $update->execute([$enabled ? 1 : 0, $session['device_id'], mysql_datetime($now), $account]);
        }
        $db->commit();
    } catch (Throwable $error) {
        if ($db->inTransaction()) $db->rollBack();
        error_log('OPPW strategy rule control failed: ' . $error->getMessage());
        json_response(['ok' => false, 'error' => 'Strategy rule control failed'], 503);
    }
    $response($db, $account, true, '');
}

if ($action === 'recordWeekState') {
    require_write_token();
    $account = $validAccount($data['accountKey'] ?? '');
    $week = $validWeek($data['weekKey'] ?? '', true);
    $status = strtoupper(trim((string)($data['status'] ?? '')));
    $requestId = strtolower(trim((string)($data['requestId'] ?? '')));
    $controlsRevision = (int)($data['controlsRevision'] ?? 0);
    $decisionId = substr(trim((string)($data['decisionId'] ?? '')), 0, 64);
    $inputs = $data['inputs'] ?? [];
    if (!in_array($status, $validWeekStatuses, true)
        || !preg_match('/^[a-f0-9]{32}$/', $requestId)
        || $controlsRevision <= 0
        || !is_array($inputs)) {
        json_response(['ok' => false, 'error' => 'valid requestId, weekKey, status and inputs required'], 400);
    }
    $ensureAccount($db, $account);
    $ensureControls($db, $account);
    $actor = require_coordination_actor($db, $account, $data['coordination'] ?? null, 'entry-rules');
    if ($actor['role'] !== 'EXECUTOR') json_response(['ok' => false, 'error' => 'Executor lease required'], 409);
    try {
        $inputsJson = json_encode($inputs, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    } catch (Throwable) {
        json_response(['ok' => false, 'error' => 'inputs must be JSON-compatible'], 400);
    }
    if (strlen($inputsJson) > 16384) json_response(['ok' => false, 'error' => 'inputs payload too large'], 413);
    $payloadHash = hash('sha256', implode('|', [
        $account, $week, $status, (string)$controlsRevision, $decisionId,
        (string)$actor['ownerId'], (string)$actor['fencingToken'], $inputsJson,
    ]));

    $db->beginTransaction();
    try {
        $now = utc_now();
        $event = $db->prepare(
            'INSERT IGNORE INTO strategy_entry_rule_week_events(
                request_id,strategy_key,week_key,status,controls_revision,decision_id,
                owner_id,fencing_token,inputs,payload_hash,recorded_at
             ) VALUES (?,?,?,?,?,?,?,?,?,?,?)'
        );
        $event->execute([
            $requestId, $account, $week, $status, $controlsRevision, $decisionId,
            $actor['ownerId'], $actor['fencingToken'], $inputsJson, $payloadHash, mysql_datetime($now),
        ]);
        $newRequest = $event->rowCount() === 1;
        if (!$newRequest) {
            $existingEvent = $db->prepare('SELECT payload_hash FROM strategy_entry_rule_week_events WHERE request_id=? FOR UPDATE');
            $existingEvent->execute([$requestId]);
            $existingHash = (string)($existingEvent->fetchColumn() ?: '');
            if ($existingHash === '' || !hash_equals($existingHash, $payloadHash)) {
                $db->rollBack();
                json_response(['ok' => false, 'error' => 'requestId was already used for different weekly-rule content'], 409);
            }
        }
        if ($newRequest) {
            $currentControls = $db->prepare('SELECT revision FROM strategy_entry_rule_controls WHERE strategy_key=? FOR UPDATE');
            $currentControls->execute([$account]);
            $currentControlsRevision = (int)($currentControls->fetchColumn() ?: 0);
            if ($currentControlsRevision !== $controlsRevision) {
                $db->rollBack();
                json_response(['ok' => false, 'error' => 'Entry-rule controls changed; reevaluate with the current revision'], 409);
            }
        }
        $state = $db->prepare('SELECT status FROM strategy_entry_rule_week_state WHERE strategy_key=? AND week_key=? FOR UPDATE');
        $state->execute([$account, $week]);
        $currentStatus = $state->fetchColumn();
        $transitionAllowed = $currentStatus === false
            || hash_equals((string)$currentStatus, $status)
            || (hash_equals((string)$currentStatus, 'DEFER_TUESDAY')
                && in_array($status, ['TUESDAY_REENTRY', 'SKIP_TUESDAY_NOT_NORMALIZED'], true));
        if (!$transitionAllowed) {
            $db->rollBack();
            json_response(['ok' => false, 'error' => 'Weekly entry-rule state is already final'], 409);
        }
        if ($currentStatus === false) {
            $insert = $db->prepare(
                'INSERT INTO strategy_entry_rule_week_state(
                    strategy_key,week_key,status,revision,controls_revision,decision_id,inputs,changed_at
                 ) VALUES (?,?,?,1,?,?,?,?)'
            );
            $insert->execute([$account, $week, $status, $controlsRevision, $decisionId, $inputsJson, mysql_datetime($now)]);
        } elseif (!hash_equals((string)$currentStatus, $status)) {
            $update = $db->prepare(
                'UPDATE strategy_entry_rule_week_state
                    SET status=?,revision=revision+1,controls_revision=?,decision_id=?,inputs=?,changed_at=?
                  WHERE strategy_key=? AND week_key=?'
            );
            $update->execute([$status, $controlsRevision, $decisionId, $inputsJson, mysql_datetime($now), $account, $week]);
        }
        $db->commit();
    } catch (Throwable $error) {
        if ($db->inTransaction()) $db->rollBack();
        error_log('OPPW weekly entry-rule state failed: ' . $error->getMessage());
        json_response(['ok' => false, 'error' => 'Weekly entry-rule state failed'], 503);
    }
    $response($db, $account, false, $week);
}

json_response(['ok' => false, 'error' => 'Unknown action'], 400);
