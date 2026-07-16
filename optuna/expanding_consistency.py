from __future__ import annotations

import numpy as np
import optuna
import pandas as pd

from config import (
    ARTIFACT_DIR,
    OPTUNA_STORAGE,
    STUDY_VERSION,
)


PARAMETERS = [
    "p1",
    "p2",
    "p3",
    "p4",
    "p5",
    "thursday_stop",
    "friday_stop",
]


def pareto_top_parameters(
    end_year: int,
    limit: int = 30,
) -> np.ndarray:
    study_name = (
        f"oppw-train-2010-{end_year}-{STUDY_VERSION}"
    )

    study = optuna.load_study(
        study_name=study_name,
        storage=OPTUNA_STORAGE,
    )

    trials = sorted(
        study.best_trials,
        key=lambda trial: (
            -trial.values[0],
            -trial.values[1],
            trial.values[2],
        ),
    )[:limit]

    return np.asarray(
        [
            [
                int(trial.params[name])
                for name in PARAMETERS
            ]
            for trial in trials
        ],
        dtype=int,
    )


def main() -> None:
    ranking_path = (
        ARTIFACT_DIR / "candidate-ranking.csv"
    )

    candidates = pd.read_csv(ranking_path)

    expanding_sets = {
        year: pareto_top_parameters(year)
        for year in range(2014, 2020)
    }

    rows = []

    for _, candidate in candidates.iterrows():
        candidate_vector = np.asarray(
            [
                int(candidate[name])
                for name in PARAMETERS
            ],
            dtype=int,
        )

        row = {
            "trial_number": int(
                candidate["trial_number"]
            )
        }

        consistent_count = 0

        for year, vectors in expanding_sets.items():
            # Chebyshev distance: largest single parameter
            # difference, measured in 0.001 ticks.
            distances = np.max(
                np.abs(
                    vectors
                    - candidate_vector[np.newaxis, :]
                ),
                axis=1,
            )

            nearest = int(np.min(distances))

            row[
                f"nearest_distance_2010_{year}"
            ] = nearest

            if nearest <= 2:
                consistent_count += 1

        row["consistent_studies"] = consistent_count
        rows.append(row)

    consistency = pd.DataFrame(rows)

    result = candidates.merge(
        consistency,
        on="trial_number",
    )

    result = result.sort_values(
        [
            "consistent_studies",
            "geometric_cagr_median",
            "geometric_cagr_p10",
        ],
        ascending=[False, False, False],
    )

    output = (
        ARTIFACT_DIR
        / "candidate-ranking-with-consistency.csv"
    )

    result.to_csv(output, index=False)

    print(result.to_string(index=False))
    print("\nSaved:", output)


if __name__ == "__main__":
    main()