"""Sweep 600 permutations around OPPW24 structural-exit idea 80."""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import math
import sys
import types
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path


START_FULL = "20180413"
END_FULL = "20260813"
START_ROBUST = "20210104"
END_ROBUST = "20260101"


def load_module():
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    for name in ("plot", "xlabel", "ylabel", "title", "legend", "grid", "show"):
        setattr(pyplot, name, lambda *args, **kwargs: None)
    matplotlib.pyplot = pyplot
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)
    import oppw24
    return oppw24


def parse_ranges(value):
    ranges = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if not ranges or any(item <= 0 for item in ranges):
        raise argparse.ArgumentTypeError("Ranges must be positive comma-separated minutes")
    if len(set(ranges)) != len(ranges):
        raise argparse.ArgumentTypeError("Ranges must not contain duplicates")
    return ranges


def make_rules(opening_ranges=(15, 30), slow_windows=(30, 45, 60)):
    rules = []
    number = 1
    for opening_range in opening_ranges:
        for entry_loss in (0.005, 0.01, 0.015, 0.02, 0.025):
            for persistence in (1, 3, 5, 10, 15):
                for slow_minutes in slow_windows:
                    for slow_decline in (0.0075, 0.01, 0.0125, 0.015):
                        rule = {
                            "opening_range_minutes": opening_range,
                            "entry_loss": entry_loss,
                            "persistence": persistence,
                            "slow_minutes": slow_minutes,
                            "slow_decline": slow_decline,
                        }
                        rules.append({
                            "idea_id": number,
                            "rule": rule,
                            "description": (
                                f"OR{opening_range} entry-{entry_loss * 100:.2f}% "
                                f"persist-{persistence}m slow-{slow_minutes}m/"
                                f"-{slow_decline * 100:.2f}%"
                            ),
                        })
                        number += 1
    expected = len(opening_ranges) * 5 * 5 * len(slow_windows) * 4
    if len(rules) != expected:
        raise AssertionError((len(rules), expected))
    return rules


def daily_drawdown(points):
    peak = 10000.0
    maximum = 0.0
    for _, equity in points:
        equity = float(equity)
        if equity > peak:
            peak = equity
        elif peak > 0:
            maximum = max(maximum, 1.0 - equity / peak)
    return maximum


class CapturingSimMixin:
    def sell(self, time, open_price, close_price, open_date, close_date, trade_type, leverage, debug=False):
        if trade_type == "STRUCTURAL_EXIT":
            self.structural_exit_count = getattr(self, "structural_exit_count", 0) + 1
        return super().sell(time, open_price, close_price, open_date, close_date, trade_type, leverage, debug)


def run_one(module, quotes, idea, start, end):
    class CapturingSim(CapturingSimMixin, module.Sim):
        pass
    sim = CapturingSim()
    sim.quotes = quotes
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            quotes, "QQQ", start, end, 8,
            (0.007, 0.02, 0.05, 0.05, 0.05),
            (100.0 - 50.0 / 8.0) / 100.0, 0.996, 0.004, 0.004,
            initial_balance=10000.0, allow_deposits=False, apply_tax=True,
            debug=False, plots=False, loss_control_lookback=None,
            arithmetic_loss_control_enabled=False, gap_momentum_enabled=True,
            tuesday_normalization_enabled=True, premarket_low_enabled=True,
            leverage_override=True,
            structural_exit_rule=None if idea is None else idea["rule"],
        )
    if abs(sim.deposited - 10000.0) > 0.005:
        raise RuntimeError(f"Deposited capital changed: {sim.deposited}")
    years = sim.week_no * 7.0 / 365.0
    cagr = ((sim.balance / sim.deposited) ** (1.0 / years) - 1.0) * 100.0
    return {
        "idea_id": 0 if idea is None else idea["idea_id"],
        "description": "No structural exit" if idea is None else idea["description"],
        "rule": None if idea is None else idea["rule"],
        "start": start,
        "end_exclusive": end,
        "final_balance": sim.balance,
        "cagr_percent": cagr,
        "daily_drawdown": daily_drawdown(sim.daily_equity_points),
        "closed_drawdown": 1.0 - sim.max_dd,
        "trades": sim.trade_no,
        "days_in_position": sim.days_in_position,
        "structural_exits": getattr(sim, "structural_exit_count", 0),
    }


