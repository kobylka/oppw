<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$options = getopt('', ['device:', 'accounts:', 'can-control-service::']);
$deviceId = trim((string)($options['device'] ?? ''));
$accounts = array_values(array_unique(array_filter(array_map('trim', explode(',', (string)($options['accounts'] ?? ''))))));
$canControlOptionProvided = array_key_exists('can-control-service', $options);
$canControlValue = strtolower(trim((string)($options['can-control-service'] ?? '0')));
$canControlService = in_array($canControlValue, ['1', 'true', 'yes', 'on'], true);
if (!preg_match('/^[a-f0-9]{32}$/', $deviceId) || !$accounts) {
    fwrite(STDERR, "Usage: php admin/set_device_accounts.php --device=DEVICE_ID --accounts=REAL,DEMO [--can-control-service=1|0]\n");
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
    $existingControlByAccount = [];
    if (!$canControlOptionProvided) {
        $controlStmt = $db->prepare('SELECT account_key, can_control_service FROM monitor_device_accounts WHERE device_id = ?');
        $controlStmt->execute([$deviceId]);
        foreach ($controlStmt->fetchAll() as $permission) {
            $existingControlByAccount[(string)$permission['account_key']] = (bool)$permission['can_control_service'];
        }
    }
    $delete = $db->prepare('DELETE FROM monitor_device_accounts WHERE device_id = ?');
    $delete->execute([$deviceId]);
    $insert = $db->prepare('INSERT INTO monitor_device_accounts(device_id, account_key, can_control_service) VALUES (?, ?, ?)');
    foreach ($accounts as $accountKey) {
        $effectiveControl = $canControlOptionProvided
            ? $canControlService
            : (bool)($existingControlByAccount[$accountKey] ?? false);
        $insert->execute([$deviceId, $accountKey, $effectiveControl ? 1 : 0]);
    }
    $db->commit();
    echo 'Device accounts set to: ' . implode(', ', $accounts) . "\n";
    echo 'Service control: ' . ($canControlOptionProvided ? ($canControlService ? 'allowed' : 'read-only') : 'preserved per account') . "\n";
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    throw $e;
}
