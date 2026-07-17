<?php
declare(strict_types=1);

require_once __DIR__ . '/lib.php';

require_https();
header('Cache-Control: no-store, max-age=0');
header('Pragma: no-cache');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");

$cfg = config();
$enabled = (bool)($cfg['pairing_admin_enabled'] ?? false);
$expectedToken = trim((string)($cfg['pairing_admin_token'] ?? ''));
if (!$enabled || $expectedToken === '') {
    http_response_code(404);
    exit('Not found');
}

function h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function enabled_accounts(PDO $db): array
{
    $stmt = $db->query(
        'SELECT account_key, display_name, account_type
           FROM monitor_accounts
          WHERE enabled = TRUE
          ORDER BY sort_order, display_name'
    );
    return $stmt->fetchAll();
}

function generate_pairing_code(PDO $db, array $accountKeys, int $minutes, string $label): array
{
    $accountKeys = array_values(array_unique(array_filter(array_map(
        static fn(mixed $value): string => trim((string)$value),
        $accountKeys
    ))));
    if (!$accountKeys) throw new RuntimeException('Select at least one account.');

    $placeholders = implode(',', array_fill(0, count($accountKeys), '?'));
    $stmt = $db->prepare("SELECT account_key FROM monitor_accounts WHERE enabled = TRUE AND account_key IN ($placeholders)");
    $stmt->execute($accountKeys);
    $existing = array_map(static fn(array $row): string => (string)$row['account_key'], $stmt->fetchAll());
    sort($existing);
    $expected = $accountKeys;
    sort($expected);
    if ($existing !== $expected) throw new RuntimeException('One or more selected accounts are unknown or disabled.');

    $alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    for ($attempt = 0; $attempt < 10; $attempt++) {
        $plain = '';
        for ($i = 0; $i < 12; $i++) $plain .= $alphabet[random_int(0, strlen($alphabet) - 1)];
        $display = substr($plain, 0, 4) . '-' . substr($plain, 4, 4) . '-' . substr($plain, 8, 4);
        $expires = utc_now()->modify('+' . $minutes . ' minutes');

        $db->beginTransaction();
        try {
            $insert = $db->prepare('INSERT INTO monitor_pairing_codes(code_hash, label, expires_at) VALUES (?, ?, ?)');
            $insert->execute([pairing_code_hash($plain), $label, mysql_datetime($expires)]);
            $pairingCodeId = (int)$db->lastInsertId();

            $permission = $db->prepare('INSERT INTO monitor_pairing_code_accounts(pairing_code_id, account_key) VALUES (?, ?)');
            foreach ($accountKeys as $accountKey) $permission->execute([$pairingCodeId, $accountKey]);

            $db->commit();
            return [
                'code' => $display,
                'accounts' => $accountKeys,
                'expires' => atom_datetime($expires),
            ];
        } catch (PDOException $e) {
            if ($db->inTransaction()) $db->rollBack();
            if ((string)$e->getCode() !== '23000') throw $e;
        } catch (Throwable $e) {
            if ($db->inTransaction()) $db->rollBack();
            throw $e;
        }
    }

    throw new RuntimeException('Could not generate a unique pairing code.');
}

$db = pdo();
$accounts = enabled_accounts($db);
$result = null;
$error = '';
$label = '';
$minutes = max(1, min(1440, (int)($cfg['pairing_code_ttl_minutes'] ?? 10)));
$selectedAccounts = [];

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    enforce_rate_limit('pairing-admin', 10, 600);

    $providedToken = trim((string)($_POST['admin_token'] ?? ''));
    if ($providedToken === '' || !hash_equals($expectedToken, $providedToken)) {
        http_response_code(401);
        $error = 'Invalid admin token.';
    } else {
        $label = substr(trim((string)($_POST['label'] ?? '')), 0, 100);
        $minutes = max(1, min(1440, (int)($_POST['minutes'] ?? $minutes)));
        $selectedAccounts = is_array($_POST['accounts'] ?? null) ? $_POST['accounts'] : [];

        try {
            $result = generate_pairing_code($db, $selectedAccounts, $minutes, $label);
        } catch (Throwable $e) {
            error_log('OPPW pairing admin failed: ' . $e->getMessage());
            $error = $e->getMessage();
        }
    }
}
?>
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>OPPW pairing administration</title>
    <style>
        :root { color-scheme: dark; font-family: system-ui, sans-serif; }
        body { margin: 0; background: #0d1117; color: #e6edf3; }
        main { max-width: 580px; margin: 0 auto; padding: 24px 16px 48px; }
        section { background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 20px; }
        h1 { margin-top: 0; font-size: 1.4rem; }
        label, legend { display: block; margin-top: 16px; font-weight: 600; }
        input[type=text], input[type=password], input[type=number] { box-sizing: border-box; width: 100%; margin-top: 6px; padding: 11px; border: 1px solid #484f58; border-radius: 8px; background: #0d1117; color: #e6edf3; font: inherit; }
        fieldset { margin-top: 16px; border: 1px solid #30363d; border-radius: 8px; padding: 12px; }
        .account { display: flex; gap: 10px; align-items: center; margin: 9px 0; font-weight: 400; }
        button { margin-top: 20px; width: 100%; padding: 12px; border: 0; border-radius: 8px; background: #238636; color: white; font: inherit; font-weight: 700; cursor: pointer; }
        .error { margin-bottom: 16px; padding: 12px; border: 1px solid #f85149; border-radius: 8px; background: #3d1518; }
        .result { margin-bottom: 16px; padding: 16px; border: 1px solid #2ea043; border-radius: 8px; background: #12261a; }
        .code { margin: 10px 0; font: 700 1.8rem ui-monospace, monospace; letter-spacing: .08em; }
        .muted { color: #8b949e; font-size: .9rem; }
    </style>
</head>
<body>
<main>
    <section>
        <h1>Create mobile pairing code</h1>
        <p class="muted">The code is single-use and expires automatically. This page does not display or store your admin token.</p>

        <?php if ($error !== ''): ?>
            <div class="error"><?= h($error) ?></div>
        <?php endif; ?>

        <?php if (is_array($result)): ?>
            <div class="result">
                <div>Pairing code</div>
                <div class="code"><?= h((string)$result['code']) ?></div>
                <div>Accounts: <?= h(implode(', ', $result['accounts'])) ?></div>
                <div>Expires: <?= h((string)$result['expires']) ?></div>
            </div>
        <?php endif; ?>

        <form method="post" autocomplete="off">
            <label for="admin-token">Admin token</label>
            <input id="admin-token" name="admin_token" type="password" required autocomplete="current-password">

            <fieldset>
                <legend>Allowed accounts</legend>
                <?php foreach ($accounts as $account): ?>
                    <?php $key = (string)$account['account_key']; ?>
                    <label class="account">
                        <input type="checkbox" name="accounts[]" value="<?= h($key) ?>" <?= in_array($key, $selectedAccounts, true) ? 'checked' : '' ?>>
                        <span><?= h((string)$account['display_name']) ?> (<?= h($key) ?>)</span>
                    </label>
                <?php endforeach; ?>
            </fieldset>

            <label for="minutes">Validity in minutes</label>
            <input id="minutes" name="minutes" type="number" min="1" max="1440" value="<?= h((string)$minutes) ?>" required>

            <label for="label">Device label</label>
            <input id="label" name="label" type="text" maxlength="100" value="<?= h($label) ?>" placeholder="Samsung A53">

            <button type="submit">Create pairing code</button>
        </form>
    </section>
</main>
</body>
</html>
