#!/usr/bin/env python3
"""
Generate an idempotent MySQL import file containing OPPW weekly trades
calculated by the existing oppw24.py Sim.process implementation.

Place this script beside oppw24.py and quotes.pkl, then run:

    py export_oppw24_mysql.py

The default range is inclusive: 2026-01-05 through 2026-07-16.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")
UTC = timezone.utc
FIRST_MINUTE_INDEX = 4
CASH_OPEN_INDEX = 934
LAST_SESSION_INDEX = 1324
DEFAULT_TPPS = (0.007, 0.020, 0.050, 0.050, 0.050)


@dataclass(frozen=True)
class CapturedTrade:
    ticket: int
    open_date: str
    close_date: str
    close_index: int
    open_price: float
    close_price: float
    exit_reason: str
    leverage: float
    volume: float
    change: float
    profit: float
    balance_before: float
    balance_after: float
    best_price: float
    worst_price: float
    mfe_points: float
    mae_points: float
    opened_at_utc: datetime
    closed_at_utc: datetime


def parse_ymd(value: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD and return YYYYMMDD."""
    compact = value.replace("-", "")
    try:
        parsed = datetime.strptime(compact, "%Y%m%d")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Invalid date {value!r}; use YYYY-MM-DD.") from exc
    return parsed.strftime("%Y%m%d")


def add_days(date_key: str, days: int) -> str:
    return (datetime.strptime(date_key, "%Y%m%d") + timedelta(days=days)).strftime("%Y%m%d")


def date_diff(first: str, second: str) -> int:
    return (datetime.strptime(second, "%Y%m%d") - datetime.strptime(first, "%Y%m%d")).days


def bar_datetime_utc(date_key: str, bar_index: int) -> datetime:
    if bar_index < FIRST_MINUTE_INDEX:
        raise ValueError(f"Minute bar index must be >= {FIRST_MINUTE_INDEX}, got {bar_index}.")
    local_midnight = datetime.strptime(date_key, "%Y%m%d").replace(tzinfo=WARSAW)
    local_time = local_midnight + timedelta(minutes=bar_index - FIRST_MINUTE_INDEX)
    return local_time.astimezone(UTC).replace(tzinfo=None)


