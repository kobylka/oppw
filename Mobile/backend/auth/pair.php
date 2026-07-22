<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';

require_method('POST');
require_https();
enforce_rate_limit('pair', 10, 600);

$data = request_json();
$code = normalize_pairing_code((string)($data['pairingCode'] ?? ''));
$deviceName = trim((string)($data['deviceName'] ?? 'Android device'));
if (strlen($code) < 8) json_response(['ok' => false, 'error' => 'Invalid pairing code'], 400);
if ($deviceName === '') $deviceName = 'Android device';
$deviceName = substr($deviceName, 0, 100);

$db = pdo();
$db->beginTransaction();
try {
    $codeStmt = $db->prepare(
        'SELECT id, expires_at, consumed_at
           FROM monitor_pairing_codes
          WHERE code_hash = ?
          LIMIT 1
          FOR UPDATE'
    );
    $codeStmt->execute([pairing_code_hash($code)]);
    $pairing = $codeStmt->fetch();
    if (!$pairing || $pairing['consumed_at'] !== null || new DateTimeImmutable((string)$pairing['expires_at'], new DateTimeZone('UTC')) <= utc_now()) {
        $db->rollBack();
        json_response(['ok' => false, 'error' => 'Pairing code is invalid, expired, or already used'], 401);
    }

    $accountsStmt = $db->prepare(
        'SELECT p.account_key, p.can_control_service
           FROM monitor_pairing_code_accounts p
           JOIN monitor_accounts a ON a.account_key = p.account_key
          WHERE p.pairing_code_id = ? AND a.enabled = TRUE'
    );
    $accountsStmt->execute([(int)$pairing['id']]);
    $accountPermissions = $accountsStmt->fetchAll();
    if (!$accountPermissions) {
        $db->rollBack();
        json_response(['ok' => false, 'error' => 'Pairing code has no enabled accounts'], 409);
    }

    $deviceId = bin2hex(random_bytes(16));
    $refreshToken = random_token(32);
    $refreshExpires = utc_now()->modify('+' . max(1, (int)config()['refresh_token_ttl_days']) . ' days');
    $insertDevice = $db->prepare(
        'INSERT INTO monitor_devices(device_id, device_name, refresh_token_hash, refresh_expires_at)
         VALUES (?, ?, ?, ?)'
    );
    $insertDevice->execute([$deviceId, $deviceName, token_hash($refreshToken), mysql_datetime($refreshExpires)]);

    $permissionStmt = $db->prepare('INSERT INTO monitor_device_accounts(device_id, account_key, can_control_service) VALUES (?, ?, ?)');
    foreach ($accountPermissions as $permission) {
        $permissionStmt->execute([$deviceId, (string)$permission['account_key'], (bool)$permission['can_control_service'] ? 1 : 0]);
    }

    $consume = $db->prepare('UPDATE monitor_pairing_codes SET consumed_at = UTC_TIMESTAMP(3) WHERE id = ?');
    $consume->execute([(int)$pairing['id']]);

    $access = create_access_token($db, $deviceId);
    $device = ['device_id' => $deviceId, 'device_name' => $deviceName];
    $session = session_payload($db, $device, $access['token'], $access['expiresAt'], $refreshToken, atom_datetime($refreshExpires));
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    json_response(['ok' => false, 'error' => 'Pairing failed'], 500);
}

json_response(['ok' => true, 'session' => $session], 201);
