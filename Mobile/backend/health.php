<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_method('GET');
require_https();
try {
    pdo()->query('SELECT 1')->fetchColumn();
    json_response(['ok' => true, 'service' => 'oppw-monitor-api', 'time' => atom_datetime(utc_now())]);
} catch (Throwable) {
    json_response(['ok' => false, 'error' => 'Database unavailable'], 503);
}
