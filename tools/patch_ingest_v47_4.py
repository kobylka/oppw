#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

INIT_START = "// OPPW_V47_4_DECISION_ACK_INIT_BEGIN"
INIT_END = "// OPPW_V47_4_DECISION_ACK_INIT_END"
DECISION_START = "// OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_BEGIN"
DECISION_END = "// OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_END"
TRADE_START = "// OPPW_V47_4_TRADE_DECISION_LINK_BEGIN"
TRADE_END = "// OPPW_V47_4_TRADE_DECISION_LINK_END"
EVENT_START = "// OPPW_V47_4_DECISION_EVENT_SKIP_BEGIN"
EVENT_END = "// OPPW_V47_4_DECISION_EVENT_SKIP_END"
RESPONSE_START = "// OPPW_V47_4_DECISION_ACK_RESPONSE_BEGIN"
RESPONSE_END = "// OPPW_V47_4_DECISION_ACK_RESPONSE_END"

OLD_MARKER_PAIRS = (
    ("// OPPW_V46_STRATEGY_DECISION_HISTORY_BEGIN", "// OPPW_V46_STRATEGY_DECISION_HISTORY_END"),
    ("// OPPW_V46_TRADE_DECISION_LINK_BEGIN", "// OPPW_V46_TRADE_DECISION_LINK_END"),
    (INIT_START, INIT_END), (DECISION_START, DECISION_END), (TRADE_START, TRADE_END),
    (EVENT_START, EVENT_END),
)

INIT_BLOCK = r'''// OPPW_V47_4_DECISION_ACK_INIT_BEGIN
$strategyDecisionStored = false;
$strategyDecisionId = '';
// OPPW_V47_4_DECISION_ACK_INIT_END
'''

DECISION_BLOCK = r'''  // OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_BEGIN
  $decision = is_array($data['strategyDecision'] ?? null)
      ? $data['strategyDecision']
      : (is_array($snapshot['strategyDecision'] ?? null) ? $snapshot['strategyDecision'] : null);
  if ($decision !== null && trim((string)($decision['decisionId'] ?? '')) !== '') {
      $inputs = is_array($decision['inputs'] ?? null) ? $decision['inputs'] : [];
      $sizing = is_array($decision['sizing'] ?? null) ? $decision['sizing'] : [];
      $risk = is_array($decision['risk'] ?? null) ? $decision['risk'] : [];
      $strategyDecisionId = substr(trim((string)$decision['decisionId']), 0, 32);
      $decisionPayload = json_encode($decision, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
      $decisionRecordedAt = normalize_datetime($decision['recordedAt'] ?? $capturedAt);
      $decisionStmt = $db->prepare(
          'INSERT INTO strategy_decisions(
              strategy_key, decision_id, decision_week, recorded_at, first_received_at, last_received_at,
              strategy_build, parameter_hash, decision_type, outcome, selected_leverage, leverage_reason,
              previous_full_week_change, previous_full_week_source, previous_trade_change, previous_trade_source,
              symbol, side, proposed_price, proposed_volume, required_deposit, required_balance,
              required_balance_multiplier, balance_multiplier_profile, effective_leverage,
              position_notional, sizing_units, margin_usage_percent, margin_level_after_percent,
              stop_loss_percent, stop_loss_price, stop_loss_cash, account_return_at_stop_percent,
              account_loss_cap_applied, error_text, payload
          ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
          ON DUPLICATE KEY UPDATE
              last_received_at=VALUES(last_received_at), recorded_at=LEAST(recorded_at, VALUES(recorded_at)),
              decision_week=VALUES(decision_week), strategy_build=VALUES(strategy_build), parameter_hash=VALUES(parameter_hash),
              decision_type=VALUES(decision_type), outcome=VALUES(outcome), selected_leverage=VALUES(selected_leverage),
              leverage_reason=VALUES(leverage_reason), previous_full_week_change=VALUES(previous_full_week_change),
              previous_full_week_source=VALUES(previous_full_week_source), previous_trade_change=VALUES(previous_trade_change),
              previous_trade_source=VALUES(previous_trade_source), symbol=VALUES(symbol), side=VALUES(side),
              proposed_price=VALUES(proposed_price), proposed_volume=VALUES(proposed_volume),
              required_deposit=VALUES(required_deposit), required_balance=VALUES(required_balance),
              required_balance_multiplier=VALUES(required_balance_multiplier),
              balance_multiplier_profile=VALUES(balance_multiplier_profile), effective_leverage=VALUES(effective_leverage),
              position_notional=VALUES(position_notional), sizing_units=VALUES(sizing_units),
              margin_usage_percent=VALUES(margin_usage_percent), margin_level_after_percent=VALUES(margin_level_after_percent),
              stop_loss_percent=VALUES(stop_loss_percent), stop_loss_price=VALUES(stop_loss_price),
              stop_loss_cash=VALUES(stop_loss_cash), account_return_at_stop_percent=VALUES(account_return_at_stop_percent),
              account_loss_cap_applied=VALUES(account_loss_cap_applied), error_text=VALUES(error_text), payload=VALUES(payload)'
      );
      $decisionStmt->execute([
          $accountKey, $strategyDecisionId, substr((string)($decision['decisionWeek'] ?? ''), 0, 10),
          $decisionRecordedAt, $capturedAt, $capturedAt,
          substr((string)($decision['build'] ?? ''), 0, 160), substr((string)($decision['parameterHash'] ?? ''), 0, 64),
          substr((string)($decision['decision'] ?? ''), 0, 64), substr((string)($decision['outcome'] ?? ''), 0, 32),
          $number($decision['selectedLeverage'] ?? 0), substr((string)($decision['leverageReason'] ?? ''), 0, 1000),
          $number($inputs['previousFullWeekChange'] ?? 0), substr((string)($inputs['previousFullWeekSource'] ?? ''), 0, 100),
          $number($inputs['previousTradeChange'] ?? 0), substr((string)($inputs['previousTradeSource'] ?? ''), 0, 100),
          substr((string)($sizing['symbol'] ?? ''), 0, 32), substr((string)($sizing['side'] ?? ''), 0, 8),
          is_numeric($sizing['price'] ?? null) ? (float)$sizing['price'] : null,
          is_numeric($sizing['volume'] ?? null) ? (float)$sizing['volume'] : null,
          is_numeric($sizing['requiredDeposit'] ?? null) ? (float)$sizing['requiredDeposit'] : null,
          is_numeric($sizing['requiredBalance'] ?? null) ? (float)$sizing['requiredBalance'] : null,
          is_numeric($sizing['requiredBalanceMultiplier'] ?? null) ? (float)$sizing['requiredBalanceMultiplier'] : null,
          substr((string)($sizing['balanceMultiplierProfile'] ?? ''), 0, 40),
          is_numeric($sizing['effectiveLeverage'] ?? null) ? (float)$sizing['effectiveLeverage'] : null,
          is_numeric($sizing['positionNotional'] ?? null) ? (float)$sizing['positionNotional'] : null,
          is_numeric($sizing['sizingUnits'] ?? null) ? (int)$sizing['sizingUnits'] : null,
          is_numeric($sizing['marginUsagePercent'] ?? null) ? (float)$sizing['marginUsagePercent'] : null,
          is_numeric($sizing['marginLevelAfterPercent'] ?? null) ? (float)$sizing['marginLevelAfterPercent'] : null,
          is_numeric($risk['potentialStopLossPercent'] ?? null) ? (float)$risk['potentialStopLossPercent'] : null,
          is_numeric($risk['potentialStopLossPrice'] ?? null) ? (float)$risk['potentialStopLossPrice'] : null,
          is_numeric($risk['potentialStopLossCash'] ?? null) ? (float)$risk['potentialStopLossCash'] : null,
          is_numeric($risk['accountLossPercentAtStop'] ?? null) ? (float)$risk['accountLossPercentAtStop'] : null,
          !empty($risk['accountLossCapApplied']) ? 1 : 0,
          substr((string)($decision['error'] ?? ''), 0, 1000), $decisionPayload,
      ]);
      $strategyDecisionStored = true;
  }
  // OPPW_V47_4_STRATEGY_DECISION_PERSISTENCE_END
'''

