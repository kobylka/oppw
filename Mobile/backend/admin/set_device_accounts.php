<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$options = getopt('', ['device:', 'accounts:']);
$deviceId = trim((string)($options['device'] ?? ''));
$accounts = array_values(array_unique(array_filter(array_map('trim', explode(',', (string)($options['accounts'] ?? ''))))));
if (!preg_match('/^[a-f0-9]{32}$/', $deviceId) || !$accounts) {
    fwrite(STDERR, "Usage: php admin/set_device_accounts.php --device=DEVICE_ID --accounts=REAL,DEMO\n");
    exit(2);
}

$db = pdo();
$deviceStmt = $db->prepare('SELECT 1 FROM monitor_devices WHERE device_id = ?');
$deviceStmt->execute([$deviceId]);
if (!$deviceStmt->fetchColumn()) {
    fwrite(STDERR, "Device not found\n");
    exit(3);
}
$placeholders = implode(',', array_fill(0, count($accounts), '?'));
$accountStmt = $db->prepare("SELECT account_key FROM monitor_accounts WHERE enabled = TRUE AND account_key IN ($placeholders)");
$accountStmt->execute($accounts);
$found = array_map(static fn(array $row): string => (string)$row['account_key'], $accountStmt->fetchAll());
sort($found);
$expected = $accounts;
sort($expected);
if ($found !== $expected) {
    fwrite(STDERR, "One or more accounts are unknown or disabled\n");
    exit(4);
}

$db->beginTransaction();
try {
    $delete = $db->prepare('DELETE FROM monitor_device_accounts WHERE device_id = ?');
    $delete->execute([$deviceId]);
    $insert = $db->prepare('INSERT INTO monitor_device_accounts(device_id, account_key) VALUES (?, ?)');
    foreach ($accounts as $accountKey) $insert->execute([$deviceId, $accountKey]);
    $db->commit();
    echo 'Device accounts set to: ' . implode(', ', $accounts) . "\n";
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    throw $e;
}
