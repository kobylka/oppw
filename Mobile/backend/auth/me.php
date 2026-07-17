<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';

require_method('GET');
$session = require_mobile_session();
$db = pdo();
json_response([
    'ok' => true,
    'device' => ['id' => $session['device_id'], 'name' => $session['device_name']],
    'allowedAccounts' => allowed_accounts($db, $session['device_id']),
]);
