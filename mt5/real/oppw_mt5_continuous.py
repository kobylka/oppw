"""
Continuous MetaTrader 5 implementation of the OPPW strategy.

Key execution rules
-------------------
* BUY is sent at XNYS cash open minus three seconds for a valid new-week entry.
* OH is evaluated exactly once at cash open minus three seconds and is no longer reported after that check.
* CH and final-week TO are evaluated at XNYS session close minus three seconds.
* Hard SL and weekday SL levels are maintained with TRADE_ACTION_SLTP.
* One configurable TSL is active continuously from Thursday date change through Friday and the weekend if needed.
* TSL is a broker-side SL label; candle lows do not latch it.
* Closing reasons are resolved from the MT5 closing deal and active protection state.
* Status deposit is read directly from MT5 as float(account.margin).
* Terminal/account AutoTrading permissions are verified continuously before every live trade request.
* EXECUTOR mode is the only role permitted to submit or modify trades.
* PUBLISHER mode is read-only and owns backend publishing while active.
* EXECUTOR automatically publishes when no PUBLISHER heartbeat is active.
* Flat status publishes an institutional-style pre-trade what-if ticket and a structured strategy decision record.
* Every completed trade is assigned a Guy Fleury A/B/C/D class and the publisher includes the label.

Run with `--mode executor|publisher` and `--account demo|real`. DEMO loads
oppw-mt5-config.py and REAL loads real-mt5-config.py. Live trading is disabled
unless LIVE_ENABLED=True in the selected account configuration or OPPW_LIVE=1 is set.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import math
import os
import signal
import shlex
import shutil
import sys
import threading
import time as time_module
import urllib.error
import urllib.request
import uuid
from collections import deque
from dataclasses import asdict, dataclass, fields, is_dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

BASE_DIR = Path(__file__).resolve().parent
BUILD_ID = "2026-07-19-what-if-decision-trade-class-v43"
SCHEDULED_ACTION_LEAD_SECONDS = 3.0
AUTOTRADING_REMINDER_SECONDS = 60.0
STALE_TICK_REMINDER_SECONDS = 60.0
PUBLISHER_HEARTBEAT_INTERVAL_SECONDS = 1.0
PUBLISHER_HEARTBEAT_STALE_SECONDS = 8.0
INSTANCE_MODE_EXECUTOR = "EXECUTOR"
INSTANCE_MODE_PUBLISHER = "PUBLISHER"
ACCOUNT_DEMO = "DEMO"
ACCOUNT_REAL = "REAL"
ACCOUNT_CONFIG_FILES = {ACCOUNT_DEMO: "oppw-mt5-config.py", ACCOUNT_REAL: "real-mt5-config.py"}
ACCOUNT_CONFIG_FALLBACKS = {ACCOUNT_DEMO: ("oppw_mt5_config.py",), ACCOUNT_REAL: ("real_mt5_config.py",)}

try:
    import exchange_calendars as xcals
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc

try:
    import MetaTrader5 as mt5
except ImportError as exc:
    raise SystemExit("Install dependencies with: py -m pip install MetaTrader5 tzdata exchange-calendars") from exc

# -----------------------------------------------------------------------------
# Account configuration loading
# -----------------------------------------------------------------------------


def load_account_config(account: str):
    account = account.upper()
    primary = BASE_DIR / ACCOUNT_CONFIG_FILES[account]
    candidates = (primary, *(BASE_DIR / name for name in ACCOUNT_CONFIG_FALLBACKS[account]))
    config_path = next((path for path in candidates if path.exists()), None)
    if config_path is None:
        names = ", ".join(path.name for path in candidates)
        raise RuntimeError(f"Missing {account} configuration. Expected one of: {names}")

    module_name = f"oppw_mt5_config_{account.lower()}_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, config_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load configuration file: {config_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    config_class = getattr(module, "Config", None)
    if config_class is None or not callable(config_class):
        raise RuntimeError(f"Configuration file does not define Config: {config_path}")
    return config_class(), config_path


def account_scoped_file(path: Path, account: str) -> Path:
    account_label = account.lower()
    normalized_tokens = path.stem.lower().replace("_", "-").replace(".", "-").split("-")
    if account_label in normalized_tokens:
        return path
    return path.with_name(f"{path.stem}.{account_label}{path.suffix}")


def account_scoped_dir(path: Path, account: str) -> Path:
    return path if path.name.lower() == account.lower() else path / account.lower()


def scope_config_to_account(config, account: str):
    changes: dict[str, Any] = {}
    if hasattr(config, "state_file"):
        changes["state_file"] = account_scoped_file(Path(config.state_file), account)
    if hasattr(config, "lock_file"):
        changes["lock_file"] = account_scoped_file(Path(config.lock_file), account)
    if hasattr(config, "monitor_history_file"):
        changes["monitor_history_file"] = account_scoped_file(Path(config.monitor_history_file), account)
    if hasattr(config, "log_dir"):
        changes["log_dir"] = account_scoped_dir(Path(config.log_dir), account)
    if hasattr(config, "monitor_account_key"):
        changes["monitor_account_key"] = account.upper()
    if not changes:
        return config
    if not is_dataclass(config):
        raise RuntimeError("Config must be a dataclass so account-specific runtime paths can be isolated safely")
    return replace(config, **changes)


def migrate_legacy_demo_runtime_files(original, scoped, account: str) -> None:
    if account != ACCOUNT_DEMO:
        return
    for name in ("state_file", "monitor_history_file"):
        if not hasattr(original, name) or not hasattr(scoped, name):
            continue
        source = Path(getattr(original, name))
        target = Path(getattr(scoped, name))
        if source == target or not source.exists() or target.exists():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


# -----------------------------------------------------------------------------
# Persistent state
# -----------------------------------------------------------------------------


@dataclass
class StrategyState:
    version: int = 5

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
    last_exit_trade_class: str = ""
    last_exit_preleverage_return: float = 0.0
    last_exit_position_identifier: int = 0

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
        os.replace(temporary, path)


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


class StaleTickError(RuntimeError):
    def __init__(self, symbol: str, age_seconds: float):
        self.symbol = symbol
        self.age_seconds = age_seconds
        super().__init__(f"Stale tick for {symbol}: age={age_seconds:.1f}s")


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
    def __init__(self, log_dir: Path, timezone: ZoneInfo, role: str):
        super().__init__(logging.INFO)
        self.log_dir = log_dir
        self.timezone = timezone
        self.role = role
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            current = datetime.fromtimestamp(record.created, self.timezone)
            iso = current.isocalendar()
            suffix = "" if self.role == INSTANCE_MODE_EXECUTOR else "_publisher"
            path = self.log_dir / f"{iso.year:04d}_week_{iso.week:02d}{suffix}.txt"
            with path.open("a", encoding="utf-8") as handle:
                handle.write(self.format(record) + "\n")
        except Exception:
            self.handleError(record)


def setup_logging(log_dir: Path, timezone: ZoneInfo, role: str, account: str) -> logging.Logger:
    logger = logging.getLogger(f"oppw_mt5.{account.lower()}.{role.lower()}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.handlers.clear()

    formatter = WarsawFormatter(timezone)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(formatter)

    weekly = WeeklyFileHandler(log_dir, timezone, role)
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



def derived_coordination_path(base: Path, label: str) -> Path:
    suffix = base.suffix or ".lock"
    return base.with_name(f"{base.stem}.{label}{suffix}")


class InterProcessFileLock:
    """OS-backed lock held for the lifetime of the open file handle."""

    def __init__(self, path: Path, owner: Optional[dict[str, Any]] = None):
        self.path = path
        self.owner = owner or {}
        self.handle = None
        self.acquired = False

    @staticmethod
    def pid_is_running(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            try:
                import ctypes
                process_query_limited_information = 0x1000
                still_active = 259
                handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
                if not handle:
                    return False
                exit_code = ctypes.c_ulong()
                ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                return bool(ok) and exit_code.value == still_active
            except Exception:
                return False
        try:
            os.kill(pid, 0)
            return True
        except PermissionError:
            return True
        except (ProcessLookupError, OSError):
            return False

    def try_acquire(self) -> bool:
        if self.acquired:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            return False

        self.handle = handle
        self.acquired = True
        metadata = {
            "pid": os.getpid(),
            "startedAt": datetime.now(UTC).isoformat(),
            **self.owner,
        }
        handle.seek(0)
        handle.truncate()
        handle.write(json.dumps(metadata, separators=(",", ":")).encode("utf-8"))
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
        return True

    def acquire(self) -> None:
        if not self.try_acquire():
            owner = ""
            try:
                owner = self.path.read_text(encoding="utf-8", errors="replace")[:500]
            except OSError:
                pass
            raise RuntimeError(f"Instance lock is already held: {self.path} owner={owner or 'unknown'}")

    def release(self) -> None:
        if not self.acquired or self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
            self.acquired = False

    def __enter__(self) -> "InterProcessFileLock":
        self.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _tb) -> None:
        self.release()


class PublisherPresence:
    def __init__(self, path: Path, role: str):
        self.path = path
        self.role = role
        self.token = uuid.uuid4().hex
        self.last_touch_monotonic = 0.0
        self.cached_active = False
        self.last_check_monotonic = 0.0

    def touch(self, force: bool = False) -> None:
        if self.role != INSTANCE_MODE_PUBLISHER:
            return
        now = time_module.monotonic()
        if not force and now - self.last_touch_monotonic < PUBLISHER_HEARTBEAT_INTERVAL_SECONDS:
            return
        self.last_touch_monotonic = now
        payload = {
            "pid": os.getpid(),
            "token": self.token,
            "role": self.role,
            "updatedEpoch": time_module.time(),
            "updatedAt": datetime.now(UTC).isoformat(),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.{self.token}.tmp")
        temporary.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, self.path)

    def dedicated_publisher_active(self) -> bool:
        if self.role == INSTANCE_MODE_PUBLISHER:
            return True
        now = time_module.monotonic()
        if now - self.last_check_monotonic < 0.5:
            return self.cached_active
        self.last_check_monotonic = now
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            pid = int(raw.get("pid", 0))
            updated = float(raw.get("updatedEpoch", 0.0))
            age = max(0.0, time_module.time() - updated)
            self.cached_active = age <= PUBLISHER_HEARTBEAT_STALE_SECONDS and InterProcessFileLock.pid_is_running(pid)
        except Exception:
            self.cached_active = False
        return self.cached_active

    def remove_if_owner(self) -> None:
        if self.role != INSTANCE_MODE_PUBLISHER:
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if raw.get("token") == self.token:
                self.path.unlink(missing_ok=True)
        except Exception:
            pass


class SharedEventSpool:
    def __init__(self, path: Path, limit: int):
        self.path = path
        self.limit = max(1, limit)
        self.lock_path = path.with_suffix(path.suffix + ".lock")

    def _read_unlocked(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        result: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    result.append(item)
            except json.JSONDecodeError:
                continue
        return result

    def _write_unlocked(self, events: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        text = "".join(json.dumps(item, separators=(",", ":"), ensure_ascii=False) + "\n" for item in events)
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, self.path)

    def append(self, event: dict[str, Any]) -> None:
        lock = InterProcessFileLock(self.lock_path, {"purpose": "monitor-event-spool"})
        with lock:
            events = self._read_unlocked()
            item = dict(event)
            item.setdefault("_spoolId", uuid.uuid4().hex)
            item.setdefault("_sourcePid", os.getpid())
            events.append(item)
            self._write_unlocked(events[-self.limit:])

    def claim(self, maximum: int) -> list[dict[str, Any]]:
        lock = InterProcessFileLock(self.lock_path, {"purpose": "monitor-event-spool"})
        with lock:
            events = self._read_unlocked()
            claimed = events[:max(0, maximum)]
            self._write_unlocked(events[len(claimed):])
            return claimed

    def requeue_front(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        lock = InterProcessFileLock(self.lock_path, {"purpose": "monitor-event-spool"})
        with lock:
            current = self._read_unlocked()
            seen: set[str] = set()
            merged: list[dict[str, Any]] = []
            for item in [*events, *current]:
                key = str(item.get("_spoolId", ""))
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(item)
            self._write_unlocked(merged[:self.limit])

class MobileMonitorPublisher:
    """Asynchronous monitor publisher with cross-process role coordination."""

    def __init__(self, config: Config, logger: logging.Logger, timezone: ZoneInfo, role: str, publisher_presence: PublisherPresence, event_spool: SharedEventSpool, publish_lock_path: Path):
        self.cfg = config
        self.log = logger
        self.timezone = timezone
        self.role = role
        self.publisher_presence = publisher_presence
        self.event_spool = event_spool
        self.publish_lock_path = publish_lock_path
        self.enabled = bool(config.monitor_enabled)
        self.ready = self.enabled and bool(config.monitor_ingest_url and config.monitor_write_token and config.monitor_account_key)
        self.condition = threading.Condition()
        self.guaranteed_snapshots: deque[dict[str, Any]] = deque(maxlen=max(1, config.monitor_minute_snapshot_buffer_size))
        self.latest_snapshot: Optional[dict[str, Any]] = None
        self.publish_requested = False
        self.stopping = False
        self.thread: Optional[threading.Thread] = None
        self.last_error_log_monotonic = 0.0
        self.last_success_utc = ""
        self.equity_history = self.load_equity_history()
        self.last_publish_permission: Optional[bool] = None

        if self.enabled and not self.ready:
            self.local_log(logging.WARNING, "EVENT MONITOR_DISABLED reason=missing_configuration required=OPPW_MONITOR_INGEST_URL,OPPW_MONITOR_WRITE_TOKEN,OPPW_MONITOR_ACCOUNT_KEY")
        elif self.ready and not config.monitor_ingest_url.lower().startswith("https://"):
            self.ready = False
            self.local_log(logging.ERROR, "EVENT MONITOR_DISABLED reason=endpoint_must_use_https")

    def local_log(self, level: int, message: str, *args: Any) -> None:
        self.log.log(level, message, *args, extra={"skip_mobile_publish": True})

    def allowed_to_publish(self) -> bool:
        dedicated_active = self.publisher_presence.dedicated_publisher_active()
        allowed = self.role == INSTANCE_MODE_PUBLISHER or not dedicated_active
        if self.last_publish_permission is None or self.last_publish_permission != allowed:
            self.last_publish_permission = allowed
            reason = "dedicated_publisher" if dedicated_active else "executor_fallback"
            self.local_log(logging.INFO, "EVENT BACKEND_PUBLISHING_STATE role=%s active=%s reason=%s", self.role, allowed, reason)
        return allowed

    def load_equity_history(self) -> list[dict[str, Any]]:
        try:
            if not self.cfg.monitor_history_file.exists():
                return []
            raw = json.loads(self.cfg.monitor_history_file.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return []
            result: list[dict[str, Any]] = []
            for item in raw[-max(1, self.cfg.monitor_equity_history_points):]:
                if isinstance(item, dict) and isinstance(item.get("time"), str) and isinstance(item.get("value"), (int, float)):
                    result.append({"time": item["time"], "value": float(item["value"])})
            return result
        except Exception:
            return []

    def save_equity_history(self) -> None:
        try:
            path = self.cfg.monitor_history_file
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
            temporary.write_text(json.dumps(self.equity_history, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, path)
        except Exception as exc:
            self.rate_limited_error("EVENT MONITOR_HISTORY_SAVE_FAILED error=%s", exc)

    def start(self) -> None:
        if not self.ready or self.thread is not None:
            return
        self.thread = threading.Thread(target=self.worker, name=f"oppw-monitor-{self.role.lower()}", daemon=True)
        self.thread.start()
        self.local_log(logging.INFO, "EVENT MONITOR_PUBLISHER_STARTED role=%s account_key=%s interval=%.1fs endpoint=%s", self.role, self.cfg.monitor_account_key, self.cfg.monitor_publish_interval_seconds, self.cfg.monitor_ingest_url)

    def stop(self) -> None:
        if self.thread is None:
            return
        with self.condition:
            self.stopping = True
            if self.allowed_to_publish() and (self.latest_snapshot is not None or self.guaranteed_snapshots):
                self.publish_requested = True
            self.condition.notify_all()
        self.thread.join(timeout=max(1.0, self.cfg.monitor_timeout_seconds + 2.0))
        self.thread = None

    def enqueue_event(self, event: dict[str, Any]) -> None:
        if not self.ready:
            return
        try:
            self.event_spool.append(event)
        except Exception as exc:
            self.rate_limited_error("EVENT MONITOR_EVENT_SPOOL_FAILED error=%s", exc)

    def submit_snapshot(self, snapshot: dict[str, Any], guaranteed: bool = False) -> None:
        if not self.ready:
            return
        with self.condition:
            if guaranteed and self.allowed_to_publish():
                self.guaranteed_snapshots.append(snapshot)
            else:
                self.latest_snapshot = snapshot
            self.publish_requested = True
            self.condition.notify_all()

    def rate_limited_error(self, message: str, *args: Any) -> None:
        now = time_module.monotonic()
        if now - self.last_error_log_monotonic >= max(5.0, self.cfg.monitor_error_log_interval_seconds):
            self.last_error_log_monotonic = now
            self.local_log(logging.ERROR, message, *args)

    def update_equity_history(self, snapshot: dict[str, Any], captured_at: str) -> None:
        self.equity_history = self.load_equity_history()
        account = snapshot.get("account")
        if not isinstance(account, dict):
            return
        equity = account.get("equity")
        if not isinstance(equity, (int, float)):
            return

        should_append = not self.equity_history
        if self.equity_history:
            try:
                previous = datetime.fromisoformat(str(self.equity_history[-1]["time"]).replace("Z", "+00:00"))
                current = datetime.fromisoformat(captured_at.replace("Z", "+00:00"))
                should_append = (current - previous).total_seconds() >= self.cfg.monitor_equity_sample_seconds
            except Exception:
                should_append = True

        if should_append:
            self.equity_history.append({"time": captured_at, "value": float(equity)})
            self.equity_history = self.equity_history[-max(1, self.cfg.monitor_equity_history_points):]
            self.save_equity_history()
        snapshot["equityHistory"] = list(self.equity_history)

    def send(self, snapshot: dict[str, Any], events: list[dict[str, Any]]) -> None:
        captured_at = datetime.now(UTC).isoformat()
        snapshot_copy = json.loads(json.dumps(snapshot, separators=(",", ":")))
        self.update_equity_history(snapshot_copy, captured_at)
        public_events = [{key: value for key, value in event.items() if not key.startswith("_spool") and key != "_sourcePid"} for event in events]
        payload = {"accountKey": self.cfg.monitor_account_key, "capturedAt": captured_at, "snapshot": snapshot_copy, "events": public_events}
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(self.cfg.monitor_ingest_url, data=body, method="POST", headers={"Authorization": f"Bearer {self.cfg.monitor_write_token}", "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "OPPW-MT5-Publisher/43"})
        try:
            with urllib.request.urlopen(request, timeout=self.cfg.monitor_timeout_seconds) as response:
                if int(response.status) not in (200, 201):
                    raise RuntimeError(f"HTTP {response.status}")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"connection failed: {exc.reason}") from exc

    def worker(self) -> None:
        while True:
            with self.condition:
                while not self.publish_requested and not self.stopping:
                    self.condition.wait()
                if self.stopping and not self.publish_requested and not self.guaranteed_snapshots:
                    return
                guaranteed = bool(self.guaranteed_snapshots)
                snapshot = self.guaranteed_snapshots.popleft() if guaranteed else self.latest_snapshot
                self.publish_requested = bool(self.guaranteed_snapshots)

            if snapshot is None:
                if self.stopping:
                    return
                continue

            if not self.allowed_to_publish():
                with self.condition:
                    self.guaranteed_snapshots.clear()
                    self.latest_snapshot = snapshot
                    self.publish_requested = False
                if self.stopping:
                    return
                continue

            publish_lock = InterProcessFileLock(self.publish_lock_path, {"purpose": "backend-publish", "role": self.role})
            if not publish_lock.try_acquire():
                with self.condition:
                    self.latest_snapshot = snapshot
                    self.publish_requested = not self.stopping
                if self.stopping:
                    return
                time_module.sleep(0.2)
                continue

            events: list[dict[str, Any]] = []
            succeeded = False
            try:
                if not self.allowed_to_publish():
                    continue
                events = self.event_spool.claim(max(1, self.cfg.monitor_event_buffer_size))
                self.send(snapshot, events)
                succeeded = True
                self.last_success_utc = datetime.now(UTC).isoformat()
            except Exception as exc:
                if events:
                    try:
                        self.event_spool.requeue_front(events)
                    except Exception as spool_exc:
                        self.rate_limited_error("EVENT MONITOR_EVENT_REQUEUE_FAILED error=%s", spool_exc)
                self.rate_limited_error("EVENT MONITOR_PUBLISH_FAILED error=%s queued_events=%s", exc, len(events))
                if guaranteed and not self.stopping:
                    with self.condition:
                        self.guaranteed_snapshots.appendleft(snapshot)
                        self.publish_requested = False
            finally:
                publish_lock.release()

            if self.stopping:
                if not succeeded:
                    return
                with self.condition:
                    if not self.guaranteed_snapshots:
                        return
                    self.publish_requested = True


class MobileEventHandler(logging.Handler):
    def __init__(self, publisher: MobileMonitorPublisher):
        super().__init__(logging.INFO)
        self.publisher = publisher

    @staticmethod
    def parse_value(value: str) -> Any:
        lowered = value.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value

    @classmethod
    def parse_details(cls, tokens: list[str]) -> dict[str, Any]:
        details: dict[str, Any] = {}
        for token in tokens:
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            if key:
                details[key] = cls.parse_value(value)
        return details

    @staticmethod
    def inferred_result(name: str) -> Optional[bool]:
        positive = ("_ACCEPTED", "_CONNECTED", "_RECOVERED", "_CAPTURED", "_ARMED", "_UPDATED", "_PROCESSED", "_STARTED")
        negative = ("_REJECTED", "_FAILED", "_LOST", "_SKIPPED", "_DISAPPEARED")
        if name.endswith(positive):
            return True
        if name.endswith(negative):
            return False
        return None

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(record, "skip_mobile_publish", False) or not self.publisher.ready:
            return
        try:
            message = record.getMessage()
            if not (message.startswith("EVENT ") or message.startswith("CHECK ")):
                return
            tokens = shlex.split(message)
            if len(tokens) < 2:
                return

            kind = tokens[0]
            details = self.parse_details(tokens[2:] if kind == "EVENT" else tokens[1:])
            if kind == "CHECK":
                name = str(details.get("name", "CHECK"))
                result_value = details.get("result")
                result = result_value if isinstance(result_value, bool) else str(result_value).upper() == "TRUE" if result_value is not None else None
            else:
                name = tokens[1]
                if name == "SCHEDULED_CHECK" and details.get("name"):
                    name = str(details["name"])
                result_value = details.get("result")
                result = result_value if isinstance(result_value, bool) else self.inferred_result(name)

            event = {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "name": name[:100],
                "result": result,
                "message": message[:1000],
                "details": details,
            }
            self.publisher.enqueue_event(event)
        except Exception:
            self.handleError(record)


# -----------------------------------------------------------------------------
# Strategy engine
# -----------------------------------------------------------------------------


class OPPWContinuousStrategy:
    def __init__(self, config, role: str, account: str, publisher_presence: PublisherPresence, event_spool: SharedEventSpool, publish_lock_path: Path):
        self.cfg = config
        self.role = role
        self.account = account.upper()
        self.is_executor = role == INSTANCE_MODE_EXECUTOR
        self.publisher_presence = publisher_presence
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
        self._session_times_cache: dict[date, SessionTimes] = {}
        self.last_monitor_publish_monotonic = 0.0
        self.last_monitor_minute_key = ""
        self.last_strategy_decision_signature: Optional[tuple[Any, ...]] = None
        self.last_strategy_decision_payload: Optional[dict[str, Any]] = None
        self.last_leverage_inputs_refresh_monotonic = 0.0
        self.cached_previous_full_week_change = float(self.state.prev_full_week_change)
        self.cached_previous_trade_change = float(self.state.prev_change)
        self.cached_previous_full_week_source = "state fallback"
        self.cached_previous_trade_source = "state fallback"
        self.monitor_publisher = MobileMonitorPublisher(config, self.log, self.tz, role, publisher_presence, event_spool, publish_lock_path)
        self.monitor_event_handler = MobileEventHandler(self.monitor_publisher)
        if self.monitor_publisher.ready:
            self.log.addHandler(self.monitor_event_handler)
            self.monitor_publisher.start()

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
        if self.is_executor:
            if not self.cfg.live_enabled:
                self.log.warning("EVENT DRY_RUN live_enabled=false")
            else:
                self.ensure_autotrading_enabled("CONNECT", force_log=True)
        else:
            self.log.info("EVENT INSTANCE_ROLE role=PUBLISHER account=%s trading_allowed=false backend_publishing=true", self.account)

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

    def print_instance_banner(self, now: datetime) -> None:
        status = f"INSTANCE_{self.role} [{self.account}]"
        text = f"{now:%Y-%m-%d %H:%M:%S} {status}"
        width = max(len(text), shutil.get_terminal_size((120, 20)).columns)
        color = "\033[1;93m" if self.is_executor else "\033[1;96m"
        reset = "\033[0m"
        print(f"\n{color}{text.center(width)}{reset}\n", flush=True)

    # ----- Sessions -----------------------------------------------------------

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
        value = SessionTimes(cash_open, cash_open - lead, close_bar_open - lead, close_bar_open, close_processing)
        self._session_times_cache[day] = value
        return value

    def trading_sessions_for_week(self, day: date) -> list[date]:
        monday = day - timedelta(days=day.weekday())
        friday = monday + timedelta(days=4)
        sessions = self.calendar.sessions_in_range(monday.isoformat(), friday.isoformat())
        return [session.date() for session in sessions]

    def final_trading_day(self, day: date) -> Optional[date]:
        sessions = self.trading_sessions_for_week(day)
        return sessions[-1] if sessions else None

    def log_week_plan(self, day: date) -> None:
        key = iso_week_key(day)
        if key == self.last_week_plan_key:
            return
        sessions = self.trading_sessions_for_week(day)
        final_day = sessions[-1] if sessions else None
        weekly_to = self.session_times(final_day).weekly_close.strftime("%Y-%m-%d %H:%M:%S %Z") if final_day else "none"
        self.last_week_plan_key = key
        self.log.info(
            "EVENT WEEK_PLAN week=%s sessions=%s final_day=%s open_action=%s weekly_TO=%s",
            key, ",".join(value.isoformat() for value in sessions) or "none", final_day,
            self.session_times(day).open_action.strftime("%Y-%m-%d %H:%M:%S %Z"), weekly_to,
        )

    # ----- Market data --------------------------------------------------------

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
            if now - previous >= STALE_TICK_REMINDER_SECONDS:
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

    # ----- Position reconciliation -------------------------------------------

    @staticmethod
    def position_identifier(position) -> int:
        return int(getattr(position, "identifier", 0) or position.ticket)

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

    def infer_position_leverage(self, position) -> int:
        from_comment = self.parse_leverage_from_comment(getattr(position, "comment", ""))
        return from_comment if from_comment in {8, 10} else 8

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

    def weekday_sl_target(self, position, now: datetime) -> tuple[float, str]:
        entry = float(position.price_open)
        hard_sl = self.hard_sl_price(position)

        # One 0.4% TSL is active continuously from the Thursday date change
        # through Friday. Keep it over the weekend if TO did not close the trade.
        if now.weekday() in (3, 4, 5, 6):
            return max(hard_sl, entry * self.cfg.tsl_ratio), "TSL"

        # Never weaken a surviving prior-week TSL before the position is closed.
        opened = parse_date(self.state.open_date)
        if opened is not None and iso_week_key(opened) != iso_week_key(now.date()) and self.state.active_sl_reason == "TSL":
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
            hard_sl = entry * self.hard_sl_ratio(self.state.entry_leverage or self.choose_leverage())
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
            return self.state.exit_latched_reason or "broker/manual", "UNRESOLVED"

        broker_code = int(getattr(exit_deal, "reason", -1))
        broker_reason = self.deal_reason_name(broker_code)
        if broker_code == getattr(mt5, "DEAL_REASON_SL", 4):
            return self.state.active_sl_reason or "SL", broker_reason
        if broker_code == getattr(mt5, "DEAL_REASON_TP", 5):
            return self.state.active_tp_reason or "TP", broker_reason
        if self.state.exit_latched_reason:
            return self.state.exit_latched_reason, broker_reason
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
            close_time = self.session_times(session_day).close_bar_open.time().replace(second=0, microsecond=0)
            bar = self.m1_bar_at(self.cfg.signal_symbol, session_day, close_time)
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
        comment_leverage = self.parse_leverage_from_comment(getattr(position, "comment", ""))
        leverage = self.infer_position_leverage(position)
        leverage_source = "comment" if comment_leverage in {8, 10} else "default_L8"
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
            "EVENT POSITION_RECOVERED ticket=%s identifier=%s magic=%s open_time=%s entry=%.5f volume=%s leverage=%s leverage_source=%s signal_open=%.5f signal_open_pending=%s break_even=%s",
            position.ticket, identifier, getattr(position, "magic", 0), opened.isoformat(), float(position.price_open),
            position.volume, leverage, leverage_source, float(signal_open), signal_pending, recovered_break_even,
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
        self.state.last_exit_position_identifier = int(identifier)
        if exit_deal is not None and self.state.entry_price > 0:
            exit_price = float(exit_deal.price)
            change = truncate_four_decimals(exit_price / self.state.entry_price - 1.0)
            trade_class = self.trade_class(change, reason)
            self.state.prev_change = change
            self.state.last_exit_price = exit_price
            self.state.last_exit_preleverage_return = change
            self.state.last_exit_trade_class = trade_class
            exit_timestamp = getattr(exit_deal, "time_msc", 0) / 1000.0 if getattr(exit_deal, "time_msc", 0) else exit_deal.time
            self.state.last_exit_time = self.mt5_timestamp_to_local(exit_timestamp).isoformat()
            self.state.last_exit_reason = reason
            self.log.info(
                "EVENT POSITION_CLOSED reason=%s broker_reason=%s deal_ticket=%s position_identifier=%s entry=%.5f exit=%.5f "
                "change=%.8f preleverage_return=%.8f trade_class=%s classification=return_priority_A_B_then_BE_TSL_C_else_D "
                "active_sl_reason=%s active_tp_reason=%s",
                reason, broker_reason, getattr(exit_deal, "ticket", 0), identifier, self.state.entry_price, exit_price, change, change,
                trade_class, self.state.active_sl_reason or "-", self.state.active_tp_reason or "-",
            )
        else:
            self.state.last_exit_reason = reason
            self.state.last_exit_trade_class = "D"
            self.state.last_exit_preleverage_return = 0.0
            self.log.warning(
                "EVENT POSITION_DISAPPEARED identifier=%s reason=%s broker_reason=%s trade_class=D classification=unresolved",
                identifier, reason, broker_reason,
            )

        self.state.active_position_identifier = 0
        self.state.active_position_ticket = 0
        self.state.open_date = ""
        self.state.entry_price = 0.0
        self.state.entry_signal_daily_open = 0.0
        self.state.entry_signal_open_pending = False
        self.state.entry_leverage = 0
        self.state.break_even = False
        self.state.entry_pending_until_utc = 0
        self.clear_current_position_exit_state(clear_last_exit=False)
        self.state.save(self.cfg.state_file)

    # ----- Status -------------------------------------------------------------

    def phase(self, now: datetime) -> str:
        if now.weekday() >= 5:
            return "WEEKEND"
        session = self.session_times(now.date())
        if now < session.cash_open:
            return "PREMARKET"
        if now < session.close_processing:
            return "REGULAR"
        return "AFTER_CLOSE"

    def protection_regime(self, now: datetime) -> str:
        if self.state.exit_latched_reason:
            return f"Closing position: {self.state.exit_latched_reason}"
        if now.weekday() in (3, 4, 5, 6) or self.state.active_sl_reason == "TSL":
            return "Tight stop loss (0.4%)" + (" + break-even exit" if self.state.break_even else "")
        return "Hard stop loss + break-even exit" if self.state.break_even else "Hard stop loss"

    def oh_check_pending(self, now: datetime) -> bool:
        session = self.session_times(now.date())
        return self.state.last_open_action_date != now.date().isoformat() and now < session.cash_open

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

        leverage = self.state.entry_leverage or self.choose_leverage()
        add("SL", floor_step(entry * self.hard_sl_ratio(leverage), tick_size))
        weekday_price, weekday_reason = self.weekday_sl_target(position, now)
        if weekday_reason != "SL":
            add(weekday_reason, floor_step(weekday_price, tick_size))
        if float(position.sl) > 0:
            add(self.state.active_sl_reason or "BROKER_SL", float(position.sl))
        if self.state.break_even:
            add(self.state.active_tp_reason or "BH", ceil_step(entry * self.cfg.break_even_ratio, tick_size))
        if float(position.tp) > 0:
            add(self.state.active_tp_reason or "BROKER_TP", float(position.tp))
        if self.oh_check_pending(now):
            add("OH", ceil_step(entry * (1.0 + self.cfg.tpps[now.weekday() if now.weekday() < 5 else 4]), tick_size))

        if not candidates:
            return "none"
        name, price = min(candidates, key=lambda item: abs(item[1] - bid))
        difference = price - bid
        distance = abs(difference)
        distance_pct = distance / bid * 100.0
        direction = "at current price" if abs(difference) <= tolerance else "above" if difference > 0 else "below"
        return f"{name} @ {price:.5f} — {distance:.5f} points {direction} ({distance_pct:.4f}%)"


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

    def latest_closed_trade_change(self, now: Optional[datetime] = None) -> Optional[float]:
        now = now or datetime.now(self.tz)
        deals = mt5.history_deals_get(now.astimezone(UTC) - timedelta(days=730), now.astimezone(UTC) + timedelta(days=1))
        if deals is None:
            return None
        in_values = {getattr(mt5, "DEAL_ENTRY_IN", 0), getattr(mt5, "DEAL_ENTRY_INOUT", 2)}
        out_values = {getattr(mt5, "DEAL_ENTRY_OUT", 1), getattr(mt5, "DEAL_ENTRY_OUT_BY", 3)}
        symbol_deals = [deal for deal in deals if str(getattr(deal, "symbol", "")) == self.cfg.trade_symbol]
        exits = sorted([deal for deal in symbol_deals if int(getattr(deal, "entry", -1)) in out_values], key=lambda deal: int(getattr(deal, "time_msc", 0) or int(getattr(deal, "time", 0)) * 1000), reverse=True)
        for exit_deal in exits:
            position_id = int(getattr(exit_deal, "position_id", 0) or 0)
            if position_id <= 0:
                continue
            position_deals = [deal for deal in symbol_deals if int(getattr(deal, "position_id", 0) or 0) == position_id]
            entries = [deal for deal in position_deals if int(getattr(deal, "entry", -1)) in in_values]
            position_exits = [deal for deal in position_deals if int(getattr(deal, "entry", -1)) in out_values]
            if not entries or not position_exits:
                continue
            strategy_entry = any(int(getattr(deal, "magic", 0) or 0) == int(self.cfg.magic) or str(getattr(deal, "comment", "")).startswith(str(self.cfg.comment_prefix)) for deal in entries)
            if not strategy_entry:
                continue
            entry_volume = sum(abs(float(getattr(deal, "volume", 0.0) or 0.0)) for deal in entries)
            exit_volume = sum(abs(float(getattr(deal, "volume", 0.0) or 0.0)) for deal in position_exits)
            if entry_volume <= 0 or exit_volume <= 0:
                continue
            entry_price = sum(abs(float(getattr(deal, "volume", 0.0) or 0.0)) * float(getattr(deal, "price", 0.0) or 0.0) for deal in entries) / entry_volume
            exit_price = sum(abs(float(getattr(deal, "volume", 0.0) or 0.0)) * float(getattr(deal, "price", 0.0) or 0.0) for deal in position_exits) / exit_volume
            if entry_price > 0 and exit_price > 0:
                return truncate_four_decimals(exit_price / entry_price - 1.0)
        return None

    def resolved_leverage_inputs(self, force: bool = False) -> tuple[float, float, str, str]:
        now_monotonic = time_module.monotonic()
        if not force and now_monotonic - self.last_leverage_inputs_refresh_monotonic < 60.0:
            return self.cached_previous_full_week_change, self.cached_previous_trade_change, self.cached_previous_full_week_source, self.cached_previous_trade_source
        self.last_leverage_inputs_refresh_monotonic = now_monotonic
        full_week = self.latest_completed_week_change()
        previous_trade = self.latest_closed_trade_change()
        self.cached_previous_full_week_change = float(full_week) if full_week is not None else float(self.state.prev_full_week_change)
        self.cached_previous_trade_change = float(previous_trade) if previous_trade is not None else float(self.state.prev_change)
        self.cached_previous_full_week_source = "market history" if full_week is not None else "state fallback"
        self.cached_previous_trade_source = "MT5 deal history" if previous_trade is not None else "state fallback"
        if self.is_executor:
            changed = abs(self.state.prev_full_week_change - self.cached_previous_full_week_change) > 1e-12 or abs(self.state.prev_change - self.cached_previous_trade_change) > 1e-12
            self.state.prev_full_week_change = self.cached_previous_full_week_change
            self.state.prev_change = self.cached_previous_trade_change
            if changed:
                self.state.save(self.cfg.state_file)
                self.log.info("EVENT LEVERAGE_INPUTS_RECOVERED previous_full_week_change=%.6f full_week_source=%s previous_trade_change=%.6f trade_source=%s", self.cached_previous_full_week_change, self.cached_previous_full_week_source.replace(" ", "_"), self.cached_previous_trade_change, self.cached_previous_trade_source.replace(" ", "_"))
        return self.cached_previous_full_week_change, self.cached_previous_trade_change, self.cached_previous_full_week_source, self.cached_previous_trade_source

    def leverage_decision(self) -> tuple[int, str]:
        previous_full_week, previous_trade, full_week_source, trade_source = self.resolved_leverage_inputs()
        if self.cfg.base_leverage == 8:
            triggers: list[str] = []
            if previous_full_week < -0.025:
                triggers.append(f"previous full-week change {previous_full_week:.4%} ({full_week_source}) < -2.5000%")
            if previous_trade < -0.007:
                triggers.append(f"previous trade change {previous_trade:.4%} ({trade_source}) < -0.7000%")
            if triggers:
                return self.cfg.loss_leverage, f"{self.cfg.loss_leverage}x because " + " and ".join(triggers)
            return self.cfg.base_leverage, f"{self.cfg.base_leverage}x because previous full-week change {previous_full_week:.4%} ({full_week_source}) >= -2.5000% and previous trade change {previous_trade:.4%} ({trade_source}) >= -0.7000%"
        return self.cfg.base_leverage, f"{self.cfg.base_leverage}x because base leverage is configured as {self.cfg.base_leverage}x"

    @staticmethod
    def broker_margin_leverage(account) -> float:
        value = float(getattr(account, "leverage", 0.0) or 0.0) if account is not None else 0.0
        return value if value > 0 else 20.0

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

    def potential_position_preview(self) -> dict[str, Any]:
        previous_full_week, previous_trade, full_week_source, trade_source = self.resolved_leverage_inputs()
        leverage, leverage_reason = self.leverage_decision()
        now = datetime.now(self.tz)
        result: dict[str, Any] = {
            "available": False, "generatedAt": now.isoformat(), "build": BUILD_ID, "account": self.account,
            "symbol": self.cfg.trade_symbol, "side": "BUY", "price": 0.0, "priceSource": "MT5 current BUY price",
            "volume": 0.0, "requiredDeposit": 0.0, "brokerMarginLeverage": 0.0, "depositSource": "",
            "balance": 0.0, "equity": 0.0, "freeMargin": 0.0, "freeMarginAfter": 0.0,
            "marginUsagePercent": 0.0, "marginLevelAfterPercent": 0.0, "effectiveLeverage": 0.0,
            "strategyLeverage": float(leverage), "leverageReason": leverage_reason,
            "previousFullWeekChange": float(previous_full_week), "previousFullWeekSource": full_week_source,
            "previousTradeChange": float(previous_trade), "previousTradeSource": trade_source,
            "fullWeekTriggerPercent": -2.5, "previousTradeTriggerPercent": -0.7,
            "potentialStopLossPercent": -0.5 / float(leverage) * 100.0 if leverage > 0 else 0.0,
            "potentialStopLossRatio": 1.0 - 0.5 / float(leverage) if leverage > 0 else 0.0,
            "potentialStopLossPrice": 0.0, "potentialStopLossCash": 0.0, "accountLossPercentAtStop": 0.0,
            "stopLossFormula": "underlying stop = -0.5 / strategy leverage",
            "positionNotional": 0.0, "sizingUnits": 0, "minimumVolumeFloor": False, "scenarios": [], "error": "",
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
            ask = float(getattr(tick, "ask", 0.0) or 0.0)
            bid = float(getattr(tick, "bid", 0.0) or 0.0)
            last = float(getattr(tick, "last", 0.0) or 0.0)
            price = ask if ask > 0 else last if last > 0 else bid
            if price <= 0:
                raise RuntimeError(f"No usable current price for {self.cfg.trade_symbol}")

            minimum_volume_notional = self.minimum_volume_notional(info, price)
            _, _, sizing_units = self.target_notional(balance, leverage, minimum_volume_notional)
            minimum_volume_floor = False
            volume = self.normalized_volume(sizing_units, info)
            if volume <= 0:
                minimum_volume = float(info.volume_min)
                minimum_margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, minimum_volume, price)
                if minimum_margin is not None and float(minimum_margin) <= max(0.0, free_margin):
                    volume = minimum_volume
                    sizing_units = 1
                    minimum_volume_floor = True
                else:
                    raise RuntimeError("Calculated potential volume is below the broker minimum and minimum volume is not affordable")

            required_raw = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, volume, price)
            if required_raw is None:
                raise RuntimeError(f"order_calc_margin failed: {mt5.last_error()}")
            required_deposit = float(required_raw)
            broker_leverage = self.broker_margin_leverage(account)
            effective_leverage = required_deposit * broker_leverage / balance if balance > 0 else 0.0
            stop_ratio = 1.0 - 0.5 / float(leverage)
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01)
            stop_price = floor_step(price * stop_ratio, tick_size)
            stop_profit_raw = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, self.cfg.trade_symbol, volume, price, stop_price)
            stop_profit = float(stop_profit_raw) if stop_profit_raw is not None else 0.0
            existing_margin = float(getattr(account, "margin", 0.0) or 0.0)
            margin_after = existing_margin + required_deposit

            result.update({
                "available": True, "price": price, "volume": float(volume), "requiredDeposit": required_deposit,
                "brokerMarginLeverage": broker_leverage, "depositSource": "MT5 order_calc_margin(proposed volume, current BUY price)",
                "balance": balance, "equity": equity, "freeMargin": free_margin, "freeMarginAfter": free_margin - required_deposit,
                "marginUsagePercent": required_deposit / balance * 100.0 if balance > 0 else 0.0,
                "marginLevelAfterPercent": equity / margin_after * 100.0 if margin_after > 0 else 0.0,
                "effectiveLeverage": effective_leverage, "potentialStopLossPrice": stop_price,
                "potentialStopLossCash": stop_profit, "accountLossPercentAtStop": stop_profit / balance * 100.0 if balance > 0 else 0.0,
                "positionNotional": sizing_units * minimum_volume_notional, "sizingUnits": int(sizing_units),
                "minimumVolumeFloor": minimum_volume_floor,
                "scenarios": self.what_if_scenarios(float(volume), price, balance, -0.5 / float(leverage)),
            })
        except Exception as exc:
            result["error"] = str(exc)
        return result

    def strategy_decision_payload(self, preview: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        preview = preview or self.potential_position_preview()
        decision_id_source = "|".join(str(value) for value in (
            self.account, iso_week_key(datetime.now(self.tz).date()), BUILD_ID, preview.get("symbol", ""),
            preview.get("strategyLeverage", 0.0), preview.get("previousFullWeekChange", 0.0),
            preview.get("previousTradeChange", 0.0), preview.get("volume", 0.0), preview.get("available", False),
        ))
        decision_id = uuid.uuid5(uuid.NAMESPACE_URL, decision_id_source).hex
        return {
            "decisionId": decision_id, "recordedAt": datetime.now(self.tz).isoformat(), "build": BUILD_ID,
            "account": self.account, "decision": "NEXT_WEEK_LONG_ENTRY",
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
                "symbol", "side", "price", "priceSource", "volume", "requiredDeposit", "depositSource",
                "brokerMarginLeverage", "effectiveLeverage", "positionNotional", "sizingUnits", "minimumVolumeFloor",
                "balance", "equity", "freeMargin", "freeMarginAfter", "marginUsagePercent", "marginLevelAfterPercent",
            )},
            "risk": {key: preview.get(key) for key in (
                "potentialStopLossPercent", "potentialStopLossRatio", "potentialStopLossPrice",
                "potentialStopLossCash", "accountLossPercentAtStop", "stopLossFormula", "scenarios",
            )},
            "error": str(preview.get("error", "")),
        }

    def record_strategy_decision_if_changed(self, force: bool = False) -> dict[str, Any]:
        preview = self.potential_position_preview()
        payload = self.strategy_decision_payload(preview)
        signature = (
            iso_week_key(datetime.now(self.tz).date()), payload["outcome"], round(float(payload["selectedLeverage"]), 6),
            round(float(payload["inputs"]["previousFullWeekChange"]), 8), round(float(payload["inputs"]["previousTradeChange"]), 8),
            str(payload["inputs"].get("previousFullWeekSource", "")), str(payload["inputs"].get("previousTradeSource", "")),
            round(float(payload["sizing"].get("volume") or 0.0), 8), bool(payload["sizing"].get("minimumVolumeFloor")),
            payload["error"].split(":", 1)[0],
        )
        self.last_strategy_decision_payload = payload
        if force or signature != self.last_strategy_decision_signature:
            self.last_strategy_decision_signature = signature
            self.log.info(
                "EVENT STRATEGY_DECISION_RECORDED decision_id=%s outcome=%s leverage=%.0f "
                "previous_full_week=%.8f full_week_source=%s previous_trade=%.8f trade_source=%s volume=%.8f required_deposit=%.2f "
                "effective_leverage=%.6f stop_loss_percent=%.4f stop_loss_price=%.5f stop_loss_cash=%.2f error=%s",
                payload["decisionId"], payload["outcome"], payload["selectedLeverage"],
                payload["inputs"]["previousFullWeekChange"], str(payload["inputs"].get("previousFullWeekSource", "")).replace(" ", "_"),
                payload["inputs"]["previousTradeChange"], str(payload["inputs"].get("previousTradeSource", "")).replace(" ", "_"),
                float(payload["sizing"].get("volume") or 0.0), float(payload["sizing"].get("requiredDeposit") or 0.0),
                float(payload["sizing"].get("effectiveLeverage") or 0.0),
                float(payload["risk"].get("potentialStopLossPercent") or 0.0),
                float(payload["risk"].get("potentialStopLossPrice") or 0.0),
                float(payload["risk"].get("potentialStopLossCash") or 0.0),
                shlex.quote(str(payload["error"] or "none")),
            )
        return payload

    def format_status(self, reason: str, position, now: datetime, current_bar: Optional[M1Bar] = None) -> str:
        due, due_reason, final_day = self.weekly_exit_status(position, now)
        account = mt5.account_info()
        equity = float(getattr(account, "equity", 0.0)) if account is not None else 0.0
        deposit = float(getattr(account, "margin", 0.0)) if account is not None else 0.0
        currency = str(getattr(account, "currency", "")).strip() if account is not None else ""
        currency_suffix = f" {currency}" if currency else ""
        phase = self.phase(now)
        regime = self.protection_regime(now) if position is not None else "None"

        if position is None:
            preview = self.potential_position_preview()
            leverage = int(preview["strategyLeverage"])
            leverage_reason = str(preview["leverageReason"])
            if bool(preview["available"]):
                potential_lines = [
                    f"next potential position: BUY {float(preview['volume']):.2f} lot {preview['symbol']} @ {float(preview['price']):.5f}",
                    f"required deposit: {float(preview['requiredDeposit']):.2f}{currency_suffix}",
                    f"effective leverage: {float(preview['effectiveLeverage']):.4f}x ({float(preview['brokerMarginLeverage']):.0f} × required deposit / balance)",
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
                "closest condition: none — no open position",
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
        leverage = self.state.entry_leverage or self.choose_leverage()
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
            f"position: {float(position.volume):.2f} lot {position.symbol}",
            f"leverage: {leverage}x",
            f"opened: {opened:%Y-%m-%d %H:%M:%S %Z}",
            f"open price: {entry:.5f}",
            f"current ask: {ask:.5f}",
            f"current P/L: {current_pnl:.2f}{currency_suffix}",
            f"current P/L %: {raw_pnl_pct:.4%}",
            f"current P/L % leveraged: {leveraged_pnl_pct:.4%}",
            f"equity: {equity:.2f}{currency_suffix} deposit: {deposit:.2f}{currency_suffix}",
            f"SL: {float(position.sl):.5f} ({self.state.active_sl_reason or '-'})",
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

    def status_signature(self, position, now: datetime) -> tuple[Any, ...]:
        if position is None:
            return (None, self.state.last_exit_reason, self.state.break_even, self.protection_regime(now))
        return (
            int(position.ticket), round(float(position.volume), 8), round(float(position.sl), 5), round(float(position.tp), 5),
            self.state.break_even, self.state.exit_latched_reason, self.state.active_sl_reason, self.state.active_tp_reason,
            self.protection_regime(now),
        )

    # ----- Mobile monitoring --------------------------------------------------

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
            if now < session.open_action and self.state.last_open_action_date != day_key:
                return "OH", session.open_action.isoformat()
            if now < session.weekly_close and self.state.last_close_action_date != day_key:
                name = "CH / TO" if self.final_trading_day(now.date()) == now.date() else "CH"
                return name, session.weekly_close.isoformat()
            if now < session.close_processing:
                return "DAILY CLOSE", session.close_processing.isoformat()

        try:
            end = now.date() + timedelta(days=14)
            sessions = self.calendar.sessions_in_range(now.date().isoformat(), end.isoformat())
            for calendar_session in sessions:
                session_day = calendar_session.date()
                candidate = self.session_times(session_day).open_action
                if candidate <= now:
                    continue
                if position is None and session_day.weekday() not in (0, 1):
                    continue
                if position is None and self.state.last_entry_week == iso_week_key(session_day):
                    continue
                if position is None:
                    return f"{session_day.strftime('%A').upper()} BUY WINDOW", candidate.isoformat()
                return "OH", candidate.isoformat()
        except Exception:
            pass
        return "WAIT", ""

    def monitor_all_conditions(self, position, now: datetime, trade_bid: float, signal_price: float) -> list[dict[str, Any]]:
        if position is None or trade_bid <= 0:
            return []
        entry = float(position.price_open)
        if entry <= 0:
            return []

        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        tolerance = tick_size * 1.5
        conditions: list[dict[str, Any]] = []

        def add(name: str, target: float, current: float, source: str, active: bool = True) -> None:
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
            })

        desired_sl, sl_reason = self.weekday_sl_target(position, now)
        add(sl_reason, floor_step(desired_sl, tick_size), trade_bid, self.cfg.trade_symbol)
        if float(position.sl) > 0:
            add(self.state.active_sl_reason or "BROKER_SL", float(position.sl), trade_bid, self.cfg.trade_symbol)

        weekday_index = now.weekday() if now.weekday() < 5 else 4
        tpp = self.cfg.tpps[weekday_index]
        if self.oh_check_pending(now):
            add("OH", ceil_step(entry * (1.0 + tpp), tick_size), trade_bid, self.cfg.trade_symbol)

        # The mobile dashboard displays OH and CH against the same trade-entry
        # target. On Friday both are exactly entry * 1.05. This is presentation
        # metadata only; the production CH execution rule is unchanged.
        if signal_price > 0:
            add("CH", ceil_step(entry * (1.0 + tpp), tick_size), signal_price, self.cfg.signal_symbol)

        if self.state.break_even:
            add("BE", ceil_step(entry * self.cfg.break_even_ratio, tick_size), trade_bid, self.cfg.trade_symbol)

        return sorted(conditions, key=lambda item: float(item["distancePoints"]))

    @staticmethod
    def monitor_closest_condition(conditions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
        return conditions[0] if conditions else None

    def monitor_position_exposure(self, position, deposit: float, account=None) -> float:
        return deposit * self.broker_margin_leverage(account) if position is not None and deposit > 0 else 0.0

    def build_mobile_snapshot(self, position, now: datetime, current_bar: Optional[M1Bar]) -> dict[str, Any]:
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

        stale = any(age is None or age > self.cfg.maximum_tick_age_seconds for age in (trade_age, signal_age))
        connected = self.connected and account is not None
        health = "CRITICAL" if not connected else "WARNING" if stale else "OK"
        next_action, next_action_at = self.monitor_next_action(position, now)
        phase = f"{now:%A} {self.phase(now).replace('_', ' ').title()}"
        regime = self.protection_regime(now) if position is not None else "None"

        position_payload: Optional[dict[str, Any]] = None
        conditions: list[dict[str, Any]] = []
        closest = None
        deposit = 0.0
        if position is not None:
            bid = trade_bid if trade_bid > 0 else float(getattr(position, "price_current", 0.0) or 0.0)
            ask = trade_ask
            entry = float(position.price_open)
            current_position_price = float(getattr(position, "price_current", 0.0) or 0.0)
            if current_position_price <= 0:
                current_position_price = bid if bid > 0 else ask
            try:
                deposit = self.position_required_deposit(position, current_position_price)
            except Exception as exc:
                self.log.warning("EVENT POSITION_MARGIN_CALC_FAILED ticket=%s price=%.5f error=%s", position.ticket, current_position_price, exc, extra={"skip_mobile_publish": True})
                deposit = 0.0
            broker_leverage = self.broker_margin_leverage(account)
            raw_change = bid / entry - 1.0 if bid > 0 and entry > 0 else 0.0
            leverage = self.state.entry_leverage or self.choose_leverage()
            profit = float(getattr(position, "profit", 0.0)) + float(getattr(position, "swap", 0.0))
            timestamp = getattr(position, "time_msc", 0) / 1000.0 if getattr(position, "time_msc", 0) else float(position.time)
            opened = self.mt5_timestamp_to_local(timestamp)
            exposure = self.monitor_position_exposure(position, deposit, account)
            info = mt5.symbol_info(position.symbol)
            tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
            weekday_index = now.weekday() if now.weekday() < 5 else 4
            potential_take_profit = ceil_step(entry * (1.0 + self.cfg.tpps[weekday_index]), tick_size)
            position_payload = {
                "open": True,
                "symbol": str(position.symbol),
                "side": "BUY",
                "volume": float(position.volume),
                "ticket": int(position.ticket),
                "openedAt": opened.isoformat(),
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
                "depositPrice": current_position_price,
                "depositSource": "MT5 order_calc_margin(position volume, current position price)",
                "brokerMarginLeverage": broker_leverage,
                "effectiveLeverage": exposure / balance if balance > 0 else 0.0,
                "stopLoss": float(position.sl),
                "takeProfit": float(position.tp),
                "potentialTakeProfit": potential_take_profit,
                "breakEvenArmed": bool(self.state.break_even),
                "protectionRegime": regime,
                "activeSlReason": self.state.active_sl_reason,
                "activeTpReason": self.state.active_tp_reason,
            }
            conditions = self.monitor_all_conditions(position, now, bid, signal_price)
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
            "potentialPosition": (preview := self.potential_position_preview()) if position is None else None,
            "strategyDecision": self.strategy_decision_payload(preview) if position is None else self.last_strategy_decision_payload,
            "lastClosedTrade": {
                "positionIdentifier": int(self.state.last_exit_position_identifier),
                "closedAt": self.state.last_exit_time,
                "exitReason": self.state.last_exit_reason,
                "preleverageReturn": float(self.state.last_exit_preleverage_return),
                "preleverageReturnPercent": float(self.state.last_exit_preleverage_return) * 100.0,
                "tradeClass": self.state.last_exit_trade_class,
            } if self.state.last_exit_time or self.state.last_exit_trade_class else None,
            "conditions": conditions,
            "closestCondition": closest,
            "equityHistory": [],
        }

    def publish_mobile_minute_status(self, position, now: datetime, current_bar: Optional[M1Bar], force: bool = False) -> bool:
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


    # ----- Calculations and order sizing -------------------------------------

    def choose_leverage(self) -> int:
        return self.leverage_decision()[0]

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

    def target_notional(self, balance: float, leverage: int, minimum_volume_notional: float) -> tuple[float, float, int]:
        if minimum_volume_notional <= 0:
            raise ValueError(f"Minimum-volume notional must be positive, got {minimum_volume_notional}")
        sizing_quantum = minimum_volume_notional / self.cfg.sizing_multiplier
        divisor = self.cfg.sizing_multiplier / leverage
        units = math.floor(balance / divisor / sizing_quantum)
        return minimum_volume_notional, sizing_quantum, units

    @staticmethod
    def normalized_volume(sizing_units: int, info) -> float:
        if sizing_units <= 0:
            return 0.0
        step = float(info.volume_step)
        volume = floor_step(sizing_units * float(info.volume_min), step)
        volume = min(volume, float(info.volume_max))
        if volume < float(info.volume_min):
            return 0.0
        return round(volume, 8)

    @staticmethod
    def filling_mode_name(mode: int) -> str:
        names = {mt5.ORDER_FILLING_FOK: "FOK", mt5.ORDER_FILLING_IOC: "IOC", mt5.ORDER_FILLING_RETURN: "RETURN"}
        return names.get(mode, str(mode))

    def order_filling_modes(self, info) -> list[int]:
        configured = os.getenv("OPPW_FILLING_MODE", "AUTO").strip().upper()
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
        return True

    def send_buy(self, current_day: date) -> bool:
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
            "comment": f"{self.cfg.comment_prefix} L{leverage}"[:31], "type_time": mt5.ORDER_TIME_GTC,
        }
        scheduled = self.session_times(current_day).open_action

        if not self.cfg.live_enabled:
            request = dict(request_base)
            request["type_filling"] = self.order_filling_modes(info)[0]
            self.log.info(
                "EVENT BUY_DRY_RUN day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f sizing_quantum=%.2f sizing_units=%s target_notional=%.2f position_notional=%.2f ask=%.5f sl=%.5f filling=%s",
                current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional,
                sizing_quantum, sizing_units, target_notional, position_notional, ask, sl,
                self.filling_mode_name(request["type_filling"]),
            )
            return False
        if not self.ensure_autotrading_enabled("BUY"):
            return False
        if not self.request_allowed_now():
            return False

        request, check = self.checked_deal_request(request_base, info, "BUY")
        self.log.info(
            "EVENT BUY_REQUEST day=%s scheduled=%s leverage=%s volume=%s minimum_volume=%.8f minimum_volume_notional=%.2f sizing_quantum=%.2f sizing_units=%s target_notional=%.2f position_notional=%.2f ask=%.5f sl=%.5f filling=%s",
            current_day, scheduled.isoformat(), leverage, volume, float(info.volume_min), minimum_volume_notional,
            sizing_quantum, sizing_units, target_notional, position_notional, ask, sl,
            self.filling_mode_name(request.get("type_filling", -1)),
        )
        if check is None or int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            if int(getattr(check, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("BUY_CHECK_RETCODE_10027", force_log=True)
            self.log.error("EVENT BUY_CHECK_REJECTED retcode=%s comment=%s", getattr(check, "retcode", None), getattr(check, "comment", mt5.last_error()))
            return False

        result = mt5.order_send(request)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if result is None or int(result.retcode) not in accepted:
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("BUY_RETCODE_10027", force_log=True)
            self.log.error("EVENT BUY_REJECTED retcode=%s comment=%s", getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False

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
        desired_sl = round(desired_sl, digits) if desired_sl else 0.0
        desired_tp = round(desired_tp, digits) if desired_tp else 0.0
        tolerance = max(tick_size * 0.5, float(info.point) * 0.5)

        if not price_changed(float(position.sl), desired_sl, tolerance) and not price_changed(float(position.tp), desired_tp, tolerance):
            self.record_active_protection(position, desired_sl, desired_tp, sl_reason, tp_reason)
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
        request = {
            "action": mt5.TRADE_ACTION_SLTP, "symbol": position.symbol, "position": int(position.ticket),
            "sl": desired_sl, "tp": desired_tp, "magic": self.cfg.magic,
        }
        result = mt5.order_send(request)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_NO_CHANGES", 10025)}
        if result is None or int(result.retcode) not in accepted:
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled("SLTP_RETCODE_10027", force_log=True)
            self.log.error("EVENT SLTP_REJECTED reason=%s retcode=%s comment=%s", reason, getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False

        self.record_active_protection(position, desired_sl, desired_tp, sl_reason, tp_reason)
        self.log.info("EVENT SLTP_ACCEPTED reason=%s retcode=%s", reason, result.retcode)
        return True

    def close_position_market(self, position, reason: str, now: datetime) -> bool:
        if not self.trade_request_role_allowed(f"SELL_{reason}"):
            return False
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
            self.log.info("EVENT SELL_DRY_RUN reason=%s ticket=%s volume=%s bid=%.5f", reason, position.ticket, position.volume, bid)
            return False
        if not self.ensure_autotrading_enabled(f"SELL_{reason}"):
            return False
        if not self.request_allowed_now():
            return False

        request, check = self.checked_deal_request(request_base, info, f"SELL_{reason}")
        if check is None or int(check.retcode) not in (0, getattr(mt5, "TRADE_RETCODE_DONE", 10009)):
            if int(getattr(check, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled(f"SELL_{reason}_CHECK_RETCODE_10027", force_log=True)
            self.log.error("EVENT SELL_CHECK_REJECTED reason=%s retcode=%s comment=%s", reason, getattr(check, "retcode", None), getattr(check, "comment", mt5.last_error()))
            return False

        self.state.exit_latched_reason = reason
        self.state.exit_latched_at = now.isoformat()
        self.state.save(self.cfg.state_file)
        self.log.info("EVENT SELL_REQUEST reason=%s ticket=%s volume=%s bid=%.5f", reason, position.ticket, position.volume, bid)
        result = mt5.order_send(request)
        accepted = {getattr(mt5, "TRADE_RETCODE_DONE", 10009), getattr(mt5, "TRADE_RETCODE_PLACED", 10008), getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)}
        if result is None or int(result.retcode) not in accepted:
            if int(getattr(result, "retcode", -1)) == int(getattr(mt5, "TRADE_RETCODE_CLIENT_DISABLES_AT", 10027)):
                self.ensure_autotrading_enabled(f"SELL_{reason}_RETCODE_10027", force_log=True)
            self.log.error("EVENT SELL_REJECTED reason=%s retcode=%s comment=%s", reason, getattr(result, "retcode", None), getattr(result, "comment", mt5.last_error()))
            return False
        self.log.info("EVENT SELL_ACCEPTED reason=%s retcode=%s", reason, result.retcode)
        return True

    # ----- Protection ---------------------------------------------------------

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

        max_valid_sl = bid - distance
        min_valid_tp = ask + distance
        if desired_sl >= max_valid_sl:
            self.arm_exit(position, "PROTECTION_SL_ALREADY_CROSSED", now)
            return False
        if desired_tp > 0 and desired_tp <= min_valid_tp:
            self.arm_exit(position, "PROTECTION_TP_ALREADY_CROSSED", now)
            return False

        desired_sl = floor_step(desired_sl, tick_size)
        desired_tp = ceil_step(desired_tp, tick_size) if desired_tp > 0 else 0.0
        leverage = self.state.entry_leverage or self.choose_leverage()
        reason_parts = [f"HARD_SL_L{leverage}_RATIO_{self.hard_sl_ratio(leverage):.6f}"]
        if sl_reason == "TSL":
            reason_parts.append(f"TSL_STOP_{self.cfg.tsl_stop:.4%}_RATIO_{self.cfg.tsl_ratio:.6f}")
        if desired_tp > 0:
            reason_parts.append(f"BE_{self.cfg.break_even_ratio:.6f}")
        return self.modify_sltp(position, desired_sl, desired_tp, "+".join(reason_parts), sl_reason, tp_reason)

    # ----- Strategy conditions ------------------------------------------------

    def evaluate_premarket_open(self, position, bar: M1Bar, now: datetime) -> None:
        entry = float(position.price_open)
        if self.state.break_even and bar.open > entry * self.cfg.break_even_ratio:
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

        close_time = self.session_times(current_day).close_bar_open.time().replace(second=0, microsecond=0)
        trade_close_bar = self.m1_bar_at(self.cfg.trade_symbol, current_day, close_time)
        signal_close_bar = self.m1_bar_at(self.cfg.signal_symbol, current_day, close_time)
        if trade_close_bar is None or signal_close_bar is None:
            return

        weekday = current_day.weekday()
        if self.state.prev_open > 0 and self.final_trading_day(current_day) == current_day:
            self.state.prev_full_week_change = trade_close_bar.close / self.state.prev_open - 1.0
            self.log.info("EVENT FULL_WEEK_CHANGE_UPDATED value=%.5f day=%s", self.state.prev_full_week_change, current_day)

        if position is not None and not self.state.exit_latched_reason:
            signal_reference = self.state.entry_signal_daily_open or self.state.entry_price
            opened = parse_date(self.state.open_date)
            if not self.state.break_even and opened is not None and current_day != opened and signal_close_bar.close < signal_reference * self.cfg.break_even_ratio:
                self.state.break_even = True
                self.state.save(self.cfg.state_file)
                self.log.info("EVENT BREAK_EVEN_ARMED day=%s signal_close=%.5f threshold=%.5f", current_day, signal_close_bar.close, signal_reference * self.cfg.break_even_ratio)
                self.emit_status("BREAK_EVEN_ARMED", position, now)

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
        if self.state.last_open_action_date == day_key:
            return False
        if now >= session.cash_open:
            self.state.last_open_action_date = day_key
            self.state.save(self.cfg.state_file)
            return False
        if now < session.open_action:
            return False

        tick = self.require_fresh_tick(position.symbol)
        bid = float(tick.bid)
        entry = float(position.price_open)
        tpp = self.cfg.tpps[current_day.weekday()]
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

        signal_reference = self.state.entry_signal_daily_open or self.state.entry_price
        signal_price = self.live_signal_price()
        tpp = self.cfg.tpps[current_day.weekday() if current_day.weekday() < 5 else 4]
        ch_threshold = signal_reference * (1.0 + tpp)
        ch = signal_price > ch_threshold
        is_final_day = final_day == current_day
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

        self.state.last_close_action_date = day_key
        self.state.save(self.cfg.state_file)
        return False

    # ----- Minute reporting ---------------------------------------------------

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
            self.log_check(now, "BUY_TIME_REACHED", now >= session.open_action, scheduled=session.open_action.strftime("%H:%M:%S"))
            self.log.info("CONDITION_REPORT_END minute=%s checks=3", now.strftime("%Y-%m-%d %H:%M"))
            return

        entry = float(position.price_open)
        self.log_check(now, "POSITION_IS_OPEN", True, ticket=position.ticket, entry=entry, volume=position.volume)
        self.log_check(now, "ENTRY_SIGNAL_OPEN_AVAILABLE", self.state.entry_signal_daily_open > 0 and not self.state.entry_signal_open_pending, signal_open=self.state.entry_signal_daily_open, pending=self.state.entry_signal_open_pending)
        self.log_check(now, "EXIT_LATCH_CLEAR", not bool(self.state.exit_latched_reason), exit_latch=self.state.exit_latched_reason or "none")

        check_count = 3
        if self.oh_check_pending(now):
            try:
                tick = self.require_fresh_tick(position.symbol)
                bid = float(tick.bid)
                tpp = self.cfg.tpps[now.weekday() if now.weekday() < 5 else 4]
                self.log_check(now, "OH", bid > entry * (1.0 + tpp), bid=bid, threshold=entry * (1.0 + tpp))
            except RuntimeError as exc:
                self.log_check(now, "OH", False, error=str(exc))
            check_count += 1

        desired_sl, sl_reason = self.weekday_sl_target(position, now)
        info = mt5.symbol_info(position.symbol)
        tick_size = float(getattr(info, "trade_tick_size", 0.0) or getattr(info, "point", 0.0) or 0.01) if info is not None else 0.01
        desired_sl = floor_step(desired_sl, tick_size)
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
            self.log_minute_condition_report(position, now, current_bar)

        if position is None:
            self.record_strategy_decision_if_changed()
        signature = self.status_signature(position, now)
        if signature != self.last_meaningful_signature:
            self.last_meaningful_signature = signature
            self.emit_status("STATUS_CHANGE", position, now, current_bar)

    # ----- Startup and loop ---------------------------------------------------

    def startup_reconcile(self) -> None:
        if not self.is_executor:
            raise RuntimeError("startup_reconcile is executor-only")
        now = datetime.now(self.tz)
        position = self.managed_position()
        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()
        elif position is not None:
            self.recover_position_state(position, now, force=True)
            self.apply_standard_protection(position, now)
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.emit_status("STARTUP", position, now, current_bar)
        self.print_instance_banner(now)
        self.print_autotrading_banner(now)
        self.last_minute_status = now.strftime("%Y-%m-%d %H:%M")
        self.last_meaningful_signature = self.status_signature(position, now)
        if position is None:
            self.record_strategy_decision_if_changed(force=True)
        self.publish_mobile_minute_status(position, now, current_bar, force=True)

    def cycle(self) -> None:
        if not self.is_executor:
            raise RuntimeError("cycle is executor-only")
        now = datetime.now(self.tz)
        self.ensure_autotrading_enabled("CYCLE")
        self.log_week_plan(now.date())
        position = self.managed_position()

        if position is None and self.state.active_position_identifier:
            self.finalize_closed_position()
        elif position is not None and self.recover_position_state(position, now):
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
        if position is None:
            self.record_strategy_decision_if_changed()
        self.log_status_if_needed(position, now, current_bar)
        minute_published = self.publish_mobile_minute_status(position, now, current_bar)
        if not minute_published:
            self.publish_mobile_if_due(position, now, current_bar)

    def reload_state_read_only(self) -> None:
        try:
            self.state = StrategyState.load(self.cfg.state_file)
        except Exception as exc:
            self.log.warning("EVENT PUBLISHER_STATE_READ_FAILED path=%s error=%s", self.cfg.state_file, exc)

    def publisher_startup(self) -> None:
        if not self.monitor_publisher.ready:
            raise RuntimeError("Publisher mode requires valid monitor configuration")
        self.publisher_presence.touch(force=True)
        self.reload_state_read_only()
        now = datetime.now(self.tz)
        position = self.managed_position()
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        self.emit_status("PUBLISHER_STARTUP", position, now, current_bar)
        self.print_instance_banner(now)
        self.last_minute_status = now.strftime("%Y-%m-%d %H:%M")
        self.last_meaningful_signature = self.status_signature(position, now)
        if position is None:
            self.record_strategy_decision_if_changed(force=True)
        self.publish_mobile_minute_status(position, now, current_bar, force=True)

    def publisher_cycle(self) -> None:
        self.publisher_presence.touch()
        self.reload_state_read_only()
        now = datetime.now(self.tz)
        position = self.managed_position()
        current_bar = self.current_m1_bar(self.cfg.trade_symbol)
        minute_key = now.strftime("%Y-%m-%d %H:%M")
        if minute_key != self.last_minute_status:
            self.last_minute_status = minute_key
            self.emit_status("PUBLISHER_MINUTE", position, now, current_bar)
            self.print_instance_banner(now)
        signature = self.status_signature(position, now)
        if signature != self.last_meaningful_signature:
            self.last_meaningful_signature = signature
            self.emit_status("PUBLISHER_STATUS_CHANGE", position, now, current_bar)
        minute_published = self.publish_mobile_minute_status(position, now, current_bar)
        if not minute_published:
            self.publish_mobile_if_due(position, now, current_bar)

    def run_executor(self) -> None:
        self.connect()
        self.startup_reconcile()
        while self.running:
            try:
                if not self.connection_healthy():
                    self.log.error("EVENT CONNECTION_LOST role=EXECUTOR reconnecting=true")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.connect()
                    self.startup_reconcile()
                self.cycle()
            except KeyboardInterrupt:
                self.running = False
            except Exception:
                self.log.exception("EVENT STRATEGY_CYCLE_FAILED role=EXECUTOR")
            time_module.sleep(self.cfg.poll_seconds)
        self.log.info("EVENT STRATEGY_STOPPED role=EXECUTOR")

    def run_publisher(self) -> None:
        self.publisher_presence.touch(force=True)
        self.connect()
        self.publisher_startup()
        while self.running:
            try:
                self.publisher_presence.touch()
                if not self.connection_healthy():
                    self.log.error("EVENT CONNECTION_LOST role=PUBLISHER reconnecting=true")
                    self.disconnect()
                    time_module.sleep(self.cfg.reconnect_seconds)
                    self.publisher_presence.touch(force=True)
                    self.connect()
                    self.publisher_startup()
                self.publisher_cycle()
            except KeyboardInterrupt:
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


# -----------------------------------------------------------------------------
# Entrypoint
# -----------------------------------------------------------------------------


def parse_arguments(argv: Optional[list[str]] = None) -> argparse.Namespace:
    default_mode = os.getenv("OPPW_INSTANCE_MODE", INSTANCE_MODE_EXECUTOR).strip().upper() or INSTANCE_MODE_EXECUTOR
    if default_mode not in {INSTANCE_MODE_EXECUTOR, INSTANCE_MODE_PUBLISHER}:
        default_mode = INSTANCE_MODE_EXECUTOR
    default_account = os.getenv("OPPW_ACCOUNT", ACCOUNT_DEMO).strip().upper() or ACCOUNT_DEMO
    if default_account not in {ACCOUNT_DEMO, ACCOUNT_REAL}:
        default_account = ACCOUNT_DEMO
    parser = argparse.ArgumentParser(description="OPPW MT5 continuous strategy")
    parser.add_argument(
        "--mode",
        choices=(INSTANCE_MODE_EXECUTOR.lower(), INSTANCE_MODE_PUBLISHER.lower()),
        default=default_mode.lower(),
        help="executor may trade and publishes only when no publisher exists; publisher is read-only and handles backend publishing",
    )
    parser.add_argument(
        "--account",
        choices=(ACCOUNT_DEMO.lower(), ACCOUNT_REAL.lower()),
        default=default_account.lower(),
        help="demo loads oppw-mt5-config.py; real loads real-mt5-config.py",
    )
    return parser.parse_args(argv)


def legacy_live_pid(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8").strip()
        if not text or not text.lstrip("-").isdigit():
            return 0
        pid = int(text)
        return pid if InterProcessFileLock.pid_is_running(pid) else 0
    except OSError:
        return 0




def ensure_unscoped_instances_stopped(original_config, scoped_config) -> None:
    if not hasattr(original_config, "lock_file") or not hasattr(scoped_config, "lock_file"):
        return
    original_lock = Path(original_config.lock_file)
    scoped_lock = Path(scoped_config.lock_file)
    if original_lock == scoped_lock:
        return

    old_pid = legacy_live_pid(original_lock)
    if old_pid:
        raise RuntimeError(f"Legacy OPPW instance PID {old_pid} is still running with lock {original_lock}")

    legacy_paths = (original_lock, derived_coordination_path(original_lock, "publisher"))
    for path in legacy_paths:
        probe = InterProcessFileLock(path, {"purpose": "v40-legacy-instance-probe"})
        if not probe.try_acquire():
            owner = "unknown"
            try:
                owner = path.read_text(encoding="utf-8", errors="replace")[:500]
            except OSError:
                pass
            raise RuntimeError(f"A v39 or older instance is still running with lock {path}: {owner}")
        probe.release()

def main() -> int:
    args = parse_arguments()
    role = str(args.mode).upper()
    account = str(args.account).upper()
    original_cfg, config_path = load_account_config(account)
    cfg = scope_config_to_account(original_cfg, account)
    ensure_unscoped_instances_stopped(original_cfg, cfg)
    migrate_legacy_demo_runtime_files(original_cfg, cfg, account)

    old_pid = legacy_live_pid(cfg.lock_file)
    if old_pid:
        print(
            f"FATAL: legacy OPPW instance PID {old_pid} is still running. Stop all v39/older instances before starting v40 roles.",
            file=sys.stderr,
        )
        return 1

    publisher_lock_path = derived_coordination_path(cfg.lock_file, "publisher")
    role_lock_path = cfg.lock_file if role == INSTANCE_MODE_EXECUTOR else publisher_lock_path
    heartbeat_path = cfg.lock_file.with_name(f"{cfg.lock_file.stem}.publisher.heartbeat.json")
    publish_lock_path = derived_coordination_path(cfg.lock_file, "backend-publish")
    event_spool_path = cfg.monitor_history_file.with_name(f"{cfg.monitor_history_file.stem}.events.jsonl")

    role_lock = InterProcessFileLock(role_lock_path, {"role": role, "account": account, "config": str(config_path), "build": BUILD_ID})
    publisher_presence = PublisherPresence(heartbeat_path, role)
    event_spool = SharedEventSpool(event_spool_path, cfg.monitor_event_buffer_size)
    strategy: Optional[OPPWContinuousStrategy] = None

    try:
        role_lock.acquire()
        strategy = OPPWContinuousStrategy(cfg, role, account, publisher_presence, event_spool, publish_lock_path)
        if role == INSTANCE_MODE_PUBLISHER and not strategy.monitor_publisher.ready:
            raise RuntimeError("Publisher mode cannot start because backend monitor publishing is not configured")
        signal.signal(signal.SIGINT, strategy.stop)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, strategy.stop)
        strategy.run()
        return 0
    except Exception:
        if strategy is not None:
            strategy.log.exception("EVENT FATAL_STARTUP_FAILURE role=%s account=%s", role, account)
        else:
            logging.basicConfig(level=logging.ERROR)
            logging.exception("FATAL_STARTUP_FAILURE role=%s account=%s", role, account)
        return 1
    finally:
        if strategy is not None:
            strategy.shutdown_mobile_publisher()
            strategy.disconnect()
        publisher_presence.remove_if_owner()
        role_lock.release()


if __name__ == "__main__":
    sys.exit(main())