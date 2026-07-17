"""Persistent configuration for oppw_mt5_continuous.py.

Edit the MT5 connection values in the "EDIT THESE VALUES ONCE" section.
Keep this file when replacing the main strategy script with a newer version.
Environment variables still override values stored here when they are set.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


# -----------------------------------------------------------------------------
# EDIT THESE VALUES ONCE
# -----------------------------------------------------------------------------

MT5_TERMINAL_PATH = r"C:\\Program Files\\MetaTrader 5\\terminal64.exe"
MT5_LOGIN = 0
MT5_PASSWORD = ""
MT5_SERVER = "BOSSAFX-Demo"

TRADE_SYMBOL = "US100"
SIGNAL_SYMBOL = "US100"
LIVE_ENABLED = True

# Read-only mobile monitor publishing. The Android app reads from the API;
# this MT5 process only sends snapshots and events to the write endpoint.
MONITOR_ENABLED = False
MONITOR_INGEST_URL = ""
MONITOR_WRITE_TOKEN = ""
MONITOR_ACCOUNT_KEY = "DEMO"


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or not value.strip() else int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or not value.strip() else float(value)


@dataclass(frozen=True)
class Config:
    trade_symbol: str = os.getenv("OPPW_TRADE_SYMBOL", TRADE_SYMBOL)
    signal_symbol: str = os.getenv("OPPW_SIGNAL_SYMBOL", SIGNAL_SYMBOL)
    timezone_name: str = os.getenv("OPPW_TIMEZONE", "Europe/Warsaw")
    market_timezone_name: str = os.getenv("OPPW_MARKET_TIMEZONE", "America/New_York")
    exchange_calendar: str = os.getenv("OPPW_EXCHANGE_CALENDAR", "XNYS")

    terminal_path: str = os.getenv("OPPW_TERMINAL_PATH", MT5_TERMINAL_PATH)
    login: int = env_int("OPPW_LOGIN", MT5_LOGIN)
    password: str = os.getenv("OPPW_PASSWORD", MT5_PASSWORD)
    server: str = os.getenv("OPPW_SERVER", MT5_SERVER)

    magic: int = env_int("OPPW_MAGIC", 240024)
    comment_prefix: str = os.getenv("OPPW_COMMENT", "OPPW24")
    deviation_points: int = env_int("OPPW_DEVIATION", 20)
    poll_seconds: float = env_float("OPPW_POLL_SECONDS", 0.20)
    entry_window_seconds: int = env_int("OPPW_ENTRY_WINDOW_SECONDS", 55)
    reconnect_seconds: float = env_float("OPPW_RECONNECT_SECONDS", 3.0)
    maximum_tick_age_seconds: float = env_float("OPPW_MAX_TICK_AGE_SECONDS", 10.0)
    request_retry_seconds: float = env_float("OPPW_REQUEST_RETRY_SECONDS", 1.0)

    base_leverage: int = env_int("OPPW_BASE_LEVERAGE", 8)
    loss_leverage: int = env_int("OPPW_LOSS_LEVERAGE", 10)
    break_even_ratio: float = env_float("OPPW_BE", 0.996)
    tsl_stop: float = env_float("OPPW_TSL_STOP", 0.004)
    leverage_stop_points: float = env_float("OPPW_LEVERAGE_STOP_POINTS", 50.0)

    tpp_monday: float = env_float("OPPW_TPP_MONDAY", 0.007)
    tpp_tuesday: float = env_float("OPPW_TPP_TUESDAY", 0.020)
    tpp_wednesday: float = env_float("OPPW_TPP_WEDNESDAY", 0.050)
    tpp_thursday: float = env_float("OPPW_TPP_THURSDAY", 0.050)
    tpp_friday: float = env_float("OPPW_TPP_FRIDAY", 0.050)

    sizing_multiplier: float = env_float("OPPW_SIZING_MULTIPLIER", 20.0)

    manage_manual_position: bool = env_bool("OPPW_MANAGE_MANUAL_POSITION", True)
    live_enabled: bool = env_bool("OPPW_LIVE", LIVE_ENABLED)

    monitor_enabled: bool = env_bool("OPPW_MONITOR_ENABLED", MONITOR_ENABLED)
    monitor_ingest_url: str = os.getenv("OPPW_MONITOR_INGEST_URL", MONITOR_INGEST_URL).strip()
    monitor_write_token: str = os.getenv("OPPW_MONITOR_WRITE_TOKEN", MONITOR_WRITE_TOKEN).strip()
    monitor_account_key: str = os.getenv("OPPW_MONITOR_ACCOUNT_KEY", MONITOR_ACCOUNT_KEY).strip()
    monitor_publish_interval_seconds: float = env_float("OPPW_MONITOR_PUBLISH_INTERVAL_SECONDS", 5.0)
    monitor_timeout_seconds: float = env_float("OPPW_MONITOR_TIMEOUT_SECONDS", 4.0)
    monitor_error_log_interval_seconds: float = env_float("OPPW_MONITOR_ERROR_LOG_INTERVAL_SECONDS", 60.0)
    monitor_event_buffer_size: int = env_int("OPPW_MONITOR_EVENT_BUFFER_SIZE", 500)
    monitor_minute_snapshot_buffer_size: int = env_int("OPPW_MONITOR_MINUTE_SNAPSHOT_BUFFER_SIZE", 180)
    monitor_equity_history_points: int = env_int("OPPW_MONITOR_EQUITY_HISTORY_POINTS", 180)
    monitor_equity_sample_seconds: float = env_float("OPPW_MONITOR_EQUITY_SAMPLE_SECONDS", 60.0)

    state_file: Path = Path(os.getenv("OPPW_STATE_FILE", str(BASE_DIR / "oppw_mt5_state.json")))
    log_dir: Path = Path(os.getenv("OPPW_LOG_DIR", str(BASE_DIR / "log")))
    lock_file: Path = Path(os.getenv("OPPW_LOCK_FILE", str(BASE_DIR / "oppw_mt5.lock")))
    monitor_history_file: Path = Path(os.getenv("OPPW_MONITOR_HISTORY_FILE", str(BASE_DIR / "oppw_monitor_equity.json")))

    premarket_start: time = time(0, 0)

    # New York exchange wall-clock times. The strategy converts them to Warsaw
    # for each session, so US/EU daylight-saving mismatch weeks are handled.
    cash_open: time = time(9, 30)
    weekly_close_time: time = time(15, 59, 55)
    close_bar_open: time = time(16, 0)
    close_processing: time = time(16, 1)

    @property
    def tpps(self) -> tuple[float, float, float, float, float]:
        return (self.tpp_monday, self.tpp_tuesday, self.tpp_wednesday, self.tpp_thursday, self.tpp_friday)

    @property
    def tsl_ratio(self) -> float:
        return 1.0 - self.tsl_stop