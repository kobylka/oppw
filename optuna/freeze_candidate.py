from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import optuna

from config import (
    ARTIFACT_DIR,
    OPTUNA_STORAGE,
    QUOTES_CACHE,
    STUDY_NAME,
)
from models import StrategyParams


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def git_commit() -> str | None:
    try:
        return subprocess.check_output(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            text=True,
        ).strip()
    except Exception:
        return None


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--trial",
        type=int,
        required=True,
    )

    args = parser.parse_args()

    study = optuna.load_study(
        study_name=STUDY_NAME,
        storage=OPTUNA_STORAGE,
    )

    trial = study.trials[args.trial]

    if trial.values is None:
        raise RuntimeError(
            "Selected trial is not complete"
        )

    params = StrategyParams.from_optuna_params(
        trial.params
    )

    frozen = {
        "study_name": STUDY_NAME,
        "trial_number": trial.number,
        "selected_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "selection_data": "2010-2019 only",
        "parameters": params.to_dict(),
        "objectives": {
            "geometric_cagr": trial.values[0],
            "worst_year_cagr": trial.values[1],
            "yearly_instability": trial.values[2],
        },
        "training_metrics": trial.user_attrs,
        "git_commit": git_commit(),
        "files": {
            "strategy.py": sha256_file(
                Path("strategy.py")
            ),
            "objective.py": sha256_file(
                Path("objective.py")
            ),
            "backtest_adapter.py": sha256_file(
                Path("backtest_adapter.py")
            ),
            "quotes_cache": sha256_file(
                QUOTES_CACHE
            ),
        },
    }

    serialized = json.dumps(
        frozen,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    frozen["candidate_sha256"] = hashlib.sha256(
        serialized
    ).hexdigest()

    output = (
        ARTIFACT_DIR / "frozen_candidate.json"
    )

    if output.exists():
        raise FileExistsError(
            f"Frozen candidate already exists: {output}"
        )

    with output.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(frozen, file, indent=2)

    print(json.dumps(frozen, indent=2))
    print("\nFrozen:", output)


if __name__ == "__main__":
    main()