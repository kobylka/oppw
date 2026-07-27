"""Account configuration loading, validation, and runtime path scoping."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import uuid
from dataclasses import is_dataclass, replace
from pathlib import Path
from typing import Any

from .versioning import (
    ACCOUNT_CONFIG_FILES,
    ACCOUNT_DEMO,
    BASE_DIR,
    PROJECT_VERSION,
)

REQUIRED_CONFIG_FIELDS = (
    "trade_symbol", "signal_symbol", "timezone_name", "market_timezone_name", "exchange_calendar",
    "terminal_path", "login", "password", "server", "magic", "comment_prefix", "deviation_points",
    "poll_seconds", "entry_window_seconds", "reconnect_seconds", "maximum_tick_age_seconds",
    "request_retry_seconds", "filling_mode", "base_leverage", "loss_leverage",
    "full_week_loss_trigger", "previous_trade_loss_trigger", "break_even_ratio", "tsl_stop",
    "leverage_stop_points", "sizing_multiplier", "required_balance_multiplier",
    "legacy_required_balance_multiplier_l10", "legacy_required_balance_multiplier_l8",
    "max_account_stop_loss_fraction", "broker_margin_leverage_fallback", "manage_manual_position",
    "live_enabled", "state_file", "log_dir", "premarket_start", "cash_open",
    "close_bar_open", "close_processing", "entry_action_lead_seconds", "non_entry_action_lead_seconds",
    "autotrading_reminder_seconds", "stale_tick_reminder_seconds",
    "coordination_url", "events_ingest_url", "coordination_timeout_seconds",
    "role_lease_ttl_seconds", "role_lease_heartbeat_seconds", "role_lease_safety_margin_seconds",
    "publisher_presence_check_interval_seconds", "trade_gate_ttl_seconds", "trade_gate_max_hold_seconds",
    "account_funding_check_interval_seconds", "mysql_trade_refresh_seconds",
    "mysql_trade_error_log_interval_seconds", "leverage_inputs_refresh_seconds",
    "monitor_enabled",
    "monitor_ingest_url", "monitor_write_token", "monitor_account_key", "monitor_publish_interval_seconds",
    "monitor_timeout_seconds", "monitor_error_log_interval_seconds", "monitor_equity_sample_seconds",
    "monitor_equity_history_points", "monitor_event_buffer_size", "monitor_minute_snapshot_buffer_size",
    "monitor_history_file", "backend_latest_trade_path", "tpps", "tsl_ratio",
)


def load_account_config(account: str):
    account = account.upper()
    account_dir = BASE_DIR / account.lower()
    config_path = account_dir / ACCOUNT_CONFIG_FILES[account]
    if not config_path.is_file():
        raise RuntimeError(f"Missing {account} configuration: {config_path}")

    module_name = f"oppw_mt5_config_{account.lower()}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load configuration file: {config_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    config_class = getattr(module, "Config", None)
    if config_class is None or not callable(config_class):
        raise RuntimeError(f"Configuration file does not define Config: {config_path}")
    return config_class(), config_path


def validate_config(config) -> None:
    missing = [name for name in REQUIRED_CONFIG_FIELDS if not hasattr(config, name)]
    if missing:
        raise RuntimeError(
            "Selected account config is incompatible with OPPW " + PROJECT_VERSION + ". Missing fields: "
            + ", ".join(missing) + ". Merge the canonical config template and restore only local credential values."
        )
    if not is_dataclass(config):
        raise RuntimeError("Config must be a frozen dataclass")
    if float(config.required_balance_multiplier) <= 0:
        raise RuntimeError("required_balance_multiplier must be positive")
    if float(config.legacy_required_balance_multiplier_l10) <= 0 or float(config.legacy_required_balance_multiplier_l8) <= 0:
        raise RuntimeError("legacy required-balance multipliers must be positive")
    if not 0 < float(config.max_account_stop_loss_fraction) <= 1:
        raise RuntimeError("max_account_stop_loss_fraction must be in (0, 1]")
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
    if not 0 < float(config.trade_gate_max_hold_seconds) < float(config.trade_gate_ttl_seconds):
        raise RuntimeError("trade_gate_max_hold_seconds must be positive and less than trade_gate_ttl_seconds")


def apply_runtime_flags(config, conservative_multiplier: bool):
    # Keep the established config field names for backward-compatible private
    # account configs; only the operator-facing CLI/profile terminology changes.
    return replace(config, use_legacy_balance_multiplier=bool(conservative_multiplier))


def account_scoped_file(path: Path, account: str) -> Path:
    account_label = account.lower()
    normalized_tokens = path.stem.lower().replace("_", "-").replace(".", "-").split("-")
    if account_label in normalized_tokens:
        return path
    return path.with_name(f"{path.stem}.{account_label}{path.suffix}")


def account_scoped_dir(path: Path, account: str) -> Path:
    return path if path.name.lower() == account.lower() else path / account.lower()


def scope_config_to_account(config, account: str):
    changes: dict[str, Any] = {}
    if hasattr(config, "state_file"):
        changes["state_file"] = account_scoped_file(Path(config.state_file), account)
    if hasattr(config, "monitor_history_file"):
        changes["monitor_history_file"] = account_scoped_file(Path(config.monitor_history_file), account)
    if hasattr(config, "log_dir"):
        changes["log_dir"] = account_scoped_dir(Path(config.log_dir), account)
    if hasattr(config, "monitor_account_key"):
        changes["monitor_account_key"] = account.upper()
    if not changes:
        return config
    if not is_dataclass(config):
        raise RuntimeError("Config must be a dataclass so account-specific runtime paths can be isolated safely")
    return replace(config, **changes)


def migrate_legacy_demo_runtime_files(original, scoped, account: str) -> None:
    if account != ACCOUNT_DEMO:
        return
    for name in ("state_file", "monitor_history_file"):
        if not hasattr(original, name) or not hasattr(scoped, name):
            continue
        source = Path(getattr(original, name))
        target = Path(getattr(scoped, name))
        if source == target or not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
