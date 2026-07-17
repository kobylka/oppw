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

function downsample_points(array $rows, int $maximum): array
{
    $count = count($rows);
    if ($count <= $maximum) return $rows;
    $step = (int)ceil($count / $maximum);
    $result = [];
    for ($index = 0; $index < $count; $index += $step) $result[] = $rows[$index];
    if ($result && end($result)['time'] !== end($rows)['time']) $result[] = end($rows);
    return $result;
}

function equity_points(PDO $db, string $accountKey, string $whereSql, int $maximum): array
{
    $sql = "SELECT captured_minute, equity FROM strategy_equity_points WHERE strategy_key = ? $whereSql ORDER BY captured_minute";
    $statement = $db->prepare($sql);
    $statement->execute([$accountKey]);
    $rows = array_map(static fn(array $value): array => [
        'time' => atom_datetime(new DateTimeImmutable((string)$value['captured_minute'], new DateTimeZone('UTC'))),
        'value' => (float)$value['equity'],
    ], $statement->fetchAll());
    return downsample_points($rows, $maximum);
}

function all_time_equity_points(PDO $db, string $accountKey): array
{
    $sql =
        'SELECT p.captured_minute, p.equity
           FROM strategy_equity_points p
           JOIN (
                SELECT DATE(captured_minute) AS day_key, MAX(captured_minute) AS last_time
                  FROM strategy_equity_points
                 WHERE strategy_key = ?
                 GROUP BY DATE(captured_minute)
           ) daily ON daily.last_time = p.captured_minute
          WHERE p.strategy_key = ?
          ORDER BY p.captured_minute';
    $statement = $db->prepare($sql);
    $statement->execute([$accountKey, $accountKey]);
    $rows = array_map(static fn(array $value): array => [
        'time' => atom_datetime(new DateTimeImmutable((string)$value['captured_minute'], new DateTimeZone('UTC'))),
        'value' => (float)$value['equity'],
    ], $statement->fetchAll());
    return downsample_points($rows, 365);
}

function build_market_week_stats(array $rows, string $weekKey, DateTimeZone $localTimezone): ?array
{
    $weekRows = [];
    foreach ($rows as $marketRow) {
        $local = (new DateTimeImmutable((string)$marketRow['captured_minute'], new DateTimeZone('UTC')))->setTimezone($localTimezone);
        if ($local->format('o-\WW') === $weekKey) $weekRows[] = [$marketRow, $local];
    }
    if (!$weekRows) return null;

    $currentPrice = null;
    $fridayOpen = null;
    $weeklyLow = null;
    $dailyLows = [];
    $lastLocal = null;

    foreach ($weekRows as [$marketRow, $local]) {
        $price = is_numeric($marketRow['current_price']) ? (float)$marketRow['current_price'] : null;
        $lowCandidates = [];
        foreach (['m1_low', 'current_price', 'bid'] as $field) {
            if (is_numeric($marketRow[$field] ?? null) && (float)$marketRow[$field] > 0) $lowCandidates[] = (float)$marketRow[$field];
        }
        $low = $lowCandidates ? min($lowCandidates) : null;
        if ($price !== null && $price > 0) $currentPrice = $price;
        if ($low !== null) {
            $weeklyLow = $weeklyLow === null ? $low : min($weeklyLow, $low);
            $dayKey = $local->format('Y-m-d');
            $dailyLows[$dayKey] = isset($dailyLows[$dayKey]) ? min($dailyLows[$dayKey], $low) : $low;
        }
        if ($fridayOpen === null && $local->format('N') === '5' && stripos((string)$marketRow['phase'], 'regular') !== false) {
            $candidate = is_numeric($marketRow['m1_open']) && (float)$marketRow['m1_open'] > 0 ? (float)$marketRow['m1_open'] : $price;
            if ($candidate !== null && $candidate > 0) $fridayOpen = $candidate;
        }
        $lastLocal = $local;
    }

    $dailyLowDate = $dailyLows ? array_key_last($dailyLows) : '';
    $dailyLow = $dailyLowDate !== '' ? $dailyLows[$dailyLowDate] : null;
    $weeklyLowPercent = $fridayOpen !== null && $weeklyLow !== null ? ($weeklyLow / $fridayOpen - 1.0) * 100.0 : null;
    $dailyLowPercent = $fridayOpen !== null && $dailyLow !== null ? ($dailyLow / $fridayOpen - 1.0) * 100.0 : null;

    return [
        'week' => $weekKey,
        'currentPrice' => $currentPrice,
        'fridayOpen' => $fridayOpen,
        'weeklyLow' => $weeklyLow,
        'weeklyLowPercent' => $weeklyLowPercent,
        'dailyLow' => $dailyLow,
        'dailyLowPercent' => $dailyLowPercent,
        'dailyLowDate' => $dailyLowDate,
        'lastPointAt' => $lastLocal?->format(DATE_ATOM) ?? '',
    ];
}

$marketStmt = $db->prepare(
    'SELECT captured_minute, current_price, bid, ask, m1_open, m1_high, m1_low, m1_close, phase
       FROM strategy_market_points
      WHERE strategy_key = ? AND captured_minute >= UTC_TIMESTAMP() - INTERVAL 22 DAY
      ORDER BY captured_minute'
);
$marketStmt->execute([$accountKey]);
$marketRows = $marketStmt->fetchAll();
$warsaw = new DateTimeZone('Europe/Warsaw');
$localNow = utc_now()->setTimezone($warsaw);
$currentWeekKey = $localNow->format('o-\WW');
$previousWeekKey = $localNow->modify('-7 days')->format('o-\WW');
$snapshot['marketStats'] = [
    'currentWeek' => build_market_week_stats($marketRows, $currentWeekKey, $warsaw),
    'previousWeek' => build_market_week_stats($marketRows, $previousWeekKey, $warsaw),
];
$snapshot['equityCurves'] = [
    'daily' => equity_points($db, $accountKey, 'AND captured_minute >= UTC_TIMESTAMP() - INTERVAL 24 HOUR', 144),
    'weekly' => equity_points($db, $accountKey, 'AND captured_minute >= UTC_TIMESTAMP() - INTERVAL 7 DAY', 168),
    'allTime' => all_time_equity_points($db, $accountKey),
];

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
