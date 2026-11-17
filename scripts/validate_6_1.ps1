param(
    [string]$SimRoot = $env:ISAAC_SIM_PATH,
    [int]$BenchmarkFrames = 100,
    [int]$Repeats = 3,
    [switch]$SkipProfiling
)
$ErrorActionPreference = 'Stop'
if ($BenchmarkFrames -lt 1 -or $Repeats -lt 2) { throw 'Use positive frames and at least two repetitions' }
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $SimRoot
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    $validationRoot = Join-Path $repoRoot ('outputs/validation_6_1_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
    New-Item -ItemType Directory -Path $validationRoot | Out-Null

    function Invoke-ValidationRun([string]$Name, [string[]]$RunArguments) {
        $console = Join-Path $validationRoot ($Name + '.log')
        $destination = Join-Path $validationRoot $Name
        & $runtime -u -m rov_sim @RunArguments --output-dir $destination *> $console
        $code = $LASTEXITCODE
        if ($code -ne 0) { throw "Runtime exited unsuccessfully: $console" }
        $errors = @(Select-String -LiteralPath $console -Pattern '\[Error\]|Traceback \(most recent call last\)|Currently unsupported type|Fatal Python error')
        if ($errors.Count) { throw "Runtime errors: $console" }
        if ($Name -eq 'startup') {
            if (-not (Select-String -LiteralPath $console -SimpleMatch '[Phase 1] SimulationApp and OceanSim startup succeeded.')) {
                throw "Missing startup success marker: $console"
            }
            return
        }
        $runs = @(Get-ChildItem -LiteralPath $destination -Directory)
        if ($runs.Count -ne 1) { throw "Expected one fresh run in $destination" }
        $status = Get-Content -LiteralPath (Join-Path $runs[0].FullName 'status.json') -Raw | ConvertFrom-Json
        if ($status.state -ne 'complete') { throw "Capture failed: $($runs[0].FullName)" }
        if ($Name -in 'stationary','moving') {
            & python -m rov_sim.tools.validation.validate_recording $runs[0].FullName
            $code = $LASTEXITCODE
            if ($code -ne 0) { throw "Recording verification failed: $($runs[0].FullName)" }
        } else {
            if ($status.process_exit_code -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $runs[0].FullName 'benchmark.json'))) {
                throw "Benchmark supervisor rejected run: $($runs[0].FullName)"
            }
        }
        Write-Output "VERIFIED $Name : $($runs[0].FullName)"
    }

    $config = Join-Path $repoRoot 'configs/validation_6_1.yaml'
    Invoke-ValidationRun 'startup' @('--startup-only','--headless')
    Invoke-ValidationRun 'stationary' @('--headless','--frames','3','--record','--stereo-diagnostics','--config',$config)
    Invoke-ValidationRun 'moving' @('--headless','--frames','12','--experiment','change_detection','--record','--stereo-diagnostics','--config',$config)
    for ($repetition = 1; $repetition -le $Repeats; $repetition++) {
        Invoke-ValidationRun "benchmark_$repetition" @('--headless','--benchmark','--frames',"$BenchmarkFrames",'--config',$config)
    }
    if (-not $SkipProfiling) {
        Invoke-ValidationRun 'profiled' @('--headless','--benchmark','--frames',"$BenchmarkFrames",'--profile-tracy','--profile-warp-gpu','--config',$config)
    }
    Write-Output "ISAAC SIM 6.1 STEREO VALIDATION PASS: $validationRoot"
} finally {
    Pop-Location
}
