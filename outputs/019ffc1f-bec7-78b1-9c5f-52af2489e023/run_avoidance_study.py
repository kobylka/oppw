from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import multiprocessing as mp
import statistics
import sys
import types
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKTEST = ROOT / "backtest"
SOURCE = BACKTEST / "oppw24.py"
QUOTES = BACKTEST / "quotes.pkl"
OUTPUT = Path(__file__).with_name("avoidance_results.json")
START = "20180413"
END_EXCLUSIVE = "20260813"
REFERENCE_WORST_20 = {
    "20210510", "20181029", "20181119", "20260727", "20181008",
    "20220307", "20201109", "20250414", "20220627", "20260622",
    "20200713", "20260608", "20240415", "20240722", "20201026",
    "20221205", "20210125", "20251215", "20210503", "20221227",
}


@dataclass(frozen=True)
class Candidate:
    idea_id: int
    family: str
    description: str
    feature: str
    operator: str
    threshold: float
    secondary_feature: str | None = None
    secondary_operator: str | None = None
    secondary_threshold: float | None = None


def install_plot_stub() -> None:
    matplotlib = types.ModuleType("matplotlib")
    pyplot = types.ModuleType("matplotlib.pyplot")
    for name in ("plot", "xlabel", "ylabel", "title", "legend", "grid", "show"):
        setattr(pyplot, name, lambda *args, **kwargs: None)
    matplotlib.pyplot = pyplot
    sys.modules["matplotlib"] = matplotlib
    sys.modules["matplotlib.pyplot"] = pyplot


def load_instrumented_module():
    install_plot_stub()
    source = SOURCE.read_text(encoding="utf-8")
    old_signature = "        leverage_override=False,\n    ):"
    new_signature = "        leverage_override=False,\n        entry_filter=None,\n    ):"
    old_entry = "            if should_open_week and open_price == 0:\n"
    new_entry = (
        "            if (\n"
        "                should_open_week\n"
        "                and open_price == 0\n"
        "                and entry_filter is not None\n"
        "                and not entry_filter(date)\n"
        "            ):\n"
        "                should_open_week = False\n\n"
        "            if should_open_week and open_price == 0:\n"
    )
    if source.count(old_signature) != 1 or source.count(old_entry) != 1:
        raise RuntimeError("oppw24.py instrumentation anchors changed")
    source = source.replace(old_signature, new_signature, 1).replace(old_entry, new_entry, 1)
    module = types.ModuleType("oppw24_instrumented")
    module.__file__ = str(SOURCE)
    module.__package__ = ""
    module.__dict__["__name__"] = "oppw24_instrumented"
    sys.path.insert(0, str(BACKTEST))
    try:
        exec(compile(source, str(SOURCE), "exec"), module.__dict__)
    finally:
        sys.path.pop(0)
    return module


