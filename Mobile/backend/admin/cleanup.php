<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");
$db = pdo();
$db->exec('DELETE FROM monitor_access_tokens WHERE expires_at < UTC_TIMESTAMP(3) - INTERVAL 7 DAY OR revoked_at < UTC_TIMESTAMP(3) - INTERVAL 7 DAY');
$db->exec('DELETE FROM monitor_pairing_codes WHERE expires_at < UTC_TIMESTAMP(3) - INTERVAL 1 DAY OR consumed_at < UTC_TIMESTAMP(3) - INTERVAL 1 DAY');
$db->exec('DELETE FROM auth_rate_limits WHERE window_start < UTC_TIMESTAMP(3) - INTERVAL 1 DAY');
$db->exec('DELETE FROM monitor_push_deliveries WHERE created_at < UTC_TIMESTAMP(3) - INTERVAL 30 DAY');
echo "Authentication cleanup complete\n";
