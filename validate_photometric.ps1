param(
    [string]$EvidenceRoot = ('outputs/photometric_checks_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')),
    [string]$SimRoot = $env:ISAAC_SIM_PATH,
    [switch]$SkipBenchmarks
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $SimRoot
if (Test-Path -LiteralPath $EvidenceRoot) { throw "Evidence exists: $EvidenceRoot" }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$geometry = Get-Content configs/validation_6_1.yaml -Raw | ConvertFrom-Json
$selected = Get-Content configs/tank_photometric.yaml -Raw | ConvertFrom-Json
$geometry.lighting = $selected.lighting
$geometry.rtx = $selected.rtx
$geometry | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $EvidenceRoot 'geometry_profile.yaml') -Encoding Ascii
$baseline = Get-Content configs/tank_photometric_baseline.yaml -Raw | ConvertFrom-Json
$baseline.simulation.warmup_frames = 30
$baseline | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $EvidenceRoot 'baseline_warm30.yaml') -Encoding Ascii

function Invoke-PhotometricCheck([string]$Name, [string[]]$RunArguments) {
    $destination = Join-Path $EvidenceRoot $Name
    $console = Join-Path $EvidenceRoot "$Name.log"
    $ErrorActionPreference = 'Continue'
    & $runtime -u run.py @RunArguments --output-dir $destination *> $console
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { throw "Runtime failed: $console" }
    if (Select-String -LiteralPath $console -Pattern '\[Error\]|Traceback \(most recent call last\)|Fatal Python error') { throw "Errors: $console" }
    $runs = @(Get-ChildItem -LiteralPath $destination -Directory)
    if ($runs.Count -ne 1) { throw "Expected one run: $destination" }
    $status = Get-Content (Join-Path $runs[0].FullName 'status.json') -Raw | ConvertFrom-Json
    if ($status.state -ne 'complete') { throw "Incomplete run: $destination" }
    if ($Name -eq 'geometry') {
        python validate_recording.py $runs[0].FullName
        if ($LASTEXITCODE -ne 0) { throw 'Geometry/recording validation failed' }
    }
    Write-Output "VERIFIED $Name : $($runs[0].FullName)"
}

Invoke-PhotometricCheck 'geometry' @('--headless','--experiment','change_detection','--frames','12','--record','--stereo-diagnostics','--config',(Join-Path $EvidenceRoot 'geometry_profile.yaml'))
Invoke-PhotometricCheck 'oriented' @('--headless','--experiment','change_detection','--frames','12','--record','--photometric-diagnostics','--config',(Join-Path $EvidenceRoot 'geometry_profile.yaml'))
Invoke-PhotometricCheck 'stationary_selected' @('--headless','--frames','20','--record','--photometric-diagnostics','--config','configs/tank_photometric.yaml')
Invoke-PhotometricCheck 'stationary_baseline' @('--headless','--frames','20','--record','--photometric-diagnostics','--config',(Join-Path $EvidenceRoot 'baseline_warm30.yaml'))
if (-not $SkipBenchmarks) {
    Invoke-PhotometricCheck 'benchmark_baseline' @('--headless','--benchmark','--frames','100','--config',(Join-Path $EvidenceRoot 'baseline_warm30.yaml'))
    for ($i = 1; $i -le 3; $i++) {
        Invoke-PhotometricCheck "benchmark_selected_$i" @('--headless','--benchmark','--frames','100','--config','configs/tank_photometric.yaml')
    }
    Invoke-PhotometricCheck 'profile_selected' @('--headless','--benchmark','--frames','100','--profile-tracy','--profile-warp-gpu','--config','configs/tank_photometric.yaml')
}
Write-Output "PHOTOMETRIC CHECKS COMPLETE: $EvidenceRoot"
