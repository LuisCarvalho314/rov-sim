param(
    [string[]]$Profiles = @('baseline','light4','exposure4','shadow_off','water_depth10','dlaa'),
    [string]$EvidenceRoot = 'outputs/photometric_6_1',
    [string]$SimRoot = $env:ISAAC_SIM_PATH
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $SimRoot
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
foreach ($profile in $Profiles) {
    $config = Join-Path $EvidenceRoot "profiles/$profile.yaml"
    $destination = Join-Path $EvidenceRoot $profile
    $console = Join-Path $EvidenceRoot "$profile.log"
    if (Test-Path -LiteralPath $destination) { throw "Evidence already exists: $destination" }
    $ErrorActionPreference = 'Continue'
    & $runtime -u run.py --headless --experiment change_detection --frames 60 --record --photometric-diagnostics --config $config --output-dir $destination *> $console
    $ErrorActionPreference = 'Stop'
    if ($LASTEXITCODE -ne 0) { throw "Runtime failed: $console" }
    $runs = @(Get-ChildItem -LiteralPath $destination -Directory)
    if ($runs.Count -ne 1) { throw "Expected one run: $destination" }
    $status = Get-Content (Join-Path $runs[0].FullName 'status.json') -Raw | ConvertFrom-Json
    if ($status.state -ne 'complete') { throw "Incomplete run: $destination" }
    if (Select-String -LiteralPath $console -Pattern '\[Error\]|Traceback \(most recent call last\)|Fatal Python error') { throw "Error in $console" }
    Write-Output "VERIFIED $profile : $($runs[0].FullName)"
}
