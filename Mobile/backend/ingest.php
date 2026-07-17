<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json();
$db = pdo();
$accountKey = trim((string)($data['accountKey'] ?? $data['strategyKey'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'accountKey required'], 400);

$accountStmt = $db->prepare('SELECT account_key FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 400);
if (!isset($data['snapshot']) || !is_array($data['snapshot'])) json_response(['ok' => false, 'error' => 'snapshot object required'], 400);

$capturedAt = normalize_datetime($data['capturedAt'] ?? null);
$payload = json_encode($data['snapshot'], JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
$events = isset($data['events']) && is_array($data['events']) ? $data['events'] : [];

$db->beginTransaction();
try {
    $snapshotStmt = $db->prepare('INSERT INTO strategy_snapshots(strategy_key, captured_at, payload) VALUES (?, ?, ?)');
    $snapshotStmt->execute([$accountKey, $capturedAt, $payload]);

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
    $db->rollBack();
    json_response(['ok' => false, 'error' => 'Database write failed'], 500);
}

json_response(['ok' => true, 'accountKey' => $accountKey, 'storedEvents' => count($events)], 201);
