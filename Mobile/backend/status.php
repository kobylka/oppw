<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
$cfg = config();
$db = pdo();
$requested = trim((string)($_GET['account'] ?? ''));
$session = require_mobile_session($requested !== '' ? $requested : null);

$accountKey = $requested;
if ($accountKey === '') {
    $defaultStmt = $db->prepare(
        'SELECT a.account_key
           FROM monitor_device_accounts da
           JOIN monitor_accounts a ON a.account_key = da.account_key
          WHERE da.device_id = ? AND a.enabled = TRUE
          ORDER BY a.is_default DESC, a.sort_order, a.display_name
          LIMIT 1'
    );
    $defaultStmt->execute([$session['device_id']]);
    $accountKey = (string)($defaultStmt->fetchColumn() ?: '');
}
if ($accountKey === '') json_response(['ok' => false, 'error' => 'No permitted account configured'], 404);

$accountStmt = $db->prepare(
    'SELECT a.account_key, a.display_name, a.account_type, a.broker_account_id
       FROM monitor_device_accounts da
       JOIN monitor_accounts a ON a.account_key = da.account_key
      WHERE da.device_id = ? AND a.account_key = ? AND a.enabled = TRUE'
);
$accountStmt->execute([$session['device_id'], $accountKey]);
$account = $accountStmt->fetch();
if (!$account) json_response(['ok' => false, 'error' => 'Forbidden for selected account'], 403);

$stmt = $db->prepare('SELECT payload, captured_at FROM strategy_snapshots WHERE strategy_key = ? ORDER BY id DESC LIMIT 1');
$stmt->execute([$accountKey]);
$row = $stmt->fetch();
if (!$row) json_response(['ok' => false, 'error' => 'No snapshot available for selected account'], 404);

try {
    $snapshot = json_decode((string)$row['payload'], true, 512, JSON_THROW_ON_ERROR);
} catch (JsonException) {
    json_response(['ok' => false, 'error' => 'Stored snapshot is invalid'], 500);
}
$limit = max(1, min(200, (int)$cfg['event_limit']));
$eventsStmt = $db->prepare("SELECT id, event_time, level, name, result, message FROM strategy_events WHERE strategy_key = ? ORDER BY id DESC LIMIT $limit");
$eventsStmt->execute([$accountKey]);
$events = array_map(static function (array $event): array {
    return [
        'id' => (int)$event['id'],
        'time' => atom_datetime(new DateTimeImmutable((string)$event['event_time'], new DateTimeZone('UTC'))),
        'level' => (string)$event['level'],
        'name' => (string)$event['name'],
        'result' => $event['result'] === null ? null : (bool)$event['result'],
        'message' => (string)$event['message'],
    ];
}, $eventsStmt->fetchAll());

json_response([
    'ok' => true,
    'generatedAt' => atom_datetime(utc_now()),
    'selectedAccount' => [
        'key' => (string)$account['account_key'],
        'displayName' => (string)$account['display_name'],
        'accountType' => (string)$account['account_type'],
        'brokerAccountId' => (string)$account['broker_account_id'],
    ],
    'snapshot' => $snapshot,
    'events' => $events,
]);
