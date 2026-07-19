<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('POST');
$data = read_json_body();
$accountKey = trim((string)($data['accountKey'] ?? ''));
$session = require_mobile_session($accountKey !== '' ? $accountKey : null);
if ($accountKey === '') json_response(['ok'=>false,'error'=>'accountKey required'],400);
$db = pdo();
$permission = $db->prepare('SELECT 1 FROM monitor_device_accounts WHERE device_id=? AND account_key=?');
$permission->execute([$session['device_id'],$accountKey]);
if (!$permission->fetchColumn()) json_response(['ok'=>false,'error'=>'Forbidden for selected account'],403);
$executionId = substr(trim((string)($data['executionId'] ?? '')),0,64);
if ($executionId === '') json_response(['ok'=>false,'error'=>'executionId required'],400);
$deviceReceivedAt = trim((string)($data['receivedAt'] ?? ''));
$receivedAt = normalize_datetime(null);
$snapshotGeneratedAt = trim((string)($data['snapshotGeneratedAt'] ?? ''));
$latencyMs = null;
if ($snapshotGeneratedAt !== '') {
    try { $latencyMs = max(0.0,(new DateTimeImmutable($receivedAt))->format('Uv')-(new DateTimeImmutable($snapshotGeneratedAt))->format('Uv')); } catch (Throwable) {}
}
$details = [
    'execution_id'=>$executionId,'decision_id'=>substr((string)($data['decisionId'] ?? ''),0,64),
    'position_ticket'=>(int)($data['positionTicket'] ?? 0),'stage'=>'MOBILE_RECEIPT','event_at'=>$receivedAt,
    'snapshot_generated_at'=>$snapshotGeneratedAt,'device_received_at'=>$deviceReceivedAt,'latency_ms'=>$latencyMs,'device_id'=>$session['device_id'],
];
$message = sprintf('EVENT EXECUTION_STAGE execution_id=%s decision_id=%s stage=MOBILE_RECEIPT position_ticket=%d latency_ms=%s', $details['execution_id'] ?: 'none', $details['decision_id'] ?: 'none', $details['position_ticket'], $latencyMs === null ? 'none' : (string)$latencyMs);
$hash = hash('sha256',$accountKey.'|'.$session['device_id'].'|'.$executionId.'|MOBILE_RECEIPT');
$statement = $db->prepare("INSERT IGNORE INTO strategy_events(strategy_key,event_time,level,name,result,message,details,event_hash) VALUES (?,?,'INFO','EXECUTION_STAGE',TRUE,?,?,?)");
$statement->execute([$accountKey,$receivedAt,substr($message,0,1000),json_encode($details,JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),$hash]);
json_response(['ok'=>true,'receivedAt'=>atom_datetime(new DateTimeImmutable($receivedAt,new DateTimeZone('UTC'))),'latencyMs'=>$latencyMs]);
