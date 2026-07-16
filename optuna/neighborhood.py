from __future__ import annotations

import argparse
import json
import random
from dataclasses import fields, replace

import numpy as np
import optuna
import pandas as pd

from backtest_adapter import evaluate_strategy
from config import (
    ARTIFACT_DIR,
    MAX_TRAIN_DRAWDOWN,
    OPTUNA_STORAGE,
    STUDY_NAME,
    TRAIN_END_DATE,
    TRAIN_START_DATE,
)
from models import StrategyParams
from objective import (
    calculate_objectives,
    valid_parameters,
)


PARAMETER_FIELDS = [
    item.name
    for item in fields(StrategyParams)
]


def parameter_key(
    params: StrategyParams,
) -> tuple:
    return tuple(
        getattr(params, name)
        for name in PARAMETER_FIELDS
    )


def create_neighbors(
    original: StrategyParams,
    random_count: int,
    seed: int,
) -> list[StrategyParams]:
    rng = random.Random(seed)

    candidates = {
        parameter_key(original): original
    }

    # One-at-a-time perturbations.
    for name in PARAMETER_FIELDS:
        for delta in [-1, 1]:
            candidate = replace(
                original,
                **{
                    name: getattr(original, name) + delta
                },
            )

            if valid_parameters(candidate):
                candidates[
                    parameter_key(candidate)
                ] = candidate

    # Combined local perturbations.
    attempts = 0

    while (
        len(candidates) < random_count + 1
        and attempts < random_count * 50
    ):
        attempts += 1

        changes = {
            name: getattr(original, name)
            + rng.choice([-1, 0, 1])
            for name in PARAMETER_FIELDS
        }

        candidate = StrategyParams(**changes)

        if valid_parameters(candidate):
            candidates[
                parameter_key(candidate)
            ] = candidate

    return list(candidates.values())


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--trial",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=250,
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
    )

    args = parser.parse_args()

    study = optuna.load_study(
        study_name=STUDY_NAME,
        storage=OPTUNA_STORAGE,
    )

    trial = study.trials[args.trial]

    params = StrategyParams.from_optuna_params(
        trial.params
    )

    neighbors = create_neighbors(
        original=params,
        random_count=args.samples,
        seed=args.seed,
    )

    rows = []

    for index, candidate in enumerate(neighbors, 1):
        result = evaluate_strategy(
            candidate,
            TRAIN_START_DATE,
            TRAIN_END_DATE,
        )

        if (
            result["max_drawdown"]
            < MAX_TRAIN_DRAWDOWN
        ):
            passed = False
            geometric = float("nan")
            worst = float("nan")
            instability = float("nan")
        else:
            try:
                (
                    geometric,
                    worst,
                    instability,
                ) = calculate_objectives(result)
                passed = True
            except ValueError:
                geometric = float("nan")
                worst = float("nan")
                instability = float("nan")
                passed = False

        row = candidate.to_dict()
        row.update(
            {
                "geometric_cagr": geometric,
                "worst_year_cagr": worst,
                "yearly_instability": instability,
                "max_drawdown": result[
                    "max_drawdown"
                ],
                "passed": passed,
            }
        )

        rows.append(row)

        print(
            f"{index}/{len(neighbors)}",
            geometric,
            candidate,
        )

    frame = pd.DataFrame(rows)

    passing = frame[
        frame["passed"]
        & frame["geometric_cagr"].notna()
    ]

    if passing.empty:
        raise RuntimeError(
            "No neighborhood candidate passed"
        )

    summary = {
        "trial_number": args.trial,
        "tested": len(frame),
        "passed": len(passing),
        "pass_fraction": len(passing) / len(frame),
        "geometric_cagr_median": float(
            passing["geometric_cagr"].median()
        ),
        "geometric_cagr_p10": float(
            passing["geometric_cagr"].quantile(0.10)
        ),
        "geometric_cagr_worst": float(
            passing["geometric_cagr"].min()
        ),
        "worst_year_median": float(
            passing["worst_year_cagr"].median()
        ),
        "max_drawdown_median": float(
            passing["max_drawdown"].median()
        ),
    }

    csv_path = (
        ARTIFACT_DIR
        / f"neighborhood-trial-{args.trial}.csv"
    )
    json_path = (
        ARTIFACT_DIR
        / f"neighborhood-trial-{args.trial}.json"
    )

    frame.to_csv(csv_path, index=False)

    with json_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(summary, file, indent=2)

    print(json.dumps(summary, indent=2))
    print("Saved:", csv_path)
    print("Saved:", json_path)


if __name__ == "__main__":
    main()