def worker(quotes_path, assigned, start, end):
    module = load_module()
    seed = module.Sim()
    quotes = seed.load_quotes(str(quotes_path))
    return [run_one(module, quotes, idea, start, end) for idea in assigned]


def enrich(rows, baseline):
    for row in rows:
        row["dd_improvement_pp"] = (
            baseline["daily_drawdown"] - row["daily_drawdown"]
        ) * 100.0
        row["cagr_change_pp"] = row["cagr_percent"] - baseline["cagr_percent"]
        row["cagr_retention"] = row["cagr_percent"] / baseline["cagr_percent"]


def pareto(rows):
    eligible = [row for row in rows if row["dd_improvement_pp"] > 0]
    return [
        row for row in eligible
        if not any(
            other["cagr_percent"] >= row["cagr_percent"]
            and other["daily_drawdown"] <= row["daily_drawdown"]
            and (
                other["cagr_percent"] > row["cagr_percent"]
                or other["daily_drawdown"] < row["daily_drawdown"]
            )
            for other in eligible
        )
    ]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quotes", type=Path, default=Path("quotes.pkl"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--ranges", type=parse_ranges, default=(15, 30))
    parser.add_argument("--slow-windows", type=parse_ranges, default=(30, 45, 60))
    args = parser.parse_args()
    quotes_path = args.quotes.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    rules = make_rules(args.ranges, args.slow_windows)
    module = load_module()
    seed = module.Sim()
    quotes = seed.load_quotes(str(quotes_path))
    full_baseline = run_one(module, quotes, None, START_FULL, END_FULL)
    chunks = [rules[index::args.workers] for index in range(args.workers)]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        full_parts = list(pool.map(
            worker,
            [quotes_path] * args.workers,
            chunks,
            [START_FULL] * args.workers,
            [END_FULL] * args.workers,
        ))
    full_rows = sorted(
        [row for part in full_parts for row in part],
        key=lambda row: row["idea_id"],
    )
    enrich(full_rows, full_baseline)

    frontier = pareto(full_rows)
    high_retention = sorted(
        [row for row in full_rows if row["dd_improvement_pp"] > 0],
        key=lambda row: (-row["cagr_retention"], -row["dd_improvement_pp"]),
    )[:10]
    high_improvement = sorted(
        [row for row in full_rows if row["dd_improvement_pp"] > 0],
        key=lambda row: (-row["dd_improvement_pp"], -row["cagr_percent"]),
    )[:10]
    selected_ids = sorted({
        row["idea_id"] for row in frontier + high_retention + high_improvement
    })
    selected = [rules[idea_id - 1] for idea_id in selected_ids]

    robust_baseline = run_one(module, quotes, None, START_ROBUST, END_ROBUST)
    robust_rows = worker(quotes_path, selected, START_ROBUST, END_ROBUST)
    enrich(robust_rows, robust_baseline)
    robust_by_id = {row["idea_id"]: row for row in robust_rows}
    for row in full_rows:
        robust = robust_by_id.get(row["idea_id"])
        if robust:
            row["robust_2021_2025"] = robust

    payload = {
        "grid_size": len(rules),
        "opening_ranges": list(args.ranges),
        "slow_windows": list(args.slow_windows),
        "full_baseline": full_baseline,
        "robust_baseline": robust_baseline,
        "pareto_ids": sorted(row["idea_id"] for row in frontier),
        "robust_tested_ids": selected_ids,
        "ideas": full_rows,
    }
    (output / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    csv_fields = [
        "idea_id", "description", "final_balance", "cagr_percent",
        "daily_drawdown", "closed_drawdown", "dd_improvement_pp",
        "cagr_change_pp", "cagr_retention", "trades", "days_in_position",
        "structural_exits",
    ]
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(full_rows)
    print(json.dumps({
        "full_baseline": full_baseline,
        "robust_baseline": robust_baseline,
        "improved": sum(row["dd_improvement_pp"] > 0 for row in full_rows),
        "pareto_ids": payload["pareto_ids"],
        "robust_tested": len(selected_ids),
        "output": str(output),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
