-- OPPW Monitor v12: persistent Guy Fleury trade labels.
-- Back up the database and run once.
USE oppw_monitor;

ALTER TABLE strategy_trades
    ADD COLUMN preleverage_return_percent DECIMAL(12,6) NULL AFTER profit_percent,
    ADD COLUMN trade_class CHAR(1) NULL AFTER preleverage_return_percent,
    ADD INDEX idx_trade_strategy_class(strategy_key, trade_class, closed_at);

UPDATE strategy_trades
SET preleverage_return_percent = CASE WHEN closed_at IS NOT NULL AND open_price > 0 AND close_price > 0 THEN (close_price / open_price - 1.0) * 100.0 ELSE NULL END,
    trade_class = CASE
        WHEN closed_at IS NULL OR open_price <= 0 OR close_price IS NULL OR close_price <= 0 THEN NULL
        WHEN close_price / open_price - 1.0 >= 0.007 THEN 'A'
        WHEN close_price / open_price - 1.0 >= 0.0 THEN 'B'
        WHEN UPPER(REPLACE(exit_reason, '-', '_')) LIKE 'TSL%'
          OR UPPER(REPLACE(exit_reason, '-', '_')) IN ('BE','BH','BEO','BEPRE','BREAK_EVEN','BREAK_EVEN_EXIT')
          OR UPPER(REPLACE(exit_reason, '-', '_')) LIKE '%BREAK_EVEN%' THEN 'C'
        ELSE 'D'
    END;

DROP TRIGGER IF EXISTS strategy_trades_class_before_insert;
DROP TRIGGER IF EXISTS strategy_trades_class_before_update;

DELIMITER $$
CREATE TRIGGER strategy_trades_class_before_insert
BEFORE INSERT ON strategy_trades FOR EACH ROW
BEGIN
    IF NEW.closed_at IS NOT NULL AND NEW.open_price > 0 AND NEW.close_price IS NOT NULL AND NEW.close_price > 0 THEN
        SET NEW.preleverage_return_percent = (NEW.close_price / NEW.open_price - 1.0) * 100.0;
        SET NEW.trade_class = CASE
            WHEN NEW.close_price / NEW.open_price - 1.0 >= 0.007 THEN 'A'
            WHEN NEW.close_price / NEW.open_price - 1.0 >= 0.0 THEN 'B'
            WHEN UPPER(REPLACE(NEW.exit_reason, '-', '_')) LIKE 'TSL%'
              OR UPPER(REPLACE(NEW.exit_reason, '-', '_')) IN ('BE','BH','BEO','BEPRE','BREAK_EVEN','BREAK_EVEN_EXIT')
              OR UPPER(REPLACE(NEW.exit_reason, '-', '_')) LIKE '%BREAK_EVEN%' THEN 'C'
            ELSE 'D'
        END;
    END IF;
END$$
CREATE TRIGGER strategy_trades_class_before_update
BEFORE UPDATE ON strategy_trades FOR EACH ROW
BEGIN
    IF NEW.closed_at IS NOT NULL AND NEW.open_price > 0 AND NEW.close_price IS NOT NULL AND NEW.close_price > 0 THEN
        SET NEW.preleverage_return_percent = (NEW.close_price / NEW.open_price - 1.0) * 100.0;
        SET NEW.trade_class = CASE
            WHEN NEW.close_price / NEW.open_price - 1.0 >= 0.007 THEN 'A'
            WHEN NEW.close_price / NEW.open_price - 1.0 >= 0.0 THEN 'B'
            WHEN UPPER(REPLACE(NEW.exit_reason, '-', '_')) LIKE 'TSL%'
              OR UPPER(REPLACE(NEW.exit_reason, '-', '_')) IN ('BE','BH','BEO','BEPRE','BREAK_EVEN','BREAK_EVEN_EXIT')
              OR UPPER(REPLACE(NEW.exit_reason, '-', '_')) LIKE '%BREAK_EVEN%' THEN 'C'
            ELSE 'D'
        END;
    ELSE
        SET NEW.preleverage_return_percent = NULL;
        SET NEW.trade_class = NULL;
    END IF;
END$$
DELIMITER ;
