from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


load_dotenv()

ROOT_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = ROOT_DIR / "data" / "raw"
CACHE_DIR = ROOT_DIR / "data" / "cache"
ARTIFACT_DIR = ROOT_DIR / "artifacts"
LOG_DIR = ROOT_DIR / "logs"

QUOTES_CACHE = CACHE_DIR / "quotes.pkl"

for directory in [RAW_DATA_DIR, CACHE_DIR, ARTIFACT_DIR, LOG_DIR]:
    directory.mkdir(parents=True, exist_ok=True)


OPTUNA_STORAGE = os.environ["OPTUNA_STORAGE"]

TRAIN_START_YEAR = 2010
TRAIN_END_YEAR = int(os.getenv("TRAIN_END_YEAR", "2019"))

TRAIN_START_DATE = f"{TRAIN_START_YEAR}0104"
TRAIN_END_DATE = f"{TRAIN_END_YEAR + 1}0101"

if(TRAIN_END_YEAR == 2019):
    TRAIN_END_DATE = "20200102"
if(TRAIN_END_YEAR == 2018):
    TRAIN_END_DATE = "20190102"
if(TRAIN_END_YEAR == 2017):
    TRAIN_END_DATE = "20180102"
if(TRAIN_END_YEAR == 2016):
    TRAIN_END_DATE = "20170102"
if(TRAIN_END_YEAR == 2015):
    TRAIN_END_DATE = "20160104"
if(TRAIN_END_YEAR == 2014):
    TRAIN_END_DATE = "20150105"
    
TRAIN_START_YEAR = 2018
TRAIN_END_YEAR = 2026
TRAIN_START_DATE = f"20180413"
TRAIN_END_DATE = f"20260717"

QUARANTINE_START_DATE = "20200101"
QUARANTINE_END_DATE = "20220101"

VALIDATION_START_DATE = "20220103"
VALIDATION_START_DATE = "20100104"

# Exclusive end date. Includes Friday, July 10, 2026.
VALIDATION_END_DATE = "20260710"
VALIDATION_END_DATE = "20200102"

STUDY_VERSION = os.getenv("STUDY_VERSION", "v1")
STUDY_NAME = (
    f"oppw-train-{TRAIN_START_YEAR}-{TRAIN_END_YEAR}-{STUDY_VERSION}"
)

INITIAL_BALANCE = 30_000.0
LEVERAGE = 3.0

# Existing general/disaster stop expressed as price ratio.
# Example: 0.95 means exit at 5% below entry.
DISASTER_STOP_RATIO = 0.9375

BREAK_EVEN_RATIO = 0.996

# Keep taxes and deposits disabled during parameter comparison.
ALLOW_DEPOSITS = False
APPLY_TAX = False

# Predetermined training constraint.
# -0.70 means reject configurations exceeding a 70% daily
# mark-to-market drawdown.
MAX_TRAIN_DRAWDOWN = -1

# Candidate selection requirements.
CANDIDATE_CAGR_FRACTION = 0.80
MIN_WORST_YEAR_CAGR = -0.9
MIN_NEIGHBORHOOD_P10_CAGR = 0.0

# Parameter ranges expressed in 0.001 increments.
P1_RANGE = (7, 7)
P2_RANGE = (7, 43)
P3_RANGE = (50, 50)
P4_RANGE = (50, 50)
P5_RANGE = (50, 50)

THURSDAY_STOP = (4, 4)
FRIDAY_STOP = (4, 4)


MINUTE_OPEN = (934, 934)
MINUTE_CLOSE = (1324, 1324)

# This makes targets non-decreasing through the week.
ENFORCE_NONDECREASING_TARGETS = True

# Maximum increase between successive target groups.
MAX_TARGET_STEP = 100