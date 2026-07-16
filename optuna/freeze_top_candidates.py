from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import optuna
import pandas as pd
from optuna.study import StudyDirection
from optuna.trial import FrozenTrial, TrialState

from config import OPTUNA_STORAGE


DEFAULT_HASH_FILES = (
    "config.py",
    "models.py",
    "backtest_adapter.py",
    "metrics.py",
    "objective.py",
    "strategy.py",
)


def json_default(value: Any) -> Any:
    """Convert common non-standard scalar types to JSON-compatible values."""
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON-encode {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=json_default,
    ).encode("utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def normalized_trial_values(
    trial: FrozenTrial,
    directions: list[StudyDirection],
) -> tuple[float, ...]:
    """Transform all objectives so that larger is always better."""
    assert trial.values is not None
    return tuple(
        float(value) if direction == StudyDirection.MAXIMIZE else -float(value)
        for value, direction in zip(trial.values, directions, strict=True)
    )


def parse_weights(raw: str | None, objective_count: int) -> list[float]:
    if raw is None:
        return [1.0 / objective_count] * objective_count

    weights = [float(part.strip()) for part in raw.split(",")]
    if len(weights) != objective_count:
        raise ValueError(
            f"Expected {objective_count} weights, received {len(weights)}"
        )
    if any(weight < 0 for weight in weights):
        raise ValueError("Weights cannot be negative")

    total = sum(weights)
    if total <= 0:
        raise ValueError("At least one weight must be positive")
    return [weight / total for weight in weights]


def trial_record(
    study_name: str,
    trial: FrozenTrial,
) -> dict[str, Any]:
    assert trial.values is not None
    return {
        "source_study": study_name,
        "trial_number": trial.number,
        "params": dict(trial.params),
        "values": [float(value) for value in trial.values],
        "user_attrs": dict(trial.user_attrs),
        "datetime_start": (
            trial.datetime_start.isoformat() if trial.datetime_start else None
        ),
        "datetime_complete": (
            trial.datetime_complete.isoformat() if trial.datetime_complete else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Freeze a deterministic top-N Optuna candidate cohort."
    )
    parser.add_argument(
        "--study",
        action="append",
        required=True,
        help=(
            "Optuna study name. Repeat this option to pool studies that used "
            "the same training window and objective definitions."
        ),
    )
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument(
        "--weights",
        default=None,
        help=(
            "Comma-separated objective weights. Ranking is percentile-based, "
            "with every objective converted so that higher is better. "
            "Default: equal weights."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/frozen_top_100.json"),
    )
    parser.add_argument(
        "--data-file",
        type=Path,
        action="append",
        default=[],
        help="Optional quote/cache file to hash. Repeat for multiple files.",
    )
    args = parser.parse_args()

    if args.top <= 0:
        raise ValueError("--top must be positive")

    studies = [
        optuna.load_study(study_name=name, storage=OPTUNA_STORAGE)
        for name in args.study
    ]

    directions = list(studies[0].directions)
    for study in studies[1:]:
        if list(study.directions) != directions:
            raise ValueError(
                "All pooled studies must have identical objective directions"
            )

    objective_count = len(directions)
    weights = parse_weights(args.weights, objective_count)

    # Deduplicate exact parameter combinations. If the same combination appears
    # more than once, retain the occurrence with the strongest objective tuple.
    unique: dict[str, tuple[FrozenTrial, str]] = {}
    completed_count = 0

    for study in studies:
        for trial in study.get_trials(deepcopy=False, states=(TrialState.COMPLETE,)):
            completed_count += 1
            if trial.values is None or len(trial.values) != objective_count:
                continue
            if not all(math.isfinite(float(value)) for value in trial.values):
                continue

            key = json.dumps(
                trial.params,
                sort_keys=True,
                separators=(",", ":"),
                default=json_default,
            )
            existing = unique.get(key)
            if existing is None:
                unique[key] = (trial, study.study_name)
                continue

            old_trial, _ = existing
            if normalized_trial_values(trial, directions) > normalized_trial_values(
                old_trial, directions
            ):
                unique[key] = (trial, study.study_name)

    if len(unique) < args.top:
        raise RuntimeError(
            f"Only {len(unique)} unique completed candidates are available; "
            f"cannot freeze top {args.top}."
        )

    rows: list[dict[str, Any]] = []
    for trial, study_name in unique.values():
        row: dict[str, Any] = {
            "source_study": study_name,
            "trial_number": trial.number,
            "trial": trial,
        }
        assert trial.values is not None
        for index, value in enumerate(trial.values):
            row[f"objective_{index}"] = float(value)
        rows.append(row)

    frame = pd.DataFrame(rows)
    rank_columns: list[str] = []

    for index, direction in enumerate(directions):
        objective_column = f"objective_{index}"
        rank_column = f"rank_{index}"

        # pandas percentile rank is 1.0 for the best value with these settings.
        frame[rank_column] = frame[objective_column].rank(
            pct=True,
            method="average",
            ascending=(direction == StudyDirection.MAXIMIZE),
        )
        rank_columns.append(rank_column)

    frame["selection_score"] = 0.0
    for rank_column, weight in zip(rank_columns, weights, strict=True):
        frame["selection_score"] += frame[rank_column] * weight

    # Stable deterministic ordering for equal scores.
    sort_columns = ["selection_score"] + [
        f"objective_{index}" for index in range(objective_count)
    ]
    ascending = [False] + [
        direction == StudyDirection.MINIMIZE for direction in directions
    ]

    selected = frame.sort_values(
        sort_columns,
        ascending=ascending,
        kind="mergesort",
    ).head(args.top)

    candidates: list[dict[str, Any]] = []
    for cohort_rank, (_, row) in enumerate(selected.iterrows(), start=1):
        trial = row["trial"]
        record = trial_record(row["source_study"], trial)
        record.update(
            {
                "candidate_id": f"C{cohort_rank:03d}",
                "cohort_rank": cohort_rank,
                "selection_score": float(row["selection_score"]),
                "objective_percentile_ranks": [
                    float(row[column]) for column in rank_columns
                ],
            }
        )
        candidates.append(record)

    files_to_hash = [Path(name) for name in DEFAULT_HASH_FILES]
    files_to_hash.extend(args.data_file)
    file_hashes = {
        str(path): sha256_file(path)
        for path in files_to_hash
        if path.exists() and path.is_file()
    }

    manifest: dict[str, Any] = {
        "schema_version": 1,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_studies": args.study,
        "storage_backend": "Optuna RDBStorage",
        "objective_directions": [direction.name for direction in directions],
        "objective_weights": weights,
        "ranking_method": "weighted percentile ranks across all objectives",
        "requested_top_n": args.top,
        "completed_trials_seen": completed_count,
        "unique_parameter_sets_seen": len(unique),
        "git_commit": git_commit(),
        "python_version": sys.version,
        "file_sha256": file_hashes,
        "candidates": candidates,
    }
    manifest["content_sha256"] = hashlib.sha256(
        canonical_json_bytes(manifest)
    ).hexdigest()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    temp_path = args.output.with_suffix(args.output.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            default=json_default,
        )
        + "\n",
        encoding="utf-8",
    )
    temp_path.replace(args.output)

    print(f"Frozen {len(candidates)} candidates to {args.output}")
    print(f"Manifest hash: {manifest['content_sha256']}")


if __name__ == "__main__":
    main()