def make_candidates() -> list[Candidate]:
    items: list[Candidate] = []

    def add(family, description, feature, operator, threshold, sf=None, so=None, st=None):
        items.append(Candidate(len(items) + 1, family, description, feature, operator, threshold, sf, so, st))

    for minutes in (1, 3, 5, 15, 30, 60):
        for threshold in (-0.002, -0.003, -0.004, -0.005, -0.006, -0.007, -0.008, -0.009, -0.010, -0.011):
            add(
                "Premarket rolling shock",
                f"Skip when the worst premarket {minutes}-minute candle is {threshold:.1%} or worse.",
                f"pm_worst_{minutes}", "<=", threshold,
            )

    for pm_range in (0.006, 0.008, 0.010, 0.012, 0.014):
        for close_location in (0.10, 0.20, 0.30, 0.40):
            add(
                "Premarket range and weak close",
                f"Skip when premarket range is at least {pm_range:.1%} and closes in its bottom {close_location:.0%}.",
                "pm_range", ">=", pm_range, "pm_close_location", "<=", close_location,
            )

    for threshold in (-0.003, -0.004, -0.005, -0.006, -0.007, -0.008, -0.009, -0.010, -0.011, -0.012):
        add("Cash gap down", f"Skip when cash open gaps down {abs(threshold):.1%} or more.", "cash_gap", "<=", threshold)

    for gap in (0.005, 0.010, 0.015, 0.020, 0.025):
        for momentum in (-0.020, -0.010, 0.000, 0.010):
            add(
                "Positive gap with weak momentum",
                f"Skip when cash gap is at least {gap:.1%} and 20-session momentum is no better than {momentum:.1%}.",
                "cash_gap", ">=", gap, "momentum_20", "<=", momentum,
            )

    for lookback in (5, 10, 20, 40):
        for threshold in (-0.02, -0.04, -0.06, -0.08, -0.10):
            add(
                "Weak trailing momentum",
                f"Skip when trailing {lookback}-session momentum is {threshold:.0%} or worse.",
                f"momentum_{lookback}", "<=", threshold,
            )

    for threshold in (-0.005, -0.010, -0.015, -0.020, -0.025, -0.030, -0.035, -0.040, -0.045, -0.050):
        add(
            "Prior cash-session loss",
            f"Skip after a prior cash-session loss of {abs(threshold):.1%} or more.",
            "previous_session_return", "<=", threshold,
        )

    for lookback in (5, 10, 20):
        for threshold in (0.012, 0.016, 0.020, 0.024, 0.028):
            add(
                "High realized volatility",
                f"Skip when {lookback}-session daily realized volatility is at least {threshold:.1%}.",
                f"realized_vol_{lookback}", ">=", threshold,
            )

    for threshold in (-0.002, -0.004, -0.006, -0.008, -0.010, -0.012, -0.014, -0.016, -0.018, -0.020):
        add(
            "Full premarket decline",
            f"Skip when the full premarket return is {threshold:.1%} or worse.",
            "pm_return", "<=", threshold,
        )

    for minutes in (5, 15, 30, 60, 120):
        for threshold in (-0.002, -0.004, -0.006, -0.008, -0.010):
            add(
                "Late premarket slide",
                f"Skip when the final {minutes} premarket minutes fall {abs(threshold):.1%} or more.",
                f"pm_late_{minutes}", "<=", threshold,
            )

    for threshold in (-0.004, -0.006, -0.008, -0.010, -0.012, -0.014, -0.016, -0.018, -0.020, -0.022):
        add(
            "Premarket peak-to-trough drawdown",
            f"Skip when premarket peak-to-trough drawdown reaches {abs(threshold):.1%}.",
            "pm_drawdown", "<=", threshold,
        )

    if len(items) != 200:
        raise AssertionError(f"Expected 200 ideas, got {len(items)}")
    return items


def compare(value: float | None, operator: str, threshold: float) -> bool:
    if value is None or not math.isfinite(value):
        return False
    if operator == "<=":
        return value <= threshold
    if operator == ">=":
        return value >= threshold
    raise ValueError(operator)


def build_features(quotes: dict) -> dict[str, dict[str, float | None]]:
    dates = sorted(quotes)
    close_history: list[float] = []
    daily_returns: list[float] = []
    features: dict[str, dict[str, float | None]] = {}
    previous_cash_close = None
    previous_cash_open = None

    for date in dates:
        bars = quotes[date]["QQQ"]
        if not isinstance(bars, (list, tuple)) or len(bars) <= 1324:
            continue
        cash_open = float(bars[934][0])
        cash_close = float(bars[1324][3])
        pm = bars[4:934]
        pm_open = float(pm[0][0])
        pm_close = float(pm[-1][3])
        pm_high = max(float(bar[1]) for bar in pm)
        pm_low = min(float(bar[2]) for bar in pm)
        pm_span = pm_high - pm_low
        item: dict[str, float | None] = {
            "cash_gap": cash_open / previous_cash_close - 1.0 if previous_cash_close else None,
            "previous_session_return": (
                previous_cash_close / previous_cash_open - 1.0
                if previous_cash_close and previous_cash_open
                else None
            ),
            "pm_range": pm_span / pm_open if pm_open else None,
            "pm_close_location": (pm_close - pm_low) / pm_span if pm_span > 0 else None,
            "pm_return": pm_close / pm_open - 1.0 if pm_open else None,
        }
        for lookback in (5, 10, 20, 40):
            item[f"momentum_{lookback}"] = (
                previous_cash_close / close_history[-lookback] - 1.0
                if previous_cash_close and len(close_history) >= lookback
                else None
            )
        for lookback in (5, 10, 20):
            values = daily_returns[-lookback:]
            item[f"realized_vol_{lookback}"] = statistics.pstdev(values) if len(values) == lookback else None
        for minutes in (1, 3, 5, 15, 30, 60):
            worst = None
            for start in range(0, len(pm) - minutes + 1):
                opening = float(pm[start][0])
                low = min(float(bar[2]) for bar in pm[start:start + minutes])
                value = low / opening - 1.0
                if worst is None or value < worst:
                    worst = value
            item[f"pm_worst_{minutes}"] = worst
        for minutes in (5, 15, 30, 60, 120):
            item[f"pm_late_{minutes}"] = pm_close / float(pm[-minutes][0]) - 1.0
        peak = float(pm[0][1])
        drawdown = 0.0
        for bar in pm:
            peak = max(peak, float(bar[1]))
            drawdown = min(drawdown, float(bar[2]) / peak - 1.0)
        item["pm_drawdown"] = drawdown
        features[date] = item
        if previous_cash_close:
            daily_returns.append(cash_close / previous_cash_close - 1.0)
        close_history.append(cash_close)
        previous_cash_open = cash_open
        previous_cash_close = cash_close
    return features


