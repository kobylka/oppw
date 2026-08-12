"""Pair each saved causal idea with current V5 as an additional OR skip."""

import contextlib
import importlib.util
import io
import math
import os
import sys
import types
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
SOURCE = Path(__file__).with_name("test_100_new_ideas.py")
REPORT = Path(__file__).with_name("v5_or_results.md")
START_DATE = "20180413"
END_DATE = "20260804"
ACCOUNT_LEVERAGE = 11.3
STRATEGY_LEVERAGE = 8

sys.path.insert(0, str(BACKTEST))
sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault("matplotlib.pyplot", types.ModuleType("matplotlib.pyplot"))

import numpy  # noqa: F401 - keep the real module before loading the saved test
import oppw24

spec = importlib.util.spec_from_file_location("saved_100_ideas", SOURCE)
saved = importlib.util.module_from_spec(spec)
spec.loader.exec_module(saved)


def iso_week(date_text):
    day = datetime.strptime(date_text, "%Y%m%d")
    return (day - timedelta(days=day.weekday())).strftime("%Y%m%d")


def decision_dates(quote_dates):
    result = []
    previous = "20000101"
    for date in quote_dates:
        if date < START_DATE:
            continue
        if date >= END_DATE:
            break
        weekday = datetime.strptime(date, "%Y%m%d").weekday()
        if weekday > 4:
            continue
        if (
            (datetime.strptime(date, "%Y%m%d")
             - datetime.strptime(previous, "%Y%m%d")).days > 1
            and weekday in (0, 1)
        ):
            result.append(date)
        previous = date
    return result


def weekly_values(sim):
    events = defaultdict(list)
    for event in sim.loss_control_events:
        events[iso_week(event["date"])].append(event)
    result = {}
    for week, week_events in events.items():
        trades = [event for event in week_events if event["action"] == "TRADE"]
        result[week] = trades[-1]["outcome"] if trades else 0.0
    return dict(sorted(result.items()))


def compounded(values):
    return math.prod(1.0 + value for value in values)


def weekly_geometric(values):
    growth = compounded(values)
    return growth ** (1.0 / len(values)) - 1.0 if growth > 0 else -1.0


def maximum_drawdown(values):
    equity = peak = 1.0
    worst = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        worst = min(worst, equity / peak - 1.0)
    return worst


def worst_52(values):
    return min(
        compounded(values[index:index + 52]) - 1.0
        for index in range(len(values) - 51)
    )


def metrics(by_week, start=None, end=None):
    values = [
        raw * ACCOUNT_LEVERAGE
        for week, raw in by_week.items()
        if (start is None or week >= start) and (end is None or week < end)
    ]
    return {
        "geo": weekly_geometric(values),
        "dd": maximum_drawdown(values),
        "worst52": worst_52(values),
    }


def run_variant(quotes, ordered_decisions, flags=None):
    original = oppw24.loss_control_entry_decision
    calls = 0

    if flags is not None:
        def combined_decision(
            outcomes,
            lookback,
            cash_open,
            previous_cash_close,
            momentum20,
            is_monday,
            arithmetic_threshold=0.02,
            gap_threshold=0.01,
            momentum_threshold=-0.005,
            premarket_low=False,
        ):
            nonlocal calls
            if calls >= len(ordered_decisions):
                raise AssertionError("more V5 decisions than prepared signals")
            additional_skip = flags[calls]
            calls += 1
            return original(
                outcomes,
                lookback,
                cash_open,
                previous_cash_close,
                momentum20,
                is_monday,
                arithmetic_threshold,
                gap_threshold,
                momentum_threshold,
                premarket_low or additional_skip,
            )

        oppw24.loss_control_entry_decision = combined_decision

    sim = oppw24.Sim()
    sim.quotes = quotes
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            sim.process(
                {},
                "QQQ",
                START_DATE,
                END_DATE,
                STRATEGY_LEVERAGE,
                [0.007, 0.02, 0.05, 0.05, 0.05],
                (100 - 50 / STRATEGY_LEVERAGE) / 100,
                0.996,
                0.004,
                0.004,
                initial_balance=30000,
                allow_deposits=False,
                apply_tax=True,
                debug=False,
                plots=False,
                loss_control_lookback=2,
                premarket_low_enabled=True,
            )
    finally:
        oppw24.loss_control_entry_decision = original

    if flags is not None and calls != len(ordered_decisions):
        raise AssertionError(
            f"prepared {len(ordered_decisions)} decisions but consumed {calls}"
        )
    return sim


