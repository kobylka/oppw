"""Evaluate the opt-in walk-forward meta-filter on requested OPPW24 profiles."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import types
from pathlib import Path

try:
    import matplotlib.pyplot  # noqa: F401
except ModuleNotFoundError:
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    for name in ("plot", "xlabel", "ylabel", "title", "legend", "grid", "show"):
        setattr(pyplot, name, lambda *args, **kwargs: None)
    matplotlib.pyplot = pyplot
    sys.modules["matplotlib"] = matplotlib
    sys.modules["matplotlib.pyplot"] = pyplot

import oppw24


def daily_drawdown(points):
    peak = 10000.0
    maximum = 0.0
    for _, equity in points:
        equity = float(equity)
        peak = max(peak, equity)
        maximum = max(maximum, 1.0 - equity / peak)
    return maximum


def run(quotes, vix, start, end, protected, or5, meta):
    sim = oppw24.Sim()
    sim.quotes = quotes
    with contextlib.redirect_stdout(io.StringIO()):
        sim.process(
            quotes, "QQQ", start, end, 8,
            (0.007, 0.02, 0.05, 0.05, 0.05),
            (100.0 - 50.0 / 8.0) / 100.0, 0.996, 0.004, 0.004,
            initial_balance=10000.0,
            allow_deposits=False,
            apply_tax=True,
            debug=False,
            plots=False,
            loss_control_lookback=None,
            arithmetic_loss_control_enabled=False,
            gap_momentum_enabled=protected,
            tuesday_normalization_enabled=protected,
            premarket_low_enabled=protected,
            leverage_override=True,
            structural_exit_rule=oppw24.selected_structural_exit_rule(or5),
            meta_filter_enabled=meta,
            vix_history=vix,
        )
    years = sim.week_no * 7.0 / 365.0
    cagr = ((sim.balance / sim.deposited) ** (1.0 / years) - 1.0) * 100.0
    events = getattr(sim, "meta_filter_events", [])
    return {
        "start": start,
        "end_exclusive": end,
        "profile": "protected_or5" if protected else "leverage_override",
        "meta_filter": meta,
        "final_balance": sim.balance,
        "cagr_percent": cagr,
        "daily_drawdown_percent": daily_drawdown(sim.daily_equity_points) * 100.0,
        "closed_drawdown_percent": (1.0 - sim.max_dd) * 100.0,
        "trades": sim.trade_no,
        "vetoes": sum(event["action"] == "VETO" for event in events),
        "scored_entries": sum(event["probability"] is not None for event in events),
        "training_outcomes": len(getattr(sim, "meta_filter_outcome_history", [])),
    }


def main():
    seed = oppw24.Sim()
    quotes = seed.load_quotes("quotes.pkl")
    vix = oppw24.load_vix_history(Path(__file__).with_name("VIX_History.csv"))
    results = []
    for start, end in (("20180413", "20260813"), ("20210104", "20260101")):
        for protected, or5 in ((False, False), (True, True)):
            for meta in (False, True):
                results.append(run(quotes, vix, start, end, protected, or5, meta))
    output = Path("../outputs/oppw24_meta_filter")
    output.mkdir(parents=True, exist_ok=True)
    (output / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