TRADE_BLOCK = r'''  // OPPW_V47_4_TRADE_DECISION_LINK_BEGIN
  $execution = is_array($snapshot['execution'] ?? null) ? $snapshot['execution'] : [];
  $linkedDecisionId = substr(trim((string)(($decision['decisionId'] ?? null) ?: ($execution['decisionId'] ?? ''))), 0, 32);
  if ($linkedDecisionId !== '') {
      $linkedBuild = substr((string)($decision['build'] ?? ''), 0, 160);
      $linkedParameterHash = substr((string)($decision['parameterHash'] ?? ''), 0, 64);
      $linkedLeverage = is_numeric($decision['selectedLeverage'] ?? null) ? (float)$decision['selectedLeverage'] : null;
      if ($decision === null || $linkedBuild === '' || $linkedParameterHash === '' || $linkedLeverage === null) {
          $linkedDecisionStmt = $db->prepare('SELECT strategy_build,parameter_hash,selected_leverage FROM strategy_decisions WHERE strategy_key=? AND decision_id=? LIMIT 1');
          $linkedDecisionStmt->execute([$accountKey, $linkedDecisionId]);
          $linkedDecisionRow = $linkedDecisionStmt->fetch();
          if (is_array($linkedDecisionRow)) {
              if ($linkedBuild === '') $linkedBuild = substr((string)($linkedDecisionRow['strategy_build'] ?? ''), 0, 160);
              if ($linkedParameterHash === '') $linkedParameterHash = substr((string)($linkedDecisionRow['parameter_hash'] ?? ''), 0, 64);
              if ($linkedLeverage === null && is_numeric($linkedDecisionRow['selected_leverage'] ?? null)) $linkedLeverage = (float)$linkedDecisionRow['selected_leverage'];
          }
      }
      $tradePosition = $currentPosition ?? $previousPosition;
      $tradeTicket = is_array($tradePosition) ? (int)($tradePosition['ticket'] ?? 0) : 0;
      if ($tradeTicket > 0) {
          $tradeDecisionStmt = $db->prepare('UPDATE strategy_trades SET decision_id=?, strategy_build=?, parameter_hash=?, entry_leverage=? WHERE strategy_key=? AND position_ticket=?');
          $tradeDecisionStmt->execute([$linkedDecisionId, $linkedBuild, $linkedParameterHash, $linkedLeverage, $accountKey, $tradeTicket]);
      }
  }
  // OPPW_V47_4_TRADE_DECISION_LINK_END
'''

