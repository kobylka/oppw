<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

try {
    pdo()->query('SELECT 1');
    json_response(['ok' => true, 'database' => 'connected', 'time' => gmdate(DATE_ATOM)]);
} catch (Throwable) {
    json_response(['ok' => false, 'database' => 'unavailable'], 503);
}
