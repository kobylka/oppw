<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/lib.php';

$assert = static function (bool $condition, string $message): void {
    if (!$condition) throw new RuntimeException($message);
};
$read = static function (string $relative): string {
    $path = dirname(__DIR__) . DIRECTORY_SEPARATOR . $relative;
    $content = file_get_contents($path);
    if ($content === false) throw new RuntimeException('Could not read ' . $relative);
    return $content;
};

$assert(requested_analytics_rolling_weeks(1) === 1, 'analytics minimum changed');
$assert(requested_analytics_rolling_weeks(82) === 82, 'analytics silently caps an explicit 82-week request');
$assert(requested_analytics_rolling_weeks(520) === 520, 'analytics silently caps a long explicit request');
$assert(requested_analytics_rolling_weeks('invalid') === 4, 'analytics invalid-input default changed');

$pairingToken = str_repeat('p', 48);
$manualToken = str_repeat('m', 48);
$assert(independent_manual_admin_token([
    'manual_admin_enabled' => true,
    'manual_admin_token' => $manualToken,
    'pairing_admin_token' => $pairingToken,
]) === $manualToken, 'independent manual token was rejected');
$assert(independent_manual_admin_token([
    'manual_admin_enabled' => true,
    'pairing_admin_enabled' => true,
    'pairing_admin_token' => $pairingToken,
]) === '', 'pairing token fallback remains active');
$assert(independent_manual_admin_token([
    'manual_admin_enabled' => true,
    'manual_admin_token' => $pairingToken,
    'pairing_admin_token' => $pairingToken,
]) === '', 'pairing and manual administration accept the same token');

$sameOrigin = [
    'HTTPS' => 'on',
    'SERVER_PORT' => 443,
    'HTTP_HOST' => 'monitor.example.com',
    'HTTP_SEC_FETCH_SITE' => 'same-origin',
    'HTTP_ORIGIN' => 'https://monitor.example.com',
];
$assert(browser_form_is_same_origin($sameOrigin), 'same-origin browser form was rejected');
$proxiedSameOrigin = $sameOrigin;
$proxiedSameOrigin['HTTP_HOST'] = 'php:9000';
$proxiedSameOrigin['HTTP_X_FORWARDED_HOST'] = 'monitor.example.com';
$assert(browser_form_is_same_origin($proxiedSameOrigin, true, true), 'same-origin browser form behind trusted proxy was rejected');
$assert(browser_form_is_same_origin($proxiedSameOrigin, true), 'browser-confirmed same-origin form depended on proxy host forwarding');
$legacyProxiedSameOrigin = $proxiedSameOrigin;
unset($legacyProxiedSameOrigin['HTTP_SEC_FETCH_SITE']);
$assert(browser_form_is_same_origin($legacyProxiedSameOrigin, true, true), 'legacy same-origin browser behind trusted proxy was rejected');
$assert(!browser_form_is_same_origin($legacyProxiedSameOrigin, true), 'untrusted forwarded host was accepted for a legacy browser');
$crossOrigin = $sameOrigin;
$crossOrigin['HTTP_SEC_FETCH_SITE'] = 'cross-site';
$crossOrigin['HTTP_ORIGIN'] = 'https://attacker.example';
$assert(!browser_form_is_same_origin($crossOrigin), 'cross-site browser form was accepted');

$receiptSource = $read('mobile-receipt.php');
$assert(!str_contains($receiptSource, 'authority.php'), 'paired receipt still loads authority persistence');
$assert(!str_contains($receiptSource, 'oppw_authority_event'), 'paired receipt still writes execution authority');
$assert(str_contains($receiptSource, "'MOBILE_RECEIPT'"), 'paired receipt is not stored as a diagnostic');

$analyticsSource = $read('analytics.php');
foreach (['enforce_single_flight', 'requested_analytics_rolling_weeks', "\$allHistory", 'oppw_analytics_data_watermark', 'X-OPPW-Analytics-Cache: HIT', 'oppw_analytics_segmented_rows', 'X-OPPW-Analytics-Segments', "name='MOBILE_RECEIPT'", 'AND occurred_at>=? AND occurred_at<?'] as $marker) {
    $assert(str_contains($analyticsSource, $marker), 'analytics work bound missing: ' . $marker);
}
$cacheSource = $read('analytics-cache.php');
foreach (['OPPW_ANALYTICS_CACHE_MAX_BYTES', 'OPPW_ANALYTICS_SEGMENT_MAX_BYTES', 'analytics_cache_ttl_seconds', 'analytics_segment_cache_ttl_seconds', 'oppw_analytics_week_segments', 'hash_equals($expectedKey', 'hash_hmac(', 'realpath(__DIR__)', 'is_link($path)', 'LOCK_SH', 'LOCK_EX', "@chmod(\$path, 0600)"] as $marker) {
    $assert(str_contains($cacheSource, $marker), 'analytics cache boundary missing: ' . $marker);
}

foreach (['market-admin.php', 'trade-admin.php'] as $manualPage) {
    $source = $read($manualPage);
    $assert(str_contains($source, 'independent_manual_admin_token'), $manualPage . ' does not require the independent manual token');
    $assert(!str_contains($source, "manual_admin_enabled'] ?? \$cfg['pairing_admin_enabled"), $manualPage . ' retains pairing-admin fallback');
}

$pushSource = $read('push-admin.php');
foreach (['require_https', 'browser_admin_headers', 'require_same_origin_browser_post', "enforce_rate_limit('push-admin'"] as $marker) {
    $assert(str_contains($pushSource, $marker), 'push administration protection missing: ' . $marker);
}

foreach (['apache-vhost.example.conf', '.htaccess', 'admin/.htaccess', 'private/.htaccess', 'publisher/.htaccess', 'sql/.htaccess'] as $apacheArtifact) {
    $assert(!file_exists(dirname(__DIR__) . DIRECTORY_SEPARATOR . str_replace('/', DIRECTORY_SEPARATOR, $apacheArtifact)), 'unused Apache artifact remains: ' . $apacheArtifact);
}

echo "SECURITY BOUNDARY TESTS PASSED cases=7\n";
