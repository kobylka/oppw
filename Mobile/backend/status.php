<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_token('read');

$cfg = config();
$db = pdo();
$requested = trim((string)($_GET['account'] ?? ''));
$accountKey = $requested !== '' ? $requested : (string)($cfg['default_account_key'] ?? '');

if ($accountKey === '') {
    $defaultStmt = $db->query('SELECT account_key FROM monitor_accounts WHERE enabled = TRUE ORDER BY is_default DESC, sort_order, display_name LIMIT 1');
    $accountKey = (string)($defaultStmt->fetchColumn() ?: '');
}
if ($accountKey === '') json_response(['ok' => false, 'error' => 'No enabled account configured'], 404);

$accountStmt = $db->prepare('SELECT account_key, display_name, account_type, broker_account_id FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
$account = $accountStmt->fetch();
if (!$account) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);

$stmt = $db->prepare('SELECT payload, captured_at FROM strategy_snapshots WHERE strategy_key = ? ORDER BY id DESC LIMIT 1');
$stmt->execute([$accountKey]);
$row = $stmt->fetch();
if (!$row) json_response(['ok' => false, 'error' => 'No snapshot available for selected account'], 404);

$snapshot = json_decode((string)$row['payload'], true, 512, JSON_THROW_ON_ERROR);
$limit = max(1, min(200, (int)$cfg['event_limit']));
$eventsStmt = $db->prepare("SELECT id, event_time, level, name, result, message FROM strategy_events WHERE strategy_key = ? ORDER BY id DESC LIMIT $limit");
$eventsStmt->execute([$accountKey]);
$events = array_map(static function (array $event): array {
    return [
        'id' => (int)$event['id'],
        'time' => (new DateTimeImmutable($event['event_time'], new DateTimeZone('UTC')))->format(DATE_ATOM),
        'level' => (string)$event['level'],
        'name' => (string)$event['name'],
        'result' => $event['result'] === null ? null : (bool)$event['result'],
        'message' => (string)$event['message'],
    ];
}, $eventsStmt->fetchAll());

json_response([
    'ok' => true,
    'generatedAt' => (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format(DATE_ATOM),
    'selectedAccount' => [
        'key' => (string)$account['account_key'],
        'displayName' => (string)$account['display_name'],
        'accountType' => (string)$account['account_type'],
        'brokerAccountId' => (string)$account['broker_account_id'],
    ],
    'snapshot' => $snapshot,
    'events' => $events,
]);
