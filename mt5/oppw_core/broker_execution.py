"""Broker execution behavior for the canonical strategy composition."""

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


class BrokerExecutionMixin:
    def choose_leverage(self) -> int:
        return self.leverage_decision()[0]

    def hard_sl_ratio(self, leverage: int) -> float:
        return (100.0 - self.cfg.leverage_stop_points / leverage) / 100.0

    def hard_sl_price(self, position) -> float:
        if self.immutable_hard_stop_matches(position):
            return float(self.state.immutable_hard_sl_price)

        # A missing v49 lock is exceptional and is repaired by position
        # reconciliation or apply_standard_protection(). Keep this fallback
        # deterministic and independent of current balance/conversion so a
        # read-only status calculation can never create a moving baseline.
        leverage = (
            self.state.entry_leverage
            if self.position_state_matches(position) and self.state.entry_leverage
            else self.infer_position_leverage(position)
        )
        entry = float(position.price_open)
        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        return ceil_step(ceil_whole_sl(entry * self.hard_sl_ratio(leverage)), tick_size)

    def is_new_week_entry(self, current_day: date) -> bool:
        if current_day.weekday() not in (0, 1) or self.state.last_entry_week == iso_week_key(current_day):
            return False
        previous = parse_date(self.state.last_trading_date)
        discovered = self.previous_trading_date(current_day)
        if discovered is not None and (previous is None or discovered > previous or previous >= current_day):
            previous = discovered
            self.state.last_trading_date = previous.isoformat()
            self.state.save(self.cfg.state_file)
        return previous is not None and (current_day - previous).days > 1

    @staticmethod
    def arithmetic_entry_rule_trigger(outcomes: list[float], threshold: float = 0.02) -> bool:
        return len(outcomes) >= 2 and sum(outcomes[-2:]) <= -float(threshold) + 1e-12

    @staticmethod
    def gap_momentum_entry_rule_trigger(
        cash_open: float,
        previous_cash_close: float,
        momentum20: Optional[float],
        gap_threshold: float = 0.01,
        momentum_threshold: float = -0.005,
    ) -> bool:
        if cash_open <= 0 or previous_cash_close <= 0 or momentum20 is None:
            return False
        return (
            cash_open / previous_cash_close - 1.0 >= float(gap_threshold) - 1e-12
            and momentum20 <= float(momentum_threshold) + 1e-12
        )

    @staticmethod
    def normalized_tuesday_entry_rule(friday_close: float, tuesday_open: float, tolerance: float = 0.005) -> bool:
        return (
            friday_close > 0
            and tuesday_open > 0
            and abs(tuesday_open / friday_close - 1.0) <= float(tolerance) + 1e-12
        )

    @staticmethod
    def premarket_low_entry_rule_trigger(
        premarket_open: float,
        premarket_high: float,
        premarket_low: float,
        premarket_close: float,
        minimum_range: float = 0.008,
        maximum_close_location: float = 0.15,
    ) -> bool:
        if premarket_open <= 0 or premarket_high <= premarket_low:
            return False
        span = premarket_high - premarket_low
        return (
            span / premarket_open >= float(minimum_range) - 1e-12
            and (premarket_close - premarket_low) / span <= float(maximum_close_location) + 1e-12
        )

    def backend_strategy_controls_url(self) -> str:
        ingest_url = str(getattr(self.cfg, "monitor_ingest_url", "") or "").strip()
        if not ingest_url:
            return ""
        base = ingest_url.rsplit("/", 1)[0]
        path = str(getattr(self.cfg, "backend_strategy_controls_path", "strategy-controls.php") or "").lstrip("/")
        return f"{base}/{path}"

    def entry_rule_backend_request(
        self,
        current_day: date,
        payload: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        url = self.backend_strategy_controls_url()
        token = str(getattr(self.cfg, "monitor_write_token", "") or "").strip()
        if not url or not url.lower().startswith("https://") or not token:
            raise RuntimeError("HTTPS strategy-controls endpoint and monitor write token are required")
        actor = self.coordinator.actor_payload()
        week_key = iso_week_key(current_day)
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": f"OPPW-MT5-Entry-Rules/{BUILD_ID}",
        }
        if payload is None:
            query = urllib.parse.urlencode({
                "accountKey": self.cfg.monitor_account_key,
                "weekKey": week_key,
                "role": actor["role"],
                "ownerId": actor["ownerId"],
                "fencingToken": actor["fencingToken"],
            })
            request = urllib.request.Request(f"{url}?{query}", method="GET", headers=headers)
        else:
            body = dict(payload)
            body["accountKey"] = self.cfg.monitor_account_key
            body["weekKey"] = week_key
            body["coordination"] = actor
            encoded = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
            request = urllib.request.Request(url, data=encoded, method="POST", headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=float(self.cfg.monitor_timeout_seconds)) as response:
                response_text = response.read().decode("utf-8", errors="replace")
                if int(response.status) not in (200, 201):
                    raise RuntimeError(f"HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"connection failed: {exc.reason}") from exc
        try:
            decoded = json.loads(response_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Strategy-controls response was not JSON: {response_text[:200]}") from exc
        if not isinstance(decoded, dict) or not bool(decoded.get("ok", False)):
            raise RuntimeError(str(decoded.get("error", "strategy-controls request rejected")) if isinstance(decoded, dict) else "strategy-controls request rejected")
        return decoded

    def apply_entry_rule_context(self, payload: dict[str, Any]) -> dict[str, Any]:
        rules = payload.get("rules")
        if not isinstance(rules, list):
            raise RuntimeError("Strategy-controls response did not contain rules")
        parsed: dict[str, bool] = {}
        for rule in rules:
            if isinstance(rule, dict) and isinstance(rule.get("enabled"), bool):
                parsed[str(rule.get("key", ""))] = bool(rule["enabled"])
        required = set(self.entry_rule_controls)
        if set(parsed) != required:
            raise RuntimeError(f"Strategy-controls response rule set mismatch: {sorted(parsed)}")
        revision = int(payload.get("revision", 0) or 0)
        if revision <= 0:
            raise RuntimeError("Strategy-controls response contained an invalid revision")
        changed = revision != self.entry_rule_controls_revision or parsed != self.entry_rule_controls
        self.entry_rule_controls = parsed
        self.entry_rule_controls_revision = revision
        self.last_entry_rule_context = payload
        self.last_entry_rule_context_monotonic = time_module.monotonic()
        if changed:
            self.state.entry_rule_controls_revision = revision
            self.state.entry_rule_controls = dict(parsed)
            self.state.save(self.cfg.state_file)
            self.log.info(
                "EVENT ENTRY_RULE_CONTROLS_UPDATED revision=%s rules=%s",
                revision, json.dumps(parsed, sort_keys=True, separators=(",", ":")),
            )
        return payload

    def refresh_entry_rule_context(self, current_day: date) -> dict[str, Any]:
        now_monotonic = time_module.monotonic()
        refresh_seconds = max(1.0, float(getattr(self.cfg, "monitor_publish_interval_seconds", 5.0)))
        elapsed = now_monotonic - self.last_entry_rule_context_monotonic
        if elapsed < refresh_seconds:
            if self.last_entry_rule_context is not None:
                return self.last_entry_rule_context
            raise RuntimeError("Strategy-controls refresh retry is rate-limited")
        self.last_entry_rule_context_monotonic = now_monotonic
        return self.apply_entry_rule_context(self.entry_rule_backend_request(current_day))

    def record_entry_rule_week_state(
        self,
        current_day: date,
        status: str,
        inputs: dict[str, Any],
    ) -> dict[str, Any]:
        decision_id = self.state.active_decision_id or str((self.last_strategy_decision_payload or {}).get("decisionId", ""))
        actor = self.coordinator.actor_payload()
        request_source = "|".join((
            self.account,
            iso_week_key(current_day),
            status,
            decision_id,
            str(actor["ownerId"]),
            str(actor["fencingToken"]),
        ))
        response = self.entry_rule_backend_request(current_day, {
            "action": "recordWeekState",
            "requestId": uuid.uuid5(uuid.NAMESPACE_URL, request_source).hex,
            "status": status,
            "controlsRevision": self.entry_rule_controls_revision,
            "decisionId": decision_id,
            "inputs": inputs,
        })
        return self.apply_entry_rule_context(response)

    def remember_entry_rule_decision(self, current_day: date, status: str, inputs: dict[str, Any]) -> None:
        week = iso_week_key(current_day)
        changed = (
            self.state.entry_rule_decision_week != week
            or self.state.entry_rule_decision_status != status
            or self.state.entry_rule_decision_inputs != inputs
            or self.state.entry_rule_controls_revision != self.entry_rule_controls_revision
            or self.state.entry_rule_controls != self.entry_rule_controls
        )
        if not changed:
            return
        self.state.entry_rule_decision_week = week
        self.state.entry_rule_decision_status = status
        self.state.entry_rule_decision_inputs = dict(inputs)
        self.state.entry_rule_controls_revision = self.entry_rule_controls_revision
        self.state.entry_rule_controls = dict(self.entry_rule_controls)
        self.state.save(self.cfg.state_file)
        self.record_strategy_decision_if_changed(force=True)

    def entry_rule_market_context(self, current_day: date) -> Optional[dict[str, Any]]:
        session = self.session_times(current_day)
        cash_open_time = session.cash_open.time().replace(second=0, microsecond=0)
        cash_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, cash_open_time)
        if cash_bar is None or cash_bar.open <= 0:
            return None

        sessions = self.calendar.sessions_in_range(
            (current_day - timedelta(days=75)).isoformat(),
            (current_day - timedelta(days=1)).isoformat(),
        )
        session_days = [value.date() for value in sessions if value.date() < current_day]
        previous_day = session_days[-1] if session_days else None
        momentum_base_day = session_days[-21] if len(session_days) >= 21 else None

        def close_for(day_value: Optional[date]) -> float:
            if day_value is None:
                return 0.0
            close_time = self.session_times(day_value).close_bar_open.time().replace(second=0, microsecond=0)
            bar = self.m1_bar_at(self.cfg.trade_symbol, day_value, close_time)
            return float(bar.close) if bar is not None and bar.close > 0 else 0.0

        previous_close = close_for(previous_day)
        momentum_base_close = close_for(momentum_base_day)
        momentum20 = (
            previous_close / momentum_base_close - 1.0
            if previous_close > 0 and momentum_base_close > 0
            else None
        )

        premarket_start = datetime.combine(current_day, self.cfg.premarket_start, self.tz)
        query_start = self.local_to_mt5_bar_query_time(premarket_start)
        query_end = self.local_to_mt5_bar_query_time(session.cash_open - timedelta(seconds=1))
        try:
            rates = mt5.copy_rates_range(self.cfg.trade_symbol, mt5.TIMEFRAME_M1, query_start, query_end)
        except Exception:
            rates = None
        premarket_rows = []
        for row in ([] if rates is None else rates):
            local_at = self.mt5_bar_timestamp_to_local(int(row["time"]))
            if premarket_start <= local_at < session.cash_open:
                premarket_rows.append(row)
        premarket_rows.sort(key=lambda row: int(row["time"]))
        return {
            "cashOpen": float(cash_bar.open),
            "previousCashClose": previous_close,
            "previousTradingDay": previous_day.isoformat() if previous_day else "",
            "momentumBaseDay": momentum_base_day.isoformat() if momentum_base_day else "",
            "momentumBaseClose": momentum_base_close,
            "momentum20": momentum20,
            "premarketOpen": float(premarket_rows[0]["open"]) if premarket_rows else 0.0,
            "premarketHigh": max(float(row["high"]) for row in premarket_rows) if premarket_rows else 0.0,
            "premarketLow": min(float(row["low"]) for row in premarket_rows) if premarket_rows else 0.0,
            "premarketClose": float(premarket_rows[-1]["close"]) if premarket_rows else 0.0,
            "premarketBars": len(premarket_rows),
        }

    def loss_control_entry_decision(
        self,
        current_day: date,
        backend_context: dict[str, Any],
        market: Optional[dict[str, Any]],
    ) -> tuple[str, dict[str, Any]]:
        raw_outcomes = backend_context.get("recentOutcomes")
        outcomes = [
            float(item["return"])
            for item in (raw_outcomes if isinstance(raw_outcomes, list) else [])
            if isinstance(item, dict) and isinstance(item.get("return"), (int, float))
        ]
        inputs: dict[str, Any] = {
            "controls": dict(self.entry_rule_controls),
            "controlsRevision": self.entry_rule_controls_revision,
            "recentOutcomes": raw_outcomes if isinstance(raw_outcomes, list) else [],
        }
        if self.entry_rule_controls["ARITHMETIC_LAST_TWO"] and self.arithmetic_entry_rule_trigger(
            outcomes,
            self.cfg.entry_rule_arithmetic_threshold,
        ):
            inputs["arithmeticSum"] = sum(outcomes[-2:])
            return "SKIP_ARITHMETIC", inputs

        market_rules_required = (
            self.entry_rule_controls["GAP_MOMENTUM"]
            or self.entry_rule_controls["PREMARKET_LOW"]
        )
        if market_rules_required and market is None:
            return "WAIT_MARKET_INPUTS", inputs
        if market is not None:
            inputs.update(market)

        if self.entry_rule_controls["PREMARKET_LOW"]:
            if int(inputs.get("premarketBars", 0) or 0) <= 0:
                return "WAIT_MARKET_INPUTS", inputs
            if self.premarket_low_entry_rule_trigger(
                float(inputs.get("premarketOpen", 0.0) or 0.0),
                float(inputs.get("premarketHigh", 0.0) or 0.0),
                float(inputs.get("premarketLow", 0.0) or 0.0),
                float(inputs.get("premarketClose", 0.0) or 0.0),
                self.cfg.entry_rule_premarket_minimum_range,
                self.cfg.entry_rule_premarket_maximum_close_location,
            ):
                span = float(inputs["premarketHigh"]) - float(inputs["premarketLow"])
                inputs["premarketRange"] = span / float(inputs["premarketOpen"])
                inputs["premarketCloseLocation"] = (float(inputs["premarketClose"]) - float(inputs["premarketLow"])) / span
                return "SKIP_PREMARKET_LOW", inputs

        if self.entry_rule_controls["GAP_MOMENTUM"]:
            if (
                float(inputs.get("previousCashClose", 0.0) or 0.0) <= 0
                or inputs.get("momentum20") is None
            ):
                return "WAIT_MARKET_INPUTS", inputs
            gap = float(inputs["cashOpen"]) / float(inputs["previousCashClose"]) - 1.0
            inputs["gap"] = gap
            if self.gap_momentum_entry_rule_trigger(
                float(inputs["cashOpen"]),
                float(inputs["previousCashClose"]),
                float(inputs["momentum20"]),
                self.cfg.entry_rule_gap_threshold,
                self.cfg.entry_rule_momentum20_threshold,
            ):
                return ("DEFER_TUESDAY" if current_day.weekday() == 0 else "SKIP_GAP_MOMENTUM"), inputs
        return "ENTER", inputs

    def refresh_previous_full_week_change(self, previous_day: date) -> None:
        if self.state.prev_open <= 0:
            return
        close_time = self.session_times(previous_day).close_bar_open.time().replace(second=0, microsecond=0)
        close_bar = self.m1_bar_at(self.cfg.trade_symbol, previous_day, close_time)
        if close_bar is None:
            self.log.warning("EVENT PREVIOUS_FULL_WEEK_CHANGE_MISSING day=%s", previous_day)
            return
        self.state.prev_full_week_change = close_bar.close / self.state.prev_open - 1.0
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT PREVIOUS_FULL_WEEK_CHANGE_UPDATED value=%.5f", self.state.prev_full_week_change)

    def minimum_volume_notional(self, info, ask: float) -> float:
        minimum_volume = float(info.volume_min)
        if minimum_volume <= 0:
            raise RuntimeError(f"Invalid minimum volume for {self.cfg.trade_symbol}: {minimum_volume}")
        profit_for_one_percent = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, minimum_volume, ask, ask * 1.01)
        if profit_for_one_percent is None or abs(profit_for_one_percent) <= 0:
            raise RuntimeError(f"Cannot derive minimum-volume notional: {mt5.last_error()}")
        return abs(float(profit_for_one_percent)) / 0.01

    @staticmethod
    def normalized_volume(sizing_units: int, info) -> float:
        if sizing_units <= 0:
            return 0.0
        minimum = float(info.volume_min)
        step = float(info.volume_step)
        maximum = float(info.volume_max)
        if minimum <= 0 or step <= 0 or maximum < minimum:
            return 0.0
        volume = minimum + (sizing_units - 1) * step
        volume = floor_step(volume + step * 1e-9, step)
        volume = min(volume, maximum)
        if volume < minimum - 1e-9:
            return 0.0
        return round(volume, 8)

    @staticmethod
    def maximum_sizing_units(info) -> int:
        minimum = float(info.volume_min)
        step = float(info.volume_step)
        maximum = float(info.volume_max)
        if minimum <= 0 or step <= 0 or maximum < minimum:
            return 0
        return max(1, int(math.floor((maximum - minimum) / step + 1e-9)) + 1)

    def required_balance_sizing(self, balance: float, available_margin: float, info, ask: float, leverage: int) -> dict[str, Any]:
        if balance <= 0:
            raise RuntimeError(f"Account balance must be positive for sizing, got {balance:.2f}")
        if available_margin < 0:
            raise RuntimeError(f"Available margin must not be negative, got {available_margin:.2f}")
        if ask <= 0:
            raise RuntimeError(f"BUY price must be positive for sizing, got {ask}")

        required_balance_multiplier = self.required_balance_multiplier(leverage)
        maximum_units = self.maximum_sizing_units(info)
        if maximum_units <= 0:
            raise RuntimeError(
                f"Invalid volume limits for {self.cfg.trade_symbol}: min={getattr(info, 'volume_min', None)} "
                f"step={getattr(info, 'volume_step', None)} max={getattr(info, 'volume_max', None)}"
            )

        def candidate(units: int) -> dict[str, Any]:
            volume = self.normalized_volume(units, info)
            if volume <= 0:
                raise RuntimeError(f"Cannot normalize sizing unit {units} for {self.cfg.trade_symbol}")
            margin_raw = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, volume, ask)
            if margin_raw is None:
                raise RuntimeError(f"order_calc_margin failed for volume {volume:.8f}: {mt5.last_error()}")
            deposit = float(margin_raw)
            required_balance = deposit * required_balance_multiplier
            affordable = required_balance <= balance + 0.01 and deposit <= available_margin + 0.01
            return {
                "sizingUnits": units, "volume": volume, "requiredDeposit": deposit,
                "requiredBalance": required_balance, "affordable": affordable,
            }

        low = 1
        high = maximum_units
        best: Optional[dict[str, Any]] = None
        while low <= high:
            middle = (low + high) // 2
            current = candidate(middle)
            if bool(current["affordable"]):
                best = current
                low = middle + 1
            else:
                high = middle - 1

        minimum_candidate = candidate(1)
        if best is None:
            raise RuntimeError(
                f"Minimum volume {minimum_candidate['volume']:.8f} requires deposit "
                f"{minimum_candidate['requiredDeposit']:.2f} and balance {minimum_candidate['requiredBalance']:.2f} "
                f"(deposit Ă— {required_balance_multiplier:.3f}); available balance={balance:.2f} "
                f"available margin={available_margin:.2f}"
            )

        next_candidate = candidate(int(best["sizingUnits"]) + 1) if int(best["sizingUnits"]) < maximum_units else None
        return {
            **best,
            "requiredBalanceMultiplier": required_balance_multiplier,
            "minimumVolumeRequiredDeposit": float(minimum_candidate["requiredDeposit"]),
            "minimumVolumeRequiredBalance": float(minimum_candidate["requiredBalance"]),
            "nextVolumeStep": float(next_candidate["volume"]) if next_candidate is not None else 0.0,
            "nextVolumeStepRequiredDeposit": float(next_candidate["requiredDeposit"]) if next_candidate is not None else 0.0,
            "nextVolumeStepRequiredBalance": float(next_candidate["requiredBalance"]) if next_candidate is not None else 0.0,
            "nextVolumeStepAffordable": bool(next_candidate["affordable"]) if next_candidate is not None else False,
        }

    @staticmethod
    def filling_mode_name(mode: int) -> str:
        names = {mt5.ORDER_FILLING_FOK: "FOK", mt5.ORDER_FILLING_IOC: "IOC", mt5.ORDER_FILLING_RETURN: "RETURN"}
        return names.get(mode, str(mode))

    def order_filling_modes(self, info) -> list[int]:
        configured = str(self.cfg.filling_mode).strip().upper()
        mapping = {"FOK": mt5.ORDER_FILLING_FOK, "IOC": mt5.ORDER_FILLING_IOC, "RETURN": mt5.ORDER_FILLING_RETURN}
        if configured in mapping:
            return [mapping[configured]]

        flags = int(getattr(info, "filling_mode", 0))
        symbol_fok = int(getattr(mt5, "SYMBOL_FILLING_FOK", 1))
        symbol_ioc = int(getattr(mt5, "SYMBOL_FILLING_IOC", 2))
        execution = int(getattr(info, "trade_exemode", -1))
        market_execution = int(getattr(mt5, "SYMBOL_TRADE_EXECUTION_MARKET", 2))

        modes: list[int] = []
        if flags & symbol_fok:
            modes.append(mt5.ORDER_FILLING_FOK)
        if flags & symbol_ioc:
            modes.append(mt5.ORDER_FILLING_IOC)
        if execution != market_execution:
            modes.append(mt5.ORDER_FILLING_RETURN)
        for mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC):
            if mode not in modes:
                modes.append(mode)
        if execution != market_execution and mt5.ORDER_FILLING_RETURN not in modes:
            modes.append(mt5.ORDER_FILLING_RETURN)
        return modes

    def checked_deal_request(self, request_base: dict[str, Any], info, event: str) -> tuple[dict[str, Any], Any]:
        last_request = dict(request_base)
        last_check = None
        invalid_fill = int(getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030))
        for mode in self.order_filling_modes(info):
            request = dict(request_base)
            request["type_filling"] = mode
            check = mt5.order_check(request)
            last_request, last_check = request, check
            if check is None:
                continue
            if int(check.retcode) in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
                self.log.info("EVENT FILLING_SELECTED event=%s mode=%s", event, self.filling_mode_name(mode))
                return request, check
            if int(check.retcode) != invalid_fill:
                return request, check
        return last_request, last_check

    def request_allowed_now(self) -> bool:
        elapsed = time_module.monotonic() - self.last_trade_request_monotonic
        if elapsed < self.cfg.request_retry_seconds:
            return False
        self.last_trade_request_monotonic = time_module.monotonic()
        return True

    def trade_request_role_allowed(self, event: str) -> bool:
        if not self.is_executor:
            self.log.critical("EVENT TRADE_BLOCKED_BY_ROLE role=%s account=%s event=%s action=none", self.role, self.account, event)
            return False
        if not self.selected_account_matches():
            self.log.critical("EVENT TRADE_BLOCKED_BY_ACCOUNT_MISMATCH selected_account=%s expected_login=%s event=%s action=none", self.account, getattr(self.cfg, "login", 0), event)
            return False
        if not self.coordinator.role_lease_valid():
            self.log.critical(
                "EVENT TRADE_BLOCKED_BY_GLOBAL_LEASE account=%s event=%s "
                "owner_id=%s fencing_token=%s action=none",
                self.account, event, self.coordinator.owner_id,
                self.coordinator.fencing_token,
            )
            return False
        return True

    def send_buy(self, current_day: date, scheduled_at: Optional[datetime] = None) -> bool:
        if not self.trade_request_role_allowed("BUY"):
            return False
        account = mt5.account_info()
        info = mt5.symbol_info(self.cfg.trade_symbol)
        tick = self.require_fresh_tick(self.cfg.trade_symbol)
        if account is None or info is None:
            raise RuntimeError(f"Cannot obtain account/symbol data: {mt5.last_error()}")

        leverage = self.choose_leverage()
        ask = float(tick.ask)
        minimum_volume_notional = self.minimum_volume_notional(info, ask)
        try:
            sizing = self.required_balance_sizing(
                float(account.balance), max(0.0, float(getattr(account, "margin_free", 0.0) or 0.0)), info, ask, leverage,
            )
        except RuntimeError as exc:
            self.log.error(
                "EVENT BUY_SKIPPED reason=required_balance_sizing_failed balance=%.2f free_margin=%.2f "
                "required_balance_multiplier=%.3f error=%s",
                float(account.balance), float(getattr(account, "margin_free", 0.0) or 0.0),
                self.required_balance_multiplier(leverage), shlex.quote(str(exc)),
            )
            return False

        required_balance_multiplier = float(sizing["requiredBalanceMultiplier"])
        sizing_units = int(sizing["sizingUnits"])
        volume = float(sizing["volume"])
        required_deposit = float(sizing["requiredDeposit"])
        required_balance = float(sizing["requiredBalance"])
        position_notional = minimum_volume_notional * (volume / float(info.volume_min))
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        sl, sl_profit, account_loss_cap_applied = self.capped_hard_stop(
            self.cfg.trade_symbol, volume, ask, float(account.balance), leverage, tick_size,
        )
        request_base = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": self.cfg.trade_symbol, "volume": volume,
            "type": mt5.ORDER_TYPE_BUY, "price": ask, "sl": sl, "tp": 0.0,
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": f"{self.cfg.comment_prefix} L{leverage}"[:31], "type_time": mt5.ORDER_TIME_GTC,
        }
        scheduled = scheduled_at or self.session_times(current_day).buy_action
        if not self.cfg.live_enabled:
            request = dict(request_base)
            request["type_filling"] = self.order_filling_modes(info)[0]
            self.log.info(
                "EVENT BUY_DRY_RUN day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f "
                "sizing_units=%s required_deposit=%.2f required_balance=%.2f required_balance_multiplier=%.3f "
                "next_volume_step=%.8f next_step_required_balance=%.2f position_notional=%.2f ask=%.5f sl=%.5f "
                "sl_cash=%.2f account_loss_cap=%s filling=%s",
                current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional,
                sizing_units, required_deposit, required_balance, required_balance_multiplier,
                float(sizing["nextVolumeStep"]), float(sizing["nextVolumeStepRequiredBalance"]),
                position_notional, ask, sl, sl_profit, account_loss_cap_applied,
                self.filling_mode_name(request["type_filling"]),
            )
            return False
        if not self.ensure_autotrading_enabled("BUY"):
            return False
        if not self.request_allowed_now():
            return False

        self.state.active_execution_id = uuid.uuid4().hex
        self.state.active_decision_id = self.state.active_decision_id or str((self.last_strategy_decision_payload or {}).get("decisionId", ""))
        self.state.active_strategy_spec_id = self.strategy_specification["specId"]
        self.state.active_strategy_spec_hash = self.strategy_specification["specHash"]
        self.state.execution_scheduled_at = scheduled.isoformat()
        self.state.execution_started_at = datetime.now(UTC).isoformat()
        self.state.execution_fill_confirmed = False
        self.state.execution_position_visible = False
        self.state.first_protection_confirmed = False
        self.state.save(self.cfg.state_file)
        self.execution_stage("SIGNAL", reference_price=ask, scheduled_at=scheduled.isoformat())
        self.execution_stage("DECISION", reference_price=ask, scheduled_at=scheduled.isoformat())

        request, check = self.checked_deal_request(request_base, info, "BUY")
        check_ok = check is not None and int(check.retcode) in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009))
        self.execution_stage("CHECKED", result=check_ok, reference_price=ask, retcode=int(getattr(check, "retcode", -1)) if check is not None else None,
                             filling_mode=self.filling_mode_name(request.get("type_filling", -1)), scheduled_at=scheduled.isoformat())
        self.log.info(
            "EVENT BUY_REQUEST day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f "
            "sizing_units=%s required_deposit=%.2f required_balance=%.2f required_balance_multiplier=%.3f "
            "next_volume_step=%.8f next_step_required_balance=%.2f position_notional=%.2f ask=%.5f sl=%.5f "
            "sl_cash=%.2f account_loss_cap=%s filling=%s",
            current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional,
            sizing_units, required_deposit, required_balance, required_balance_multiplier,
            float(sizing["nextVolumeStep"]), float(sizing["nextVolumeStepRequiredBalance"]),
            position_notional, ask, sl, sl_profit, account_loss_cap_applied,
            self.filling_mode_name(request.get("type_filling", -1)),
        )
        if check is None or int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            if int(getattr(check, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("BUY_CHECK_RETCODE_10027", force_log=True)
            self.log.error("EVENT BUY_CHECK_REJECTED retcode=%s comment=%s", getattr(check, "retcode", None), getattr(check, "comment", mt5.last_error()))
            return False

        execution_id = self.state.active_execution_id or uuid.uuid4().hex
        decision_id = self.state.active_decision_id or str(
            (self.last_strategy_decision_payload or {}).get("decisionId", "")
        )
        week_key = iso_week_key(current_day)
        gate: Optional[TradeExecutionGate] = None
        weekly_entry_claimed = False
        order_send_started = False
        try:
            gate = self.coordinator.acquire_trade_gate("BUY", execution_id)
            claim = self.coordinator.claim_weekly_entry(
                week_key, execution_id, decision_id, gate,
            )
            if not bool(claim.get("claimed", False)):
                existing = claim.get("entry") if isinstance(claim.get("entry"), dict) else {}
                self.log.error(
                    "EVENT BUY_SKIPPED reason=weekly_entry_globally_claimed week=%s "
                    "existing_status=%s existing_execution_id=%s existing_order=%s",
                    week_key, existing.get("status", "unknown"),
                    existing.get("executionId", "unknown"), existing.get("orderTicket", 0),
                )
                return False
            weekly_entry_claimed = True
            if self.managed_position() is not None:
                self.coordinator.complete_weekly_entry(
                    week_key, execution_id, "REJECTED", error="position appeared before order_send",
                )
                self.log.error("EVENT BUY_SKIPPED reason=position_appeared_before_send week=%s", week_key)
                return False
            self.coordinator.validate_trade_gate(gate)
            self.execution_stage("SENT", reference_price=ask, filling_mode=self.filling_mode_name(request.get("type_filling", -1)), scheduled_at=scheduled.isoformat())
            sent_monotonic = time_module.monotonic()
            order_send_started = True
            result = mt5.order_send(request)
            acknowledgement_ms = (time_module.monotonic() - sent_monotonic) * 1000.0
        except Exception as exc:
            if weekly_entry_claimed:
                self.coordinator.complete_weekly_entry(
                    week_key,
                    execution_id,
                    "UNKNOWN" if order_send_started else "REJECTED",
                    error=str(exc),
                )
            self.log.error(
                "EVENT BUY_BLOCKED_BY_GLOBAL_COORDINATION week=%s execution_id=%s error=%s",
                week_key, execution_id, exc,
            )
            return False
        finally:
            if gate is not None:
                self.coordinator.release_trade_gate(gate)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if result is None or int(result.retcode) not in accepted:
            self.coordinator.complete_weekly_entry(
                week_key, execution_id,
                "UNKNOWN" if result is None else "REJECTED",
                result=result,
                error="order_send returned None" if result is None else str(getattr(result, "comment", "rejected")),
            )
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("BUY_RETCODE_10027", force_log=True)
            self.execution_stage("ACCEPTED", result=False, reference_price=ask, retcode=int(getattr(result, "retcode", -1)) if result is not None else None,
                                 filling_mode=self.filling_mode_name(request.get("type_filling", -1)), latency_ms=acknowledgement_ms)
            self.log.error("EVENT BUY_REJECTED retcode=%s comment=%s", getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False

        self.coordinator.complete_weekly_entry(
            week_key, execution_id, "ACCEPTED", result=result,
        )

        self.state.entry_pending_until_utc = int(datetime.now(UTC).timestamp()) + 10
        self.state.open_date = current_day.isoformat()
        self.state.entry_price = ask
        self.state.entry_leverage = leverage
        self.state.prev_open = ask
        self.state.last_entry_week = iso_week_key(current_day)
        self.state.entry_signal_daily_open = self.signal_cash_open(self.cfg.signal_symbol, current_day) or 0.0
        self.state.entry_signal_open_pending = self.state.entry_signal_daily_open <= 0
        self.state.break_even = False
        self.clear_current_position_exit_state(clear_last_exit=True)
        self.state.active_sl_reason = "SL"
        self.state.active_sl_price = sl
        self.state.save(self.cfg.state_file)
        if self.state.entry_signal_open_pending:
            self.log.info(
                "EVENT ENTRY_SIGNAL_OPEN_PENDING day=%s symbol=%s capture_at=%s entry_fill_reference=not_used",
                current_day, self.cfg.signal_symbol, self.session_times(current_day).cash_open.isoformat(),
            )
        actual_price = float(getattr(result, "price", 0.0) or ask)
        self.execution_stage("ACCEPTED", reference_price=ask, actual_price=actual_price, retcode=int(result.retcode),
                             filling_mode=self.filling_mode_name(request.get("type_filling", -1)), latency_ms=acknowledgement_ms,
                             order_ticket=int(getattr(result, "order", 0) or 0), deal_ticket=int(getattr(result, "deal", 0) or 0),
                             side="BUY", volume=float(volume))
        if int(getattr(result, "deal", 0) or 0) > 0:
            self.execution_stage("FILLED", reference_price=ask, actual_price=actual_price, retcode=int(result.retcode),
                                 filling_mode=self.filling_mode_name(request.get("type_filling", -1)), latency_ms=acknowledgement_ms,
                                 order_ticket=int(getattr(result, "order", 0) or 0), deal_ticket=int(getattr(result, "deal", 0) or 0),
                                 side="BUY", volume=float(volume))
            self.state.execution_fill_confirmed = True
            self.state.save(self.cfg.state_file)
        self.log.info("EVENT BUY_ACCEPTED retcode=%s order=%s deal=%s", result.retcode, getattr(result, "order", 0), getattr(result, "deal", 0))
        return True

    def modify_sltp(self, position, desired_sl: float, desired_tp: float, reason: str, sl_reason: str = "", tp_reason: str = "") -> bool:
        if not self.trade_request_role_allowed(f"SLTP_{reason}"):
            return False
        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        digits = int(info.digits)
        desired_sl = ceil_step(ceil_whole_sl(desired_sl), tick_size) if desired_sl else 0.0
        desired_tp = round(desired_tp, digits) if desired_tp else 0.0
        tolerance = max(tick_size * 0.5, float(info.point) * 0.5)
        sl_already_installed = (
            desired_sl > 0
            and float(getattr(position, "sl", 0.0) or 0.0) > 0
            and not price_changed(float(position.sl), desired_sl, tolerance)
        )
        if desired_sl > 0 and not sl_already_installed:
            tick = self.latest_tick(position.symbol)
            maximum_valid_sl = float(getattr(tick, "bid", 0.0) or 0.0) - self.broker_minimum_distance(info)
            if maximum_valid_sl > 0 and desired_sl >= maximum_valid_sl:
                desired_sl = floor_step(math.floor(maximum_valid_sl - 1e-9), tick_size)
        desired_sl = round(desired_sl, digits) if desired_sl > 0 else 0.0

        if not price_changed(float(position.sl), desired_sl, tolerance) and not price_changed(float(position.tp), desired_tp, tolerance):
            self.record_active_protection(position, desired_sl, desired_tp, sl_reason, tp_reason)
            if desired_sl > 0 and not self.state.first_protection_confirmed:
                self.state.first_protection_confirmed = True
                self.state.save(self.cfg.state_file)
                self.execution_stage(
                    "PROTECTED", position_ticket=int(position.ticket), actual_price=desired_sl,
                    reason=f"{reason}:confirmed_existing", old_sl=float(position.sl), new_sl=desired_sl,
                    old_tp=float(position.tp), new_tp=desired_tp,
                )
            return True

        if not self.cfg.live_enabled:
            self.log.info(
                "EVENT SLTP_DRY_RUN reason=%s ticket=%s SL=%.5f->%.5f TP=%.5f->%.5f",
                reason, position.ticket, float(position.sl), desired_sl, float(position.tp), desired_tp,
            )
            return False
        if not self.ensure_autotrading_enabled("SLTP"):
            return False
        if not self.request_allowed_now():
            return False

        self.log.info(
            "EVENT SLTP_REQUEST reason=%s ticket=%s SL=%.5f->%.5f TP=%.5f->%.5f",
            reason, position.ticket, float(position.sl), desired_sl, float(position.tp), desired_tp,
        )
        self.execution_stage(
            "PROTECTION_REQUESTED", position_ticket=int(position.ticket), reason=reason,
            old_sl=float(position.sl), new_sl=desired_sl, old_tp=float(position.tp), new_tp=desired_tp,
        )
        request = {
            "action": mt5.TRADE_ACTION_SLTP, "symbol": position.symbol, "position": int(position.ticket),
            "sl": desired_sl, "tp": desired_tp, "magic": self.cfg.magic,
        }
        operation_id = f"SLTP-{int(position.ticket)}-{uuid.uuid4().hex}"
        gate: Optional[TradeExecutionGate] = None
        try:
            gate = self.coordinator.acquire_trade_gate("SLTP", operation_id)
            self.coordinator.validate_trade_gate(gate)
            result = mt5.order_send(request)
        except Exception as exc:
            self.log.error(
                "EVENT SLTP_BLOCKED_BY_GLOBAL_COORDINATION reason=%s ticket=%s error=%s",
                reason, position.ticket, exc,
            )
            return False
        finally:
            if gate is not None:
                self.coordinator.release_trade_gate(gate)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_NO_CHANGES", 10025)}
        if result is None or int(result.retcode) not in accepted:
            self.execution_stage(
                "PROTECTION_REJECTED", result=False, position_ticket=int(position.ticket), reason=reason,
                retcode=int(getattr(result, "retcode", -1)) if result is not None else None,
                old_sl=float(position.sl), new_sl=desired_sl, old_tp=float(position.tp), new_tp=desired_tp,
            )
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("SLTP_RETCODE_10027", force_log=True)
            self.log.error("EVENT SLTP_REJECTED reason=%s retcode=%s comment=%s", reason, getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False

        was_protected = self.state.first_protection_confirmed
        self.record_active_protection(position, desired_sl, desired_tp, sl_reason, tp_reason)
        self.state.first_protection_confirmed = True
        self.state.save(self.cfg.state_file)
        self.execution_stage("MODIFIED" if was_protected else "PROTECTED", position_ticket=int(position.ticket), actual_price=desired_sl,
                             retcode=int(result.retcode), reason=reason,
                             old_sl=float(position.sl), new_sl=desired_sl, old_tp=float(position.tp), new_tp=desired_tp)
        self.log.info("EVENT SLTP_ACCEPTED reason=%s retcode=%s", reason, result.retcode)
        return True

    def close_position_market(self, position, reason: str, now: datetime) -> bool:
        if not self.trade_request_role_allowed(f"SELL_{reason}"):
            return False
        reason_log = shlex.quote(reason)
        info = mt5.symbol_info(position.symbol)
        tick = self.require_fresh_tick(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

        bid = float(tick.bid)
        request_base = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol, "position": int(position.ticket),
            "volume": float(position.volume), "type": mt5.ORDER_TYPE_SELL, "price": bid,
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": f"{self.cfg.comment_prefix} {reason}"[:31], "type_time": mt5.ORDER_TIME_GTC,
        }
        if not self.cfg.live_enabled:
            self.log.info("EVENT SELL_DRY_RUN reason=%s ticket=%s volume=%s bid=%.5f", reason_log, position.ticket, position.volume, bid)
            return False
        if not self.ensure_autotrading_enabled(f"SELL_{reason}"):
            return False
        if not self.request_allowed_now():
            return False

        request, check = self.checked_deal_request(request_base, info, f"SELL_{reason}")
        exit_check_ok = check is not None and int(check.retcode) in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009))
        self.execution_stage("EXIT_CHECKED", result=exit_check_ok, position_ticket=int(position.ticket), reference_price=bid,
                             retcode=int(getattr(check, "retcode", -1)) if check is not None else None,
                             filling_mode=self.filling_mode_name(request.get("type_filling", -1)), reason=reason)
        if not exit_check_ok:
            if int(getattr(check, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled(f"SELL_{reason}_CHECK_RETCODE_10027", force_log=True)
            self.log.error("EVENT SELL_CHECK_REJECTED reason=%s retcode=%s comment=%s", reason_log, getattr(check, "retcode", None), getattr(check, "comment", mt5.last_error()))
            return False

        self.state.exit_latched_reason = reason
        self.state.exit_latched_at = now.isoformat()
        # Preserve the market-SELL reference immediately so a concurrent
        # publisher cannot fall back to an older installed SL while the order
        # acknowledgement is still in flight.  A confirmed deal price below
        # replaces this reference before the executor returns to its loop.
        self.state.last_exit_price = bid
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT SELL_REQUEST reason=%s ticket=%s volume=%s bid=%.5f", reason_log, position.ticket, position.volume, bid)
        self.execution_stage("EXIT_SENT", position_ticket=int(position.ticket), reference_price=bid, reason=reason)
        operation_id = f"SELL-{reason}-{int(position.ticket)}-{uuid.uuid4().hex}"
        gate: Optional[TradeExecutionGate] = None
        try:
            gate = self.coordinator.acquire_trade_gate(f"SELL_{reason}", operation_id)
            self.coordinator.validate_trade_gate(gate)
            exit_sent_monotonic = time_module.monotonic()
            result = mt5.order_send(request)
            exit_ack_ms = (time_module.monotonic() - exit_sent_monotonic) * 1000.0
        except Exception as exc:
            self.log.error(
                "EVENT SELL_BLOCKED_BY_GLOBAL_COORDINATION reason=%s ticket=%s error=%s",
                reason_log, position.ticket, exc,
            )
            return False
        finally:
            if gate is not None:
                self.coordinator.release_trade_gate(gate)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if result is None or int(result.retcode) not in accepted:
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled(f"SELL_{reason}_RETCODE_10027", force_log=True)
            self.execution_stage("EXIT_ACCEPTED", result=False, position_ticket=int(position.ticket), reference_price=bid,
                                 retcode=int(getattr(result, "retcode", -1)) if result is not None else None,
                                 filling_mode=self.filling_mode_name(request.get("type_filling", -1)), reason=reason, latency_ms=exit_ack_ms)
            self.log.error("EVENT SELL_REJECTED reason=%s retcode=%s comment=%s", reason_log, getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False
        actual_price = float(getattr(result, "price", 0.0) or bid)
        self.execution_stage("EXIT_ACCEPTED", position_ticket=int(position.ticket), reference_price=bid,
                             actual_price=actual_price, retcode=int(result.retcode), reason=reason, latency_ms=exit_ack_ms,
                             order_ticket=int(getattr(result, "order", 0) or 0), deal_ticket=int(getattr(result, "deal", 0) or 0),
                             side="SELL", volume=float(position.volume), filling_mode=self.filling_mode_name(request.get("type_filling", -1)))
        if int(getattr(result, "deal", 0) or 0) > 0:
            self.state.last_exit_price = actual_price
            self.state.save(self.cfg.state_file)
            self.execution_stage(
                "EXIT_FILLED", position_ticket=int(position.ticket), reference_price=bid,
                actual_price=actual_price, retcode=int(result.retcode), reason=reason,
                latency_ms=exit_ack_ms, order_ticket=int(getattr(result, "order", 0) or 0),
                deal_ticket=int(getattr(result, "deal", 0) or 0), side="SELL", volume=float(position.volume),
                filling_mode=self.filling_mode_name(request.get("type_filling", -1)),
            )
        self.log.info("EVENT SELL_ACCEPTED reason=%s retcode=%s", reason_log, result.retcode)
        return True

    @staticmethod
    def broker_minimum_distance(info) -> float:
        point = float(info.point)
        stops = int(getattr(info, "trade_stops_level", 0)) * point
        freeze = int(getattr(info, "trade_freeze_level", 0)) * point
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or point)
        return max(stops, freeze, tick_size) + tick_size

    def arm_exit(self, position, reason: str, now: datetime) -> None:
        if not self.state.exit_latched_reason:
            self.state.exit_latched_reason = reason
            self.state.exit_latched_at = now.isoformat()
            self.state.save(self.cfg.state_file)
            self.log.warning("EVENT EXIT_LATCHED reason=%s", reason)
        self.apply_exit_bracket(position, self.state.exit_latched_reason)

    def apply_exit_bracket(self, position, reason: str) -> bool:
        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")
        tick = self.fresh_tick_for_protection(position, f"EXIT_{reason}")
        if tick is None:
            return False

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        distance = self.broker_minimum_distance(info)
        bid = float(tick.bid)
        ask = float(tick.ask)
        sl = floor_step(bid - distance, tick_size)
        tp = ceil_step(ask + distance, tick_size)
        if float(position.sl) > 0 and float(position.sl) < bid and float(position.sl) > sl:
            sl = float(position.sl)
        if float(position.tp) > ask and float(position.tp) < tp:
            tp = float(position.tp)
        return self.modify_sltp(position, sl, tp, f"EXIT_{reason}", reason, reason)

    def apply_standard_protection(self, position, now: datetime) -> bool:
        if self.state.exit_latched_reason:
            return self.apply_exit_bracket(position, self.state.exit_latched_reason)

        if not self.immutable_hard_stop_matches(position):
            self.lock_immutable_hard_stop(position, now, "PROTECTION_RECONCILIATION")

        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")
        tick = self.fresh_tick_for_protection(position, "STANDARD")
        if tick is None:
            return False

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        distance = self.broker_minimum_distance(info)
        bid = float(tick.bid)
        ask = float(tick.ask)

        desired_sl, sl_reason = self.weekday_sl_target(position, now)
        desired_tp = float(position.price_open) * self.cfg.break_even_ratio if self.state.break_even else 0.0
        tp_reason = "BH" if desired_tp > 0 else ""
        tolerance = max(tick_size * 0.5, float(info.point) * 0.5)
        current_broker_sl = float(getattr(position, "sl", 0.0) or 0.0)
        desired_sl = ceil_step(ceil_whole_sl(desired_sl), tick_size)
        max_valid_sl = bid - distance
        desired_sl_already_installed = False

        # TSL is an executable price threshold, not merely a desired broker
        # modification. If a gap or any other move places the live bid at or
        # below the normalized TSL before it can be installed or restored,
        # close immediately through the globally fenced market-SELL path.
        if sl_reason == "TSL":
            tsl_threshold = ceil_step(
                ceil_whole_sl(float(position.price_open) * self.cfg.tsl_ratio), tick_size,
            )
            if bid <= tsl_threshold:
                self.log.warning(
                    "EVENT TSL_MARKET_EXIT_REQUIRED ticket=%s bid=%.5f threshold=%.5f "
                    "entry=%.5f ratio=%.6f reason=threshold_crossed",
                    int(position.ticket), bid, tsl_threshold,
                    float(position.price_open), self.cfg.tsl_ratio,
                )
                self.tsl_install_deferred = False
                # Retain the established taxonomy for a Thursday premarket
                # gap through the newly-active TSL threshold.  Later TSL
                # market exits keep the unified TSL label.
                tsl_exit_reason = (
                    "TSL1PRE"
                    if now.weekday() == 3 and now < self.session_times(now.date()).cash_open
                    else "TSL"
                )
                return self.close_position_market(position, tsl_exit_reason, now)

            tsl_already_installed = (
                current_broker_sl > 0
                and current_broker_sl >= tsl_threshold - tolerance
            )
            if tsl_already_installed:
                desired_sl = current_broker_sl
                desired_sl_already_installed = True
                self.tsl_install_deferred = False
            elif desired_sl >= max_valid_sl:
                if not self.tsl_install_deferred:
                    self.log.warning(
                        "EVENT TSL_INSTALL_DEFERRED ticket=%s bid=%.5f threshold=%.5f "
                        "max_valid_sl=%.5f existing_sl=%.5f retry=next_cycle",
                        int(position.ticket), bid, tsl_threshold, max_valid_sl, current_broker_sl,
                    )
                self.tsl_install_deferred = True
                return True
            else:
                if self.tsl_install_deferred:
                    self.log.info(
                        "EVENT TSL_INSTALL_RETRY_READY ticket=%s bid=%.5f threshold=%.5f max_valid_sl=%.5f",
                        int(position.ticket), bid, tsl_threshold, max_valid_sl,
                    )
                self.tsl_install_deferred = False
        else:
            self.tsl_install_deferred = False

        # Never weaken protection already present at the broker. The immutable
        # baseline is the floor; TSL and any existing tighter broker SL are the
        # only values allowed to raise it.
        if self.state.first_protection_confirmed and current_broker_sl > desired_sl:
            desired_sl = current_broker_sl
            desired_sl_already_installed = True
            if sl_reason == "SL":
                sl_reason = self.state.active_sl_reason or "BROKER_TIGHTER_SL"

        if (
            self.state.first_protection_confirmed
            and current_broker_sl > 0
            and not price_changed(current_broker_sl, desired_sl, tolerance)
        ):
            desired_sl_already_installed = True

        min_valid_tp = ask + distance
        if not desired_sl_already_installed and desired_sl >= max_valid_sl:
            self.arm_exit(position, "PROTECTION_SL_ALREADY_CROSSED", now)
            return False
        if desired_tp > 0 and desired_tp <= min_valid_tp:
            return self.close_position_market(position, "BH", now)

        desired_tp = ceil_step(desired_tp, tick_size) if desired_tp > 0 else 0.0
        leverage = int(self.state.immutable_hard_sl_leverage or self.state.entry_leverage or self.choose_leverage())
        reason_parts = [
            f"IMMUTABLE_HARD_SL_L{leverage}_RATIO_{self.hard_sl_ratio(leverage):.6f}"
        ]
        if self.state.immutable_hard_sl_account_loss_cap_applied:
            reason_parts.append("ACCOUNT_LOSS_CAP_50_PERCENT")
        if sl_reason == "TSL":
            reason_parts.append(f"TSL_STOP_{self.cfg.tsl_stop:.4%}_RATIO_{self.cfg.tsl_ratio:.6f}")
        if desired_tp > 0:
            reason_parts.append(f"BE_{self.cfg.break_even_ratio:.6f}")
        return self.modify_sltp(position, desired_sl, desired_tp, "+".join(reason_parts), sl_reason, tp_reason)

    def evaluate_premarket_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        if self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.close_position_market(position, "BEPRE", now)
            return

        premarket_tpp = self.premarket_high_tpp(position, bar.local_datetime)
        if premarket_tpp is None:
            return
        threshold = entry * (1.0 + premarket_tpp)
        condition = bar.open > threshold
        self.log.info(
            "EVENT PREMARKET_CHECK name='PRE H' result=%s time=%s bar_open=%.5f entry=%.5f "
            "tpp=%.8f threshold=%.5f session_index=%s",
            condition, bar.local_datetime.isoformat(), bar.open, entry, premarket_tpp,
            threshold, self.trading_session_index(bar.local_datetime.date()),
        )
        if condition:
            self.close_position_market(position, "PRE H", now)

    def evaluate_cash_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        if self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.close_position_market(position, "BEO", now)

    def evaluate_regular_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if self.state.exit_latched_reason:
            return
        entry = float(position.price_open)
        # A break-even state armed immediately after today's CH check applies
        # from the following session. Do not use an earlier high from the same
        # day's already-forming M1 candle to trigger BH retroactively.
        armed_during_today_close = self.state.last_close_action_date == bar.local_datetime.date().isoformat()
        if self.state.break_even and not armed_during_today_close and bar.high > entry * self.cfg.break_even_ratio:
            self.close_position_market(position, "BH", now)

    def process_completed_close(self, current_day: date, now: datetime, position) -> None:
        day_key = current_day.isoformat()
        if self.state.last_close_processed_date == day_key:
            return

        close_time = self.session_times(current_day).close_bar_open.time().replace(second=0, microsecond=0)
        trade_close_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, close_time)
        signal_close_bar = self.m1_bar_at(self.cfg.signal_symbol, current_day, close_time)
        if trade_close_bar is None or signal_close_bar is None:
            return

        weekday = current_day.weekday()
        if self.state.prev_open > 0 and self.final_trading_day(current_day) == current_day:
            self.state.prev_full_week_change = trade_close_bar.close / self.state.prev_open - 1.0
            self.log.info("EVENT FULL_WEEK_CHANGE_UPDATED value=%.5f day=%s", self.state.prev_full_week_change, current_day)

        self.state.last_trading_date = day_key
        self.state.last_close_processed_date = day_key
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT DAILY_CLOSE_PROCESSED day=%s trade_close=%.5f signal_close=%.5f", current_day, trade_close_bar.close, signal_close_bar.close)

    def process_new_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if bar.utc_timestamp == self.state.last_processed_bar_utc:
            return
        self.state.last_processed_bar_utc = bar.utc_timestamp
        self.state.save(self.cfg.state_file)
        if position is None:
            return

        session = self.session_times(bar.local_datetime.date())
        bar_time = bar.local_datetime.time().replace(second=0, microsecond=0)
        cash_open_time = session.cash_open.time().replace(second=0, microsecond=0)
        if self.cfg.premarket_start <= bar_time < cash_open_time:
            self.evaluate_premarket_open(position, bar, now)
        elif bar_time == cash_open_time:
            self.evaluate_cash_open(position, bar, now)

    def maybe_open_new_week(self, current_day: date, now: datetime, current_bar: Optional[M1Bar], position) -> None:
        if position is not None or self.state.exit_latched_reason or current_day.weekday() not in (0, 1):
            return
        week = iso_week_key(current_day)
        session = self.session_times(current_day)
        context_lead_seconds = max(1.0, float(getattr(self.cfg, "monitor_publish_interval_seconds", 5.0)))
        if now < session.buy_action - timedelta(seconds=context_lead_seconds):
            return
        try:
            backend_context = self.refresh_entry_rule_context(current_day)
        except Exception as exc:
            now_monotonic = time_module.monotonic()
            if now_monotonic - self.last_entry_rule_error_monotonic >= float(self.cfg.monitor_error_log_interval_seconds):
                self.last_entry_rule_error_monotonic = now_monotonic
                self.log.error(
                    "EVENT ENTRY_RULE_CONTEXT_UNAVAILABLE week=%s action=none error=%s",
                    week, shlex.quote(str(exc)),
                )
            return

        week_state = backend_context.get("weekState") if isinstance(backend_context.get("weekState"), dict) else None
        week_status = str((week_state or {}).get("status", ""))
        new_week_entry = self.is_new_week_entry(current_day)
        if not new_week_entry and week_status not in {"ENTRY_APPROVED", "DEFER_TUESDAY", "TUESDAY_REENTRY"}:
            return
        if week_status.startswith("SKIP_"):
            self.remember_entry_rule_decision(current_day, week_status, dict((week_state or {}).get("inputs") or {}))
            return

        latest_entry = session.cash_open + timedelta(seconds=self.cfg.entry_window_seconds)
        premarket_enabled = self.entry_rule_controls["PREMARKET_LOW"]
        approved_inputs = dict((week_state or {}).get("inputs") or {}) if week_status == "ENTRY_APPROVED" else {}
        cash_open_required = (
            bool(approved_inputs.get("cashOpenRequired"))
            if week_status == "ENTRY_APPROVED"
            else (
                self.entry_rule_controls["GAP_MOMENTUM"]
                or premarket_enabled
                or week_status in {"DEFER_TUESDAY", "TUESDAY_REENTRY"}
            )
        )
        scheduled_at = session.cash_open if cash_open_required else session.buy_action
        if now < scheduled_at:
            return
        if now > latest_entry:
            if self.state.last_missed_entry_week != week:
                self.state.active_execution_id = uuid.uuid4().hex
                self.state.active_decision_id = self.state.active_decision_id or str((self.last_strategy_decision_payload or {}).get("decisionId", ""))
                self.state.active_strategy_spec_id = self.strategy_specification["specId"]
                self.state.active_strategy_spec_hash = self.strategy_specification["specHash"]
                self.state.execution_scheduled_at = scheduled_at.isoformat()
                self.state.execution_started_at = datetime.now(UTC).isoformat()
                self.state.last_missed_entry_week = week
                self.state.save(self.cfg.state_file)
                self.execution_stage("MISSED_WINDOW", result=False, scheduled_at=scheduled_at.isoformat(), reason="entry_window_elapsed")
                self.log.error("EVENT ENTRY_WINDOW_MISSED week=%s scheduled=%s latest_entry=%s now=%s", week, scheduled_at.isoformat(), latest_entry.isoformat(), now.isoformat())
            return
        if int(datetime.now(UTC).timestamp()) < self.state.entry_pending_until_utc:
            return

        if week_status == "ENTRY_APPROVED":
            self.remember_entry_rule_decision(current_day, "ENTER", approved_inputs)
            self.send_buy(current_day, scheduled_at=scheduled_at)
            return

        if week_status in {"DEFER_TUESDAY", "TUESDAY_REENTRY"}:
            if current_day.weekday() != 1:
                return
            inputs = dict((week_state or {}).get("inputs") or {})
            if week_status == "DEFER_TUESDAY":
                cash_open_time = session.cash_open.time().replace(second=0, microsecond=0)
                cash_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, cash_open_time)
                if cash_bar is None or cash_bar.open <= 0:
                    return
                friday_close = float(inputs.get("previousCashClose", 0.0) or 0.0)
                tuesday_open = float(cash_bar.open)
                inputs["tuesdayOpen"] = tuesday_open
                inputs["fridayClose"] = friday_close
                normalized = (
                    not self.entry_rule_controls["TUESDAY_NORMALIZATION"]
                    or self.normalized_tuesday_entry_rule(
                        friday_close,
                        tuesday_open,
                        self.cfg.entry_rule_tuesday_normalization_tolerance,
                    )
                )
                status = "TUESDAY_REENTRY" if normalized else "SKIP_TUESDAY_NOT_NORMALIZED"
                try:
                    backend_context = self.record_entry_rule_week_state(current_day, status, inputs)
                except Exception as exc:
                    self.log.error(
                        "EVENT ENTRY_RULE_WEEK_STATE_FAILED week=%s status=%s action=none error=%s",
                        week, status, shlex.quote(str(exc)),
                    )
                    return
                self.remember_entry_rule_decision(current_day, status, inputs)
                self.log.info(
                    "EVENT ENTRY_RULE_DECISION week=%s status=%s controls_revision=%s friday_close=%.5f tuesday_open=%.5f normalized=%s",
                    week, status, self.entry_rule_controls_revision, friday_close, tuesday_open, normalized,
                )
                if not normalized:
                    return
            self.send_buy(current_day, scheduled_at=session.cash_open)
            return

        previous = self.previous_trading_date(current_day) or parse_date(self.state.last_trading_date)
        if previous is not None:
            self.refresh_previous_full_week_change(previous)
        market = self.entry_rule_market_context(current_day) if cash_open_required else None
        status, inputs = self.loss_control_entry_decision(current_day, backend_context, market)
        if status == "WAIT_MARKET_INPUTS":
            return
        if status != "ENTER":
            try:
                self.record_entry_rule_week_state(current_day, status, inputs)
            except Exception as exc:
                self.log.error(
                    "EVENT ENTRY_RULE_WEEK_STATE_FAILED week=%s status=%s action=none error=%s",
                    week, status, shlex.quote(str(exc)),
                )
                return
            self.remember_entry_rule_decision(current_day, status, inputs)
            self.log.info(
                "EVENT ENTRY_RULE_DECISION week=%s status=%s controls_revision=%s inputs=%s",
                week, status, self.entry_rule_controls_revision,
                json.dumps(inputs, sort_keys=True, separators=(",", ":")),
            )
            return

        inputs["cashOpenRequired"] = cash_open_required
        inputs["scheduledAt"] = scheduled_at.isoformat()
        try:
            self.record_entry_rule_week_state(current_day, "ENTRY_APPROVED", inputs)
        except Exception as exc:
            self.log.error(
                "EVENT ENTRY_RULE_WEEK_STATE_FAILED week=%s status=ENTRY_APPROVED action=none error=%s",
                week, shlex.quote(str(exc)),
            )
            return
        self.remember_entry_rule_decision(current_day, "ENTER", inputs)
        self.send_buy(current_day, scheduled_at=scheduled_at)

    def maybe_execute_open_action(self, position, now: datetime) -> bool:
        if position is None or self.state.exit_latched_reason:
            return False
        current_day = now.date()
        session = self.session_times(current_day)
        day_key = current_day.isoformat()
        if self.state.last_open_action_date == day_key:
            return False
        if now >= session.cash_open:
            self.state.last_open_action_date = day_key
            self.state.save(self.cfg.state_file)
            return False
        if now < session.open_action:
            return False
        if not self.oh_check_eligible(current_day):
            self.state.last_open_action_date = day_key
            self.state.save(self.cfg.state_file)
            self.log.info(
                "EVENT SCHEDULED_CHECK name=OH skipped=true reason=first_trading_session day=%s scheduled=%s",
                current_day, session.open_action.isoformat(),
            )
            return False

        tick = self.require_fresh_tick(position.symbol)
        bid = float(tick.bid)
        entry = float(position.price_open)
        tpp = self.tpp_for_day(current_day)
        threshold = entry * (1.0 + tpp)
        condition = bid > threshold
        self.log.info("EVENT SCHEDULED_CHECK name=OH result=%s time=%s scheduled=%s bid=%.5f entry=%.5f tpp=%.6f threshold=%.5f", condition, now.isoformat(), session.open_action.isoformat(), bid, entry, tpp, threshold)
        if condition:
            if self.close_position_market(position, "OH", now):
                self.state.last_open_action_date = day_key
                self.state.save(self.cfg.state_file)
                return True
            return False

        self.state.last_open_action_date = day_key
        self.state.save(self.cfg.state_file)
        return False

    def maybe_execute_close_action(self, position, now: datetime) -> bool:
        if position is None:
            return False
        current_day = now.date()
        session = self.session_times(current_day)
        day_key = current_day.isoformat()
        final_day = self.final_trading_day(current_day)
        if self.state.last_close_action_date == day_key or now < session.weekly_close:
            return False

        is_final_day = final_day == current_day
        signal_reference = float(self.state.entry_signal_daily_open or 0.0)
        signal_available = signal_reference > 0 and not self.state.entry_signal_open_pending
        if not signal_available:
            if is_final_day:
                self.log.warning(
                    "EVENT SIGNAL_DEPENDENT_CLOSE_UNAVAILABLE action=CH skipped=true fallback=none final_action=TO"
                )
                if self.close_position_market(position, "TO", now):
                    self.state.last_close_action_date = day_key
                    self.state.save(self.cfg.state_file)
                    return True
                return False
            current = time_module.monotonic()
            if current - self.last_signal_open_pending_log_monotonic >= 60.0:
                self.last_signal_open_pending_log_monotonic = current
                self.log.warning(
                    "EVENT SIGNAL_DEPENDENT_CLOSE_DEFERRED action=CH+BREAK_EVEN reason=signal_cash_open_unavailable retry=true fallback=none"
                )
            return False

        signal_price = self.live_signal_price()
        tpp = self.tpp_for_day(current_day)
        ch_threshold = signal_reference * (1.0 + tpp)
        ch = signal_price > ch_threshold
        self.log.info(
            "EVENT SCHEDULED_CHECK name=CH result=%s time=%s scheduled=%s signal_price=%.5f signal_open=%.5f tpp=%.6f threshold=%.5f final_day=%s",
            ch, now.isoformat(), session.weekly_close.isoformat(), signal_price, signal_reference, tpp, ch_threshold, is_final_day,
        )

        reason = "CH" if ch else "TO" if is_final_day else ""
        if reason:
            if self.close_position_market(position, reason, now):
                self.state.last_close_action_date = day_key
                self.state.save(self.cfg.state_file)
                return True
            return False

        opened = parse_date(self.state.open_date)
        be_threshold = signal_reference * self.cfg.break_even_ratio
        break_even = (
            not self.state.break_even
            and opened is not None
            and self.break_even_check_eligible(opened, current_day)
            and signal_price < be_threshold
        )
        self.log.info(
            "EVENT SCHEDULED_CHECK name=BREAK_EVEN result=%s time=%s scheduled=%s "
            "signal_price=%.5f signal_open=%.5f ratio=%.6f threshold=%.5f after_ch=true",
            break_even, now.isoformat(), session.weekly_close.isoformat(),
            signal_price, signal_reference, self.cfg.break_even_ratio, be_threshold,
        )
        if break_even:
            self.state.break_even = True
            self.state.save(self.cfg.state_file)
            self.log.info(
                "EVENT BREAK_EVEN_ARMED day=%s signal_price=%.5f threshold=%.5f source=AFTER_CH",
                current_day, signal_price, be_threshold,
            )
            self.emit_status("BREAK_EVEN_ARMED", position, now)

        self.state.last_close_action_date = day_key
        self.state.save(self.cfg.state_file)
        return False
