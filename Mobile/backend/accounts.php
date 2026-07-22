<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
$session = require_mobile_session();
$db = pdo();
$stmt = $db->prepare(
    'SELECT a.account_key, a.display_name, a.account_type, a.broker_account_id, a.is_default,
            da.can_control_service,
            s.payload, s.captured_at,
            (SELECT MAX(mp.captured_minute)
               FROM strategy_market_points mp
              WHERE mp.strategy_key = a.account_key
                AND (COALESCE(mp.current_price, 0) > 0 OR COALESCE(mp.bid, 0) > 0 OR COALESCE(mp.ask, 0) > 0)) AS last_tick_at
       FROM monitor_device_accounts da
       JOIN monitor_accounts a ON a.account_key = da.account_key
       LEFT JOIN strategy_snapshots s ON s.id = (
            SELECT s2.id FROM strategy_snapshots s2
             WHERE s2.strategy_key = a.account_key
             ORDER BY s2.id DESC LIMIT 1
       )
      WHERE da.device_id = ? AND a.enabled = TRUE
      ORDER BY a.sort_order, a.display_name'
);
$stmt->execute([$session['device_id']]);

$now = utc_now();
$warsaw = new DateTimeZone('Europe/Warsaw');
$priceWarningSeconds = max(10, (int)(config()['monitor_price_warning_seconds'] ?? 60));
$accounts = array_map(static function (array $row) use ($now, $priceWarningSeconds): array {
    $snapshot = $row['payload'] ? json_decode((string)$row['payload'], true) : null;
    $connection = is_array($snapshot) && isset($snapshot['connection']) && is_array($snapshot['connection']) ? $snapshot['connection'] : [];
    $capturedAt = $row['captured_at'] ? new DateTimeImmutable((string)$row['captured_at'], new DateTimeZone('UTC')) : null;
    $lastTickAt = $row['last_tick_at'] ? new DateTimeImmutable((string)$row['last_tick_at'], new DateTimeZone('UTC')) : null;
    $lastTickAge = $lastTickAt ? max(0, $now->getTimestamp() - $lastTickAt->getTimestamp()) : null;
    $health = $lastTickAge === null ? 'UNKNOWN' : ($lastTickAge <= $priceWarningSeconds ? 'OK' : 'WARNING');
    return [
        'key' => (string)$row['account_key'],
        'displayName' => (string)$row['display_name'],
        'accountType' => (string)$row['account_type'],
        'brokerAccountId' => (string)$row['broker_account_id'],
        'isDefault' => (bool)$row['is_default'],
        'canControlService' => (bool)$row['can_control_service'],
        'connected' => (bool)($connection['connected'] ?? false),
        'health' => $health,
        'lastSync' => $capturedAt ? atom_datetime($capturedAt) : '',
    ];
}, $stmt->fetchAll());

json_response([
    'ok' => true,
    'generatedAt' => atom_datetime(utc_now()),
    'accounts' => $accounts,
]);
