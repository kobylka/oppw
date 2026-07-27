-- strategy_snapshots is a current mobile projection, not historical authority.
-- Production with the legacy multi-row table should drop that table before
-- applying this migration, as the operator elected to discard its 6 GB history.

CREATE TABLE IF NOT EXISTS strategy_snapshots (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    captured_at DATETIME(3) NOT NULL,
    payload JSON NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_snapshot_strategy (strategy_key),
    INDEX idx_snapshot_strategy_time (strategy_key, captured_at, id),
    CONSTRAINT fk_snapshot_account FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key)
) ENGINE=InnoDB;

-- Fresh databases already receive this key from schema.sql. This conditional
-- DDL also upgrades an empty or manually deduplicated legacy table. It fails
-- safely if historical duplicates remain instead of deleting them implicitly.
SET @oppw_snapshot_unique_exists = (
    SELECT COUNT(*)
      FROM information_schema.STATISTICS
     WHERE TABLE_SCHEMA = DATABASE()
       AND TABLE_NAME = 'strategy_snapshots'
       AND INDEX_NAME = 'uq_snapshot_strategy'
);
SET @oppw_snapshot_unique_ddl = IF(
    @oppw_snapshot_unique_exists > 0,
    'SELECT 1',
    'ALTER TABLE strategy_snapshots ADD UNIQUE KEY uq_snapshot_strategy (strategy_key)'
);
PREPARE oppw_snapshot_unique_stmt FROM @oppw_snapshot_unique_ddl;
EXECUTE oppw_snapshot_unique_stmt;
DEALLOCATE PREPARE oppw_snapshot_unique_stmt;
