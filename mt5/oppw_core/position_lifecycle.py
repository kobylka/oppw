"""Position lifecycle behavior for the canonical strategy composition."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import shlex
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections import deque
from dataclasses import asdict, fields
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import MetaTrader5 as mt5

from .coordination import LeaseLostError, TradeExecutionGate
from .models import M1Bar, SessionTimes, StaleTickError, StrategyState
from .utilities import (
    ceil_step,
    ceil_whole_sl,
    floor_step,
    iso_week_key,
    parse_date,
    price_changed,
    truncate_four_decimals,
)
from .versioning import BUILD_ID, PROJECT_VERSION


class PositionLifecycleMixin:
    @staticmethod
    def position_identifier(position) -> int:
        return int(getattr(position, "identifier", 0) or getattr(position, "ticket", 0) or 0)

    def position_state_matches(self, position) -> bool:
        """Whether persisted position-scoped state belongs to this MT5 position."""
        state_identifier = getattr(self.state, "active_position_identifier", None)
        if state_identifier is None:
            # Compatibility for isolated calculations/tests with partial state.
            return True
        identifier = PositionLifecycleMixin.position_identifier(position)
        if identifier <= 0:
            return bool(
                float(getattr(self.state, "entry_price", 0.0) or 0.0) > 0
                or parse_date(getattr(self.state, "open_date", "")) is not None
            )
        return (
            identifier > 0
            and int(state_identifier or 0) == identifier
            and float(getattr(self.state, "entry_price", 0.0) or 0.0) > 0
        )

    def position_open_date(self, position) -> Optional[date]:
        if position is None:
            return parse_date(getattr(self.state, "open_date", ""))
        if PositionLifecycleMixin.position_identifier(position) <= 0:
            persisted = parse_date(getattr(self.state, "open_date", ""))
            if persisted is not None:
                return persisted
        if PositionLifecycleMixin.position_state_matches(self, position):
            persisted = parse_date(getattr(self.state, "open_date", ""))
            if persisted is not None:
                return persisted
        timestamp = (
            float(getattr(position, "time_msc", 0) or 0) / 1000.0
            if getattr(position, "time_msc", 0)
            else float(getattr(position, "time", 0.0) or 0.0)
        )
        return self.mt5_timestamp_to_local(timestamp).date() if timestamp > 0 else None

    def managed_position(self):
        positions = mt5.positions_get(symbol=self.cfg.trade_symbol)
        if positions is None:
            raise RuntimeError(f"positions_get({self.cfg.trade_symbol}) failed: {mt5.last_error()}")

        longs = [position for position in positions if int(position.type) == int(mt5.POSITION_TYPE_BUY)]
        for position in longs:
            identifier = self.position_identifier(position)
            if identifier == self.state.active_position_identifier or int(position.ticket) == self.state.active_position_ticket:
                return position

        magic_positions = [position for position in longs if int(getattr(position, "magic", 0)) == self.cfg.magic]
        if len(magic_positions) == 1:
            return magic_positions[0]
        if len(magic_positions) > 1:
            raise RuntimeError(f"Found {len(magic_positions)} long positions with strategy magic on {self.cfg.trade_symbol}")

        if self.cfg.manage_manual_position and len(longs) == 1:
            return longs[0]
        if len(longs) > 1:
            raise RuntimeError(f"Cannot safely adopt position: found {len(longs)} long positions on {self.cfg.trade_symbol}")
        return None

    @staticmethod
    def parse_leverage_from_comment(comment: str) -> int:
        marker = " L"
        if marker not in comment:
            return 0
        try:
            return int(comment.rsplit(marker, 1)[1].split()[0])
        except (ValueError, IndexError):
            return 0

    def resolve_position_leverage(self, position) -> tuple[int, str, str]:
        from_comment = self.parse_leverage_from_comment(getattr(position, "comment", ""))
        if from_comment in {8, 10}:
            return from_comment, "comment", f"{from_comment}x from MT5 position comment"
        leverage, reason = self.leverage_decision()
        return int(leverage), "strategy_decision", reason

    def infer_position_leverage(self, position) -> int:
        return self.resolve_position_leverage(position)[0]

    def is_manual_position(self, position) -> bool:
        return int(getattr(position, "magic", 0) or 0) != int(self.cfg.magic)

    def clear_stale_execution_link_for_manual_position(self, position) -> bool:
        if not self.is_manual_position(position):
            return False
        fields_to_clear = (
            "active_execution_id", "active_decision_id", "active_strategy_spec_id",
            "active_strategy_spec_hash", "execution_scheduled_at", "execution_started_at",
        )
        had_link = any(str(getattr(self.state, field_name, "") or "") for field_name in fields_to_clear)
        had_link = had_link or bool(self.state.execution_fill_confirmed or self.state.execution_position_visible)
        if not had_link:
            return False
        stale_execution_id = self.state.active_execution_id
        stale_decision_id = self.state.active_decision_id
        for field_name in fields_to_clear:
            setattr(self.state, field_name, "")
        self.state.execution_fill_confirmed = False
        self.state.execution_position_visible = False
        self.log.warning(
            "EVENT MANUAL_POSITION_STALE_EXECUTION_LINK_CLEARED position_identifier=%s "
            "stale_execution_id=%s stale_decision_id=%s",
            self.position_identifier(position), stale_execution_id or "none", stale_decision_id or "none",
        )
        return True

    def clear_immutable_hard_stop(self) -> None:
        self.state.immutable_hard_sl_position_identifier = 0
        self.state.immutable_hard_sl_price = 0.0
        self.state.immutable_hard_sl_entry_price = 0.0
        self.state.immutable_hard_sl_volume = 0.0
        self.state.immutable_hard_sl_balance = 0.0
        self.state.immutable_hard_sl_leverage = 0
        self.state.immutable_hard_sl_profit = 0.0
        self.state.immutable_hard_sl_account_currency = ""
        self.state.immutable_hard_sl_value_per_price_unit = 0.0
        self.state.immutable_hard_sl_tick_size = 0.0
        self.state.immutable_hard_sl_account_loss_cap_applied = False
        self.state.immutable_hard_sl_locked_at = ""
        self.state.immutable_hard_sl_source = ""

    def immutable_hard_stop_matches(self, position) -> bool:
        return (
            int(self.state.immutable_hard_sl_position_identifier or 0) == self.position_identifier(position)
            and float(self.state.immutable_hard_sl_price or 0.0) > 0
        )

    def lock_immutable_hard_stop(
        self,
        position,
        now: datetime,
        source: str,
        balance_override: Optional[float] = None,
    ) -> bool:
        """Calculate and persist the definitive hard stop exactly once.

        The calculation deliberately occurs only after MT5 exposes the filled
        position, so it uses the actual average fill and filled volume. A
        restart reloads the persisted values and never re-prices the baseline.
        Legacy positions without v49 state receive a one-time recovery lock.
        """
        if self.immutable_hard_stop_matches(position):
            return False

        info = mt5.symbol_info(position.symbol)
        account = mt5.account_info()
        if info is None or account is None:
            raise RuntimeError(f"Cannot lock immutable hard stop: {mt5.last_error()}")

        identifier = self.position_identifier(position)
        entry_price = float(position.price_open)
        volume = float(position.volume)
        balance = float(balance_override or getattr(account, "balance", 0.0) or 0.0)
        leverage = int(
            self.state.entry_leverage
            if self.position_state_matches(position) and self.state.entry_leverage
            else self.infer_position_leverage(position)
        )
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01)
        if identifier <= 0 or entry_price <= 0 or volume <= 0 or balance <= 0:
            raise RuntimeError(
                "Cannot lock immutable hard stop with invalid filled-position inputs: "
                f"identifier={identifier} entry={entry_price} volume={volume} balance={balance}"
            )

        price, profit, cap_applied = self.capped_hard_stop(
            position.symbol, volume, entry_price, balance, leverage, tick_size,
        )
        price = ceil_step(ceil_whole_sl(price), tick_size)
        profit_raw = mt5.order_calc_profit(
            mt5.ORDER_TYPE_BUY, position.symbol, volume, entry_price, price,
        )
        if profit_raw is None:
            raise RuntimeError(f"order_calc_profit failed while locking immutable hard stop: {mt5.last_error()}")
        profit = float(profit_raw)
        price_distance = abs(entry_price - price)
        account_value_per_price_unit = abs(profit) / price_distance if price_distance > 0 else 0.0

        self.state.immutable_hard_sl_position_identifier = identifier
        self.state.immutable_hard_sl_price = float(price)
        self.state.immutable_hard_sl_entry_price = entry_price
        self.state.immutable_hard_sl_volume = volume
        self.state.immutable_hard_sl_balance = balance
        self.state.immutable_hard_sl_leverage = leverage
        self.state.immutable_hard_sl_profit = profit
        self.state.immutable_hard_sl_account_currency = str(getattr(account, "currency", "") or "")
        self.state.immutable_hard_sl_value_per_price_unit = account_value_per_price_unit
        self.state.immutable_hard_sl_tick_size = tick_size
        self.state.immutable_hard_sl_account_loss_cap_applied = bool(cap_applied)
        self.state.immutable_hard_sl_locked_at = now.isoformat()
        self.state.immutable_hard_sl_source = source
        self.state.save(self.cfg.state_file)
        self.log.info(
            "EVENT IMMUTABLE_HARD_SL_LOCKED position_identifier=%s ticket=%s source=%s price=%.5f "
            "entry=%.5f volume=%.8f balance_at_fill=%.2f leverage=%s profit_at_stop=%.2f "
            "account_currency=%s account_value_per_price_unit=%.8f tick_size=%.8f account_loss_cap=%s",
            identifier, int(position.ticket), source, price, entry_price, volume, balance, leverage, profit,
            self.state.immutable_hard_sl_account_currency or "unknown", account_value_per_price_unit,
            tick_size, bool(cap_applied),
        )
        return True

    def recovery_hard_stop_needs_leverage_repair(self, position, leverage: int) -> bool:
        return (
            self.immutable_hard_stop_matches(position)
            and self.is_manual_position(position)
            and int(self.state.immutable_hard_sl_leverage or 0) in {8, 10}
            and int(self.state.immutable_hard_sl_leverage) != int(leverage)
        )

    def repair_recovery_hard_stop_leverage(self, position, now: datetime, leverage: int) -> bool:
        if not self.recovery_hard_stop_needs_leverage_repair(position, leverage):
            return False
        old_leverage = int(self.state.immutable_hard_sl_leverage)
        old_price = float(self.state.immutable_hard_sl_price)
        balance_at_fill = float(self.state.immutable_hard_sl_balance or 0.0)
        self.clear_immutable_hard_stop()
        self.state.entry_leverage = int(leverage)
        self.lock_immutable_hard_stop(
            position,
            now,
            "RECOVERY_LEVERAGE_CORRECTION",
            balance_override=balance_at_fill if balance_at_fill > 0 else None,
        )
        self.state.first_protection_confirmed = False
        self.log.warning(
            "EVENT RECOVERY_HARD_SL_CORRECTED position_identifier=%s old_leverage=%s new_leverage=%s "
            "old_price=%.5f new_price=%.5f balance_at_fill=%.2f",
            self.position_identifier(position), old_leverage, leverage, old_price,
            float(self.state.immutable_hard_sl_price), balance_at_fill,
        )
        return True

    def clear_current_position_exit_state(self, clear_last_exit: bool = True) -> None:
        self.state.exit_latched_reason = ""
        self.state.exit_latched_at = ""
        self.state.active_sl_reason = ""
        self.state.active_tp_reason = ""
        self.state.active_sl_price = 0.0
        self.state.active_tp_price = 0.0
        self.state.active_protection_updated_at = ""
        self.state.active_protection_position_identifier = 0
        self.state.or5_last_evaluated_bar_utc = 0
        self.state.or5_authorized_request_id = ""
        self.state.or5_authorized_position_identifier = 0
        self.state.or5_authorized_inputs = {}
        self.clear_immutable_hard_stop()
        if clear_last_exit:
            self.state.last_exit_reason = ""
            self.state.last_exit_price = 0.0
            self.state.last_exit_time = ""
            self.state.last_exit_deal_ticket = 0

    def weekday_sl_target(self, position, now: datetime) -> tuple[float, str]:
        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)

        # One 0.4% TSL is active continuously from the Thursday date change
        # through Friday. Keep it over the weekend if TO did not close the trade.
        if now.weekday() in (3, 4, 5, 6):
            return max(hard_sl, entry * self.cfg.tsl_ratio), "TSL"

        # Never weaken a surviving prior-week TSL before the position is closed.
        state_matches = self.position_state_matches(position)
        opened = self.position_open_date(position)
        if (
            state_matches
            and opened is not None
            and iso_week_key(opened) != iso_week_key(now.date())
            and self.state.active_sl_reason == "TSL"
        ):
            return max(hard_sl, entry * self.cfg.tsl_ratio), "TSL"

        return hard_sl, "SL"

    def infer_active_protection(self, position, now: datetime) -> None:
        identifier = self.position_identifier(position)
        entry = float(position.price_open)
        sl = float(position.sl)
        tp = float(position.tp)
        info = mt5.symbol_info(position.symbol)
        tolerance = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) * 1.5 if info is not None else 0.01

        self.state.active_protection_position_identifier = identifier
        self.state.active_sl_price = sl
        self.state.active_tp_price = tp
        self.state.active_sl_reason = ""
        self.state.active_tp_reason = ""

        if sl > 0 and entry > 0:
            tsl = entry * self.cfg.tsl_ratio
            hard_sl = self.hard_sl_price(position)
            if abs(sl - tsl) <= tolerance:
                self.state.active_sl_reason = "TSL"
            elif abs(sl - hard_sl) <= tolerance:
                self.state.active_sl_reason = "SL"
            else:
                self.state.active_sl_reason = "BROKER_SL"

        if tp > 0:
            self.state.active_tp_reason = "BH" if self.state.break_even else "BROKER_TP"
        self.state.active_protection_updated_at = now.isoformat()

    def record_active_protection(self, position, sl: float, tp: float, sl_reason: str, tp_reason: str, now: Optional[datetime] = None) -> None:
        now = now or datetime.now(self.tz)
        identifier = self.position_identifier(position)
        same_position = self.state.active_protection_position_identifier == identifier
        tolerance = 1e-8
        before = (
            self.state.active_sl_reason, self.state.active_tp_reason, self.state.active_sl_price,
            self.state.active_tp_price, self.state.active_protection_position_identifier,
        )

        if sl > 0:
            same_sl = same_position and abs(self.state.active_sl_price - sl) <= tolerance
            legacy_tsl = self.state.active_sl_reason.startswith("TSL") and self.state.active_sl_reason != "TSL"
            if not same_sl or not self.state.active_sl_reason or legacy_tsl:
                self.state.active_sl_reason = sl_reason or ("TSL" if legacy_tsl else self.state.active_sl_reason) or "SL"
            self.state.active_sl_price = sl
        else:
            self.state.active_sl_reason = ""
            self.state.active_sl_price = 0.0

        if tp > 0:
            same_tp = same_position and abs(self.state.active_tp_price - tp) <= tolerance
            if not same_tp or not self.state.active_tp_reason:
                self.state.active_tp_reason = tp_reason or self.state.active_tp_reason or "TP"
            self.state.active_tp_price = tp
        else:
            self.state.active_tp_reason = ""
            self.state.active_tp_price = 0.0

        self.state.active_protection_position_identifier = identifier
        after = (
            self.state.active_sl_reason, self.state.active_tp_reason, self.state.active_sl_price,
            self.state.active_tp_price, self.state.active_protection_position_identifier,
        )
        if after != before:
            self.state.active_protection_updated_at = now.isoformat()
            self.state.save(self.cfg.state_file)

    def reconstruct_break_even(self, opened: date, signal_reference: float, now: datetime) -> bool:
        if signal_reference <= 0:
            return False
        final_day = now.date() if now >= self.session_times(now.date()).close_processing else now.date() - timedelta(days=1)
        if final_day <= opened:
            return False

        sessions = self.calendar.sessions_in_range((opened + timedelta(days=1)).isoformat(), final_day.isoformat())
        for session in sessions:
            session_day = session.date()
            if not self.break_even_check_eligible(opened, session_day):
                continue
            bar = self.completed_session_close_bar(self.cfg.signal_symbol, session_day)
            if bar is not None and bar.close < signal_reference * self.cfg.break_even_ratio:
                return True
        return False

    def recover_position_state(self, position, now: datetime, force: bool = False) -> bool:
        identifier = self.position_identifier(position)
        same_position = self.state.active_position_identifier == identifier and self.state.entry_price > 0
        if same_position and not force:
            return False

        position_timestamp = getattr(position, "time_msc", 0) / 1000.0 if getattr(position, "time_msc", 0) else position.time
        opened = self.mt5_timestamp_to_local(position_timestamp)
        leverage, leverage_source, leverage_reason = self.resolve_position_leverage(position)
        self.clear_stale_execution_link_for_manual_position(position)
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, opened.date())
        cash_open = self.session_times(opened.date()).cash_open
        if signal_open is not None and signal_open > 0:
            signal_pending = False
        elif same_position and self.state.entry_signal_daily_open > 0 and not self.state.entry_signal_open_pending:
            # Preserve an already captured cash-open reference if a later MT5
            # historical-bar request is temporarily unavailable.
            signal_open = float(self.state.entry_signal_daily_open)
            signal_pending = False
        else:
            # An early BUY can legitimately precede the signal cash open by
            # hours. Never fabricate that future reference from the fill price.
            # Keep it pending after cash open too, so restart/reconnect cycles
            # continue retrieving the exact opening M1 bar until it is present.
            signal_open = 0.0
            signal_pending = True
            self.log.warning(
                "EVENT RECOVERY_SIGNAL_OPEN_PENDING open_day=%s cash_open=%s capture_status=%s fallback=none",
                opened.date(), cash_open.isoformat(), "WAITING" if now < cash_open else "RETRYING",
            )

        recovered_break_even = self.state.break_even if same_position else False
        if signal_open > 0:
            recovered_break_even = recovered_break_even or self.reconstruct_break_even(opened.date(), signal_open, now)

        previous_identifier = self.state.active_position_identifier
        self.state.active_position_identifier = identifier
        self.state.active_position_ticket = int(position.ticket)
        self.state.open_date = opened.date().isoformat()
        self.state.entry_price = float(position.price_open)
        self.state.entry_signal_daily_open = float(signal_open)
        self.state.entry_signal_open_pending = signal_pending
        self.state.entry_leverage = leverage
        if not self.state.active_strategy_spec_id:
            self.state.active_strategy_spec_id = self.strategy_specification["specId"]
            self.state.active_strategy_spec_hash = self.strategy_specification["specHash"]
        self.state.prev_open = float(position.price_open)
        self.state.last_entry_week = iso_week_key(opened.date())
        self.state.entry_pending_until_utc = 0
        self.state.break_even = recovered_break_even

        if previous_identifier != identifier:
            self.clear_current_position_exit_state(clear_last_exit=True)
            self.state.first_protection_confirmed = False
            self.state.last_processed_bar_utc = 0
            self.state.last_close_processed_date = ""
            lock_source = "POST_FILL" if self.state.active_execution_id else "RECOVERY_INITIALIZATION"
            self.lock_immutable_hard_stop(position, now, lock_source)
            self.infer_active_protection(position, now)
        else:
            if self.repair_recovery_hard_stop_leverage(position, now, leverage):
                self.infer_active_protection(position, now)
            elif not self.immutable_hard_stop_matches(position):
                self.lock_immutable_hard_stop(position, now, "RECOVERY_INITIALIZATION")
            if force and self.state.active_protection_position_identifier != identifier:
                self.infer_active_protection(position, now)

        self.state.save(self.cfg.state_file)
        self.log.info(
            "EVENT POSITION_RECOVERED ticket=%s identifier=%s magic=%s open_time=%s entry=%.5f volume=%s leverage=%s "
            "leverage_source=%s leverage_reason=%s signal_open=%.5f signal_open_pending=%s break_even=%s",
            position.ticket, identifier, getattr(position, "magic", 0), opened.isoformat(), float(position.price_open),
            position.volume, leverage, leverage_source, shlex.quote(leverage_reason),
            float(signal_open), signal_pending, recovered_break_even,
        )
        actual_price = float(getattr(position, "price_current", 0.0) or position.price_open)
        if self.state.active_execution_id and not self.state.execution_fill_confirmed:
            self.execution_stage("FILLED", position_ticket=int(position.ticket), reference_price=float(position.price_open), actual_price=actual_price, reason="position_reconciliation")
            self.state.execution_fill_confirmed = True
        if self.state.active_execution_id and not self.state.execution_position_visible:
            self.execution_stage("POSITION_VISIBLE", position_ticket=int(position.ticket), reference_price=float(position.price_open), actual_price=actual_price)
            self.state.execution_position_visible = True
        if self.is_executor:
            self.state.save(self.cfg.state_file)
        return True

    def capture_entry_signal_open(self, position, now: datetime) -> bool:
        if position is None or not self.state.entry_signal_open_pending:
            return False
        opened = parse_date(self.state.open_date)
        if opened is None or now < self.session_times(opened).cash_open:
            return False
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, opened)
        if signal_open is None:
            current = time_module.monotonic()
            if current - self.last_signal_open_pending_log_monotonic >= 60.0:
                self.last_signal_open_pending_log_monotonic = current
                self.log.warning(
                    "EVENT ENTRY_SIGNAL_OPEN_CAPTURE_RETRY day=%s symbol=%s cash_open=%s fallback=none",
                    opened, self.cfg.signal_symbol, self.session_times(opened).cash_open.isoformat(),
                )
            return False
        self.state.entry_signal_daily_open = float(signal_open)
        self.state.entry_signal_open_pending = False
        self.last_signal_open_pending_log_monotonic = 0.0
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT ENTRY_SIGNAL_OPEN_CAPTURED day=%s symbol=%s price=%.5f", opened, self.cfg.signal_symbol, signal_open)
        self.emit_status("ENTRY_SIGNAL_OPEN_CAPTURED", position, now)
        return True

    def live_signal_price(self) -> float:
        tick = self.require_fresh_tick(self.cfg.signal_symbol)
        last = float(getattr(tick, "last", 0.0) or 0.0)
        bid = float(getattr(tick, "bid", 0.0) or 0.0)
        ask = float(getattr(tick, "ask", 0.0) or 0.0)
        price = last if last > 0 else bid if bid > 0 else ask
        if price <= 0:
            raise RuntimeError(f"No usable live price for {self.cfg.signal_symbol}")
        return price

    @staticmethod
    def trade_class(preleverage_return: float, exit_reason: str) -> str:
        """Classify in priority order A, B, C, D.

        A and B are return classes and therefore take priority over the exit
        mechanism. A positive TSL/BE trade remains A or B. C is reserved for
        negative break-even/TSL outcomes. Everything else is D.
        """
        value = float(preleverage_return)
        reason = str(exit_reason or "").strip().upper().replace("-", "_")
        if value >= 0.007:
            return "A"
        if value >= 0.0:
            return "B"
        c_reasons = {"BE", "BH", "BEO", "BEPRE", "BREAK_EVEN", "BREAK_EVEN_EXIT"}
        if reason in c_reasons or reason.startswith("TSL") or "BREAK_EVEN" in reason:
            return "C"
        return "D"

    def closed_position_contract(self) -> tuple[str, float, float]:
        """Return the authoritative strategy close label, reference and raw return.

        Broker-side protective stops can fill while this process is stopped. In
        that case the first post-restart quote is not the exit price, so retain
        the installed protection threshold. For a latched market exit, retain
        the confirmed MT5 deal price instead of older installed protection.
        Account P/L remains the authority for actual cash execution results.
        """
        latched_reason = str(self.state.exit_latched_reason or "")
        reference_price = float(self.state.last_exit_price or 0.0)
        if latched_reason:
            # A fenced market exit is authoritative over protection that was
            # installed earlier on the same position.  close_position_market
            # records its request price and replaces it with the exact MT5
            # deal price when the acknowledgement includes a deal ticket.
            reason = latched_reason
        else:
            # Keep the reason and its installed price paired. The former code
            # preferred a TP reason but then independently preferred the SL
            # price, producing an impossible BH-at-hard-SL close contract.
            if self.state.active_tp_reason and self.state.active_tp_price > 0:
                reason = self.state.active_tp_reason
                reference_price = float(self.state.active_tp_price)
            elif self.state.active_sl_reason and self.state.active_sl_price > 0:
                reason = self.state.active_sl_reason
                reference_price = float(self.state.active_sl_price)
            else:
                reason = "broker/manual"

        if str(reason).upper() == "TSL":
            reason = f"TSL_{float(self.cfg.tsl_stop) * 100.0:g}%"

        entry_price = float(self.state.entry_price or 0.0)
        change = reference_price / entry_price - 1.0 if reference_price > 0 and entry_price > 0 else 0.0
        return reason, reference_price, change

    def exact_broker_exit_deal(self, position_identifier: int):
        """Return the latest exact SELL deal for the disappeared long position."""
        history = getattr(mt5, "history_deals_get", None)
        if not callable(history):
            raise RuntimeError("MT5 history_deals_get is unavailable")
        deals = history(position=int(position_identifier))
        if deals is None:
            raise RuntimeError(f"history_deals_get(position={position_identifier}) failed: {mt5.last_error()}")
        sell_type = int(getattr(mt5, "DEAL_TYPE_SELL", 1))
        candidates = [
            deal for deal in deals
            if int(getattr(deal, "type", -1)) == sell_type
            and float(getattr(deal, "price", 0.0) or 0.0) > 0
            and float(getattr(deal, "volume", 0.0) or 0.0) > 0
            and int(getattr(deal, "ticket", 0) or 0) > 0
        ]
        if not candidates:
            raise RuntimeError(f"No exact closing SELL deal yet for position {position_identifier}")
        return max(
            candidates,
            key=lambda deal: (
                int(getattr(deal, "time_msc", 0) or 0),
                int(getattr(deal, "time", 0) or 0),
                int(getattr(deal, "ticket", 0) or 0),
            ),
        )

    def broker_deal_exit_reason(self, deal) -> str:
        deal_reason = int(getattr(deal, "reason", -1))
        if deal_reason == int(getattr(mt5, "DEAL_REASON_TP", 5)):
            return self.state.active_tp_reason or "BROKER_TP"
        if deal_reason == int(getattr(mt5, "DEAL_REASON_SL", 4)):
            reason = self.state.active_sl_reason or "SL"
            return f"TSL_{float(self.cfg.tsl_stop) * 100.0:g}%" if str(reason).upper() == "TSL" else reason
        return self.state.exit_latched_reason or "broker/manual"

    @staticmethod
    def broker_deal_time(deal) -> str:
        time_msc = int(getattr(deal, "time_msc", 0) or 0)
        timestamp = time_msc / 1000.0 if time_msc > 0 else float(getattr(deal, "time", 0) or 0)
        if timestamp <= 0:
            raise RuntimeError("Exact closing deal has no valid timestamp")
        return datetime.fromtimestamp(timestamp, UTC).isoformat()

    def finalize_closed_position(self) -> bool:
        """Publish the exact broker close and then clear local position state.

        The authoritative completed-trade return, prices, reason and class are
        read from MySQL on the next normal weekday leverage-input refresh. The
        exact EXIT_FILLED event repairs any earlier flat-snapshot projection.
        Missing deal history leaves state intact so a later cycle retries and
        no new entry can proceed on an unverified previous-trade outcome.
        """
        identifier = int(self.state.active_position_identifier or self.state.active_position_ticket or 0)
        position_ticket = int(self.state.active_position_ticket or identifier)
        if not identifier:
            return True

        try:
            deal = self.exact_broker_exit_deal(identifier)
            exit_price = float(deal.price)
            reason = self.broker_deal_exit_reason(deal)
            filled_at = self.broker_deal_time(deal)
        except Exception as exc:
            self.log.warning(
                "EVENT POSITION_CLOSE_RECONCILIATION_DEFERRED position_identifier=%s ticket=%s "
                "reason=exact_broker_deal_unavailable retry=true error=%s",
                identifier, position_ticket, exc,
            )
            return False
        entry_price = float(self.state.entry_price or 0.0)
        change = exit_price / entry_price - 1.0 if exit_price > 0 and entry_price > 0 else 0.0
        reason_log = shlex.quote(reason)
        deal_ticket = int(getattr(deal, "ticket", 0) or 0)
        exit_fill_already_published = int(getattr(self.state, "last_exit_deal_ticket", 0) or 0) == deal_ticket
        self.state.last_exit_position_identifier = identifier
        self.state.last_exit_time = filled_at
        self.state.last_exit_reason = reason
        self.state.last_exit_price = exit_price
        self.state.last_exit_deal_ticket = deal_ticket
        self.state.save(self.cfg.state_file)
        if not exit_fill_already_published:
            self.execution_stage(
                "EXIT_FILLED", position_ticket=position_ticket,
                reference_price=(
                    float(self.state.active_tp_price)
                    if int(getattr(deal, "reason", -1)) == int(getattr(mt5, "DEAL_REASON_TP", 5))
                    else float(self.state.active_sl_price or 0.0)
                ),
                actual_price=exit_price, reason=reason,
                order_ticket=int(getattr(deal, "order", 0) or 0),
                deal_ticket=deal_ticket,
                side="SELL", volume=float(getattr(deal, "volume", 0.0) or 0.0),
                event_at=filled_at,
            )
        self.execution_stage(
            "CLOSED", position_ticket=position_ticket,
            reference_price=entry_price, actual_price=exit_price,
            deal_ticket=deal_ticket, reason=reason,
            event_at=filled_at,
        )
        self.log.info(
            "EVENT POSITION_CLOSED reason=%s source=exact_mt5_deal position_identifier=%s deal_ticket=%s "
            "entry=%.5f exit=%.5f change=%.10f preleverage_return=%.10f trade_class=%s",
            reason_log, identifier, deal_ticket,
            entry_price, exit_price, change, change,
            self.trade_class(change, reason),
        )

        self.state.active_position_identifier = 0
        self.state.active_position_ticket = 0
        self.state.open_date = ""
        self.state.entry_price = 0.0
        self.state.entry_signal_daily_open = 0.0
        self.state.entry_signal_open_pending = False
        self.state.entry_leverage = 0
        self.state.active_strategy_spec_id = ""
        self.state.active_strategy_spec_hash = ""
        self.state.break_even = False
        self.state.entry_pending_until_utc = 0
        self.clear_current_position_exit_state(clear_last_exit=False)
        self.state.save(self.cfg.state_file)
        return True
