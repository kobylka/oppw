<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
require_method('POST');
$session = require_mobile_session();
$data = request_json(8192);
$token = trim((string)($data['token'] ?? ''));
if ($token === '' || strlen($token) > 4096) json_response(['ok' => false, 'error' => 'Valid FCM token required'], 400);
$appVersion = substr(trim((string)($data['appVersion'] ?? '')), 0, 32);
$platform = substr(trim((string)($data['platform'] ?? 'ANDROID')), 0, 16);
$db = pdo();
$tokenHash = hash('sha256', $token);
$disable = $db->prepare('UPDATE monitor_push_tokens SET enabled = FALSE, updated_at = UTC_TIMESTAMP(3) WHERE device_id = ? AND fcm_token_hash <> ?');
$disable->execute([$session['device_id'], $tokenHash]);
$stmt = $db->prepare(
    'INSERT INTO monitor_push_tokens(device_id, fcm_token_hash, fcm_token, platform, app_version, enabled, updated_at)
     VALUES (?, ?, ?, ?, ?, TRUE, UTC_TIMESTAMP(3))
     ON DUPLICATE KEY UPDATE device_id = VALUES(device_id), fcm_token = VALUES(fcm_token), platform = VALUES(platform), app_version = VALUES(app_version), enabled = TRUE, updated_at = UTC_TIMESTAMP(3)'
);
$stmt->execute([$session['device_id'], $tokenHash, $token, $platform, $appVersion]);
json_response(['ok' => true]);
