<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$options = getopt('', ['device:']);
$deviceId = trim((string)($options['device'] ?? ''));
if (!preg_match('/^[a-f0-9]{32}$/', $deviceId)) {
    fwrite(STDERR, "Usage: php admin/revoke_device.php --device=DEVICE_ID\n");
    exit(2);
}
$db = pdo();
$db->beginTransaction();
try {
    $disable = $db->prepare("UPDATE monitor_devices SET enabled = FALSE, refresh_token_hash = REPEAT('0', 64), refresh_expires_at = UTC_TIMESTAMP(3) WHERE device_id = ?");
    $disable->execute([$deviceId]);
    $revoke = $db->prepare('UPDATE monitor_access_tokens SET revoked_at = UTC_TIMESTAMP(3) WHERE device_id = ? AND revoked_at IS NULL');
    $revoke->execute([$deviceId]);
    $db->commit();
    echo $disable->rowCount() ? "Device revoked\n" : "Device not found\n";
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    throw $e;
}
