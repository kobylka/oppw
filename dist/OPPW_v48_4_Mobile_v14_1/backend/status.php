<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_once __DIR__ . '/oppw_latest_trade.php';

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

// v45.3.1: last-trade enrichment is optional and must never break status JSON.
$oppwTradeBufferLevel = ob_get_level();
ob_start();
try {
    $authoritativeLastTrade = oppw_authoritative_last_trade($db, $accountKey);
    if ($authoritativeLastTrade !== null) $snapshot['lastClosedTrade'] = $authoritativeLastTrade;
} catch (Throwable $oppwTradeError) {
    error_log('OPPW status last-trade enrichment failed: ' . $oppwTradeError->getMessage());
} finally {
    while (ob_get_level() > $oppwTradeBufferLevel) ob_end_clean();
}

$serverNowUtc = utc_now();
$warsaw = new DateTimeZone('Europe/Warsaw');
$localNow = $serverNowUtc->setTimezone($warsaw);
$snapshotCapturedAt = new DateTimeImmutable((string)$row['captured_at'], new DateTimeZone('UTC'));
$lastUpdateAgeSeconds = max(0.0, (float)($serverNowUtc->getTimestamp() - $snapshotCapturedAt->getTimestamp()));
$heartbeatStaleSeconds = max(60, (int)(config()['monitor_heartbeat_stale_seconds'] ?? 180));
$priceWarningSeconds = max(10, (int)(config()['monitor_price_warning_seconds'] ?? 60));
$positionValue = $snapshot['position'] ?? null;
$positionOpen = is_array($positionValue) && (!array_key_exists('open', $positionValue) || (bool)$positionValue['open']);
$weekendIdle = !$positionOpen && (int)$localNow->format('N') >= 6;
$heartbeatStatus = $weekendIdle ? 'WEEKEND IDLE' : ($lastUpdateAgeSeconds <= $heartbeatStaleSeconds ? 'RUNNING' : 'STALE');

$lastTickStmt = $db->prepare(
    'SELECT captured_minute
       FROM strategy_market_points
      WHERE strategy_key = ?
        AND (COALESCE(current_price, 0) > 0 OR COALESCE(bid, 0) > 0 OR COALESCE(ask, 0) > 0)
      ORDER BY captured_minute DESC
      LIMIT 1'
);
$lastTickStmt->execute([$accountKey]);
$lastTickRaw = $lastTickStmt->fetchColumn();
$lastTickAt = is_string($lastTickRaw) && $lastTickRaw !== '' ? new DateTimeImmutable($lastTickRaw, new DateTimeZone('UTC')) : null;
$lastTickAgeSeconds = $lastTickAt ? max(0.0, (float)($serverNowUtc->getTimestamp() - $lastTickAt->getTimestamp())) : null;
$priceHealth = $lastTickAgeSeconds === null ? 'UNKNOWN' : ($lastTickAgeSeconds <= $priceWarningSeconds ? 'OK' : 'WARNING');

if (!is_array($snapshot['connection'] ?? null)) $snapshot['connection'] = [];
$snapshot['connection']['heartbeatStatus'] = $heartbeatStatus;
$snapshot['connection']['lastUpdate'] = atom_datetime($snapshotCapturedAt);
$snapshot['connection']['lastUpdateAgeSeconds'] = $lastUpdateAgeSeconds;
$snapshot['connection']['lastTick'] = $lastTickAt ? atom_datetime($lastTickAt) : '';
$snapshot['connection']['us100AgeSeconds'] = $lastTickAgeSeconds;
$snapshot['connection']['health'] = $priceHealth;
if ($weekendIdle) {
    $snapshot['connection']['phase'] = 'Weekend';
    $snapshot['connection']['regime'] = 'None';
    $snapshot['connection']['nextAction'] = 'None';
    $snapshot['connection']['nextActionAt'] = '';
    $snapshot['conditions'] = [];
    $snapshot['closestCondition'] = null;
}

