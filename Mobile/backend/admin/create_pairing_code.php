<?php
declare(strict_types=1);
require dirname(__DIR__) . '/lib.php';
if (PHP_SAPI !== 'cli') exit("CLI only\n");

$options = getopt('', ['accounts:', 'minutes::', 'label::']);
$accountList = array_values(array_filter(array_map('trim', explode(',', (string)($options['accounts'] ?? '')))));
$minutes = max(1, min(1440, (int)($options['minutes'] ?? config()['pairing_code_ttl_minutes'] ?? 10)));
$label = substr(trim((string)($options['label'] ?? '')), 0, 100);
if (!$accountList) {
    fwrite(STDERR, "Usage: php admin/create_pairing_code.php --accounts=REAL,DEMO [--minutes=10] [--label=Samsung-A53]\n");
    exit(2);
}

$db = pdo();
$placeholders = implode(',', array_fill(0, count($accountList), '?'));
$stmt = $db->prepare("SELECT account_key FROM monitor_accounts WHERE enabled = TRUE AND account_key IN ($placeholders)");
$stmt->execute($accountList);
$existing = array_map(static fn(array $row): string => (string)$row['account_key'], $stmt->fetchAll());
sort($existing);
$expected = $accountList;
sort($expected);
if ($existing !== $expected) {
    fwrite(STDERR, 'Unknown or disabled account. Requested: ' . implode(',', $accountList) . "\n");
    exit(3);
}

$alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
for ($attempt = 0; $attempt < 10; $attempt++) {
    $plain = '';
    for ($i = 0; $i < 12; $i++) $plain .= $alphabet[random_int(0, strlen($alphabet) - 1)];
    $display = substr($plain, 0, 4) . '-' . substr($plain, 4, 4) . '-' . substr($plain, 8, 4);
    $expires = utc_now()->modify("+$minutes minutes");
    $db->beginTransaction();
    try {
        $insert = $db->prepare('INSERT INTO monitor_pairing_codes(code_hash, label, expires_at) VALUES (?, ?, ?)');
        $insert->execute([pairing_code_hash($plain), $label, mysql_datetime($expires)]);
        $id = (int)$db->lastInsertId();
        $permission = $db->prepare('INSERT INTO monitor_pairing_code_accounts(pairing_code_id, account_key) VALUES (?, ?)');
        foreach ($accountList as $accountKey) $permission->execute([$id, $accountKey]);
        $db->commit();
        echo "Pairing code: $display\n";
        echo 'Accounts: ' . implode(', ', $accountList) . "\n";
        echo 'Expires: ' . atom_datetime($expires) . "\n";
        exit(0);
    } catch (PDOException $e) {
        if ($db->inTransaction()) $db->rollBack();
        if ((string)$e->getCode() !== '23000') throw $e;
    }
}
fwrite(STDERR, "Could not generate a unique pairing code\n");
exit(4);
