from __future__ import annotations

import pandas as pd
import optuna

from config import (
    ARTIFACT_DIR,
    OPTUNA_STORAGE,
    STUDY_NAME,
)


def main() -> None:
    study = optuna.load_study(
        study_name=STUDY_NAME,
        storage=OPTUNA_STORAGE,
    )

    rows = []

    for trial in study.best_trials:
        row = {
            "trial_number": trial.number,
            "geometric_cagr": trial.values[0],
            "worst_year_cagr": trial.values[1],
            "yearly_instability": trial.values[2],
        }

        row.update(trial.params)
        row.update(trial.user_attrs)

        rows.append(row)

    frame = pd.DataFrame(rows)

    if frame.empty:
        raise RuntimeError(
            "The study has no completed Pareto trials"
        )

    frame = frame.sort_values(
        [
            "geometric_cagr",
            "worst_year_cagr",
            "yearly_instability",
        ],
        ascending=[False, False, True],
    )

    output = (
        ARTIFACT_DIR
        / f"{STUDY_NAME}-pareto.parquet"
    )

    frame.to_parquet(output, index=False)

    csv_output = output.with_suffix(".csv")
    frame.to_csv(csv_output, index=False)

    print(frame.head(30).to_string(index=False))
    print("\nSaved:", output)
    print("Saved:", csv_output)


if __name__ == "__main__":
    main()