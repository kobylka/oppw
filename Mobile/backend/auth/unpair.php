<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';

require_method('POST');
$session = require_mobile_session();
$db = pdo();
$db->beginTransaction();
try {
    $disable = $db->prepare(
        "UPDATE monitor_devices
            SET enabled = FALSE,
                refresh_token_hash = REPEAT('0', 64),
                refresh_expires_at = UTC_TIMESTAMP(3),
                last_seen_at = UTC_TIMESTAMP(3)
          WHERE device_id = ?"
    );
    $disable->execute([$session['device_id']]);
    $revoke = $db->prepare('UPDATE monitor_access_tokens SET revoked_at = UTC_TIMESTAMP(3) WHERE device_id = ? AND revoked_at IS NULL');
    $revoke->execute([$session['device_id']]);
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    json_response(['ok' => false, 'error' => 'Unpair failed'], 500);
}
json_response(['ok' => true]);
