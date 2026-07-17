<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

$cfg = config();
if (!(bool)($cfg['pairing_admin_enabled'] ?? false)) {
    http_response_code(404);
    exit('Not found');
}

$db = pdo();
$message = '';
$error = '';
$accounts = $db->query('SELECT account_key, display_name FROM monitor_accounts WHERE enabled = TRUE ORDER BY sort_order, display_name')->fetchAll();
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    $provided = trim((string)($_POST['admin_token'] ?? ''));
    $expected = trim((string)($cfg['pairing_admin_token'] ?? ''));
    if ($expected === '' || !hash_equals($expected, $provided)) {
        $error = 'Invalid admin token.';
    } elseif (!push_enabled()) {
        $error = 'Firebase push is disabled or incomplete in the server configuration.';
    } else {
        $accountKey = trim((string)($_POST['account_key'] ?? ''));
        $title = trim((string)($_POST['title'] ?? 'OPPW Monitor test'));
        $body = trim((string)($_POST['body'] ?? 'Test notification from the OPPW backend.'));
        $valid = array_filter($accounts, static fn(array $row): bool => (string)$row['account_key'] === $accountKey);
        if (!$valid) {
            $error = 'Select a valid account.';
        } else {
            send_account_push($db, $accountKey, 'manual-test:' . bin2hex(random_bytes(12)), substr($title, 0, 120), substr($body, 0, 500), ['type' => 'MANUAL_TEST']);
            $message = 'Test notification queued for paired devices permitted to view ' . htmlspecialchars($accountKey, ENT_QUOTES, 'UTF-8') . '.';
        }
    }
}
?>
<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPPW push test</title>
<style>body{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 18px;background:#10151f;color:#eef2ff}form{display:grid;gap:14px;background:#182131;padding:20px;border-radius:14px}input,select,textarea,button{font:inherit;padding:11px;border-radius:8px;border:1px solid #465066}button{cursor:pointer}.ok{color:#66e0a3}.error{color:#ff8f8f}small{color:#aeb8ca}</style></head>
<body><h1>OPPW push test</h1><p><small>Available only while pairing browser administration is enabled. Disable it again after testing.</small></p>
<?php if ($message !== ''): ?><p class="ok"><?= $message ?></p><?php endif; ?>
<?php if ($error !== ''): ?><p class="error"><?= htmlspecialchars($error, ENT_QUOTES, 'UTF-8') ?></p><?php endif; ?>
<form method="post">
<label>Admin token<input type="password" name="admin_token" required autocomplete="current-password"></label>
<label>Account<select name="account_key" required><?php foreach ($accounts as $account): ?><option value="<?= htmlspecialchars((string)$account['account_key'], ENT_QUOTES, 'UTF-8') ?>"><?= htmlspecialchars((string)$account['display_name'] . ' (' . (string)$account['account_key'] . ')', ENT_QUOTES, 'UTF-8') ?></option><?php endforeach; ?></select></label>
<label>Title<input name="title" value="OPPW Monitor test" maxlength="120" required></label>
<label>Message<textarea name="body" maxlength="500" rows="4" required>Test notification from the OPPW backend.</textarea></label>
<button type="submit">Send test notification</button>
</form></body></html>
