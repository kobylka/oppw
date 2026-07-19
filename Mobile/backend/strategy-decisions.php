<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('GET');
$db = pdo();
$requested = trim((string)($_GET['account'] ?? ''));
$session = require_mobile_session($requested !== '' ? $requested : null);
$accountKey = $requested;
if ($accountKey === '') {
    $statement = $db->prepare('SELECT a.account_key FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key WHERE da.device_id=? AND a.enabled=TRUE ORDER BY a.is_default DESC,a.sort_order,a.display_name LIMIT 1');
    $statement->execute([$session['device_id']]);
    $accountKey = (string)($statement->fetchColumn() ?: '');
}
if ($accountKey === '') json_response(['ok'=>false,'error'=>'No permitted account configured'],404);
$permission = $db->prepare('SELECT 1 FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key WHERE da.device_id=? AND a.account_key=? AND a.enabled=TRUE');
$permission->execute([$session['device_id'],$accountKey]);
if (!$permission->fetchColumn()) json_response(['ok'=>false,'error'=>'Forbidden for selected account'],403);
$limit = max(1,min(250,(int)($_GET['limit'] ?? 100)));
$beforeId = max(0,(int)($_GET['before_id'] ?? 0));
$where = 'strategy_key = ?';
$params = [$accountKey];
if ($beforeId > 0) { $where .= ' AND id < ?'; $params[] = $beforeId; }
$sql = "SELECT id,decision_id,decision_week,recorded_at,strategy_build,parameter_hash,decision_type,outcome,selected_leverage,leverage_reason,previous_full_week_change,previous_full_week_source,previous_trade_change,previous_trade_source,symbol,side,proposed_price,proposed_volume,required_deposit,effective_leverage,stop_loss_percent,stop_loss_price,stop_loss_cash,account_return_at_stop_percent,account_loss_cap_applied,error_text,payload FROM strategy_decisions WHERE $where ORDER BY id DESC LIMIT $limit";
$statement = $db->prepare($sql);
$statement->execute($params);
$rows = $statement->fetchAll();
$decisions = [];
foreach ($rows as $row) {
    $payload = [];
    try { $payload = json_decode((string)$row['payload'],true,512,JSON_THROW_ON_ERROR); } catch (Throwable) {}
    $decisions[] = [
        'id'=>(int)$row['id'],'decisionId'=>(string)$row['decision_id'],'decisionWeek'=>(string)$row['decision_week'],'recordedAt'=>atom_datetime(new DateTimeImmutable((string)$row['recorded_at'],new DateTimeZone('UTC'))),
        'build'=>(string)$row['strategy_build'],'parameterHash'=>(string)$row['parameter_hash'],'decision'=>(string)$row['decision_type'],'outcome'=>(string)$row['outcome'],
        'selectedLeverage'=>(float)$row['selected_leverage'],'leverageReason'=>(string)$row['leverage_reason'],
        'previousFullWeekChange'=>(float)$row['previous_full_week_change'],'previousFullWeekSource'=>(string)$row['previous_full_week_source'],
        'previousTradeChange'=>(float)$row['previous_trade_change'],'previousTradeSource'=>(string)$row['previous_trade_source'],
        'symbol'=>(string)$row['symbol'],'side'=>(string)$row['side'],'price'=>$row['proposed_price']!==null?(float)$row['proposed_price']:null,
        'volume'=>$row['proposed_volume']!==null?(float)$row['proposed_volume']:null,'requiredDeposit'=>$row['required_deposit']!==null?(float)$row['required_deposit']:null,
        'effectiveLeverage'=>$row['effective_leverage']!==null?(float)$row['effective_leverage']:null,'stopLossPercent'=>$row['stop_loss_percent']!==null?(float)$row['stop_loss_percent']:null,
        'stopLossPrice'=>$row['stop_loss_price']!==null?(float)$row['stop_loss_price']:null,'stopLossCash'=>$row['stop_loss_cash']!==null?(float)$row['stop_loss_cash']:null,
        'accountReturnAtStopPercent'=>$row['account_return_at_stop_percent']!==null?(float)$row['account_return_at_stop_percent']:null,
        'accountLossCapApplied'=>(bool)$row['account_loss_cap_applied'],'error'=>(string)$row['error_text'],'payload'=>$payload,
    ];
}
json_response(['ok'=>true,'generatedAt'=>atom_datetime(new DateTimeImmutable('now',new DateTimeZone('UTC'))),'accountKey'=>$accountKey,'decisions'=>$decisions,'nextBeforeId'=>$decisions?end($decisions)['id']:null]);
