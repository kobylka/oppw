$ProjectPath = $PSScriptRoot
$Python = Join-Path $ProjectPath ".venv\Scripts\python.exe"

for ($worker = 1; $worker -le 16; $worker++) {
    $command = @"
Set-Location '$ProjectPath'

`$env:SAMPLER_TYPE = 'sobol'
`$env:QMC_SEED = '42'
`$env:N_TRIALS = '1024'
`$env:STUDY_VERSION = 'sobol-v1'
`$env:WORKER_ID = '$worker'

& '$Python' worker_enchanced.py
"@

    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command", $command
    )
}