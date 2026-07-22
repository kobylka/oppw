-- OPPW v51: canonical strategy specifications and immutable authority ledgers.
-- Apply after all earlier migrations and before deploying the v51 backend.

CREATE TABLE IF NOT EXISTS strategy_specifications (
    spec_id CHAR(32) NOT NULL,
    spec_hash CHAR(64) NOT NULL,
    spec_key VARCHAR(64) NOT NULL,
    spec_version VARCHAR(32) NOT NULL,
    effective_from DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    strategy_build VARCHAR(160) NOT NULL,
    execution_symbol VARCHAR(32) NOT NULL,
    signal_symbol VARCHAR(32) NOT NULL,
    document JSON NOT NULL,
    document_hash CHAR(64) NOT NULL,
    PRIMARY KEY (spec_id),
    UNIQUE KEY uq_strategy_spec_hash (spec_hash),
    UNIQUE KEY uq_strategy_spec_version (spec_key, spec_version, spec_hash),
    INDEX idx_strategy_spec_effective (spec_key, effective_from),
    CHECK (spec_hash = document_hash)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_account_spec_assignments (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    spec_id CHAR(32) NOT NULL,
    assigned_at DATETIME(3) NOT NULL,
    owner_id CHAR(32) NOT NULL DEFAULT '',
    fencing_token BIGINT UNSIGNED NOT NULL DEFAULT 0,
    strategy_build VARCHAR(160) NOT NULL DEFAULT '',
    PRIMARY KEY (id),
    UNIQUE KEY uq_account_spec_assignment (strategy_key, spec_id),
    INDEX idx_account_spec_current (strategy_key, assigned_at, id),
    CONSTRAINT fk_account_spec_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_account_spec_document FOREIGN KEY (spec_id)
        REFERENCES strategy_specifications(spec_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_execution_stages (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    stage_record_id CHAR(64) NOT NULL,
    execution_id VARCHAR(96) NOT NULL,
    decision_id CHAR(32) NULL,
    spec_id CHAR(32) NULL,
    position_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    stage VARCHAR(40) NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    scheduled_at DATETIME(3) NULL,
    result BOOLEAN NULL,
    reference_price DECIMAL(20,8) NULL,
    actual_price DECIMAL(20,8) NULL,
    latency_ms DECIMAL(20,6) NULL,
    retcode INT NULL,
    filling_mode VARCHAR(32) NOT NULL DEFAULT '',
    reason VARCHAR(100) NOT NULL DEFAULT '',
    order_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    deal_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    side VARCHAR(8) NOT NULL DEFAULT '',
    volume DECIMAL(20,8) NULL,
    payload JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_execution_stage_record (strategy_key, stage_record_id),
    INDEX idx_execution_stage_timeline (strategy_key, execution_id, occurred_at, id),
    INDEX idx_execution_stage_position (strategy_key, position_ticket, occurred_at),
    CONSTRAINT fk_execution_stage_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_execution_stage_spec FOREIGN KEY (spec_id)
        REFERENCES strategy_specifications(spec_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_fills (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    fill_record_id CHAR(64) NOT NULL,
    execution_id VARCHAR(96) NOT NULL,
    decision_id CHAR(32) NULL,
    spec_id CHAR(32) NULL,
    position_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    order_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    deal_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    side VARCHAR(8) NOT NULL,
    filled_at DATETIME(3) NOT NULL,
    reference_price DECIMAL(20,8) NULL,
    fill_price DECIMAL(20,8) NOT NULL,
    volume DECIMAL(20,8) NULL,
    retcode INT NULL,
    filling_mode VARCHAR(32) NOT NULL DEFAULT '',
    fill_source VARCHAR(40) NOT NULL DEFAULT 'EXECUTION_STAGE',
    is_exact BOOLEAN NOT NULL DEFAULT TRUE,
    payload JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_strategy_fill_record (strategy_key, fill_record_id),
    INDEX idx_fill_execution (strategy_key, execution_id, filled_at),
    INDEX idx_fill_position (strategy_key, position_ticket, filled_at),
    INDEX idx_fill_deal (strategy_key, deal_ticket),
    CONSTRAINT fk_fill_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_fill_spec FOREIGN KEY (spec_id)
        REFERENCES strategy_specifications(spec_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_protection_changes (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    change_record_id CHAR(64) NOT NULL,
    execution_id VARCHAR(96) NOT NULL DEFAULT '',
    decision_id CHAR(32) NULL,
    spec_id CHAR(32) NULL,
    position_ticket BIGINT UNSIGNED NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    change_stage VARCHAR(32) NOT NULL,
    old_sl DECIMAL(20,8) NULL,
    new_sl DECIMAL(20,8) NULL,
    old_tp DECIMAL(20,8) NULL,
    new_tp DECIMAL(20,8) NULL,
    reason VARCHAR(160) NOT NULL DEFAULT '',
    result BOOLEAN NULL,
    retcode INT NULL,
    payload JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_protection_change_record (strategy_key, change_record_id),
    INDEX idx_protection_position_time (strategy_key, position_ticket, occurred_at, id),
    CONSTRAINT fk_protection_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_protection_spec FOREIGN KEY (spec_id)
        REFERENCES strategy_specifications(spec_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_trade_ledger (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    trade_record_id CHAR(64) NOT NULL,
    position_ticket BIGINT UNSIGNED NOT NULL,
    execution_id VARCHAR(96) NOT NULL DEFAULT '',
    decision_id CHAR(32) NULL,
    spec_id CHAR(32) NULL,
    transition_type VARCHAR(32) NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    symbol VARCHAR(32) NOT NULL DEFAULT '',
    side VARCHAR(8) NOT NULL DEFAULT '',
    volume DECIMAL(20,8) NULL,
    price DECIMAL(20,8) NULL,
    reason VARCHAR(100) NOT NULL DEFAULT '',
    payload JSON NOT NULL,
    payload_hash CHAR(64) NOT NULL,
    received_at DATETIME(3) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_trade_ledger_record (strategy_key, trade_record_id),
    INDEX idx_trade_ledger_position (strategy_key, position_ticket, occurred_at, id),
    CONSTRAINT fk_trade_ledger_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE CASCADE,
    CONSTRAINT fk_trade_ledger_spec FOREIGN KEY (spec_id)
        REFERENCES strategy_specifications(spec_id)
) ENGINE=InnoDB;

DROP PROCEDURE IF EXISTS oppw_v51_add_column;
DELIMITER $$
CREATE PROCEDURE oppw_v51_add_column(IN table_name_value VARCHAR(64), IN column_name_value VARCHAR(64), IN definition_value TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND COLUMN_NAME = column_name_value
    ) THEN
        SET @sql_text = CONCAT('ALTER TABLE ', table_name_value, ' ADD COLUMN ', column_name_value, ' ', definition_value);
        PREPARE statement_value FROM @sql_text;
        EXECUTE statement_value;
        DEALLOCATE PREPARE statement_value;
    END IF;
END$$
DELIMITER ;

CALL oppw_v51_add_column('strategy_decisions', 'strategy_spec_id', 'CHAR(32) NULL AFTER decision_id');
CALL oppw_v51_add_column('strategy_decisions', 'strategy_spec_hash', 'CHAR(64) NOT NULL DEFAULT '''' AFTER strategy_spec_id');
CALL oppw_v51_add_column('strategy_decisions', 'payload_hash', 'CHAR(64) NOT NULL DEFAULT '''' AFTER payload');
CALL oppw_v51_add_column('strategy_trades', 'strategy_spec_id', 'CHAR(32) NULL AFTER decision_id');
CALL oppw_v51_add_column('strategy_trades', 'strategy_spec_hash', 'CHAR(64) NOT NULL DEFAULT '''' AFTER strategy_spec_id');
CALL oppw_v51_add_column('account_cash_flows', 'payload_hash', 'CHAR(64) NOT NULL DEFAULT '''' AFTER note');
DROP PROCEDURE oppw_v51_add_column;

DROP PROCEDURE IF EXISTS oppw_v51_add_index;
DELIMITER $$
CREATE PROCEDURE oppw_v51_add_index(IN table_name_value VARCHAR(64), IN index_name_value VARCHAR(64), IN definition_value TEXT)
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = table_name_value AND INDEX_NAME = index_name_value
    ) THEN
        SET @sql_text = CONCAT('ALTER TABLE ', table_name_value, ' ADD INDEX ', index_name_value, ' ', definition_value);
        PREPARE statement_value FROM @sql_text;
        EXECUTE statement_value;
        DEALLOCATE PREPARE statement_value;
    END IF;
END$$
DELIMITER ;

CALL oppw_v51_add_index('strategy_decisions', 'idx_decision_spec', '(strategy_key,strategy_spec_id,recorded_at)');
CALL oppw_v51_add_index('strategy_trades', 'idx_trade_spec', '(strategy_key,strategy_spec_id,opened_at)');
DROP PROCEDURE oppw_v51_add_index;

UPDATE strategy_decisions
SET payload_hash = SHA2(CAST(payload AS CHAR CHARACTER SET utf8mb4), 256)
WHERE payload_hash = '';

UPDATE account_cash_flows
SET payload_hash = SHA2(CONCAT_WS('|', strategy_key, occurred_at, flow_type, amount, balance_after, source, COALESCE(reference_key, ''), note), 256)
WHERE payload_hash = '';

-- Authority tables are append-only. Projections such as strategy_trades remain
-- mutable because they are reconstructed views over these immutable records.
DROP TRIGGER IF EXISTS strategy_specifications_no_update;
DROP TRIGGER IF EXISTS strategy_specifications_no_delete;
DROP TRIGGER IF EXISTS strategy_account_spec_assignments_no_update;
DROP TRIGGER IF EXISTS strategy_account_spec_assignments_no_delete;
DROP TRIGGER IF EXISTS strategy_decisions_no_update;
DROP TRIGGER IF EXISTS strategy_decisions_no_delete;
DROP TRIGGER IF EXISTS strategy_execution_stages_no_update;
DROP TRIGGER IF EXISTS strategy_execution_stages_no_delete;
DROP TRIGGER IF EXISTS strategy_fills_no_update;
DROP TRIGGER IF EXISTS strategy_fills_no_delete;
DROP TRIGGER IF EXISTS strategy_protection_changes_no_update;
DROP TRIGGER IF EXISTS strategy_protection_changes_no_delete;
DROP TRIGGER IF EXISTS strategy_trade_ledger_no_update;
DROP TRIGGER IF EXISTS strategy_trade_ledger_no_delete;
DROP TRIGGER IF EXISTS account_cash_flows_no_update;
DROP TRIGGER IF EXISTS account_cash_flows_no_delete;

DELIMITER $$
CREATE TRIGGER strategy_specifications_no_update BEFORE UPDATE ON strategy_specifications FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy specifications are immutable'; END$$
CREATE TRIGGER strategy_specifications_no_delete BEFORE DELETE ON strategy_specifications FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy specifications are immutable'; END$$
CREATE TRIGGER strategy_account_spec_assignments_no_update BEFORE UPDATE ON strategy_account_spec_assignments FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy specification assignments are immutable'; END$$
CREATE TRIGGER strategy_account_spec_assignments_no_delete BEFORE DELETE ON strategy_account_spec_assignments FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy specification assignments are immutable'; END$$
CREATE TRIGGER strategy_decisions_no_update BEFORE UPDATE ON strategy_decisions FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy decisions are immutable'; END$$
CREATE TRIGGER strategy_decisions_no_delete BEFORE DELETE ON strategy_decisions FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy decisions are immutable'; END$$
CREATE TRIGGER strategy_execution_stages_no_update BEFORE UPDATE ON strategy_execution_stages FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'execution stages are immutable'; END$$
CREATE TRIGGER strategy_execution_stages_no_delete BEFORE DELETE ON strategy_execution_stages FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'execution stages are immutable'; END$$
CREATE TRIGGER strategy_fills_no_update BEFORE UPDATE ON strategy_fills FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'fills are immutable'; END$$
CREATE TRIGGER strategy_fills_no_delete BEFORE DELETE ON strategy_fills FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'fills are immutable'; END$$
CREATE TRIGGER strategy_protection_changes_no_update BEFORE UPDATE ON strategy_protection_changes FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'protection changes are immutable'; END$$
CREATE TRIGGER strategy_protection_changes_no_delete BEFORE DELETE ON strategy_protection_changes FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'protection changes are immutable'; END$$
CREATE TRIGGER strategy_trade_ledger_no_update BEFORE UPDATE ON strategy_trade_ledger FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'trade ledger records are immutable'; END$$
CREATE TRIGGER strategy_trade_ledger_no_delete BEFORE DELETE ON strategy_trade_ledger FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'trade ledger records are immutable'; END$$
CREATE TRIGGER account_cash_flows_no_update BEFORE UPDATE ON account_cash_flows FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'cash-flow records are immutable'; END$$
CREATE TRIGGER account_cash_flows_no_delete BEFORE DELETE ON account_cash_flows FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'cash-flow records are immutable'; END$$
DELIMITER ;
