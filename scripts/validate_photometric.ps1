param(
    [string]$EvidenceRoot = ('outputs/photometric_checks_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')),
    [string]$SimRoot = $env:ISAAC_SIM_PATH,
    [switch]$SkipBenchmarks
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $SimRoot
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not [IO.Path]::IsPathRooted($EvidenceRoot)) { $EvidenceRoot = Join-Path $repoRoot $EvidenceRoot }
$EvidenceRoot = [IO.Path]::GetFullPath($EvidenceRoot)
Push-Location -LiteralPath $repoRoot
try {
    if (Test-Path -LiteralPath $EvidenceRoot) { throw "Evidence exists: $EvidenceRoot" }
    New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
    $geometry = Get-Content (Join-Path $repoRoot 'configs/validation_6_1.yaml') -Raw | ConvertFrom-Json
    $selectedConfig = Join-Path $repoRoot 'configs/tank_photometric.yaml'
    $selected = Get-Content $selectedConfig -Raw | ConvertFrom-Json
    $geometry.lighting = $selected.lighting
    $geometry.rtx = $selected.rtx
    $geometry | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $EvidenceRoot 'geometry_profile.yaml') -Encoding Ascii
    $baseline = Get-Content (Join-Path $repoRoot 'configs/tank_photometric_baseline.yaml') -Raw | ConvertFrom-Json
    $baseline.simulation.warmup_frames = 30
    $baseline | ConvertTo-Json -Depth 30 | Set-Content (Join-Path $EvidenceRoot 'baseline_warm30.yaml') -Encoding Ascii

    function Invoke-PhotometricCheck([string]$Name, [string[]]$RunArguments) {
        $destination = Join-Path $EvidenceRoot $Name
        $console = Join-Path $EvidenceRoot "$Name.log"
        $ErrorActionPreference = 'Continue'
        & $runtime -u -m rov_sim @RunArguments --output-dir $destination *> $console
        $code = $LASTEXITCODE
        $ErrorActionPreference = 'Stop'
        if ($code -ne 0) { throw "Runtime failed: $console" }
        if (Select-String -LiteralPath $console -Pattern '\[Error\]|Traceback \(most recent call last\)|Fatal Python error') { throw "Errors: $console" }
        $runs = @(Get-ChildItem -LiteralPath $destination -Directory)
        if ($runs.Count -ne 1) { throw "Expected one run: $destination" }
        $status = Get-Content (Join-Path $runs[0].FullName 'status.json') -Raw | ConvertFrom-Json
        if ($status.state -ne 'complete') { throw "Incomplete run: $destination" }
        if ($Name -eq 'geometry') {
            python -m rov_sim.tools.validation.validate_recording $runs[0].FullName
            $code = $LASTEXITCODE
            if ($code -ne 0) { throw 'Geometry/recording validation failed' }
        }
        Write-Output "VERIFIED $Name : $($runs[0].FullName)"
    }

    Invoke-PhotometricCheck 'geometry' @('--headless','--experiment','change_detection','--frames','12','--record','--stereo-diagnostics','--config',(Join-Path $EvidenceRoot 'geometry_profile.yaml'))
    Invoke-PhotometricCheck 'oriented' @('--headless','--experiment','change_detection','--frames','12','--record','--photometric-diagnostics','--config',(Join-Path $EvidenceRoot 'geometry_profile.yaml'))
    Invoke-PhotometricCheck 'stationary_selected' @('--headless','--frames','20','--record','--photometric-diagnostics','--config',$selectedConfig)
    Invoke-PhotometricCheck 'stationary_baseline' @('--headless','--frames','20','--record','--photometric-diagnostics','--config',(Join-Path $EvidenceRoot 'baseline_warm30.yaml'))
    if (-not $SkipBenchmarks) {
        Invoke-PhotometricCheck 'benchmark_baseline' @('--headless','--benchmark','--frames','100','--config',(Join-Path $EvidenceRoot 'baseline_warm30.yaml'))
        for ($i = 1; $i -le 3; $i++) {
            Invoke-PhotometricCheck "benchmark_selected_$i" @('--headless','--benchmark','--frames','100','--config',$selectedConfig)
        }
        Invoke-PhotometricCheck 'profile_selected' @('--headless','--benchmark','--frames','100','--profile-tracy','--profile-warp-gpu','--config',$selectedConfig)
    }
    Write-Output "PHOTOMETRIC CHECKS COMPLETE: $EvidenceRoot"
} finally {
    Pop-Location
}
