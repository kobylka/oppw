<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('GET');

$requested = trim((string)($_GET['account'] ?? ''));
$session = require_mobile_session($requested !== '' ? $requested : null);
$db = pdo();
$accountKey = $requested;
if ($accountKey === '') {
    $statement = $db->prepare('SELECT a.account_key FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key WHERE da.device_id=? AND a.enabled=TRUE ORDER BY a.is_default DESC,a.sort_order,a.display_name LIMIT 1');
    $statement->execute([$session['device_id']]);
    $accountKey = (string)($statement->fetchColumn() ?: '');
}
if ($accountKey === '') json_response(['ok' => false, 'error' => 'No permitted account configured'], 404);
$permission = $db->prepare('SELECT 1 FROM monitor_device_accounts da JOIN monitor_accounts a ON a.account_key=da.account_key WHERE da.device_id=? AND a.account_key=? AND a.enabled=TRUE');
$permission->execute([$session['device_id'], $accountKey]);
if (!$permission->fetchColumn()) json_response(['ok' => false, 'error' => 'Forbidden for selected account'], 403);
$limit = max(1, min(100, (int)($_GET['limit'] ?? 20)));
$stmt = $db->prepare(
    'SELECT s.spec_id,s.spec_hash,s.spec_key,s.spec_version,s.effective_from,s.created_at,
            s.strategy_build,s.execution_symbol,s.signal_symbol,s.document,a.assigned_at
       FROM strategy_account_spec_assignments a
       JOIN strategy_specifications s ON s.spec_id=a.spec_id
      WHERE a.strategy_key=?
      ORDER BY a.assigned_at DESC,a.id DESC LIMIT ' . $limit
);
$stmt->execute([$accountKey]);
$items = [];
foreach ($stmt->fetchAll() as $row) {
    $document = [];
    try { $document = json_decode((string)$row['document'], true, 512, JSON_THROW_ON_ERROR); } catch (Throwable) {}
    $items[] = [
        'specId' => (string)$row['spec_id'], 'specHash' => (string)$row['spec_hash'],
        'specKey' => (string)$row['spec_key'], 'specVersion' => (string)$row['spec_version'],
        'effectiveFrom' => atom_datetime(new DateTimeImmutable((string)$row['effective_from'], new DateTimeZone('UTC'))),
        'createdAt' => atom_datetime(new DateTimeImmutable((string)$row['created_at'], new DateTimeZone('UTC'))),
        'assignedAt' => atom_datetime(new DateTimeImmutable((string)$row['assigned_at'], new DateTimeZone('UTC'))),
        'build' => (string)$row['strategy_build'],
        'executionSymbol' => (string)$row['execution_symbol'],
        'signalSymbol' => (string)$row['signal_symbol'], 'document' => $document,
    ];
}
json_response(['ok' => true, 'accountKey' => $accountKey, 'specifications' => $items]);
