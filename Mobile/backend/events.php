<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
$db = pdo();
$accountKey = trim((string)($_GET['account'] ?? ''));
if ($accountKey === '') json_response(['ok' => false, 'error' => 'account required'], 400);
require_mobile_session($accountKey);

$limit = max(20, min(150, (int)($_GET['limit'] ?? 75)));
$beforeId = max(0, (int)($_GET['before_id'] ?? 0));
$buySellOnly = filter_var($_GET['buy_sell_only'] ?? false, FILTER_VALIDATE_BOOLEAN);
$hideRoutine = filter_var($_GET['hide_routine'] ?? false, FILTER_VALIDATE_BOOLEAN);
$eventName = trim((string)($_GET['event_name'] ?? ''));

$filterWhere = ['strategy_key = ?'];
$filterParams = [$accountKey];
if ($buySellOnly) {
    $filterWhere[] = "name IN ('BUY_REQUEST','BUY_ACCEPTED','BUY_REJECTED','BUY_CHECK_REJECTED','BUY_DRY_RUN','BUY_SKIPPED','SELL_REQUEST','SELL_ACCEPTED','SELL_REJECTED','SELL_CHECK_REJECTED','SELL_DRY_RUN','POSITION_CLOSED')";
}
if ($eventName !== '') {
    if (strtoupper($eventName) === 'POSITION_IS_OPEN') {
        $filterWhere[] = "name IN ('POSITION_OPEN','POSITION_IS_OPEN')";
    } else {
        $filterWhere[] = 'name = ?';
        $filterParams[] = $eventName;
    }
} elseif ($hideRoutine) {
    $filterWhere[] = "name NOT IN ('POSITION_OPEN','POSITION_IS_OPEN','ENTRY_SIGNAL_OPEN_AVAILABLE','EXIT_LATCH_CLEAR','OH','CH') AND name NOT LIKE 'TSL%'";
}

$countStmt = $db->prepare('SELECT COUNT(*) FROM strategy_events WHERE ' . implode(' AND ', $filterWhere));
$countStmt->execute($filterParams);
$totalMatching = (int)$countStmt->fetchColumn();

$where = $filterWhere;
$params = $filterParams;
if ($beforeId > 0) {
    $where[] = 'id < ?';
    $params[] = $beforeId;
}

$sql = 'SELECT id, event_time, level, name, result, message FROM strategy_events WHERE ' . implode(' AND ', $where) . ' ORDER BY id DESC LIMIT ' . ($limit + 1);
$stmt = $db->prepare($sql);
$stmt->execute($params);
$rows = $stmt->fetchAll();
$hasMore = count($rows) > $limit;
if ($hasMore) array_pop($rows);

$events = array_map(static function (array $event): array {
    $name = strtoupper((string)$event['name']) === 'POSITION_OPEN' ? 'POSITION_IS_OPEN' : (string)$event['name'];
    return [
        'id' => (int)$event['id'],
        'time' => atom_datetime(new DateTimeImmutable((string)$event['event_time'], new DateTimeZone('UTC'))),
        'level' => (string)$event['level'],
        'name' => $name,
        'result' => $event['result'] === null ? null : (bool)$event['result'],
        'message' => (string)$event['message'],
    ];
}, $rows);

json_response([
    'ok' => true,
    'events' => $events,
    'hasMore' => $hasMore,
    'nextBeforeId' => $events ? (int)end($events)['id'] : null,
    'totalMatching' => $totalMatching,
]);
