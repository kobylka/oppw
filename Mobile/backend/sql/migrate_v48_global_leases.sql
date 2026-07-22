-- OPPW MT5 v48: global MySQL coordination, fencing, and weekly-entry idempotency.
-- Run once after backing up the database.

CREATE TABLE IF NOT EXISTS strategy_runtime_leases (
    strategy_key VARCHAR(64) NOT NULL,
    lease_name VARCHAR(32) NOT NULL,
    owner_id CHAR(32) NOT NULL,
    fencing_token BIGINT UNSIGNED NOT NULL,
    hostname VARCHAR(120) NOT NULL DEFAULT '',
    process_id BIGINT NOT NULL DEFAULT 0,
    build_id VARCHAR(160) NOT NULL DEFAULT '',
    operation_id VARCHAR(96) NOT NULL DEFAULT '',
    operation_kind VARCHAR(64) NOT NULL DEFAULT '',
    acquired_at DATETIME(3) NOT NULL,
    heartbeat_at DATETIME(3) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    released_at DATETIME(3) NULL,
    metadata JSON NULL,
    PRIMARY KEY (strategy_key, lease_name),
    INDEX idx_runtime_lease_expiry (expires_at),
    CONSTRAINT fk_runtime_lease_account
        FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_weekly_entries (
    strategy_key VARCHAR(64) NOT NULL,
    week_key VARCHAR(10) NOT NULL,
    execution_id VARCHAR(96) NOT NULL,
    decision_id VARCHAR(64) NOT NULL DEFAULT '',
    owner_id CHAR(32) NOT NULL,
    executor_fencing_token BIGINT UNSIGNED NOT NULL,
    gate_fencing_token BIGINT UNSIGNED NOT NULL,
    status VARCHAR(16) NOT NULL,
    attempt_count INT UNSIGNED NOT NULL DEFAULT 1,
    claimed_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    order_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    deal_ticket BIGINT UNSIGNED NOT NULL DEFAULT 0,
    retcode INT NOT NULL DEFAULT -1,
    error_text VARCHAR(500) NOT NULL DEFAULT '',
    updated_at DATETIME(3) NOT NULL,
    PRIMARY KEY (strategy_key, week_key),
    UNIQUE KEY uq_weekly_entry_execution (strategy_key, execution_id),
    INDEX idx_weekly_entry_status (strategy_key, status, updated_at),
    CONSTRAINT fk_weekly_entry_account
        FOREIGN KEY (strategy_key)
        REFERENCES monitor_accounts(account_key)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- Backfill accepted entry claims from existing trade history. This prevents a
-- missing local state file from causing another BUY in a historically traded week.
INSERT IGNORE INTO strategy_weekly_entries (
    strategy_key,
    week_key,
    execution_id,
    decision_id,
    owner_id,
    executor_fencing_token,
    gate_fencing_token,
    status,
    attempt_count,
    claimed_at,
    completed_at,
    order_ticket,
    deal_ticket,
    retcode,
    error_text,
    updated_at
)
SELECT
    strategy_key,
    DATE_FORMAT(opened_at, '%x-W%v'),
    CONCAT('MIGRATED-', position_ticket),
    COALESCE(decision_id, ''),
    '00000000000000000000000000000000',
    0,
    0,
    'ACCEPTED',
    1,
    opened_at,
    COALESCE(closed_at, opened_at),
    position_ticket,
    0,
    10009,
    'Backfilled from strategy_trades by v48 migration',
    COALESCE(closed_at, opened_at)
FROM strategy_trades
WHERE opened_at IS NOT NULL
  AND position_ticket > 0;

