-- Repair mutable trade projections whose entry-decision identity was replaced
-- by a later flat-account what-if decision. Immutable decisions and execution
-- stages are not modified. POSITION_VISIBLE is the first stage that can carry
-- the definitive MT5 position ticket for an entry execution.
UPDATE strategy_trades AS trade
JOIN (
    SELECT strategy_key, position_ticket, decision_id, spec_id
    FROM (
        SELECT
            strategy_key,
            position_ticket,
            decision_id,
            spec_id,
            ROW_NUMBER() OVER (
                PARTITION BY strategy_key, position_ticket
                ORDER BY occurred_at, id
            ) AS lifecycle_rank
        FROM strategy_execution_stages
        WHERE stage = 'POSITION_VISIBLE'
          AND position_ticket > 0
          AND decision_id IS NOT NULL
          AND decision_id <> ''
    ) AS ranked_lifecycle
    WHERE lifecycle_rank = 1
) AS lifecycle
  ON BINARY lifecycle.strategy_key = BINARY trade.strategy_key
 AND lifecycle.position_ticket = trade.position_ticket
LEFT JOIN strategy_decisions AS decision_record
  ON BINARY decision_record.strategy_key = BINARY lifecycle.strategy_key
 AND BINARY decision_record.decision_id = BINARY lifecycle.decision_id
LEFT JOIN strategy_specifications AS specification
  ON specification.spec_id = COALESCE(lifecycle.spec_id, decision_record.strategy_spec_id)
SET
    trade.decision_id = lifecycle.decision_id,
    trade.strategy_spec_id = COALESCE(
        lifecycle.spec_id,
        decision_record.strategy_spec_id,
        trade.strategy_spec_id
    ),
    trade.strategy_spec_hash = COALESCE(
        NULLIF(decision_record.strategy_spec_hash, ''),
        NULLIF(specification.spec_hash, ''),
        trade.strategy_spec_hash
    ),
    trade.strategy_build = COALESCE(
        NULLIF(decision_record.strategy_build, ''),
        trade.strategy_build
    ),
    trade.parameter_hash = COALESCE(
        NULLIF(decision_record.parameter_hash, ''),
        trade.parameter_hash
    ),
    trade.entry_leverage = COALESCE(
        decision_record.selected_leverage,
        trade.entry_leverage
    )
WHERE trade.decision_id IS NULL
   OR trade.decision_id = ''
   OR BINARY trade.decision_id <> BINARY lifecycle.decision_id;
