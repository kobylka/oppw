"""Evaluate 100 sustained-breakdown exit ideas on protected OPPW24."""

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


def ideas():
    result = []
    number = 1
    entry_losses = (0.01, 0.015, 0.02, 0.025, 0.03)
    persistence_values = (3, 5, 10, 15, 30)
    for loss in entry_losses:
        for persistence in persistence_values:
            result.append({"idea_id": number, "family": "entry+persistence", "rule": {
                "opening_range_minutes": 15, "entry_loss": loss,
                "persistence": persistence,
            }})
            number += 1
    recovery_windows = (5, 10, 15, 30, 60)
    for loss in entry_losses:
        for window in recovery_windows:
            result.append({"idea_id": number, "family": "failed-recovery", "rule": {
                "opening_range_minutes": 30, "entry_loss": loss,
                "persistence": 3, "failed_recovery_minutes": window,
                "recovery_gap": loss / 2.0,
            }})
            number += 1
    session_losses = (0.005, 0.0075, 0.01, 0.0125, 0.015)
    for loss in session_losses:
        for persistence in persistence_values:
            result.append({"idea_id": number, "family": "session+persistence", "rule": {
                "opening_range_minutes": 30, "session_loss": loss,
                "persistence": persistence,
            }})
            number += 1
    slow_clauses = ((15, 0.005), (15, 0.0075), (30, 0.01), (30, 0.0125), (60, 0.015))
    for loss in entry_losses:
        for minutes, decline in slow_clauses:
            result.append({"idea_id": number, "family": "entry+slow-candle", "rule": {
                "opening_range_minutes": 30, "entry_loss": loss,
                "persistence": 3, "slow_minutes": minutes,
                "slow_decline": decline,
            }})
            number += 1
    if len(result) != 100:
        raise AssertionError(len(result))
    for item in result:
        item["description"] = json.dumps(item["rule"], sort_keys=True)
    return result


def daily_dd(points):
    peak = 10000.0
    maximum = 0.0
    for _, equity in points:
        equity = float(equity)
        if equity > peak:
            peak = equity
        elif peak > 0:
            maximum = max(maximum, 1.0 - equity / peak)
    return maximum


def run_one(module, quotes, idea):
    sim = module.Sim()
    sim.quotes = quotes
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            quotes, "QQQ", "20180413", "20260813", 8,
            (0.007, 0.02, 0.05, 0.05, 0.05),
            (100.0 - 50.0 / 8.0) / 100.0, 0.996, 0.004, 0.004,
            initial_balance=10000.0, allow_deposits=False, apply_tax=True,
            debug=False, plots=False, loss_control_lookback=None,
            arithmetic_loss_control_enabled=False, gap_momentum_enabled=True,
            tuesday_normalization_enabled=True, premarket_low_enabled=True,
            leverage_override=True,
            structural_exit_rule=None if idea is None else idea["rule"],
        )
    years = sim.week_no * 7.0 / 365.0
    cagr = ((sim.balance / sim.deposited) ** (1.0 / years) - 1.0) * 100.0
    return {
        "idea_id": 0 if idea is None else idea["idea_id"],
        "family": "baseline" if idea is None else idea["family"],
        "description": "No structural exit" if idea is None else idea["description"],
        "final_balance": sim.balance, "deposited": sim.deposited,
        "cagr_percent": cagr, "daily_drawdown": daily_dd(sim.daily_equity_points),
        "closed_drawdown": 1.0 - sim.max_dd, "trades": sim.trade_no,
        "days_in_position": sim.days_in_position,
    }


def worker(quotes_path, assigned):
    module = load_module()
    seed = module.Sim()
    quotes = seed.load_quotes(str(quotes_path))
    return [run_one(module, quotes, idea) for idea in assigned]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quotes", type=Path, default=Path("quotes.pkl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    all_ideas = ideas()
    module = load_module()
    seed = module.Sim()
    quotes = seed.load_quotes(str(args.quotes.resolve()))
    baseline = run_one(module, quotes, None)
    with ProcessPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, args.quotes.resolve(), all_ideas[:50]),
            pool.submit(worker, args.quotes.resolve(), all_ideas[50:]),
        ]
        rows = futures[0].result() + futures[1].result()
    for row in rows:
        row["dd_improvement_pp"] = (baseline["daily_drawdown"] - row["daily_drawdown"]) * 100.0
        row["cagr_change_pp"] = row["cagr_percent"] - baseline["cagr_percent"]
        row["cagr_retention"] = row["cagr_percent"] / baseline["cagr_percent"]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps({"baseline": baseline, "ideas": rows}, indent=2), encoding="utf-8")
    with (output / "results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"baseline": baseline, "improved": sum(r["dd_improvement_pp"] > 0 for r in rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
