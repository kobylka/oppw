"""
Continuous MetaTrader 5 implementation of the OPPW Sim.process() trading logic.

Execution model
---------------
* Python sends a BUY only for a valid new-week entry.
* Python never sends a SELL or PositionClose request.
* All exits are implemented by changing the existing long position's SL/TP.
* SL/TP is changed only when the required protection differs from the current one.
* A condition requiring an immediate exit installs the closest broker-valid SL/TP
  bracket and latches the reason until the position disappears.

The default strategy clock is Europe/Warsaw:
* premarket minute-open checks: 00:00 <= time < 15:30
* cash-open checks / weekly entry: 15:30
* regular-session checks: 15:30 through the 22:00 M1 bar
* close-based checks: after the 22:00 M1 bar has completed (normally 22:01)

IMPORTANT: live trading is disabled unless OPPW_LIVE=1 is set.
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
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata") from exc


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None or not value.strip() else int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return default if value is None or not value.strip() else float(value)


@dataclass(frozen=True)
class Config:
    trade_symbol: str = os.getenv("OPPW_TRADE_SYMBOL", "US100")
    signal_symbol: str = os.getenv("OPPW_SIGNAL_SYMBOL", os.getenv("OPPW_TRADE_SYMBOL", "US100"))
    timezone_name: str = os.getenv("OPPW_TIMEZONE", "Europe/Warsaw")

    terminal_path: str = os.getenv("OPPW_TERMINAL_PATH", "C:\\Program Files\\MetaTrader 5\\terminal64.exe")
    login: int = env_int("OPPW_LOGIN", REMOVED_DEMO_ACCOUNT_ID)
    password: str = os.getenv("OPPW_PASSWORD", "REMOVED_ROTATED_MT5_PASSWORD")
    server: str = os.getenv("OPPW_SERVER", "BOSSAFX-Demo")

    magic: int = env_int("OPPW_MAGIC", 240024)
    comment_prefix: str = os.getenv("OPPW_COMMENT", "OPPW24")
    deviation_points: int = env_int("OPPW_DEVIATION", 20)
    poll_seconds: float = env_float("OPPW_POLL_SECONDS", 0.20)
    entry_window_seconds: int = env_int("OPPW_ENTRY_WINDOW_SECONDS", 55)
    reconnect_seconds: float = env_float("OPPW_RECONNECT_SECONDS", 3.0)
    maximum_tick_age_seconds: float = env_float("OPPW_MAX_TICK_AGE_SECONDS", 10.0)

    base_leverage: int = env_int("OPPW_BASE_LEVERAGE", 8)
    loss_leverage: int = env_int("OPPW_LOSS_LEVERAGE", 10)
    break_even_ratio: float = env_float("OPPW_BE", 0.996)
    thursday_stop: float = env_float("OPPW_THURSDAY_STOP", 0.004)
    friday_stop: float = env_float("OPPW_FRIDAY_STOP", 0.015)
    leverage_stop_points: float = env_float("OPPW_LEVERAGE_STOP_POINTS", 50.0)

    # Latest Sim values: Monday 0.7%, Tuesday 2%, Wed/Thu/Fri 5%.
    tpp_monday: float = env_float("OPPW_TPP_MONDAY", 0.007)
    tpp_tuesday: float = env_float("OPPW_TPP_TUESDAY", 0.020)
    tpp_wednesday: float = env_float("OPPW_TPP_WEDNESDAY", 0.050)
    tpp_thursday: float = env_float("OPPW_TPP_THURSDAY", 0.050)
    tpp_friday: float = env_float("OPPW_TPP_FRIDAY", 0.050)

    # Exact Sim sizing constants used by sell():
    # floor(balance / (20/leverage) / 2240) * 2240 * 20 notional.
    sizing_quantum: float = env_float("OPPW_SIZING_QUANTUM", 2240.0)
    sizing_multiplier: float = env_float("OPPW_SIZING_MULTIPLIER", 20.0)
    margin_reserve_ratio: float = env_float("OPPW_MARGIN_RESERVE", 0.05)

    manage_manual_position: bool = env_bool("OPPW_MANAGE_MANUAL_POSITION", True)
    live_enabled: bool = env_bool("OPPW_LIVE", True)

    state_file: Path = Path(os.getenv("OPPW_STATE_FILE", "oppw_mt5_state.json"))
    log_file: Path = Path(os.getenv("OPPW_LOG_FILE", "oppw_mt5.log"))
    lock_file: Path = Path(os.getenv("OPPW_LOCK_FILE", "oppw_mt5.lock"))

    premarket_start: time = time(0, 0)
    cash_open: time = time(15, 30)
    close_bar_open: time = time(22, 0)
    close_processing: time = time(22, 1)

    @property
    def tpps(self) -> tuple[float, float, float, float, float]:
        return (
            self.tpp_monday,
            self.tpp_tuesday,
            self.tpp_wednesday,
            self.tpp_thursday,
            self.tpp_friday,
        )

    @property
    def thursday_sl_ratio(self) -> float:
        return 1.0 - self.thursday_stop

    @property
    def friday_sl_ratio(self) -> float:
        return 1.0 - self.friday_stop


# -----------------------------------------------------------------------------
# Persistent strategy state
# -----------------------------------------------------------------------------


@dataclass
class StrategyState:
    version: int = 1

    last_trading_date: str = ""
    last_close_processed_date: str = ""
    last_processed_bar_utc: int = 0
    last_entry_week: str = ""
    entry_pending_until_utc: int = 0

    active_position_identifier: int = 0
    active_position_ticket: int = 0
    open_date: str = ""
    entry_price: float = 0.0
    entry_signal_daily_open: float = 0.0
    entry_leverage: int = 0

    break_even: bool = False
    exit_latched_reason: str = ""
    exit_latched_at: str = ""

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
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            allowed = {field.name for field in fields(cls)}
            return cls(**{key: value for key, value in raw.items() if key in allowed})
        except Exception as exc:
            raise RuntimeError(f"Cannot load strategy state from {path}: {exc}") from exc

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


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------


def setup_logging(path: Path) -> logging.Logger:
    logger = logging.getLogger("oppw_mt5")
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    path.parent.mkdir(parents=True, exist_ok=True)
    rotating = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=5, encoding="utf-8")
    rotating.setFormatter(formatter)
    logger.addHandler(rotating)
    return logger


def truncate_four_decimals(value: float) -> float:
    return math.trunc(value * 10_000.0) / 10_000.0


def iso_week_key(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year:04d}-W{iso.week:02d}"


def parse_date(value: str) -> Optional[date]:
    return date.fromisoformat(value) if value else None


def floor_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.floor((value + 1e-12) / step) * step


def ceil_step(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.ceil((value - 1e-12) / step) * step


def price_changed(current: float, desired: float, tolerance: float) -> bool:
    if current == 0.0 and desired == 0.0:
        return False
    return abs(current - desired) >= tolerance


class SingleInstanceLock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise RuntimeError(f"Another strategy instance may be running: {self.path}") from exc
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
        self.state = StrategyState.load(config.state_file)
        self.log = setup_logging(config.log_file)
        self.running = True
        self.connected = False

    # ----- MT5 connection -----------------------------------------------------

    def connect(self) -> None:
        kwargs: dict[str, Any] = {}
        if self.cfg.login:
            kwargs["login"] = self.cfg.login
        if self.cfg.password:
            kwargs["password"] = self.cfg.password
        if self.cfg.server:
            kwargs["server"] = self.cfg.server

        if self.cfg.terminal_path:
            ok = mt5.initialize(self.cfg.terminal_path, **kwargs)
        else:
            ok = mt5.initialize(**kwargs)

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
        self.log.info(
            "Connected: account=%s server=%s trade=%s signal=%s live=%s",
            getattr(account, "login", "?"),
            getattr(account, "server", "?"),
            self.cfg.trade_symbol,
            self.cfg.signal_symbol,
            self.cfg.live_enabled,
        )
        if not self.cfg.live_enabled:
            self.log.warning("DRY RUN: set OPPW_LIVE=1 to permit BUY and SL/TP modification requests")

    def disconnect(self) -> None:
        if self.connected:
            mt5.shutdown()
            self.connected = False

    def connection_healthy(self) -> bool:
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        return terminal is not None and account is not None and bool(getattr(terminal, "connected", True))

    # ----- Market data --------------------------------------------------------

    def latest_tick(self, symbol: str):
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            raise RuntimeError(f"symbol_info_tick({symbol}) failed: {mt5.last_error()}")
        return tick

    def tick_local_datetime(self, symbol: str) -> datetime:
        tick = self.latest_tick(symbol)
        timestamp = getattr(tick, "time_msc", 0) / 1000.0 if getattr(tick, "time_msc", 0) else tick.time
        return datetime.fromtimestamp(timestamp, UTC).astimezone(self.tz)

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
        utc_ts = int(row["time"])
        local_dt = datetime.fromtimestamp(utc_ts, UTC).astimezone(self.tz)
        return M1Bar(utc_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

    def m1_bar_at(self, symbol: str, local_day: date, local_time: time) -> Optional[M1Bar]:
        local_start = datetime.combine(local_day, local_time, self.tz)
        utc_start = local_start.astimezone(UTC)
        utc_end = utc_start + timedelta(seconds=59)
        rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_M1, utc_start, utc_end)
        if rates is None or len(rates) == 0:
            return None
        row = min(rates, key=lambda item: abs(int(item["time"]) - int(utc_start.timestamp())))
        utc_ts = int(row["time"])
        local_dt = datetime.fromtimestamp(utc_ts, UTC).astimezone(self.tz)
        if local_dt.date() != local_day or local_dt.hour != local_time.hour or local_dt.minute != local_time.minute:
            return None
        return M1Bar(utc_ts, local_dt, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))

    def signal_cash_open(self, symbol: str, local_day: date) -> Optional[float]:
        # quotes[0] in Sim is the daily signal open. For QQQ/US cash data this
        # is the 15:30 Warsaw cash-session open, not the 00:00 CFD premarket open.
        bar = self.m1_bar_at(symbol, local_day, self.cfg.cash_open)
        return None if bar is None else bar.open

    def previous_trading_date(self, current_day: date) -> Optional[date]:
        start_local = datetime.combine(current_day - timedelta(days=10), time(0, 0), self.tz)
        end_local = datetime.combine(current_day, time(0, 0), self.tz) - timedelta(seconds=1)
        rates = mt5.copy_rates_range(
            self.cfg.signal_symbol,
            mt5.TIMEFRAME_M1,
            start_local.astimezone(UTC),
            end_local.astimezone(UTC),
        )
        if rates is None or len(rates) == 0:
            return None
        days = {
            datetime.fromtimestamp(int(row["time"]), UTC).astimezone(self.tz).date()
            for row in rates
            if datetime.fromtimestamp(int(row["time"]), UTC).astimezone(self.tz).date() < current_day
        }
        return max(days) if days else None

    # ----- Position/history reconciliation -----------------------------------

    def managed_position(self):
        positions = mt5.positions_get(symbol=self.cfg.trade_symbol)
        if positions is None:
            raise RuntimeError(f"positions_get failed: {mt5.last_error()}")

        selected = []
        for position in positions:
            is_long = position.type == mt5.POSITION_TYPE_BUY
            magic_matches = int(getattr(position, "magic", 0)) == self.cfg.magic
            if is_long and (magic_matches or self.cfg.manage_manual_position):
                selected.append(position)

        if len(selected) > 1:
            raise RuntimeError(f"Expected at most one managed long position, found {len(selected)}")
        return selected[0] if selected else None

    @staticmethod
    def position_identifier(position) -> int:
        return int(getattr(position, "identifier", 0) or position.ticket)

    def recover_position_state(self, position) -> None:
        identifier = self.position_identifier(position)
        if self.state.active_position_identifier == identifier and self.state.entry_price > 0:
            return

        opened = datetime.fromtimestamp(int(position.time), UTC).astimezone(self.tz)
        leverage = self.parse_leverage_from_comment(getattr(position, "comment", "")) or self.choose_leverage()
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, opened.date())
        if signal_open is None:
            signal_open = float(position.price_open)
            self.log.warning("Could not recover entry-day signal open; using position entry price")

        self.state.active_position_identifier = identifier
        self.state.active_position_ticket = int(position.ticket)
        self.state.open_date = opened.date().isoformat()
        self.state.entry_price = float(position.price_open)
        self.state.entry_signal_daily_open = signal_open
        self.state.entry_leverage = leverage
        self.state.prev_open = float(position.price_open)
        self.state.last_entry_week = iso_week_key(opened.date())
        self.state.entry_pending_until_utc = 0
        self.state.save(self.cfg.state_file)
        self.log.info(
            "Recovered position ticket=%s identifier=%s open=%s leverage=%s",
            position.ticket,
            identifier,
            position.price_open,
            leverage,
        )

    def finalize_closed_position(self) -> None:
        identifier = self.state.active_position_identifier
        if not identifier:
            return

        deals = mt5.history_deals_get(position=identifier)
        exit_deal = None
        if deals:
            out_values = {
                getattr(mt5, "DEAL_ENTRY_OUT", 1),
                getattr(mt5, "DEAL_ENTRY_OUT_BY", 3),
            }
            candidates = [deal for deal in deals if int(getattr(deal, "entry", -1)) in out_values]
            if candidates:
                exit_deal = max(candidates, key=lambda deal: int(getattr(deal, "time_msc", 0) or deal.time * 1000))

        if exit_deal is not None and self.state.entry_price > 0:
            exit_price = float(exit_deal.price)
            change = truncate_four_decimals(exit_price / self.state.entry_price - 1.0)
            self.state.prev_change = change
            self.state.last_exit_price = exit_price
            exit_timestamp = getattr(exit_deal, "time_msc", 0) / 1000.0 if getattr(exit_deal, "time_msc", 0) else exit_deal.time
            self.state.last_exit_time = datetime.fromtimestamp(exit_timestamp, UTC).astimezone(self.tz).isoformat()
            self.log.info(
                "Position closed by broker: reason=%s entry=%.5f exit=%.5f change=%.4f",
                self.state.exit_latched_reason or "broker/manual",
                self.state.entry_price,
                exit_price,
                change,
            )
        else:
            self.log.warning("Managed position disappeared, but closing deal could not be resolved for identifier=%s", identifier)

        self.state.last_exit_reason = self.state.exit_latched_reason or "broker/manual"
        self.state.active_position_identifier = 0
        self.state.active_position_ticket = 0
        self.state.open_date = ""
        self.state.entry_price = 0.0
        self.state.entry_signal_daily_open = 0.0
        self.state.entry_leverage = 0
        self.state.break_even = False
        self.state.exit_latched_reason = ""
        self.state.exit_latched_at = ""
        self.state.entry_pending_until_utc = 0
        self.state.save(self.cfg.state_file)

    @staticmethod
    def parse_leverage_from_comment(comment: str) -> int:
        marker = " L"
        if marker not in comment:
            return 0
        try:
            return int(comment.rsplit(marker, 1)[1].split()[0])
        except (ValueError, IndexError):
            return 0

    # ----- Strategy calculations ---------------------------------------------

    def choose_leverage(self) -> int:
        if self.cfg.base_leverage == 8 and (
            self.state.prev_full_week_change < -0.025 or self.state.prev_change < -0.007
        ):
            return self.cfg.loss_leverage
        return self.cfg.base_leverage

    def hard_sl_ratio(self, leverage: int) -> float:
        return (100.0 - self.cfg.leverage_stop_points / leverage) / 100.0

    def hard_sl_price(self, position) -> float:
        leverage = self.state.entry_leverage or self.choose_leverage()
        return float(position.price_open) * self.hard_sl_ratio(leverage)

    def is_new_week_entry(self, current_day: date) -> bool:
        if current_day.weekday() not in (0, 1):
            return False
        if self.state.last_entry_week == iso_week_key(current_day):
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
        close_bar = self.m1_bar_at(self.cfg.trade_symbol, previous_day, self.cfg.close_bar_open)
        if close_bar is None:
            self.log.warning("Cannot refresh previous full-week change: no %s 22:00 bar", previous_day)
            return
        self.state.prev_full_week_change = close_bar.close / self.state.prev_open - 1.0
        self.state.save(self.cfg.state_file)
        self.log.info("Previous full-week change refreshed: %.5f", self.state.prev_full_week_change)

    # ----- Sizing and order requests -----------------------------------------

    def target_notional(self, balance: float, leverage: int) -> float:
        divisor = self.cfg.sizing_multiplier / leverage
        units = math.floor(balance / divisor / self.cfg.sizing_quantum)
        return units * self.cfg.sizing_quantum * self.cfg.sizing_multiplier

    def normalized_volume(self, target_notional: float, ask: float) -> float:
        info = mt5.symbol_info(self.cfg.trade_symbol)
        account = mt5.account_info()
        if info is None or account is None:
            raise RuntimeError(f"Cannot obtain symbol/account information: {mt5.last_error()}")

        one_percent_price = ask * 1.01
        profit_per_lot = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, 1.0, ask, one_percent_price)
        if profit_per_lot is None or abs(profit_per_lot) <= 0:
            raise RuntimeError(f"order_calc_profit failed: {mt5.last_error()}")

        volume = target_notional * 0.01 / abs(profit_per_lot)

        margin_per_lot = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, 1.0, ask)
        if margin_per_lot is not None and margin_per_lot > 0:
            maximum_by_margin = account.margin_free * (1.0 - self.cfg.margin_reserve_ratio) / margin_per_lot
            volume = min(volume, maximum_by_margin)

        step = float(info.volume_step)
        volume = floor_step(volume, step)
        volume = min(volume, float(info.volume_max))
        if volume < float(info.volume_min):
            return 0.0
        return round(volume, 8)

    def order_filling_mode(self, info) -> int:
        configured = os.getenv("OPPW_FILLING_MODE", "AUTO").strip().upper()
        mapping = {
            "FOK": mt5.ORDER_FILLING_FOK,
            "IOC": mt5.ORDER_FILLING_IOC,
            "RETURN": mt5.ORDER_FILLING_RETURN,
        }
        if configured in mapping:
            return mapping[configured]

        symbol_mode = int(getattr(info, "filling_mode", mt5.ORDER_FILLING_IOC))
        if symbol_mode in mapping.values():
            return symbol_mode
        return mt5.ORDER_FILLING_IOC

    def send_buy(self, current_day: date, cash_open_price: float) -> bool:
        account = mt5.account_info()
        info = mt5.symbol_info(self.cfg.trade_symbol)
        tick = self.require_fresh_tick(self.cfg.trade_symbol)
        if account is None or info is None:
            raise RuntimeError(f"Cannot obtain account/symbol data: {mt5.last_error()}")

        leverage = self.choose_leverage()
        target_notional = self.target_notional(float(account.balance), leverage)
        if target_notional <= 0:
            self.log.error("Sizing produced zero notional; live strategy cannot perform the Sim's artificial deposit top-up")
            return False

        ask = float(tick.ask)
        volume = self.normalized_volume(target_notional, ask)
        if volume <= 0:
            self.log.error("Calculated volume is below broker minimum")
            return False

        info_tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        sl = floor_step(ask * self.hard_sl_ratio(leverage), info_tick_size)
        comment = f"{self.cfg.comment_prefix} L{leverage}"[:31]
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.cfg.trade_symbol,
            "volume": volume,
            "type": mt5.ORDER_TYPE_BUY,
            "price": ask,
            "sl": sl,
            "tp": 0.0,
            "deviation": self.cfg.deviation_points,
            "magic": self.cfg.magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self.order_filling_mode(info),
        }

        self.log.info(
            "BUY requested: day=%s leverage=%s volume=%s target_notional=%.2f ask=%.5f sl=%.5f",
            current_day,
            leverage,
            volume,
            target_notional,
            ask,
            sl,
        )
        if not self.cfg.live_enabled:
            return False

        check = mt5.order_check(request)
        if check is None:
            self.log.error("order_check returned None: %s", mt5.last_error())
            return False
        if int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            self.log.error("order_check rejected BUY: retcode=%s comment=%s", check.retcode, check.comment)
            return False

        result = mt5.order_send(request)
        if result is None:
            self.log.error("BUY order_send returned None: %s", mt5.last_error())
            return False

        accepted = {
            getattr(mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(mt5, "TRADE_RETCODE_PLACED", 10008),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010),
        }
        if int(result.retcode) not in accepted:
            self.log.error("BUY rejected: retcode=%s comment=%s", result.retcode, result.comment)
            return False

        self.state.entry_pending_until_utc = int(datetime.now(UTC).timestamp()) + 10
        self.state.open_date = current_day.isoformat()
        self.state.entry_price = cash_open_price
        self.state.entry_leverage = leverage
        self.state.prev_open = cash_open_price
        self.state.last_entry_week = iso_week_key(current_day)
        signal_open = self.signal_cash_open(self.cfg.signal_symbol, current_day)
        self.state.entry_signal_daily_open = signal_open or cash_open_price
        self.state.break_even = False
        self.state.exit_latched_reason = ""
        self.state.exit_latched_at = ""
        self.state.save(self.cfg.state_file)
        return True

    def modify_sltp(self, position, desired_sl: float, desired_tp: float, reason: str) -> bool:
        info = mt5.symbol_info(position.symbol)
        if info is None:
            raise RuntimeError(f"symbol_info({position.symbol}) failed: {mt5.last_error()}")

        tick_size = float(getattr(info, "trade_tick_size", 0.0) or info.point)
        digits = int(info.digits)
        desired_sl = round(desired_sl, digits) if desired_sl else 0.0
        desired_tp = round(desired_tp, digits) if desired_tp else 0.0
        tolerance = max(tick_size * 0.5, float(info.point) * 0.5)

        if not price_changed(float(position.sl), desired_sl, tolerance) and not price_changed(float(position.tp), desired_tp, tolerance):
            return True

        self.log.info(
            "SL/TP modify: reason=%s ticket=%s SL %.5f->%.5f TP %.5f->%.5f",
            reason,
            position.ticket,
            float(position.sl),
            desired_sl,
            float(position.tp),
            desired_tp,
        )
        if not self.cfg.live_enabled:
            return False

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": int(position.ticket),
            "sl": desired_sl,
            "tp": desired_tp,
            "magic": self.cfg.magic,
            "comment": reason[:31],
        }
        result = mt5.order_send(request)
        if result is None:
            self.log.error("SL/TP order_send returned None: %s", mt5.last_error())
            return False

        accepted = {
            getattr(mt5, "TRADE_RETCODE_DONE", 10009),
            getattr(mt5, "TRADE_RETCODE_NO_CHANGES", 10025),
        }
        if int(result.retcode) not in accepted:
            self.log.error("SL/TP rejected: retcode=%s comment=%s", result.retcode, result.comment)
            return False
        return True

    # ----- Protection and exit latching --------------------------------------

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
            self.log.warning("Exit condition latched: %s", reason)
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

        # Never weaken a valid, closer long SL or replace a closer valid TP.
        if float(position.sl) > 0 and float(position.sl) < bid and float(position.sl) > sl:
            sl = float(position.sl)
        if float(position.tp) > ask and float(position.tp) < tp:
            tp = float(position.tp)

        self.modify_sltp(position, sl, tp, f"EXIT {reason}")

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
        hard_sl = self.hard_sl_price(position)
        desired_sl = hard_sl
        desired_tp = 0.0

        in_regular = self.cfg.cash_open <= now.time() < self.cfg.close_processing
        if in_regular:
            if now.weekday() == 3:
                desired_sl = max(desired_sl, entry * self.cfg.thursday_sl_ratio)
            elif now.weekday() == 4:
                desired_sl = max(desired_sl, entry * self.cfg.friday_sl_ratio)
            if self.state.break_even:
                desired_tp = entry * self.cfg.break_even_ratio

        max_valid_sl = bid - distance
        min_valid_tp = ask + distance

        if desired_sl >= max_valid_sl:
            self.arm_exit(position, "PROTECTION_SL_ALREADY_CROSSED", now)
            return
        if desired_tp > 0 and desired_tp <= min_valid_tp:
            self.arm_exit(position, "PROTECTION_TP_ALREADY_CROSSED", now)
            return

        desired_sl = floor_step(desired_sl, tick_size)
        desired_tp = ceil_step(desired_tp, tick_size) if desired_tp > 0 else 0.0
        self.modify_sltp(position, desired_sl, desired_tp, "STANDARD")

    # ----- Time-scoped Sim conditions ----------------------------------------

    def evaluate_premarket_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)

        # Exact Sim priority: hard SL first, then Thursday premarket, then BEPRE.
        if bar.open < hard_sl:
            reason = "GAP DOWN" if bar.local_datetime.time() == self.cfg.premarket_start else "SLPRE"
            self.arm_exit(position, reason, now)
        elif bar.local_datetime.weekday() == 3 and bar.open / entry < self.cfg.thursday_sl_ratio:
            self.arm_exit(position, "TSL1PRE", now)
        elif self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BEPRE", now)

    def evaluate_cash_open(self, position, bar: M1Bar, now: datetime) -> None:
        current_day = bar.local_datetime.date()
        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)
        tpp = self.cfg.tpps[current_day.weekday()]

        # Sim closes a stale carried position before processing the new week's entry.
        if self.is_new_week_entry(current_day):
            self.arm_exit(position, "ROLLOVER_TO", now)
            return

        # Exact Sim cash-open priority.
        if bar.open < hard_sl:
            self.arm_exit(position, "SLO", now)
        elif bar.open > entry * (1.0 + tpp):
            self.arm_exit(position, "OH", now)
        elif self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BEO", now)
        elif current_day.weekday() == 3 and bar.open / entry < self.cfg.thursday_sl_ratio:
            self.arm_exit(position, "TSL1", now)
        elif current_day.weekday() == 4 and bar.open / entry < self.cfg.friday_sl_ratio:
            self.arm_exit(position, "TSL3", now)

    def evaluate_regular_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if self.state.exit_latched_reason:
            return
        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)
        weekday = bar.local_datetime.weekday()

        # Exact Sim regular-session priority. Broker-side orders should normally
        # trigger first; these checks are a fallback if a protection update failed.
        if bar.open < hard_sl or bar.low < hard_sl:
            self.arm_exit(position, "SL", now)
        elif weekday == 3 and bar.low / entry < self.cfg.thursday_sl_ratio:
            self.arm_exit(position, "TSL2", now)
        elif weekday == 4 and bar.low / entry < self.cfg.friday_sl_ratio:
            self.arm_exit(position, "TSL4", now)
        elif self.state.break_even and bar.high > entry * self.cfg.break_even_ratio:
            self.arm_exit(position, "BH", now)

    def process_completed_close(self, current_day: date, now: datetime, position) -> None:
        day_key = current_day.isoformat()
        if self.state.last_close_processed_date == day_key:
            return

        trade_close_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, self.cfg.close_bar_open)
        signal_close_bar = self.m1_bar_at(self.cfg.signal_symbol, current_day, self.cfg.close_bar_open)
        if trade_close_bar is None or signal_close_bar is None:
            return

        weekday = current_day.weekday()
        if self.state.prev_open > 0 and weekday == 4:
            self.state.prev_full_week_change = trade_close_bar.close / self.state.prev_open - 1.0

        if position is not None and not self.state.exit_latched_reason:
            tpp = self.cfg.tpps[weekday]
            signal_reference = self.state.entry_signal_daily_open or self.state.entry_price

            if signal_close_bar.close > signal_reference * (1.0 + tpp):
                self.arm_exit(position, "CH", now)
            # Preserved literally from the latest Sim. With +100000 this branch is
            # effectively disabled for normal positive index prices.
            elif weekday == 2 and (trade_close_bar.close + 100000.0) / float(position.price_open) < self.cfg.thursday_sl_ratio:
                self.arm_exit(position, "TSL0", now)
            elif weekday == 4:
                self.arm_exit(position, "TO", now)
            else:
                opened = parse_date(self.state.open_date)
                if (
                    not self.state.break_even
                    and opened is not None
                    and (current_day - opened).days != 0
                    and signal_close_bar.close < signal_reference * self.cfg.break_even_ratio
                ):
                    self.state.break_even = True
                    self.log.info("Break-even state armed after close on %s", current_day)

        self.state.last_trading_date = day_key
        self.state.last_close_processed_date = day_key
        self.state.save(self.cfg.state_file)

    # ----- Main event loop ----------------------------------------------------

    def process_new_bar(self, position, bar: M1Bar, now: datetime) -> None:
        if bar.utc_timestamp == self.state.last_processed_bar_utc:
            return
        self.state.last_processed_bar_utc = bar.utc_timestamp
        self.state.save(self.cfg.state_file)

        bar_time = bar.local_datetime.time().replace(second=0, microsecond=0)
        if position is None:
            return

        if self.cfg.premarket_start <= bar_time < self.cfg.cash_open:
            self.evaluate_premarket_open(position, bar, now)
        elif bar_time == self.cfg.cash_open:
            self.evaluate_cash_open(position, bar, now)

    def maybe_open_new_week(self, current_day: date, now: datetime, current_bar: Optional[M1Bar], position) -> None:
        if position is not None or self.state.exit_latched_reason:
            return
        if not self.is_new_week_entry(current_day):
            return

        open_dt = datetime.combine(current_day, self.cfg.cash_open, self.tz)
        seconds_after_open = (now - open_dt).total_seconds()
        if seconds_after_open < 0 or seconds_after_open > self.cfg.entry_window_seconds:
            return
        if int(datetime.now(UTC).timestamp()) < self.state.entry_pending_until_utc:
            return

        cash_bar = current_bar
        if cash_bar is None or cash_bar.local_datetime.date() != current_day or cash_bar.local_datetime.time().replace(second=0, microsecond=0) != self.cfg.cash_open:
            cash_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, self.cfg.cash_open)
        if cash_bar is None:
            return

        previous = parse_date(self.state.last_trading_date)
        if previous is not None:
            self.refresh_previous_full_week_change(previous)
        self.send_buy(current_day, cash_bar.open)

    def cycle(self) -> None:
        now = datetime.now(self.tz)
        position = self.managed_position()

        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()
        elif position is not None:
            self.recover_position_state(position)

        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        if current_bar is not None:
            # Ignore stale bars from a prior market day when the terminal is open on a weekend.
            if current_bar.local_datetime.date() == now.date():
                self.process_new_bar(position, current_bar, now)

        # The current position may have changed due to a just-triggered broker SL/TP.
        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()

        if position is not None:
            if self.cfg.cash_open <= now.time() < self.cfg.close_processing and current_bar is not None and current_bar.local_datetime.date() == now.date():
                self.evaluate_regular_bar(position, current_bar, now)
            if now.time() >= self.cfg.close_processing:
                self.process_completed_close(now.date(), now, position)
            self.apply_standard_protection(position, now)
        else:
            if now.time() >= self.cfg.close_processing:
                self.process_completed_close(now.date(), now, None)
            self.maybe_open_new_week(now.date(), now, current_bar, None)

    def run(self) -> None:
        self.connect()
        while self.running:
            try:
                if not self.connection_healthy():
                    self.log.error("MT5 connection lost; reconnecting")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.connect()
                self.cycle()
            except KeyboardInterrupt:
                self.running = False
            except Exception:
                self.log.exception("Strategy cycle failed")
            time_module.sleep(self.cfg.poll_seconds)

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
    finally:
        strategy.disconnect()
        lock.release()


if __name__ == "__main__":
    sys.exit(main())
