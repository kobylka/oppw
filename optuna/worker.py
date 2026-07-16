from __future__ import annotations

import os

import optuna

from config import OPTUNA_STORAGE, STUDY_NAME
from objective import objective


def main() -> None:
    worker_seed = int(
        os.getenv("WORKER_SEED", "1")
    )
    trial_count = int(
        os.getenv("N_TRIALS", "1000")
    )

    storage = optuna.storages.RDBStorage(
        url=OPTUNA_STORAGE,
        heartbeat_interval=60,
        grace_period=180,
        engine_kwargs={
            "pool_pre_ping": True,
        },
    )

    sampler = optuna.samplers.NSGAIISampler(
        population_size=100,
        seed=worker_seed,
    )

    study = optuna.create_study(
        study_name=STUDY_NAME,
        storage=storage,
        sampler=sampler,
        directions=[
            "maximize",  # geometric CAGR
            "maximize",  # worst-year CAGR
            "minimize",  # year-to-year instability
        ],
        load_if_exists=True,
    )

    print("Study:", STUDY_NAME)
    print("Worker seed:", worker_seed)
    print("Requested trials:", trial_count)

    study.optimize(
        objective,
        n_trials=trial_count,
        gc_after_trial=True,
        show_progress_bar=False,
    )


if __name__ == "__main__":
    main()