<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$db = pdo();
$stmt = $db->query(
    "SELECT d.device_id, d.device_name, d.enabled, d.created_at, d.last_seen_at, d.refresh_expires_at,
            GROUP_CONCAT(da.account_key ORDER BY da.account_key SEPARATOR ',') AS accounts
       FROM monitor_devices d
       LEFT JOIN monitor_device_accounts da ON da.device_id = d.device_id
      GROUP BY d.device_id, d.device_name, d.enabled, d.created_at, d.last_seen_at, d.refresh_expires_at
      ORDER BY d.created_at DESC"
);
printf("%-32s  %-24s  %-8s  %-16s  %-24s\n", 'DEVICE ID', 'NAME', 'STATUS', 'ACCOUNTS', 'LAST SEEN');
foreach ($stmt->fetchAll() as $row) {
    printf(
        "%-32s  %-24s  %-8s  %-16s  %-24s\n",
        $row['device_id'], substr((string)$row['device_name'], 0, 24), (bool)$row['enabled'] ? 'ACTIVE' : 'REVOKED',
        (string)($row['accounts'] ?? ''), (string)($row['last_seen_at'] ?? '-')
    );
}
