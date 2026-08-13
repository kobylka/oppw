"""Monitoring behavior for the canonical strategy composition."""

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


def format_lot_volume(value: Any) -> str:
    """Render broker lot precision without hiding sub-0.01 volume steps."""
    rendered = f"{float(value):.8f}".rstrip("0").rstrip(".")
    return rendered if rendered else "0"


class MonitoringMixin:
    def format_status(self, reason: str, position, now: datetime, current_bar: Optional[M1Bar] = None) -> str:
        due, due_reason, final_day = self.weekly_exit_status(position, now)
        account = mt5.account_info()
        equity = float(getattr(account, "equity", 0.0)) if account is not None else 0.0
        deposit = float(getattr(account, "margin", 0.0)) if account is not None else 0.0
        currency = str(getattr(account, "currency", "")).strip() if account is not None else ""
        currency_suffix = f" {currency}" if currency else ""
        phase = self.phase(now)
        regime = self.protection_regime(now, position) if position is not None else "None"

        if position is None:
            preview = self.potential_position_preview()
            leverage = int(preview["strategyLeverage"])
            leverage_reason = str(preview["leverageReason"])
            if bool(preview["available"]):
                potential_lines = [
                    f"next potential position: BUY {format_lot_volume(preview['volume'])} lot {preview['symbol']} @ {float(preview['price']):.5f}",
                    f"required deposit: {float(preview['requiredDeposit']):.2f}{currency_suffix}",
                    f"required balance: {float(preview['requiredBalance']):.2f}{currency_suffix} ({float(preview.get('requiredBalanceMultiplier') or self.required_balance_multiplier(int(preview.get('strategyLeverage') or self.cfg.base_leverage))):.3f} Ă— deposit)",
                    f"balance headroom: {float(preview['requiredBalanceHeadroom']):.2f}{currency_suffix}",
                    f"next volume step: {format_lot_volume(preview['nextVolumeStep'])} lot requires balance {float(preview['nextVolumeStepRequiredBalance']):.2f}{currency_suffix}",
                    f"effective leverage: {float(preview['effectiveLeverage']):.4f}x ({float(self.cfg.sizing_multiplier):g} Ă— required deposit / balance)",
                    f"potential hard SL: {float(preview['potentialStopLossPrice']):.5f} ({float(preview['potentialStopLossPercent']):.4f}%)",
                    f"potential SL cash P/L: {float(preview['potentialStopLossCash']):.2f}{currency_suffix}",
                    f"free margin after: {float(preview['freeMarginAfter']):.2f}{currency_suffix}",
                    f"potential notional: {float(preview['positionNotional']):.2f}{currency_suffix}",
                ]
            else:
                potential_lines = [
                    "next potential position: unavailable",
                    f"potential position error: {preview['error'] or 'unknown'}",
                ]
            lines = [
                f"==================== TRADE STATUS - {reason} ====================",
                f"phase: {phase} protection regime: {regime}",
                f"time: {now:%Y-%m-%d %H:%M:%S %Z} week: {iso_week_key(now.date())}",
                "closest condition: none â€” no open position",
                "position: FLAT",
                *potential_lines,
                f"chosen leverage: {leverage}x",
                f"leverage reason: {leverage_reason}",
                f"current P/L: 0.00{currency_suffix}",
                "current P/L %: 0.0000%",
                "current P/L % leveraged: 0.0000%",
                f"equity: {equity:.2f}{currency_suffix} deposit: {deposit:.2f}{currency_suffix}",
                f"final trading day: {final_day or '-'}",
                f"weekly exit: {due_reason} (due={due})",
                f"last exit: {self.state.last_exit_reason or '-'}",
                f"build: {BUILD_ID}",
                "======================================================",
            ]
            return "\n" + "\n".join(lines) + "\n"

        try:
            tick = self.latest_tick(position.symbol)
            bid = float(tick.bid)
            ask = float(tick.ask)
        except Exception:
            bid = float(getattr(position, "price_current", 0.0))
            ask = 0.0

        entry = float(position.price_open)
        raw_pnl_pct = bid / entry - 1.0 if bid > 0 and entry > 0 else 0.0
        leverage = (
            self.state.entry_leverage
            if self.position_state_matches(position) and self.state.entry_leverage
            else self.infer_position_leverage(position)
        )
        leveraged_pnl_pct = raw_pnl_pct * leverage
        current_pnl = float(getattr(position, "profit", 0.0)) + float(getattr(position, "swap", 0.0))
        position_timestamp = getattr(position, "time_msc", 0) / 1000.0 if getattr(position, "time_msc", 0) else position.time
        opened = self.mt5_timestamp_to_local(position_timestamp)
        closest = self.closest_price_condition(position, now, bid)
        previous_bar = self.previous_m1_bar(position.symbol, now)
        if previous_bar is None:
            previous_bar_text = "None"
        else:
            raw_epoch_utc = datetime.fromtimestamp(previous_bar.utc_timestamp, UTC)
            bar_local = previous_bar.local_datetime
            actual_utc = bar_local.astimezone(UTC)
            previous_bar_text = (
                f"epoch={previous_bar.utc_timestamp} "
                f"raw_epoch_utc={raw_epoch_utc.isoformat(timespec='milliseconds')} "
                f"bar_time={bar_local.isoformat(timespec='milliseconds')} "
                f"actual_utc={actual_utc.isoformat(timespec='milliseconds')} "
                f"O={previous_bar.open:.5f} H={previous_bar.high:.5f} "
                f"L={previous_bar.low:.5f} C={previous_bar.close:.5f}"
            )

        lines = [
            f"==================== TRADE STATUS - {reason} ====================",
            f"phase: {phase} protection regime: {regime}",
            f"time: {now:%Y-%m-%d %H:%M:%S %Z} week: {iso_week_key(now.date())}",
            f"closest condition: {closest}",
            f"position: {format_lot_volume(position.volume)} lot {position.symbol}",
            f"leverage: {leverage}x",
            f"opened: {opened:%Y-%m-%d %H:%M:%S %Z}",
            f"open price: {entry:.5f}",
            f"current ask: {ask:.5f}",
            f"current P/L: {current_pnl:.2f}{currency_suffix}",
            f"current P/L %: {raw_pnl_pct:.4%}",
            f"current P/L % leveraged: {leveraged_pnl_pct:.4%}",
            f"equity: {equity:.2f}{currency_suffix} deposit: {deposit:.2f}{currency_suffix}",
            f"SL: {float(position.sl):.5f} ({self.state.active_sl_reason or '-'})",
            f"immutable hard SL: {float(self.state.immutable_hard_sl_price or 0.0):.5f} "
            f"(locked={self.state.immutable_hard_sl_locked_at or '-'} source={self.state.immutable_hard_sl_source or '-'})",
            f"immutable SL inputs: entry={float(self.state.immutable_hard_sl_entry_price or 0.0):.5f} "
            f"volume={float(self.state.immutable_hard_sl_volume or 0.0):.8f} "
            f"balance={float(self.state.immutable_hard_sl_balance or 0.0):.2f}{currency_suffix} "
            f"profit={float(self.state.immutable_hard_sl_profit or 0.0):.2f}{currency_suffix}",
            f"TP: {float(position.tp):.5f} ({self.state.active_tp_reason or '-'})",
            f"break-even armed: {self.state.break_even}",
            f"exit latch: {self.state.exit_latched_reason or '-'}",
            f"final trading day: {final_day or '-'}",
            f"weekly exit: {due_reason} (due={due})",
            f"previous M1: {previous_bar_text}",
            f"build: {BUILD_ID}",
            "======================================================",
        ]
        return "\n" + "\n".join(lines) + "\n"

    def emit_status(self, reason: str, position=None, now: Optional[datetime] = None, current_bar: Optional[M1Bar] = None) -> None:
        now = now or datetime.now(self.tz)
        self.log.info("STATUS%s", self.format_status(reason, position, now, current_bar))

    @staticmethod
    def account_funding_signature(account) -> Optional[tuple[float, float]]:
        if account is None:
            return None
        return (round(float(getattr(account, "balance", 0.0) or 0.0), 2), round(float(getattr(account, "credit", 0.0) or 0.0), 2))

    def publish_account_change_if_needed(self, position, now: datetime, current_bar: Optional[M1Bar], label: str) -> bool:
        monotonic = time_module.monotonic()
        if monotonic - self.last_account_funding_check_monotonic < float(self.cfg.account_funding_check_interval_seconds):
            return False
        self.last_account_funding_check_monotonic = monotonic
        account = mt5.account_info()
        signature = self.account_funding_signature(account)
        if signature is None:
            return False
        previous = self.last_account_funding_signature
        self.last_account_funding_signature = signature
        if previous is None or signature == previous:
            return False

        position_open = position is not None
        preview = self.potential_position_preview(assume_current_position_closed=position_open)
        decision = self.last_strategy_decision_payload
        if not position_open:
            decision = self.record_strategy_decision_if_changed(force=self.is_weekend(now), preview=preview)

        current_bar = current_bar or self.current_m1_bar(self.cfg.trade_symbol)
        if self.is_weekend(now):
            snapshot = self.build_weekend_startup_snapshot(
                position, now, current_bar, preview, decision, self.last_closed_trade_payload(refresh=False),
            )
        else:
            snapshot = self.build_mobile_snapshot(position, now, current_bar, potential_position=preview)
            snapshot["strategyDecision"] = decision
        snapshot["statusUpdate"] = {
            "kind": "ACCOUNT_FUNDING_CHANGE", "minute": now.strftime("%Y-%m-%d %H:%M"),
            "generatedAt": now.isoformat(), "build": BUILD_ID,
        }
        self.monitor_publisher.submit_snapshot(snapshot, guaranteed=True)
        self.last_monitor_publish_monotonic = monotonic
        self.log.info(
            "EVENT ACCOUNT_FUNDING_CHANGE_DETECTED role=%s old_balance=%.2f new_balance=%.2f old_credit=%.2f new_credit=%.2f "
            "position_open=%s current_position_unchanged=true next_trade_volume=%.8f next_trade_required_deposit=%.2f "
            "next_trade_required_balance=%.2f required_balance_multiplier=%.3f actual_free_margin=%.2f "
            "sizing_free_margin=%.2f sizing_units=%s",
            label, previous[0], signature[0], previous[1], signature[1], str(position_open).lower(),
            float(preview.get("volume") or 0.0), float(preview.get("requiredDeposit") or 0.0),
            float(preview.get("requiredBalance") or 0.0), float(preview.get("requiredBalanceMultiplier") or self.required_balance_multiplier(int(preview.get("strategyLeverage") or self.cfg.base_leverage))),
            float(preview.get("freeMargin") or 0.0), float(preview.get("sizingFreeMargin") or 0.0),
            int(preview.get("sizingUnits") or 0), extra={"skip_mobile_publish": True},
        )
        return True

    def status_signature(self, position, now: datetime) -> tuple[Any, ...]:
        if position is None:
            return (None, self.state.last_exit_reason, self.state.break_even, self.protection_regime(now), self.account_funding_signature(mt5.account_info()))
        return (
            int(position.ticket), round(float(position.volume), 8), round(float(position.sl), 5), round(float(position.tp), 5),
            self.state.break_even, self.state.exit_latched_reason, self.state.active_sl_reason, self.state.active_tp_reason,
            self.protection_regime(now, position), self.account_funding_signature(mt5.account_info()),
        )

    def monitor_tick_snapshot(self, symbol: str, now: datetime) -> tuple[float, float, Optional[float], str]:
        try:
            tick = self.latest_tick(symbol)
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            timestamp = getattr(tick, "time_msc", 0) / 1000.0 if getattr(tick, "time_msc", 0) else float(getattr(tick, "time", 0.0) or 0.0)
            age = None
            tick_time = ""
            if timestamp > 0:
                tick_local = self.mt5_timestamp_to_local(timestamp)
                age = max(0.0, (now - tick_local).total_seconds())
                tick_time = tick_local.isoformat()
            return bid, ask, age, tick_time
        except Exception:
            return 0.0, 0.0, None, ""

    def monitor_next_action(self, position, now: datetime) -> tuple[str, str]:
        session = self.session_times(now.date())
        day_key = now.date().isoformat()
        if position is not None:
            state_matches = self.position_state_matches(position)
            if (
                self.oh_check_eligible(now.date())
                and now < session.open_action
                and (not state_matches or self.state.last_open_action_date != day_key)
            ):
                return "OH", session.open_action.isoformat()
            if now < session.weekly_close and (not state_matches or self.state.last_close_action_date != day_key):
                name = "CH / TO" if self.final_trading_day(now.date()) == now.date() else "CH"
                return name, session.weekly_close.isoformat()
            if now < session.close_processing:
                return "DAILY CLOSE", session.close_processing.isoformat()

        try:
            end = now.date() + timedelta(days=14)
            sessions = self.calendar.sessions_in_range(now.date().isoformat(), end.isoformat())
            for calendar_session in sessions:
                session_day = calendar_session.date()
                candidate_session = self.session_times(session_day)
                candidate = candidate_session.buy_action if position is None else candidate_session.open_action
                if candidate <= now:
                    continue
                if position is None and session_day.weekday() not in (0, 1):
                    continue
                if position is None and self.state.last_entry_week == iso_week_key(session_day):
                    continue
                if position is None:
                    return f"{session_day.strftime('%A').upper()} BUY WINDOW", candidate.isoformat()
                if not self.oh_check_eligible(session_day):
                    continue
                return "OH", candidate.isoformat()
        except Exception:
            pass
        return "WAIT", ""

    def monitor_all_conditions(
        self,
        position,
        now: datetime,
        trade_bid: float,
        signal_price: float,
        break_even_check: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        if position is None or trade_bid <= 0:
            return []
        entry = float(position.price_open)
        if entry <= 0:
            return []

        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        tolerance = tick_size * 1.5
        conditions: list[dict[str, Any]] = []

        def add(
            name: str,
            target: float,
            current: float,
            source: str,
            active: bool = True,
            potential_tp_percent: Optional[float] = None,
        ) -> None:
            if not name or target <= 0 or current <= 0:
                return
            if any(item["name"] == name and abs(float(item["targetPrice"]) - target) <= tolerance for item in conditions):
                return
            difference = target - current
            distance = abs(difference)
            conditions.append({
                "name": name,
                "targetPrice": target,
                "currentPrice": current,
                "distancePoints": distance,
                "distancePercent": distance / current * 100.0,
                "direction": "at" if abs(difference) <= tolerance else "above" if difference > 0 else "below",
                "active": bool(active),
                "source": source,
                "potentialTpPercent": float(potential_tp_percent) if potential_tp_percent is not None else None,
            })

        desired_sl, sl_reason = self.weekday_sl_target(position, now)
        add(sl_reason, ceil_step(ceil_whole_sl(desired_sl), tick_size), trade_bid, self.cfg.trade_symbol)
        state_matches = self.position_state_matches(position)
        if float(position.sl) > 0:
            add((self.state.active_sl_reason if state_matches else "") or "BROKER_SL", float(position.sl), trade_bid, self.cfg.trade_symbol)

        tpp = self.tpp_for_day(now.date())
        if self.oh_check_pending(now, position):
            add("OH", ceil_step(entry * (1.0 + tpp), tick_size), trade_bid, self.cfg.trade_symbol)
        premarket_tpp = self.premarket_high_tpp(position, now)
        if premarket_tpp is not None and now < self.session_times(now.date()).cash_open:
            add(
                "PRE H",
                ceil_step(entry * (1.0 + premarket_tpp), tick_size),
                trade_bid,
                self.cfg.trade_symbol,
                potential_tp_percent=premarket_tpp * 100.0,
            )

        # The mobile dashboard displays OH and CH against the same trade-entry
        # target. On Friday both are exactly entry * 1.05. This is presentation
        # metadata only; the production CH execution rule is unchanged.
        if signal_price > 0:
            add("CH", ceil_step(entry * (1.0 + tpp), tick_size), signal_price, self.cfg.signal_symbol)

        break_even_armed = bool(self.state.break_even) if state_matches else False
        if not break_even_armed and break_even_check is not None:
            check_status = str(break_even_check.get("status", "")).upper()
            check_threshold = float(break_even_check.get("threshold", 0.0) or 0.0)
            if check_status in {"SCHEDULED", "DUE"}:
                add("BE CHECK", check_threshold, signal_price, self.cfg.signal_symbol)

        if break_even_armed:
            add("BE", ceil_step(entry * self.cfg.break_even_ratio, tick_size), trade_bid, self.cfg.trade_symbol)

        return sorted(conditions, key=lambda item: float(item["distancePoints"]))

    @staticmethod
    def monitor_closest_condition(conditions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return conditions[0] if conditions else None

    def monitor_position_exposure(self, position, deposit: float, account=None) -> float:
        return deposit * float(self.cfg.sizing_multiplier) if position is not None and deposit > 0 else 0.0

    def last_closed_trade_payload(self, refresh: bool = True) -> Optional[dict[str, Any]]:
        record = self.latest_closed_trade_record() if refresh and not self.is_weekend(datetime.now(self.tz)) else self.cached_mysql_trade_record
        if record is not None:
            value = float(record["change"])
            reason = str(record.get("exitReason") or self.state.last_exit_reason)
            return {
                "positionIdentifier": int(record.get("positionIdentifier") or 0),
                "closedAt": str(record.get("closedAt") or ""),
                "exitReason": reason,
                "preleverageReturn": value,
                "preleverageReturnPercent": value * 100.0,
                "tradeClass": str(record.get("tradeClass") or self.trade_class(value, reason)),
                "returnSource": str(record.get("source") or "MySQL strategy_trades"),
            }
        if not (self.state.last_exit_time or self.state.last_exit_trade_class or self.state.last_exit_position_identifier):
            return None
        value = float(self.state.last_exit_preleverage_return or self.state.prev_change)
        trade_class = self.state.last_exit_trade_class or self.trade_class(value, self.state.last_exit_reason)
        return {
            "positionIdentifier": int(self.state.last_exit_position_identifier),
            "closedAt": self.state.last_exit_time,
            "exitReason": self.state.last_exit_reason,
            "preleverageReturn": value,
            "preleverageReturnPercent": value * 100.0,
            "tradeClass": trade_class,
            "returnSource": "strategy state fallback",
        }

    def snapshot_strategy_decision(self, position, preview: dict[str, Any]) -> Optional[dict[str, Any]]:
        if self.last_strategy_decision_payload is not None:
            return self.last_strategy_decision_payload
        if position is None:
            return self.record_strategy_decision_if_changed(preview=preview)
        return None

    def immutable_hard_stop_payload(self, position) -> dict[str, Any]:
        if not self.immutable_hard_stop_matches(position):
            return {
                "positionIdentifier": 0, "price": 0.0, "entryPrice": 0.0, "volume": 0.0,
                "balanceAtFill": 0.0, "leverage": 0, "profitAtStop": 0.0,
                "accountCurrency": "", "accountValuePerPriceUnit": 0.0, "tickSize": 0.0,
                "accountLossCapApplied": False, "lockedAt": "", "source": "",
            }
        return {
            "positionIdentifier": int(self.state.immutable_hard_sl_position_identifier or 0),
            "price": float(self.state.immutable_hard_sl_price or 0.0),
            "entryPrice": float(self.state.immutable_hard_sl_entry_price or 0.0),
            "volume": float(self.state.immutable_hard_sl_volume or 0.0),
            "balanceAtFill": float(self.state.immutable_hard_sl_balance or 0.0),
            "leverage": int(self.state.immutable_hard_sl_leverage or 0),
            "profitAtStop": float(self.state.immutable_hard_sl_profit or 0.0),
            "accountCurrency": self.state.immutable_hard_sl_account_currency,
            "accountValuePerPriceUnit": float(self.state.immutable_hard_sl_value_per_price_unit or 0.0),
            "tickSize": float(self.state.immutable_hard_sl_tick_size or 0.0),
            "accountLossCapApplied": bool(self.state.immutable_hard_sl_account_loss_cap_applied),
            "lockedAt": self.state.immutable_hard_sl_locked_at,
            "source": self.state.immutable_hard_sl_source,
        }

    def protection_target_payload(self, position, now: datetime) -> dict[str, Any]:
        broker_sl = float(getattr(position, "sl", 0.0) or 0.0)
        if broker_sl > 0:
            reason = self.state.active_sl_reason if self.position_state_matches(position) else ""
            return {
                "price": broker_sl, "applied": True, "reason": reason or "BROKER_SL",
                "source": "BROKER_SL", "executorRequired": False,
            }
        target, reason = self.weekday_sl_target(position, now)
        return {
            "price": float(target or 0.0),
            "applied": False,
            "reason": reason,
            "source": "IMMUTABLE_HARD_STOP" if self.immutable_hard_stop_matches(position) else "PENDING_EXECUTOR_HARD_STOP",
            "executorRequired": True,
        }

    def build_mobile_snapshot(self, position, now: datetime, current_bar: Optional[M1Bar], potential_position: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        account = mt5.account_info()
        balance = float(getattr(account, "balance", 0.0)) if account is not None else 0.0
        equity = float(getattr(account, "equity", 0.0)) if account is not None else 0.0
        currency = str(getattr(account, "currency", "")).strip() if account is not None else ""
        account_login = str(getattr(account, "login", self.cfg.login or "")) if account is not None else str(self.cfg.login or "")

        trade_bid, trade_ask, trade_age, trade_time = self.monitor_tick_snapshot(self.cfg.trade_symbol, now)
        if self.cfg.signal_symbol == self.cfg.trade_symbol:
            signal_bid, signal_ask, signal_age, signal_time = trade_bid, trade_ask, trade_age, trade_time
        else:
            signal_bid, signal_ask, signal_age, signal_time = self.monitor_tick_snapshot(self.cfg.signal_symbol, now)
        signal_price = signal_bid if signal_bid > 0 else signal_ask
        current_week_bar = self.current_week_market_bar(self.cfg.trade_symbol, now, position)

        stale = any(age is None or age > self.cfg.maximum_tick_age_seconds for age in (trade_age, signal_age))
        connected = self.connected and account is not None
        health = "CRITICAL" if not connected else "WARNING" if stale else "OK"
        next_action, next_action_at = self.monitor_next_action(position, now)
        phase = f"{now:%A} {self.phase(now).replace('_', ' ').title()}"
        regime = self.protection_regime(now, position) if position is not None else "None"

        position_payload: Optional[dict[str, Any]] = None
        conditions: list[dict[str, Any]] = []
        closest = None
        deposit = 0.0
        if position is not None:
            state_matches = self.position_state_matches(position)
            bid = trade_bid if trade_bid > 0 else float(getattr(position, "price_current", 0.0) or 0.0)
            ask = trade_ask
            entry = float(position.price_open)
            # The broker-reported account margin is the authoritative used
            # deposit for the live position. Recalculating order margin at the
            # current quote makes the displayed deposit drift with price even
            # though the position's opening margin is already locked by MT5.
            deposit = max(0.0, float(getattr(account, "margin", 0.0) or 0.0)) if account is not None else 0.0
            broker_leverage = self.broker_margin_leverage(account)
            raw_change = bid / entry - 1.0 if bid > 0 and entry > 0 else 0.0
            leverage = self.state.entry_leverage if state_matches and self.state.entry_leverage else self.infer_position_leverage(position)
            profit = float(getattr(position, "profit", 0.0)) + float(getattr(position, "swap", 0.0))
            timestamp = getattr(position, "time_msc", 0) / 1000.0 if getattr(position, "time_msc", 0) else float(position.time)
            opened = self.mt5_timestamp_to_local(timestamp)
            signal_capture_at = self.session_times(opened.date()).cash_open
            exposure = self.monitor_position_exposure(position, deposit, account)
            info = mt5.symbol_info(position.symbol)
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
            potential_take_profit = ceil_step(entry * (1.0 + self.tpp_for_day(now.date())), tick_size)
            break_even_check = self.break_even_check_payload(position, now)
            signal_reference = float(break_even_check.get("signalReference", 0.0) or 0.0)
            signal_pending = signal_reference <= 0
            position_payload = {
                "open": True,
                "symbol": str(position.symbol),
                "side": "BUY",
                "volume": float(position.volume),
                "ticket": int(position.ticket),
                "openedAt": opened.isoformat(),
                "manual": self.is_manual_position(position),
                "openPrice": entry,
                "bid": bid,
                "ask": ask,
                "priceTime": trade_time,
                "bidAt": trade_time,
                "askAt": trade_time,
                "tickAgeSeconds": trade_age,
                "profit": profit,
                "profitPercent": raw_change * 100.0,
                "strategyLeverage": float(leverage),
                "leveragedProfitPercent": raw_change * leverage * 100.0,
                "exposure": exposure,
                "requiredDeposit": deposit,
                "depositPrice": entry,
                "depositSource": "MT5 account_info().margin (broker-reported used margin)",
                "brokerMarginLeverage": broker_leverage,
                "effectiveLeverage": exposure / balance if balance > 0 else 0.0,
                "stopLoss": float(position.sl),
                "takeProfit": float(position.tp),
                "potentialTakeProfit": potential_take_profit,
                "entrySignalOpen": signal_reference,
                "entrySignalOpenPending": signal_pending,
                "entrySignalCaptureAt": signal_capture_at.isoformat(),
                "entrySignalReferenceSource": (
                    "CASH_OPEN_M1" if signal_reference > 0 and not signal_pending
                    else "PENDING_CASH_OPEN_M1"
                ),
                "breakEvenArmed": bool(self.state.break_even) if state_matches else False,
                "breakEvenCheck": break_even_check,
                "protectionRegime": regime,
                "activeSlReason": self.state.active_sl_reason if state_matches else "",
                "activeTpReason": self.state.active_tp_reason if state_matches else "",
                "immutableHardStop": self.immutable_hard_stop_payload(position),
                "protectionTarget": self.protection_target_payload(position, now),
            }
            conditions = self.monitor_all_conditions(position, now, bid, signal_price, break_even_check)
            closest = self.monitor_closest_condition(conditions)

        current_price = trade_bid if trade_bid > 0 else trade_ask
        profit = float(position_payload["profit"]) if position_payload is not None else 0.0
        profit_percent = float(position_payload["profitPercent"]) if position_payload is not None else 0.0
        leveraged_profit_percent = float(position_payload["leveragedProfitPercent"]) if position_payload is not None else 0.0
        strategy_leverage = float(position_payload["strategyLeverage"]) if position_payload is not None else float(self.choose_leverage())
        current_bar_payload = None if current_bar is None else {
            "time": current_bar.local_datetime.isoformat(),
            "open": current_bar.open,
            "high": current_bar.high,
            "low": current_bar.low,
            "close": current_bar.close,
        }
        current_week_bar_payload = None if current_week_bar is None else {
            "time": current_week_bar.local_datetime.isoformat(),
            "open": current_week_bar.open,
            "high": current_week_bar.high,
            "low": current_week_bar.low,
            "close": current_week_bar.close,
            "source": "MT5_M1_WINDOW",
        }

        preview = potential_position or self.potential_position_preview(assume_current_position_closed=position is not None)

        return {
            "connection": {
                "connected": connected,
                "instanceRole": self.role,
                "backendPublisher": self.monitor_publisher.allowed_to_publish(),
                "lastSync": now.isoformat(),
                "accountId": account_login,
                "week": iso_week_key(now.date()),
                "health": health,
                "phase": phase,
                "regime": regime,
                "nextAction": next_action,
                "nextActionAt": next_action_at,
                "us100AgeSeconds": trade_age,
                "qqqAgeSeconds": signal_age,
            },
            "account": {
                "currency": currency,
                "strategyCapital": balance,
                "deposit": deposit,
                "balance": balance,
                "equity": equity,
            },
            "market": {
                "symbol": self.cfg.trade_symbol,
                "currentPrice": current_price,
                "bid": trade_bid,
                "ask": trade_ask,
                "priceTime": trade_time,
                "tickAgeSeconds": trade_age,
                "signalSymbol": self.cfg.signal_symbol,
                "signalPrice": signal_price,
                "signalPriceTime": signal_time,
                "currentM1": current_bar_payload,
                "currentW1": current_week_bar_payload,
                "session": self.market_session_payload(now, current_week_bar),
            },
            "metrics": {
                "currentPrice": current_price,
                "currentProfit": profit,
                "currentProfitPercent": profit_percent,
                "currentLeveragedProfitPercent": leveraged_profit_percent,
                "equity": equity,
                "balance": balance,
                "deposit": deposit,
                "strategyLeverage": strategy_leverage,
                "currency": currency,
            },
            "position": position_payload,
            "potentialPosition": preview,
            "strategyDecision": self.snapshot_strategy_decision(position, preview),
            "strategySpecification": self.strategy_specification,
            "lastClosedTrade": self.last_closed_trade_payload(),
            "execution": self.execution_snapshot(),
            "conditions": conditions,
            "closestCondition": closest,
            "equityHistory": [],
        }

    def publish_mobile_minute_status(self, position, now: datetime, current_bar: Optional[M1Bar], force: bool = False) -> bool:
        if self.is_weekend(now):
            return False
        if not self.monitor_publisher.ready:
            return False
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if not force and minute_key == self.last_monitor_minute_key:
            return False
        self.last_monitor_minute_key = minute_key
        try:
            snapshot = self.build_mobile_snapshot(position, now, current_bar)
            snapshot["statusUpdate"] = {
                "kind": "MINUTE",
                "minute": minute_key,
                "generatedAt": now.isoformat(),
                "build": BUILD_ID,
            }
            self.monitor_publisher.submit_snapshot(snapshot, guaranteed=True)
            self.last_monitor_publish_monotonic = time_module.monotonic()
            self.log.info(
                "EVENT MONITOR_MINUTE_STATUS_QUEUED minute=%s current_price=%.5f profit=%.2f profit_percent=%.6f leveraged_profit_percent=%.6f equity=%.2f balance=%.2f deposit=%.2f",
                minute_key,
                float(snapshot["metrics"]["currentPrice"]),
                float(snapshot["metrics"]["currentProfit"]),
                float(snapshot["metrics"]["currentProfitPercent"]),
                float(snapshot["metrics"]["currentLeveragedProfitPercent"]),
                float(snapshot["metrics"]["equity"]),
                float(snapshot["metrics"]["balance"]),
                float(snapshot["metrics"]["deposit"]),
                extra={"skip_mobile_publish": True},
            )
            return True
        except Exception as exc:
            self.log.warning("EVENT MONITOR_MINUTE_STATUS_FAILED error=%s", exc, extra={"skip_mobile_publish": True})
            return False

    def publish_mobile_if_due(self, position, now: datetime, current_bar: Optional[M1Bar], force: bool = False) -> None:
        if self.is_weekend(now):
            return
        if not self.monitor_publisher.ready:
            return
        monotonic = time_module.monotonic()
        if not force and monotonic - self.last_monitor_publish_monotonic < self.cfg.monitor_publish_interval_seconds:
            return
        self.last_monitor_publish_monotonic = monotonic
        try:
            self.monitor_publisher.submit_snapshot(self.build_mobile_snapshot(position, now, current_bar))
        except Exception as exc:
            self.log.warning("EVENT MONITOR_SNAPSHOT_FAILED error=%s", exc, extra={"skip_mobile_publish": True})

    def shutdown_mobile_publisher(self) -> None:
        try:
            self.monitor_publisher.stop()
        except Exception as exc:
            self.log.warning("EVENT MONITOR_SHUTDOWN_FAILED error=%s", exc, extra={"skip_mobile_publish": True})

    def execution_stage(self, stage: str, *, result: Optional[bool] = True, position_ticket: int = 0, reference_price: float = 0.0,
                         actual_price: float = 0.0, retcode: Optional[int] = None, filling_mode: str = "", reason: str = "",
                         scheduled_at: str = "", latency_ms: Optional[float] = None,
                         order_ticket: int = 0, deal_ticket: int = 0, side: str = "", volume: float = 0.0,
                         old_sl: float = 0.0, new_sl: float = 0.0, old_tp: float = 0.0, new_tp: float = 0.0,
                         event_at: str = "") -> None:
        execution_id = self.state.active_execution_id
        if not execution_id:
            execution_id = uuid.uuid4().hex
            self.state.active_execution_id = execution_id
        decision_id = self.state.active_decision_id or str((self.last_strategy_decision_payload or {}).get("decisionId", ""))
        now = event_at or datetime.now(UTC).isoformat()
        fields = {
            "execution_id": execution_id, "decision_id": decision_id, "position_ticket": int(position_ticket or self.state.active_position_ticket or 0),
            "stage": stage, "event_at": now, "scheduled_at": scheduled_at or self.state.execution_scheduled_at,
            "reference_price": float(reference_price or 0.0), "actual_price": float(actual_price or 0.0),
            "retcode": retcode, "filling_mode": filling_mode, "reason": reason, "latency_ms": latency_ms, "result": result,
            "order_ticket": int(order_ticket or 0), "deal_ticket": int(deal_ticket or 0),
            "side": side, "volume": float(volume or 0.0),
            "old_sl": float(old_sl or 0.0), "new_sl": float(new_sl or 0.0),
            "old_tp": float(old_tp or 0.0), "new_tp": float(new_tp or 0.0),
            "strategy_spec_id": self.state.active_strategy_spec_id or self.strategy_specification["specId"],
            "strategy_spec_hash": self.state.active_strategy_spec_hash or self.strategy_specification["specHash"],
        }
        result_token = "none" if result is None else str(bool(result)).lower()
        tokens = [f"execution_id={execution_id}", f"decision_id={decision_id or 'none'}", f"stage={stage}", f"result={result_token}", f"position_ticket={fields['position_ticket']}",
                  f"event_at={now}", f"scheduled_at={fields['scheduled_at'] or 'none'}", f"reference_price={fields['reference_price']:.8f}",
                  f"actual_price={fields['actual_price']:.8f}", f"retcode={retcode if retcode is not None else 'none'}",
                  f"filling_mode={filling_mode or 'none'}", f"reason={reason or 'none'}", f"latency_ms={latency_ms if latency_ms is not None else 'none'}",
                  f"order_ticket={fields['order_ticket']}", f"deal_ticket={fields['deal_ticket']}", f"side={side or 'none'}", f"volume={fields['volume']:.8f}",
                  f"old_sl={fields['old_sl']:.8f}", f"new_sl={fields['new_sl']:.8f}", f"old_tp={fields['old_tp']:.8f}", f"new_tp={fields['new_tp']:.8f}",
                  f"strategy_spec_id={fields['strategy_spec_id']}", f"strategy_spec_hash={fields['strategy_spec_hash']}"]
        level = logging.INFO if result is not False else logging.ERROR
        self.log.log(level, "EVENT EXECUTION_STAGE " + " ".join(tokens))

    def execution_snapshot(self) -> dict[str, Any]:
        return {
            "executionId": self.state.active_execution_id, "decisionId": self.state.active_decision_id,
            "strategySpecId": self.state.active_strategy_spec_id or self.strategy_specification["specId"],
            "strategySpecHash": self.state.active_strategy_spec_hash or self.strategy_specification["specHash"],
            "positionTicket": int(self.state.active_position_ticket or 0), "scheduledAt": self.state.execution_scheduled_at,
            "startedAt": self.state.execution_started_at,
        }
