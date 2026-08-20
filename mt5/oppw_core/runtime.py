"""Runtime behavior for the canonical strategy composition."""

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


class RuntimeMixin:
    def log_check(self, now: datetime, name: str, result: bool, **values: Any) -> None:
        details = " ".join(f"{key}={value}" for key, value in values.items() if value is not None)
        self.log.info(
            "CHECK minute=%s weekday=%s phase=%s name=%s result=%s%s",
            now.strftime("%Y-%m-%d_%H:%M"), now.strftime("%A"), self.phase(now), name,
            "TRUE" if result else "FALSE", f" {details}" if details else "",
        )

    def log_minute_condition_report(self, position, now: datetime, current_bar: Optional[M1Bar]) -> None:
        self.log.info("CONDITION_REPORT_BEGIN minute=%s", now.strftime("%Y-%m-%d %H:%M"))
        if position is None:
            current_day = now.date()
            new_week = self.is_new_week_entry(current_day)
            session = self.session_times(current_day)
            self.log_check(now, "POSITION_IS_OPEN", False)
            self.log_check(now, "NEW_WEEK_ENTRY", new_week)
            self.log_check(now, "BUY_TIME_REACHED", now >= session.buy_action, scheduled=session.buy_action.strftime("%H:%M:%S"))
            self.log.info("CONDITION_REPORT_END minute=%s checks=3", now.strftime("%Y-%m-%d %H:%M"))
            return

        entry = float(position.price_open)
        self.log_check(now, "POSITION_IS_OPEN", True, ticket=position.ticket, entry=entry, volume=position.volume)
        opened = parse_date(self.state.open_date)
        signal_capture_at = self.session_times(opened).cash_open.isoformat() if opened is not None else "unknown"
        self.log_check(
            now,
            "ENTRY_SIGNAL_OPEN_AVAILABLE",
            self.state.entry_signal_daily_open > 0 and not self.state.entry_signal_open_pending,
            signal_open=self.state.entry_signal_daily_open,
            pending=self.state.entry_signal_open_pending,
            capture_at=signal_capture_at,
            fallback="none",
        )
        self.log_check(now, "EXIT_LATCH_CLEAR", not bool(self.state.exit_latched_reason), exit_latch=self.state.exit_latched_reason or "none")

        check_count = 3
        if self.oh_check_pending(now, position):
            try:
                tick = self.require_fresh_tick(position.symbol)
                bid = float(tick.bid)
                tpp = self.tpp_for_day(now.date())
                self.log_check(now, "OH", bid > entry * (1.0 + tpp), bid=bid, threshold=entry * (1.0 + tpp))
                premarket_tpp = self.premarket_high_tpp(position, now)
                if premarket_tpp is not None:
                    self.log_check(
                        now, shlex.quote("PRE H"), bid > entry * (1.0 + premarket_tpp), bid=bid,
                        tpp=f"{premarket_tpp:.8f}", threshold=entry * (1.0 + premarket_tpp),
                    )
                    check_count += 1
            except RuntimeError as exc:
                self.log_check(now, "OH", False, error=str(exc))
            check_count += 1

        desired_sl, sl_reason = self.weekday_sl_target(position, now)
        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        desired_sl = ceil_step(ceil_whole_sl(desired_sl), tick_size)
        sl_set = float(position.sl) > 0 and abs(float(position.sl) - desired_sl) <= tick_size * 1.5
        self.log_check(now, sl_reason, sl_set, current_sl=f"{float(position.sl):.5f}", required_sl=f"{desired_sl:.5f}")
        check_count += 1

        if self.state.break_even:
            be_price = entry * self.cfg.break_even_ratio
            bar_high = current_bar.high if current_bar is not None else None
            self.log_check(now, "BH", bool(bar_high is not None and bar_high > be_price), bar_high=bar_high, threshold=be_price)
            check_count += 1
        self.log.info("CONDITION_REPORT_END minute=%s checks=%s", now.strftime("%Y-%m-%d %H:%M"), check_count)

    def log_status_if_needed(self, position, now: datetime, current_bar: Optional[M1Bar]) -> None:
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if minute_key != self.last_minute_status:
            self.last_minute_status = minute_key
            self.emit_status("MINUTE", position, now, current_bar)
            self.print_instance_banner(now)
            self.print_autotrading_banner(now)
            self.print_live_enabled_banner(now)
            self.log_minute_condition_report(position, now, current_bar)

        if position is None:
            self.record_strategy_decision_if_changed()
        signature = self.status_signature(position, now)
        if signature != self.last_meaningful_signature:
            self.last_meaningful_signature = signature
            self.emit_status("STATUS_CHANGE", position, now, current_bar)

    def weekend_position_read_only(self):
        positions = mt5.positions_get(symbol=self.cfg.trade_symbol)
        if not positions:
            return None
        matching = [position for position in positions if int(getattr(position, "ticket", 0) or 0) == int(self.state.active_position_ticket or 0)]
        return matching[0] if matching else positions[0]

    def build_weekend_startup_snapshot(
        self, position, now: datetime, current_bar: Optional[M1Bar],
        potential_position: Optional[dict[str, Any]], strategy_decision: Optional[dict[str, Any]],
        last_closed_trade: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build the single weekend startup snapshot.

        The caller may perform one startup-only What-if calculation and one
        MySQL trade-history read. No recurring weekend checks or publishing
        occur after this snapshot.
        """
        account = mt5.account_info()
        balance = float(getattr(account, "balance", 0.0) or 0.0) if account is not None else 0.0
        equity = float(getattr(account, "equity", 0.0) or 0.0) if account is not None else 0.0
        currency = str(getattr(account, "currency", "") or "") if account is not None else ""
        account_login = str(getattr(account, "login", self.cfg.login or "")) if account is not None else str(self.cfg.login or "")
        candle = None if current_bar is None else {
            "time": current_bar.local_datetime.isoformat(), "open": current_bar.open, "high": current_bar.high,
            "low": current_bar.low, "close": current_bar.close,
        }
        current_week_bar = self.current_week_market_bar(self.cfg.trade_symbol, now, position)
        week_candle = None if current_week_bar is None else {
            "time": current_week_bar.local_datetime.isoformat(), "open": current_week_bar.open,
            "high": current_week_bar.high, "low": current_week_bar.low, "close": current_week_bar.close,
            "source": "MT5_M1_WINDOW",
        }
        current_price = float(current_bar.close) if current_bar is not None else 0.0
        position_payload = None
        deposit = float(getattr(account, "margin", 0.0) or 0.0) if account is not None else 0.0
        if position is not None:
            state_matches = self.position_state_matches(position)
            position_leverage = self.state.entry_leverage if state_matches and self.state.entry_leverage else self.infer_position_leverage(position)
            opened_timestamp = float(getattr(position, "time", 0.0) or 0.0)
            opened_at = self.mt5_timestamp_to_local(opened_timestamp).isoformat() if opened_timestamp > 0 else ""
            position_payload = {
                "open": True, "symbol": str(getattr(position, "symbol", self.cfg.trade_symbol)), "side": "BUY",
                "volume": float(getattr(position, "volume", 0.0) or 0.0), "ticket": int(getattr(position, "ticket", 0) or 0),
                "openedAt": opened_at, "manual": self.is_manual_position(position),
                "openPrice": float(getattr(position, "price_open", 0.0) or 0.0),
                "bid": current_price, "ask": 0.0, "priceTime": current_bar.local_datetime.isoformat() if current_bar else "",
                "bidAt": current_bar.local_datetime.isoformat() if current_bar else "", "askAt": "", "tickAgeSeconds": None,
                "profit": float(getattr(position, "profit", 0.0) or 0.0) + float(getattr(position, "swap", 0.0) or 0.0),
                "profitPercent": 0.0, "strategyLeverage": float(position_leverage),
                "leveragedProfitPercent": 0.0, "exposure": 0.0, "requiredDeposit": deposit,
                "effectiveLeverage": 0.0, "stopLoss": float(getattr(position, "sl", 0.0) or 0.0),
                "takeProfit": float(getattr(position, "tp", 0.0) or 0.0), "potentialTakeProfit": 0.0,
                "breakEvenArmed": bool(self.state.break_even) if state_matches else False,
                "breakEvenCheck": self.break_even_check_payload(position, now),
                "protectionRegime": "Weekend idle",
                "activeSlReason": self.state.active_sl_reason if state_matches else "",
                "activeTpReason": self.state.active_tp_reason if state_matches else "",
                "immutableHardStop": self.immutable_hard_stop_payload(position),
                "protectionTarget": self.protection_target_payload(position, now),
            }
        plan_day = self.week_plan_day(now.date())
        return {
            "connection": {
                "connected": self.connected, "instanceRole": self.role, "backendPublisher": self.monitor_publisher.allowed_to_publish(),
                "lastSync": now.isoformat(), "accountId": account_login, "week": iso_week_key(plan_day), "health": "WEEKEND",
                "phase": "Weekend", "regime": "Weekend idle", "nextAction": "WAIT", "nextActionAt": "",
                "us100AgeSeconds": None, "qqqAgeSeconds": None,
            },
            "account": {"currency": currency, "strategyCapital": balance, "deposit": deposit, "balance": balance, "equity": equity},
            "market": {
                "symbol": self.cfg.trade_symbol, "currentPrice": current_price, "bid": 0.0, "ask": 0.0,
                "priceTime": current_bar.local_datetime.isoformat() if current_bar else "", "tickAgeSeconds": None,
                "signalSymbol": self.cfg.signal_symbol, "signalPrice": 0.0, "signalPriceTime": "", "currentM1": candle,
                "currentW1": week_candle, "session": self.market_session_payload(now, current_week_bar),
            },
            "metrics": {
                "currentPrice": current_price, "currentProfit": float(position_payload["profit"]) if position_payload else 0.0,
                "currentProfitPercent": 0.0, "currentLeveragedProfitPercent": 0.0, "equity": equity, "balance": balance,
                "deposit": deposit, "strategyLeverage": float(position_payload["strategyLeverage"]) if position_payload else float(self.cfg.base_leverage), "currency": currency,
            },
            "position": position_payload,
            "potentialPosition": potential_position,
            "strategyDecision": strategy_decision,
            "lastClosedTrade": last_closed_trade, "execution": self.execution_snapshot(), "conditions": [], "closestCondition": None,
            "equityHistory": [],
        }

    def weekend_startup(self, label: str) -> None:
        """Always calculate and queue one fresh weekend startup snapshot."""
        now = datetime.now(self.tz)
        self.weekend_idle = True
        self.monitor_publisher.set_weekend_idle(True)
        self.log_week_plan(now.date())

        position = self.weekend_position_read_only()
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.last_account_funding_signature = self.account_funding_signature(mt5.account_info())
        self.last_account_funding_check_monotonic = time_module.monotonic()

        # Startup-only weekend work. This runs on every script start; the loop
        # remains completely idle after the snapshot has been queued.
        self.latest_closed_trade_record(force=True)
        potential_position = self.potential_position_preview(assume_current_position_closed=position is not None)
        strategy_decision = self.record_strategy_decision_if_changed(force=True, preview=potential_position)
        last_closed_trade = self.last_closed_trade_payload(refresh=False)

        self.log.info(
            "EVENT WEEKEND_WHAT_IF_CALCULATED outcome=%s leverage=%.0f previous_trade=%.8f "
            "trade_source=%s volume=%.8f required_deposit=%.2f required_balance=%.2f "
            "required_balance_multiplier=%.3f effective_leverage=%.6f",
            strategy_decision["outcome"], strategy_decision["selectedLeverage"],
            strategy_decision["inputs"]["previousTradeChange"],
            str(strategy_decision["inputs"].get("previousTradeSource", "")).replace(" ", "_"),
            float(strategy_decision["sizing"].get("volume") or 0.0),
            float(strategy_decision["sizing"].get("requiredDeposit") or 0.0),
            float(strategy_decision["sizing"].get("requiredBalance") or 0.0),
            float(strategy_decision["sizing"].get("requiredBalanceMultiplier") or self.required_balance_multiplier(int(strategy_decision["selectedLeverage"] or self.cfg.base_leverage))),
            float(strategy_decision["sizing"].get("effectiveLeverage") or 0.0),
        )

        snapshot = self.build_weekend_startup_snapshot(
            position, now, current_bar, potential_position, strategy_decision, last_closed_trade,
        )
        snapshot["statusUpdate"] = {
            "kind": "WEEKEND_STARTUP", "minute": now.strftime("%Y-%m-%d %H:%M"),
            "generatedAt": now.isoformat(), "build": BUILD_ID,
        }
        self.monitor_publisher.submit_snapshot(snapshot, guaranteed=True)
        self.log.info(
            "EVENT WEEKEND_STARTUP_QUEUED role=%s candle_time=%s plan_week=%s what_if_outcome=%s",
            label, current_bar.local_datetime.isoformat() if current_bar else "none",
            iso_week_key(self.week_plan_day(now.date())), strategy_decision["outcome"],
            extra={"skip_mobile_publish": True},
        )
        self.print_instance_banner(now)
        self.log.info(
            "EVENT WEEKEND_IDLE_STARTED role=%s candle_time=%s plan_week=%s minute_updates=false recurring_checks=false",
            label, current_bar.local_datetime.isoformat() if current_bar else "none",
            iso_week_key(self.week_plan_day(now.date())), extra={"skip_mobile_publish": True},
        )

    def enter_weekend_idle_without_publish(self, label: str) -> None:
        now = datetime.now(self.tz)
        self.weekend_idle = True
        self.monitor_publisher.set_weekend_idle(True)
        self.log_week_plan(now.date())
        self.log.info(
            "EVENT WEEKEND_IDLE_ENTERED role=%s plan_week=%s minute_updates=false checks=false",
            label, iso_week_key(self.week_plan_day(now.date())), extra={"skip_mobile_publish": True},
        )

    def startup_reconcile(self) -> None:
        if not self.is_executor:
            raise RuntimeError("startup_reconcile is executor-only")
        now = datetime.now(self.tz)
        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            if not self.finalize_closed_position():
                raise RuntimeError("Exact broker close deal is not available yet")
        elif position is not None:
            self.recover_position_state(position, now, force=True)
            try:
                self.refresh_entry_rule_context(now.date())
            except Exception as exc:
                self.log.error(
                    "EVENT POSITION_RULE_STARTUP_RECOVERY_UNAVAILABLE action=none error=%s",
                    shlex.quote(str(exc)),
                )
            if self.maybe_execute_authorized_or5_exit(position, now):
                position = self.managed_position()
            if position is not None:
                self.apply_standard_protection(position, now)
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.last_account_funding_signature = self.account_funding_signature(mt5.account_info())
        self.last_account_funding_check_monotonic = time_module.monotonic()
        self.emit_status("STARTUP", position, now, current_bar)
        self.print_instance_banner(now)
        self.print_autotrading_banner(now)
        self.print_live_enabled_banner(now)
        self.last_minute_status = now.strftime("%Y-%m-%d %H:%M")
        self.last_meaningful_signature = self.status_signature(position, now)
        if position is None:
            self.record_strategy_decision_if_changed(force=True)
        self.publish_mobile_minute_status(position, now, current_bar, force=True)

    def cycle(self) -> None:
        if self.is_weekend(datetime.now(self.tz)):
            return
        if not self.is_executor:
            raise RuntimeError("cycle is executor-only")
        self.coordinator.require_role_lease()
        now = datetime.now(self.tz)
        self.ensure_autotrading_enabled("CYCLE")
        self.log_week_plan(now.date())
        position = self.managed_position()

        if position is None and self.state.active_position_identifier:
            if not self.finalize_closed_position():
                return
        elif position is not None and self.recover_position_state(position, now):
            # A manually adopted position may have no broker protection. Attach
            # the immutable hard stop before any bar or scheduled-exit logic can
            # interrupt the cycle, then refresh the broker position for status.
            self.apply_standard_protection(position, now)
            position = self.managed_position()
            self.emit_status("POSITION_RECOVERED", position, now)

        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        if current_bar is not None and current_bar.local_datetime.date() == now.date():
            self.process_new_bar(position, current_bar, now)

        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            if not self.finalize_closed_position():
                return

        if position is not None:
            self.capture_entry_signal_open(position, now)
            if self.maybe_execute_authorized_or5_exit(position, now):
                position = self.managed_position()
            if position is not None and self.maybe_execute_open_action(position, now):
                position = self.managed_position()
            if position is not None and self.maybe_execute_close_action(position, now):
                position = self.managed_position()
            if position is not None:
                session = self.session_times(now.date())
                if session.cash_open <= now < session.close_processing and current_bar is not None and current_bar.local_datetime.date() == now.date():
                    self.evaluate_regular_bar(position, current_bar, now)
                if now >= session.close_processing:
                    self.process_completed_close(now.date(), now, position)
                self.apply_standard_protection(position, now)
        else:
            if now >= self.session_times(now.date()).close_processing:
                self.process_completed_close(now.date(), now, None)
            self.maybe_open_new_week(now.date(), now, current_bar, None)

        position = self.managed_position()
        funding_published = self.publish_account_change_if_needed(position, now, current_bar, "EXECUTOR")
        if position is None:
            self.record_strategy_decision_if_changed()
        self.log_status_if_needed(position, now, current_bar)
        minute_published = self.publish_mobile_minute_status(position, now, current_bar)
        if not minute_published and not funding_published:
            self.publish_mobile_if_due(position, now, current_bar)

    def reload_state_read_only(self) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, 6):
            try:
                self.state = StrategyState.load(self.cfg.state_file)
                if attempt > 1:
                    self.log.info(
                        "EVENT PUBLISHER_STATE_READ_RECOVERED path=%s attempt=%s",
                        self.cfg.state_file, attempt,
                    )
                return
            except PermissionError as exc:
                last_error = exc
                if attempt < 5:
                    time_module.sleep(0.05)
            except Exception as exc:
                last_error = exc
                break
        self.log.warning(
            "EVENT PUBLISHER_STATE_READ_FAILED path=%s attempts=%s error=%s",
            self.cfg.state_file, 5 if isinstance(last_error, PermissionError) else 1, last_error,
        )

    def publisher_startup(self) -> None:
        if not self.monitor_publisher.ready:
            raise RuntimeError("Publisher mode requires valid monitor configuration")
        self.coordinator.require_role_lease()
        self.reload_state_read_only()
        now = datetime.now(self.tz)
        position = self.managed_position()
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.last_account_funding_signature = self.account_funding_signature(mt5.account_info())
        self.last_account_funding_check_monotonic = time_module.monotonic()
        self.emit_status("PUBLISHER_STARTUP", position, now, current_bar)
        self.print_instance_banner(now)
        self.last_minute_status = now.strftime("%Y-%m-%d %H:%M")
        self.last_meaningful_signature = self.status_signature(position, now)
        if position is None:
            # A publisher can start during the weekend, when ordinary reads
            # are intentionally cache-only. Refresh once before producing its
            # forced What-if record so a prior projection repair is included.
            self.latest_closed_trade_record(force=True)
            self.record_strategy_decision_if_changed(force=True)
        self.publish_mobile_minute_status(position, now, current_bar, force=True)

    def publisher_cycle(self) -> None:
        if self.is_weekend(datetime.now(self.tz)):
            return
        self.coordinator.require_role_lease()
        self.reload_state_read_only()
        now = datetime.now(self.tz)
        position = self.managed_position()
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        if position is None:
            # The dedicated publisher owns normal snapshot delivery. It must
            # therefore recalculate and publish an immutable decision when
            # MySQL-authoritative leverage inputs change after startup.
            self.record_strategy_decision_if_changed()
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if minute_key != self.last_minute_status:
            self.last_minute_status = minute_key
            self.emit_status("PUBLISHER_MINUTE", position, now, current_bar)
            self.print_instance_banner(now)
        funding_published = self.publish_account_change_if_needed(position, now, current_bar, "PUBLISHER")
        signature = self.status_signature(position, now)
        if signature != self.last_meaningful_signature:
            self.last_meaningful_signature = signature
            self.emit_status("PUBLISHER_STATUS_CHANGE", position, now, current_bar)
        minute_published = self.publish_mobile_minute_status(position, now, current_bar)
        if not minute_published and not funding_published:
            self.publish_mobile_if_due(position, now, current_bar)

    def run_executor(self) -> None:
        self.connect()
        started_on_weekend = self.is_weekend(datetime.now(self.tz))
        if started_on_weekend:
            self.weekend_startup("EXECUTOR")
        else:
            self.startup_reconcile()
        while self.running:
            try:
                self.coordinator.require_role_lease()
                now = datetime.now(self.tz)
                if self.is_weekend(now):
                    if not self.weekend_idle:
                        self.enter_weekend_idle_without_publish("EXECUTOR")
                    weekend_position = self.managed_position()
                    self.publish_account_change_if_needed(weekend_position, now, None, "EXECUTOR")
                    time_module.sleep(max(1.0, self.cfg.poll_seconds))
                    continue
                if self.weekend_idle:
                    self.weekend_idle = False
                    self.monitor_publisher.set_weekend_idle(False)
                    self.startup_reconcile()
                if not self.connection_healthy():
                    self.log.error("EVENT CONNECTION_LOST role=EXECUTOR reconnecting=true")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.connect()
                    self.startup_reconcile()
                self.cycle()
            except KeyboardInterrupt:
                self.running = False
            except LeaseLostError:
                self.log.exception("EVENT EXECUTOR_SUSPENDED_LEASE_INVALID account=%s", self.account)
                if self.coordinator.recover_role_lease(self.cfg.reconnect_seconds):
                    self.log.info(
                        "EVENT EXECUTOR_RESUMED_LEASE_REACQUIRED account=%s fencing_token=%s",
                        self.account, self.coordinator.fencing_token,
                    )
                    self.startup_reconcile()
                    continue
                self.running = False
            except Exception:
                self.log.exception("EVENT STRATEGY_CYCLE_FAILED role=EXECUTOR")
            time_module.sleep(self.cfg.poll_seconds)
        self.log.info("EVENT STRATEGY_STOPPED role=EXECUTOR")

    def run_publisher(self) -> None:
        self.coordinator.require_role_lease()
        self.connect()
        started_on_weekend = self.is_weekend(datetime.now(self.tz))
        if started_on_weekend:
            self.weekend_startup("PUBLISHER")
        else:
            self.publisher_startup()
        while self.running:
            try:
                self.coordinator.require_role_lease()
                now = datetime.now(self.tz)
                if self.is_weekend(now):
                    # Market-idle coordination plus an account-funding watcher that also covers carried positions.
                    self.coordinator.require_role_lease()
                    if not self.weekend_idle:
                        self.enter_weekend_idle_without_publish("PUBLISHER")
                    weekend_position = self.managed_position()
                    self.publish_account_change_if_needed(weekend_position, now, None, "PUBLISHER")
                    time_module.sleep(max(1.0, self.cfg.poll_seconds))
                    continue
                self.coordinator.require_role_lease()
                if self.weekend_idle:
                    self.weekend_idle = False
                    self.monitor_publisher.set_weekend_idle(False)
                    self.publisher_startup()
                if not self.connection_healthy():
                    self.log.error("EVENT CONNECTION_LOST role=PUBLISHER reconnecting=true")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.coordinator.require_role_lease()
                    self.connect()
                    self.publisher_startup()
                self.publisher_cycle()
            except KeyboardInterrupt:
                self.running = False
            except LeaseLostError:
                self.log.exception("EVENT PUBLISHER_SUSPENDED_LEASE_INVALID account=%s", self.account)
                if self.coordinator.recover_role_lease(self.cfg.reconnect_seconds):
                    self.log.info(
                        "EVENT PUBLISHER_RESUMED_LEASE_REACQUIRED account=%s fencing_token=%s",
                        self.account, self.coordinator.fencing_token,
                    )
                    self.publisher_startup()
                    continue
                self.running = False
            except Exception:
                self.log.exception("EVENT PUBLISHER_CYCLE_FAILED role=PUBLISHER")
            time_module.sleep(self.cfg.poll_seconds)
        self.log.info("EVENT STRATEGY_STOPPED role=PUBLISHER")

    def run(self) -> None:
        if self.is_executor:
            self.run_executor()
        else:
            self.run_publisher()

    def stop(self, *_args: Any) -> None:
        self.running = False
        self.coordinator.stop_event.set()
