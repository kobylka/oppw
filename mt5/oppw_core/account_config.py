"""Canonical configuration construction and private account overrides."""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
import uuid
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from datetime import time
from pathlib import Path
from typing import Any

from .settings import Config
from .versioning import (
    ACCOUNT_CONFIG_FILES,
    ACCOUNT_DEMO,
    ACCOUNT_TYPES,
    BASE_DIR,
    PROJECT_VERSION,
)


PRIVATE_CONSTANT_FIELDS = {
    "MT5_TERMINAL_PATH": "terminal_path",
    "MT5_LOGIN": "login",
    "MT5_PASSWORD": "password",
    "MT5_SERVER": "server",
    "MONITOR_WRITE_TOKEN": "monitor_write_token",
}

ENVIRONMENT_VARIABLES = {
    "config_name": "OPPW_CONFIG_NAME",
    "trade_symbol": "OPPW_TRADE_SYMBOL",
    "signal_symbol": "OPPW_SIGNAL_SYMBOL",
    "timezone_name": "OPPW_TIMEZONE",
    "market_timezone_name": "OPPW_MARKET_TIMEZONE",
    "exchange_calendar": "OPPW_EXCHANGE_CALENDAR",
    "terminal_path": "OPPW_TERMINAL_PATH",
    "login": "OPPW_LOGIN",
    "password": "OPPW_PASSWORD",
    "server": "OPPW_SERVER",
    "magic": "OPPW_MAGIC",
    "comment_prefix": "OPPW_COMMENT",
    "deviation_points": "OPPW_DEVIATION",
    "filling_mode": "OPPW_FILLING_MODE",
    "poll_seconds": "OPPW_POLL_SECONDS",
    "entry_window_seconds": "OPPW_ENTRY_WINDOW_SECONDS",
    "reconnect_seconds": "OPPW_RECONNECT_SECONDS",
    "maximum_tick_age_seconds": "OPPW_MAX_TICK_AGE_SECONDS",
    "request_retry_seconds": "OPPW_REQUEST_RETRY_SECONDS",
    "mt5_initialize_timeout_seconds": "OPPW_MT5_INITIALIZE_TIMEOUT_SECONDS",
    "market_order_priority_delay_seconds": "OPPW_MARKET_ORDER_PRIORITY_DELAY_SECONDS",
    "separate_mt5_login_after_initialize": "OPPW_SEPARATE_MT5_LOGIN_AFTER_INITIALIZE",
    "entry_action_lead_seconds": "OPPW_ENTRY_ACTION_LEAD_SECONDS",
    "non_entry_action_lead_seconds": "OPPW_NON_ENTRY_ACTION_LEAD_SECONDS",
    "base_leverage": "OPPW_BASE_LEVERAGE",
    "loss_leverage": "OPPW_LOSS_LEVERAGE",
    "full_week_loss_trigger": "OPPW_FULL_WEEK_LOSS_TRIGGER",
    "previous_trade_loss_trigger": "OPPW_PREVIOUS_TRADE_LOSS_TRIGGER",
    "entry_rule_arithmetic_threshold": "OPPW_ENTRY_RULE_ARITHMETIC_THRESHOLD",
    "entry_rule_gap_threshold": "OPPW_ENTRY_RULE_GAP_THRESHOLD",
    "entry_rule_momentum20_threshold": "OPPW_ENTRY_RULE_MOMENTUM20_THRESHOLD",
    "entry_rule_tuesday_normalization_tolerance": "OPPW_ENTRY_RULE_TUESDAY_NORMALIZATION_TOLERANCE",
    "entry_rule_premarket_minimum_range": "OPPW_ENTRY_RULE_PREMARKET_MINIMUM_RANGE",
    "entry_rule_premarket_maximum_close_location": "OPPW_ENTRY_RULE_PREMARKET_MAXIMUM_CLOSE_LOCATION",
    "break_even_ratio": "OPPW_BE",
    "tsl_stop": "OPPW_TSL_STOP",
    "leverage_stop_points": "OPPW_LEVERAGE_STOP_POINTS",
    "hard_stop_ratio_override": "OPPW_HARD_STOP_RATIO_OVERRIDE",
    "tpp_monday": "OPPW_TPP_MONDAY",
    "tpp_tuesday": "OPPW_TPP_TUESDAY",
    "tpp_wednesday": "OPPW_TPP_WEDNESDAY",
    "tpp_thursday": "OPPW_TPP_THURSDAY",
    "tpp_friday": "OPPW_TPP_FRIDAY",
    "sizing_multiplier": "OPPW_SIZING_MULTIPLIER",
    "required_balance_multiplier": "OPPW_REQUIRED_BALANCE_MULTIPLIER",
    "legacy_required_balance_multiplier_l10": "OPPW_LEGACY_REQUIRED_BALANCE_MULTIPLIER_L10",
    "legacy_required_balance_multiplier_l8": "OPPW_LEGACY_REQUIRED_BALANCE_MULTIPLIER_L8",
    "max_account_stop_loss_fraction": "OPPW_MAX_ACCOUNT_STOP_LOSS_FRACTION",
    "broker_margin_leverage_fallback": "OPPW_BROKER_MARGIN_LEVERAGE_FALLBACK",
    "manage_manual_position": "OPPW_MANAGE_MANUAL_POSITION",
    "live_enabled": "OPPW_LIVE",
    "autotrading_reminder_seconds": "OPPW_AUTOTRADING_REMINDER_SECONDS",
    "stale_tick_reminder_seconds": "OPPW_STALE_TICK_REMINDER_SECONDS",
    "premarket_start": "OPPW_PREMARKET_START",
    "cash_open": "OPPW_CASH_OPEN",
    "close_bar_open": "OPPW_CLOSE_BAR_OPEN",
    "close_processing": "OPPW_CLOSE_PROCESSING",
    "state_file": "OPPW_STATE_FILE",
    "log_dir": "OPPW_LOG_DIR",
    "account_funding_check_interval_seconds": "OPPW_ACCOUNT_FUNDING_CHECK_INTERVAL_SECONDS",
    "mysql_trade_refresh_seconds": "OPPW_MYSQL_TRADE_REFRESH_SECONDS",
    "mysql_trade_error_log_interval_seconds": "OPPW_MYSQL_TRADE_ERROR_LOG_INTERVAL_SECONDS",
    "leverage_inputs_refresh_seconds": "OPPW_LEVERAGE_INPUTS_REFRESH_SECONDS",
    "coordination_url": "OPPW_COORDINATION_URL",
    "events_ingest_url": "OPPW_EVENTS_INGEST_URL",
    "coordination_timeout_seconds": "OPPW_COORDINATION_TIMEOUT_SECONDS",
    "role_lease_ttl_seconds": "OPPW_ROLE_LEASE_TTL_SECONDS",
    "role_lease_heartbeat_seconds": "OPPW_ROLE_LEASE_HEARTBEAT_SECONDS",
    "role_lease_safety_margin_seconds": "OPPW_ROLE_LEASE_SAFETY_MARGIN_SECONDS",
    "publisher_presence_check_interval_seconds": "OPPW_PUBLISHER_PRESENCE_CHECK_INTERVAL_SECONDS",
    "trade_gate_ttl_seconds": "OPPW_TRADE_GATE_TTL_SECONDS",
    "trade_gate_max_hold_seconds": "OPPW_TRADE_GATE_MAX_HOLD_SECONDS",
    "monitor_enabled": "OPPW_MONITOR_ENABLED",
    "monitor_ingest_url": "OPPW_MONITOR_INGEST_URL",
    "monitor_write_token": "OPPW_MONITOR_WRITE_TOKEN",
    "monitor_account_key": "OPPW_MONITOR_ACCOUNT_KEY",
    "monitor_publish_interval_seconds": "OPPW_MONITOR_PUBLISH_INTERVAL_SECONDS",
    "monitor_timeout_seconds": "OPPW_MONITOR_TIMEOUT_SECONDS",
    "monitor_error_log_interval_seconds": "OPPW_MONITOR_ERROR_LOG_INTERVAL_SECONDS",
    "monitor_equity_sample_seconds": "OPPW_MONITOR_EQUITY_SAMPLE_SECONDS",
    "monitor_equity_history_points": "OPPW_MONITOR_EQUITY_HISTORY_POINTS",
    "monitor_event_buffer_size": "OPPW_MONITOR_EVENT_BUFFER_SIZE",
    "monitor_minute_snapshot_buffer_size": "OPPW_MONITOR_MINUTE_SNAPSHOT_BUFFER_SIZE",
    "monitor_history_file": "OPPW_MONITOR_HISTORY_FILE",
    "backend_latest_trade_path": "OPPW_BACKEND_LATEST_TRADE_PATH",
    "backend_strategy_controls_path": "OPPW_BACKEND_STRATEGY_CONTROLS_PATH",
}
# use_legacy_balance_multiplier remains an explicit CLI-only runtime choice.

