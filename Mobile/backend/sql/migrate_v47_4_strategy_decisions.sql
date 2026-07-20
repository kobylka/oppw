-- OPPW v47.4: durable, acknowledged strategy-decision persistence.
-- Run this before deploying the v47.4 ingest.php patch.

CREATE TABLE IF NOT EXISTS strategy_decisions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    decision_id CHAR(32) NOT NULL,
    decision_week VARCHAR(10) NOT NULL DEFAULT '',
    recorded_at DATETIME(3) NOT NULL,
    first_received_at DATETIME(3) NOT NULL,
    last_received_at DATETIME(3) NOT NULL,
    strategy_build VARCHAR(160) NOT NULL DEFAULT '',
    parameter_hash CHAR(64) NOT NULL DEFAULT '',
    decision_type VARCHAR(64) NOT NULL DEFAULT '',
    outcome VARCHAR(32) NOT NULL DEFAULT '',
    selected_leverage DECIMAL(12,6) NOT NULL DEFAULT 0,
    leverage_reason VARCHAR(1000) NOT NULL DEFAULT '',
    previous_full_week_change DECIMAL(18,10) NOT NULL DEFAULT 0,
    previous_full_week_source VARCHAR(100) NOT NULL DEFAULT '',
    previous_trade_change DECIMAL(18,10) NOT NULL DEFAULT 0,
    previous_trade_source VARCHAR(100) NOT NULL DEFAULT '',
    symbol VARCHAR(32) NOT NULL DEFAULT '',
    side VARCHAR(8) NOT NULL DEFAULT '',
    proposed_price DECIMAL(20,8) NULL,
    proposed_volume DECIMAL(20,8) NULL,
    required_deposit DECIMAL(20,4) NULL,
    required_balance DECIMAL(20,4) NULL,
    required_balance_multiplier DECIMAL(12,6) NULL,
    balance_multiplier_profile VARCHAR(40) NOT NULL DEFAULT '',
    effective_leverage DECIMAL(12,6) NULL,
    position_notional DECIMAL(20,4) NULL,
    sizing_units INT NULL,
    margin_usage_percent DECIMAL(12,6) NULL,
    margin_level_after_percent DECIMAL(12,6) NULL,
    stop_loss_percent DECIMAL(12,6) NULL,
    stop_loss_price DECIMAL(20,8) NULL,
    stop_loss_cash DECIMAL(20,4) NULL,
    account_return_at_stop_percent DECIMAL(12,6) NULL,
    account_loss_cap_applied BOOLEAN NOT NULL DEFAULT FALSE,
    error_text VARCHAR(1000) NOT NULL DEFAULT '',
    payload JSON NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_strategy_decision (strategy_key, decision_id),
    INDEX idx_decision_strategy_recorded (strategy_key, recorded_at, id),
    INDEX idx_decision_strategy_week (strategy_key, decision_week, recorded_at),
    INDEX idx_decision_strategy_build (strategy_key, strategy_build, recorded_at),
    INDEX idx_decision_strategy_outcome (strategy_key, outcome, recorded_at),
    CONSTRAINT fk_strategy_decision_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

DROP PROCEDURE IF EXISTS oppw_v47_4_add_decision_column;
DELIMITER $$
CREATE PROCEDURE oppw_v47_4_add_decision_column(IN column_name_value VARCHAR(64), IN definition_value TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'strategy_decisions' AND COLUMN_NAME = column_name_value
    ) THEN
        SET @sql_text = CONCAT('ALTER TABLE strategy_decisions ADD COLUMN ', column_name_value, ' ', definition_value);
        PREPARE statement_value FROM @sql_text;
        EXECUTE statement_value;
        DEALLOCATE PREPARE statement_value;
    END IF;
END$$
DELIMITER ;

