<?php
declare(strict_types=1);

return [
    'dsn' => 'mysql:host=127.0.0.1;dbname=oppw_monitor;charset=utf8mb4',
    'db_user' => 'oppw_monitor',
    'db_password' => 'replace-with-database-password',
    'read_token' => 'replace-with-a-long-random-read-token',
    'write_token' => 'replace-with-a-different-long-random-write-token',
    'default_account_key' => 'REAL',
    'event_limit' => 50,
];