CONFIG_FIELD_NAMES = tuple(field.name for field in fields(Config))
REQUIRED_CONFIG_FIELDS = CONFIG_FIELD_NAMES + ("tpps", "tsl_ratio")
SENSITIVE_CONFIG_FIELDS = frozenset({"password", "monitor_write_token"})
ACCOUNT_KEY_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,63}$")


def normalize_account_type(account_type: str) -> str:
    normalized = str(account_type).strip().upper()
    if normalized not in ACCOUNT_TYPES:
        raise RuntimeError("Account type must be DEMO or REAL")
    return normalized


def normalize_account_key(account_key: str) -> str:
    normalized = str(account_key).strip().upper()
    if not ACCOUNT_KEY_PATTERN.fullmatch(normalized):
        raise RuntimeError(
            "Account key must contain 1-64 uppercase letters, digits, underscores, or hyphens"
        )
    return normalized


def account_config_path(account_type: str, account_key: str, base_dir: Path = BASE_DIR) -> Path:
    normalized_type = normalize_account_type(account_type)
    normalized_key = normalize_account_key(account_key)
    if normalized_key in ACCOUNT_TYPES and normalized_key != normalized_type:
        raise RuntimeError(f"Reserved account key {normalized_key} must use type {normalized_key}")
    account_dir = base_dir / normalized_type.lower()
    filename = (
        ACCOUNT_CONFIG_FILES[normalized_type]
        if normalized_key == normalized_type
        else f"{normalized_key.lower()}_mt5_config.py"
    )
    return account_dir / filename