def load_module(path: Path) -> ModuleType:
    if not path.is_file():
        raise FileNotFoundError(f"oppw24.py not found: {path}")
    spec = importlib.util.spec_from_file_location("oppw24_export_source", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load Python module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not hasattr(module, "Sim"):
        raise RuntimeError(f"{path} does not define Sim.")
    return module


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def sql_number(value: float, decimals: int) -> str:
    if not math.isfinite(value):
        raise ValueError(f"Cannot write non-finite SQL number: {value}")
    rounded = f"{value:.{decimals}f}"
    if "." in rounded:
        rounded = rounded.rstrip("0").rstrip(".")
    return rounded if rounded not in ("", "-0") else "0"


def sql_datetime(value: datetime, milliseconds: bool = True) -> str:
    fmt = "%Y-%m-%d %H:%M:%S.%f" if milliseconds else "%Y-%m-%d %H:%M:%S"
    text = value.strftime(fmt)
    if milliseconds:
        text = text[:-3]
    return sql_string(text)


def parse_tpps(value: str) -> tuple[float, ...]:
    try:
        result = tuple(float(part.strip()) for part in value.split(",") if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("TPPs must be comma-separated numbers.") from exc
    if len(result) < 2:
        raise argparse.ArgumentTypeError("At least two TPP values are required.")
    if any(item < 0 for item in result):
        raise argparse.ArgumentTypeError("TPPs cannot be negative.")
    return result


def expected_entry_dates(quotes: dict[str, Any], source_stock: str, start: str, end_inclusive: str) -> list[str]:
    entries: list[str] = []
    prev_date = "20000101"
    for date_key in sorted(quotes):
        if date_key < start:
            continue
        if date_key > end_inclusive:
            break
        date_obj = datetime.strptime(date_key, "%Y%m%d").date()
        if date_obj.weekday() > 4 or source_stock not in quotes[date_key]:
            continue
        if date_diff(prev_date, date_key) > 1 and date_obj.weekday() in (0, 1):
            entries.append(date_key)
        prev_date = date_key
    return entries


def make_exporting_sim(module: ModuleType, source_stock: str, ticket_base: int):
    class ExportingSim(module.Sim):  # type: ignore[misc, valid-type]
        def __init__(self) -> None:
            super().__init__()
            self.captured_trades: list[CapturedTrade] = []
            self._source_stock = source_stock
            self._ticket_base = ticket_base
            self._ticket_sequence_by_date: dict[str, int] = {}

        def _next_ticket(self, open_date: str) -> int:
            sequence = self._ticket_sequence_by_date.get(open_date, 0)
            self._ticket_sequence_by_date[open_date] = sequence + 1
            return self._ticket_base + int(open_date) * 100 + sequence

        def _extrema(self, open_date: str, close_date: str, close_index: int, open_price: float, close_price: float, exit_reason: str) -> tuple[float, float]:
            best = max(open_price, close_price)
            worst = min(open_price, close_price)
            close_based_exit = exit_reason.upper() in {"CH", "TO", "TSL0"}
            for date_key in sorted(self.quotes):
                if date_key < open_date:
                    continue
                if date_key > close_date:
                    break
                day = self.quotes.get(date_key, {})
                bars = day.get(self._source_stock) if isinstance(day, dict) else None
                if not isinstance(bars, (list, tuple)):
                    continue
                first = CASH_OPEN_INDEX if date_key == open_date else FIRST_MINUTE_INDEX
                if date_key == close_date:
                    last = close_index if close_based_exit else close_index - 1
                else:
                    last = min(LAST_SESSION_INDEX, len(bars) - 1)
                if last < first:
                    continue
                for index in range(first, last + 1):
                    if index >= len(bars):
                        break
                    bar = bars[index]
                    if not isinstance(bar, (list, tuple)) or len(bar) < 4:
                        continue
                    high = float(bar[1])
                    low = float(bar[2])
                    if math.isfinite(high):
                        best = max(best, high)
                    if math.isfinite(low):
                        worst = min(worst, low)
            return best, worst

        def sell(self, time, open_price, close_price, open_date, close_date, trade_type, LEVERAGE, debug=False):
            close_index = int(time)
            open_price_f = float(open_price)
            close_price_f = float(close_price)
            leverage_f = float(LEVERAGE)
            balance_before = float(self.balance)

            # This exactly mirrors oppw24.py: truncate toward zero to four decimals.
            change = math.trunc((close_price_f / open_price_f - 1.0) * 10000.0) / 10000.0
            granular = int(balance_before / (20.0 / leverage_f) / 2240.0) * 2240
            volume = granular / 2240.0 * 0.01
            profit = granular * 20.0 * change
            exit_reason = str(trade_type or "MANUAL")[:100]
            best_price, worst_price = self._extrema(open_date, close_date, close_index, open_price_f, close_price_f, exit_reason)

            super().sell(time, open_price, close_price, open_date, close_date, trade_type, LEVERAGE, debug)
            balance_after = float(self.balance)

            if abs(balance_after - (balance_before + profit)) > 0.011:
                raise RuntimeError(
                    f"Captured P/L does not match oppw24.py for {open_date}: "
                    f"expected {balance_before + profit:.4f}, got {balance_after:.4f}."
                )
            if volume <= 0:
                raise RuntimeError(f"oppw24.py produced zero volume for the trade opened {open_date}.")

            mfe_points = max(0.0, best_price - open_price_f)
            mae_points = max(0.0, open_price_f - worst_price)
            self.captured_trades.append(
                CapturedTrade(
                    ticket=self._next_ticket(open_date),
                    open_date=open_date,
                    close_date=close_date,
                    close_index=close_index,
                    open_price=open_price_f,
                    close_price=close_price_f,
                    exit_reason=exit_reason,
                    leverage=leverage_f,
                    volume=volume,
                    change=change,
                    profit=profit,
                    balance_before=balance_before,
                    balance_after=balance_after,
                    best_price=best_price,
                    worst_price=worst_price,
                    mfe_points=mfe_points,
                    mae_points=mae_points,
                    opened_at_utc=bar_datetime_utc(open_date, CASH_OPEN_INDEX),
                    closed_at_utc=bar_datetime_utc(close_date, close_index),
                )
            )

    return ExportingSim


def trade_row(trade: CapturedTrade, account: str, db_symbol: str) -> str:
    mfe_percent = trade.mfe_points / trade.open_price * 100.0
    mae_percent = -trade.mae_points / trade.open_price * 100.0
    return "(" + ", ".join(
        [
            sql_string(account),
            str(trade.ticket),
            sql_string(db_symbol),
            "'BUY'",
            sql_number(trade.volume, 8),
            sql_datetime(trade.opened_at_utc),
            sql_datetime(trade.closed_at_utc),
            sql_number(trade.open_price, 8),
            "NULL",
            "NULL",
            "NULL",
            sql_number(trade.close_price, 8),
            "NULL",
            "NULL",
            "NULL",
            sql_number(trade.profit, 4),
            sql_number(trade.change * 100.0, 6),
            sql_number(trade.best_price, 8),
            sql_number(trade.worst_price, 8),
            sql_number(trade.mfe_points, 8),
            sql_number(mfe_percent, 6),
            sql_number(-trade.mae_points, 8),
            sql_number(mae_percent, 6),
            sql_number(max(0.0, trade.profit), 4),
            sql_number(min(0.0, trade.profit), 4),
            sql_string(trade.exit_reason),
            sql_number(trade.balance_before, 4),
            sql_number(trade.balance_after, 4),
        ]
    ) + ")"


def build_sql(trades: list[CapturedTrade], account: str, db_symbol: str, database: str, initial_balance: float, source_name: str, start: str, end_inclusive: str) -> str:
    if not trades:
        raise RuntimeError("No closed trades were produced for the requested range.")

    first_open = min(trade.opened_at_utc for trade in trades)
    lines = [
        "-- Generated by export_oppw24_mysql.py",
        f"-- Source strategy: {source_name}",
        f"-- Requested inclusive range: {start[:4]}-{start[4:6]}-{start[6:]} through {end_inclusive[:4]}-{end_inclusive[4:6]}-{end_inclusive[6:]}",
        "-- Times are UTC, matching Mobile/backend/trade-admin.php storage.",
        "-- Run migrate_v12_trade_classes.sql first; its triggers fill preleverage_return_percent and trade_class.",
        "",
        "SET NAMES utf8mb4;",
        "SET time_zone = '+00:00';",
        f"USE `{database.replace('`', '``')}`;",
        "START TRANSACTION;",
        "",
        "-- Match trade-admin.php initial-balance behavior.",
        "UPDATE account_cash_flows",
        "SET occurred_at = " + sql_datetime(first_open) + ",",
        "    amount = " + sql_number(initial_balance, 4) + ",",
        "    balance_after = " + sql_number(initial_balance, 4) + ",",
        "    source = 'MANUAL_API',",
        "    note = 'Initial balance moved earlier by historical trade import'",
        "WHERE strategy_key = " + sql_string(account),
        "  AND flow_type = 'INITIAL'",
        "  AND occurred_at > " + sql_datetime(first_open),
        "ORDER BY occurred_at",
        "LIMIT 1;",
        "",
        "INSERT INTO account_cash_flows(strategy_key, occurred_at, flow_type, amount, balance_after, source, reference_key, note)",
        "SELECT " + ", ".join(
            [
                sql_string(account),
                sql_datetime(first_open),
                "'INITIAL'",
                sql_number(initial_balance, 4),
                sql_number(initial_balance, 4),
                "'MANUAL_API'",
                sql_string("manual-initial:" + account),
                "'Initial balance supplied with historical trade import'",
            ]
        ),
        "WHERE NOT EXISTS (",
        "    SELECT 1 FROM account_cash_flows",
        "    WHERE strategy_key = " + sql_string(account) + " AND flow_type = 'INITIAL'",
        ");",
        "",
        "INSERT INTO strategy_trades(",
        "    strategy_key, position_ticket, symbol, side, volume, opened_at, closed_at, open_price,",
        "    entry_reference_price, entry_slippage_points, entry_slippage_percent, close_price,",
        "    exit_reference_price, exit_slippage_points, exit_slippage_percent, profit, profit_percent,",
        "    best_price, worst_price, mfe_points, mfe_percent, mae_points, mae_percent,",
        "    max_profit, max_drawdown, exit_reason, balance_before, balance_after",
        ") VALUES",
        ",\n".join(trade_row(trade, account, db_symbol) for trade in trades),
        "ON DUPLICATE KEY UPDATE",
        "    symbol=VALUES(symbol), side=VALUES(side), volume=VALUES(volume), opened_at=VALUES(opened_at), closed_at=VALUES(closed_at),",
        "    open_price=VALUES(open_price), entry_reference_price=VALUES(entry_reference_price),",
        "    entry_slippage_points=VALUES(entry_slippage_points), entry_slippage_percent=VALUES(entry_slippage_percent),",
        "    close_price=VALUES(close_price), exit_reference_price=VALUES(exit_reference_price),",
        "    exit_slippage_points=VALUES(exit_slippage_points), exit_slippage_percent=VALUES(exit_slippage_percent),",
        "    profit=VALUES(profit), profit_percent=VALUES(profit_percent), best_price=VALUES(best_price),",
        "    worst_price=VALUES(worst_price), mfe_points=VALUES(mfe_points), mfe_percent=VALUES(mfe_percent),",
        "    mae_points=VALUES(mae_points), mae_percent=VALUES(mae_percent), max_profit=VALUES(max_profit),",
        "    max_drawdown=VALUES(max_drawdown), exit_reason=VALUES(exit_reason),",
        "    balance_before=VALUES(balance_before), balance_after=VALUES(balance_after);",
        "",
    ]

    equity: OrderedDict[tuple[str, datetime], tuple[float, float]] = OrderedDict()
    for trade in trades:
        open_minute = trade.opened_at_utc.replace(second=0, microsecond=0)
        close_minute = trade.closed_at_utc.replace(second=0, microsecond=0)
        equity[(account, open_minute)] = (trade.balance_before, trade.balance_before)
        equity[(account, close_minute)] = (trade.balance_after, trade.balance_after)

    lines.extend(
        [
            "INSERT INTO strategy_equity_points(strategy_key, captured_minute, balance, equity, deposit, current_profit, position_ticket)",
            "VALUES",
            ",\n".join(
                "(" + ", ".join(
                    [
                        sql_string(strategy_key),
                        sql_datetime(captured_minute, milliseconds=False),
                        sql_number(balance, 4),
                        sql_number(equity_value, 4),
                        "0",
                        "0",
                        "NULL",
                    ]
                ) + ")"
                for (strategy_key, captured_minute), (balance, equity_value) in equity.items()
            ),
            "ON DUPLICATE KEY UPDATE balance=VALUES(balance), equity=VALUES(equity);",
            "",
            "COMMIT;",
            "",
        ]
    )
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export oppw24 weekly trades to an idempotent MySQL SQL file.")
    parser.add_argument("--oppw24", type=Path, default=Path("oppw24.py"), help="Path to codex/v48 oppw24.py.")
    parser.add_argument("--quotes", type=Path, default=Path("quotes.pkl"), help="Path to the quotes.pkl used by oppw24.py.")
    parser.add_argument("--output", type=Path, default=Path("oppw_trades_20260105_20260716.sql"), help="Output SQL file.")
    parser.add_argument("--start", type=parse_ymd, default="20250106", help="Inclusive start date.")
    parser.add_argument("--end", type=parse_ymd, default="20260717", help="Inclusive end date.")
    parser.add_argument("--account", default="DEMO", help="monitor_accounts.account_key, normally REAL or DEMO.")
    parser.add_argument("--database", default="oppw_monitor", help="MySQL database name.")
    parser.add_argument("--source-stock", default="QQQ", help="Key passed to oppw24.py Sim.process.")
    parser.add_argument("--db-symbol", default="US100", help="Symbol written to strategy_trades.")
    parser.add_argument("--base-leverage", type=float, default=8.0, help="Matches codex/v48 oppw24.py main block.")
    parser.add_argument("--initial-balance", type=float, default=16000.0, help="Matches codex/v48 oppw24.py main block.")
    parser.add_argument("--tpps", type=parse_tpps, default=DEFAULT_TPPS, help="Comma-separated TPP values.")
    parser.add_argument("--be", type=float, default=0.996, help="Break-even ratio.")
    parser.add_argument("--thursday-stop", type=float, default=0.004, help="Thursday stop fraction.")
    parser.add_argument("--friday-stop", type=float, default=0.004, help="Friday stop fraction.")
    parser.add_argument("--ticket-base", type=int, default=800_000_000_000_000, help="Base for deterministic synthetic tickets.")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.start > args.end:
        raise SystemExit("--start must not be after --end.")
    if args.base_leverage <= 0 or args.initial_balance <= 0:
        raise SystemExit("--base-leverage and --initial-balance must be positive.")
    if args.ticket_base < 0:
        raise SystemExit("--ticket-base must be non-negative.")

    module = load_module(args.oppw24.resolve())
    ExportingSim = make_exporting_sim(module, args.source_stock, args.ticket_base)
    sim = ExportingSim()
    sim.quotes = sim.load_quotes(str(args.quotes.resolve()))
    if not isinstance(sim.quotes, dict) or not sim.quotes:
        raise SystemExit(f"No quotes were loaded from {args.quotes}.")
    if args.start not in sim.quotes:
        print(f"Warning: {args.start} is not present in quotes.pkl; oppw24.py will begin at the next available session.", file=sys.stderr)

    disaster_stop_ratio = (100.0 - 50.0 / args.base_leverage) / 100.0
    end_exclusive = add_days(args.end, 0)
    sim.process(
        sim.quotes,
        args.source_stock,
        args.start,
        end_exclusive,
        args.base_leverage,
        tuple(args.tpps),
        disaster_stop_ratio,
        args.be,
        args.thursday_stop,
        args.friday_stop,
        args.initial_balance,
        False,
        False,
        False,
        False,
    )

    trades = sorted(sim.captured_trades, key=lambda item: (item.opened_at_utc, item.ticket))
    expected = expected_entry_dates(sim.quotes, args.source_stock, args.start, args.end)
    closed_open_dates = {trade.open_date for trade in trades}
    missing = [date_key for date_key in expected if date_key not in closed_open_dates]

    if float(sim.deposited) > args.initial_balance + 0.005:
        print(
            "Warning: oppw24.py added automatic capital during the run. "
            "The generated SQL records the resulting trade balances but only creates the initial cash-flow row.",
            file=sys.stderr,
        )
    if missing:
        readable = ", ".join(f"{item[:4]}-{item[4:6]}-{item[6:]}" for item in missing)
        print(
            "Warning: no closed trade was produced for these weekly entries: "
            + readable
            + ". A position may still have been open at the inclusive end date.",
            file=sys.stderr,
        )

    sql = build_sql(
        trades=trades,
        account=args.account,
        db_symbol=args.db_symbol,
        database=args.database,
        initial_balance=args.initial_balance,
        source_name=args.oppw24.name,
        start=args.start,
        end_inclusive=args.end,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(sql, encoding="utf-8", newline="\n")

    print(f"Wrote {len(trades)} closed trades to {args.output.resolve()}")
    print(f"Expected weekly entries in range: {len(expected)}")
    print("Synthetic tickets are deterministic, so rerunning and reimporting updates the same rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
