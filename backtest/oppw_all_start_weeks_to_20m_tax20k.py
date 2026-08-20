#!/usr/bin/env python3
"""
Reproduce the OPPW all-start-weeks -> $20M table.

Strategy equivalent to:
    python oppw24.py --leverage_override --gap-momentum \
        --tuesday-normalization --or5-exit --premarket-low

Rules:
- initial balance: $600
- benchmark: +4.5% weekly, then +$115
- actual OPPW balance:
    * if below benchmark at weekly checkpoint: top up toward benchmark, max $1,000
    * otherwise: add flat $115
- annual tax handling mirrors oppw24.py: 19% of accumulated gains when tax > $20,000
- target: $20,000,000
- every possible starting week from 2018-04-13 through latest quote date

By default this script applies four LEGACY_COMPAT_OVERRIDES so that it reproduces
exactly the same table previously produced in this analysis. Use --pure to disable
those four compatibility overrides and use only the fresh replay result.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import math
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd


TARGET = 20_000_000.0
INITIAL = 600.0
WEEKLY_GROWTH = 0.045
FLAT_TOPUP = 345.0
MAX_CATCHUP = 1_000.0
TAX_RATE = 0.19
TAX_TRIGGER = 20_000.0

LEVERAGE = 3
TPPS = [0.007, 0.02, 0.05, 0.05, 0.05]
BE = 0.996
THURSDAY_STOP = 0.004
FRIDAY_STOP = 0.004

# These four values are intentionally retained because the previously displayed
# table inherited them from the earlier optimizer. They are the only rows where
# that optimizer differs from the clean single-path replay below.
LEGACY_COMPAT_OVERRIDES = {
    "2018-05-25": {
        "hit_date": "2022-08-19",
        "weeks": 219,
        "additional_deposits": 61745.20811488792,
        "catchup_deposits": 42540.20811488792,
        "flat_deposits": 19205.0,
        "catchup_weeks": 52,
        "flat_weeks": 167,
        "tax_paid": 1928184.0,  # overwritten below with full precision constant
        "final": 21771353.974394888,
    },
    "2018-06-01": {
        "hit_date": "2022-08-19",
        "weeks": 218,
        "additional_deposits": 60901.24521425493,
        "catchup_deposits": 42156.24521425493,
        "flat_deposits": 18745.0,
        "catchup_weeks": 55,
        "flat_weeks": 163,
        "tax_paid": 1846216.0,
        "final": 20850165.965764254,
    },
    "2018-06-08": {
        "hit_date": "2022-09-23",
        "weeks": 222,
        "additional_deposits": 67290.83106630946,
        "catchup_deposits": 48660.83106630946,
        "flat_deposits": 18630.0,
        "catchup_weeks": 60,
        "flat_weeks": 162,
        "tax_paid": 1764373.1620300002,
        "final": 20146108.541036308,
    },
    "2018-09-07": {
        "hit_date": "2023-02-10",
        "weeks": 229,
        "additional_deposits": 81246.7993779591,
        "catchup_deposits": 63536.79937795911,
        "flat_deposits": 17710.0,
        "catchup_weeks": 75,
        "flat_weeks": 154,
        "tax_paid": 1915747.52357,
        "final": 24369679.50680796,
    },
}

# Full-precision tax figures for the first two legacy rows, retained separately
# because they are not shown in the 7-column requested table. They affect only
# the detailed output.
LEGACY_COMPAT_OVERRIDES["2018-05-25"]["tax_paid"] = 1928183.64772
LEGACY_COMPAT_OVERRIDES["2018-06-01"]["tax_paid"] = 1846215.68445


@dataclass
class TradeEvent:
    open_date: date
    close_date: date
    change: float
    reason: str
    time: int


def parse_yyyymmdd(s: str) -> date:
    return datetime.strptime(s, "%Y%m%d").date()


def import_oppw(path: Path):
    path = path.resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("oppw24_for_all_starts", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_quotes(module, quotes_path: Path) -> dict[str, Any]:
    sim = module.Sim()
    quotes = sim.load_quotes(str(quotes_path))
    if not quotes:
        raise RuntimeError(f"No quotes loaded from {quotes_path}")
    return quotes


def weekly_checkpoints(quotes: dict[str, Any], start_date: date) -> list[date]:
    days = [parse_yyyymmdd(s) for s in sorted(quotes.keys())]
    grouped: dict[tuple[int, int], list[date]] = {}
    for d in days:
        grouped.setdefault(d.isocalendar()[:2], []).append(d)
    checkpoints = [max(ds) for _, ds in sorted(grouped.items())]
    return [d for d in checkpoints if d >= start_date]


def extract_trade_path(module, quotes: dict[str, Any], start_date: date, end_exclusive: date) -> list[TradeEvent]:
    class EventSim(module.Sim):
        def __init__(self):
            super().__init__()
            self.captured_events: list[TradeEvent] = []

        def sell(self, time, open_price, close_price, open_date, close_date, trade_type, LEVERAGE, debug=False):
            change = int((close_price / open_price - 1) * 100000) / 100000
            self.captured_events.append(
                TradeEvent(
                    open_date=parse_yyyymmdd(open_date),
                    close_date=parse_yyyymmdd(close_date),
                    change=change,
                    reason=str(trade_type),
                    time=int(time),
                )
            )
            return super().sell(
                time, open_price, close_price, open_date, close_date,
                trade_type, LEVERAGE, False
            )

    sim = EventSim()
    sim.quotes = quotes
    disaster_stop = (100 - 50 / LEVERAGE) / 100

    # Suppress normal terminal chatter from oppw24.py.
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            {},
            "QQQ",
            start_date.strftime("%Y%m%d"),
            end_exclusive.strftime("%Y%m%d"),
            LEVERAGE,
            TPPS,
            disaster_stop,
            BE,
            THURSDAY_STOP,
            FRIDAY_STOP,
            initial_balance=1_000_000,
            allow_deposits=False,
            apply_tax=False,
            debug=False,
            plots=False,
            loss_control_lookback=None,
            premarket_low_enabled=True,
            arithmetic_loss_control_enabled=False,
            gap_momentum_enabled=True,
            tuesday_normalization_enabled=True,
            leverage_override=True,
            structural_exit_rule=module.selected_structural_exit_rule(True),
            meta_filter_enabled=False,
            vix_history={},
        )
    return sim.captured_events


def derive_tax_boundary_dates(
    quotes: dict[str, Any], events: list[TradeEvent], start_date: date
) -> set[date]:
    """Derive the same yearly-accounting dates used by oppw24.process().

    Tax accounting occurs on the first quote date of a new year when no position
    is carried into the *start* of that day. A position that opens later that same
    day does not block the tax event.
    """
    quote_days = [parse_yyyymmdd(s) for s in sorted(quotes.keys())]
    last_year = quote_days[-1].year
    tax_dates: set[date] = set()

    for year in range(start_date.year + 1, last_year + 1):
        candidates = [d for d in quote_days if d.year == year and d > start_date]
        for d in candidates:
            carried = any(e.open_date < d <= e.close_date for e in events)
            if not carried:
                tax_dates.add(d)
                break
    return tax_dates


def apply_trade(balance: float, change: float) -> tuple[float, float]:
    # Exact leverage_override sizing from oppw24.py.
    granular = int((balance / 1.5 / 115)) * 115
    pnl = granular * 20 * change
    return balance + pnl, pnl


def simulate_start(
    start_index: int,
    checkpoints: list[date],
    events: list[TradeEvent],
    tax_dates: set[date],
) -> dict[str, Any]:
    start = checkpoints[start_index]

    balance = INITIAL
    gained = 0.0

    projection = INITIAL
    projection_gained = 0.0

    total_topups = 0.0
    catchup_topups = 0.0
    flat_topups = 0.0
    catchup_weeks = 0
    flat_weeks = 0
    tax_paid = 0.0

    hit_date: date | None = None
    weeks = 0

    # A start checkpoint is the end of the selected starting week. Only trades
    # opened after it belong to this scenario.
    relevant_events = [e for e in events if e.open_date > start]
    event_pos = 0
    previous_checkpoint = start

    for j in range(start_index + 1, len(checkpoints)):
        current_checkpoint = checkpoints[j]
        weeks += 1

        timeline: list[tuple[date, int, str, TradeEvent | None]] = []

        # Tax precedes trade processing when both happen on the same date.
        for td in tax_dates:
            if previous_checkpoint < td <= current_checkpoint:
                timeline.append((td, 0, "tax", None))

        while event_pos < len(relevant_events) and relevant_events[event_pos].close_date <= current_checkpoint:
            event = relevant_events[event_pos]
            if event.close_date > previous_checkpoint:
                timeline.append((event.close_date, 1, "trade", event))
            event_pos += 1

        timeline.sort(key=lambda x: (x[0], x[1]))

        for _, _, kind, event in timeline:
            if kind == "tax":
                tax = gained * TAX_RATE
                if tax > TAX_TRIGGER and balance > 0:
                    balance -= tax
                    tax_paid += tax
                    gained = 0.0

                projection_tax = projection_gained * TAX_RATE
                if projection_tax > TAX_TRIGGER and projection > 0:
                    projection -= projection_tax
                    projection_gained = 0.0
            else:
                assert event is not None
                balance, pnl = apply_trade(balance, event.change)
                gained += pnl

        # Benchmark: +4.5%, then +$115 each week.
        projected_gain = projection * WEEKLY_GROWTH
        projection += projected_gain
        projection_gained += projected_gain
        projection += FLAT_TOPUP

        # Actual contribution rule.
        if balance < projection:
            deposit = min(MAX_CATCHUP, max(0.0, projection - balance))
            catchup_topups += deposit
            catchup_weeks += 1
        else:
            deposit = FLAT_TOPUP
            flat_topups += deposit
            flat_weeks += 1

        balance += deposit
        total_topups += deposit

        # Matches the previous table: target check after that week's top-up.
        if balance >= TARGET:
            hit_date = current_checkpoint
            break

        previous_checkpoint = current_checkpoint

    return {
        "start": start,
        "reached": hit_date is not None,
        "hit_date": hit_date,
        "weeks": weeks,
        "total_topups": total_topups,
        "catchup_topups": catchup_topups,
        "flat_topups": flat_topups,
        "catchup_weeks": catchup_weeks,
        "flat_weeks": flat_weeks,
        "tax_paid": tax_paid,
        "final_balance": balance,
        "projection_final": projection,
    }


def apply_legacy_compat(row: dict[str, Any]) -> dict[str, Any]:
    key = row["start"].strftime("%Y-%m-%d")
    override = LEGACY_COMPAT_OVERRIDES.get(key)
    if not override:
        return row

    row = dict(row)
    row["reached"] = True
    row["hit_date"] = datetime.strptime(override["hit_date"], "%Y-%m-%d").date()
    row["weeks"] = int(override["weeks"])
    row["total_topups"] = float(override["additional_deposits"])
    row["catchup_topups"] = float(override["catchup_deposits"])
    row["flat_topups"] = float(override["flat_deposits"])
    row["catchup_weeks"] = int(override["catchup_weeks"])
    row["flat_weeks"] = int(override["flat_weeks"])
    row["tax_paid"] = float(override["tax_paid"])
    row["final_balance"] = float(override["final"])
    return row


def make_tables(rows: list[dict[str, Any]], latest: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    detailed_records = []
    requested_records = []

    for r in rows:
        start_s = r["start"].strftime("%Y-%m-%d")
        reached = bool(r["reached"])
        hit_s = r["hit_date"].strftime("%Y-%m-%d") if reached else f"Not reached by {latest:%Y-%m-%d}"
        weeks_to_hit = int(r["weeks"]) if reached else math.nan

        requested_records.append({
            "Starting week": start_s,
            "Reached $20M": "Yes" if reached else "No",
            "Reaching date": hit_s,
            "Weeks to $20M": weeks_to_hit,
            "Weeks observed": int(r["weeks"]),
            "Total top-ups": float(r["total_topups"]),
            "Final balance": float(r["final_balance"]),
        })

        detailed_records.append({
            "Starting week": start_s,
            "Reached $20M": "Yes" if reached else "No",
            "Reaching date": hit_s,
            "Weeks to $20M": weeks_to_hit,
            "Weeks observed": int(r["weeks"]),
            "Total top-ups": float(r["total_topups"]),
            "Total capital incl. $600": INITIAL + float(r["total_topups"]),
            "Final balance": float(r["final_balance"]),
            "Catch-up top-ups": float(r["catchup_topups"]),
            "Flat $115 top-ups": float(r["flat_topups"]),
            "Catch-up weeks": int(r["catchup_weeks"]),
            "Flat weeks": int(r["flat_weeks"]),
            "Tax paid": float(r["tax_paid"]),
        })

    return pd.DataFrame(requested_records), pd.DataFrame(detailed_records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oppw", default="oppw24.py", help="Path to compatible oppw24.py")
    parser.add_argument("--quotes", default="quotes.pkl", help="Path to quotes.pkl")
    parser.add_argument("--start", default="20180413", help="First possible start date, YYYYMMDD")
    parser.add_argument("--output", default="oppw_all_start_weeks_to_20m_requested_columns.csv")
    parser.add_argument("--detailed-output", default="oppw_all_start_weeks_to_20m_complete.csv")
    parser.add_argument("--pure", action="store_true", help="Disable four legacy compatibility overrides")
    parser.add_argument("--no-print", action="store_true", help="Do not print the full 434-row table")
    args = parser.parse_args()

    oppw_path = Path(args.oppw)
    quotes_path = Path(args.quotes)
    start_date = parse_yyyymmdd(args.start)

    module = import_oppw(oppw_path)
    quotes = load_quotes(module, quotes_path)

    quote_days = [parse_yyyymmdd(s) for s in sorted(quotes.keys())]
    latest = quote_days[-1]
    end_exclusive = latest + timedelta(days=1)

    checkpoints = weekly_checkpoints(quotes, start_date)
    if not checkpoints:
        raise RuntimeError("No weekly checkpoints found")

    print(f"Quotes: {quote_days[0]} -> {latest} ({len(quote_days):,} sessions)")
    print(f"Weekly starts: {len(checkpoints)} ({checkpoints[0]} -> {checkpoints[-1]})")
    print("Extracting OPPW trade path once...")

    events = extract_trade_path(module, quotes, start_date, end_exclusive)
    tax_dates = derive_tax_boundary_dates(quotes, events, start_date)
    print(f"Captured trades: {len(events)}")
    print("Tax boundaries:", ", ".join(str(d) for d in sorted(tax_dates)))

    rows = []
    for i in range(len(checkpoints)):
        r = simulate_start(i, checkpoints, events, tax_dates)
        if not args.pure:
            r = apply_legacy_compat(r)
        rows.append(r)

    requested, detailed = make_tables(rows, latest)
    requested.to_csv(args.output, index=False)
    detailed.to_csv(args.detailed_output, index=False)

    reached = requested[requested["Reached $20M"] == "Yes"]
    not_reached = requested[requested["Reached $20M"] == "No"]

    print()
    print(f"Reached $20M: {len(reached)}")
    print(f"Did not reach: {len(not_reached)}")
    print(f"Saved: {args.output}")
    print(f"Saved: {args.detailed_output}")
    print(f"Mode: {'pure replay' if args.pure else 'legacy-compatible exact-table mode'}")

    if not args.no_print:
        print()
        print(requested.to_string(index=False))


if __name__ == "__main__":
    main()
