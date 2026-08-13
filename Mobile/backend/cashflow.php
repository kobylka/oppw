<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('POST');
require_write_token();

$data = request_json();
$db = pdo();
$accountKey = trim((string)($data['accountKey'] ?? ''));
$amount = $data['amount'] ?? null;
$balanceAfter = $data['balanceAfter'] ?? null;
$type = strtoupper(trim((string)($data['type'] ?? ((float)$amount >= 0 ? 'TOP_UP' : 'WITHDRAWAL'))));
if ($accountKey === '' || !is_numeric($amount) || !is_numeric($balanceAfter)) json_response(['ok' => false, 'error' => 'accountKey, amount and balanceAfter are required'], 400);
if (!in_array($type, ['TOP_UP', 'WITHDRAWAL', 'TAX', 'ADJUSTMENT'], true)) json_response(['ok' => false, 'error' => 'Unsupported cash-flow type'], 400);
$normalizedAmount = (float)$amount;
$normalizedBalanceAfter = (float)$balanceAfter;
if (!is_finite($normalizedAmount) || !is_finite($normalizedBalanceAfter)) json_response(['ok' => false, 'error' => 'amount and balanceAfter must be finite'], 400);
if ($type === 'TAX') {
    if (abs($normalizedAmount) <= 1.0e-15) json_response(['ok' => false, 'error' => 'Tax amount must be non-zero'], 400);
    $normalizedAmount = -abs($normalizedAmount);
}

$accountStmt = $db->prepare('SELECT 1 FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);

$occurredAt = normalize_datetime($data['occurredAt'] ?? null);
$reference = trim((string)($data['referenceKey'] ?? 'manual:' . $accountKey . ':' . bin2hex(random_bytes(8))));
$reference = substr($reference, 0, 100);
$reference = $reference !== '' ? $reference : 'manual:' . $accountKey . ':' . bin2hex(random_bytes(8));
$note = substr((string)($data['note'] ?? ''), 0, 255);
$payloadHash = hash('sha256', implode('|', [$accountKey,$occurredAt,$type,(string)$normalizedAmount,(string)$normalizedBalanceAfter,'MANUAL_API',$reference,$note]));
$stmt = $db->prepare('INSERT INTO account_cash_flows(strategy_key,occurred_at,flow_type,amount,balance_after,source,reference_key,note,payload_hash) VALUES (?,?,?,?,?,?,?,?,?)');
$created = false;
try {
    $stmt->execute([$accountKey,$occurredAt,$type,$normalizedAmount,$normalizedBalanceAfter,'MANUAL_API',$reference,$note,$payloadHash]);
    $created = true;
} catch (PDOException $error) {
    if ((string)$error->getCode() !== '23000') throw $error;
    $storedStmt = $db->prepare('SELECT payload_hash FROM account_cash_flows WHERE strategy_key = ? AND reference_key = ? LIMIT 1');
    $storedStmt->execute([$accountKey,$reference]);
    $storedHash = $storedStmt->fetchColumn();
    if (!is_string($storedHash) || !hash_equals($payloadHash, $storedHash)) {
        json_response(['ok' => false, 'error' => 'Cash-flow reference conflicts with immutable content'], 409);
    }
}
json_response([
    'ok' => true,
    'created' => $created,
    'cashFlow' => [
        'accountKey' => $accountKey,
        'type' => $type,
        'amount' => $normalizedAmount,
        'balanceAfter' => $normalizedBalanceAfter,
        'occurredAt' => $occurredAt,
        'referenceKey' => $reference,
    ],
], $created ? 201 : 200);