def default_config(account: str, account_dir: Path) -> Config:
    account = account.upper()
    return replace(
        Config(),
        config_name=account,
        monitor_account_key=account,
        state_file=account_dir / "oppw_mt5_state.json",
        log_dir=account_dir / "log",
        monitor_history_file=account_dir / "oppw_monitor_equity_history.json",
    )


def coerce_config_value(field_name: str, value: Any, current: Any) -> Any:
    try:
        if isinstance(current, bool):
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {"1", "true", "yes", "on"}
        if isinstance(current, Path):
            return Path(value)
        if isinstance(current, time):
            return value if isinstance(value, time) else time.fromisoformat(str(value).strip())
        if isinstance(current, int):
            return int(value)
        if isinstance(current, float):
            return float(value)
        if isinstance(current, str):
            return str(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"Invalid value for configuration field {field_name}: {value!r}") from exc
    raise RuntimeError(f"Unsupported configuration field type for {field_name}: {type(current).__name__}")


def apply_config_overrides(config: Config, overrides: Mapping[str, Any], source: str) -> Config:
    unknown = sorted(set(overrides) - set(CONFIG_FIELD_NAMES))
    if unknown:
        raise RuntimeError(f"Unknown configuration fields in {source}: {', '.join(unknown)}")
    converted = {
        name: coerce_config_value(name, value, getattr(config, name))
        for name, value in overrides.items()
    }
    return replace(config, **converted)


