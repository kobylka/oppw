<?php
declare(strict_types=1);

require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json(524288);
$db = pdo();
$accountKey = trim((string)($data['accountKey'] ?? $data['strategyKey'] ?? ''));
if ($accountKey === '') {
    json_response(['ok' => false, 'error' => 'accountKey required'], 400);
}

$accountStmt = $db->prepare(
    'SELECT account_key, display_name
       FROM monitor_accounts
      WHERE account_key = ? AND enabled = TRUE'
);
$accountStmt->execute([$accountKey]);
$monitorAccount = $accountStmt->fetch();
if (!$monitorAccount) {
    json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 400);
}

require_coordination_actor($db, $accountKey, $data['coordination'] ?? null, 'events');
$events = isset($data['events']) && is_array($data['events']) ? $data['events'] : null;
if ($events === null) {
    json_response(['ok' => false, 'error' => 'events array required'], 400);
}

$normalized = [];
foreach (array_slice($events, 0, 5000) as $event) {
    if (!is_array($event)) continue;
    $name = strtoupper(trim((string)($event['name'] ?? 'EVENT')));
    if (in_array($name, [
        'STRATEGY_DECISION_RECORDED',
        'STRATEGY_DECISION_CALCULATED',
        'STRATEGY_DECISION_PERSISTED',
    ], true)) continue;

    $eventTime = normalize_datetime($event['time'] ?? null);
    $message = substr((string)($event['message'] ?? ''), 0, 1000);
    $normalized[] = [
        'time' => $eventTime,
        'level' => substr((string)($event['level'] ?? 'INFO'), 0, 16),
        'name' => substr($name, 0, 100),
        'result' => array_key_exists('result', $event) && $event['result'] !== null
            ? (int)(bool)$event['result']
            : null,
        'message' => $message,
        'details' => is_array($event['details'] ?? null) ? $event['details'] : [],
        'hash' => hash('sha256', $accountKey . '|' . $eventTime . '|' . $name . '|' . $message),
    ];
}

$inserted = 0;
$critical = [];
$db->beginTransaction();
try {
    $stmt = $db->prepare(
        'INSERT IGNORE INTO strategy_events(
            strategy_key, event_time, level, name, result, message, details, event_hash
         ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
    );
    foreach ($normalized as $event) {
        $detailsJson = $event['details']
            ? json_encode($event['details'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR)
            : null;
        $stmt->execute([
            $accountKey,
            $event['time'],
            $event['level'],
            $event['name'],
            $event['result'],
            $event['message'],
            $detailsJson,
            $event['hash'],
        ]);
        if ($stmt->rowCount() <= 0) continue;
        $inserted++;
        if (in_array($event['name'], [
            'CONNECTION_LOST',
            'STRATEGY_CYCLE_FAILED',
            'POSITION_DISAPPEARED',
            'SLTP_REJECTED',
        ], true) || str_starts_with($event['name'], 'PROTECTION_')) {
            $critical[] = $event;
        }
    }
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    error_log('OPPW events ingest failed: ' . $e->getMessage());
    json_response(['ok' => false, 'error' => 'Database write failed'], 500);
}

$displayName = (string)$monitorAccount['display_name'];
foreach ($critical as $event) {
    send_account_push(
        $db,
        $accountKey,
        'event:' . $event['hash'],
        $displayName . ': ' . $event['name'],
        $event['message'],
        ['type' => $event['name']]
    );
}

json_response([
    'ok' => true,
    'accountKey' => $accountKey,
    'receivedEvents' => count($normalized),
    'storedEvents' => $inserted,
], 201);