// Normalize v7/v34 snapshots so exposure and OH lifecycle are correct immediately,
// even before the upgraded publisher sends its first v35 snapshot.
if (is_array($snapshot['position'] ?? null) && (!array_key_exists('open', $snapshot['position']) || (bool)$snapshot['position']['open'])) {
    $depositValue = is_numeric($snapshot['account']['deposit'] ?? null) ? (float)$snapshot['account']['deposit'] : 0.0;
    $balanceValue = is_numeric($snapshot['account']['balance'] ?? null) ? (float)$snapshot['account']['balance'] : 0.0;
    $snapshot['position']['exposure'] = $depositValue * 20.0;
    $snapshot['position']['effectiveLeverage'] = $balanceValue > 0 ? $snapshot['position']['exposure'] / $balanceValue : 0.0;

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

// OPPW_V47_3_V13_2_BEGIN
function oppw_valid_iso_day(mixed $value): ?string
{
    $text = trim((string)$value);
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $text)) return null;
    $parsed = DateTimeImmutable::createFromFormat('!Y-m-d', $text, new DateTimeZone('Europe/Warsaw'));
    return $parsed && $parsed->format('Y-m-d') === $text ? $text : null;
}

function oppw_previous_weekday(DateTimeImmutable $localDay): DateTimeImmutable
{
    $candidate = $localDay->modify('-1 day');
    while ((int)$candidate->format('N') > 5) $candidate = $candidate->modify('-1 day');
    return $candidate;
}

function oppw_equity_period_points(
    PDO $db,
    string $accountKey,
    DateTimeImmutable $startLocal,
    DateTimeImmutable $endLocal,
    int $maximum
): array {
    if ($endLocal <= $startLocal) return [];
    $utc = new DateTimeZone('UTC');
    $startUtc = $startLocal->setTimezone($utc);
    $endUtc = $endLocal->setTimezone($utc);
    $startSql = $startUtc->format('Y-m-d H:i:s');
    $endSql = $endUtc->format('Y-m-d H:i:s');

    $baselineStmt = $db->prepare(
        'SELECT captured_minute, equity FROM strategy_equity_points '
        . 'WHERE strategy_key = ? AND captured_minute <= ? '
        . 'ORDER BY captured_minute DESC LIMIT 1'
    );
    $baselineStmt->execute([$accountKey, $startSql]);
    $baseline = $baselineStmt->fetch();

    $pointsStmt = $db->prepare(
        'SELECT captured_minute, equity FROM strategy_equity_points '
        . 'WHERE strategy_key = ? AND captured_minute >= ? AND captured_minute <= ? '
        . 'ORDER BY captured_minute'
    );
    $pointsStmt->execute([$accountKey, $startSql, $endSql]);
    $stored = $pointsStmt->fetchAll();

    $startValue = $baseline && is_numeric($baseline['equity'] ?? null)
        ? (float)$baseline['equity']
        : ($stored && is_numeric($stored[0]['equity'] ?? null) ? (float)$stored[0]['equity'] : null);
    if ($startValue === null) return [];

    $rows = [['time' => atom_datetime($startUtc), 'value' => $startValue]];
    $lastValue = $startValue;
    foreach ($stored as $row) {
        if (!is_numeric($row['equity'] ?? null)) continue;
        $time = new DateTimeImmutable((string)$row['captured_minute'], $utc);
        $lastValue = (float)$row['equity'];
        if ($time <= $startUtc) {
            $rows[0]['value'] = $lastValue;
            continue;
        }
        $rows[] = ['time' => atom_datetime($time), 'value' => $lastValue];
    }

    $endAtom = atom_datetime($endUtc);
    if (!$rows || (string)end($rows)['time'] !== $endAtom) $rows[] = ['time' => $endAtom, 'value' => $lastValue];
    return downsample_points($rows, $maximum);
}

