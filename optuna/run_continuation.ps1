$ProjectPath = $PSScriptRoot
$Python = Join-Path $ProjectPath ".venv\Scripts\python.exe"

for ($worker = 1; $worker -le 16; $worker++) {
    $seed = 2000 + $worker

    $command = @"
Set-Location '$ProjectPath'

`$env:SAMPLER_TYPE = 'nsgaii-warm'
`$env:STUDY_NAME = 'oppw-train-2022-2025-sobol-8192-v1'
`$env:WORKER_SEED = '$seed'
`$env:N_TRIALS = '1024'

& '$Python' worker.py
"@

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $command
    )
}