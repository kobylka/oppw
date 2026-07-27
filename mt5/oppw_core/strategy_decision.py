"""Strategy decision behavior for the canonical strategy composition."""

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


class StrategyDecisionMixin:
    def phase(self, now: datetime) -> str:
        if now.weekday() >= 5:
            return "WEEKEND"
        session = self.session_times(now.date())
        if now < session.cash_open:
            return "PREMARKET"
        if now < session.close_processing:
            return "REGULAR"
        return "AFTER_CLOSE"

    def protection_regime(self, now: datetime, position=None) -> str:
        state_matches = position is None or self.position_state_matches(position)
        if state_matches and self.state.exit_latched_reason:
            return f"Closing position: {self.state.exit_latched_reason}"
        break_even = bool(self.state.break_even) if state_matches else False
        active_sl_reason = self.state.active_sl_reason if state_matches else ""
        if now.weekday() in (3, 4, 5, 6) or active_sl_reason == "TSL":
            return "Tight stop loss (0.4%)" + (" + break-even exit" if break_even else "")
        return "Hard stop loss + break-even exit" if break_even else "Hard stop loss"

    def oh_check_pending(self, now: datetime, position=None) -> bool:
        session = self.session_times(now.date())
        state_matches = position is None or self.position_state_matches(position)
        return (
            self.oh_check_eligible(now.date())
            and (not state_matches or self.state.last_open_action_date != now.date().isoformat())
            and now < session.cash_open
        )

    def weekly_exit_status(self, position, now: datetime) -> tuple[bool, str, Optional[date]]:
        final_day = self.final_trading_day(now.date())
        if position is None or final_day is None:
            return False, "WAIT", final_day
        if now.date() > final_day:
            return True, "OVERDUE_TO", final_day
        if now.date() == final_day and now >= self.session_times(final_day).weekly_close:
            return True, "TO", final_day
        return False, "WAIT", final_day

    def closest_price_condition(self, position, now: datetime, bid: float) -> str:
        if position is None or bid <= 0:
            return "none"
        entry = float(position.price_open)
        if entry <= 0:
            return "none"

        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        tolerance = tick_size * 1.5
        candidates: list[tuple[str, float]] = []

        def add(name: str, price: float) -> None:
            if not name or price <= 0:
                return
            if any(existing_name == name and abs(existing_price - price) <= tolerance for existing_name, existing_price in candidates):
                return
            candidates.append((name, price))

        add("SL", self.hard_sl_price(position))
        weekday_price, weekday_reason = self.weekday_sl_target(position, now)
        if weekday_reason != "SL":
            add(weekday_reason, ceil_step(ceil_whole_sl(weekday_price), tick_size))
        state_matches = self.position_state_matches(position)
        if float(position.sl) > 0:
            add((self.state.active_sl_reason if state_matches else "") or "BROKER_SL", float(position.sl))
        if state_matches and self.state.break_even:
            add(self.state.active_tp_reason or "BH", ceil_step(entry * self.cfg.break_even_ratio, tick_size))
        if float(position.tp) > 0:
            add((self.state.active_tp_reason if state_matches else "") or "BROKER_TP", float(position.tp))
        if self.oh_check_pending(now, position):
            add("OH", ceil_step(entry * (1.0 + self.tpp_for_day(now.date())), tick_size))
        premarket_tpp = self.premarket_high_tpp(position, now)
        if premarket_tpp is not None and now < self.session_times(now.date()).cash_open:
            add("PRE H", ceil_step(entry * (1.0 + premarket_tpp), tick_size))

        if not candidates:
            return "none"
        name, price = min(candidates, key=lambda item: abs(item[1] - bid))
        difference = price - bid
        distance = abs(difference)
        distance_pct = distance / bid * 100.0
        direction = "at current price" if abs(difference) <= tolerance else "above" if difference > 0 else "below"
        return f"{name} @ {price:.5f} â€” {distance:.5f} points {direction} ({distance_pct:.4f}%)"

    def m1_bar_near(self, symbol: str, local_day: date, target_time: time, before_minutes: int = 5, after_minutes: int = 0) -> Optional[M1Bar]:
        target_local = datetime.combine(local_day, target_time, self.tz)
        start_local = target_local - timedelta(minutes=max(0, before_minutes))
        end_local = target_local + timedelta(minutes=max(0, after_minutes), seconds=59)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, self.local_to_mt5_bar_query_time(start_local), self.local_to_mt5_bar_query_time(end_local))
        if rates is None or len(rates) == 0:
            return None
        candidates: list[M1Bar] = []
        for row in rates:
            raw_ts = int(row["time"])
            local_dt = self.mt5_bar_timestamp_to_local(raw_ts)
            if local_dt.date() != local_day:
                continue
            candidates.append(M1Bar(raw_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])))
        if not candidates:
            return None
        not_after = [bar for bar in candidates if bar.local_datetime <= target_local]
        return max(not_after, key=lambda bar: bar.local_datetime) if not_after else min(candidates, key=lambda bar: abs((bar.local_datetime - target_local).total_seconds()))

    def latest_completed_week_change(self, now: Optional[datetime] = None) -> Optional[float]:
        now = now or datetime.now(self.tz)
        current_monday = now.date() - timedelta(days=now.date().weekday())
        for monday in (current_monday, current_monday - timedelta(days=7)):
            friday = monday + timedelta(days=4)
            sessions = self.calendar.sessions_in_range(monday.isoformat(), friday.isoformat())
            session_days = [session.date() for session in sessions]
            if not session_days:
                continue
            first_day, last_day = session_days[0], session_days[-1]
            if now < self.session_times(last_day).close_processing:
                continue
            open_time = self.session_times(first_day).cash_open.time().replace(second=0, microsecond=0)
            close_time = self.session_times(last_day).close_bar_open.time().replace(second=0, microsecond=0)
            open_bar = self.m1_bar_near(self.cfg.trade_symbol, first_day, open_time, before_minutes=5)
            close_bar = self.m1_bar_near(self.cfg.trade_symbol, last_day, close_time, before_minutes=5)
            if open_bar is not None and close_bar is not None and open_bar.open > 0:
                return close_bar.close / open_bar.open - 1.0
        return None

    def backend_trade_history_urls(self) -> list[str]:
        """Return the single canonical MySQL trade-history endpoint."""
        configured = str(getattr(self.cfg, "monitor_trade_history_url", "") or "").strip()
        if configured:
            return [configured]
        ingest_url = str(getattr(self.cfg, "monitor_ingest_url", "") or "").strip()
        if not ingest_url:
            return []
        base = ingest_url.rsplit("/", 1)[0]
        return [f"{base}/{str(self.cfg.backend_latest_trade_path).lstrip('/')}"]

    def backend_trade_history_url(self) -> str:
        urls = self.backend_trade_history_urls()
        return urls[0] if urls else ""

    @staticmethod
    def mysql_datetime_to_local(value: str, timezone: ZoneInfo) -> str:
        if not value:
            return ""
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(timezone).isoformat()
        except ValueError:
            return value

    def latest_closed_trade_record(self, force: bool = False) -> Optional[dict[str, Any]]:
        """Read the latest completed strategy trade from MySQL via HTTPS.

        MT5 deal/order history is deliberately never queried in v45.
        """
        # A weekend startup is allowed one forced MySQL read so the new
        # What-if ticket and Last publisher-labeled trade use authoritative
        # metadata. All non-forced weekend calls remain cache-only.
        if self.is_weekend(datetime.now(self.tz)) and not force:
            return self.cached_mysql_trade_record
        now_monotonic = time_module.monotonic()
        if not force and now_monotonic - self.last_mysql_trade_refresh_monotonic < float(self.cfg.mysql_trade_refresh_seconds):
            return self.cached_mysql_trade_record
        self.last_mysql_trade_refresh_monotonic = now_monotonic

        urls = self.backend_trade_history_urls()
        token = str(getattr(self.cfg, "monitor_write_token", "") or "").strip()
        account_key = str(getattr(self.cfg, "monitor_account_key", "") or "").strip()
        if not urls or not token or not account_key:
            self.cached_mysql_trade_record = None
            return None

        timeout = float(getattr(self.cfg, "monitor_timeout_seconds", 10.0) or 10.0)
        errors: list[str] = []
        for url in urls:
            separator = "&" if "?" in url else "?"
            request_url = f"{url}{separator}{urllib.parse.urlencode({'accountKey': account_key})}"
            request = urllib.request.Request(
                request_url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "User-Agent": f"OPPW-MT5-History/{BUILD_ID}",
                },
            )
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    if int(response.status) != 200:
                        raise RuntimeError(f"HTTP {response.status}")
                    payload = json.loads(response.read().decode("utf-8"))
                trade = payload.get("trade") if isinstance(payload, dict) else None
                if not isinstance(trade, dict):
                    self.cached_mysql_trade_record = None
                    return None

                entry_price = float(trade.get("openPrice") or 0.0)
                exit_price = float(trade.get("closePrice") or 0.0)
                raw_return = trade.get("preleverageReturn")
                if raw_return is None and entry_price > 0 and exit_price > 0:
                    raw_return = exit_price / entry_price - 1.0
                if raw_return is None:
                    raise RuntimeError("response did not contain a usable pre-leverage return")
                change = float(raw_return)
                trade_class = str(trade.get("tradeClass") or "").strip().upper()
                if trade_class not in {"A", "B", "C", "D"}:
                    trade_class = ""
                record = {
                    "change": change,
                    "positionIdentifier": int(trade.get("positionTicket") or 0),
                    "closedAt": self.mysql_datetime_to_local(str(trade.get("closedAt") or ""), self.tz),
                    "exitPrice": exit_price,
                    "entryPrice": entry_price,
                    "exitReason": str(trade.get("exitReason") or "").strip(),
                    "exitReasonSource": str(trade.get("exitReasonSource") or ""),
                    "tradeClass": trade_class,
                    "tradeClassSource": str(trade.get("tradeClassSource") or ""),
                    "source": "MySQL strategy_trades",
                    "endpoint": url,
                }
                self.cached_mysql_trade_record = record
                self.log.info(
                    "EVENT MYSQL_TRADE_HISTORY_LOADED position_identifier=%s previous_trade=%.8f "
                    "exit_reason=%s trade_class=%s reason_source=%s class_source=%s endpoint=%s",
                    record["positionIdentifier"], change, record["exitReason"] or "-", record["tradeClass"] or "-",
                    record["exitReasonSource"] or "-", record["tradeClassSource"] or "-", url,
                    extra={"skip_mobile_publish": True},
                )
                return record
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        if now_monotonic - self.last_mysql_trade_error_monotonic >= float(self.cfg.mysql_trade_error_log_interval_seconds):
            self.last_mysql_trade_error_monotonic = now_monotonic
            self.log.warning(
                "EVENT MYSQL_TRADE_HISTORY_READ_FAILED errors=%s",
                " | ".join(errors), extra={"skip_mobile_publish": True},
            )
        return self.cached_mysql_trade_record

    def resolved_leverage_inputs(self, force: bool = False) -> tuple[float, float, str, str]:
        state_signature = (
            self.state.last_exit_time,
            int(self.state.last_exit_position_identifier),
            round(float(self.state.last_exit_preleverage_return), 10),
            round(float(self.state.prev_change), 10),
            round(float(self.state.prev_full_week_change), 10),
        )
        now_monotonic = time_module.monotonic()
        state_changed = state_signature != self.last_leverage_state_signature
        if not force and not state_changed and now_monotonic - self.last_leverage_inputs_refresh_monotonic < float(self.cfg.leverage_inputs_refresh_seconds):
            return self.cached_previous_full_week_change, self.cached_previous_trade_change, self.cached_previous_full_week_source, self.cached_previous_trade_source
        self.last_leverage_inputs_refresh_monotonic = now_monotonic
        self.last_leverage_state_signature = state_signature

        full_week = self.latest_completed_week_change()
        database_record = self.latest_closed_trade_record(force=force)
        self.cached_previous_full_week_change = float(full_week) if full_week is not None else float(self.state.prev_full_week_change)
        self.cached_previous_full_week_source = "market history" if full_week is not None else "state fallback"

        labeled_return = float(self.state.last_exit_preleverage_return)
        legacy_return = float(self.state.prev_change)
        database_used = database_record is not None
        if database_record is not None:
            self.cached_previous_trade_change = float(database_record["change"])
            self.cached_previous_trade_source = str(database_record["source"])
        elif abs(labeled_return) > 1e-12:
            self.cached_previous_trade_change = labeled_return
            self.cached_previous_trade_source = "publisher-labeled strategy state"
        else:
            self.cached_previous_trade_change = legacy_return
            self.cached_previous_trade_source = "state fallback"

        state_changed_for_save = (
            abs(self.state.prev_full_week_change - self.cached_previous_full_week_change) > 1e-12
            or abs(self.state.prev_change - self.cached_previous_trade_change) > 1e-12
        )
        self.state.prev_full_week_change = self.cached_previous_full_week_change
        self.state.prev_change = self.cached_previous_trade_change

        if database_record is not None:
            updates = {
                "last_exit_position_identifier": int(database_record["positionIdentifier"]),
                "last_exit_time": str(database_record["closedAt"]),
                "last_exit_price": float(database_record["exitPrice"]),
                "last_exit_preleverage_return": self.cached_previous_trade_change,
                "last_exit_reason": str(database_record.get("exitReason") or self.state.last_exit_reason),
                "last_exit_trade_class": str(database_record.get("tradeClass") or self.trade_class(self.cached_previous_trade_change, str(database_record.get("exitReason") or self.state.last_exit_reason))),
            }
            for field_name, value in updates.items():
                if getattr(self.state, field_name) != value:
                    setattr(self.state, field_name, value)
                    state_changed_for_save = True

        # Publisher remains strictly read-only; only executor persists MySQL-confirmed inputs.
        if self.is_executor and state_changed_for_save:
            self.state.save(self.cfg.state_file)
            event_name = "PREVIOUS_TRADE_STATE_REPAIRED" if database_used else "LEVERAGE_INPUTS_RECOVERED"
            self.log.info(
                "EVENT %s previous_full_week_change=%.6f full_week_source=%s previous_trade_change=%.6f trade_source=%s position_identifier=%s",
                event_name, self.cached_previous_full_week_change, self.cached_previous_full_week_source.replace(" ", "_"),
                self.cached_previous_trade_change, self.cached_previous_trade_source.replace(" ", "_"),
                int(database_record["positionIdentifier"]) if database_record is not None else int(self.state.last_exit_position_identifier or 0),
            )
        return self.cached_previous_full_week_change, self.cached_previous_trade_change, self.cached_previous_full_week_source, self.cached_previous_trade_source

    def leverage_decision(self) -> tuple[int, str]:
        previous_full_week, previous_trade, full_week_source, trade_source = self.resolved_leverage_inputs()
        if self.cfg.base_leverage == 8:
            triggers: list[str] = []
            if previous_full_week < float(self.cfg.full_week_loss_trigger):
                triggers.append(f"previous full-week change {previous_full_week:.4%} ({full_week_source}) < {float(self.cfg.full_week_loss_trigger):.4%}")
            if previous_trade < float(self.cfg.previous_trade_loss_trigger):
                triggers.append(f"previous trade change {previous_trade:.4%} ({trade_source}) < {float(self.cfg.previous_trade_loss_trigger):.4%}")
            if triggers:
                return self.cfg.loss_leverage, f"{self.cfg.loss_leverage}x because " + " and ".join(triggers)
            return self.cfg.base_leverage, f"{self.cfg.base_leverage}x because previous full-week change {previous_full_week:.4%} ({full_week_source}) >= {float(self.cfg.full_week_loss_trigger):.4%} and previous trade change {previous_trade:.4%} ({trade_source}) >= {float(self.cfg.previous_trade_loss_trigger):.4%}"
        return self.cfg.base_leverage, f"{self.cfg.base_leverage}x because base leverage is configured as {self.cfg.base_leverage}x"

    def broker_margin_leverage(self, account) -> float:
        value = float(getattr(account, "leverage", 0.0) or 0.0) if account is not None else 0.0
        return value if value > 0 else float(self.cfg.broker_margin_leverage_fallback)

    def position_required_deposit(self, position, current_price: float) -> float:
        if position is None:
            return 0.0
        volume = float(getattr(position, "volume", 0.0) or 0.0)
        symbol = str(getattr(position, "symbol", "") or self.cfg.trade_symbol)
        price = float(current_price or getattr(position, "price_current", 0.0) or 0.0)
        if volume <= 0 or price <= 0:
            return 0.0
        position_type = int(getattr(position, "type", mt5.POSITION_TYPE_BUY))
        order_type = mt5.ORDER_TYPE_SELL if position_type == int(mt5.POSITION_TYPE_SELL) else mt5.ORDER_TYPE_BUY
        margin = mt5.order_calc_margin(order_type, symbol, volume, price)
        if margin is None:
            raise RuntimeError(f"order_calc_margin failed for open position: {mt5.last_error()}")
        return float(margin)

    def capped_hard_stop(self, symbol: str, volume: float, entry_price: float, balance: float, leverage: int, tick_size: float) -> tuple[float, float, bool]:
        requested_price = ceil_step(ceil_whole_sl(entry_price * self.hard_sl_ratio(leverage)), tick_size)
        requested_profit_raw = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, entry_price, requested_price)
        if requested_profit_raw is None:
            raise RuntimeError(f"order_calc_profit failed for hard stop: {mt5.last_error()}")
        requested_profit = float(requested_profit_raw)
        if not self.account_loss_cap_enabled():
            return requested_price, requested_profit, False

        maximum_loss = -float(self.cfg.max_account_stop_loss_fraction) * max(0.0, balance)
        if balance <= 0 or requested_profit >= maximum_loss - 1e-8:
            return requested_price, requested_profit, False

        low = requested_price
        high = entry_price
        for _ in range(80):
            middle = (low + high) / 2.0
            profit_raw = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, entry_price, middle)
            if profit_raw is None:
                raise RuntimeError(f"order_calc_profit failed while applying account-loss cap: {mt5.last_error()}")
            if float(profit_raw) < maximum_loss:
                low = middle
            else:
                high = middle

        capped_price = ceil_step(ceil_whole_sl(high), tick_size)
        capped_profit_raw = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, entry_price, capped_price)
        if capped_profit_raw is None:
            raise RuntimeError(f"order_calc_profit failed for capped hard stop: {mt5.last_error()}")
        capped_profit = float(capped_profit_raw)
        while capped_profit < maximum_loss - 1e-8 and capped_price < entry_price:
            capped_price = min(entry_price, capped_price + max(1.0, tick_size))
            capped_profit_raw = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, entry_price, capped_price)
            if capped_profit_raw is None:
                raise RuntimeError(f"order_calc_profit failed while rounding capped hard stop: {mt5.last_error()}")
            capped_profit = float(capped_profit_raw)
        return capped_price, capped_profit, True

    def what_if_scenarios(self, volume: float, entry_price: float, balance: float, stop_return: float) -> list[dict[str, Any]]:
        scenarios = [("-0.5%", -0.005), ("-1.0%", -0.01), ("HARD SL", stop_return), ("-3.0%", -0.03), ("-5.0%", -0.05)]
        result: list[dict[str, Any]] = []
        seen: set[int] = set()
        for label, change in scenarios:
            key = round(change * 1_000_000)
            if key in seen:
                continue
            seen.add(key)
            scenario_price = entry_price * (1.0 + change)
            raw_profit = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, volume, entry_price, scenario_price)
            profit = float(raw_profit) if raw_profit is not None else 0.0
            result.append({
                "label": label, "underlyingReturnPercent": change * 100.0, "price": scenario_price, "profit": profit,
                "balanceAfter": balance + profit, "accountReturnPercent": profit / balance * 100.0 if balance > 0 else 0.0,
            })
        return result

    def required_balance_multiplier(self, leverage: int) -> float:
        if bool(getattr(self.cfg, "use_legacy_balance_multiplier", False)):
            if int(leverage) == int(self.cfg.loss_leverage):
                return float(self.cfg.legacy_required_balance_multiplier_l10)
            if int(leverage) == int(self.cfg.base_leverage):
                return float(self.cfg.legacy_required_balance_multiplier_l8)
            raise RuntimeError(f"No legacy required-balance multiplier configured for leverage {leverage}")
        return float(self.cfg.required_balance_multiplier)

    def balance_multiplier_profile(self) -> str:
        return "CONSERVATIVE_LEVERAGE_BOUND" if bool(getattr(self.cfg, "use_legacy_balance_multiplier", False)) else "GROWTH_1_765"

    def account_loss_cap_enabled(self) -> bool:
        return bool(getattr(self.cfg, "use_legacy_balance_multiplier", False))

    def account_loss_cap_policy(self) -> str:
        return "BALANCE_50_PERCENT" if self.account_loss_cap_enabled() else "DISABLED_FOR_GROWTH_1_765"

    def potential_position_preview(self, assume_current_position_closed: bool = False) -> dict[str, Any]:
        previous_full_week, previous_trade, full_week_source, trade_source = self.resolved_leverage_inputs()
        leverage, leverage_reason = self.leverage_decision()
        required_balance_multiplier = self.required_balance_multiplier(leverage)
        now = datetime.now(self.tz)
        result: dict[str, Any] = {
            "available": False, "generatedAt": now.isoformat(), "build": BUILD_ID, "account": self.account,
            "symbol": self.cfg.trade_symbol, "side": "BUY", "price": 0.0, "priceSource": "MT5 current BUY price",
            "volume": 0.0, "requiredDeposit": 0.0, "requiredBalance": 0.0,
            "requiredBalanceMultiplier": required_balance_multiplier, "requiredBalanceHeadroom": 0.0,
            "minimumVolumeRequiredDeposit": 0.0, "minimumVolumeRequiredBalance": 0.0,
            "nextVolumeStep": 0.0, "nextVolumeStepRequiredDeposit": 0.0,
            "nextVolumeStepRequiredBalance": 0.0, "nextVolumeStepAffordable": False,
            "sizingMethod": "MAX_VOLUME_BY_REQUIRED_BALANCE", "balanceMultiplierProfile": self.balance_multiplier_profile(), "brokerMarginLeverage": 0.0, "depositSource": "",
            "balance": 0.0, "equity": 0.0, "freeMargin": 0.0, "freeMarginAfter": 0.0,
            "marginUsagePercent": 0.0, "marginLevelAfterPercent": 0.0, "effectiveLeverage": 0.0,
            "strategyLeverage": float(leverage), "leverageReason": leverage_reason,
            "previousFullWeekChange": float(previous_full_week), "previousFullWeekSource": full_week_source,
            "previousTradeChange": float(previous_trade), "previousTradeSource": trade_source,
            "fullWeekTriggerPercent": float(self.cfg.full_week_loss_trigger) * 100.0, "previousTradeTriggerPercent": float(self.cfg.previous_trade_loss_trigger) * 100.0,
            "potentialStopLossPercent": 0.0, "potentialStopLossRatio": 0.0,
            "potentialStopLossPrice": 0.0, "potentialStopLossCash": 0.0, "accountLossPercentAtStop": 0.0,
            "accountLossCapApplied": False, "accountLossCapPolicy": self.account_loss_cap_policy(), "stopLossFormula": "",
            "positionNotional": 0.0, "sizingUnits": 0, "minimumVolumeFloor": False, "scenarios": [], "error": "",
            "purpose": "NEXT_TRADE", "currentPositionOpen": bool(assume_current_position_closed),
            "assumesCurrentPositionClosed": bool(assume_current_position_closed), "sizingFreeMargin": 0.0,
            "sizingBalanceSource": "MT5 account balance",
            "assumptionNote": (
                "Current position remains unchanged; next-trade sizing assumes it is closed before the hypothetical entry"
                if assume_current_position_closed else "Account is flat at the hypothetical entry"
            ),
        }
        try:
            account = mt5.account_info()
            info = mt5.symbol_info(self.cfg.trade_symbol)
            tick = self.latest_tick(self.cfg.trade_symbol)
            if account is None or info is None:
                raise RuntimeError(f"Cannot obtain account/symbol data: {mt5.last_error()}")

            balance = float(getattr(account, "balance", 0.0) or 0.0)
            equity = float(getattr(account, "equity", 0.0) or 0.0)
            free_margin = float(getattr(account, "margin_free", 0.0) or 0.0)
            sizing_free_margin = max(0.0, balance) if assume_current_position_closed else max(0.0, free_margin)
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            last = float(getattr(tick, "last", 0.0) or 0.0)
            price = ask if ask > 0 else last if last > 0 else bid
            if price <= 0:
                raise RuntimeError(f"No usable current price for {self.cfg.trade_symbol}")

            sizing = self.required_balance_sizing(balance, sizing_free_margin, info, price, leverage)
            minimum_volume_notional = self.minimum_volume_notional(info, price)
            sizing_units = int(sizing["sizingUnits"])
            volume = float(sizing["volume"])
            required_deposit = float(sizing["requiredDeposit"])
            required_balance = float(sizing["requiredBalance"])
            broker_leverage = self.broker_margin_leverage(account)
            effective_leverage = required_deposit * float(self.cfg.sizing_multiplier) / balance if balance > 0 else 0.0
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01)
            stop_price, stop_profit, account_loss_cap_applied = self.capped_hard_stop(
                self.cfg.trade_symbol, float(volume), price, balance, leverage, tick_size,
            )
            stop_ratio = stop_price / price if price > 0 else 0.0
            stop_return = stop_ratio - 1.0
            existing_margin = float(getattr(account, "margin", 0.0) or 0.0)
            margin_before_hypothetical_entry = 0.0 if assume_current_position_closed else existing_margin
            margin_after = margin_before_hypothetical_entry + required_deposit
            equity_for_margin_level = balance if assume_current_position_closed else equity

            result.update({
                "available": True, "price": price, "volume": float(volume), "requiredDeposit": required_deposit,
                "requiredBalance": required_balance, "requiredBalanceMultiplier": required_balance_multiplier,
                "requiredBalanceHeadroom": balance - required_balance,
                "minimumVolumeRequiredDeposit": float(sizing["minimumVolumeRequiredDeposit"]),
                "minimumVolumeRequiredBalance": float(sizing["minimumVolumeRequiredBalance"]),
                "nextVolumeStep": float(sizing["nextVolumeStep"]),
                "nextVolumeStepRequiredDeposit": float(sizing["nextVolumeStepRequiredDeposit"]),
                "nextVolumeStepRequiredBalance": float(sizing["nextVolumeStepRequiredBalance"]),
                "nextVolumeStepAffordable": bool(sizing["nextVolumeStepAffordable"]),
                "sizingMethod": "MAX_VOLUME_BY_REQUIRED_BALANCE", "balanceMultiplierProfile": self.balance_multiplier_profile(),
                "brokerMarginLeverage": broker_leverage,
                "depositSource": f"MT5 order_calc_margin(volume, current BUY price); required balance = deposit Ă— {required_balance_multiplier:.3f}",
                "balance": balance, "equity": equity, "freeMargin": free_margin, "sizingFreeMargin": sizing_free_margin,
                "freeMarginAfter": sizing_free_margin - required_deposit,
                "marginUsagePercent": required_deposit / balance * 100.0 if balance > 0 else 0.0,
                "marginLevelAfterPercent": equity_for_margin_level / margin_after * 100.0 if margin_after > 0 else 0.0,
                "effectiveLeverage": effective_leverage, "potentialStopLossPercent": stop_return * 100.0,
                "potentialStopLossRatio": stop_ratio, "potentialStopLossPrice": stop_price,
                "potentialStopLossCash": stop_profit, "accountLossPercentAtStop": stop_profit / balance * 100.0 if balance > 0 else 0.0,
                "accountLossCapApplied": account_loss_cap_applied, "accountLossCapPolicy": self.account_loss_cap_policy(),
                "positionNotional": minimum_volume_notional * (float(volume) / float(info.volume_min)),
                "sizingUnits": int(sizing_units), "minimumVolumeFloor": False,
                "scenarios": self.what_if_scenarios(float(volume), price, balance, stop_return),
            })
        except Exception as exc:
            result["error"] = str(exc)
        return result

    def strategy_parameter_hash(self) -> str:
        values = {
            "baseLeverage": self.cfg.base_leverage, "lossLeverage": self.cfg.loss_leverage,
            "breakEvenRatio": self.cfg.break_even_ratio, "tslStop": self.cfg.tsl_stop,
            "leverageStopPoints": self.cfg.leverage_stop_points, "tpps": list(self.cfg.tpps),
            "sizingMultiplier": self.cfg.sizing_multiplier,
            "requiredBalanceMultiplier": self.required_balance_multiplier(self.leverage_decision()[0]),
            "balanceMultiplierProfile": self.balance_multiplier_profile(),
            "accountLossCapPolicy": self.account_loss_cap_policy(),
            "hardStopRatioL10": self.hard_sl_ratio(int(self.cfg.loss_leverage)),
            "hardStopRatioL8": self.hard_sl_ratio(int(self.cfg.base_leverage)),
            "sizingMethod": "MAX_VOLUME_BY_REQUIRED_BALANCE",
            "strategySpecHash": str(getattr(self, "strategy_specification", {}).get("specHash", "")),
        }
        return hashlib.sha256(json.dumps(values, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    def build_strategy_specification(self) -> dict[str, Any]:
        """Return the resolved, canonical and hash-addressed strategy contract.

        Credentials, account identifiers and operational file paths are
        deliberately excluded. Every value capable of changing a trading
        decision, order, size, timestamp or exit is included.
        """
        document: dict[str, Any] = {
            "schemaVersion": 1,
            "strategy": {"key": "OPPW24", "version": PROJECT_VERSION, "direction": "LONG_ONLY"},
            "instruments": {
                "execution": self.cfg.trade_symbol,
                "signal": self.cfg.signal_symbol,
                "executionSource": "MetaTrader5",
                "signalSource": "MetaTrader5",
            },
            "calendarAndTime": {
                "exchangeCalendar": self.cfg.exchange_calendar,
                "strategyTimezone": self.cfg.timezone_name,
                "marketTimezone": self.cfg.market_timezone_name,
                "premarketStart": self.cfg.premarket_start.isoformat(),
                "cashOpenFallback": self.cfg.cash_open.isoformat(),
                "cashCloseFallback": self.cfg.close_bar_open.isoformat(),
                "entryLeadSeconds": float(self.cfg.entry_action_lead_seconds),
                "nonEntryLeadSeconds": float(self.cfg.non_entry_action_lead_seconds),
                "entryWindowSeconds": int(self.cfg.entry_window_seconds),
                "entryDayRule": "FIRST_XNYS_SESSION_OF_WEEK; Monday when open, otherwise the first later XNYS session after any closure sequence",
                "signalOpenRule": "EXACT_ENTRY_SESSION_CASH_OPEN_M1; deferred without fill-price fallback",
            },
            "leverageSelection": {
                "baseLeverage": int(self.cfg.base_leverage),
                "lossLeverage": int(self.cfg.loss_leverage),
                "previousFullWeekTrigger": float(self.cfg.full_week_loss_trigger),
                "previousTradeTrigger": float(self.cfg.previous_trade_loss_trigger),
                "rule": "loss leverage if either trigger is met; otherwise base leverage",
                "manualPositionRule": "use valid L8/L10 MT5 comment; otherwise run the authoritative leverage decision",
                "manualRecoveryLinkRule": "detach a manual position from stale strategy execution and decision identifiers before protection locking",
            },
            "sizing": {
                "method": "MAX_VOLUME_BY_REQUIRED_BALANCE",
                "brokerExposureMultiplier": float(self.cfg.sizing_multiplier),
                "growthRequiredBalanceMultiplier": float(self.cfg.required_balance_multiplier),
                "conservativeMultiplierL10": float(self.cfg.legacy_required_balance_multiplier_l10),
                "conservativeMultiplierL8": float(self.cfg.legacy_required_balance_multiplier_l8),
                "activeProfile": self.balance_multiplier_profile(),
                "activeRequiredBalanceMultiplierRule": (
                    "growthRequiredBalanceMultiplier"
                    if self.balance_multiplier_profile() == "GROWTH_1_765"
                    else "conservativeMultiplier selected by leverage"
                ),
                "volumeRule": "largest broker volume step whose required balance and margin are available",
            },
            "thresholds": {
                "sessionIndexedTakeProfit": [float(value) for value in self.cfg.tpps],
                "holidayShiftRule": "TPP index follows actual XNYS session ordinal, not weekday name",
                "preHighRamp": "on second actual session after entry, linear first-to-second TPP from premarket start to cash open",
                "preHighFormula": "execution M1 open > position fill price * (1 + active ramp TPP) causes market SELL",
                "openHighSchedule": "cash-open-minus-lead checks begin on the second actual XNYS session; the first session is never checked",
                "openHighFormula": "from the second session onward, live execution bid at open check > position fill price * (1 + session-indexed TPP) causes market SELL",
                "closeHighFormula": "live signal price at close check > entry-session signal cash open * (1 + session-indexed TPP) causes market SELL",
                "breakEvenRatio": float(self.cfg.break_even_ratio),
                "breakEvenArmSchedule": "no earlier than the second actual XNYS session day close and never on the position opening day",
                "breakEvenArmFormula": "after false CH on an eligible session, live signal price < entry-session signal cash open * breakEvenRatio",
                "breakEvenExitFormula": "BEPRE/BEO/BH compare execution price with position fill price * breakEvenRatio and use market SELL",
                "thursdayTslDistance": float(self.cfg.tsl_stop),
                "thursdayTslFormula": "position fill price * (1 - thursdayTslDistance), active from Thursday date change",
                "hardStopPointsOverLeverage": float(self.cfg.leverage_stop_points),
                "hardStopRatioL10": float(self.hard_sl_ratio(int(self.cfg.loss_leverage))),
                "hardStopRatioL8": float(self.hard_sl_ratio(int(self.cfg.base_leverage))),
                "accountLossCapPolicy": self.account_loss_cap_policy(),
                "maximumAccountStopLossFraction": float(self.cfg.max_account_stop_loss_fraction),
            },
            "orderSemantics": {
                "entry": "MARKET BUY using current ask in TRADE_ACTION_DEAL",
                "strategyExit": "MARKET SELL using current bid in TRADE_ACTION_DEAL",
                "weeklyTimeout": "MARKET SELL at final XNYS session close minus non-entry lead",
                "protection": "TRADE_ACTION_SLTP broker-side SL; no pending entry or exit orders",
                "deviationPoints": int(self.cfg.deviation_points),
                "fillingMode": self.cfg.filling_mode,
            },
            "hardStopInvariant": {
                "provisional": "attached to BUY using requested ask",
                "definitive": "calculated once from actual fill, volume, balance, leverage and account conversion",
                "persistence": "immutable per position",
                "allowedTightening": ["post-fill correction", "recovery leverage correction", "Thursday TSL", "explicit break-even/exit protection", "restoration"],
                "wholePointRounding": "round positive SL upward to nearest whole index point",
            },
            "exitHierarchy": [
                "broker hard SL",
                "PRE H premarket threshold",
                "BEPRE market exit",
                "OH market exit",
                "BEO market exit",
                "Thursday TSL tightening or crossed-threshold market exit",
                "BH market exit",
                "CH market exit",
                "break-even arming immediately after false CH",
                "final-session TO market exit",
            ],
            "persistenceAuthority": {
                "specifications": "immutable MySQL strategy_specifications",
                "decisions": "immutable MySQL strategy_decisions",
                "trades": "immutable MySQL strategy_trade_ledger plus strategy_trades projection",
                "fills": "immutable MySQL strategy_fills",
                "cashFlows": "immutable MySQL account_cash_flows",
                "protection": "immutable MySQL strategy_protection_changes",
                "lifecycle": "immutable MySQL strategy_execution_stages",
                "events": "diagnostic stream only",
            },
        }
        canonical = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        spec_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "specId": spec_hash[:32],
            "specHash": spec_hash,
            "specKey": "OPPW24",
            "specVersion": PROJECT_VERSION,
            "effectiveFrom": "2026-07-21T00:00:00+00:00",
            "createdAt": self.started_at.astimezone(UTC).isoformat(),
            "build": BUILD_ID,
            "document": document,
        }

    def strategy_decision_week_key(self, now: Optional[datetime] = None) -> str:
        now = now or datetime.now(self.tz)
        if not self.is_weekend(now):
            return iso_week_key(now.date())
        sessions = self.trading_sessions_for_week(now.date() + timedelta(days=7))
        return iso_week_key(sessions[0] if sessions else now.date() + timedelta(days=1))

    def strategy_decision_payload(self, preview: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        preview = preview or self.potential_position_preview()
        recorded_at = datetime.now(self.tz).isoformat()
        decision_id_source = "|".join(str(value) for value in (
            self.account, self.strategy_decision_week_key(), BUILD_ID, preview.get("symbol", ""),
            self.strategy_specification["specHash"],
            preview.get("strategyLeverage", 0.0), preview.get("previousFullWeekChange", 0.0),
            preview.get("previousTradeChange", 0.0), preview.get("volume", 0.0), preview.get("available", False),
            round(float(preview.get("balance") or 0.0), 2), round(float(preview.get("sizingFreeMargin", preview.get("freeMargin")) or 0.0), 2),
            recorded_at,
        ))
        decision_id = uuid.uuid5(uuid.NAMESPACE_URL, decision_id_source).hex
        return {
            "decisionId": decision_id, "decisionWeek": self.strategy_decision_week_key(), "recordedAt": recorded_at, "build": BUILD_ID,
            "strategySpecId": self.strategy_specification["specId"],
            "strategySpecHash": self.strategy_specification["specHash"],
            "parameterHash": self.strategy_parameter_hash(), "account": self.account, "decision": "NEXT_WEEK_LONG_ENTRY",
            "outcome": "READY" if bool(preview.get("available")) else "UNAVAILABLE",
            "selectedLeverage": float(preview.get("strategyLeverage", 0.0)), "leverageReason": str(preview.get("leverageReason", "")),
            "inputs": {
                "previousFullWeekChange": float(preview.get("previousFullWeekChange", 0.0)),
                "previousFullWeekSource": str(preview.get("previousFullWeekSource", "")),
                "previousTradeChange": float(preview.get("previousTradeChange", 0.0)),
                "previousTradeSource": str(preview.get("previousTradeSource", "")),
                "fullWeekTriggerPercent": float(preview.get("fullWeekTriggerPercent", -2.5)),
                "previousTradeTriggerPercent": float(preview.get("previousTradeTriggerPercent", -0.7)),
            },
            "sizing": {key: preview.get(key) for key in (
                "symbol", "side", "price", "priceSource", "volume", "requiredDeposit", "requiredBalance",
                "requiredBalanceMultiplier", "requiredBalanceHeadroom", "balanceMultiplierProfile", "minimumVolumeRequiredDeposit",
                "minimumVolumeRequiredBalance", "nextVolumeStep", "nextVolumeStepRequiredDeposit",
                "nextVolumeStepRequiredBalance", "nextVolumeStepAffordable", "sizingMethod", "depositSource",
                "brokerMarginLeverage", "effectiveLeverage", "positionNotional", "sizingUnits", "minimumVolumeFloor",
                "balance", "equity", "freeMargin", "sizingFreeMargin", "freeMarginAfter", "marginUsagePercent", "marginLevelAfterPercent",
                "purpose", "currentPositionOpen", "assumesCurrentPositionClosed", "sizingBalanceSource", "assumptionNote",
            )},
            "risk": {key: preview.get(key) for key in (
                "potentialStopLossPercent", "potentialStopLossRatio", "potentialStopLossPrice",
                "potentialStopLossCash", "accountLossPercentAtStop", "accountLossCapApplied", "scenarios",
            )},
            "error": str(preview.get("error", "")),
        }

    def record_strategy_decision_if_changed(self, force: bool = False, preview: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        # Weekends suppress recurring decision checks, but a forced call is
        # permitted once during weekend startup to create the fresh What-if
        # ticket requested by the operator.
        if self.is_weekend(datetime.now(self.tz)) and not force:
            return {}
        preview = preview or self.potential_position_preview()
        payload = self.strategy_decision_payload(preview)
        signature = (
            self.strategy_decision_week_key(), payload["outcome"], round(float(payload["selectedLeverage"]), 6),
            round(float(payload["inputs"]["previousFullWeekChange"]), 8), round(float(payload["inputs"]["previousTradeChange"]), 8),
            str(payload["inputs"].get("previousFullWeekSource", "")), str(payload["inputs"].get("previousTradeSource", "")),
            round(float(payload["sizing"].get("volume") or 0.0), 8), int(payload["sizing"].get("sizingUnits") or 0),
            round(float(payload["sizing"].get("balance") or 0.0), 2), round(float(payload["sizing"].get("sizingFreeMargin", payload["sizing"].get("freeMargin")) or 0.0), 2),
            bool(payload["sizing"].get("minimumVolumeFloor")), payload["error"].split(":", 1)[0],
        )
        if not force and signature == self.last_strategy_decision_signature and self.last_strategy_decision_payload:
            return self.last_strategy_decision_payload
        self.last_strategy_decision_payload = payload
        self.state.active_decision_id = str(payload.get("decisionId", ""))
        self.state.active_strategy_spec_id = self.strategy_specification["specId"]
        self.state.active_strategy_spec_hash = self.strategy_specification["specHash"]
        if self.is_executor:
            self.state.save(self.cfg.state_file)
        if force or signature != self.last_strategy_decision_signature:
            self.last_strategy_decision_signature = signature
            self.log.info(
                "EVENT STRATEGY_DECISION_CALCULATED decision_id=%s strategy_spec_id=%s strategy_spec_hash=%s parameter_hash=%s outcome=%s leverage=%.0f "
                "previous_full_week=%.8f full_week_source=%s previous_trade=%.8f trade_source=%s volume=%.8f required_deposit=%.2f "
                "required_balance=%.2f required_balance_multiplier=%.3f effective_leverage=%.6f stop_loss_percent=%.4f "
                "stop_loss_price=%.5f stop_loss_cash=%.2f error=%s",
                payload["decisionId"], payload["strategySpecId"], payload["strategySpecHash"], payload["parameterHash"], payload["outcome"], payload["selectedLeverage"],
                payload["inputs"]["previousFullWeekChange"], str(payload["inputs"].get("previousFullWeekSource", "")).replace(" ", "_"),
                payload["inputs"]["previousTradeChange"], str(payload["inputs"].get("previousTradeSource", "")).replace(" ", "_"),
                float(payload["sizing"].get("volume") or 0.0), float(payload["sizing"].get("requiredDeposit") or 0.0),
                float(payload["sizing"].get("requiredBalance") or 0.0),
                float(payload["sizing"].get("requiredBalanceMultiplier") or self.required_balance_multiplier(int(payload["selectedLeverage"] or self.cfg.base_leverage))),
                float(payload["sizing"].get("effectiveLeverage") or 0.0),
                float(payload["risk"].get("potentialStopLossPercent") or 0.0),
                float(payload["risk"].get("potentialStopLossPrice") or 0.0),
                float(payload["risk"].get("potentialStopLossCash") or 0.0),
                shlex.quote(str(payload["error"] or "none")),
            )
        return payload
