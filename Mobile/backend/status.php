<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
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

// Normalize v7/v34 snapshots so exposure and OH lifecycle are correct immediately,
// even before the upgraded publisher sends its first v35 snapshot.
if (is_array($snapshot['position'] ?? null) && (!array_key_exists('open', $snapshot['position']) || (bool)$snapshot['position']['open'])) {
    $depositValue = is_numeric($snapshot['account']['deposit'] ?? null) ? (float)$snapshot['account']['deposit'] : 0.0;
    $equityValue = is_numeric($snapshot['account']['equity'] ?? null) ? (float)$snapshot['account']['equity'] : 0.0;
    $snapshot['position']['exposure'] = $depositValue * 20.0;
    $snapshot['position']['effectiveLeverage'] = $equityValue > 0 ? $snapshot['position']['exposure'] / $equityValue : 0.0;

    $nextAction = strtoupper(trim((string)($snapshot['connection']['nextAction'] ?? '')));
    if ($nextAction !== 'OH' && is_array($snapshot['conditions'] ?? null)) {
        $snapshot['conditions'] = array_values(array_filter($snapshot['conditions'], static fn(mixed $condition): bool => is_array($condition) && strtoupper((string)($condition['name'] ?? '')) !== 'OH'));
        if (strtoupper((string)($snapshot['closestCondition']['name'] ?? '')) === 'OH') {
            usort($snapshot['conditions'], static fn(array $a, array $b): int => ((float)($a['distancePoints'] ?? INF)) <=> ((float)($b['distancePoints'] ?? INF)));
            $snapshot['closestCondition'] = $snapshot['conditions'][0] ?? null;
        }
    }
    if (!is_numeric($snapshot['position']['potentialTakeProfit'] ?? null) || (float)$snapshot['position']['potentialTakeProfit'] <= 0) {
        foreach (($snapshot['conditions'] ?? []) as $condition) {
            if (!is_array($condition) || !in_array(strtoupper((string)($condition['name'] ?? '')), ['OH', 'CH'], true)) continue;
            if (is_numeric($condition['targetPrice'] ?? null) && (float)$condition['targetPrice'] > 0) {
                $snapshot['position']['potentialTakeProfit'] = (float)$condition['targetPrice'];
                break;
            }
        }
    }
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
    $dailyRows = $statement->fetchAll();

    $flowStatement = $db->prepare('SELECT occurred_at, flow_type, amount FROM account_cash_flows WHERE strategy_key = ? ORDER BY occurred_at, id');
    $flowStatement->execute([$accountKey]);
    $flows = $flowStatement->fetchAll();
    $flowIndex = 0;
    $cumulativeDeposits = 0.0;
    $rows = [];

    foreach ($dailyRows as $value) {
        $pointTime = new DateTimeImmutable((string)$value['captured_minute'], new DateTimeZone('UTC'));
        while ($flowIndex < count($flows)) {
            $flowTime = new DateTimeImmutable((string)$flows[$flowIndex]['occurred_at'], new DateTimeZone('UTC'));
            if ($flowTime > $pointTime) break;
            $amount = (float)$flows[$flowIndex]['amount'];
            $type = strtoupper((string)$flows[$flowIndex]['flow_type']);
            if (in_array($type, ['INITIAL', 'TOP_UP'], true)) $cumulativeDeposits += abs($amount);
            elseif ($type === 'ADJUSTMENT' && $amount > 0) $cumulativeDeposits += $amount;
            $flowIndex++;
        }
        $rows[] = [
            'time' => atom_datetime($pointTime),
            'value' => (float)$value['equity'],
            'deposits' => $cumulativeDeposits,
        ];
    }
    return downsample_points($rows, 730);
}

function positive_number(array $row, string $field): ?float
{
    return is_numeric($row[$field] ?? null) && (float)$row[$field] > 0 ? (float)$row[$field] : null;
}

