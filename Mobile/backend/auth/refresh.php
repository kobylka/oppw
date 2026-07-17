<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';

require_method('POST');
require_https();
enforce_rate_limit('refresh', 30, 60);

$data = request_json();
$deviceId = trim((string)($data['deviceId'] ?? ''));
$providedRefresh = trim((string)($data['refreshToken'] ?? ''));
if (!preg_match('/^[a-f0-9]{32}$/', $deviceId) || $providedRefresh === '') {
    json_response(['ok' => false, 'error' => 'Invalid refresh request'], 400);
}

$db = pdo();
$db->beginTransaction();
try {
    $stmt = $db->prepare(
        'SELECT device_id, device_name, refresh_token_hash, refresh_expires_at, enabled
           FROM monitor_devices
          WHERE device_id = ?
          LIMIT 1
          FOR UPDATE'
    );
    $stmt->execute([$deviceId]);
    $device = $stmt->fetch();
    $valid = $device
        && (bool)$device['enabled']
        && hash_equals((string)$device['refresh_token_hash'], token_hash($providedRefresh))
        && new DateTimeImmutable((string)$device['refresh_expires_at'], new DateTimeZone('UTC')) > utc_now();
    if (!$valid) {
        $db->rollBack();
        json_response(['ok' => false, 'error' => 'Refresh token is invalid, expired, or revoked'], 401);
    }

    $newRefresh = random_token(32);
    $refreshExpires = utc_now()->modify('+' . max(1, (int)config()['refresh_token_ttl_days']) . ' days');
    $rotate = $db->prepare(
        'UPDATE monitor_devices
            SET refresh_token_hash = ?, refresh_expires_at = ?, last_seen_at = UTC_TIMESTAMP(3)
          WHERE device_id = ?'
    );
    $rotate->execute([token_hash($newRefresh), mysql_datetime($refreshExpires), $deviceId]);

    $revoke = $db->prepare('UPDATE monitor_access_tokens SET revoked_at = UTC_TIMESTAMP(3) WHERE device_id = ? AND revoked_at IS NULL');
    $revoke->execute([$deviceId]);
    $access = create_access_token($db, $deviceId);
    $session = session_payload($db, $device, $access['token'], $access['expiresAt'], $newRefresh, atom_datetime($refreshExpires));
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    json_response(['ok' => false, 'error' => 'Token refresh failed'], 500);
}

json_response(['ok' => true, 'session' => $session]);
