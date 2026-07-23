-- Repair generic close projections from the immutable accepted protection ledger.
-- Protective-stop strategy return uses the installed stop threshold; realized
-- cash P/L remains stored independently in strategy_trades.profit.
UPDATE strategy_trades t
JOIN (
    SELECT p.strategy_key, p.position_ticket, p.new_sl, p.reason
      FROM strategy_protection_changes p
      JOIN (
          SELECT strategy_key, position_ticket, MAX(id) AS latest_id
            FROM strategy_protection_changes
           WHERE result = TRUE AND new_sl > 0
           GROUP BY strategy_key, position_ticket
      ) latest ON latest.latest_id = p.id
) protection
  ON protection.strategy_key = t.strategy_key
 AND protection.position_ticket = t.position_ticket
SET t.close_price = protection.new_sl,
    t.exit_reason = CASE
        WHEN protection.reason REGEXP 'TSL_STOP_0\\.4000%'
            THEN 'TSL_0.4%'
        WHEN UPPER(protection.reason) LIKE '%HARD_SL%'
            THEN 'SL'
        ELSE t.exit_reason
    END
WHERE t.closed_at IS NOT NULL
  AND (TRIM(t.exit_reason) = '' OR UPPER(TRIM(t.exit_reason)) IN ('POSITION_CLOSED', 'CLOSED', 'UNKNOWN'))
  AND (protection.reason REGEXP 'TSL_STOP_0\\.4000%' OR UPPER(protection.reason) LIKE '%HARD_SL%');
