param(
    [string]$IsaacSimPath = $env:ISAAC_SIM_PATH,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RunArguments
)
$ErrorActionPreference = 'Stop'
if (-not $IsaacSimPath) { $IsaacSimPath = 'C:\isaacsim' }
$candidates = @(
    (Join-Path $IsaacSimPath 'python.bat'),
    (Join-Path $IsaacSimPath '_build\windows-x86_64\release\python.bat')
)
$runtime = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $runtime) { throw "Cannot find Isaac Sim python.bat under $IsaacSimPath. Set ISAAC_SIM_PATH or -IsaacSimPath." }
& $runtime (Join-Path $PSScriptRoot 'run.py') @RunArguments
exit $LASTEXITCODE
