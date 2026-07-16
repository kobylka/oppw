from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


def finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def drawdown_magnitude(value: Any) -> float | None:
    number = finite_float(value)
    return abs(number) if number is not None else None


def percentile_summary(series: pd.Series) -> dict[str, float | None]:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return {
            "min": None,
            "p10": None,
            "p25": None,
            "median": None,
            "p75": None,
            "p90": None,
            "max": None,
        }

    values = clean.to_numpy(dtype=float)
    return {
        "min": float(np.min(values)),
        "p10": float(np.percentile(values, 10)),
        "p25": float(np.percentile(values, 25)),
        "median": float(np.percentile(values, 50)),
        "p75": float(np.percentile(values, 75)),
        "p90": float(np.percentile(values, 90)),
        "max": float(np.max(values)),
    }


def row_from_record(
    record: dict[str, Any],
    partial_year: str | None,
) -> dict[str, Any]:
    metrics = record.get("metrics") or {}
    yearly = metrics.get("yearly_returns") or {}

    validation_cagr = finite_float(
        first_present(
            metrics,
            "full_period_cagr",
            "final_cagr",
            "total_cagr",
            "cagr",
        )
    )
    training_values = record.get("training_values") or []
    training_cagr = finite_float(training_values[0] if training_values else None)

    completed_returns: list[float] = []
    all_year_returns: list[float] = []
    if isinstance(yearly, dict):
        for year, raw_return in yearly.items():
            yearly_return = finite_float(raw_return)
            if yearly_return is None:
                continue
            all_year_returns.append(yearly_return)
            if partial_year is None or str(year) != partial_year:
                completed_returns.append(yearly_return)

    row: dict[str, Any] = {
        "candidate_id": record["candidate_id"],
        "cohort_rank": record["cohort_rank"],
        "source_study": record["source_study"],
        "trial_number": record["trial_number"],
        "selection_score": record["selection_score"],
        "status": record["status"],
        "training_cagr": training_cagr,
        "validation_cagr": validation_cagr,
        "final_balance": finite_float(metrics.get("final_balance")),
        "max_drawdown": finite_float(metrics.get("max_drawdown")),
        "max_drawdown_magnitude": drawdown_magnitude(metrics.get("max_drawdown")),
        "sharpe": finite_float(metrics.get("sharpe")),
        "sortino": finite_float(metrics.get("sortino")),
        "trade_count": finite_float(metrics.get("trade_count")),
        "ruined": bool(metrics.get("ruined", False)),
        "completed_year_count": len(completed_returns),
        "profitable_completed_years": sum(value > 0 for value in completed_returns),
        "all_completed_years_profitable": bool(completed_returns)
        and all(value > 0 for value in completed_returns),
        "worst_completed_year": min(completed_returns)
        if completed_returns
        else None,
        "profitable_all_reported_years": bool(all_year_returns)
        and all(value > 0 for value in all_year_returns),
        "error_type": (record.get("error") or {}).get("type"),
        "error_message": (record.get("error") or {}).get("message"),
    }

    if training_cagr is not None and training_cagr != 0 and validation_cagr is not None:
        row["validation_to_training_cagr_ratio"] = validation_cagr / training_cagr
    else:
        row["validation_to_training_cagr_ratio"] = None

    for key, value in sorted((record.get("params") or {}).items()):
        row[f"param_{key}"] = value

    if isinstance(yearly, dict):
        for year, value in sorted(yearly.items(), key=lambda item: str(item[0])):
            row[f"year_{year}"] = finite_float(value)

    return row