def environment_config_overrides(config: Config, environ: Mapping[str, str]) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    for field_name, environment_name in ENVIRONMENT_VARIABLES.items():
        if environment_name not in environ:
            continue
        raw = environ[environment_name]
        current = getattr(config, field_name)
        if raw == "" and isinstance(current, (int, float, time)) and not isinstance(current, bool):
            continue
        overrides[field_name] = raw
    return overrides


def load_private_overrides(config_path: Path) -> dict[str, Any]:
    module_name = f"oppw_mt5_private_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load configuration file: {config_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)

    if hasattr(module, "Config"):
        raise RuntimeError(
            f"Private configuration still defines Config: {config_path}. "
            "Run tools/migrate_mt5_config.py before starting OPPW."
        )
    raw_overrides = getattr(module, "OVERRIDES", {})
    if not isinstance(raw_overrides, Mapping):
        raise RuntimeError(f"OVERRIDES must be a mapping in {config_path}")
    overrides = dict(raw_overrides)
    for constant_name, field_name in PRIVATE_CONSTANT_FIELDS.items():
        if not hasattr(module, constant_name):
            raise RuntimeError(f"Private configuration is missing {constant_name}: {config_path}")
        if field_name in overrides:
            raise RuntimeError(
                f"Private configuration sets {field_name} both through {constant_name} and OVERRIDES: {config_path}"
            )
        overrides[field_name] = getattr(module, constant_name)
    unknown = sorted(set(overrides) - set(CONFIG_FIELD_NAMES))
    if unknown:
        raise RuntimeError(f"Unknown private configuration fields in {config_path}: {', '.join(unknown)}")
    return overrides


def build_account_config(
    account: str,
    account_dir: Path,
    private_overrides: Mapping[str, Any],
    environ: Mapping[str, str] | None = None,
) -> Config:
    config = default_config(account, account_dir)
    config = apply_config_overrides(config, private_overrides, "private account configuration")
    environment = os.environ if environ is None else environ
    environment_overrides = environment_config_overrides(config, environment)
    return apply_config_overrides(config, environment_overrides, "environment")


def load_account_config(account_type: str, account_key: str | None = None):
    normalized_type = normalize_account_type(account_type)
    normalized_key = normalize_account_key(account_key or normalized_type)
    account_dir = BASE_DIR / normalized_type.lower()
    config_path = account_config_path(normalized_type, normalized_key)
    if not config_path.is_file():
        raise RuntimeError(
            f"Missing {normalized_type} account configuration for {normalized_key}: {config_path}"
        )
    private_overrides = load_private_overrides(config_path)
    return build_account_config(normalized_key, account_dir, private_overrides), config_path


def effective_config_summary(config: Config) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for field in fields(config):
        if field.name in SENSITIVE_CONFIG_FIELDS:
            continue
        value = getattr(config, field.name)
        if isinstance(value, (Path, time)):
            value = str(value)
        summary[field.name] = value
    return summary


