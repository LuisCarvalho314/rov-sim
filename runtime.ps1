# Shared runtime discovery for launch and reproduction scripts.
function Resolve-IsaacPython([string]$SimRoot) {
    if (-not $SimRoot) { throw 'Set ISAAC_SIM_PATH or pass -SimRoot/-IsaacSimPath to your Isaac Sim installation.' }
    $candidates = @(
        (Join-Path $SimRoot 'python.bat'),
        (Join-Path $SimRoot '_build/windows-x86_64/release/python.bat')
    )
    $runtime = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $runtime) { throw "Cannot find Isaac Sim python.bat under $SimRoot" }
    return (Resolve-Path -LiteralPath $runtime).Path
}
