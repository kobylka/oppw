"""Pure numerical and calendar-key helpers shared by strategy modules."""

from __future__ import annotations

import math
from datetime import date
from typing import Optional

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


def ceil_whole_sl(value: float) -> float:
    """Normalize every positive SL upward to the next whole index point."""
    return 0.0 if value <= 0 else float(math.ceil(value - 1e-9))


def price_changed(current: float, desired: float, tolerance: float) -> bool:
    if current == 0.0 and desired == 0.0:
        return False
    return abs(current - desired) >= tolerance
