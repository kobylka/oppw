<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
require_method('POST');
$session = require_mobile_session();
$data = request_json(8192);
$token = trim((string)($data['token'] ?? ''));
$db = pdo();
if ($token !== '') {
    $stmt = $db->prepare('UPDATE monitor_push_tokens SET enabled = FALSE, updated_at = UTC_TIMESTAMP(3) WHERE device_id = ? AND fcm_token_hash = ?');
    $stmt->execute([$session['device_id'], hash('sha256', $token)]);
} else {
    $stmt = $db->prepare('UPDATE monitor_push_tokens SET enabled = FALSE, updated_at = UTC_TIMESTAMP(3) WHERE device_id = ?');
    $stmt->execute([$session['device_id']]);
}
json_response(['ok' => true]);
