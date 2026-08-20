"""Persistent state and immutable runtime value objects."""

from __future__ import annotations

import json
import os
import time as time_module
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path

@dataclass
class StrategyState:
    version: int = 11

    last_trading_date: str = ""
    last_close_processed_date: str = ""
    last_processed_bar_utc: int = 0
    last_entry_week: str = ""
    entry_pending_until_utc: int = 0
    last_open_action_date: str = ""
    last_close_action_date: str = ""

    active_position_identifier: int = 0
    active_position_ticket: int = 0
    open_date: str = ""
    entry_price: float = 0.0
    entry_signal_daily_open: float = 0.0
    entry_signal_open_pending: bool = False
    entry_leverage: int = 0
    active_strategy_spec_id: str = ""
    active_strategy_spec_hash: str = ""

    break_even: bool = False
    exit_latched_reason: str = ""
    exit_latched_at: str = ""
    pending_market_exit_reason: str = ""
    pending_market_exit_position_identifier: int = 0
    pending_market_exit_request_id: str = ""
    pending_market_exit_triggered_at: str = ""
    pending_market_exit_not_before: str = ""
    pending_market_exit_inputs: dict[str, object] = field(default_factory=dict)

    active_sl_reason: str = ""
    active_tp_reason: str = ""
    active_sl_price: float = 0.0
    active_tp_price: float = 0.0
    active_protection_updated_at: str = ""
    active_protection_position_identifier: int = 0

    # Definitive filled-position hard-stop invariant. These values are written
    # once when the actual position first becomes visible and remain immutable
    # until that position closes.
    immutable_hard_sl_position_identifier: int = 0
    immutable_hard_sl_price: float = 0.0
    immutable_hard_sl_entry_price: float = 0.0
    immutable_hard_sl_volume: float = 0.0
    immutable_hard_sl_balance: float = 0.0
    immutable_hard_sl_leverage: int = 0
    immutable_hard_sl_profit: float = 0.0
    immutable_hard_sl_account_currency: str = ""
    immutable_hard_sl_value_per_price_unit: float = 0.0
    immutable_hard_sl_tick_size: float = 0.0
    immutable_hard_sl_account_loss_cap_applied: bool = False
    immutable_hard_sl_locked_at: str = ""
    immutable_hard_sl_source: str = ""

    prev_change: float = 0.0
    prev_full_week_change: float = 0.0
    prev_open: float = 0.0

    last_exit_price: float = 0.0
    last_exit_time: str = ""
    last_exit_reason: str = ""
    last_exit_trade_class: str = ""
    last_exit_preleverage_return: float = 0.0
    last_exit_position_identifier: int = 0
    last_exit_deal_ticket: int = 0

    active_execution_id: str = ""
    active_decision_id: str = ""
    execution_scheduled_at: str = ""
    execution_started_at: str = ""
    execution_fill_confirmed: bool = False
    execution_position_visible: bool = False
    first_protection_confirmed: bool = False
    last_missed_entry_week: str = ""

    entry_rule_controls_revision: int = 0
    entry_rule_controls: dict[str, bool] = field(default_factory=dict)
    entry_rule_decision_week: str = ""
    entry_rule_decision_status: str = ""
    entry_rule_decision_inputs: dict[str, object] = field(default_factory=dict)

    position_rule_controls_revision: int = 0
    position_rule_controls: dict[str, bool] = field(default_factory=dict)
    or5_last_evaluated_bar_utc: int = 0
    or5_authorized_request_id: str = ""
    or5_authorized_position_identifier: int = 0
    or5_authorized_inputs: dict[str, object] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "StrategyState":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")
        for attempt in range(1, 6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt >= 5:
                    raise
                time_module.sleep(0.05)


@dataclass(frozen=True)
class M1Bar:
    utc_timestamp: int
    local_datetime: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class SessionTimes:
    cash_open: datetime
    buy_action: datetime
    open_action: datetime
    weekly_close: datetime
    close_bar_open: datetime
    close_processing: datetime


class StaleTickError(RuntimeError):
    def __init__(self, symbol: str, age_seconds: float):
        self.symbol = symbol
        self.age_seconds = age_seconds
        super().__init__(f"Stale tick for {symbol}: age={age_seconds:.1f}s")
