import os

import optuna
import optunahub

from config import (
    OPTUNA_STORAGE,
)
from objective import objective

STUDY_NAME = os.environ["STUDY_NAME"]

N_TRIALS = int(
    os.getenv("N_TRIALS", "1000")
)

WORKER_SEED = int(
    os.getenv("WORKER_SEED", "1")
)

SAMPLER_TYPE = os.getenv(
    "SAMPLER_TYPE",
    "sobol",
).lower()

QMC_SEED = int(
    os.getenv("QMC_SEED", "42")
)


SAMPLER_TYPE = os.getenv(
    "SAMPLER_TYPE",
    "sobol",
).lower()


def create_sampler() -> optuna.samplers.BaseSampler:
    if SAMPLER_TYPE == "sobol":
        return optuna.samplers.QMCSampler(
            qmc_type="sobol",
            scramble=True,
            seed=42,
        )

    if SAMPLER_TYPE == "nsgaii-warm":
        module = optunahub.load_module(
            "samplers/nsgaii_with_initial_trials"
        )

        return module.NSGAIIwITSampler(
            population_size=256,
            mutation_prob=0.30,
            crossover_prob=0.80,
            swapping_prob=0.50,
            seed=WORKER_SEED,
        )

    if SAMPLER_TYPE == "nsgaii":
        return optuna.samplers.NSGAIISampler(
            population_size=256,
            mutation_prob=0.30,
            crossover_prob=0.80,
            swapping_prob=0.50,
            seed=WORKER_SEED,
        )

    raise ValueError(
        f"Unknown sampler type: {SAMPLER_TYPE}"
    )


sampler = create_sampler()

study = optuna.load_study(
    study_name=STUDY_NAME,
    storage=OPTUNA_STORAGE,
    sampler=sampler,
)

study.optimize(
    objective,
    n_trials=N_TRIALS,
    gc_after_trial=True,
)