def validate_config(config) -> None:
    missing = [name for name in REQUIRED_CONFIG_FIELDS if not hasattr(config, name)]
    if missing:
        raise RuntimeError(
            "Selected account config is incompatible with OPPW " + PROJECT_VERSION + ". Missing fields: "
            + ", ".join(missing)
        )
    if not is_dataclass(config) or not isinstance(config, Config):
        raise RuntimeError("Config must use the canonical frozen oppw_core.settings.Config dataclass")
    if float(config.required_balance_multiplier) <= 0:
        raise RuntimeError("required_balance_multiplier must be positive")
    if float(config.legacy_required_balance_multiplier_l10) <= 0 or float(config.legacy_required_balance_multiplier_l8) <= 0:
        raise RuntimeError("legacy required-balance multipliers must be positive")
    if not 0 < float(config.max_account_stop_loss_fraction) <= 1:
        raise RuntimeError("max_account_stop_loss_fraction must be in (0, 1]")
    hard_stop_override = float(config.hard_stop_ratio_override)
    if hard_stop_override != 0.0 and not 0 < hard_stop_override < 1:
        raise RuntimeError("hard_stop_ratio_override must be 0 or in (0, 1)")
    for field_name in (
        "entry_rule_arithmetic_threshold",
        "entry_rule_gap_threshold",
        "entry_rule_tuesday_normalization_tolerance",
        "entry_rule_premarket_minimum_range",
    ):
        if float(getattr(config, field_name)) <= 0:
            raise RuntimeError(f"{field_name} must be positive")
    if float(config.entry_rule_momentum20_threshold) >= 0:
        raise RuntimeError("entry_rule_momentum20_threshold must be negative")
    if not 0 < float(config.entry_rule_premarket_maximum_close_location) <= 1:
        raise RuntimeError("entry_rule_premarket_maximum_close_location must be in (0, 1]")
    for field_name in ("coordination_url", "events_ingest_url", "monitor_ingest_url"):
        value = str(getattr(config, field_name)).strip().lower()
        if not value.startswith("https://"):
            raise RuntimeError(f"{field_name} must use HTTPS")
    lease_ttl = float(config.role_lease_ttl_seconds)
    heartbeat = float(config.role_lease_heartbeat_seconds)
    safety_margin = float(config.role_lease_safety_margin_seconds)
    if heartbeat <= 0 or safety_margin < 0 or lease_ttl <= heartbeat + safety_margin:
        raise RuntimeError(
            "role_lease_ttl_seconds must exceed role_lease_heartbeat_seconds "
            "+ role_lease_safety_margin_seconds"
        )
    if float(config.trade_gate_ttl_seconds) <= 0:
        raise RuntimeError("trade_gate_ttl_seconds must be positive")
    if not 1 <= float(config.high_risk_warning_timeout_seconds) <= 180:
        raise RuntimeError("high_risk_warning_timeout_seconds must be between 1 and 180")
    if not 5 <= float(config.mt5_initialize_timeout_seconds) <= 140:
        raise RuntimeError("mt5_initialize_timeout_seconds must be between 5 and 140")
    if not 0 <= float(config.market_order_priority_delay_seconds) <= 5:
        raise RuntimeError("market_order_priority_delay_seconds must be between 0 and 5")
    if not 0 < float(config.trade_gate_max_hold_seconds) < float(config.trade_gate_ttl_seconds):
        raise RuntimeError("trade_gate_max_hold_seconds must be positive and less than trade_gate_ttl_seconds")


def apply_runtime_flags(config, conservative_multiplier: bool):
    return replace(config, use_legacy_balance_multiplier=bool(conservative_multiplier))


def account_scoped_file(path: Path, account: str) -> Path:
    account_label = account.lower()
    normalized_stem = re.sub(r"[^a-z0-9]+", "-", path.stem.lower()).strip("-")
    normalized_label = re.sub(r"[^a-z0-9]+", "-", account_label).strip("-")
    if normalized_stem == normalized_label or normalized_stem.endswith("-" + normalized_label):
        return path
    return path.with_name(f"{path.stem}.{account_label}{path.suffix}")


def account_scoped_dir(path: Path, account: str) -> Path:
    return path if path.name.lower() == account.lower() else path / account.lower()


def scope_config_to_account(config, account: str):
    changes: dict[str, Any] = {
        "state_file": account_scoped_file(Path(config.state_file), account),
        "monitor_history_file": account_scoped_file(Path(config.monitor_history_file), account),
        "log_dir": account_scoped_dir(Path(config.log_dir), account),
        "monitor_account_key": account.upper(),
    }
    return replace(config, **changes)


def migrate_legacy_demo_runtime_files(original, scoped, account: str) -> None:
    if account != ACCOUNT_DEMO:
        return
    for name in ("state_file", "monitor_history_file"):
        source = Path(getattr(original, name))
        target = Path(getattr(scoped, name))
        if source == target or not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