WORKER_MODULE = None
WORKER_QUOTES = None
WORKER_FEATURES = None


def worker_init():
    global WORKER_MODULE, WORKER_QUOTES, WORKER_FEATURES
    WORKER_MODULE = load_instrumented_module()
    base = WORKER_MODULE.Sim()
    WORKER_QUOTES = base.load_quotes(str(QUOTES))
    WORKER_FEATURES = build_features(WORKER_QUOTES)


def candidate_triggers(candidate: Candidate, feature_values: dict[str, float | None]) -> bool:
    first = compare(feature_values.get(candidate.feature), candidate.operator, candidate.threshold)
    if not first:
        return False
    if candidate.secondary_feature is None:
        return True
    return compare(
        feature_values.get(candidate.secondary_feature),
        candidate.secondary_operator,
        candidate.secondary_threshold,
    )


def run_one(task):
    candidate_dict, config_name = task
    candidate = Candidate(**candidate_dict) if candidate_dict else None
    skipped_dates: list[str] = []

    class CaptureSim(WORKER_MODULE.Sim):
        def __init__(self):
            super().__init__()
            self.captured_trades = []

        def sell(self, time, open_price, close_price, open_date, close_date, trade_type, leverage, debug=False):
            balance_before = self.balance
            super().sell(time, open_price, close_price, open_date, close_date, trade_type, leverage, False)
            change = int((close_price / open_price - 1.0) * 100000) / 100000
            self.captured_trades.append({
                "open_date": open_date,
                "close_date": close_date,
                "change": change,
                "account_return": self.trade_returns[-1],
                "pnl": self.balance - balance_before,
                "exit": trade_type,
                "leverage": leverage,
            })

    def entry_filter(date):
        if candidate is None:
            return True
        values = WORKER_FEATURES.get(date, {})
        triggered = candidate_triggers(candidate, values)
        if triggered:
            skipped_dates.append(date)
        return not triggered

    protected = config_name == "protected"
    sim = CaptureSim()
    sim.quotes = WORKER_QUOTES
    with contextlib.redirect_stdout(io.StringIO()):
        result = sim.process(
            sim.quotes,
            "QQQ",
            START,
            END_EXCLUSIVE,
            8,
            [0.007, 0.02, 0.05, 0.05, 0.05],
            (100 - 50 / 8) / 100,
            0.996,
            0.004,
            0.004,
            initial_balance=580,
            allow_deposits=True,
            apply_tax=False,
            debug=False,
            plots=False,
            loss_control_lookback=None,
            premarket_low_enabled=protected,
            arithmetic_loss_control_enabled=False,
            gap_momentum_enabled=protected,
            tuesday_normalization_enabled=protected,
            leverage_override=True,
            entry_filter=entry_filter,
        )

    daily = [(date, equity) for date, equity in sim.daily_equity_points if equity > 0]
    daily_peak = 0.0
    daily_max_dd = 0.0
    pre_peak = 0.0
    pre_max_dd = 0.0
    post_peak = 0.0
    post_max_dd = 0.0
    for date, equity in daily:
        daily_peak = max(daily_peak, equity)
        daily_max_dd = max(daily_max_dd, 1.0 - equity / daily_peak)
        if date < "20230101":
            pre_peak = max(pre_peak, equity)
            pre_max_dd = max(pre_max_dd, 1.0 - equity / pre_peak)
        else:
            post_peak = max(post_peak, equity)
            post_max_dd = max(post_max_dd, 1.0 - equity / post_peak)

    losing_skips = 0
    profitable_skips = 0
    reference_avoided = len(set(skipped_dates) & REFERENCE_WORST_20)
    return {
        "idea_id": candidate.idea_id if candidate else 0,
        "config": config_name,
        "description": candidate.description if candidate else "Baseline: no additional candidate rule.",
        "family": candidate.family if candidate else "Baseline",
        "feature": candidate.feature if candidate else None,
        "operator": candidate.operator if candidate else None,
        "threshold": candidate.threshold if candidate else None,
        "secondary_feature": candidate.secondary_feature if candidate else None,
        "secondary_operator": candidate.secondary_operator if candidate else None,
        "secondary_threshold": candidate.secondary_threshold if candidate else None,
        "final_balance": sim.balance,
        "deposited": sim.deposited,
        "growth_multiple": result[2],
        "cagr_factor": result[3],
        "closed_trade_dd": result[5],
        "daily_max_dd": daily_max_dd,
        "pre_2023_daily_dd": pre_max_dd,
        "post_2023_daily_dd": post_max_dd,
        "trade_count": len(sim.captured_trades),
        "skipped_count": len(skipped_dates),
        "skipped_dates": skipped_dates,
        "reference_worst20_avoided": reference_avoided,
        "worst_trade_return": min((trade["account_return"] for trade in sim.captured_trades), default=0.0),
        "trades": sim.captured_trades if candidate is None else None,
    }


