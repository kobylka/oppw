from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from config import (
    ARTIFACT_DIR,
    CANDIDATE_CAGR_FRACTION,
    MAX_TRAIN_DRAWDOWN,
    MIN_NEIGHBORHOOD_P10_CAGR,
    MIN_WORST_YEAR_CAGR,
    STUDY_NAME,
)


def main() -> None:
    pareto_path = (
        ARTIFACT_DIR
        / f"{STUDY_NAME}-pareto.parquet"
    )

    pareto = pd.read_parquet(pareto_path)

    best_cagr = pareto["geometric_cagr"].max()

    pareto = pareto[
        pareto["geometric_cagr"]
        >= best_cagr * CANDIDATE_CAGR_FRACTION
    ]

    pareto = pareto[
        pareto["worst_year_cagr"]
        >= MIN_WORST_YEAR_CAGR
    ]

    pareto = pareto[
        pareto["max_drawdown"]
        >= MAX_TRAIN_DRAWDOWN
    ]

    summaries = []

    for path in ARTIFACT_DIR.glob(
        "neighborhood-trial-*.json"
    ):
        with path.open(encoding="utf-8") as file:
            summaries.append(json.load(file))

    neighborhood = pd.DataFrame(summaries)

    if neighborhood.empty:
        raise RuntimeError(
            "Run neighborhood.py for candidate trials first"
        )
    combined = pareto.merge(

        neighborhood,
        on="trial_number",
        how="inner",
    )

    combined = combined[
        combined["geometric_cagr_p10"]
        >= MIN_NEIGHBORHOOD_P10_CAGR
    ]

    combined = combined.sort_values(
        [
            "geometric_cagr_median",
            "geometric_cagr_p10",
            "worst_year_cagr",
            "yearly_instability",
        ],
        ascending=[False, False, False, True],
    )

    output = ARTIFACT_DIR / "candidate-ranking.csv"
    combined.to_csv(output, index=False)

    print(combined.to_string(index=False))
    print("\nSaved:", output)


if __name__ == "__main__":
    main()