def main():
    old_cwd = Path.cwd()
    os.chdir(BACKTEST)
    try:
        quotes = oppw24.Sim().load_quotes("quotes.pkl")
    finally:
        os.chdir(old_cwd)

    dates = sorted(quotes)
    sessions = [saved.session_record(quotes[date]["QQQ"]) for date in dates]
    positions = {date: index for index, date in enumerate(dates)}
    entries = decision_dates(dates)

    signals = []
    names = None
    for date in entries:
        index = positions[date]
        if index >= 40:
            entry_signals, names = saved.make_signals(
                index, dates, sessions, quotes
            )
        else:
            entry_signals = {number: False for number in range(1, 101)}
        signals.append(entry_signals)

    base_sim = run_variant(quotes, entries)
    base_weeks = weekly_values(base_sim)
    if len(base_weeks) != 432:
        raise AssertionError(f"expected 432 V5 weeks, got {len(base_weeks)}")
    base_metrics = metrics(base_weeks)
    base_skips = {week for week, value in base_weeks.items() if value == 0.0}

    results = []
    for number in range(1, 101):
        flags = [row[number] for row in signals]
        sim = run_variant(quotes, entries, flags)
        weeks = weekly_values(sim)
        result_metrics = metrics(weeks)
        skips = {week for week, value in weeks.items() if value == 0.0}
        post2021 = metrics(weeks, "20210101")
        y2022_2025 = metrics(weeks, "20220101", "20260101")
        results.append({
            "id": number,
            "name": names[number],
            "signal_fires": sum(flags),
            "skips": len(skips),
            "additional": len(skips - base_skips),
            "restored": len(base_skips - skips),
            "geo": result_metrics["geo"],
            "geo_delta": result_metrics["geo"] - base_metrics["geo"],
            "dd": result_metrics["dd"],
            "dd_delta": result_metrics["dd"] - base_metrics["dd"],
            "worst52": result_metrics["worst52"],
            "worst52_delta": (
                result_metrics["worst52"] - base_metrics["worst52"]
            ),
            "post2021_geo": post2021["geo"],
            "y2022_2025_geo": y2022_2025["geo"],
        })
        if number % 5 == 0:
            print(f"completed {number}/100", flush=True)

    duplicate = next(row for row in results if row["id"] == 50)
    if any(
        abs(duplicate[key] - expected) > 1e-12
        for key, expected in (
            ("geo", base_metrics["geo"]),
            ("dd", base_metrics["dd"]),
            ("worst52", base_metrics["worst52"]),
        )
    ) or duplicate["additional"] or duplicate["restored"]:
        raise AssertionError("idea 50 duplicate did not reproduce current V5")

    results.sort(key=lambda row: (row["geo"], row["dd_delta"]), reverse=True)
    report = [
        "# Saved 100 ideas paired with current V5 using OR",
        "",
        "Each saved causal signal was added separately as a whole-week OR skip ",
        "to current V5: last-two arithmetic loss control OR the gap/momentum ",
        "gate with normalized Tuesday re-entry OR the premarket-low gate. ",
        "Skipped weeks retain 0% accounting. Strategy stop geometry uses 8x; ",
        "reported return metrics evaluate raw weekly outcomes at fixed 11.3x. ",
        "The test runs statefully from 2018-04-13 through 2026-08-03.",
        "",
        "## Current V5 authority",
        "",
        f"- Weeks: {len(base_weeks)}",
        f"- Skipped weeks: {len(base_skips)}",
        f"- Weekly geometric: {100 * base_metrics['geo']:.6f}%",
        f"- Maximum drawdown: {100 * base_metrics['dd']:.4f}%",
        f"- Worst rolling 52 weeks: {100 * base_metrics['worst52']:.4f}%",
        "- Alignment check: idea 50 duplicates the installed premarket-low gate ",
        "  and produced exactly zero behavioral or metric change.",
        "",
        "## All results ranked by weekly geometric return",
        "",
        "|Rank|ID|Idea|Signal fires|Total skips|Added/restored|Weekly geo|Delta|Max DD|DD delta|Worst 52|Worst-52 delta|Post-2021 geo|2022-2025 geo|",
        "|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(results, 1):
        report.append(
            f"|{rank}|{row['id']}|{row['name']}|{row['signal_fires']}|"
            f"{row['skips']}|{row['additional']}/{row['restored']}|"
            f"{100 * row['geo']:.6f}%|{100 * row['geo_delta']:+.6f} pp|"
            f"{100 * row['dd']:.4f}%|{100 * row['dd_delta']:+.4f} pp|"
            f"{100 * row['worst52']:.4f}%|"
            f"{100 * row['worst52_delta']:+.4f} pp|"
            f"{100 * row['post2021_geo']:.6f}%|"
            f"{100 * row['y2022_2025_geo']:.6f}%|"
        )
    report.extend([
        "",
        "## Interpretation",
        "",
        "All 100 alternatives reuse the same in-sample history on which the ",
        "ideas were created. Ranking is exploratory and requires frozen-rule ",
        "walk-forward or live shadow confirmation before deployment.",
        "",
    ])
    REPORT.write_text("\n".join(report), encoding="utf-8")

    print("BASE", base_metrics, "skips", len(base_skips))
    print("TOP15")
    for rank, row in enumerate(results[:15], 1):
        print(
            rank,
            row["id"],
            row["name"],
            f"geo={100 * row['geo']:.6f}%",
            f"delta={100 * row['geo_delta']:+.6f}pp",
            f"dd={100 * row['dd']:.4f}%",
            f"worst52={100 * row['worst52']:.4f}%",
            f"added/restored={row['additional']}/{row['restored']}",
        )
    print("REPORT", REPORT)


if __name__ == "__main__":
    main()
