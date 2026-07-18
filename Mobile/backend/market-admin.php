<?php
declare(strict_types=1);
require __DIR__ . '/lib.php';

require_https();
header('Cache-Control: no-store, max-age=0');
header('Pragma: no-cache');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');
header("Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'");

$cfg = config();
$enabled = (bool)($cfg['manual_admin_enabled'] ?? $cfg['pairing_admin_enabled'] ?? false);
$expectedToken = trim((string)($cfg['manual_admin_token'] ?? $cfg['pairing_admin_token'] ?? ''));
if (!$enabled || $expectedToken === '') {
    http_response_code(404);
    exit('Not found');
}

function market_h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function market_accounts(PDO $db): array
{
    return $db->query('SELECT account_key, display_name FROM monitor_accounts WHERE enabled = TRUE ORDER BY sort_order, display_name')->fetchAll();
}

function market_number(mixed $value): ?float
{
    if ($value === null || trim((string)$value) === '') return null;
    return is_numeric($value) ? (float)$value : null;
}

$db = pdo();
$accounts = market_accounts($db);
$warsaw = new DateTimeZone('Europe/Warsaw');
$newYork = new DateTimeZone('America/New_York');
$utc = new DateTimeZone('UTC');
$previousMonday = (new DateTimeImmutable('monday this week', $warsaw))->modify('-7 days');
$weekStartValue = trim((string)($_POST['week_start'] ?? $previousMonday->format('Y-m-d')));
$accountKey = trim((string)($_POST['account_key'] ?? ($accounts[0]['account_key'] ?? '')));
$error = '';
$message = '';
$values = [];
for ($day = 0; $day < 5; $day++) {
    foreach (['open', 'high', 'low', 'close'] as $field) $values[$day][$field] = trim((string)($_POST["d{$day}_{$field}"] ?? ''));
}

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    enforce_rate_limit('market-admin', 20, 600);
    $providedToken = trim((string)($_POST['admin_token'] ?? ''));
    if ($providedToken === '' || !hash_equals($expectedToken, $providedToken)) {
        http_response_code(401);
        $error = 'Invalid admin token.';
    } else {
        try {
            $accountStmt = $db->prepare('SELECT 1 FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
            $accountStmt->execute([$accountKey]);
            if (!$accountStmt->fetchColumn()) throw new RuntimeException('Select a valid account.');

            $weekStart = DateTimeImmutable::createFromFormat('!Y-m-d', $weekStartValue, $warsaw);
            if (!$weekStart || $weekStart->format('Y-m-d') !== $weekStartValue || $weekStart->format('N') !== '1') throw new RuntimeException('Week start must be a valid Monday.');

            $upsert = $db->prepare(
                'INSERT INTO strategy_market_points(strategy_key, captured_minute, current_price, bid, ask, m1_open, m1_high, m1_low, m1_close, phase)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ON DUPLICATE KEY UPDATE current_price = VALUES(current_price), bid = VALUES(bid), ask = VALUES(ask), m1_open = VALUES(m1_open), m1_high = VALUES(m1_high), m1_low = VALUES(m1_low), m1_close = VALUES(m1_close), phase = VALUES(phase)'
            );

            $insertedDays = [];
            $db->beginTransaction();
            for ($day = 0; $day < 5; $day++) {
                $date = $weekStart->modify("+$day days");
                $open = market_number($values[$day]['open']);
                $high = market_number($values[$day]['high']);
                $low = market_number($values[$day]['low']);
                $close = market_number($values[$day]['close']);
                $provided = array_filter([$open, $high, $low, $close], static fn(?float $value): bool => $value !== null);
                if (!$provided) continue;
                if (count($provided) !== 4) throw new RuntimeException($date->format('Y-m-d') . ': provide all four O/H/L/C values or leave the whole day blank.');
                if ($open <= 0 || $high <= 0 || $low <= 0 || $close <= 0) throw new RuntimeException($date->format('Y-m-d') . ': prices must be positive.');
                if ($high < max($open, $close) || $low > min($open, $close) || $high < $low) throw new RuntimeException($date->format('Y-m-d') . ': invalid O/H/L/C relationship.');

                $dateText = $date->format('Y-m-d');
                $openUtc = (new DateTimeImmutable($dateText . ' 09:30:00', $newYork))->setTimezone($utc)->format('Y-m-d H:i:s');
                $closeUtc = (new DateTimeImmutable($dateText . ' 15:59:00', $newYork))->setTimezone($utc)->format('Y-m-d H:i:s');
                $upsert->execute([$accountKey, $openUtc, $open, $open, $open, $open, $open, $open, $open, 'REGULAR MANUAL OPEN']);
                $upsert->execute([$accountKey, $closeUtc, $close, $close, $close, $open, $high, $low, $close, 'REGULAR MANUAL CLOSE']);
                $insertedDays[] = $dateText;
            }
            if (!$insertedDays) throw new RuntimeException('Enter at least one trading day.');
            $db->commit();
            $message = 'Saved US100 O/H/L/C for ' . count($insertedDays) . ' day(s): ' . implode(', ', $insertedDays) . '.';
        } catch (Throwable $e) {
            if ($db->inTransaction()) $db->rollBack();
            error_log('OPPW market admin failed: ' . $e->getMessage());
            $error = $e->getMessage();
        }
    }
}