function oppw_selected_equity_periods(
    PDO $db,
    string $accountKey,
    array $snapshot,
    DateTimeImmutable $localNow,
    DateTimeZone $localTimezone
): array {
    $session = is_array($snapshot['market']['session'] ?? null) ? $snapshot['market']['session'] : [];
    $isTradingDay = array_key_exists('isTradingDay', $session)
        ? (bool)$session['isTradingDay']
        : ((int)$localNow->format('N') <= 5 && strtoupper((string)($snapshot['connection']['phase'] ?? '')) !== 'WEEKEND');

    $today = $localNow->setTimezone($localTimezone)->setTime(0, 0, 0);
    $previousTradingDayKey = oppw_valid_iso_day($session['previousTradingDay'] ?? null);
    $previousTradingDay = $previousTradingDayKey !== null
        ? new DateTimeImmutable($previousTradingDayKey . ' 00:00:00', $localTimezone)
        : oppw_previous_weekday($today);

    if ($isTradingDay) {
        $dailyStart = $today;
        $dailyEnd = $localNow;
        $weeklyStart = strategy_week_start($today);
        $weeklyEnd = $localNow;
    } else {
        $dailyStart = $previousTradingDay;
        $dailyEnd = $dailyStart->modify('+1 day');
        $thisMonday = strategy_week_start($today);
        $weeklyStart = $thisMonday->modify('-7 days');
        $weeklyEnd = $thisMonday;
    }

    return [
        'daily' => oppw_equity_period_points($db, $accountKey, $dailyStart, $dailyEnd, 144),
        'weekly' => oppw_equity_period_points($db, $accountKey, $weeklyStart, $weeklyEnd, 168),
    ];
}
// OPPW_V47_3_V13_2_END

