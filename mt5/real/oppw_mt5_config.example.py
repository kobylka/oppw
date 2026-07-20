"""OPPW MT5 v47.4 account configuration template.

Copy this file beside oppw_mt5_continuous.py using the account-specific local
name expected by the launcher:

DEMO: oppw-mt5-config.py
REAL: real-mt5-config.py

Keep the local file out of Git. Environment variables override the values here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or not value.strip() else int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or not value.strip() else float(value)


def env_time(name: str, default: time) -> time:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return time.fromisoformat(value.strip())


# Local credentials. Keep placeholders in Git; set actual values only in ignored files.
MT5_TERMINAL_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"
MT5_LOGIN = 0
MT5_PASSWORD = ""
MT5_SERVER = ""
MONITOR_WRITE_TOKEN = ""


@dataclass(frozen=True)
class Config:
    # Identity and symbols
    config_name: str = os.getenv("OPPW_CONFIG_NAME", "REAL")
    trade_symbol: str = os.getenv("OPPW_TRADE_SYMBOL", "US100")
    signal_symbol: str = os.getenv("OPPW_SIGNAL_SYMBOL", "US100")
    timezone_name: str = os.getenv("OPPW_TIMEZONE", "Europe/Warsaw")
    market_timezone_name: str = os.getenv("OPPW_MARKET_TIMEZONE", "America/New_York")
    exchange_calendar: str = os.getenv("OPPW_EXCHANGE_CALENDAR", "XNYS")

    # MT5 connection
    terminal_path: str = os.getenv("OPPW_TERMINAL_PATH", MT5_TERMINAL_PATH)
    login: int = env_int("OPPW_LOGIN", MT5_LOGIN)
    password: str = os.getenv("OPPW_PASSWORD", MT5_PASSWORD)
    server: str = os.getenv("OPPW_SERVER", MT5_SERVER)

    # Order execution
    magic: int = env_int("OPPW_MAGIC", 240024)
    comment_prefix: str = os.getenv("OPPW_COMMENT", "OPPW24")
    deviation_points: int = env_int("OPPW_DEVIATION", 20)
    filling_mode: str = os.getenv("OPPW_FILLING_MODE", "AUTO")
    poll_seconds: float = env_float("OPPW_POLL_SECONDS", 0.20)
    entry_window_seconds: int = env_int("OPPW_ENTRY_WINDOW_SECONDS", 55)
    reconnect_seconds: float = env_float("OPPW_RECONNECT_SECONDS", 3.0)
    maximum_tick_age_seconds: float = env_float("OPPW_MAX_TICK_AGE_SECONDS", 10.0)
    request_retry_seconds: float = env_float("OPPW_REQUEST_RETRY_SECONDS", 1.0)

    # Independent execution clocks
    entry_action_lead_seconds: float = env_float("OPPW_ENTRY_ACTION_LEAD_SECONDS", 3.0)
    non_entry_action_lead_seconds: float = env_float("OPPW_NON_ENTRY_ACTION_LEAD_SECONDS", 3.0)

    # Strategy and leverage selection
    base_leverage: int = env_int("OPPW_BASE_LEVERAGE", 8)
    loss_leverage: int = env_int("OPPW_LOSS_LEVERAGE", 10)
    full_week_loss_trigger: float = env_float("OPPW_FULL_WEEK_LOSS_TRIGGER", -0.025)
    previous_trade_loss_trigger: float = env_float("OPPW_PREVIOUS_TRADE_LOSS_TRIGGER", -0.007)
    break_even_ratio: float = env_float("OPPW_BE", 0.996)
    tsl_stop: float = env_float("OPPW_TSL_STOP", 0.004)
    leverage_stop_points: float = env_float("OPPW_LEVERAGE_STOP_POINTS", 50.0)

    # OH/CH targets by weekday
    tpp_monday: float = env_float("OPPW_TPP_MONDAY", 0.007)
    tpp_tuesday: float = env_float("OPPW_TPP_TUESDAY", 0.020)
    tpp_wednesday: float = env_float("OPPW_TPP_WEDNESDAY", 0.050)
    tpp_thursday: float = env_float("OPPW_TPP_THURSDAY", 0.050)
    tpp_friday: float = env_float("OPPW_TPP_FRIDAY", 0.050)

    # Broker exposure and required-balance sizing
    sizing_multiplier: float = env_float("OPPW_SIZING_MULTIPLIER", 20.0)
    required_balance_multiplier: float = env_float("OPPW_REQUIRED_BALANCE_MULTIPLIER", 1.765)
    legacy_required_balance_multiplier_l10: float = env_float("OPPW_LEGACY_REQUIRED_BALANCE_MULTIPLIER_L10", 2.0)
    legacy_required_balance_multiplier_l8: float = env_float("OPPW_LEGACY_REQUIRED_BALANCE_MULTIPLIER_L8", 2.5)
    use_legacy_balance_multiplier: bool = False
    max_account_stop_loss_fraction: float = env_float("OPPW_MAX_ACCOUNT_STOP_LOSS_FRACTION", 0.50)
    broker_margin_leverage_fallback: float = env_float("OPPW_BROKER_MARGIN_LEVERAGE_FALLBACK", 20.0)

    # Role and safety
    manage_manual_position: bool = env_bool("OPPW_MANAGE_MANUAL_POSITION", True)
    live_enabled: bool = env_bool("OPPW_LIVE", False)
    autotrading_reminder_seconds: float = env_float("OPPW_AUTOTRADING_REMINDER_SECONDS", 60.0)
    stale_tick_reminder_seconds: float = env_float("OPPW_STALE_TICK_REMINDER_SECONDS", 60.0)

    # Exchange fallback wall-clock values. XNYS calendar remains authoritative.
    premarket_start: time = env_time("OPPW_PREMARKET_START", time(0, 0))
    cash_open: time = env_time("OPPW_CASH_OPEN", time(9, 30))
    close_bar_open: time = env_time("OPPW_CLOSE_BAR_OPEN", time(16, 0))
    close_processing: time = env_time("OPPW_CLOSE_PROCESSING", time(16, 1))

    # Runtime state and coordination
    state_file: Path = Path(os.getenv("OPPW_STATE_FILE", str(BASE_DIR / "oppw_mt5_state.json")))
    log_dir: Path = Path(os.getenv("OPPW_LOG_DIR", str(BASE_DIR / "log")))
    lock_file: Path = Path(os.getenv("OPPW_LOCK_FILE", str(BASE_DIR / "oppw_mt5.lock")))
    publisher_heartbeat_interval_seconds: float = env_float("OPPW_PUBLISHER_HEARTBEAT_INTERVAL_SECONDS", 1.0)
    publisher_heartbeat_stale_seconds: float = env_float("OPPW_PUBLISHER_HEARTBEAT_STALE_SECONDS", 8.0)
    publisher_presence_check_interval_seconds: float = env_float("OPPW_PUBLISHER_PRESENCE_CHECK_INTERVAL_SECONDS", 0.5)
    account_funding_check_interval_seconds: float = env_float("OPPW_ACCOUNT_FUNDING_CHECK_INTERVAL_SECONDS", 5.0)
    mysql_trade_refresh_seconds: float = env_float("OPPW_MYSQL_TRADE_REFRESH_SECONDS", 60.0)
    mysql_trade_error_log_interval_seconds: float = env_float("OPPW_MYSQL_TRADE_ERROR_LOG_INTERVAL_SECONDS", 60.0)
    leverage_inputs_refresh_seconds: float = env_float("OPPW_LEVERAGE_INPUTS_REFRESH_SECONDS", 60.0)
    event_spool_lock_timeout_seconds: float = env_float("OPPW_EVENT_SPOOL_LOCK_TIMEOUT_SECONDS", 5.0)
    event_spool_lock_retry_seconds: float = env_float("OPPW_EVENT_SPOOL_LOCK_RETRY_SECONDS", 0.02)

    # Backend publisher
    monitor_enabled: bool = env_bool("OPPW_MONITOR_ENABLED", True)
    monitor_ingest_url: str = os.getenv("OPPW_MONITOR_INGEST_URL", "https://eloski.eu/oppw-backend/ingest.php")
    monitor_write_token: str = os.getenv("OPPW_MONITOR_WRITE_TOKEN", MONITOR_WRITE_TOKEN)
    monitor_account_key: str = os.getenv("OPPW_MONITOR_ACCOUNT_KEY", "REAL")
    monitor_publish_interval_seconds: float = env_float("OPPW_MONITOR_PUBLISH_INTERVAL_SECONDS", 5.0)
    monitor_timeout_seconds: float = env_float("OPPW_MONITOR_TIMEOUT_SECONDS", 10.0)
    monitor_error_log_interval_seconds: float = env_float("OPPW_MONITOR_ERROR_LOG_INTERVAL_SECONDS", 30.0)
    monitor_equity_sample_seconds: float = env_float("OPPW_MONITOR_EQUITY_SAMPLE_SECONDS", 60.0)
    monitor_equity_history_points: int = env_int("OPPW_MONITOR_EQUITY_HISTORY_POINTS", 10080)
    monitor_event_buffer_size: int = env_int("OPPW_MONITOR_EVENT_BUFFER_SIZE", 5000)
    monitor_minute_snapshot_buffer_size: int = env_int("OPPW_MONITOR_MINUTE_SNAPSHOT_BUFFER_SIZE", 720)
    monitor_history_file: Path = Path(os.getenv("OPPW_MONITOR_HISTORY_FILE", str(BASE_DIR / "oppw_monitor_equity_history.json")))
    backend_latest_trade_path: str = os.getenv("OPPW_BACKEND_LATEST_TRADE_PATH", "oppw_latest_trade.php")

    @property
    def tpps(self) -> tuple[float, float, float, float, float]:
        return (self.tpp_monday, self.tpp_tuesday, self.tpp_wednesday, self.tpp_thursday, self.tpp_friday)

    @property
    def tsl_ratio(self) -> float:
        return 1.0 - self.tsl_stop