EVENT_SKIP_BLOCK = r'''      // OPPW_V47_4_DECISION_EVENT_SKIP_BEGIN
      if (in_array($event['name'], ['STRATEGY_DECISION_RECORDED', 'STRATEGY_DECISION_CALCULATED', 'STRATEGY_DECISION_PERSISTED'], true)) continue;
      // OPPW_V47_4_DECISION_EVENT_SKIP_END
'''

RESPONSE_BLOCK = r'''// OPPW_V47_4_DECISION_ACK_RESPONSE_BEGIN
json_response([
    'ok' => true,
    'accountKey' => $accountKey,
    'storedEvents' => count($normalizedEvents),
    'strategyDecisionStored' => $strategyDecisionStored,
    'strategyDecisionId' => $strategyDecisionId,
], 201);
// OPPW_V47_4_DECISION_ACK_RESPONSE_END'''


def remove_marked(text: str, start: str, end: str) -> str:
    pattern = re.compile(r"[ \t]*" + re.escape(start) + r".*?" + re.escape(end) + r"[ \t]*(?:\r?\n)?", re.DOTALL)
    return pattern.sub("", text)


def insert_after_once(text: str, pattern: str, block: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise RuntimeError(f"Could not find {label} anchor in ingest.php")
    return text[:match.end()] + "\n" + block + text[match.end():]


def insert_before_once(text: str, pattern: str, block: str, label: str) -> str:
    match = re.search(pattern, text, flags=re.DOTALL)
    if match is None:
        raise RuntimeError(f"Could not find {label} anchor in ingest.php")
    return text[:match.start()] + block + "\n" + text[match.start():]


def patch(path: Path) -> None:
    original = path.read_text(encoding="utf-8-sig")
    if not original.lstrip().startswith("<?php"):
        raise RuntimeError("ingest.php is truncated or is not executable PHP; restore the intact file before applying v47.4")

    text = original
    if RESPONSE_START in text and RESPONSE_END in text:
        response_marker_pattern = re.compile(
            r"[ \t]*" + re.escape(RESPONSE_START) + r".*?" + re.escape(RESPONSE_END) + r"[ \t]*(?:\r?\n)?",
            re.DOTALL,
        )
        text = response_marker_pattern.sub(
            "json_response(['ok' => true, 'accountKey' => $accountKey, 'storedEvents' => count($normalizedEvents)], 201);\n",
            text,
            count=1,
        )
    for start, end in OLD_MARKER_PAIRS:
        text = remove_marked(text, start, end)
    text = re.sub(r"\s*if \(\$event\['name'\] === 'STRATEGY_DECISION_RECORDED'\) continue;[^\n]*(?:\r?\n)?", "\n", text)

    text = insert_before_once(text, r"\$db\s*->\s*beginTransaction\s*\(\s*\)\s*;", INIT_BLOCK, "transaction")
    text = insert_after_once(
        text,
        r"\$snapshotStmt\s*->\s*execute\s*\(\s*\[\s*\$accountKey\s*,\s*\$capturedAt\s*,\s*\$payload\s*\]\s*\)\s*;",
        DECISION_BLOCK,
        "snapshot insert",
    )
    text = insert_before_once(
        text,
        r"\$previousAccount\s*=\s*is_array\s*\(\s*\$previousSnapshot\['account'\]\s*\?\?\s*null\s*\)",
        TRADE_BLOCK,
        "trade metadata",
    )
    text = insert_after_once(text, r"foreach\s*\(\s*\$normalizedEvents\s+as\s+\$event\s*\)\s*\{", EVENT_SKIP_BLOCK, "event loop")

    response_pattern = re.compile(
        r"json_response\s*\(\s*\[\s*'ok'\s*=>\s*true\s*,\s*'accountKey'\s*=>\s*\$accountKey\s*,\s*'storedEvents'\s*=>\s*count\s*\(\s*\$normalizedEvents\s*\)\s*\]\s*,\s*201\s*\)\s*;",
        re.DOTALL,
    )
    matches = list(response_pattern.finditer(text))
    if not matches:
        raise RuntimeError("Could not find final ingest JSON response")
    match = matches[-1]
    text = text[:match.start()] + RESPONSE_BLOCK + text[match.end():]

    backup = path.with_suffix(path.suffix + ".pre-v47.4.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    target = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    path = target if target.is_file() else target / "Mobile/backend/ingest.php"
    if not path.is_file():
        raise FileNotFoundError(path)
    patch(path)
    print(f"Patched {path}")
    print(f"Backup: {path.with_suffix(path.suffix + '.pre-v47.4.bak')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
