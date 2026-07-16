"""
Continuous MetaTrader 5 implementation of the latest OPPW Sim.process() logic.

Production behavior
-------------------
* Reconstructs strategy state from an already-open long position after restart.
* Sends one BUY at XNYS cash open minus three seconds for a valid new-week entry.
* Uses TRADE_ACTION_SLTP only when the required SL/TP actually changes.
* Evaluates OH at cash open minus three seconds and CH at session close minus
  three seconds; a true OH or CH is executed with one market SELL.
* Sends one market SELL for TO at session close minus three seconds on the final
  XNYS trading session of the week, or as an overdue recovery close.
* Prints live status immediately at startup, once per minute, whenever the
  week's meaningful state changes, and after every successful trading update.
* Writes every event, each minute status, and every applicable strategy condition
  with a TRUE/FALSE result to log/YEAR_week_WEEK_NO.txt and stdout.

Live trading is disabled unless LIVE_ENABLED=True in oppw_mt5_config.py or OPPW_LIVE=1 is set.
"""

from __future__ import annotations

import json
import logging
import math
import os
import signal
import sys
import time as time_module
from dataclasses import asdict, dataclass, fields
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
BUILD_ID = "2026-07-16-position-deposit-v21"
SCHEDULED_ACTION_LEAD_SECONDS = 3.0

try:
    import exchange_calendars as xcals
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

from oppw_mt5_config import Config


# -----------------------------------------------------------------------------
# Persistent strategy state
# -----------------------------------------------------------------------------


@dataclass
class StrategyState:
    version: int = 4

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

    break_even: bool = False
    exit_latched_reason: str = ""
    exit_latched_at: str = ""

    active_sl_reason: str = ""
    active_tp_reason: str = ""
    active_sl_price: float = 0.0
    active_tp_price: float = 0.0
    active_protection_updated_at: str = ""
    active_protection_position_identifier: int = 0

    prev_change: float = 0.0
    prev_full_week_change: float = 0.0
    prev_open: float = 0.0

    last_exit_price: float = 0.0
    last_exit_time: str = ""
    last_exit_reason: str = ""

    @classmethod
    def load(cls, path: Path) -> "StrategyState":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        allowed = {field.name for field in fields(cls)}
        return cls(**{key: value for key, value in raw.items() if key in allowed})

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, path)


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
    open_action: datetime
    weekly_close: datetime
    close_bar_open: datetime
    close_processing: datetime


# -----------------------------------------------------------------------------
# Logging and utilities
# -----------------------------------------------------------------------------


