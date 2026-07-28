-- OPPW data lifecycle: verified retention runs, indefinite equity daily projection,
-- and an explicit no-delete guarantee for minute market OHLC history.

CREATE TABLE IF NOT EXISTS strategy_equity_daily (
    strategy_key VARCHAR(64) NOT NULL,
    equity_day DATE NOT NULL,
    first_captured_at DATETIME NOT NULL,
    last_captured_at DATETIME NOT NULL,
    open_balance DECIMAL(20,4) NOT NULL,
    open_equity DECIMAL(20,4) NOT NULL,
    close_balance DECIMAL(20,4) NOT NULL,
    close_equity DECIMAL(20,4) NOT NULL,
    minimum_equity DECIMAL(20,4) NOT NULL,
    maximum_equity DECIMAL(20,4) NOT NULL,
    sample_count BIGINT UNSIGNED NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (strategy_key, equity_day),
    INDEX idx_equity_daily_day (equity_day, strategy_key),
    CONSTRAINT fk_equity_daily_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_retention_runs (
    run_id CHAR(32) NOT NULL,
    dataset_name VARCHAR(64) NOT NULL,
    cutoff_at DATETIME(3) NOT NULL,
    first_source_key VARCHAR(160) NOT NULL,
    last_source_key VARCHAR(160) NOT NULL,
    row_count BIGINT UNSIGNED NOT NULL,
    archive_name VARCHAR(255) NOT NULL,
    archive_sha256 CHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    error_text VARCHAR(1000) NOT NULL DEFAULT '',
    PRIMARY KEY (run_id),
    UNIQUE KEY uq_retention_archive (dataset_name, archive_sha256),
    INDEX idx_retention_dataset_time (dataset_name, completed_at, run_id),
    CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED'))
) ENGINE=InnoDB;

DROP PROCEDURE IF EXISTS oppw_add_lifecycle_index;
DELIMITER $$
CREATE PROCEDURE oppw_add_lifecycle_index(IN table_name_value VARCHAR(64), IN index_name_value VARCHAR(64), IN definition_value TEXT)
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

CALL oppw_add_lifecycle_index('strategy_events', 'idx_event_retention_time', '(event_time,id)');
CALL oppw_add_lifecycle_index('strategy_equity_points', 'idx_equity_retention_time', '(captured_minute,strategy_key)');
DROP PROCEDURE oppw_add_lifecycle_index;

ALTER TABLE strategy_market_points
    DROP FOREIGN KEY fk_market_account;
ALTER TABLE strategy_market_points
    ADD CONSTRAINT fk_market_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key) ON DELETE RESTRICT;

DROP TRIGGER IF EXISTS strategy_market_points_no_delete;
DELIMITER $$
CREATE TRIGGER strategy_market_points_no_delete
BEFORE DELETE ON strategy_market_points FOR EACH ROW
BEGIN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'strategy_market_points minute OHLC history is retained indefinitely';
END$$
DELIMITER ;