$displayWeek = DateTimeImmutable::createFromFormat('!Y-m-d', $weekStartValue, $warsaw) ?: $previousMonday;
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPPW manual US100 history</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif}body{margin:0;background:#0d1117;color:#e6edf3}main{max-width:900px;margin:0 auto;padding:24px 14px 48px}section{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:20px}h1{margin-top:0}label{display:block;font-weight:600}input,select,button{box-sizing:border-box;width:100%;padding:10px;border:1px solid #484f58;border-radius:8px;background:#0d1117;color:#e6edf3;font:inherit}.top{display:grid;grid-template-columns:1fr 1fr;gap:14px}.days{overflow-x:auto;margin-top:18px}table{width:100%;border-collapse:collapse;min-width:720px}th,td{padding:8px;border-bottom:1px solid #30363d;text-align:left}td input{min-width:120px}button{margin-top:18px;background:#238636;border:0;font-weight:700;cursor:pointer}.error,.ok{padding:12px;border-radius:8px;margin-bottom:14px}.error{background:#3d1518;border:1px solid #f85149}.ok{background:#12261a;border:1px solid #2ea043}.muted{color:#8b949e;font-size:.9rem}@media(max-width:620px){.top{grid-template-columns:1fr}}
</style></head>
<body><main><section>
<h1>Add weekly US100 O/H/L/C</h1>
<p class="muted">Choose the Monday starting the week. Leave holidays blank. The page stores exchange-open and exchange-close markers in UTC, so daylight-saving changes are handled automatically.</p>
<?php if ($error !== ''): ?><div class="error"><?= market_h($error) ?></div><?php endif; ?>
<?php if ($message !== ''): ?><div class="ok"><?= market_h($message) ?></div><?php endif; ?>
<form method="post" autocomplete="off">
<div class="top">
<label>Admin token<input type="password" name="admin_token" required autocomplete="current-password"></label>
<label>Account<select name="account_key" required><?php foreach ($accounts as $account): $key=(string)$account['account_key']; ?><option value="<?= market_h($key) ?>" <?= $key===$accountKey?'selected':'' ?>><?= market_h((string)$account['display_name'].' ('.$key.')') ?></option><?php endforeach; ?></select></label>
<label>Week start (Monday)<input type="date" name="week_start" value="<?= market_h($weekStartValue) ?>" required></label>
</div>
<div class="days"><table><thead><tr><th>Date</th><th>Open</th><th>High</th><th>Low</th><th>Close</th></tr></thead><tbody>
<?php for ($day=0;$day<5;$day++): $date=$displayWeek->modify("+$day days"); ?>
<tr><th><?= market_h($date->format('D Y-m-d')) ?></th><?php foreach (['open','high','low','close'] as $field): ?><td><input type="number" step="0.00001" min="0" name="d<?= $day ?>_<?= $field ?>" value="<?= market_h($values[$day][$field]) ?>"></td><?php endforeach; ?></tr>
<?php endfor; ?>
</tbody></table></div>
<button type="submit">Save weekly market history</button>
</form></section></main></body></html>
