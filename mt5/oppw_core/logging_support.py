"""Terminal and per-week logging infrastructure."""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from .versioning import INSTANCE_MODE_EXECUTOR

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
