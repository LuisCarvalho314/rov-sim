param(
    [string]$IsaacSimPath = $env:ISAAC_SIM_PATH,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunArguments
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $IsaacSimPath
$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $repoRoot
try {
    & $runtime -m rov_sim @RunArguments
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