CALL oppw_v47_4_add_decision_column('required_balance', 'DECIMAL(20,4) NULL AFTER required_deposit');
CALL oppw_v47_4_add_decision_column('required_balance_multiplier', 'DECIMAL(12,6) NULL AFTER required_balance');
CALL oppw_v47_4_add_decision_column('balance_multiplier_profile', 'VARCHAR(40) NOT NULL DEFAULT '''' AFTER required_balance_multiplier');
DROP PROCEDURE oppw_v47_4_add_decision_column;

-- Backfill or refresh decisions already embedded in stored snapshots.
INSERT INTO strategy_decisions(
    strategy_key, decision_id, decision_week, recorded_at, first_received_at, last_received_at,
    strategy_build, parameter_hash, decision_type, outcome, selected_leverage, leverage_reason,
    previous_full_week_change, previous_full_week_source, previous_trade_change, previous_trade_source,
    symbol, side, proposed_price, proposed_volume, required_deposit, required_balance,
    required_balance_multiplier, balance_multiplier_profile, effective_leverage,
    position_notional, sizing_units, margin_usage_percent, margin_level_after_percent,
    stop_loss_percent, stop_loss_price, stop_loss_cash, account_return_at_stop_percent,
    account_loss_cap_applied, error_text, payload
)
SELECT
    s.strategy_key,
    LEFT(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.decisionId')), 32),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.decisionWeek')), ''), 10),
    s.captured_at, s.captured_at, s.captured_at,
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.build')), ''), 160),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.parameterHash')), ''), 64),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.decision')), ''), 64),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.outcome')), ''), 32),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.selectedLeverage')) AS DECIMAL(12,6)), 0),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.leverageReason')), ''), 1000),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.inputs.previousFullWeekChange')) AS DECIMAL(18,10)), 0),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.inputs.previousFullWeekSource')), ''), 100),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.inputs.previousTradeChange')) AS DECIMAL(18,10)), 0),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.inputs.previousTradeSource')), ''), 100),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.symbol')), ''), 32),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.side')), ''), 8),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.price')) AS DECIMAL(20,8)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.volume')) AS DECIMAL(20,8)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.requiredDeposit')) AS DECIMAL(20,4)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.requiredBalance')) AS DECIMAL(20,4)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.requiredBalanceMultiplier')) AS DECIMAL(12,6)),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.balanceMultiplierProfile')), ''), 40),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.effectiveLeverage')) AS DECIMAL(12,6)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.positionNotional')) AS DECIMAL(20,4)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.sizingUnits')) AS SIGNED),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.marginUsagePercent')) AS DECIMAL(12,6)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.sizing.marginLevelAfterPercent')) AS DECIMAL(12,6)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.risk.potentialStopLossPercent')) AS DECIMAL(12,6)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.risk.potentialStopLossPrice')) AS DECIMAL(20,8)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.risk.potentialStopLossCash')) AS DECIMAL(20,4)),
    CAST(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.risk.accountLossPercentAtStop')) AS DECIMAL(12,6)),
    CASE WHEN LOWER(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.risk.accountLossCapApplied')), 'false')) IN ('true','1') THEN 1 ELSE 0 END,
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.error')), ''), 1000),
    JSON_EXTRACT(s.payload, '$.strategyDecision')
FROM strategy_snapshots s
WHERE JSON_EXTRACT(s.payload, '$.strategyDecision.decisionId') IS NOT NULL
  AND COALESCE(JSON_UNQUOTE(JSON_EXTRACT(s.payload, '$.strategyDecision.decisionId')), '') <> ''
ORDER BY s.id
ON DUPLICATE KEY UPDATE
    recorded_at=LEAST(recorded_at,VALUES(recorded_at)),
    first_received_at=LEAST(first_received_at,VALUES(first_received_at)),
    last_received_at=GREATEST(last_received_at,VALUES(last_received_at)),
    decision_week=VALUES(decision_week), strategy_build=VALUES(strategy_build), parameter_hash=VALUES(parameter_hash),
    decision_type=VALUES(decision_type), outcome=VALUES(outcome), selected_leverage=VALUES(selected_leverage),
    leverage_reason=VALUES(leverage_reason), previous_full_week_change=VALUES(previous_full_week_change),
    previous_full_week_source=VALUES(previous_full_week_source), previous_trade_change=VALUES(previous_trade_change),
    previous_trade_source=VALUES(previous_trade_source), symbol=VALUES(symbol), side=VALUES(side),
    proposed_price=VALUES(proposed_price), proposed_volume=VALUES(proposed_volume), required_deposit=VALUES(required_deposit),
    required_balance=VALUES(required_balance), required_balance_multiplier=VALUES(required_balance_multiplier),
    balance_multiplier_profile=VALUES(balance_multiplier_profile), effective_leverage=VALUES(effective_leverage),
    position_notional=VALUES(position_notional), sizing_units=VALUES(sizing_units),
    margin_usage_percent=VALUES(margin_usage_percent), margin_level_after_percent=VALUES(margin_level_after_percent),
    stop_loss_percent=VALUES(stop_loss_percent), stop_loss_price=VALUES(stop_loss_price), stop_loss_cash=VALUES(stop_loss_cash),
    account_return_at_stop_percent=VALUES(account_return_at_stop_percent), account_loss_cap_applied=VALUES(account_loss_cap_applied),
    error_text=VALUES(error_text), payload=VALUES(payload);

DROP PROCEDURE IF EXISTS oppw_v47_4_add_trade_column;
DELIMITER $$
CREATE PROCEDURE oppw_v47_4_add_trade_column(IN column_name_value VARCHAR(64), IN definition_value TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'strategy_trades' AND COLUMN_NAME = column_name_value
    ) THEN
        SET @sql_text = CONCAT('ALTER TABLE strategy_trades ADD COLUMN ', column_name_value, ' ', definition_value);
        PREPARE statement_value FROM @sql_text;
        EXECUTE statement_value;
        DEALLOCATE PREPARE statement_value;
    END IF;
END$$
DELIMITER ;

CALL oppw_v47_4_add_trade_column('decision_id', 'CHAR(32) NULL AFTER position_ticket');
CALL oppw_v47_4_add_trade_column('strategy_build', 'VARCHAR(160) NOT NULL DEFAULT '''' AFTER decision_id');
CALL oppw_v47_4_add_trade_column('parameter_hash', 'CHAR(64) NOT NULL DEFAULT '''' AFTER strategy_build');
CALL oppw_v47_4_add_trade_column('entry_leverage', 'DECIMAL(12,6) NULL AFTER parameter_hash');
DROP PROCEDURE oppw_v47_4_add_trade_column;

SET @decision_index_exists = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'strategy_trades' AND INDEX_NAME = 'idx_trade_strategy_decision'
);
SET @decision_index_sql = IF(
    @decision_index_exists = 0,
    'ALTER TABLE strategy_trades ADD INDEX idx_trade_strategy_decision (strategy_key, decision_id)',
    'SELECT 1'
);
PREPARE decision_index_statement FROM @decision_index_sql;
EXECUTE decision_index_statement;
DEALLOCATE PREPARE decision_index_statement;
