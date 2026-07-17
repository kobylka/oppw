CREATE TABLE IF NOT EXISTS strategy_equity_points (
    strategy_key VARCHAR(64) NOT NULL,
    captured_minute DATETIME NOT NULL,
    balance DECIMAL(20, 4) NOT NULL DEFAULT 0,
    equity DECIMAL(20, 4) NOT NULL DEFAULT 0,
    deposit DECIMAL(20, 4) NOT NULL DEFAULT 0,
    current_profit DECIMAL(20, 4) NOT NULL DEFAULT 0,
    position_ticket BIGINT UNSIGNED NULL,
    PRIMARY KEY (strategy_key, captured_minute),
    INDEX idx_equity_strategy_time (strategy_key, captured_minute),
    CONSTRAINT fk_equity_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_market_points (
    strategy_key VARCHAR(64) NOT NULL,
    captured_minute DATETIME NOT NULL,
    current_price DECIMAL(20, 8) NULL,
    bid DECIMAL(20, 8) NULL,
    ask DECIMAL(20, 8) NULL,
    m1_open DECIMAL(20, 8) NULL,
    m1_high DECIMAL(20, 8) NULL,
    m1_low DECIMAL(20, 8) NULL,
    m1_close DECIMAL(20, 8) NULL,
    phase VARCHAR(64) NOT NULL DEFAULT '',
    PRIMARY KEY (strategy_key, captured_minute),
    INDEX idx_market_strategy_time (strategy_key, captured_minute),
    CONSTRAINT fk_market_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS strategy_trades (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    position_ticket BIGINT UNSIGNED NOT NULL,
    symbol VARCHAR(32) NOT NULL DEFAULT '',
    side VARCHAR(8) NOT NULL DEFAULT 'BUY',
    volume DECIMAL(20, 8) NOT NULL DEFAULT 0,
    opened_at DATETIME(3) NOT NULL,
    closed_at DATETIME(3) NULL,
    open_price DECIMAL(20, 8) NOT NULL DEFAULT 0,
    close_price DECIMAL(20, 8) NULL,
    profit DECIMAL(20, 4) NULL,
    profit_percent DECIMAL(12, 6) NULL,
    exit_reason VARCHAR(100) NOT NULL DEFAULT '',
    balance_before DECIMAL(20, 4) NULL,
    balance_after DECIMAL(20, 4) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_trade_ticket (strategy_key, position_ticket),
    INDEX idx_trade_strategy_opened (strategy_key, opened_at),
    CONSTRAINT fk_trade_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS account_cash_flows (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    strategy_key VARCHAR(64) NOT NULL,
    occurred_at DATETIME(3) NOT NULL,
    flow_type VARCHAR(32) NOT NULL,
    amount DECIMAL(20, 4) NOT NULL,
    balance_after DECIMAL(20, 4) NOT NULL,
    source VARCHAR(32) NOT NULL DEFAULT 'MANUAL',
    reference_key VARCHAR(100) NULL,
    note VARCHAR(255) NOT NULL DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_cash_flow_reference (strategy_key, reference_key),
    INDEX idx_cash_flow_strategy_time (strategy_key, occurred_at),
    CONSTRAINT fk_cash_flow_account FOREIGN KEY (strategy_key) REFERENCES monitor_accounts(account_key) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Backfill equity and market minute history from existing JSON snapshots.
INSERT INTO strategy_equity_points(strategy_key, captured_minute, balance, equity, deposit, current_profit, position_ticket)
SELECT
    strategy_key,
    STR_TO_DATE(DATE_FORMAT(captured_at, '%Y-%m-%d %H:%i:00'), '%Y-%m-%d %H:%i:%s'),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.account.balance')) AS DECIMAL(20,4)), 0),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.account.equity')) AS DECIMAL(20,4)), 0),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.account.deposit')) AS DECIMAL(20,4)), 0),
    COALESCE(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.metrics.currentProfit')) AS DECIMAL(20,4)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.position.ticket')) AS UNSIGNED), 0)
FROM strategy_snapshots
ON DUPLICATE KEY UPDATE
    balance = VALUES(balance),
    equity = VALUES(equity),
    deposit = VALUES(deposit),
    current_profit = VALUES(current_profit),
    position_ticket = VALUES(position_ticket);

INSERT INTO strategy_market_points(strategy_key, captured_minute, current_price, bid, ask, m1_open, m1_high, m1_low, m1_close, phase)
SELECT
    strategy_key,
    STR_TO_DATE(DATE_FORMAT(captured_at, '%Y-%m-%d %H:%i:00'), '%Y-%m-%d %H:%i:%s'),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.currentPrice')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.bid')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.ask')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.currentM1.open')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.currentM1.high')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.currentM1.low')) AS DECIMAL(20,8)), 0),
    NULLIF(CAST(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.market.currentM1.close')) AS DECIMAL(20,8)), 0),
    LEFT(COALESCE(JSON_UNQUOTE(JSON_EXTRACT(payload, '$.connection.phase')), ''), 64)
FROM strategy_snapshots
ON DUPLICATE KEY UPDATE
    current_price = VALUES(current_price),
    bid = VALUES(bid),
    ask = VALUES(ask),
    m1_open = VALUES(m1_open),
    m1_high = VALUES(m1_high),
    m1_low = VALUES(m1_low),
    m1_close = VALUES(m1_close),
    phase = VALUES(phase);