class WarsawFormatter(logging.Formatter):
    def __init__(self, timezone: ZoneInfo):
        super().__init__("%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        self.timezone = timezone

    def formatTime(self, record: logging.LogRecord, datefmt: Optional[str] = None) -> str:
        current = datetime.fromtimestamp(record.created, self.timezone)
        return current.strftime(datefmt or "%Y-%m-%d %H:%M:%S")


class WeeklyFileHandler(logging.Handler):
    def __init__(self, log_dir: Path, timezone: ZoneInfo):
        super().__init__(logging.INFO)
        self.log_dir = log_dir
        self.timezone = timezone
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            current = datetime.fromtimestamp(record.created, self.timezone)
            iso = current.isocalendar()
            path = self.log_dir / f"{iso.year:04d}_week_{iso.week:02d}.txt"
            message = self.format(record)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(message + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(log_dir: Path, timezone: ZoneInfo) -> logging.Logger:
    logger = logging.getLogger("oppw_mt5")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = WarsawFormatter(timezone)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    weekly = WeeklyFileHandler(log_dir, timezone)
    weekly.setLevel(logging.INFO)
    weekly.setFormatter(formatter)

    logger.addHandler(console)
    logger.addHandler(weekly)
    return logger


def truncate_four_decimals(value: float) -> float:
    return math.trunc(value * 10_000.0) / 10_000.0


def iso_week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def parse_date(value: str) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def floor_step(value: float, step: float) -> float:
    return value if step <= 0 else math.floor((value + 1e-12) / step) * step


def ceil_step(value: float, step: float) -> float:
    return value if step <= 0 else math.ceil((value - 1e-12) / step) * step


def price_changed(current: float, desired: float, tolerance: float) -> bool:
    if current == 0.0 and desired == 0.0:
        return False
    return abs(current - desired) >= tolerance


class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    @staticmethod
    def pid_is_running(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                old_pid = int(self.path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                old_pid = 0
            if self.pid_is_running(old_pid):
                raise RuntimeError(f"Another strategy instance is running with PID {old_pid}: {self.path}")
            self.path.unlink(missing_ok=True)

        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            try:
                self.path.unlink(missing_ok=True)
            finally:
                self.acquired = False


# -----------------------------------------------------------------------------
# Strategy engine
# -----------------------------------------------------------------------------


class OPPWContinuousStrategy:
    def __init__(self, config: Config):
        self.cfg = config
        self.tz = ZoneInfo(config.timezone_name)
        self.market_tz = ZoneInfo(config.market_timezone_name)
        self.log = setup_logging(config.log_dir, self.tz)
        try:
            self.state = StrategyState.load(config.state_file)
        except Exception as exc:
            self.log.error("Cannot load state file %s: %s; starting with recoverable empty state", config.state_file, exc)
            self.state = StrategyState()
        self.calendar = xcals.get_calendar(config.exchange_calendar)
        self.running = True
        self.connected = False
        self.last_minute_status = ""
        self.last_meaningful_signature: Optional[tuple[Any, ...]] = None
        self.last_week_plan_key = ""
        self.last_trade_request_monotonic = 0.0
        self._session_times_cache: dict[date, SessionTimes] = {}

    # ----- MT5 connection -----------------------------------------------------

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
        if not mt5.symbol_select(self.cfg.trade_symbol, True):
            raise RuntimeError(f"Cannot select trade symbol {self.cfg.trade_symbol}: {mt5.last_error()}")
        if not mt5.symbol_select(self.cfg.signal_symbol, True):
            raise RuntimeError(f"Cannot select signal symbol {self.cfg.signal_symbol}: {mt5.last_error()}")

        self.connected = True
        self.log.info("EVENT CONNECTED build=%s script=%s account=%s server=%s trade=%s signal=%s live=%s", BUILD_ID, Path(__file__).resolve(), getattr(account, "login", "?"), getattr(account, "server", "?"), self.cfg.trade_symbol, self.cfg.signal_symbol, self.cfg.live_enabled)
        if not self.cfg.live_enabled:
            self.log.warning("EVENT DRY_RUN set OPPW_LIVE=1 to permit BUY, SL/TP and weekly TO requests")

    def disconnect(self) -> None:
        if self.connected:
            mt5.shutdown()
            self.connected = False

    def connection_healthy(self) -> bool:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        return terminal is not None and account is not None and bool(getattr(terminal, "connected", True))

    # ----- Market calendar ----------------------------------------------------

    @staticmethod
    def week_bounds(day: date) -> tuple[date, date]:
        monday = day - timedelta(days=day.weekday())
        return monday, monday + timedelta(days=4)

    def trading_sessions_for_week(self, day: date) -> list[date]:
        monday, friday = self.week_bounds(day)
        sessions = self.calendar.sessions_in_range(monday.isoformat(), friday.isoformat())
        return [session.date() for session in sessions]

    def final_trading_day(self, day: date) -> Optional[date]:
        sessions = self.trading_sessions_for_week(day)
        return sessions[-1] if sessions else None

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

        lead = timedelta(seconds=SCHEDULED_ACTION_LEAD_SECONDS)
        open_action = cash_open - lead
        weekly_close = close_bar_open - lead
        value = SessionTimes(cash_open, open_action, weekly_close, close_bar_open, close_processing)
        self._session_times_cache[day] = value
        return value

    def log_week_plan(self, day: date) -> None:
        key = iso_week_key(day)
        if key == self.last_week_plan_key:
            return
        sessions = self.trading_sessions_for_week(day)
        final_day = sessions[-1] if sessions else None
        weekly_to = self.session_times(final_day).weekly_close.strftime("%Y-%m-%d %H:%M:%S %Z") if final_day else "none"
        self.last_week_plan_key = key
        self.log.info("EVENT WEEK_PLAN week=%s sessions=%s final_day=%s open_action=%s weekly_TO=%s", key, ",".join(value.isoformat() for value in sessions) or "none", final_day, self.session_times(day).open_action.strftime("%Y-%m-%d %H:%M:%S %Z"), weekly_to)

    # ----- Market data --------------------------------------------------------

    def latest_tick(self, symbol: str):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed: {mt5.last_error()}")
        return tick

    def mt5_bar_timestamp_to_local(self, timestamp: float) -> datetime:
        # This broker exposes MT5 bar timestamps as local terminal wall-clock
        # values encoded in an epoch field. Interpreting them as UTC and then
        # converting to Warsaw adds the Warsaw UTC offset a second time.
        wall_clock = datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)
        return wall_clock.replace(tzinfo=self.tz)

    def local_to_mt5_bar_query_time(self, local_dt: datetime) -> datetime:
        # copy_rates_range receives an aware datetime, but this terminal expects
        # the requested local wall-clock value encoded as an epoch timestamp.
        wall_clock = local_dt.astimezone(self.tz).replace(tzinfo=None)
        return wall_clock.replace(tzinfo=UTC)

    def require_fresh_tick(self, symbol: str) -> Any:
        tick = self.latest_tick(symbol)
        timestamp = getattr(tick, "time_msc", 0) / 1000.0 if getattr(tick, "time_msc", 0) else tick.time
        age = datetime.now(UTC).timestamp() - timestamp
        if age > self.cfg.maximum_tick_age_seconds:
            raise RuntimeError(f"Stale tick for {symbol}: age={age:.1f}s")
        return tick

    def current_m1_bar(self, symbol: str) -> Optional[M1Bar]:
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 3)
        if rates is None or len(rates) == 0:
            return None
        row = max(rates, key=lambda item: int(item["time"]))
        raw_ts = int(row["time"])
        local_dt = self.mt5_bar_timestamp_to_local(raw_ts)
        return M1Bar(raw_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

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
        bar = self.m1_bar_at(symbol, local_day, self.session_times(local_day).cash_open.time())
        return None if bar is None else bar.open

    def previous_trading_date(self, current_day: date) -> Optional[date]:
        sessions = self.calendar.sessions_in_range((current_day - timedelta(days=14)).isoformat(), (current_day - timedelta(days=1)).isoformat())
        dates = [session.date() for session in sessions if session.date() < current_day]
        return dates[-1] if dates else None

    # ----- Position/history reconciliation -----------------------------------

    @staticmethod
    def position_identifier(position) -> int:
        return int(getattr(position, "identifier", 0) or position.ticket)

    def managed_position(self):
        positions = mt5.positions_get(symbol=self.cfg.trade_symbol)
        if positions is None:
            raise RuntimeError(f"positions_get failed: {mt5.last_error()}")

        longs = [position for position in positions if position.type == mt5.POSITION_TYPE_BUY]
        if not longs:
            return None

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

    def infer_position_leverage(self, position) -> int:
        from_comment = self.parse_leverage_from_comment(getattr(position, "comment", ""))
        if from_comment > 0:
            return from_comment
        if float(position.sl) > 0 and float(position.price_open) > 0:
            actual_ratio = float(position.sl) / float(position.price_open)
            candidates = (self.cfg.base_leverage, self.cfg.loss_leverage)
            return min(candidates, key=lambda leverage: abs(actual_ratio - self.hard_sl_ratio(leverage)))
        return self.choose_leverage()

    def clear_current_position_exit_state(self, clear_last_exit: bool = True) -> None:
        self.state.exit_latched_reason = ""
        self.state.exit_latched_at = ""
        self.state.active_sl_reason = ""
        self.state.active_tp_reason = ""
        self.state.active_sl_price = 0.0
        self.state.active_tp_price = 0.0
        self.state.active_protection_updated_at = ""
        self.state.active_protection_position_identifier = 0
        if clear_last_exit:
            self.state.last_exit_reason = ""
            self.state.last_exit_price = 0.0
            self.state.last_exit_time = ""

    def weekday_sl_reason(self, now: datetime) -> str:
        session = self.session_times(now.date())
        first_minute_end = session.cash_open + timedelta(minutes=1)
        if now.weekday() == 3 and session.cash_open <= now < session.close_processing:
            return "TSL1" if now < first_minute_end else "TSL2"
        if now.weekday() == 4 and session.cash_open <= now < session.close_processing:
            return "TSL3" if now < first_minute_end else "TSL4"
        return "SL"

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
            thursday_sl = entry * self.cfg.thursday_sl_ratio
            friday_sl = entry * self.cfg.friday_sl_ratio
            hard_sl = entry * self.hard_sl_ratio(self.state.entry_leverage or self.choose_leverage())
            if abs(sl - thursday_sl) <= tolerance:
                self.state.active_sl_reason = "TSL1" if now.weekday() == 3 and now < self.session_times(now.date()).cash_open + timedelta(minutes=1) else "TSL2"
            elif abs(sl - friday_sl) <= tolerance:
                self.state.active_sl_reason = "TSL3" if now.weekday() == 4 and now < self.session_times(now.date()).cash_open + timedelta(minutes=1) else "TSL4"
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
            self.state.active_sl_reason, self.state.active_tp_reason,
            self.state.active_sl_price, self.state.active_tp_price,
            self.state.active_protection_position_identifier,
        )

        if sl > 0:
            same_sl = same_position and abs(self.state.active_sl_price - sl) <= tolerance
            if not same_sl or not self.state.active_sl_reason:
                self.state.active_sl_reason = sl_reason or self.state.active_sl_reason or "SL"
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
            self.state.active_sl_reason, self.state.active_tp_reason,
            self.state.active_sl_price, self.state.active_tp_price,
            self.state.active_protection_position_identifier,
        )
        if after != before:
            self.state.active_protection_updated_at = now.isoformat()
            self.state.save(self.cfg.state_file)

    @staticmethod
    def deal_reason_name(reason_code: int) -> str:
        names = {
            getattr(mt5, "DEAL_REASON_CLIENT", 0): "CLIENT",
            getattr(mt5, "DEAL_REASON_MOBILE", 1): "MOBILE",
            getattr(mt5, "DEAL_REASON_WEB", 2): "WEB",
            getattr(mt5, "DEAL_REASON_EXPERT", 3): "EXPERT",
            getattr(mt5, "DEAL_REASON_SL", 4): "SL",
            getattr(mt5, "DEAL_REASON_TP", 5): "TP",
            getattr(mt5, "DEAL_REASON_SO", 6): "STOP_OUT",
            getattr(mt5, "DEAL_REASON_ROLLOVER", 7): "ROLLOVER",
            getattr(mt5, "DEAL_REASON_VMARGIN", 8): "VARIATION_MARGIN",
            getattr(mt5, "DEAL_REASON_SPLIT", 9): "SPLIT",
            getattr(mt5, "DEAL_REASON_CORPORATE_ACTION", 10): "CORPORATE_ACTION",
        }
        return names.get(reason_code, f"UNKNOWN_{reason_code}")

    def resolve_closed_position_reason(self, exit_deal) -> tuple[str, str]:
        if exit_deal is None:
            return self.state.exit_latched_reason or self.state.last_exit_reason or "broker/manual", "UNRESOLVED"

        broker_code = int(getattr(exit_deal, "reason", -1))
        broker_reason = self.deal_reason_name(broker_code)
        if broker_code == getattr(mt5, "DEAL_REASON_SL", 4):
            return self.state.active_sl_reason or "SL", broker_reason
        if broker_code == getattr(mt5, "DEAL_REASON_TP", 5):
            return self.state.active_tp_reason or "TP", broker_reason
        if self.state.exit_latched_reason:
            return self.state.exit_latched_reason, broker_reason
        if self.state.last_exit_reason:
            return self.state.last_exit_reason, broker_reason
        return "broker/manual", broker_reason

    def reconstruct_break_even(self, opened: date, signal_reference: float, now: datetime) -> bool:
        if signal_reference <= 0:
            return False
        final_day = now.date() if now >= self.session_times(now.date()).close_processing else now.date() - timedelta(days=1)
        if final_day <= opened:
            return False

        sessions = self.calendar.sessions_in_range((opened + timedelta(days=1)).isoformat(), final_day.isoformat())
        for session in sessions:
            session_day = session.date()
            bar = self.m1_bar_at(self.cfg.signal_symbol, session_day, self.session_times(session_day).close_bar_open.time())
            if bar is not None and bar.close < signal_reference * self.cfg.break_even_ratio:
                return True
        return False

    def recover_position_state(self, position, now: datetime, force: bool = False) -> bool:
        identifier = self.position_identifier(position)
        same_position = self.state.active_position_identifier == identifier and self.state.entry_price > 0
        if same_position and not force:
            return False

        opened = datetime.fromtimestamp(int(position.time), UTC).astimezone(self.tz)
        leverage = self.infer_position_leverage(position)
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, opened.date())
        cash_open = self.session_times(opened.date()).cash_open
        signal_pending = signal_open is None and (opened < cash_open or self.state.entry_signal_open_pending)
        if signal_open is None:
            if signal_pending:
                signal_open = self.state.entry_signal_daily_open if same_position else 0.0
                self.log.warning("EVENT RECOVERY_SIGNAL_OPEN_PENDING open_day=%s cash_open=%s", opened.date(), cash_open.isoformat())
            else:
                signal_open = float(position.price_open)
                self.log.warning("EVENT RECOVERY_SIGNAL_OPEN_MISSING open_day=%s fallback=entry_price", opened.date())

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
        self.state.prev_open = float(position.price_open)
        self.state.last_entry_week = iso_week_key(opened.date())
        self.state.entry_pending_until_utc = 0
        self.state.break_even = recovered_break_even
        if previous_identifier != identifier:
            self.clear_current_position_exit_state(clear_last_exit=True)
            self.state.last_processed_bar_utc = 0
            self.state.last_close_processed_date = ""
            self.infer_active_protection(position, now)
        elif force and self.state.active_protection_position_identifier != identifier:
            self.infer_active_protection(position, now)
        self.state.save(self.cfg.state_file)
        self.log.info(
            "EVENT POSITION_RECOVERED ticket=%s identifier=%s magic=%s open_time=%s entry=%.5f volume=%s leverage=%s signal_open=%.5f signal_open_pending=%s break_even=%s",
            position.ticket, identifier, getattr(position, "magic", 0), opened.isoformat(), float(position.price_open),
            position.volume, leverage, float(signal_open), signal_pending, recovered_break_even,
        )
        return True


    def capture_entry_signal_open(self, position, now: datetime) -> bool:
        if position is None or not self.state.entry_signal_open_pending:
            return False
        opened = parse_date(self.state.open_date)
        if opened is None or now < self.session_times(opened).cash_open:
            return False
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, opened)
        if signal_open is None:
            return False
        self.state.entry_signal_daily_open = float(signal_open)
        self.state.entry_signal_open_pending = False
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

    def finalize_closed_position(self) -> None:
        identifier = self.state.active_position_identifier
        if not identifier:
            return

        deals = mt5.history_deals_get(position=identifier)
        exit_deal = None
        if deals:
            out_values = {getattr(mt5, "DEAL_ENTRY_OUT", 1), getattr(mt5, "DEAL_ENTRY_OUT_BY", 3)}
            candidates = [deal for deal in deals if int(getattr(deal, "entry", -1)) in out_values]
            if candidates:
                exit_deal = max(candidates, key=lambda deal: int(getattr(deal, "time_msc", 0) or deal.time * 1000))

        reason, broker_reason = self.resolve_closed_position_reason(exit_deal)
        if exit_deal is not None and self.state.entry_price > 0:
            exit_price = float(exit_deal.price)
            change = truncate_four_decimals(exit_price / self.state.entry_price - 1.0)
            self.state.prev_change = change
            self.state.last_exit_price = exit_price
            exit_timestamp = getattr(exit_deal, "time_msc", 0) / 1000.0 if getattr(exit_deal, "time_msc", 0) else exit_deal.time
            self.state.last_exit_time = datetime.fromtimestamp(exit_timestamp, UTC).astimezone(self.tz).isoformat()
            self.log.info(
                "EVENT POSITION_CLOSED reason=%s broker_reason=%s deal_ticket=%s entry=%.5f exit=%.5f change=%.4f active_sl_reason=%s active_tp_reason=%s",
                reason, broker_reason, getattr(exit_deal, "ticket", 0), self.state.entry_price, exit_price, change,
                self.state.active_sl_reason or "-", self.state.active_tp_reason or "-",
            )
        else:
            self.log.warning("EVENT POSITION_DISAPPEARED identifier=%s closing_deal=unresolved reason=%s", identifier, reason)

        self.state.last_exit_reason = reason
        self.state.active_position_identifier = 0
        self.state.active_position_ticket = 0
        self.state.open_date = ""
        self.state.entry_price = 0.0
        self.state.entry_signal_daily_open = 0.0
        self.state.entry_signal_open_pending = False
        self.state.entry_leverage = 0
        self.state.break_even = False
        self.state.exit_latched_reason = ""
        self.state.exit_latched_at = ""
        self.state.active_sl_reason = ""
        self.state.active_tp_reason = ""
        self.state.active_sl_price = 0.0
        self.state.active_tp_price = 0.0
        self.state.active_protection_updated_at = ""
        self.state.active_protection_position_identifier = 0
        self.state.entry_pending_until_utc = 0
        self.state.save(self.cfg.state_file)

    # ----- Status -------------------------------------------------------------

    def phase(self, now: datetime) -> str:
        session = self.session_times(now.date())
        if now < session.cash_open:
            return "PREMARKET"
        if now < session.weekly_close:
            return "REGULAR"
        if now < session.close_processing:
            return "CLOSE_WINDOW"
        return "POST_CLOSE"

    def protection_regime(self, now: datetime) -> str:
        if self.state.exit_latched_reason:
            return f"EXIT_BRACKET:{self.state.exit_latched_reason}"
        session = self.session_times(now.date())
        if session.cash_open <= now < session.close_processing:
            if now.weekday() == 3:
                return "THURSDAY_TIGHT_SL" + ("+BE_TP" if self.state.break_even else "")
            if now.weekday() == 4:
                return "FRIDAY_TIGHT_SL" + ("+BE_TP" if self.state.break_even else "")
            if self.state.break_even:
                return "HARD_SL+BE_TP"
        return "HARD_SL"

    def weekly_exit_status(self, position, now: datetime) -> tuple[bool, str, Optional[date]]:
        if position is None:
            return False, "FLAT", self.final_trading_day(now.date())
        opened = parse_date(self.state.open_date) or datetime.fromtimestamp(int(position.time), UTC).astimezone(self.tz).date()
        open_week_final = self.final_trading_day(opened)
        current_week_final = self.final_trading_day(now.date())
        if open_week_final is not None and now.date() > open_week_final:
            return True, "OVERDUE_TO", open_week_final
        if current_week_final == now.date() and now >= self.session_times(now.date()).weekly_close:
            return True, "TO", current_week_final
        return False, "WAIT", current_week_final

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

        def add_candidate(name: str, price: float) -> None:
            if not name or price <= 0:
                return
            for existing_name, existing_price in candidates:
                if existing_name == name and abs(existing_price - price) <= tolerance:
                    return
            candidates.append((name, price))

        leverage = self.state.entry_leverage or self.choose_leverage()
        hard_sl = floor_step(entry * self.hard_sl_ratio(leverage), tick_size)
        add_candidate("SL", hard_sl)

        session = self.session_times(now.date())
        in_session = session.cash_open <= now < session.close_processing
        if now.weekday() == 3:
            thursday_sl = floor_step(entry * self.cfg.thursday_sl_ratio, tick_size)
            if now < session.cash_open:
                add_candidate("TSL1PRE", thursday_sl)
            elif in_session:
                add_candidate(self.state.active_sl_reason if self.state.active_sl_reason in {"TSL1", "TSL2"} else self.weekday_sl_reason(now), thursday_sl)
        elif now.weekday() == 4 and in_session:
            friday_sl = floor_step(entry * self.cfg.friday_sl_ratio, tick_size)
            add_candidate(self.state.active_sl_reason if self.state.active_sl_reason in {"TSL3", "TSL4"} else self.weekday_sl_reason(now), friday_sl)

        if float(position.sl) > 0:
            add_candidate(self.state.active_sl_reason or "BROKER_SL", float(position.sl))

        if self.state.break_even:
            be_price = ceil_step(entry * self.cfg.break_even_ratio, tick_size)
            if now < session.cash_open:
                be_name = "BEPRE"
            elif now < session.cash_open + timedelta(minutes=1):
                be_name = "BEO"
            else:
                be_name = self.state.active_tp_reason or "BH"
            add_candidate(be_name, be_price)

        if float(position.tp) > 0:
            add_candidate(self.state.active_tp_reason or "BROKER_TP", float(position.tp))

        if not candidates:
            return "none"

        name, price = min(candidates, key=lambda item: abs(item[1] - bid))
        difference = price - bid
        distance = abs(difference)
        distance_pct = distance / bid * 100.0 if bid > 0 else 0.0
        if abs(difference) <= tolerance:
            direction = "at current price"
        elif difference > 0:
            direction = "above"
        else:
            direction = "below"
        return f"{name} @ {price:.5f} — {distance:.5f} points {direction} ({distance_pct:.4f}%)"

    def format_status(self, reason: str, position, now: datetime, current_bar: Optional[M1Bar] = None) -> str:
        due, due_reason, final_day = self.weekly_exit_status(position, now)
        account = mt5.account_info()
        balance = float(getattr(account, "balance", 0.0)) if account is not None else 0.0
        equity = float(getattr(account, "equity", 0.0)) if account is not None else 0.0
        currency = str(getattr(account, "currency", "")).strip() if account is not None else ""
        currency_suffix = f" {currency}" if currency else ""

        lines = [
            "==================== TRADE STATUS ====================",
            f"reason: {reason}",
            f"time: {now:%Y-%m-%d %H:%M:%S %Z}",
            f"week: {iso_week_key(now.date())}",
            f"phase: {self.phase(now)}",
        ]

        if position is None:
            leverage = self.choose_leverage()
            lines.extend([
                "position: FLAT",
                f"deposit: {0.0:.2f}{currency_suffix}",
                f"equity: {equity:.2f}{currency_suffix}",
                f"current P/L: 0.00{currency_suffix}",
                "current P/L %: 0.0000%",
                f"leverage: {leverage}x",
                "current P/L % leveraged: 0.0000%",
                "closest condition: none — no open position",
                f"final trading day: {final_day or '-'}",
                f"weekly exit: {due_reason}",
                f"last exit: {self.state.last_exit_reason or '-'}",
                f"build: {BUILD_ID}",
                "======================================================",
            ])
            return "\n" + "\n".join(lines) + "\n"

        try:
            tick = self.latest_tick(position.symbol)
            bid = float(tick.bid)
            ask = float(tick.ask)
        except Exception:
            bid = float(getattr(position, "price_current", 0.0))
            ask = 0.0

        entry = float(position.price_open)
        raw_pnl_pct = (bid / entry - 1.0) if bid > 0 and entry > 0 else 0.0
        leverage = self.state.entry_leverage or self.choose_leverage()
        leveraged_pnl_pct = raw_pnl_pct * leverage
        current_pnl = float(getattr(position, "profit", 0.0)) + float(getattr(position, "swap", 0.0))
        info = mt5.symbol_info(position.symbol)
        quantum_price = ask if ask > 0 else bid if bid > 0 else entry
        sizing_quantum = self.minimum_volume_notional(info, quantum_price) / self.cfg.sizing_multiplier if info is not None and quantum_price > 0 else 0.0
        deposit = float(position.volume) * sizing_quantum
        opened = datetime.fromtimestamp(int(position.time), UTC).astimezone(self.tz)
        side = "BUY" if int(getattr(position, "type", getattr(mt5, "POSITION_TYPE_BUY", 0))) == getattr(mt5, "POSITION_TYPE_BUY", 0) else "SELL"
        closest = self.closest_price_condition(position, now, bid)
        bar_text = "none" if current_bar is None else f"{current_bar.local_datetime:%H:%M} O={current_bar.open:.5f} H={current_bar.high:.5f} L={current_bar.low:.5f} C={current_bar.close:.5f}"

        lines.extend([
            f"position: {side} {position.symbol} {float(position.volume):.4f} lot",
            f"ticket: {position.ticket}",
            f"opened: {opened:%Y-%m-%d %H:%M:%S %Z}",
            f"open price: {entry:.5f}",
            f"current bid / ask: {bid:.5f} / {ask:.5f}",
            f"deposit: {deposit:.2f}{currency_suffix}",
            f"equity: {equity:.2f}{currency_suffix}",
            f"current P/L: {current_pnl:.2f}{currency_suffix}",
            f"current P/L %: {raw_pnl_pct:.4%}",
            f"leverage: {leverage}x",
            f"current P/L % leveraged: {leveraged_pnl_pct:.4%}",
            f"SL: {float(position.sl):.5f} ({self.state.active_sl_reason or '-'})",
            f"TP: {float(position.tp):.5f} ({self.state.active_tp_reason or '-'})",
            f"closest condition: {closest}",
            f"break-even armed: {self.state.break_even}",
            f"protection regime: {self.protection_regime(now)}",
            f"exit latch: {self.state.exit_latched_reason or '-'}",
            f"final trading day: {final_day or '-'}",
            f"weekly exit: {due_reason} (due={due})",
            f"current M1: {bar_text}",
            f"build: {BUILD_ID}",
            "======================================================",
        ])
        return "\n" + "\n".join(lines) + "\n"

    def emit_status(self, reason: str, position=None, now: Optional[datetime] = None, current_bar: Optional[M1Bar] = None) -> None:
        now = now or datetime.now(self.tz)
        if position is None:
            position = self.managed_position()
        self.log.info(self.format_status(reason, position, now, current_bar))

    def status_signature(self, position, now: datetime) -> tuple[Any, ...]:
        due, due_reason, final_day = self.weekly_exit_status(position, now)
        return (
            iso_week_key(now.date()), self.phase(now), self.protection_regime(now), bool(position),
            0 if position is None else self.position_identifier(position),
            0.0 if position is None else round(float(position.sl), 8),
            0.0 if position is None else round(float(position.tp), 8),
            self.state.break_even, self.state.exit_latched_reason, final_day, due, due_reason,
            self.is_new_week_entry(now.date()) if position is None else False,
        )

    @staticmethod
    def check_value(value: Any) -> str:
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if value is None:
            return "none"
        if isinstance(value, float):
            return f"{value:.8f}"
        return str(value).replace(" ", "_")

    def log_check(self, now: datetime, name: str, result: bool, **details: Any) -> None:
        detail_text = " ".join(f"{key}={self.check_value(value)}" for key, value in details.items())
        self.log.info(
            "CHECK minute=%s weekday=%s phase=%s name=%s result=%s%s",
            now.strftime("%Y-%m-%d_%H:%M"), now.strftime("%A"), self.phase(now), name,
            "TRUE" if result else "FALSE", f" {detail_text}" if detail_text else "",
        )

    def log_minute_condition_report(self, position, now: datetime, current_bar: Optional[M1Bar]) -> None:
        current_day = now.date()
        weekday = current_day.weekday()
        phase = self.phase(now)
        week = iso_week_key(current_day)
        sessions = self.trading_sessions_for_week(current_day)
        final_day = sessions[-1] if sessions else None
        is_session = current_day in sessions
        is_final_day = final_day == current_day
        session = self.session_times(current_day)

        self.log.info(
            "CONDITION_REPORT_BEGIN minute=%s week=%s weekday=%s phase=%s position=%s",
            now.strftime("%Y-%m-%d %H:%M"), week, now.strftime("%A"), phase,
            "OPEN" if position is not None else "FLAT",
        )
        self.log_check(now, "TRADING_SESSION_TODAY", is_session, date=current_day, final_day=final_day)
        self.log_check(now, "LAST_TRADING_DAY_OF_WEEK", is_final_day, date=current_day, final_day=final_day)

        if position is None:
            previous = parse_date(self.state.last_trading_date)
            discovered = self.previous_trading_date(current_day)
            if discovered is not None and (previous is None or discovered > previous or previous >= current_day):
                previous = discovered
            entry_day_allowed = weekday in (0, 1)
            week_not_entered = self.state.last_entry_week != week
            previous_gap = previous is not None and (current_day - previous).days > 1
            execution_window_open = session.open_action <= now <= session.cash_open + timedelta(seconds=self.cfg.entry_window_seconds)
            pending_clear = int(datetime.now(UTC).timestamp()) >= self.state.entry_pending_until_utc
            fresh_tick = False
            tick_age_error = "none"
            try:
                self.require_fresh_tick(self.cfg.trade_symbol)
                fresh_tick = True
            except RuntimeError as exc:
                tick_age_error = str(exc)
            new_week_entry = entry_day_allowed and week_not_entered and previous_gap
            buy_eligible = new_week_entry and execution_window_open and pending_clear and fresh_tick and not self.state.exit_latched_reason

            self.log_check(now, "POSITION_OPEN", False)
            self.log_check(now, "ENTRY_DAY_MONDAY_OR_TUESDAY", entry_day_allowed, weekday_index=weekday)
            self.log_check(now, "WEEK_NOT_ALREADY_ENTERED", week_not_entered, last_entry_week=self.state.last_entry_week or "none", current_week=week)
            self.log_check(now, "PREVIOUS_TRADING_DAY_GAP_GT_1", previous_gap, previous_trading_day=previous, gap_days=(current_day - previous).days if previous else None)
            self.log_check(now, "NEW_WEEK_ENTRY", new_week_entry)
            self.log_check(now, "BUY_TIME_REACHED", now >= session.open_action, scheduled=session.open_action.strftime("%H:%M:%S"), cash_open=session.cash_open.strftime("%H:%M:%S"))
            self.log_check(now, "ENTRY_EXECUTION_WINDOW_OPEN", execution_window_open, scheduled=session.open_action.strftime("%H:%M:%S"), latest=(session.cash_open + timedelta(seconds=self.cfg.entry_window_seconds)).strftime("%H:%M:%S"))
            self.log_check(now, "ENTRY_PENDING_CLEAR", pending_clear, pending_until_utc=self.state.entry_pending_until_utc)
            self.log_check(now, "FRESH_TRADE_TICK", fresh_tick, error=tick_age_error)
            self.log_check(now, "EXIT_LATCH_CLEAR", not bool(self.state.exit_latched_reason), exit_latch=self.state.exit_latched_reason or "none")
            self.log_check(now, "BUY_ELIGIBLE", buy_eligible)
            self.log.info("CONDITION_REPORT_END minute=%s checks=13", now.strftime("%Y-%m-%d %H:%M"))
            return

        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)
        bar_available = current_bar is not None and current_bar.local_datetime.date() == current_day
        due, due_reason, due_final_day = self.weekly_exit_status(position, now)
        day_key = current_day.isoformat()
        if self.state.last_open_action_date == day_key:
            open_action_status = "PROCESSED"
        elif now < session.open_action:
            open_action_status = "PENDING"
        elif now < session.cash_open:
            open_action_status = "DUE"
        else:
            open_action_status = "MISSED"
        open_action_pending = open_action_status in ("PENDING", "DUE")

        if self.state.last_close_action_date == day_key:
            close_action_status = "PROCESSED"
        elif now < session.weekly_close:
            close_action_status = "PENDING"
        elif now < session.close_bar_open:
            close_action_status = "DUE"
        else:
            close_action_status = "OVERDUE" if is_final_day else "MISSED"
        close_action_pending = close_action_status in ("PENDING", "DUE", "OVERDUE")

        self.log_check(now, "POSITION_OPEN", True, ticket=int(position.ticket), entry=entry, volume=float(position.volume))
        self.log_check(now, "CURRENT_M1_AVAILABLE", bar_available, bar_time=current_bar.local_datetime.strftime("%H:%M") if bar_available else None)
        self.log_check(now, "ENTRY_SIGNAL_OPEN_AVAILABLE", self.state.entry_signal_daily_open > 0 and not self.state.entry_signal_open_pending, signal_open=self.state.entry_signal_daily_open, pending=self.state.entry_signal_open_pending)
        self.log_check(now, "EXIT_LATCH_CLEAR", not bool(self.state.exit_latched_reason), exit_latch=self.state.exit_latched_reason or "none")
        self.log_check(now, "OPEN_MINUS_3_REACHED", now >= session.open_action, scheduled=session.open_action.strftime("%H:%M:%S"), action_status=open_action_status, action_pending=open_action_pending)
        self.log_check(now, "CLOSE_MINUS_3_REACHED", now >= session.weekly_close, scheduled=session.weekly_close.strftime("%H:%M:%S"), action_status=close_action_status, action_pending=close_action_pending)
        self.log_check(now, "TO", due, due_reason=due_reason, final_day=due_final_day)
        check_count = 9

        if self.state.exit_latched_reason:
            self.log.info("CONDITION_REPORT_END minute=%s checks=%s reason=exit_latched", now.strftime("%Y-%m-%d %H:%M"), check_count)
            return

        try:
            trade_tick = self.require_fresh_tick(position.symbol)
            bid = float(trade_tick.bid)
            tpp = self.cfg.tpps[weekday]
            oh = bid > entry * (1.0 + tpp)
            self.log_check(now, "OH", oh, scheduled=session.open_action.strftime("%H:%M:%S"), action_status=open_action_status, action_pending=open_action_pending, execution_eligible=(open_action_status == "DUE"), bid=bid, entry=entry, tpp=tpp, threshold=entry * (1.0 + tpp))
        except RuntimeError as exc:
            self.log_check(now, "OH", False, scheduled=session.open_action.strftime("%H:%M:%S"), action_status=open_action_status, action_pending=open_action_pending, execution_eligible=(open_action_status == "DUE"), error=str(exc))
        check_count += 1

        if bar_available:
            bar = current_bar
            bar_time = bar.local_datetime.time().replace(second=0, microsecond=0)
            cash_open_time = session.cash_open.time().replace(second=0, microsecond=0)
            close_processing_time = session.close_processing.time().replace(second=0, microsecond=0)

            if self.cfg.premarket_start <= bar_time < cash_open_time:
                if weekday == 3:
                    tsl1pre = bar.open / entry < self.cfg.thursday_sl_ratio
                    self.log_check(now, "TSL1PRE", tsl1pre, bar_open=bar.open, entry=entry, ratio=bar.open / entry, threshold=self.cfg.thursday_sl_ratio)
                    check_count += 1
                bepre = self.state.break_even and bar.open > entry * self.cfg.break_even_ratio
                self.log_check(now, "BEPRE", bepre, break_even_armed=self.state.break_even, bar_open=bar.open, threshold=entry * self.cfg.break_even_ratio)
                check_count += 1

            if bar_time == cash_open_time:
                beo = self.state.break_even and bar.open > entry * self.cfg.break_even_ratio
                self.log_check(now, "BEO", beo, break_even_armed=self.state.break_even, cash_open=bar.open, threshold=entry * self.cfg.break_even_ratio)
                check_count += 1
                info = mt5.symbol_info(position.symbol)
                tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
                if weekday == 3:
                    required_sl = floor_step(entry * self.cfg.thursday_sl_ratio, tick_size)
                    tsl1_set = float(position.sl) > 0 and float(position.sl) + tick_size / 2 >= required_sl
                    self.log_check(now, "TSL1", tsl1_set, current_sl=float(position.sl), required_sl=required_sl, threshold=self.cfg.thursday_sl_ratio)
                    check_count += 1
                if weekday == 4:
                    required_sl = floor_step(entry * self.cfg.friday_sl_ratio, tick_size)
                    tsl3_set = float(position.sl) > 0 and float(position.sl) + tick_size / 2 >= required_sl
                    self.log_check(now, "TSL3", tsl3_set, current_sl=float(position.sl), required_sl=required_sl, threshold=self.cfg.friday_sl_ratio)
                    check_count += 1

            if cash_open_time <= bar_time < close_processing_time:
                info = mt5.symbol_info(position.symbol)
                tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
                if weekday == 3:
                    required_sl = floor_step(entry * self.cfg.thursday_sl_ratio, tick_size)
                    tsl2_set = float(position.sl) > 0 and float(position.sl) + tick_size / 2 >= required_sl
                    self.log_check(now, "TSL2", tsl2_set, current_sl=float(position.sl), required_sl=required_sl, threshold=self.cfg.thursday_sl_ratio)
                    check_count += 1
                if weekday == 4:
                    required_sl = floor_step(entry * self.cfg.friday_sl_ratio, tick_size)
                    tsl4_set = float(position.sl) > 0 and float(position.sl) + tick_size / 2 >= required_sl
                    self.log_check(now, "TSL4", tsl4_set, current_sl=float(position.sl), required_sl=required_sl, threshold=self.cfg.friday_sl_ratio)
                    check_count += 1
                bh = self.state.break_even and bar.high > entry * self.cfg.break_even_ratio
                self.log_check(now, "BH", bh, break_even_armed=self.state.break_even, bar_high=bar.high, threshold=entry * self.cfg.break_even_ratio)
                check_count += 1

        try:
            signal_price = self.live_signal_price()
            signal_reference = self.state.entry_signal_daily_open
            tpp = self.cfg.tpps[weekday]
            ch = signal_reference > 0 and signal_price > signal_reference * (1.0 + tpp)
            self.log_check(now, "CH", ch, scheduled=session.weekly_close.strftime("%H:%M:%S"), action_status=close_action_status, action_pending=close_action_pending, execution_eligible=(close_action_status in ("DUE", "OVERDUE")), signal_price=signal_price, signal_reference=signal_reference, tpp=tpp, threshold=signal_reference * (1.0 + tpp) if signal_reference > 0 else 0.0)
        except RuntimeError as exc:
            self.log_check(now, "CH", False, scheduled=session.weekly_close.strftime("%H:%M:%S"), action_status=close_action_status, action_pending=close_action_pending, execution_eligible=(close_action_status in ("DUE", "OVERDUE")), error=str(exc))
        check_count += 1

        if now >= session.close_processing:
            close_bar_time = session.close_bar_open.time().replace(second=0, microsecond=0)
            trade_close_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, close_bar_time)
            signal_close_bar = self.m1_bar_at(self.cfg.signal_symbol, current_day, close_bar_time)
            close_bars_available = trade_close_bar is not None and signal_close_bar is not None
            self.log_check(now, "CLOSE_BARS_AVAILABLE", close_bars_available)
            check_count += 1
            if close_bars_available:
                signal_reference = self.state.entry_signal_daily_open or self.state.entry_price
                if weekday == 2:
                    tsl0_ratio = (trade_close_bar.close + 100000.0) / entry
                    tsl0 = tsl0_ratio < self.cfg.thursday_sl_ratio
                    self.log_check(now, "TSL0", tsl0, trade_close=trade_close_bar.close, entry=entry, ratio=tsl0_ratio, threshold=self.cfg.thursday_sl_ratio)
                    check_count += 1
                opened = parse_date(self.state.open_date)
                later_session = opened is not None and (current_day - opened).days != 0
                be_arm = not self.state.break_even and later_session and signal_close_bar.close < signal_reference * self.cfg.break_even_ratio
                self.log_check(now, "BREAK_EVEN_ARM", be_arm, already_armed=self.state.break_even, later_session=later_session, signal_close=signal_close_bar.close, threshold=signal_reference * self.cfg.break_even_ratio)
                check_count += 1

        self.log.info("CONDITION_REPORT_END minute=%s checks=%s", now.strftime("%Y-%m-%d %H:%M"), check_count)

    def log_status_if_needed(self, position, now: datetime, current_bar: Optional[M1Bar]) -> None:
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if minute_key != self.last_minute_status:
            self.last_minute_status = minute_key
            self.emit_status("MINUTE", position, now, current_bar)
            self.log_minute_condition_report(position, now, current_bar)

        signature = self.status_signature(position, now)
        if signature != self.last_meaningful_signature:
            self.last_meaningful_signature = signature
            self.emit_status("STATUS_CHANGE", position, now, current_bar)

    # ----- Strategy calculations ---------------------------------------------

    def choose_leverage(self) -> int:
        if self.cfg.base_leverage == 8 and (self.state.prev_full_week_change < -0.025 or self.state.prev_change < -0.007):
            return self.cfg.loss_leverage
        return self.cfg.base_leverage

    def hard_sl_ratio(self, leverage: int) -> float:
        return (100.0 - self.cfg.leverage_stop_points / leverage) / 100.0

    def hard_sl_price(self, position) -> float:
        leverage = self.state.entry_leverage or self.choose_leverage()
        return float(position.price_open) * self.hard_sl_ratio(leverage)

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

    def refresh_previous_full_week_change(self, previous_day: date) -> None:
        if self.state.prev_open <= 0:
            return
        close_bar = self.m1_bar_at(self.cfg.trade_symbol, previous_day, self.session_times(previous_day).close_bar_open.time())
        if close_bar is None:
            self.log.warning("EVENT FULL_WEEK_CHANGE_NOT_UPDATED day=%s reason=no_22:00_bar", previous_day)
            return
        self.state.prev_full_week_change = close_bar.close / self.state.prev_open - 1.0
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT FULL_WEEK_CHANGE_UPDATED value=%.5f", self.state.prev_full_week_change)
        self.emit_status("FULL_WEEK_CHANGE_UPDATED")

    # ----- Sizing and trade requests -----------------------------------------

    def minimum_volume_notional(self, info, ask: float) -> float:
        minimum_volume = float(info.volume_min)
        if minimum_volume <= 0:
            raise RuntimeError(f"Invalid minimum volume for {self.cfg.trade_symbol}: {minimum_volume}")

        profit_for_one_percent = mt5.order_calc_profit(
            mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, minimum_volume, ask, ask * 1.01
        )
        if profit_for_one_percent is None or abs(profit_for_one_percent) <= 0:
            raise RuntimeError(f"Cannot derive minimum-volume notional: {mt5.last_error()}")

        return abs(float(profit_for_one_percent)) / 0.01

    def target_notional(self, balance: float, leverage: int, minimum_volume_notional: float) -> tuple[float, float, int]:
        if minimum_volume_notional <= 0:
            raise ValueError(f"Minimum-volume notional must be positive, got {minimum_volume_notional}")
        sizing_quantum = minimum_volume_notional / self.cfg.sizing_multiplier
        divisor = self.cfg.sizing_multiplier / leverage
        units = math.floor(balance / divisor / sizing_quantum)
        return minimum_volume_notional, sizing_quantum, units

    def normalized_volume(self, sizing_units: int, info) -> float:
        if sizing_units <= 0:
            return 0.0

        minimum_volume = float(info.volume_min)
        step = float(info.volume_step)
        volume = sizing_units * minimum_volume
        volume = min(floor_step(volume, step), float(info.volume_max))
        if volume < minimum_volume:
            return 0.0
        return round(volume, 8)

    def filling_mode_name(self, mode: int) -> str:
        names = {
            mt5.ORDER_FILLING_FOK: "FOK",
            mt5.ORDER_FILLING_IOC: "IOC",
            mt5.ORDER_FILLING_RETURN: "RETURN",
        }
        return names.get(mode, str(mode))

    def order_filling_modes(self, info) -> list[int]:
        configured = os.getenv("OPPW_FILLING_MODE", "AUTO").strip().upper()
        mapping = {"FOK": mt5.ORDER_FILLING_FOK, "IOC": mt5.ORDER_FILLING_IOC, "RETURN": mt5.ORDER_FILLING_RETURN}
        if configured in mapping:
            return [mapping[configured]]

        # info.filling_mode is a SYMBOL_FILLING_* bitmask, not an ORDER_FILLING_* enum.
        # Their numeric values overlap differently, so the raw value must never be
        # copied directly into request["type_filling"].
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

        # Broker metadata can occasionally be incomplete. Keep safe fallbacks,
        # but let order_check() validate each mode before an order is sent.
        for mode in (mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC):
            if mode not in modes:
                modes.append(mode)
        if execution != market_execution and mt5.ORDER_FILLING_RETURN not in modes:
            modes.append(mt5.ORDER_FILLING_RETURN)
        return modes

    def checked_deal_request(self, request_base: dict, info, event: str):
        last_request = None
        last_check = None
        invalid_fill = int(getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030))
        accepted_checks = {0, int(getattr(mt5, "TRADE_RETCODE_DONE", 10009))}

        for mode in self.order_filling_modes(info):
            request = dict(request_base)
            request["type_filling"] = mode
            check = mt5.order_check(request)
            last_request = request
            last_check = check
            retcode = None if check is None else int(check.retcode)

            if check is not None and retcode in accepted_checks:
                self.log.info(
                    "EVENT FILLING_SELECTED event=%s mode=%s symbol_flags=%s execution=%s",
                    event, self.filling_mode_name(mode), int(getattr(info, "filling_mode", 0)),
                    int(getattr(info, "trade_exemode", -1)),
                )
                return request, check

            if retcode == invalid_fill:
                self.log.warning(
                    "EVENT FILLING_REJECTED event=%s mode=%s retcode=%s comment=%s",
                    event, self.filling_mode_name(mode), retcode, getattr(check, "comment", ""),
                )
                continue

            return request, check

        return last_request, last_check

    def request_allowed_now(self) -> bool:
        elapsed = time_module.monotonic() - self.last_trade_request_monotonic
        if elapsed < self.cfg.request_retry_seconds:
            return False
        self.last_trade_request_monotonic = time_module.monotonic()
        return True

    def send_buy(self, current_day: date) -> bool:
        account = mt5.account_info()
        info = mt5.symbol_info(self.cfg.trade_symbol)
        tick = self.require_fresh_tick(self.cfg.trade_symbol)
        if account is None or info is None:
            raise RuntimeError(f"Cannot obtain account/symbol data: {mt5.last_error()}")

        leverage = self.choose_leverage()
        ask = float(tick.ask)
        minimum_volume_notional = self.minimum_volume_notional(info, ask)
        target_notional, sizing_quantum, sizing_units = self.target_notional(float(account.balance), leverage, minimum_volume_notional)
        if sizing_units <= 0:
            self.log.error(
                "EVENT BUY_SKIPPED reason=zero_sizing_units minimum_volume=%.8f minimum_volume_notional=%.2f sizing_quantum=%.2f sizing_units=%s",
                float(info.volume_min), minimum_volume_notional, sizing_quantum, sizing_units,
            )
            return False

        volume = self.normalized_volume(sizing_units, info)
        if volume <= 0:
            self.log.error("EVENT BUY_SKIPPED reason=volume_below_minimum sizing_units=%s minimum_volume=%.8f", sizing_units, float(info.volume_min))
            return False
        position_notional = sizing_units * target_notional

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        sl = floor_step(ask * self.hard_sl_ratio(leverage), tick_size)
        request_base = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": self.cfg.trade_symbol, "volume": volume,
            "type": mt5.ORDER_TYPE_BUY, "price": ask, "sl": sl, "tp": 0.0,
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": f"{self.cfg.comment_prefix} L{leverage}"[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        scheduled = self.session_times(current_day).open_action
        if not self.cfg.live_enabled:
            request = dict(request_base)
            request["type_filling"] = self.order_filling_modes(info)[0]
            self.log.info(
                "EVENT BUY_REQUEST day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f sizing_quantum=%.2f sizing_units=%s target_notional=%.2f position_notional=%.2f ask=%.5f sl=%.5f filling=%s",
                current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional, sizing_quantum, sizing_units,
                target_notional, position_notional, ask, sl, self.filling_mode_name(request["type_filling"]),
            )
            return False
        if not self.request_allowed_now():
            return False

        request, check = self.checked_deal_request(request_base, info, "BUY")
        self.log.info(
            "EVENT BUY_REQUEST day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f sizing_quantum=%.2f sizing_units=%s target_notional=%.2f position_notional=%.2f ask=%.5f sl=%.5f filling=%s",
            current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional, sizing_quantum, sizing_units,
            target_notional, position_notional, ask, sl, self.filling_mode_name(request["type_filling"]) if request else "NONE",
        )
        if request is None or check is None or int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            self.log.error("EVENT BUY_CHECK_REJECTED result=%s last_error=%s", check, mt5.last_error())
            return False
        result = mt5.order_send(request)
        if result is None:
            self.log.error("EVENT BUY_SEND_FAILED last_error=%s", mt5.last_error())
            return False

        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if int(result.retcode) not in accepted:
            self.log.error("EVENT BUY_REJECTED retcode=%s comment=%s", result.retcode, result.comment)
            return False

        signal_open = self.signal_cash_open(self.cfg.signal_symbol, current_day)
        self.state.entry_pending_until_utc = int(datetime.now(UTC).timestamp()) + 10
        self.state.open_date = current_day.isoformat()
        self.state.entry_price = ask
        self.state.entry_leverage = leverage
        self.state.prev_open = ask
        self.state.last_entry_week = iso_week_key(current_day)
        self.state.last_open_action_date = current_day.isoformat()
        self.state.entry_signal_daily_open = float(signal_open or 0.0)
        self.state.entry_signal_open_pending = signal_open is None
        self.state.break_even = False
        self.clear_current_position_exit_state(clear_last_exit=True)
        self.state.save(self.cfg.state_file)
        self.log.info(
            "EVENT BUY_ACCEPTED retcode=%s order=%s deal=%s preopen_seconds=%.3f signal_open=%.5f signal_open_pending=%s",
            result.retcode, getattr(result, "order", 0), getattr(result, "deal", 0),
            (self.session_times(current_day).cash_open - datetime.now(self.tz)).total_seconds(), float(signal_open or 0.0), signal_open is None,
        )
        time_module.sleep(0.1)
        position = self.managed_position()
        if position is not None:
            self.recover_position_state(position, datetime.now(self.tz), force=True)
        self.emit_status("BUY_ACCEPTED", position)
        return True

    def modify_sltp(self, position, desired_sl: float, desired_tp: float, reason: str, sl_reason: str = "", tp_reason: str = "") -> bool:
        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        digits = int(info.digits)
        desired_sl = round(desired_sl, digits) if desired_sl else 0.0
        desired_tp = round(desired_tp, digits) if desired_tp else 0.0
        tolerance = max(tick_size * 0.5, float(info.point) * 0.5)
        if not price_changed(float(position.sl), desired_sl, tolerance) and not price_changed(float(position.tp), desired_tp, tolerance):
            self.record_active_protection(position, desired_sl, desired_tp, sl_reason, tp_reason)
            return True

        if not self.cfg.live_enabled:
            self.log.info("EVENT SLTP_DRY_RUN reason=%s ticket=%s SL=%.5f->%.5f TP=%.5f->%.5f", reason, position.ticket, float(position.sl), desired_sl, float(position.tp), desired_tp)
            return False
        if not self.request_allowed_now():
            return False

        self.log.info("EVENT SLTP_REQUEST reason=%s ticket=%s SL=%.5f->%.5f TP=%.5f->%.5f", reason, position.ticket, float(position.sl), desired_sl, float(position.tp), desired_tp)
        request = {"action": mt5.TRADE_ACTION_SLTP, "symbol": position.symbol, "position": int(position.ticket), "sl": desired_sl, "tp": desired_tp, "magic": self.cfg.magic}
        result = mt5.order_send(request)
        if result is None:
            self.log.error("EVENT SLTP_SEND_FAILED last_error=%s", mt5.last_error())
            return False

        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_NO_CHANGES", 10025)}
        if int(result.retcode) not in accepted:
            self.log.error("EVENT SLTP_REJECTED retcode=%s comment=%s", result.retcode, result.comment)
            return False

        self.log.info("EVENT SLTP_ACCEPTED reason=%s retcode=%s", reason, result.retcode)
        refreshed = self.managed_position() or position
        self.record_active_protection(refreshed, desired_sl, desired_tp, sl_reason, tp_reason)
        self.emit_status("SLTP_ACCEPTED", refreshed)
        return True

    def close_position_market(self, position, reason: str, now: datetime) -> bool:
        if not self.request_allowed_now():
            return False
        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")
        try:
            tick = self.require_fresh_tick(position.symbol)
        except RuntimeError as exc:
            self.log.warning("EVENT MARKET_EXIT_WAIT reason=%s error=%s", reason, exc)
            return False

        request_base = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": position.symbol, "position": int(position.ticket),
            "volume": float(position.volume), "type": mt5.ORDER_TYPE_SELL, "price": float(tick.bid),
            "deviation": self.cfg.deviation_points, "magic": self.cfg.magic,
            "comment": f"{self.cfg.comment_prefix} {reason}"[:31],
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if not self.cfg.live_enabled:
            request = dict(request_base)
            request["type_filling"] = self.order_filling_modes(info)[0]
            self.log.warning(
                "EVENT MARKET_EXIT_REQUEST reason=%s ticket=%s volume=%s bid=%.5f time=%s filling=%s",
                reason, position.ticket, position.volume, float(tick.bid), now.isoformat(),
                self.filling_mode_name(request["type_filling"]),
            )
            return False

        request, check = self.checked_deal_request(request_base, info, f"MARKET_EXIT_{reason}")
        self.log.warning(
            "EVENT MARKET_EXIT_REQUEST reason=%s ticket=%s volume=%s bid=%.5f time=%s filling=%s",
            reason, position.ticket, position.volume, float(tick.bid), now.isoformat(),
            self.filling_mode_name(request["type_filling"]) if request else "NONE",
        )
        if request is None or check is None or int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            self.log.error("EVENT MARKET_EXIT_CHECK_REJECTED reason=%s result=%s last_error=%s", reason, check, mt5.last_error())
            return False

        result = mt5.order_send(request)
        if result is None:
            self.log.error("EVENT MARKET_EXIT_SEND_FAILED reason=%s last_error=%s", reason, mt5.last_error())
            return False
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if int(result.retcode) not in accepted:
            self.log.error("EVENT MARKET_EXIT_REJECTED reason=%s retcode=%s comment=%s", reason, result.retcode, result.comment)
            return False

        self.state.exit_latched_reason = reason
        self.state.exit_latched_at = now.isoformat()
        self.state.last_exit_reason = reason
        self.state.save(self.cfg.state_file)
        self.log.warning("EVENT MARKET_EXIT_ACCEPTED reason=%s retcode=%s order=%s deal=%s", reason, result.retcode, getattr(result, "order", 0), getattr(result, "deal", 0))
        time_module.sleep(0.1)
        remaining = self.managed_position()
        if remaining is None:
            self.finalize_closed_position()
        self.emit_status("MARKET_EXIT_ACCEPTED", remaining, datetime.now(self.tz))
        return True

    def broker_minimum_distance(self, info) -> float:
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
            self.log.warning("EVENT EXIT_CONDITION_LATCHED reason=%s", reason)
            self.emit_status("EXIT_LATCHED", position, now)
        self.apply_exit_bracket(position, self.state.exit_latched_reason)

    def apply_exit_bracket(self, position, reason: str) -> None:
        info = mt5.symbol_info(position.symbol)
        tick = self.require_fresh_tick(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

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
        self.modify_sltp(position, sl, tp, f"EXIT {reason}", sl_reason=reason, tp_reason=reason)

    def apply_standard_protection(self, position, now: datetime) -> None:
        if self.state.exit_latched_reason:
            self.apply_exit_bracket(position, self.state.exit_latched_reason)
            return

        info = mt5.symbol_info(position.symbol)
        tick = self.require_fresh_tick(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        distance = self.broker_minimum_distance(info)
        bid = float(tick.bid)
        ask = float(tick.ask)
        entry = float(position.price_open)
        leverage = self.state.entry_leverage or self.choose_leverage()
        hard_ratio = self.hard_sl_ratio(leverage)
        desired_sl = self.hard_sl_price(position)
        desired_tp = 0.0
        sl_reason = "SL"
        tp_reason = ""
        reason_parts = [f"HARD_SL_L{leverage}_RATIO_{hard_ratio:.6f}"]

        session = self.session_times(now.date())
        if session.cash_open <= now < session.close_processing:
            if now.weekday() == 3:
                desired_sl = max(desired_sl, entry * self.cfg.thursday_sl_ratio)
                sl_reason = self.weekday_sl_reason(now)
                reason_parts.append(f"THURSDAY_STOP_{self.cfg.thursday_stop:.4%}_RATIO_{self.cfg.thursday_sl_ratio:.6f}")
            elif now.weekday() == 4:
                desired_sl = max(desired_sl, entry * self.cfg.friday_sl_ratio)
                sl_reason = self.weekday_sl_reason(now)
                reason_parts.append(f"FRIDAY_STOP_{self.cfg.friday_stop:.4%}_RATIO_{self.cfg.friday_sl_ratio:.6f}")
            if self.state.break_even:
                desired_tp = entry * self.cfg.break_even_ratio
                tp_reason = "BH"
                reason_parts.append(f"BREAK_EVEN_TP_RATIO_{self.cfg.break_even_ratio:.6f}")

        if desired_sl >= bid - distance:
            self.arm_exit(position, "PROTECTION_SL_ALREADY_CROSSED", now)
            return
        if desired_tp > 0 and desired_tp <= ask + distance:
            self.arm_exit(position, "PROTECTION_TP_ALREADY_CROSSED", now)
            return

        desired_sl = floor_step(desired_sl, tick_size)
        desired_tp = ceil_step(desired_tp, tick_size) if desired_tp > 0 else 0.0
        self.modify_sltp(position, desired_sl, desired_tp, "+".join(reason_parts), sl_reason=sl_reason, tp_reason=tp_reason)

    # ----- Time-scoped Sim conditions ----------------------------------------

    def evaluate_premarket_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        if bar.local_datetime.weekday() == 3 and bar.open / entry < self.cfg.thursday_sl_ratio:
            self.arm_exit(position, "TSL1PRE", now)
        elif self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BEPRE", now)

    def evaluate_cash_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        if self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BEO", now)

    def evaluate_regular_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if self.state.exit_latched_reason:
            return
        entry = float(position.price_open)
        if self.state.break_even and bar.high > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BH", now)

    def process_completed_close(self, current_day: date, now: datetime, position) -> None:
        day_key = current_day.isoformat()
        if self.state.last_close_processed_date == day_key:
            return

        close_bar_time = self.session_times(current_day).close_bar_open.time().replace(second=0, microsecond=0)
        trade_close_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, close_bar_time)
        signal_close_bar = self.m1_bar_at(self.cfg.signal_symbol, current_day, close_bar_time)
        if trade_close_bar is None or signal_close_bar is None:
            return

        weekday = current_day.weekday()
        if self.state.prev_open > 0 and self.final_trading_day(current_day) == current_day:
            self.state.prev_full_week_change = trade_close_bar.close / self.state.prev_open - 1.0
            self.log.info("EVENT FULL_WEEK_CHANGE_UPDATED value=%.5f day=%s", self.state.prev_full_week_change, current_day)

        if position is not None and not self.state.exit_latched_reason:
            signal_reference = self.state.entry_signal_daily_open or self.state.entry_price
            if weekday == 2 and (trade_close_bar.close + 100000.0) / float(position.price_open) < self.cfg.thursday_sl_ratio:
                self.arm_exit(position, "TSL0", now)
            else:
                opened = parse_date(self.state.open_date)
                if not self.state.break_even and opened is not None and (current_day - opened).days != 0 and signal_close_bar.close < signal_reference * self.cfg.break_even_ratio:
                    self.state.break_even = True
                    self.state.save(self.cfg.state_file)
                    self.log.info("EVENT BREAK_EVEN_ARMED day=%s signal_close=%.5f threshold=%.5f", current_day, signal_close_bar.close, signal_reference * self.cfg.break_even_ratio)
                    self.emit_status("BREAK_EVEN_ARMED", position, now)

        self.state.last_trading_date = day_key
        self.state.last_close_processed_date = day_key
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT DAILY_CLOSE_PROCESSED day=%s trade_close=%.5f signal_close=%.5f", current_day, trade_close_bar.close, signal_close_bar.close)
        self.emit_status("DAILY_CLOSE_PROCESSED", position, now)

    def process_new_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if bar.utc_timestamp == self.state.last_processed_bar_utc:
            return
        self.state.last_processed_bar_utc = bar.utc_timestamp
        self.state.save(self.cfg.state_file)
        if position is None:
            return
        bar_time = bar.local_datetime.time().replace(second=0, microsecond=0)
        cash_open_time = self.session_times(bar.local_datetime.date()).cash_open.time().replace(second=0, microsecond=0)
        if self.cfg.premarket_start <= bar_time < cash_open_time:
            self.evaluate_premarket_open(position, bar, now)
        elif bar_time == cash_open_time:
            self.evaluate_cash_open(position, bar, now)

    def maybe_open_new_week(self, current_day: date, now: datetime, current_bar: Optional[M1Bar], position) -> None:
        if position is not None or self.state.exit_latched_reason or not self.is_new_week_entry(current_day):
            return
        session = self.session_times(current_day)
        latest_entry = session.cash_open + timedelta(seconds=self.cfg.entry_window_seconds)
        if now < session.open_action or now > latest_entry:
            return
        if int(datetime.now(UTC).timestamp()) < self.state.entry_pending_until_utc:
            return

        previous = parse_date(self.state.last_trading_date)
        if previous is not None:
            self.refresh_previous_full_week_change(previous)
        self.send_buy(current_day)

    def maybe_execute_open_action(self, position, now: datetime) -> bool:
        if position is None or self.state.exit_latched_reason:
            return False
        current_day = now.date()
        session = self.session_times(current_day)
        day_key = current_day.isoformat()
        if self.state.last_open_action_date == day_key or now < session.open_action:
            return False
        if now >= session.cash_open:
            self.state.last_open_action_date = day_key
            self.state.save(self.cfg.state_file)
            self.log.warning("EVENT SCHEDULED_CHECK_MISSED name=OH day=%s scheduled=%s now=%s reason=started_or_reconnected_after_open", current_day, session.open_action.isoformat(), now.isoformat())
            return False

        tick = self.require_fresh_tick(position.symbol)
        bid = float(tick.bid)
        entry = float(position.price_open)
        tpp = self.cfg.tpps[current_day.weekday()]
        threshold = entry * (1.0 + tpp)
        condition = bid > threshold
        self.log.info(
            "EVENT SCHEDULED_CHECK name=OH result=%s time=%s scheduled=%s bid=%.5f entry=%.5f tpp=%.6f threshold=%.5f",
            condition, now.isoformat(), session.open_action.isoformat(), bid, entry, tpp, threshold,
        )
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
        final_day = self.final_trading_day(current_day)
        is_final_day = final_day == current_day

        opened = parse_date(self.state.open_date) or datetime.fromtimestamp(int(position.time), UTC).astimezone(self.tz).date()
        opened_final = self.final_trading_day(opened)
        if opened_final is not None and current_day > opened_final:
            return self.close_position_market(position, "OVERDUE_TO", now)

        day_key = current_day.isoformat()
        if self.state.last_close_action_date == day_key or now < session.weekly_close:
            return False
        if now >= session.close_bar_open:
            if is_final_day:
                return self.close_position_market(position, "TO", now)
            self.state.last_close_action_date = day_key
            self.state.save(self.cfg.state_file)
            self.log.warning("EVENT SCHEDULED_CHECK_MISSED name=CH day=%s scheduled=%s now=%s", current_day, session.weekly_close.isoformat(), now.isoformat())
            return False

        signal_price = 0.0
        signal_error = ""
        try:
            signal_price = self.live_signal_price()
        except RuntimeError as exc:
            signal_error = str(exc)

        signal_reference = self.state.entry_signal_daily_open
        if signal_reference <= 0 and not signal_error:
            signal_error = "entry_signal_open_unavailable"
        tpp = self.cfg.tpps[current_day.weekday()]
        threshold = signal_reference * (1.0 + tpp) if signal_reference > 0 else 0.0
        ch = signal_price > threshold if signal_price > 0 and threshold > 0 else False
        self.log.info(
            "EVENT SCHEDULED_CHECK name=CH result=%s time=%s scheduled=%s signal_price=%.5f signal_reference=%.5f tpp=%.6f threshold=%.5f signal_error=%s",
            ch, now.isoformat(), session.weekly_close.isoformat(), signal_price, signal_reference, tpp, threshold, signal_error or "none",
        )

        if ch:
            if self.close_position_market(position, "CH", now):
                self.state.last_close_action_date = day_key
                self.state.save(self.cfg.state_file)
                return True
            return False

        self.log.info(
            "EVENT SCHEDULED_CHECK name=TO result=%s time=%s scheduled=%s final_day=%s",
            is_final_day, now.isoformat(), session.weekly_close.isoformat(), final_day,
        )
        if is_final_day:
            if self.close_position_market(position, "TO", now):
                self.state.last_close_action_date = day_key
                self.state.save(self.cfg.state_file)
                return True
            return False

        if signal_error:
            return False
        self.state.last_close_action_date = day_key
        self.state.save(self.cfg.state_file)
        return False

    def startup_reconcile(self) -> None:
        now = datetime.now(self.tz)
        self.log.info("EVENT STARTUP_RECONCILE_BEGIN build=%s script=%s time=%s", BUILD_ID, Path(__file__).resolve(), now.isoformat())
        self.log_week_plan(now.date())
        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()
        elif position is not None:
            recovered = self.recover_position_state(position, now, force=True)
            if recovered and int(getattr(position, "magic", 0)) != self.cfg.magic:
                self.log.warning("EVENT MANUAL_POSITION_ADOPTED ticket=%s magic=%s symbol=%s", position.ticket, getattr(position, "magic", 0), position.symbol)
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.emit_status("STARTUP", position, now, current_bar)
        self.log_minute_condition_report(position, now, current_bar)
        self.last_minute_status = now.strftime("%Y-%m-%d %H:%M")
        self.last_meaningful_signature = self.status_signature(position, now)

    def cycle(self) -> None:
        now = datetime.now(self.tz)
        self.log_week_plan(now.date())
        position = self.managed_position()

        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()
        elif position is not None:
            if self.recover_position_state(position, now):
                self.emit_status("POSITION_RECOVERED", position, now)

        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        if current_bar is not None and current_bar.local_datetime.date() == now.date():
            self.process_new_bar(position, current_bar, now)

        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()

        if position is not None:
            self.capture_entry_signal_open(position, now)
            if self.maybe_execute_open_action(position, now):
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
        self.log_status_if_needed(position, now, current_bar)

    def run(self) -> None:
        self.connect()
        self.startup_reconcile()
        while self.running:
            try:
                if not self.connection_healthy():
                    self.log.error("EVENT CONNECTION_LOST reconnecting=true")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.connect()
                    self.startup_reconcile()
                self.cycle()
            except KeyboardInterrupt:
                self.running = False
            except Exception:
                self.log.exception("EVENT STRATEGY_CYCLE_FAILED")
            time_module.sleep(self.cfg.poll_seconds)
        self.log.info("EVENT STRATEGY_STOPPED")

    def stop(self, *_args: Any) -> None:
        self.running = False


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------


def main() -> int:
    cfg = Config()
    lock = SingleInstanceLock(cfg.lock_file)
    strategy = OPPWContinuousStrategy(cfg)
    try:
        lock.acquire()
        signal.signal(signal.SIGINT, strategy.stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, strategy.stop)
        strategy.run()
        return 0
    except Exception:
        strategy.log.exception("EVENT FATAL_STARTUP_FAILURE")
        return 1
    finally:
        strategy.disconnect()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