def enrich(results):
    baselines = {row["config"]: row for row in results if row["idea_id"] == 0}
    for row in results:
        base = baselines[row["config"]]
        row["cagr_net"] = row["cagr_factor"] - 1.0
        row["baseline_cagr_net"] = base["cagr_factor"] - 1.0
        row["cagr_retention"] = (
            row["cagr_net"] / row["baseline_cagr_net"]
            if base["cagr_factor"] > 1.0
            else None
        )
        row["closed_dd_improvement"] = base["closed_trade_dd"] - row["closed_trade_dd"]
        row["daily_dd_improvement"] = base["daily_max_dd"] - row["daily_max_dd"]
        row["trade_reduction"] = base["trade_count"] - row["trade_count"]
        baseline_worst = {
            trade["open_date"]
            for trade in sorted(base["trades"], key=lambda trade: trade["account_return"])[:20]
        }
        row["config_worst20_avoided"] = len(set(row["skipped_dates"]) & baseline_worst)
        baseline_by_date = {trade["open_date"]: trade for trade in base["trades"]}
        skipped_baseline = [baseline_by_date[date] for date in row["skipped_dates"] if date in baseline_by_date]
        row["baseline_losers_skipped"] = sum(1 for trade in skipped_baseline if trade["account_return"] < 0)
        row["baseline_winners_skipped"] = sum(1 for trade in skipped_baseline if trade["account_return"] >= 0)
        row["skipped_baseline_return_sum"] = sum(trade["account_return"] for trade in skipped_baseline)
        retention_penalty = max(0.0, 0.90 - (row["cagr_retention"] or 0.0))
        row["score"] = row["daily_dd_improvement"] + 0.4 * row["closed_dd_improvement"] - 2.0 * retention_penalty
        row["recommended"] = (
            row["idea_id"] > 0
            and row["cagr_retention"] is not None
            and row["cagr_retention"] >= 0.80
            and row["daily_dd_improvement"] > 0.0
            and row["config_worst20_avoided"] >= 1
        )
    return baselines


def main() -> int:
    candidates = make_candidates()
    tasks = [(None, config) for config in ("protected", "leverage_only")]
    tasks.extend((asdict(candidate), config) for candidate in candidates for config in ("protected", "leverage_only"))
    print(f"Running {len(tasks)} exact simulations with {min(4, mp.cpu_count())} workers", flush=True)
    results = []
    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=min(4, mp.cpu_count()), initializer=worker_init) as pool:
        for index, row in enumerate(pool.imap_unordered(run_one, tasks, chunksize=1), start=1):
            results.append(row)
            if index % 20 == 0 or index == len(tasks):
                print(f"PROGRESS {index}/{len(tasks)}", flush=True)
    baselines = enrich(results)
    results.sort(key=lambda row: (row["idea_id"], row["config"]))
    payload = {
        "metadata": {
            "source": str(SOURCE),
            "quotes": str(QUOTES),
            "start": START,
            "end_inclusive": "20260812",
            "idea_count": len(candidates),
            "simulation_count": len(results),
            "method": "Exact oppw24.py reruns with a pre-entry candidate filter; no candidate uses future data.",
        },
        "candidates": [asdict(candidate) for candidate in candidates],
        "baselines": baselines,
        "results": results,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"WROTE {OUTPUT}", flush=True)
    return 0


if __name__ == "__main__":
    mp.freeze_support()
    raise SystemExit(main())
