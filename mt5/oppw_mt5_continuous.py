"""
Continuous MetaTrader 5 implementation of the OPPW strategy.

Key execution rules
-------------------
* BUY is sent at its separately configurable entry-action lead time for a valid new-week entry.
* OH is evaluated exactly once at cash open minus three seconds from the second actual trading session onward;
  it is never evaluated on the first trading session of the week.
* TPP levels follow actual XNYS trading-session order within the week. If Tuesday is the first session, it receives
  Monday's TPP, Wednesday receives Tuesday's TPP, and the remaining sessions advance accordingly.
* On the second trading session after entry, PRE H ramps linearly from the first-session TPP at midnight
  to the second-session TPP at cash open and exits with a fenced market SELL when an M1 open crosses it.
* CH and final-week TO are always evaluated at XNYS session close minus three seconds.
* Every outgoing SL is normalized to a whole index point by rounding upward, then constrained to a broker-valid long-position level.
* BUY carries a provisional hard SL calculated from the requested ask. Once the actual fill becomes visible, one definitive
  hard SL is calculated from the actual fill price, filled volume, balance, leverage, and account-currency profit conversion.
* The definitive hard SL and all calculation inputs are persisted immutably for that position. Routine cycles, deposits,
  withdrawals, and later currency-conversion changes cannot recalculate or weaken it.
* Hard SL restoration and deliberate Thursday TSL tightening are maintained with TRADE_ACTION_SLTP.
* BEPRE, BEO, and BH submit fenced market SELL requests; they do not create an exit bracket as their primary action.
* One configurable TSL is active continuously from Thursday date change through Friday and the weekend if needed.
* TSL is a broker-side SL label; candle lows do not latch it.
* Closed-trade leverage inputs come exclusively from the OPPW MySQL trade history through the authenticated backend endpoint.
* Status deposit is read directly from MT5 as float(account.margin).
* Terminal/account AutoTrading permissions are verified continuously before every live trade request.
* EXECUTOR mode is the only role permitted to submit or modify trades.
* PUBLISHER mode is read-only and owns backend publishing while its global MySQL lease is active.
* EXECUTOR automatically publishes when no global PUBLISHER lease is active.
* EXECUTOR, PUBLISHER, and TRADE_EXECUTION ownership use MySQL leases with monotonically increasing fencing tokens.
* Transport failures trigger fast lease-renewal retries; role activity is suspended and automatically reacquired after a longer outage.
* Weekly BUY idempotency is enforced in MySQL before order_send; an uncertain send is never retried automatically.
* No authoritative filesystem lock, heartbeat file, or cross-process event-spool lock is used.
* Status publishes an institutional-style next-trade What-if ticket; while a position is open it assumes the current position closes first and never resizes that live position.
* Entry volume uses the configured balance-multiplier profile. The default growth profile uses 1.765; --conservative-multiplier selects 2.0 at L10 and 2.5 at L8.
* All runtime, strategy, timing, risk, publisher, and backend settings are loaded from the selected account config file.
* Strategy decisions remain visible in every mobile snapshot, but each decision ID is sent to the MySQL persistence path only until its first successful backend acknowledgement.
* Every completed trade is assigned a Guy Fleury A/B/C/D class and the publisher includes the label.
* Weekends remain market-idle after startup. A lightweight MT5 account-balance watcher runs regardless of position state and may publish a fresh next-trade What-if snapshot after a top-up or withdrawal; no recurring market checks or minute publishing follow.

Run with `--mode executor|publisher` and `--account demo|real`. DEMO loads
demo/demo_mt5_config.py and REAL loads real/real_mt5_config.py. Live trading is disabled
unless LIVE_ENABLED=True in the selected account configuration or OPPW_LIVE=1 is set.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import shutil
import sys
import threading
import time as time_module
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    import exchange_calendars as xcals
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc

from oppw_core.account_config import (
    REQUIRED_CONFIG_FIELDS,
    account_scoped_dir,
    account_scoped_file,
    apply_runtime_flags,
    load_account_config,
    migrate_legacy_demo_runtime_files,
    scope_config_to_account,
    validate_config,
)
from oppw_core.broker_execution import BrokerExecutionMixin
from oppw_core.coordination import (
    BackendLeaseCoordinator,
    CoordinationError,
    LeaseLostError,
    TradeExecutionGate,
)
from oppw_core.logging_support import WeeklyFileHandler, WarsawFormatter, setup_logging
from oppw_core.models import M1Bar, SessionTimes, StaleTickError, StrategyState
from oppw_core.monitoring import MonitoringMixin
from oppw_core.position_lifecycle import PositionLifecycleMixin
from oppw_core.publishing import MobileEventHandler, MobileMonitorPublisher
from oppw_core.runtime import RuntimeMixin
from oppw_core.session_calendar import SessionCalendarMixin
from oppw_core.strategy_decision import StrategyDecisionMixin
from oppw_core.utilities import (
    ceil_step,
    ceil_whole_sl,
    floor_step,
    iso_week_key,
    parse_date,
    price_changed,
    truncate_four_decimals,
)
from oppw_core.versioning import (
    ACCOUNT_CONFIG_FILES,
    ACCOUNT_DEMO,
    ACCOUNT_REAL,
    INSTANCE_MODE_EXECUTOR,
    INSTANCE_MODE_PUBLISHER,
    read_project_version,
)

PROJECT_VERSION = read_project_version()
BUILD_ID = f"oppw-{PROJECT_VERSION}"


class OPPWContinuousStrategy(
    SessionCalendarMixin,
    PositionLifecycleMixin,
    StrategyDecisionMixin,
    MonitoringMixin,
    BrokerExecutionMixin,
    RuntimeMixin,
):
    def __init__(
        self, config, role: str, account: str, coordinator: BackendLeaseCoordinator,
        service_ready_file: Optional[Path] = None,
    ):
        self.cfg = config
        self.role = role
        self.account = account.upper()
        self.is_executor = role == INSTANCE_MODE_EXECUTOR
        self.coordinator = coordinator
        self.service_ready_file = service_ready_file
        self.tz = ZoneInfo(config.timezone_name)
        self.market_tz = ZoneInfo(config.market_timezone_name)
        self.log = setup_logging(config.log_dir, self.tz, role, self.account)
        try:
            self.state = StrategyState.load(config.state_file)
        except Exception as exc:
            self.log.error("EVENT STATE_LOAD_FAILED path=%s error=%s", config.state_file, exc)
            self.state = StrategyState()

        self.calendar = xcals.get_calendar(config.exchange_calendar)
        self.running = True
        self.connected = False
        self.last_minute_status = ""
        self.last_meaningful_signature: Optional[tuple[Any, ...]] = None
        self.last_week_plan_key = ""
        self.last_trade_request_monotonic = 0.0
        self.last_autotrading_signature: Optional[tuple[Any, ...]] = None
        self.last_autotrading_log_monotonic = 0.0
        self.last_stale_tick_log_monotonic: dict[str, float] = {}
        self.last_signal_open_pending_log_monotonic = 0.0
        self.tsl_install_deferred = False
        self._session_times_cache: dict[date, SessionTimes] = {}
        self._week_open_price_cache: dict[str, float] = {}
        self.last_monitor_publish_monotonic = 0.0
        self.last_monitor_minute_key = ""
        self.last_strategy_decision_signature: Optional[tuple[Any, ...]] = None
        self.last_strategy_decision_payload: Optional[dict[str, Any]] = None
        self.last_leverage_inputs_refresh_monotonic = 0.0
        self.cached_previous_full_week_change = float(self.state.prev_full_week_change)
        self.cached_previous_trade_change = float(self.state.prev_change)
        self.cached_previous_full_week_source = "state fallback"
        self.cached_previous_trade_source = "state fallback"
        self.last_leverage_state_signature: Optional[tuple[Any, ...]] = None
        self.cached_mysql_trade_record: Optional[dict[str, Any]] = None
        self.last_mysql_trade_refresh_monotonic = 0.0
        self.last_mysql_trade_error_monotonic = 0.0
        self.last_account_funding_check_monotonic = 0.0
        self.last_account_funding_signature: Optional[tuple[float, float]] = None
        self.weekend_idle = False
        self.started_at = datetime.now(self.tz)
        self.strategy_specification = self.build_strategy_specification()
        self.coordinator.set_logger(self.log)
        self.monitor_publisher = MobileMonitorPublisher(config, self.log, self.tz, role, coordinator)
        self.monitor_publisher.canonical_strategy_specification = self.strategy_specification
        self.monitor_event_handler = MobileEventHandler(self.monitor_publisher)
        if self.monitor_publisher.ready:
            self.log.addHandler(self.monitor_event_handler)
            self.monitor_publisher.start()

    def connect(self) -> None:
        kwargs: dict[str, Any] = {}
        if self.cfg.login:
            kwargs["login"] = self.cfg.login
        if self.cfg.password:
            kwargs["password"] = self.cfg.password
        if self.cfg.server:
            kwargs["server"] = self.cfg.server

        ok = mt5.initialize(self.cfg.terminal_path, **kwargs) if self.cfg.terminal_path else mt5.initialize(**kwargs)
        if not ok:
            raise RuntimeError(f"mt5.initialize() failed: {mt5.last_error()}")

        terminal = mt5.terminal_info()
        account = mt5.account_info()
        if terminal is None or account is None:
            raise RuntimeError(f"Cannot read terminal/account information: {mt5.last_error()}")
        expected_login = int(getattr(self.cfg, "login", 0) or 0)
        actual_login = int(getattr(account, "login", 0) or 0)
        if expected_login > 0 and actual_login != expected_login:
            mt5.shutdown()
            raise RuntimeError(f"Selected {self.account} config expects MT5 login {expected_login}, but terminal returned {actual_login}")
        if not mt5.symbol_select(self.cfg.trade_symbol, True):
            raise RuntimeError(f"Cannot select trade symbol {self.cfg.trade_symbol}: {mt5.last_error()}")
        if not mt5.symbol_select(self.cfg.signal_symbol, True):
            raise RuntimeError(f"Cannot select signal symbol {self.cfg.signal_symbol}: {mt5.last_error()}")

        self.connected = True
        self.log.info(
            "EVENT CONNECTED role=%s selected_account=%s login=%s server=%s trade=%s signal=%s live=%s build=%s script=%s",
            self.role, self.account, getattr(account, "login", "?"), getattr(account, "server", "?"), self.cfg.trade_symbol,
            self.cfg.signal_symbol, self.cfg.live_enabled, BUILD_ID, Path(__file__).resolve(),
        )
        self.log.info(
            "EVENT CONFIG_PROFILE config=%s balance_multiplier_profile=%s default_multiplier=%.3f conservative_L10=%.3f conservative_L8=%.3f",
            getattr(self.cfg, "config_name", self.account), self.balance_multiplier_profile(), float(self.cfg.required_balance_multiplier),
            float(self.cfg.legacy_required_balance_multiplier_l10), float(self.cfg.legacy_required_balance_multiplier_l8),
        )
        if self.is_executor:
            if not self.cfg.live_enabled:
                self.log.warning("EVENT DRY_RUN live_enabled=false")
            elif not self.is_weekend(datetime.now(self.tz)):
                self.ensure_autotrading_enabled("CONNECT", force_log=True)
            else:
                self.log.info("EVENT WEEKEND_AUTOTRADING_CHECK_SKIPPED checks=false")
        else:
            self.log.info("EVENT INSTANCE_ROLE role=PUBLISHER account=%s trading_allowed=false backend_publishing=true", self.account)
        if self.service_ready_file is not None:
            ready_payload = {
                "account": self.account,
                "role": self.role,
                "pid": os.getpid(),
                "connectedAt": datetime.now(UTC).isoformat(),
                "build": BUILD_ID,
            }
            temporary_ready_file = self.service_ready_file.with_suffix(
                self.service_ready_file.suffix + f".{os.getpid()}.tmp"
            )
            temporary_ready_file.write_text(
                json.dumps(ready_payload, separators=(",", ":")), encoding="utf-8"
            )
            os.replace(temporary_ready_file, self.service_ready_file)

    def disconnect(self) -> None:
        if self.connected:
            mt5.shutdown()
            self.connected = False

    def selected_account_matches(self) -> bool:
        expected_login = int(getattr(self.cfg, "login", 0) or 0)
        if expected_login <= 0:
            return True
        account = mt5.account_info()
        return account is not None and int(getattr(account, "login", 0) or 0) == expected_login

    def connection_healthy(self) -> bool:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        return terminal is not None and account is not None and bool(getattr(terminal, "connected", True)) and self.selected_account_matches()

    def autotrading_status(self) -> tuple[bool, dict[str, bool]]:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        values = {
            "connected": terminal is not None and bool(getattr(terminal, "connected", True)),
            "terminal_trade_allowed": terminal is not None and bool(getattr(terminal, "trade_allowed", False)),
            "tradeapi_disabled": terminal is None or bool(getattr(terminal, "tradeapi_disabled", False)),
            "account_trade_allowed": account is not None and bool(getattr(account, "trade_allowed", True)),
            "account_trade_expert": account is not None and bool(getattr(account, "trade_expert", True)),
            "selected_account_matches": self.selected_account_matches(),
        }
        enabled = all((
            values["connected"], values["terminal_trade_allowed"], not values["tradeapi_disabled"],
            values["account_trade_allowed"], values["account_trade_expert"], values["selected_account_matches"],
        ))
        return enabled, values

    def ensure_autotrading_enabled(self, context: str, force_log: bool = False) -> bool:
        if not self.is_executor:
            return False
        if not self.cfg.live_enabled:
            return True

        enabled, values = self.autotrading_status()
        signature = (
            enabled, values["connected"], values["terminal_trade_allowed"], values["tradeapi_disabled"],
            values["account_trade_allowed"], values["account_trade_expert"], values["selected_account_matches"],
        )
        state_changed = self.last_autotrading_signature is None or bool(self.last_autotrading_signature[0]) != enabled
        if force_log or state_changed:
            if enabled:
                self.log.info("EVENT AUTOTRADING_ENABLED")
            else:
                self.log.error("EVENT AUTOTRADING_DISABLED")
        self.last_autotrading_signature = signature
        return enabled

    def print_autotrading_banner(self, now: datetime) -> None:
        enabled = True if not self.cfg.live_enabled else self.autotrading_status()[0]
        status = "AUTOTRADING_ENABLED" if enabled else "AUTOTRADING_DISABLED"
        text = f"{now:%Y-%m-%d %H:%M:%S} {status}"
        width = max(len(text), shutil.get_terminal_size((120, 20)).columns)
        color = "\033[1;92m" if enabled else "\033[1;91m"
        reset = "\033[0m"
        print(f"\n{color}{text.center(width)}{reset}\n", flush=True)

    def print_live_enabled_banner(self, now: datetime) -> None:
        enabled = bool(self.cfg.live_enabled)
        status = "LIVE_ENABLED" if enabled else "LIVE_DISABLED"
        text = f"{now:%Y-%m-%d %H:%M:%S} {status}"
        width = max(len(text), shutil.get_terminal_size((120, 20)).columns)
        color = "\033[1;92m" if enabled else "\033[1;91m"
        reset = "\033[0m"
        print(f"{color}{text.center(width)}{reset}\n", flush=True)

    def print_instance_banner(self, now: datetime) -> None:
        status = f"INSTANCE_{self.role} [{self.account}]"
        text = f"{now:%Y-%m-%d %H:%M:%S} {status}"
        width = max(len(text), shutil.get_terminal_size((120, 20)).columns)
        color = "\033[1;93m" if self.is_executor else "\033[1;96m"
        reset = "\033[0m"
        print(f"\n{color}{text.center(width)}{reset}\n", flush=True)


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OPPW MT5 continuous strategy")
    parser.add_argument(
        "--mode",
        choices=(INSTANCE_MODE_EXECUTOR.lower(), INSTANCE_MODE_PUBLISHER.lower()),
        default=INSTANCE_MODE_EXECUTOR.lower(),
        help="executor may trade and publishes only when no publisher exists; publisher is read-only and handles backend publishing",
    )
    parser.add_argument(
        "--account",
        choices=(ACCOUNT_DEMO.lower(), ACCOUNT_REAL.lower()),
        default=ACCOUNT_DEMO.lower(),
        help="demo loads demo/demo_mt5_config.py; real loads real/real_mt5_config.py",
    )
    parser.add_argument(
        "--conservative-multiplier",
        action="store_true",
        help="replace the default 1.765 growth multiplier with conservative leverage-bound sizing: 2.0 at L10 and 2.5 at L8",
    )
    parser.add_argument(
        "--service-stop-file",
        default="",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--service-ready-file",
        default="",
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main() -> int:
    args = parse_arguments()
    role = str(args.mode).upper()
    account = str(args.account).upper()
    original_cfg, config_path = load_account_config(account)
    validate_config(original_cfg)
    original_cfg = apply_runtime_flags(
        original_cfg, bool(args.conservative_multiplier)
    )
    cfg = scope_config_to_account(original_cfg, account)
    migrate_legacy_demo_runtime_files(original_cfg, cfg, account)

    coordinator = BackendLeaseCoordinator(cfg, role, account)
    strategy: Optional[OPPWContinuousStrategy] = None
    try:
        coordinator.start()
        service_ready_file = Path(str(args.service_ready_file)).resolve() if str(args.service_ready_file).strip() else None
        strategy = OPPWContinuousStrategy(cfg, role, account, coordinator, service_ready_file)
        if (
            role == INSTANCE_MODE_PUBLISHER
            and not strategy.monitor_publisher.ready
        ):
            raise RuntimeError(
                "Publisher mode cannot start because backend monitor publishing "
                "is not configured"
            )
        service_stop_file = Path(str(args.service_stop_file)).resolve() if str(args.service_stop_file).strip() else None
        if service_stop_file is not None:
            def watch_service_stop() -> None:
                while strategy is not None and strategy.running:
                    if service_stop_file.is_file():
                        strategy.log.warning(
                            "EVENT SERVICE_STOP_REQUESTED role=%s account=%s stop_file=%s",
                            role, account, service_stop_file,
                        )
                        strategy.stop()
                        return
                    time_module.sleep(0.20)

            threading.Thread(
                target=watch_service_stop,
                name=f"oppw-{account.lower()}-{role.lower()}-service-stop",
                daemon=True,
            ).start()
        signal.signal(signal.SIGINT, strategy.stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, strategy.stop)
        strategy.run()
        return 0
    except Exception:
        if strategy is not None:
            strategy.log.exception(
                "EVENT FATAL_STARTUP_FAILURE role=%s account=%s",
                role,
                account,
            )
        else:
            logging.basicConfig(level=logging.ERROR)
            logging.exception(
                "FATAL_STARTUP_FAILURE role=%s account=%s config=%s",
                role,
                account,
                config_path,
            )
        return 1
    finally:
        if strategy is not None:
            strategy.shutdown_mobile_publisher()
            strategy.disconnect()
        coordinator.stop()


if __name__ == "__main__":
    sys.exit(main())
