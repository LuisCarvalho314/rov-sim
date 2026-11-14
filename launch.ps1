param(
    [string]$IsaacSimPath = $env:ISAAC_SIM_PATH,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunArguments
)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'runtime.ps1')
$runtime = Resolve-IsaacPython $IsaacSimPath
& $runtime (Join-Path $PSScriptRoot 'run.py') @RunArguments
exit $LASTEXITCODE
