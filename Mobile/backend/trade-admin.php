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

function trade_h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function trade_optional_number(mixed $value): ?float
{
    if ($value === null || trim((string)$value) === '') return null;
    return is_numeric($value) ? (float)$value : null;
}

function trade_local_datetime(string $value): DateTimeImmutable
{
    $timezone = new DateTimeZone('Europe/Warsaw');
    $parsed = DateTimeImmutable::createFromFormat('!Y-m-d\TH:i', $value, $timezone);
    if (!$parsed || $parsed->format('Y-m-d\TH:i') !== $value) throw new RuntimeException('Invalid date/time: ' . $value);
    return $parsed->setTimezone(new DateTimeZone('UTC'));
}

$db = pdo();
$accounts = $db->query('SELECT account_key, display_name FROM monitor_accounts WHERE enabled = TRUE ORDER BY sort_order, display_name')->fetchAll();
$defaults = [
    'account_key' => (string)($accounts[0]['account_key'] ?? ''), 'ticket' => '', 'symbol' => 'US100', 'side' => 'BUY', 'volume' => '0.01',
    'opened_at' => '', 'closed_at' => '', 'open_price' => '', 'close_price' => '', 'profit' => '', 'profit_percent' => '',
    'exit_reason' => '', 'balance_before' => '', 'balance_after' => '', 'mfe_points' => '', 'mae_points' => '',
    'entry_slippage_points' => '', 'exit_slippage_points' => '',
];
$form = [];
foreach ($defaults as $key => $default) $form[$key] = trim((string)($_POST[$key] ?? $default));
$error = '';
$message = '';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    enforce_rate_limit('trade-admin', 20, 600);
    $providedToken = trim((string)($_POST['admin_token'] ?? ''));
    if ($providedToken === '' || !hash_equals($expectedToken, $providedToken)) {
        http_response_code(401);
        $error = 'Invalid admin token.';
    } else {
        try {
            $accountStmt = $db->prepare('SELECT 1 FROM monitor_accounts WHERE account_key = ? AND enabled = TRUE');
            $accountStmt->execute([$form['account_key']]);
            if (!$accountStmt->fetchColumn()) throw new RuntimeException('Select a valid account.');

            $opened = trade_local_datetime($form['opened_at']);
            $closed = trade_local_datetime($form['closed_at']);
            if ($closed <= $opened) throw new RuntimeException('Closed time must be after opened time.');

            $side = strtoupper($form['side']);
            if (!in_array($side, ['BUY', 'SELL'], true)) throw new RuntimeException('Side must be BUY or SELL.');
            $volume = trade_optional_number($form['volume']);
            $openPrice = trade_optional_number($form['open_price']);
            $closePrice = trade_optional_number($form['close_price']);
            $profit = trade_optional_number($form['profit']);
            if ($volume === null || $volume <= 0 || $openPrice === null || $openPrice <= 0 || $closePrice === null || $closePrice <= 0 || $profit === null) throw new RuntimeException('Volume, open price, close price and profit are required.');

            $ticket = preg_match('/^\d+$/', $form['ticket']) ? (int)$form['ticket'] : 800000000000000 + random_int(0, 999999999999);
            $profitPercent = trade_optional_number($form['profit_percent']);
            if ($profitPercent === null) $profitPercent = ($side === 'BUY' ? $closePrice / $openPrice - 1.0 : $openPrice / $closePrice - 1.0) * 100.0;
            $mfe = max(0.0, trade_optional_number($form['mfe_points']) ?? 0.0);
            $maeMagnitude = max(0.0, trade_optional_number($form['mae_points']) ?? 0.0);
            $mae = -$maeMagnitude;
            $entrySlip = trade_optional_number($form['entry_slippage_points']);
            $exitSlip = trade_optional_number($form['exit_slippage_points']);
            $balanceBefore = trade_optional_number($form['balance_before']);
            $balanceAfter = trade_optional_number($form['balance_after']);
            $bestPrice = $side === 'BUY' ? $openPrice + $mfe : $openPrice - $mfe;
            $worstPrice = $side === 'BUY' ? $openPrice - $maeMagnitude : $openPrice + $maeMagnitude;
            $entryReference = $entrySlip !== null ? ($side === 'BUY' ? $openPrice - $entrySlip : $openPrice + $entrySlip) : null;
            $exitReference = $exitSlip !== null ? ($side === 'BUY' ? $closePrice + $exitSlip : $closePrice - $exitSlip) : null;
            $entrySlipPercent = $entryReference !== null && $entryReference > 0 ? $entrySlip / $entryReference * 100.0 : null;
            $exitSlipPercent = $exitReference !== null && $exitReference > 0 ? $exitSlip / $exitReference * 100.0 : null;
            $openedSql = $opened->format('Y-m-d H:i:s.v');
            $closedSql = $closed->format('Y-m-d H:i:s.v');

            $db->beginTransaction();
            $tradeStmt = $db->prepare(
                'INSERT INTO strategy_trades(
                    strategy_key, position_ticket, symbol, side, volume, opened_at, closed_at, open_price,
                    entry_reference_price, entry_slippage_points, entry_slippage_percent, close_price,
                    exit_reference_price, exit_slippage_points, exit_slippage_percent, profit, profit_percent,
                    best_price, worst_price, mfe_points, mfe_percent, mae_points, mae_percent,
                    max_profit, max_drawdown, exit_reason, balance_before, balance_after
                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                 ON DUPLICATE KEY UPDATE
                    symbol=VALUES(symbol), side=VALUES(side), volume=VALUES(volume), opened_at=VALUES(opened_at), closed_at=VALUES(closed_at),
                    open_price=VALUES(open_price), entry_reference_price=VALUES(entry_reference_price), entry_slippage_points=VALUES(entry_slippage_points),
                    entry_slippage_percent=VALUES(entry_slippage_percent), close_price=VALUES(close_price), exit_reference_price=VALUES(exit_reference_price),
                    exit_slippage_points=VALUES(exit_slippage_points), exit_slippage_percent=VALUES(exit_slippage_percent), profit=VALUES(profit),
                    profit_percent=VALUES(profit_percent), best_price=VALUES(best_price), worst_price=VALUES(worst_price), mfe_points=VALUES(mfe_points),
                    mfe_percent=VALUES(mfe_percent), mae_points=VALUES(mae_points), mae_percent=VALUES(mae_percent), max_profit=VALUES(max_profit),
                    max_drawdown=VALUES(max_drawdown), exit_reason=VALUES(exit_reason), balance_before=VALUES(balance_before), balance_after=VALUES(balance_after)'
            );
            $tradeStmt->execute([
                $form['account_key'], $ticket, substr($form['symbol'], 0, 32), $side, $volume, $openedSql, $closedSql, $openPrice,
                $entryReference, $entrySlip, $entrySlipPercent, $closePrice, $exitReference, $exitSlip, $exitSlipPercent, $profit, $profitPercent,
                $bestPrice, $worstPrice, $mfe, $openPrice > 0 ? $mfe / $openPrice * 100.0 : 0.0, $mae, $openPrice > 0 ? $mae / $openPrice * 100.0 : 0.0,
                max(0.0, $profit), min(0.0, $profit), substr($form['exit_reason'] ?: 'MANUAL', 0, 100), $balanceBefore, $balanceAfter,
            ]);

            $equityStmt = $db->prepare(
                'INSERT INTO strategy_equity_points(strategy_key, captured_minute, balance, equity, deposit, current_profit, position_ticket)
                 VALUES (?, ?, ?, ?, 0, 0, NULL)
                 ON DUPLICATE KEY UPDATE balance=VALUES(balance), equity=VALUES(equity)'
            );
            if ($balanceBefore !== null) {
                $equityStmt->execute([$form['account_key'], $opened->format('Y-m-d H:i:00'), $balanceBefore, $balanceBefore]);
                $initialStmt = $db->prepare("SELECT id, occurred_at FROM account_cash_flows WHERE strategy_key = ? AND flow_type = 'INITIAL' ORDER BY occurred_at LIMIT 1");
                $initialStmt->execute([$form['account_key']]);
                $initial = $initialStmt->fetch();
                if (!$initial) {
                    $insertInitial = $db->prepare("INSERT INTO account_cash_flows(strategy_key, occurred_at, flow_type, amount, balance_after, source, reference_key, note) VALUES (?, ?, 'INITIAL', ?, ?, 'MANUAL_API', ?, 'Initial balance supplied with historical trade')");
                    $insertInitial->execute([$form['account_key'], $openedSql, $balanceBefore, $balanceBefore, 'manual-initial:' . $form['account_key']]);
                } elseif (new DateTimeImmutable((string)$initial['occurred_at'], new DateTimeZone('UTC')) > $opened) {
                    $updateInitial = $db->prepare("UPDATE account_cash_flows SET occurred_at = ?, amount = ?, balance_after = ?, source = 'MANUAL_API', note = 'Initial balance moved earlier by historical trade import' WHERE id = ?");
                    $updateInitial->execute([$openedSql, $balanceBefore, $balanceBefore, (int)$initial['id']]);
                }
            }
            if ($balanceAfter !== null) $equityStmt->execute([$form['account_key'], $closed->format('Y-m-d H:i:00'), $balanceAfter, $balanceAfter]);
            $db->commit();

            $form['ticket'] = (string)$ticket;
            $message = 'Saved trade ticket ' . $ticket . '. Analytics and the all-time equity curve will use it immediately.';
        } catch (Throwable $e) {
            if ($db->inTransaction()) $db->rollBack();
            error_log('OPPW trade admin failed: ' . $e->getMessage());
            $error = $e->getMessage();
        }
    }
}
?>
<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>OPPW manual trade history</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif}body{margin:0;background:#0d1117;color:#e6edf3}main{max-width:900px;margin:0 auto;padding:24px 14px 48px}section{background:#161b22;border:1px solid #30363d;border-radius:14px;padding:20px}h1{margin-top:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}label{display:block;font-weight:600}input,select,button{box-sizing:border-box;width:100%;margin-top:5px;padding:10px;border:1px solid #484f58;border-radius:8px;background:#0d1117;color:#e6edf3;font:inherit}button{margin-top:20px;background:#238636;border:0;font-weight:700;cursor:pointer}.error,.ok{padding:12px;border-radius:8px;margin-bottom:14px}.error{background:#3d1518;border:1px solid #f85149}.ok{background:#12261a;border:1px solid #2ea043}.muted{color:#8b949e;font-size:.9rem}.wide{grid-column:1/-1}@media(max-width:680px){.grid{grid-template-columns:1fr}.wide{grid-column:auto}}
</style></head><body><main><section>
<h1>Add historical trade</h1><p class="muted">Times are entered in Europe/Warsaw time and stored in UTC. Leave the ticket blank to generate a synthetic historical ticket. MFE and MAE are entered as positive point distances.</p>
<?php if ($error !== ''): ?><div class="error"><?= trade_h($error) ?></div><?php endif; ?>
<?php if ($message !== ''): ?><div class="ok"><?= trade_h($message) ?></div><?php endif; ?>
<form method="post" autocomplete="off"><div class="grid">
<label class="wide">Admin token<input type="password" name="admin_token" required autocomplete="current-password"></label>
<label>Account<select name="account_key" required><?php foreach ($accounts as $account): $key=(string)$account['account_key']; ?><option value="<?= trade_h($key) ?>" <?= $key===$form['account_key']?'selected':'' ?>><?= trade_h((string)$account['display_name'].' ('.$key.')') ?></option><?php endforeach; ?></select></label>
<label>Ticket (optional)<input name="ticket" inputmode="numeric" value="<?= trade_h($form['ticket']) ?>"></label>
<label>Symbol<input name="symbol" maxlength="32" value="<?= trade_h($form['symbol']) ?>" required></label>
<label>Side<select name="side"><option value="BUY" <?= $form['side']==='BUY'?'selected':'' ?>>BUY</option><option value="SELL" <?= $form['side']==='SELL'?'selected':'' ?>>SELL</option></select></label>
<label>Volume<input type="number" step="0.00000001" min="0" name="volume" value="<?= trade_h($form['volume']) ?>" required></label>
<label>Exit reason<input name="exit_reason" maxlength="100" value="<?= trade_h($form['exit_reason']) ?>" placeholder="OH, CH, TO, SL, TSL"></label>
<label>Opened at<input type="datetime-local" name="opened_at" value="<?= trade_h($form['opened_at']) ?>" required></label>
<label>Closed at<input type="datetime-local" name="closed_at" value="<?= trade_h($form['closed_at']) ?>" required></label>
<label>Open price<input type="number" step="0.00001" min="0" name="open_price" value="<?= trade_h($form['open_price']) ?>" required></label>
<label>Close price<input type="number" step="0.00001" min="0" name="close_price" value="<?= trade_h($form['close_price']) ?>" required></label>
<label>Profit<input type="number" step="0.01" name="profit" value="<?= trade_h($form['profit']) ?>" required></label>
<label>Raw profit % (optional)<input type="number" step="0.000001" name="profit_percent" value="<?= trade_h($form['profit_percent']) ?>"></label>
<label>Balance before (optional)<input type="number" step="0.01" name="balance_before" value="<?= trade_h($form['balance_before']) ?>"></label>
<label>Balance after (optional)<input type="number" step="0.01" name="balance_after" value="<?= trade_h($form['balance_after']) ?>"></label>
<label>MFE points (optional)<input type="number" step="0.00001" min="0" name="mfe_points" value="<?= trade_h($form['mfe_points']) ?>"></label>
<label>MAE points (optional)<input type="number" step="0.00001" min="0" name="mae_points" value="<?= trade_h($form['mae_points']) ?>"></label>
<label>Entry slippage points (optional)<input type="number" step="0.00001" name="entry_slippage_points" value="<?= trade_h($form['entry_slippage_points']) ?>"></label>
<label>Exit slippage points (optional)<input type="number" step="0.00001" name="exit_slippage_points" value="<?= trade_h($form['exit_slippage_points']) ?>"></label>
</div><button type="submit">Save historical trade</button></form>
</section></main></body></html>
