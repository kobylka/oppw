<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_method('GET');

$db = pdo();
$session = require_access_session($db);
$requested = trim((string)($_GET['account'] ?? ''));
$allowed = array_values(array_filter(array_map('strval', $session['accounts'] ?? [])));
if ($requested === '' || !in_array($requested, $allowed, true)) {
    if (count($allowed) !== 1) json_response(['ok' => false, 'error' => 'Accessible account required'], 400);
    $requested = $allowed[0];
}
$limit = max(1, min(100, (int)($_GET['limit'] ?? 20)));
$stmt = $db->prepare(
    'SELECT s.spec_id,s.spec_hash,s.spec_key,s.spec_version,s.effective_from,s.created_at,
            s.strategy_build,s.execution_symbol,s.signal_symbol,s.document,a.assigned_at
       FROM strategy_account_spec_assignments a
       JOIN strategy_specifications s ON s.spec_id=a.spec_id
      WHERE a.strategy_key=?
      ORDER BY a.assigned_at DESC,a.id DESC LIMIT ' . $limit
);
$stmt->execute([$requested]);
$items = [];
foreach ($stmt->fetchAll() as $row) {
    $document = [];
    try { $document = json_decode((string)$row['document'], true, 512, JSON_THROW_ON_ERROR); } catch (Throwable) {}
    $items[] = [
        'specId' => (string)$row['spec_id'], 'specHash' => (string)$row['spec_hash'],
        'specKey' => (string)$row['spec_key'], 'specVersion' => (string)$row['spec_version'],
        'effectiveFrom' => atom_datetime((string)$row['effective_from']),
        'createdAt' => atom_datetime((string)$row['created_at']),
        'assignedAt' => atom_datetime((string)$row['assigned_at']),
        'build' => (string)$row['strategy_build'],
        'executionSymbol' => (string)$row['execution_symbol'],
        'signalSymbol' => (string)$row['signal_symbol'], 'document' => $document,
    ];
}
json_response(['ok' => true, 'accountKey' => $requested, 'specifications' => $items]);
