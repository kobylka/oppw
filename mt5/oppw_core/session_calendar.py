"""Session calendar behavior for the canonical strategy composition."""

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
from .position_lifecycle import PositionLifecycleMixin


class SessionCalendarMixin:
    @staticmethod
    def is_weekend(value: datetime | date) -> bool:
        day = value.date() if isinstance(value, datetime) else value
        return day.weekday() >= 5

    @staticmethod
    def next_week_monday(day: date) -> date:
        return day + timedelta(days=7 - day.weekday()) if day.weekday() >= 5 else day - timedelta(days=day.weekday())

    def week_plan_day(self, day: date) -> date:
        return self.next_week_monday(day) if day.weekday() >= 5 else day

    def entry_action_lead_seconds(self) -> float:
        return max(0.0, float(self.cfg.entry_action_lead_seconds))

    def session_times(self, day: date) -> SessionTimes:
        cached = self._session_times_cache.get(day)
        if cached is not None:
            return cached

        sessions = self.calendar.sessions_in_range(day.isoformat(), day.isoformat())
        if len(sessions):
            session = sessions[0]
            cash_open = self.calendar.session_open(session).to_pydatetime().astimezone(self.tz)
            close_bar_open = self.calendar.session_close(session).to_pydatetime().astimezone(self.tz)
            close_processing = close_bar_open + timedelta(minutes=1)
        else:
            cash_open = datetime.combine(day, self.cfg.cash_open, self.market_tz).astimezone(self.tz)
            close_bar_open = datetime.combine(day, self.cfg.close_bar_open, self.market_tz).astimezone(self.tz)
            close_processing = datetime.combine(day, self.cfg.close_processing, self.market_tz).astimezone(self.tz)

        entry_lead = timedelta(seconds=self.entry_action_lead_seconds())
        non_entry_lead = timedelta(seconds=float(self.cfg.non_entry_action_lead_seconds))
        value = SessionTimes(
            cash_open=cash_open,
            buy_action=cash_open - entry_lead,
            open_action=cash_open - non_entry_lead,
            weekly_close=close_bar_open - non_entry_lead,
            close_bar_open=close_bar_open,
            close_processing=close_processing,
        )
        self._session_times_cache[day] = value
        return value

    def trading_sessions_for_week(self, day: date) -> list[date]:
        monday = day - timedelta(days=day.weekday())
        friday = monday + timedelta(days=4)
        sessions = self.calendar.sessions_in_range(monday.isoformat(), friday.isoformat())
        return [session.date() for session in sessions]

    def trading_session_index(self, day: date) -> int:
        """Return the zero-based XNYS session index for *day* within its week."""
        sessions = self.trading_sessions_for_week(day)
        if not sessions:
            return min(max(day.weekday(), 0), len(self.cfg.tpps) - 1)
        if day in sessions:
            return min(sessions.index(day), len(self.cfg.tpps) - 1)

        # A non-session date has no executable TPP. Use the most recently
        # reached session for read-only weekend/holiday status presentation,
        # or the first session when the week has not started yet.
        completed = sum(session_day <= day for session_day in sessions)
        return min(max(completed - 1, 0), len(self.cfg.tpps) - 1)

    def tpp_for_day(self, day: date) -> float:
        return float(self.cfg.tpps[self.trading_session_index(day)])

    def premarket_high_tpp(self, position, at: datetime) -> Optional[float]:
        """Return the PRE H ramp on the second trading session after entry."""
        current_day = at.astimezone(self.tz).date()
        sessions = self.trading_sessions_for_week(current_day)
        opened = self.position_open_date(position)
        if len(sessions) < 2 or opened != sessions[0] or current_day != sessions[1]:
            return None

        session = self.session_times(current_day)
        ramp_start = datetime.combine(current_day, self.cfg.premarket_start, self.tz)
        ramp_end = session.cash_open
        duration = (ramp_end - ramp_start).total_seconds()
        if duration <= 0:
            return self.tpp_for_day(current_day)

        progress = (at.astimezone(self.tz) - ramp_start).total_seconds() / duration
        progress = min(max(progress, 0.0), 1.0)
        start_tpp = float(self.cfg.tpps[0])
        end_tpp = float(self.cfg.tpps[1])
        return start_tpp + (end_tpp - start_tpp) * progress

    def is_trading_session_day(self, day: date) -> bool:
        return len(self.calendar.sessions_in_range(day.isoformat(), day.isoformat())) > 0

    def trading_session_ordinal(self, day: date) -> Optional[int]:
        sessions = self.trading_sessions_for_week(day)
        try:
            return sessions.index(day)
        except ValueError:
            return None

    def oh_check_eligible(self, day: date) -> bool:
        ordinal = self.trading_session_ordinal(day)
        return ordinal is not None and ordinal >= 1

    def break_even_check_eligible(self, opened: date, day: date) -> bool:
        ordinal = self.trading_session_ordinal(day)
        return day > opened and ordinal is not None and ordinal >= 1

    def week_open_reference(self, day: date, now: datetime) -> tuple[str, float]:
        sessions = self.trading_sessions_for_week(day)
        if not sessions:
            return "", 0.0
        first_day = sessions[0]
        cash_open = self.session_times(first_day).cash_open
        if now < cash_open:
            return cash_open.isoformat(), 0.0

        week_key = iso_week_key(first_day)
        cache = getattr(self, "_week_open_price_cache", {})
        cached = float(cache.get(week_key, 0.0) or 0.0)
        if cached > 0:
            return cash_open.isoformat(), cached

        cash_open_time = cash_open.time().replace(second=0, microsecond=0)
        bar = self.m1_bar_at(self.cfg.trade_symbol, first_day, cash_open_time)
        price = float(bar.open) if bar is not None and bar.open > 0 else 0.0
        if price > 0:
            cache[week_key] = price
            self._week_open_price_cache = cache
        return cash_open.isoformat(), price

    def market_session_payload(self, now: datetime, current_week_bar: Optional[M1Bar] = None) -> dict[str, Any]:
        local_day = now.date()
        monday = local_day - timedelta(days=local_day.weekday())
        is_trading_day = self.is_trading_session_day(local_day)
        previous_day = self.previous_trading_date(local_day)
        session = self.session_times(local_day) if is_trading_day else None
        week_cash_open, week_open_price = self.week_open_reference(local_day, now)
        return {
            "isTradingDay": is_trading_day,
            "regularSessionStarted": bool(session is not None and now >= session.cash_open),
            "cashOpen": session.cash_open.isoformat() if session is not None else "",
            "cashClose": session.close_bar_open.isoformat() if session is not None else "",
            "weekCashOpen": week_cash_open,
            "weekOpenPrice": week_open_price if week_open_price > 0 else None,
            "weekMarketOpen": current_week_bar.local_datetime.isoformat() if current_week_bar is not None else "",
            "weekMarketOpenPrice": current_week_bar.open if current_week_bar is not None else None,
            "weekMarketOpenSource": "MT5_M1_WINDOW" if current_week_bar is not None else "",
            "weekMonday": monday.isoformat(),
            "previousWeekMonday": (monday - timedelta(days=7)).isoformat(),
            "previousTradingDay": previous_day.isoformat() if previous_day is not None else "",
            "entryActionLeadSeconds": self.entry_action_lead_seconds(),
            "nonEntryActionLeadSeconds": float(self.cfg.non_entry_action_lead_seconds),
        }

    def break_even_check_payload(self, position, now: datetime) -> dict[str, Any]:
        state_matches = PositionLifecycleMixin.position_state_matches(self, position)
        entry = float(
            getattr(position, "price_open", 0.0)
            or (self.state.entry_price if state_matches else 0.0)
            or 0.0
        )
        opened = PositionLifecycleMixin.position_open_date(self, position)
        signal_reference = float(self.state.entry_signal_daily_open or 0.0) if state_matches else 0.0
        signal_pending = bool(self.state.entry_signal_open_pending) if state_matches else True
        if (
            not state_matches
            and opened is not None
            and now >= self.session_times(opened).cash_open
            and callable(getattr(self, "signal_cash_open", None))
        ):
            signal_reference = float(self.signal_cash_open(self.cfg.signal_symbol, opened) or 0.0)
            signal_pending = signal_reference <= 0
        threshold = signal_reference * float(self.cfg.break_even_ratio) if signal_reference > 0 else 0.0
        if state_matches and self.state.break_even:
            return {
                "status": "ARMED",
                "nextCheckAt": "",
                "signalReference": signal_reference,
                "threshold": threshold,
                "condition": "Break-even protection is armed; live exit checks are active.",
            }

        if opened is None:
            return {
                "status": "UNAVAILABLE",
                "nextCheckAt": "",
                "signalReference": signal_reference,
                "threshold": threshold,
                "condition": "Position opening date is unavailable.",
            }

        final_day = self.final_trading_day(opened)
        next_check_at: Optional[datetime] = None
        for offset in range(15):
            candidate = now.date() + timedelta(days=offset)
            if final_day is not None and candidate >= final_day:
                break
            if not self.break_even_check_eligible(opened, candidate):
                continue
            if state_matches and (
                self.state.last_close_action_date == candidate.isoformat()
                or self.state.last_close_processed_date == candidate.isoformat()
            ):
                continue
            next_check_at = self.session_times(candidate).weekly_close
            break

        if next_check_at is None:
            return {
                "status": "NO_FURTHER_CHECK",
                "nextCheckAt": "",
                "signalReference": signal_reference,
                "threshold": threshold,
                "condition": "No further break-even arming check is scheduled before weekly TO.",
            }

        if signal_pending or signal_reference <= 0:
            return {
                "status": "DUE_SIGNAL_PENDING" if next_check_at <= now else "SCHEDULED_SIGNAL_PENDING",
                "nextCheckAt": next_check_at.isoformat(),
                "signalReference": 0.0,
                "threshold": 0.0,
                "condition": (
                    "The exact entry-session cash-open signal reference is still pending; "
                    "the first arming evaluation remains at the second trading-session day close."
                ),
            }

        return {
            "status": "DUE" if next_check_at <= now else "SCHEDULED",
            "nextCheckAt": next_check_at.isoformat(),
            "signalReference": signal_reference,
            "threshold": threshold,
            "condition": "Runs immediately after CH and arms when the live signal price is below the threshold.",
        }

    def final_trading_day(self, day: date) -> Optional[date]:
        sessions = self.trading_sessions_for_week(day)
        return sessions[-1] if sessions else None

    def log_week_plan(self, day: date) -> None:
        plan_day = self.week_plan_day(day)
        key = iso_week_key(plan_day)
        if key == self.last_week_plan_key:
            return
        sessions = self.trading_sessions_for_week(plan_day)
        first_day = sessions[0] if sessions else None
        first_oh_day = sessions[1] if len(sessions) > 1 else None
        final_day = sessions[-1] if sessions else None
        buy_action = self.session_times(first_day).buy_action.strftime("%Y-%m-%d %H:%M:%S %Z") if first_day else "none"
        open_action = self.session_times(first_oh_day).open_action.strftime("%Y-%m-%d %H:%M:%S %Z") if first_oh_day else "none"
        weekly_to = self.session_times(final_day).weekly_close.strftime("%Y-%m-%d %H:%M:%S %Z") if final_day else "none"
        self.last_week_plan_key = key
        self.log.info(
            "EVENT WEEK_PLAN week=%s sessions=%s first_day=%s final_day=%s buy_action=%s OH=%s weekly_TO=%s "
            "entry_lead_seconds=%.1f non_entry_lead_seconds=%.1f source_day=%s weekend_next_week=%s",
            key, ",".join(value.isoformat() for value in sessions) or "none", first_day, final_day,
            buy_action, open_action, weekly_to, self.entry_action_lead_seconds(), float(self.cfg.non_entry_action_lead_seconds),
            day.isoformat(), day.weekday() >= 5,
        )

    def latest_tick(self, symbol: str):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed: {mt5.last_error()}")
        return tick

    def mt5_timestamp_to_local(self, timestamp: float) -> datetime:
        wall_clock = datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
        return wall_clock.replace(tzinfo=self.tz)

    def mt5_bar_timestamp_to_local(self, timestamp: float) -> datetime:
        return self.mt5_timestamp_to_local(timestamp)

    def local_to_mt5_bar_query_time(self, local_dt: datetime) -> datetime:
        wall_clock = local_dt.astimezone(self.tz).replace(tzinfo=None)
        return wall_clock.replace(tzinfo=UTC)

    def require_fresh_tick(self, symbol: str) -> Any:
        tick = self.latest_tick(symbol)
        timestamp = getattr(tick, "time_msc", 0) / 1000.0 if getattr(tick, "time_msc", 0) else tick.time
        tick_local = self.mt5_timestamp_to_local(timestamp)
        age = (datetime.now(self.tz) - tick_local).total_seconds()
        if age > self.cfg.maximum_tick_age_seconds:
            raise StaleTickError(symbol, age)
        return tick

    def fresh_tick_for_protection(self, position, context: str) -> Optional[Any]:
        try:
            return self.require_fresh_tick(position.symbol)
        except StaleTickError as exc:
            key = f"{position.symbol}:{context}"
            now = time_module.monotonic()
            previous = self.last_stale_tick_log_monotonic.get(key, 0.0)
            if now - previous >= float(self.cfg.stale_tick_reminder_seconds):
                self.last_stale_tick_log_monotonic[key] = now
                log = self.log.error if float(position.sl) <= 0 else self.log.warning
                log(
                    "EVENT PROTECTION_DEFERRED context=%s symbol=%s reason=stale_tick tick_age_seconds=%.1f limit_seconds=%.1f existing_sl=%.5f existing_tp=%.5f exit_latched=%s",
                    context, position.symbol, exc.age_seconds, self.cfg.maximum_tick_age_seconds,
                    float(position.sl), float(position.tp), self.state.exit_latched_reason or "none",
                )
            return None

    def current_m1_bar(self, symbol: str) -> Optional[M1Bar]:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 3)
        if rates is None or len(rates) == 0:
            return None
        row = max(rates, key=lambda item: int(item["time"]))
        raw_ts = int(row["time"])
        local_dt = self.mt5_bar_timestamp_to_local(raw_ts)
        return M1Bar(raw_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

    def current_w1_bar(self, symbol: str, now: datetime) -> Optional[M1Bar]:
        """Return MT5's live broker-week candle for the current ISO week."""
        timeframe = getattr(mt5, "TIMEFRAME_W1", None)
        if timeframe is None:
            return None
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, 3)
        except Exception:
            return None
        if rates is None or len(rates) == 0:
            return None
        row = max(rates, key=lambda item: int(item["time"]))
        raw_ts = int(row["time"])
        local_dt = self.mt5_bar_timestamp_to_local(raw_ts)
        monday = now.astimezone(self.tz).date() - timedelta(days=now.astimezone(self.tz).date().weekday())
        if not (monday - timedelta(days=1) <= local_dt.date() <= monday + timedelta(days=1)):
            return None
        return M1Bar(raw_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

    def current_week_observation_start(self, position, now: datetime) -> tuple[datetime, float]:
        """Choose the monitoring boundary without relying on a broker W1 rollover."""
        local_now = now.astimezone(self.tz)
        sessions = self.trading_sessions_for_week(local_now.date())
        first_day = sessions[0] if sessions else local_now.date() - timedelta(days=local_now.date().weekday())
        cash_open = self.session_times(first_day).cash_open
        if position is None or not self.is_manual_position(position):
            return cash_open, 0.0
        raw_timestamp = (
            float(getattr(position, "time_msc", 0) or 0) / 1000.0
            if getattr(position, "time_msc", 0)
            else float(getattr(position, "time", 0) or 0)
        )
        if raw_timestamp <= 0:
            return cash_open, 0.0
        opened = self.mt5_timestamp_to_local(raw_timestamp)
        if iso_week_key(opened.date()) != iso_week_key(local_now.date()) or opened > local_now:
            return cash_open, 0.0
        return opened, float(getattr(position, "price_open", 0.0) or 0.0)

    def current_week_market_bar(self, symbol: str, now: datetime, position=None) -> Optional[M1Bar]:
        """Aggregate the current monitoring week from its explicit M1 boundary."""
        local_now = now.astimezone(self.tz)
        start, position_open_price = self.current_week_observation_start(position, local_now)
        if start > local_now:
            return None
        try:
            rates = mt5.copy_rates_range(
                symbol,
                mt5.TIMEFRAME_M1,
                self.local_to_mt5_bar_query_time(start.replace(second=0, microsecond=0)),
                self.local_to_mt5_bar_query_time(local_now.replace(second=59, microsecond=0)),
            )
        except Exception:
            rates = None
        rows = [] if rates is None else sorted(rates, key=lambda item: int(item["time"]))
        eligible = []
        for row in rows:
            local_at = self.mt5_bar_timestamp_to_local(int(row["time"]))
            if start.replace(second=0, microsecond=0) <= local_at <= local_now:
                eligible.append((row, local_at))
        if not eligible and position_open_price <= 0:
            return None
        first_row = eligible[0][0] if eligible else None
        last_row = eligible[-1][0] if eligible else None
        open_price = position_open_price if position_open_price > 0 else float(first_row["open"])
        highs = [float(row["high"]) for row, _ in eligible]
        lows = [float(row["low"]) for row, _ in eligible]
        if position_open_price > 0:
            highs.append(position_open_price)
            lows.append(position_open_price)
        high = max(highs) if highs else open_price
        low = min(lows) if lows else open_price
        close = float(last_row["close"]) if last_row is not None else open_price
        return M1Bar(int(start.timestamp()), start, open_price, high, low, close)

    def previous_m1_bar(self, symbol: str, now: datetime) -> Optional[M1Bar]:
        previous_minute = now.astimezone(self.tz).replace(second=0, microsecond=0) - timedelta(minutes=1)
        previous_time = previous_minute.time().replace(tzinfo=None)
        return self.m1_bar_at(symbol, previous_minute.date(), previous_time)

    def m1_bar_at(self, symbol: str, local_day: date, local_time: time) -> Optional[M1Bar]:
        local_start = datetime.combine(local_day, local_time, self.tz)
        query_start = self.local_to_mt5_bar_query_time(local_start)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, query_start, query_start + timedelta(seconds=59))
        if rates is None or len(rates) == 0:
            return None
        row = min(rates, key=lambda item: abs(int(item["time"]) - int(query_start.timestamp())))
        raw_ts = int(row["time"])
        local_dt = self.mt5_bar_timestamp_to_local(raw_ts)
        if local_dt.date() != local_day or local_dt.hour != local_time.hour or local_dt.minute != local_time.minute:
            return None
        return M1Bar(raw_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

    def signal_cash_open(self, symbol: str, local_day: date) -> Optional[float]:
        cash_open_time = self.session_times(local_day).cash_open.time().replace(second=0, microsecond=0)
        bar = self.m1_bar_at(symbol, local_day, cash_open_time)
        return None if bar is None else float(bar.open)

    def previous_trading_date(self, current_day: date) -> Optional[date]:
        sessions = self.calendar.sessions_in_range((current_day - timedelta(days=14)).isoformat(), (current_day - timedelta(days=1)).isoformat())
        days = [session.date() for session in sessions if session.date() < current_day]
        return days[-1] if days else None