function all_time_equity_points(PDO $db, string $accountKey): array
{
    $equitySql =
        'SELECT p.captured_minute, p.balance, p.equity
           FROM strategy_equity_points p
           JOIN (
                SELECT DATE(captured_minute) AS day_key, MAX(captured_minute) AS last_time
                  FROM strategy_equity_points
                 WHERE strategy_key = ?
                 GROUP BY DATE(captured_minute)
           ) daily ON daily.last_time = p.captured_minute
          WHERE p.strategy_key = ?
          ORDER BY p.captured_minute';
    $equityStmt = $db->prepare($equitySql);
    $equityStmt->execute([$accountKey, $accountKey]);
    $equityByDay = [];
    foreach ($equityStmt->fetchAll() as $row) $equityByDay[substr((string)$row['captured_minute'], 0, 10)] = $row;

    $flowStmt = $db->prepare('SELECT occurred_at, flow_type, amount, balance_after FROM account_cash_flows WHERE strategy_key = ? ORDER BY occurred_at, id');
    $flowStmt->execute([$accountKey]);
    $flowsByDay = [];
    $hasPositiveInitial = false;
    foreach ($flowStmt->fetchAll() as $flow) {
        $type = strtoupper((string)$flow['flow_type']);
        $amount = abs((float)$flow['amount']);
        $balanceAfter = is_numeric($flow['balance_after'] ?? null) ? abs((float)$flow['balance_after']) : 0.0;
        if ($type === 'INITIAL' && max($amount, $balanceAfter) > 0) $hasPositiveInitial = true;
        $flowsByDay[substr((string)$flow['occurred_at'], 0, 10)][] = $flow;
    }

    if (!$hasPositiveInitial && $equityByDay) {
        $firstDay = array_key_first($equityByDay);
        $firstRow = $equityByDay[$firstDay];
        $fallbackInitial = is_numeric($firstRow['balance'] ?? null) && (float)$firstRow['balance'] > 0
            ? (float)$firstRow['balance']
            : (float)$firstRow['equity'];
        if ($fallbackInitial > 0) {
            $flowsByDay[$firstDay][] = [
                'occurred_at' => $firstDay . ' 00:00:00',
                'flow_type' => 'INITIAL',
                'amount' => $fallbackInitial,
                'balance_after' => $fallbackInitial,
            ];
        }
    }

    $days = array_values(array_unique(array_merge(array_keys($equityByDay), array_keys($flowsByDay))));
    sort($days, SORT_STRING);
    $cumulativeDeposits = 0.0;
    $lastEquity = null;
    $rows = [];

    foreach ($days as $day) {
        $dayFlows = $flowsByDay[$day] ?? [];
        usort($dayFlows, static fn(array $a, array $b): int => strcmp((string)$a['occurred_at'], (string)$b['occurred_at']));
        $netExternalFlow = 0.0;
        $pointTime = null;
        $balanceAfter = null;
        foreach ($dayFlows as $flow) {
            $flowTime = new DateTimeImmutable((string)$flow['occurred_at'], new DateTimeZone('UTC'));
            $pointTime = $pointTime === null || $flowTime > $pointTime ? $flowTime : $pointTime;
            $rawAmount = (float)$flow['amount'];
            $amount = abs($rawAmount);
            $type = strtoupper((string)$flow['flow_type']);
            $flowBalanceAfter = is_numeric($flow['balance_after'] ?? null) ? (float)$flow['balance_after'] : null;
            if ($type === 'INITIAL') $cumulativeDeposits += $amount > 0 ? $amount : max(0.0, (float)($flowBalanceAfter ?? 0.0));
            elseif ($type === 'TOP_UP') $cumulativeDeposits += $amount;
            elseif ($type === 'ADJUSTMENT' && $rawAmount > 0) $cumulativeDeposits += $rawAmount;
            if ($type === 'TOP_UP') $netExternalFlow += $amount;
            elseif ($type === 'WITHDRAWAL') $netExternalFlow -= $amount;
            elseif ($type === 'ADJUSTMENT') $netExternalFlow += $rawAmount;
            if ($flowBalanceAfter !== null) $balanceAfter = $flowBalanceAfter;
        }

        if (isset($equityByDay[$day])) {
            $equityRow = $equityByDay[$day];
            $pointTime = new DateTimeImmutable((string)$equityRow['captured_minute'], new DateTimeZone('UTC'));
            $equity = (float)$equityRow['equity'];
        } elseif ($lastEquity !== null) {
            $equity = $lastEquity + $netExternalFlow;
        } else {
            $equity = $balanceAfter ?? $cumulativeDeposits;
        }

        $pointTime ??= new DateTimeImmutable($day . ' 23:59:00', new DateTimeZone('UTC'));
        $rows[] = ['time' => atom_datetime($pointTime), 'value' => $equity, 'deposits' => $cumulativeDeposits];
        $lastEquity = $equity;
    }

    if (count($rows) <= 730) return $rows;
    $required = [0 => true, count($rows) - 1 => true];
    for ($index = 1; $index < count($rows); $index++) {
        if ((float)$rows[$index]['deposits'] !== (float)$rows[$index - 1]['deposits']) $required[$index] = true;
    }
    $step = (int)ceil(count($rows) / 730);
    for ($index = 0; $index < count($rows); $index += $step) $required[$index] = true;
    ksort($required, SORT_NUMERIC);
    return array_values(array_map(static fn(int $index): array => $rows[$index], array_keys($required)));
}

function positive_number(array $row, string $field): ?float
{
    return is_numeric($row[$field] ?? null) && (float)$row[$field] > 0 ? (float)$row[$field] : null;
}

function strategy_week_start(DateTimeImmutable $local): DateTimeImmutable
{
    $date = $local->setTime(0, 0);
    $daysSinceMonday = (int)$local->format('N') - 1;
    return $date->modify("-$daysSinceMonday days");
}

function market_point_price(array $row, string $field, ?float $fallback = null): ?float
{
    return positive_number($row, $field) ?? $fallback;
}

