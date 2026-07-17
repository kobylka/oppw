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
if (!in_array($type, ['TOP_UP', 'WITHDRAWAL', 'ADJUSTMENT'], true)) json_response(['ok' => false, 'error' => 'Unsupported cash-flow type'], 400);

$accountStmt = $db->prepare('SELECT 1 FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
$accountStmt->execute([$accountKey]);
if (!$accountStmt->fetchColumn()) json_response(['ok' => false, 'error' => 'Unknown or disabled account'], 404);

$occurredAt = normalize_datetime($data['occurredAt'] ?? null);
$reference = trim((string)($data['referenceKey'] ?? 'manual:' . $accountKey . ':' . bin2hex(random_bytes(8))));
$stmt = $db->prepare('INSERT INTO account_cash_flows(strategy_key, occurred_at, flow_type, amount, balance_after, source, reference_key, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
$stmt->execute([$accountKey, $occurredAt, $type, (float)$amount, (float)$balanceAfter, 'MANUAL_API', substr($reference, 0, 100), substr((string)($data['note'] ?? ''), 0, 255)]);
json_response(['ok' => true], 201);