function build_market_week_stats(array $rows, string $weekKey, DateTimeZone $localTimezone): ?array
{
    $weekRows = [];
    foreach ($rows as $marketRow) {
        $local = (new DateTimeImmutable((string)$marketRow['captured_minute'], new DateTimeZone('UTC')))->setTimezone($localTimezone);
        if ($local->format('o-\WW') === $weekKey) $weekRows[] = [$marketRow, $local];
    }
    if (!$weekRows) return null;

    $weekOpen = null;
    $weekOpenDate = '';
    $weeklyHigh = null;
    $weeklyLow = null;
    $weeklyClose = null;
    $currentPrice = null;
    $lastPointAt = '';
    $days = [];

    foreach ($weekRows as [$row, $local]) {
        $regular = stripos((string)($row['phase'] ?? ''), 'regular') !== false;
        $price = positive_number($row, 'current_price') ?? positive_number($row, 'bid') ?? positive_number($row, 'ask');
        $open = positive_number($row, 'm1_open') ?? $price;
        $high = positive_number($row, 'm1_high') ?? $price;
        $low = positive_number($row, 'm1_low') ?? $price;
        $close = positive_number($row, 'm1_close') ?? $price;
        $dayKey = $local->format('Y-m-d');

        if (!isset($days[$dayKey])) {
            $days[$dayKey] = ['open' => null, 'high' => null, 'low' => null, 'close' => null, 'last' => ''];
        }
        if ($regular && $days[$dayKey]['open'] === null && $open !== null) $days[$dayKey]['open'] = $open;
        if ($high !== null) $days[$dayKey]['high'] = $days[$dayKey]['high'] === null ? $high : max($days[$dayKey]['high'], $high);
        if ($low !== null) $days[$dayKey]['low'] = $days[$dayKey]['low'] === null ? $low : min($days[$dayKey]['low'], $low);
        if ($close !== null) $days[$dayKey]['close'] = $close;
        $days[$dayKey]['last'] = $local->format(DATE_ATOM);

        if ($regular && $weekOpen === null && $open !== null) {
            $weekOpen = $open;
            $weekOpenDate = $dayKey;
        }
        if ($high !== null) $weeklyHigh = $weeklyHigh === null ? $high : max($weeklyHigh, $high);
        if ($low !== null) $weeklyLow = $weeklyLow === null ? $low : min($weeklyLow, $low);
        if ($close !== null) $weeklyClose = $close;
        if ($price !== null) $currentPrice = $price;
        $lastPointAt = $local->format(DATE_ATOM);
    }

    if ($weekOpen === null) {
        foreach ($days as $dayKey => $day) {
            if ($day['open'] !== null) {
                $weekOpen = (float)$day['open'];
                $weekOpenDate = $dayKey;
                break;
            }
        }
    }

    $latestDayDate = $days ? array_key_last($days) : '';
    $latestDay = $latestDayDate !== '' ? $days[$latestDayDate] : null;
    $relative = static fn(?float $value): ?float => $weekOpen !== null && $value !== null ? ($value / $weekOpen - 1.0) * 100.0 : null;

    return [
        'week' => $weekKey,
        'currentPrice' => $currentPrice,
        'weekOpen' => $weekOpen,
        'weekOpenDate' => $weekOpenDate,
        'weeklyHigh' => $weeklyHigh,
        'weeklyLow' => $weeklyLow,
        'weeklyClose' => $weeklyClose,
        'weeklyHighPercent' => $relative($weeklyHigh),
        'weeklyLowPercent' => $relative($weeklyLow),
        'weeklyClosePercent' => $relative($weeklyClose),
        'dailyDate' => $latestDayDate,
        'dailyOpen' => $latestDay !== null && $latestDay['open'] !== null ? (float)$latestDay['open'] : null,
        'dailyHigh' => $latestDay !== null && $latestDay['high'] !== null ? (float)$latestDay['high'] : null,
        'dailyLow' => $latestDay !== null && $latestDay['low'] !== null ? (float)$latestDay['low'] : null,
        'dailyClose' => $latestDay !== null && $latestDay['close'] !== null ? (float)$latestDay['close'] : null,
        'dailyHighPercent' => $latestDay !== null ? $relative($latestDay['high'] === null ? null : (float)$latestDay['high']) : null,
        'dailyLowPercent' => $latestDay !== null ? $relative($latestDay['low'] === null ? null : (float)$latestDay['low']) : null,
        'dailyClosePercent' => $latestDay !== null ? $relative($latestDay['close'] === null ? null : (float)$latestDay['close']) : null,
        'lastPointAt' => $lastPointAt,
        // Backward-compatible aliases for older app versions.
        'fridayOpen' => $weekOpen,
        'dailyLowDate' => $latestDayDate,
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

$eventTypesStmt = $db->prepare('SELECT DISTINCT name FROM strategy_events WHERE strategy_key = ? ORDER BY name');
$eventTypesStmt->execute([$accountKey]);
$eventTypes = array_map(static fn(array $event): string => (string)$event['name'], $eventTypesStmt->fetchAll());

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
    'eventTypes' => $eventTypes,
]);