function is_regular_market_phase(mixed $phase): bool
{
    $normalized = strtoupper(trim(str_replace(['_', '-'], ' ', (string)$phase)));
    if ($normalized === '') return false;
    return preg_match('/(^|\s)REGULAR(\s|$)/', $normalized) === 1;
}


function build_market_week_stats(array $rows, DateTimeImmutable $weekStart, DateTimeZone $localTimezone): ?array
{
    $weekStartKey = $weekStart->format('Y-m-d');
    $currentWeekKey = strategy_week_start(new DateTimeImmutable('now', $localTimezone))->format('Y-m-d');
    $isCurrentWeek = $weekStartKey === $currentWeekKey;
    $weekRows = []; $regularRows = []; $currentPrice = null;
    foreach ($rows as $row) {
        $local = (new DateTimeImmutable((string)$row['captured_minute'], new DateTimeZone('UTC')))->setTimezone($localTimezone);
        if (strategy_week_start($local)->format('Y-m-d') !== $weekStartKey) continue;
        $weekRows[] = [$row, $local];
        $price = positive_number($row, 'current_price') ?? positive_number($row, 'bid') ?? positive_number($row, 'ask');
        if ($price !== null) $currentPrice = $price;
        if (is_regular_market_phase($row['phase'] ?? '')) $regularRows[] = [$row, $local];
    }
    if (!$weekRows) return null;
    if (!$isCurrentWeek && !$regularRows) $regularRows = $weekRows;
    $weekEnd = $weekStart->modify('+6 days');
    $result = ['week'=>$weekStart->format('d M').' – '.$weekEnd->format('d M Y'),'currentPrice'=>$currentPrice,'weekOpen'=>null,'weekOpenDate'=>'','weeklyHigh'=>null,'weeklyLow'=>null,'weeklyClose'=>null,'weeklyHighPercent'=>null,'weeklyLowPercent'=>null,'weeklyClosePercent'=>null,'dailyDate'=>'','dailyOpen'=>null,'dailyHigh'=>null,'dailyLow'=>null,'dailyClose'=>null,'dailyHighPercent'=>null,'dailyLowPercent'=>null,'dailyClosePercent'=>null,'fridayOpen'=>null,'dailyLowDate'=>''];
    if (!$regularRows) return $result;
    usort($regularRows, static fn(array $a,array $b):int=>$a[1]->getTimestamp()<=>$b[1]->getTimestamp());
    $days=[];
    foreach ($regularRows as [$row,$local]) {
        $day=$local->format('Y-m-d'); $price=positive_number($row,'current_price')??positive_number($row,'bid')??positive_number($row,'ask');
        $open=market_point_price($row,'m1_open',$price); $high=market_point_price($row,'m1_high',$price); $low=market_point_price($row,'m1_low',$price); $close=market_point_price($row,'m1_close',$price);
        if (!isset($days[$day])) $days[$day]=['open'=>$open,'high'=>null,'low'=>null,'close'=>null];
        if ($days[$day]['open']===null&&$open!==null) $days[$day]['open']=$open;
        if ($high!==null) $days[$day]['high']=$days[$day]['high']===null?$high:max((float)$days[$day]['high'],$high);
        if ($low!==null) $days[$day]['low']=$days[$day]['low']===null?$low:min((float)$days[$day]['low'],$low);
        if ($close!==null) $days[$day]['close']=$close;
    }
    ksort($days,SORT_STRING); $firstKey=(string)(array_key_first($days)??''); $lastKey=(string)(array_key_last($days)??'');
    if ($firstKey===''||$lastKey==='') return $result; $first=$days[$firstKey]; $last=$days[$lastKey]; $weekOpen=$first['open']; if ($weekOpen===null) return $result;
    $weeklyHigh=null; $weeklyLow=null; $weeklyClose=null;
    foreach ($days as $day) { if ($day['high']!==null) $weeklyHigh=$weeklyHigh===null?$day['high']:max($weeklyHigh,$day['high']); if ($day['low']!==null) $weeklyLow=$weeklyLow===null?$day['low']:min($weeklyLow,$day['low']); if ($day['close']!==null) $weeklyClose=$day['close']; }
    $relative=static fn(?float $v):?float=>$v!==null&&$weekOpen>0?($v/$weekOpen-1.0)*100.0:null;
    return array_merge($result,['weekOpen'=>(float)$weekOpen,'weekOpenDate'=>$firstKey,'weeklyHigh'=>$weeklyHigh,'weeklyLow'=>$weeklyLow,'weeklyClose'=>$weeklyClose,'weeklyHighPercent'=>$relative($weeklyHigh),'weeklyLowPercent'=>$relative($weeklyLow),'weeklyClosePercent'=>$relative($weeklyClose),'dailyDate'=>$lastKey,'dailyOpen'=>$last['open'],'dailyHigh'=>$last['high'],'dailyLow'=>$last['low'],'dailyClose'=>$last['close'],'dailyHighPercent'=>$relative($last['high']),'dailyLowPercent'=>$relative($last['low']),'dailyClosePercent'=>$relative($last['close']),'fridayOpen'=>(float)$weekOpen,'dailyLowDate'=>$lastKey]);
}

