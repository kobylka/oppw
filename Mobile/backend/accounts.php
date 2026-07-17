<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';
require_token('read');

$db = pdo();
$stmt = $db->query(
    'SELECT a.account_key, a.display_name, a.account_type, a.broker_account_id, a.is_default,
            s.payload, s.captured_at
       FROM monitor_accounts a
       LEFT JOIN strategy_snapshots s ON s.id = (
            SELECT s2.id FROM strategy_snapshots s2
             WHERE s2.strategy_key = a.account_key
             ORDER BY s2.id DESC LIMIT 1
       )
      WHERE a.enabled = TRUE
      ORDER BY a.sort_order, a.display_name'
);

$accounts = array_map(static function (array $row): array {
    $snapshot = $row['payload'] ? json_decode((string)$row['payload'], true) : null;
    $connection = is_array($snapshot) && isset($snapshot['connection']) && is_array($snapshot['connection']) ? $snapshot['connection'] : [];
    return [
        'key' => (string)$row['account_key'],
        'displayName' => (string)$row['display_name'],
        'accountType' => (string)$row['account_type'],
        'brokerAccountId' => (string)$row['broker_account_id'],
        'isDefault' => (bool)$row['is_default'],
        'connected' => (bool)($connection['connected'] ?? false),
        'health' => (string)($connection['health'] ?? 'NO DATA'),
        'lastSync' => isset($connection['lastSync']) ? (string)$connection['lastSync'] : '',
    ];
}, $stmt->fetchAll());

json_response([
    'ok' => true,
    'generatedAt' => (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format(DATE_ATOM),
    'accounts' => $accounts,
]);
