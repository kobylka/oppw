<?php
declare(strict_types=1);

require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$options = getopt('', ['account:', 'type:', 'display-name::', 'broker-account-id::', 'sort-order::']);
$account = strtoupper(trim((string)($options['account'] ?? '')));
$type = strtoupper(trim((string)($options['type'] ?? '')));
$displayName = trim((string)($options['display-name'] ?? $account));
$brokerAccountId = trim((string)($options['broker-account-id'] ?? ''));
$sortOrder = (int)($options['sort-order'] ?? 100);

if (!preg_match('/^[A-Z0-9][A-Z0-9_-]{0,63}$/', $account)
    || !in_array($type, ['DEMO', 'REAL'], true)
    || (in_array($account, ['DEMO', 'REAL'], true) && $account !== $type)
    || $displayName === ''
    || strlen($displayName) > 100
    || strlen($brokerAccountId) > 100) {
    fwrite(
        STDERR,
        "Usage: php admin/register_account.php --account=DEMO_ALPHA --type=DEMO "
        . "[--display-name=\"Demo Alpha\"] [--broker-account-id=123456] [--sort-order=100]\n"
    );
    exit(2);
}

$db = pdo();
$db->beginTransaction();
try {
    $existingStatement = $db->prepare(
        'SELECT account_type FROM monitor_accounts WHERE account_key=? FOR UPDATE'
    );
    $existingStatement->execute([$account]);
    $existingType = $existingStatement->fetchColumn();
    if ($existingType !== false && !hash_equals(strtoupper((string)$existingType), $type)) {
        throw new RuntimeException(
            "Account $account is already registered as " . strtoupper((string)$existingType)
        );
    }
    $accountStatement = $db->prepare(
        'INSERT INTO monitor_accounts(account_key,display_name,account_type,broker_account_id,enabled,sort_order)
         VALUES (?,?,?,?,TRUE,?)
         ON DUPLICATE KEY UPDATE display_name=VALUES(display_name),
            broker_account_id=VALUES(broker_account_id),enabled=TRUE,sort_order=VALUES(sort_order)'
    );
    $accountStatement->execute([$account, $displayName, $type, $brokerAccountId, $sortOrder]);
    $desiredStatement = $db->prepare(
        'INSERT IGNORE INTO strategy_service_desired_state(strategy_key,role_name,desired_running)
         VALUES (?, ?, TRUE)'
    );
    foreach (['EXECUTOR', 'PUBLISHER'] as $role) $desiredStatement->execute([$account, $role]);
    $controlsStatement = $db->prepare(
        'INSERT IGNORE INTO strategy_entry_rule_controls(strategy_key) VALUES (?)'
    );
    $controlsStatement->execute([$account]);
    $positionControlsStatement = $db->prepare(
        'INSERT IGNORE INTO strategy_position_rule_controls(strategy_key) VALUES (?)'
    );
    $positionControlsStatement->execute([$account]);
    $db->commit();
} catch (Throwable $e) {
    if ($db->inTransaction()) $db->rollBack();
    throw $e;
}

echo "ACCOUNT REGISTERED key=$account type=$type display=$displayName\n";