function oppw_restore_market_history_cards(array $marketStats): array
{
    $current=is_array($marketStats['currentWeek']??null)?$marketStats['currentWeek']:null; $previous=is_array($marketStats['previousWeek']??null)?$marketStats['previousWeek']:null;
    if ($current===null||$previous===null) return $marketStats;
    if (!is_numeric($current['weekOpen']??null)&&!is_numeric($current['dailyOpen']??null)&&is_numeric($previous['dailyOpen']??null)) {
        foreach (['dailyDate','dailyOpen','dailyHigh','dailyLow','dailyClose','dailyHighPercent','dailyLowPercent','dailyClosePercent','dailyLowDate'] as $field) $current[$field]=$previous[$field]??null;
        $current['dailySource']='PREVIOUS_COMPLETED_TRADING_DAY';
    }
    $marketStats['currentWeek']=$current; return $marketStats;
}


$marketStmt = $db->prepare(
    'SELECT captured_minute, current_price, bid, ask, m1_open, m1_high, m1_low, m1_close, phase
       FROM strategy_market_points
      WHERE strategy_key = ? AND captured_minute >= UTC_TIMESTAMP() - INTERVAL 35 DAY
      ORDER BY captured_minute'
);
$marketStmt->execute([$accountKey]);
$marketRows = $marketStmt->fetchAll();
$currentWeekStart = strategy_week_start($localNow);
$previousWeekStart = $currentWeekStart->modify('-7 days');
$snapshot['marketStats'] = oppw_restore_market_history_cards([
    'currentWeek' => build_market_week_stats($marketRows, $currentWeekStart, $warsaw),
    'previousWeek' => build_market_week_stats($marketRows, $previousWeekStart, $warsaw),
]);
$oppwEquityPeriods = oppw_selected_equity_periods($db, $accountKey, $snapshot, $localNow, $warsaw);
$snapshot['equityCurves'] = [
    'daily' => $oppwEquityPeriods['daily'],
    'weekly' => $oppwEquityPeriods['weekly'],
    'allTime' => all_time_equity_points($db, $accountKey),
];

$eventTypesStmt = $db->prepare('SELECT DISTINCT name FROM strategy_events WHERE strategy_key = ? ORDER BY name');
$eventTypesStmt->execute([$accountKey]);
$eventTypes = array_values(array_unique(array_map(static fn(array $event): string => strtoupper((string)$event['name']) === 'POSITION_OPEN' ? 'POSITION_IS_OPEN' : (string)$event['name'], $eventTypesStmt->fetchAll())));
sort($eventTypes, SORT_STRING);

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