def safe_rate(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Analyze out-of-sample survival of a frozen candidate cohort."
    )
    parser.add_argument(
        "--validation",
        type=Path,
        default=Path("artifacts/top_100_validation.json"),
    )
    parser.add_argument(
        "--min-cagr",
        type=float,
        default=0.10,
        help="Minimum full-period validation CAGR required to pass.",
    )
    parser.add_argument(
        "--max-drawdown",
        type=float,
        default=None,
        help=(
            "Optional maximum drawdown magnitude, e.g. 0.50 for 50%%. "
            "Both -0.50 and +0.50 result formats are normalized to 0.50."
        ),
    )
    parser.add_argument(
        "--min-trades",
        type=int,
        default=0,
    )
    parser.add_argument(
        "--partial-year",
        default="2026",
        help="Year excluded from completed-year consistency counts; use '' for none.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("artifacts/top_100_cohort_analysis.csv"),
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/top_100_cohort_summary.json"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()


    payload = json.loads(args.validation.read_text(encoding="utf-8"))
    partial_year = args.partial_year or None
    frame = pd.DataFrame(
        row_from_record(record, partial_year) for record in payload["records"]
    )

    frame["pass_execution"] = frame["status"].eq("ok")
    frame["pass_cagr"] = (
        frame["pass_execution"]
        & frame["validation_cagr"].notna()
        & frame["validation_cagr"].ge(args.min_cagr)
    )
    frame["pass_drawdown"] = True
    if args.max_drawdown is not None:
        frame["pass_drawdown"] = (
            frame["max_drawdown_magnitude"].notna()
            & frame["max_drawdown_magnitude"].le(args.max_drawdown)
        )

    frame["pass_trade_count"] = (
        frame["trade_count"].fillna(0).ge(args.min_trades)
        if args.min_trades > 0
        else True
    )
    frame["passed"] = (
        frame["pass_execution"]
        & frame["pass_cagr"]
        & frame["pass_drawdown"]
        & frame["pass_trade_count"]
        & ~frame["ruined"]
    )

    valid = frame[frame["pass_execution"]].copy()

    if len(valid) >= 2:
        training_rank = valid["training_cagr"].rank(method="average")
        validation_rank = valid["validation_cagr"].rank(method="average")
        spearman = finite_float(training_rank.corr(validation_rank))
    else:
        spearman = None

    year_columns = sorted(
        column for column in frame.columns if column.startswith("year_")
    )
    per_year: dict[str, Any] = {}
    for column in year_columns:
        year_values = pd.to_numeric(valid[column], errors="coerce").dropna()
        per_year[column.removeprefix("year_")] = {
            "candidate_count": int(len(year_values)),
            "profitable_count": int((year_values > 0).sum()),
            "profitable_rate": float((year_values > 0).mean())
            if len(year_values)
            else None,
            "distribution": percentile_summary(year_values),
        }

    summary: dict[str, Any] = {
        "schema_version": 1,
        "validation_file": str(args.validation),
        "validation_hash": payload.get("content_sha256"),
        "criteria": {
            "minimum_cagr": args.min_cagr,
            "maximum_drawdown_magnitude": args.max_drawdown,
            "minimum_trade_count": args.min_trades,
            "partial_year_excluded_from_completed_year_counts": partial_year,
        },
        "cohort": {
            "frozen_candidates": int(len(frame)),
            "successful_backtests": int(frame["pass_execution"].sum()),
            "backtest_errors": int((~frame["pass_execution"]).sum()),
            "passed": int(frame["passed"].sum()),
            "pass_rate": safe_rate(frame["passed"]),
            "passed_cagr": int(frame["pass_cagr"].sum()),
            "cagr_pass_rate": safe_rate(frame["pass_cagr"]),
            "ruined": int(frame["ruined"].sum()),
            "all_completed_years_profitable": int(
                frame["all_completed_years_profitable"].sum()
            ),
            "all_completed_years_profitable_rate": safe_rate(
                frame["all_completed_years_profitable"]
            ),
        },
        "validation_cagr_distribution": percentile_summary(
            valid["validation_cagr"]
        ),
        "max_drawdown_magnitude_distribution": percentile_summary(
            valid["max_drawdown_magnitude"]
        ),
        "training_to_validation_cagr_ratio_distribution": percentile_summary(
            valid["validation_to_training_cagr_ratio"]
        ),
        "training_validation_spearman_rank_correlation": spearman,
        "per_year": per_year,
    }

    frame = frame.sort_values(
        ["passed", "validation_cagr", "max_drawdown_magnitude"],
        ascending=[False, False, True],
        na_position="last",
        kind="mergesort",
    )

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output_csv, index=False)
    args.output_json.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    cohort = summary["cohort"]
    cagr_dist = summary["validation_cagr_distribution"]
    dd_dist = summary["max_drawdown_magnitude_distribution"]

    print(f"Frozen candidates: {cohort['frozen_candidates']}")
    print(f"Successful backtests: {cohort['successful_backtests']}")
    print(
        f"Passed all criteria: {cohort['passed']}/"
        f"{cohort['frozen_candidates']} ({cohort['pass_rate']:.1%})"
    )
    print(
        f"CAGR >= {args.min_cagr:.1%}: {cohort['passed_cagr']}/"
        f"{cohort['frozen_candidates']} ({cohort['cagr_pass_rate']:.1%})"
    )
    print(f"Ruined: {cohort['ruined']}")
    print(f"Median validation CAGR: {cagr_dist['median']}")
    print(f"10th percentile CAGR: {cagr_dist['p10']}")
    print(f"Median max drawdown magnitude: {dd_dist['median']}")
    print(f"Training/validation Spearman: {spearman}")
    print(f"Detailed CSV: {args.output_csv}")
    print(f"Summary JSON: {args.output_json}")


if __name__ == "__main__":
    main()