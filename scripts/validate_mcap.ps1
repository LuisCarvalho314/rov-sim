# Runtime validation of --record-mcap (docs/designs/isaac-stereo-mcap.md, item 12).
# Needs Isaac Sim 6.1, the OceanSim assets and NVIDIA's Pixi ROS 2 workspace.
param(
    [string]$SimRoot = $env:ISAAC_SIM_PATH,
    [string]$PixiEnv = $env:ROV_SIM_PIXI_ENV,
    [string]$EvidenceRoot
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $SimRoot
if (-not $PixiEnv) { throw 'Set ROV_SIM_PIXI_ENV or pass -PixiEnv (<workspace>\jazzy_ws\.pixi\envs\default).' }
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $EvidenceRoot) {
    $EvidenceRoot = Join-Path $repoRoot ('outputs/validation_mcap_' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ'))
}
if (Test-Path -LiteralPath $EvidenceRoot) { throw "EvidenceRoot already exists: $EvidenceRoot" }
New-Item -ItemType Directory -Path $EvidenceRoot | Out-Null
$EvidenceRoot = (Resolve-Path -LiteralPath $EvidenceRoot).Path
$hadPixiEnv = Test-Path Env:ROV_SIM_PIXI_ENV
$previousPixiEnv = $env:ROV_SIM_PIXI_ENV
Push-Location -LiteralPath $repoRoot
try {
    function Invoke-McapRun([string]$Name, [string[]]$RunArguments, [switch]$ExpectFailure) {
        $console = Join-Path $EvidenceRoot ($Name + '.log')
        $destination = Join-Path $EvidenceRoot $Name
        & $runtime -u -m rov_sim @RunArguments --output-dir $destination *> $console
        $code = $LASTEXITCODE
        if (-not $ExpectFailure) {
            if ($code -ne 0) { throw "Runtime exited unsuccessfully ($code): $console" }
            $errors = @(Select-String -LiteralPath $console -Pattern '\[Error\]|Traceback \(most recent call last\)|Fatal Python error')
            if ($errors.Count) { throw "Runtime errors: $console" }
        }
        $runs = @(Get-ChildItem -LiteralPath $destination -Directory)
        if ($runs.Count -ne 1) { throw "Expected one fresh run in $destination" }
        $status = Get-Content -LiteralPath (Join-Path $runs[0].FullName 'status.json') -Raw | ConvertFrom-Json
        return [pscustomobject]@{ Run = $runs[0].FullName; Status = $status; Console = $console; ExitCode = $code }
    }

    function Assert-BagPasses($Result, [string[]]$Passes) {
        foreach ($pass in $Passes) {
            $entry = $Result.Status.mcap.$pass
            if ($entry.state -ne 'complete') { throw "MCAP pass $pass is '$($entry.state)': $($Result.Run)" }
            $bag = Join-Path $Result.Run "mcap/$pass"
            if (-not (Test-Path -LiteralPath (Join-Path $bag 'metadata.yaml'))) { throw "No metadata.yaml in $bag" }
            if (@(Get-ChildItem -LiteralPath $bag -Filter '*.mcap').Count -ne 1) { throw "Expected one MCAP file in $bag" }
        }
        if (Test-Path -LiteralPath (Join-Path $Result.Run 'mcap/.staging/*')) { throw "Staging folders left behind: $($Result.Run)" }
    }

    $env:ROV_SIM_PIXI_ENV = $PixiEnv
    $photometric = Join-Path $repoRoot 'configs/tank_photometric.yaml'
    $validation = Join-Path $repoRoot 'configs/validation_6_1.yaml'
    $firstBag = @('--headless','--config',$photometric,'--camera-backend','camera-sensor',
                  '--experiment','change_detection','--frames','30','--record-mcap')

    # 1. First bag (Goal 1).
    $result = Invoke-McapRun 'first_bag' $firstBag
    if ($result.Status.state -ne 'complete') { throw "Capture failed: $($result.Run)" }
    Assert-BagPasses $result @('before','after')
    $environment = $result.Status.mcap.environment
    if (-not "$($environment.process_image)".ToLower().EndsWith('kit.exe')) { throw "Not kit.exe: $($environment.process_image)" }
    if ($environment.numpy_version -ne '2.3.1') { throw "Kit NumPy changed: $($environment.numpy_version)" }
    $counts = $result.Status.mcap.before.message_counts
    if ($counts.'/stereo/left/image_raw' -ne 30) { throw "Expected 30 left images, found $($counts.'/stereo/left/image_raw')" }
    Write-Output "VERIFIED first_bag : $($result.Run)\mcap\before"

    # 2. Stereo diagnostics with the flag (Goal 2).
    $result = Invoke-McapRun 'stereo_diagnostics' @('--headless','--config',$validation,'--camera-backend','camera-sensor',
        '--experiment','change_detection','--frames','12','--stereo-diagnostics','--record-mcap')
    if ($result.Status.state -ne 'complete') { throw "Capture failed: $($result.Run)" }
    $summary = Get-Content -LiteralPath (Join-Path $result.Run 'diagnostics/summary.json') -Raw | ConvertFrom-Json
    if ($summary.status -ne 'PASS') { throw "Stereo diagnostics did not pass: $($result.Run)" }
    Assert-BagPasses $result @('before','after')
    Write-Output "VERIFIED stereo_diagnostics : $($result.Run)"

    # 3. Bootstrap failure is recorded (Goal 5). Kit's wrapper can exit 0 after a failure.
    $emptyEnv = Join-Path $EvidenceRoot 'empty_pixi_env'
    New-Item -ItemType Directory -Path $emptyEnv | Out-Null
    $env:ROV_SIM_PIXI_ENV = $emptyEnv
    $result = Invoke-McapRun 'bootstrap_failure' $firstBag -ExpectFailure
    $env:ROV_SIM_PIXI_ENV = $PixiEnv
    if ($result.Status.state -ne 'failed') { throw "Expected state 'failed', found '$($result.Status.state)': $($result.Run)" }
    if ("$($result.Status.error)" -notlike '*MCAP recording bootstrap*') { throw "Bootstrap error not recorded: $($result.Run)" }
    if (-not (Select-String -LiteralPath $result.Console -SimpleMatch 'Traceback (most recent call last)')) {
        throw "No traceback in $($result.Console)"
    }
    Write-Output "VERIFIED bootstrap_failure (exit code $($result.ExitCode)) : $($result.Run)"

    # 4. Recording cost per storage preset (Goal 7); compare with 12.8005 pairs/s in docs/REPRODUCIBILITY.md.
    foreach ($storage in 'none','zstd') {
        $result = Invoke-McapRun "benchmark_$storage" @('--headless','--config',$photometric,'--camera-backend','camera-sensor',
            '--experiment','change_detection','--benchmark','--frames','40','--record-mcap','--mcap-storage',$storage)
        $report = Join-Path $result.Run 'benchmark.json'
        if ($result.Status.process_exit_code -ne 0 -or -not (Test-Path -LiteralPath $report)) {
            throw "Benchmark supervisor rejected run: $($result.Run)"
        }
        Assert-BagPasses $result @('before','after')
        $benchmark = Get-Content -LiteralPath $report -Raw | ConvertFrom-Json
        $recording = $benchmark.summary.stage_statistics.recording_ms
        Write-Output ("BENCHMARK storage={0} pairs/s={1:N4} recording_ms mean={2:N2} p95={3:N2} bytes/frame before={4:N0} after={5:N0} : {6}" -f
            $storage, $benchmark.summary.effective_pairs_per_s, $recording.mean_ms, $recording.p95_ms,
            $result.Status.mcap.before.bytes_per_frame, $result.Status.mcap.after.bytes_per_frame, $result.Run)
    }
    Write-Output "MCAP RECORDING VALIDATION PASS: $EvidenceRoot"
} finally {
    if ($hadPixiEnv) { $env:ROV_SIM_PIXI_ENV = $previousPixiEnv } else { Remove-Item Env:ROV_SIM_PIXI_ENV -ErrorAction SilentlyContinue }
    Pop-Location
}
