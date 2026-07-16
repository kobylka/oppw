param(
    [int]$WorkerId,
    [int]$Trials = 500,
    [int]$EndYear = 2025
)

$env:WORKER_SEED = "$WorkerId"
$env:N_TRIALS = "$Trials"
$env:TRAIN_END_YEAR = "$EndYear"
$env:STUDY_VERSION = "v1"

python worker.py