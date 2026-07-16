from __future__ import annotations

import argparse
import hashlib
import json
import math
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import MISSING, fields, is_dataclass
from pathlib import Path
from typing import Any

import pandas as pd

import config
from backtest_adapter import evaluate_strategy
from models import StrategyParams


DEFAULT_START_DATE = getattr(config, "VALIDATION_START_DATE", "20220101")
DEFAULT_END_DATE = getattr(config, "VALIDATION_END_DATE", "20260711")

METRIC_KEYS = (
    "full_period_cagr",
    "final_cagr",
    "total_cagr",
    "cagr",
    "max_drawdown",
    "sharpe",
    "sortino",
    "trade_count",
    "worst_trade",
    "initial_balance",
    "final_balance",
    "ruined",
    "yearly_returns",
)


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return value
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if hasattr(value, "tolist"):
        return json_safe(value.tolist())
    if hasattr(value, "item"):
        return json_safe(value.item())
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=json_safe,
    ).encode("utf-8")


def verify_manifest(manifest: dict[str, Any]) -> None:
    expected = manifest.get("content_sha256")
    if not expected:
        raise ValueError("Frozen manifest has no content_sha256")

    unsigned = dict(manifest)
    unsigned.pop("content_sha256", None)
    actual = hashlib.sha256(canonical_json_bytes(unsigned)).hexdigest()
    if actual != expected:
        raise ValueError(
            "Frozen manifest hash mismatch. The file was modified after freezing."
        )


def build_strategy_params(raw_params: dict[str, Any]) -> StrategyParams:
    """
    Build StrategyParams while ignoring derived Optuna attributes that are not
    constructor fields. This works when StrategyParams is the dataclass from the
    optimizer scaffold.
    """
    if not is_dataclass(StrategyParams):
        return StrategyParams(**raw_params)

    strategy_fields = {field.name: field for field in fields(StrategyParams)}
    constructor_params = {
        key: value for key, value in raw_params.items() if key in strategy_fields
    }

    missing = [
        name
        for name, field in strategy_fields.items()
        if field.init
        and field.default is MISSING
        and field.default_factory is MISSING
        and name not in constructor_params
    ]
    if missing:
        raise ValueError(
            "Frozen candidate is missing StrategyParams fields: "
            + ", ".join(missing)
        )

    return StrategyParams(**constructor_params)


def compact_result(result: dict[str, Any], include_returns: bool) -> dict[str, Any]:
    compact = {key: json_safe(result[key]) for key in METRIC_KEYS if key in result}

    if include_returns:
        for key in ("trade_returns", "weekly_returns", "period_returns"):
            if key in result:
                compact[key] = json_safe(result[key])

    if not any(
        key in compact
        for key in ("full_period_cagr", "final_cagr", "total_cagr", "cagr")
    ):
        raise KeyError(
            "Backtest result has no CAGR key. Available keys: "
            + ", ".join(sorted(result))
        )

    return compact


def run_candidate(
    candidate: dict[str, Any],
    start_date: str,
    end_date: str,
    include_returns: bool,
) -> dict[str, Any]:
    base = {
        "candidate_id": candidate["candidate_id"],
        "cohort_rank": candidate["cohort_rank"],
        "source_study": candidate["source_study"],
        "trial_number": candidate["trial_number"],
        "selection_score": candidate["selection_score"],
        "training_values": candidate["values"],
        "params": candidate["params"],
    }

    try:
        params = build_strategy_params(candidate["params"])
        result = evaluate_strategy(
            params=params,
            start_date=start_date,
            end_date=end_date,
        )
        if not isinstance(result, dict):
            raise TypeError(
                f"evaluate_strategy returned {type(result).__name__}, expected dict"
            )

        return {
            **base,
            "status": "ok",
            "metrics": compact_result(result, include_returns),
            "error": None,
        }
    except Exception as exc:  # Each candidate must be recorded, even on failure.
        return {
            **base,
            "status": "error",
            "metrics": {},
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=20),
            },
        }


