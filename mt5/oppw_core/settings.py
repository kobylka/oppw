"""Canonical MT5 configuration schema and defaults.

Private account files contain credentials and explicit overrides only. They do
not define application configuration classes or duplicate these defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path


@dataclass(frozen=True)
class Config:
    # Identity and symbols
    config_name: str = "DEMO"
    trade_symbol: str = "US100"
    signal_symbol: str = "US100"
    timezone_name: str = "Europe/Warsaw"
    market_timezone_name: str = "America/New_York"
    exchange_calendar: str = "XNYS"

    # MT5 connection
    terminal_path: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    login: int = 0
    password: str = ""
    server: str = ""

    # Order execution
    magic: int = 240024
    comment_prefix: str = "OPPW24"
    deviation_points: int = 20
    filling_mode: str = "AUTO"
    poll_seconds: float = 0.20
    entry_window_seconds: int = 55
    reconnect_seconds: float = 3.0
    maximum_tick_age_seconds: float = 10.0
    request_retry_seconds: float = 1.0
    mt5_initialize_timeout_seconds: float = 60.0
    separate_mt5_login_after_initialize: bool = False
    auto_acknowledge_high_risk_warning: bool = False
    high_risk_warning_timeout_seconds: float = 90.0
    market_order_priority_delay_seconds: float = 0.0

    # Independent execution clocks
    entry_action_lead_seconds: float = 3.0
    non_entry_action_lead_seconds: float = 3.0

    # Strategy and leverage selection
    base_leverage: int = 8
    loss_leverage: int = 10
    full_week_loss_trigger: float = -0.025
    previous_trade_loss_trigger: float = -0.007
    entry_rule_arithmetic_threshold: float = 0.02
    entry_rule_gap_threshold: float = 0.01
    entry_rule_momentum20_threshold: float = -0.005
    entry_rule_tuesday_normalization_tolerance: float = 0.005
    entry_rule_premarket_minimum_range: float = 0.008
    entry_rule_premarket_maximum_close_location: float = 0.15
    break_even_ratio: float = 0.996
    tsl_stop: float = 0.004
    leverage_stop_points: float = 50.0

    # OH/CH targets by actual trading-session index
    tpp_monday: float = 0.007
    tpp_tuesday: float = 0.020
    tpp_wednesday: float = 0.050
    tpp_thursday: float = 0.050
    tpp_friday: float = 0.050

    # Broker exposure and required-balance sizing
    sizing_multiplier: float = 20.0
    required_balance_multiplier: float = 1.765
    legacy_required_balance_multiplier_l10: float = 2.0
    legacy_required_balance_multiplier_l8: float = 2.5
    use_legacy_balance_multiplier: bool = False
    max_account_stop_loss_fraction: float = 0.50
    broker_margin_leverage_fallback: float = 20.0

    # Role and safety
    manage_manual_position: bool = True
    live_enabled: bool = False
    autotrading_reminder_seconds: float = 60.0
    stale_tick_reminder_seconds: float = 60.0

    # Exchange fallback wall-clock values. XNYS remains authoritative.
    premarket_start: time = time(0, 0)
    cash_open: time = time(9, 30)
    close_bar_open: time = time(16, 0)
    close_processing: time = time(16, 1)

    # Runtime state; account-specific roots are supplied by the loader.
    state_file: Path = Path("oppw_mt5_state.json")
    log_dir: Path = Path("log")
    account_funding_check_interval_seconds: float = 5.0
    mysql_trade_refresh_seconds: float = 60.0
    mysql_trade_error_log_interval_seconds: float = 60.0
    leverage_inputs_refresh_seconds: float = 60.0

    # Global MySQL-backed coordination
    coordination_url: str = "https://eloski.eu/oppw-backend/coordination.php"
    events_ingest_url: str = "https://eloski.eu/oppw-backend/events-ingest.php"
    coordination_timeout_seconds: float = 5.0
    role_lease_ttl_seconds: float = 30.0
    role_lease_heartbeat_seconds: float = 3.0
    role_lease_safety_margin_seconds: float = 5.0
    publisher_presence_check_interval_seconds: float = 1.0
    trade_gate_ttl_seconds: float = 10.0
    trade_gate_max_hold_seconds: float = 5.0

    # Backend publishing
    monitor_enabled: bool = True
    monitor_ingest_url: str = "https://eloski.eu/oppw-backend/ingest.php"
    monitor_write_token: str = ""
    monitor_account_key: str = "DEMO"
    monitor_publish_interval_seconds: float = 5.0
    monitor_timeout_seconds: float = 10.0
    monitor_error_log_interval_seconds: float = 30.0
    monitor_equity_sample_seconds: float = 60.0
    monitor_equity_history_points: int = 10080
    monitor_event_buffer_size: int = 5000
    monitor_minute_snapshot_buffer_size: int = 720
    monitor_history_file: Path = Path("oppw_monitor_equity_history.json")
    backend_latest_trade_path: str = "oppw_latest_trade.php"
    backend_strategy_controls_path: str = "strategy-controls.php"

    @property
    def tpps(self) -> tuple[float, float, float, float, float]:
        return (
            self.tpp_monday,
            self.tpp_tuesday,
            self.tpp_wednesday,
            self.tpp_thursday,
            self.tpp_friday,
        )

    @property
    def tsl_ratio(self) -> float:
        return 1.0 - self.tsl_stop