def metric_value(metrics: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return None


def flatten_record(record: dict[str, Any]) -> dict[str, Any]:
    metrics = record["metrics"]
    row: dict[str, Any] = {
        "candidate_id": record["candidate_id"],
        "cohort_rank": record["cohort_rank"],
        "source_study": record["source_study"],
        "trial_number": record["trial_number"],
        "selection_score": record["selection_score"],
        "status": record["status"],
        "error_type": (record["error"] or {}).get("type"),
        "error_message": (record["error"] or {}).get("message"),
        "training_objective_0": (
            record["training_values"][0] if record["training_values"] else None
        ),
        "validation_cagr": metric_value(
            metrics,
            "full_period_cagr",
            "final_cagr",
            "total_cagr",
            "cagr",
        ),
        "max_drawdown": metrics.get("max_drawdown"),
        "sharpe": metrics.get("sharpe"),
        "sortino": metrics.get("sortino"),
        "trade_count": metrics.get("trade_count"),
        "worst_trade": metrics.get("worst_trade"),
        "ruined": metrics.get("ruined"),
    }

    for key, value in sorted(record["params"].items()):
        row[f"param_{key}"] = value

    yearly = metrics.get("yearly_returns") or {}
    if isinstance(yearly, dict):
        for year, value in sorted(yearly.items(), key=lambda item: str(item[0])):
            row[f"year_{year}"] = value

    return row


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate an immutable frozen Optuna candidate cohort."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("artifacts/frozen_top_100.json"),
    )
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument(
        "--end-date",
        default=DEFAULT_END_DATE,
        help="Exclusive end date, matching evaluate_strategy semantics.",
    )
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument(
        "--include-returns",
        action="store_true",
        help="Also save trade/weekly return arrays when supplied by the backtest.",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/top_100_validation.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("artifacts/top_100_validation.csv"),
    )
    args = parser.parse_args()

    if args.workers <= 0:
        raise ValueError("--workers must be positive")

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    verify_manifest(manifest)
    candidates = manifest["candidates"]

    if args.workers == 1:
        records = [
            run_candidate(
                candidate,
                args.start_date,
                args.end_date,
                args.include_returns,
            )
            for candidate in candidates
        ]
    else:
        records = []
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            futures = {
                executor.submit(
                    run_candidate,
                    candidate,
                    args.start_date,
                    args.end_date,
                    args.include_returns,
                ): candidate["candidate_id"]
                for candidate in candidates
            }
            for completed, future in enumerate(as_completed(futures), start=1):
                record = future.result()
                records.append(record)
                print(
                    f"[{completed}/{len(candidates)}] "
                    f"{record['candidate_id']}: {record['status']}"
                )

        records.sort(key=lambda record: record["cohort_rank"])

    payload = {
        "schema_version": 1,
        "manifest_path": str(args.manifest),
        "manifest_sha256": manifest["content_sha256"],
        "validation_start_date": args.start_date,
        "validation_end_date_exclusive": args.end_date,
        "candidate_count": len(candidates),
        "records": records,
    }
    payload["content_sha256"] = hashlib.sha256(
        canonical_json_bytes(payload)
    ).hexdigest()

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_csv.parent.mkdir(parents=True, exist_ok=True)

    json_temp = args.output_json.with_suffix(args.output_json.suffix + ".tmp")
    csv_temp = args.output_csv.with_suffix(args.output_csv.suffix + ".tmp")

    json_temp.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    pd.DataFrame(flatten_record(record) for record in records).to_csv(
        csv_temp,
        index=False,
    )

    json_temp.replace(args.output_json)
    csv_temp.replace(args.output_csv)

    ok_count = sum(record["status"] == "ok" for record in records)
    print(f"Validated successfully: {ok_count}/{len(records)}")
    print(f"JSON: {args.output_json}")
    print(f"CSV:  {args.output_csv}")
    print(f"Validation hash: {payload['content_sha256']}")


if __name__ == "__main__":
    main()