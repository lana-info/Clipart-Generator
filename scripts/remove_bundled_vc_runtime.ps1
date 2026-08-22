param(
    [Parameter(Mandatory = $true)]
    [string]$AppDir
)

$ErrorActionPreference = "Stop"
$internalDir = Join-Path $AppDir "_internal"
if (-not (Test-Path -LiteralPath $internalDir -PathType Container)) {
    throw "PyInstaller internal directory is missing: $internalDir"
}

$vcRuntimePattern = '^(msvcp|vcruntime|concrt|vccorlib).*\.dll$'
$bundledRuntimes = @(
    Get-ChildItem -LiteralPath $internalDir -File |
        Where-Object { $_.Name -match $vcRuntimePattern }
)
foreach ($runtime in $bundledRuntimes) {
    Write-Host "Removing bundled VC runtime shadow: $($runtime.Name)"
    Remove-Item -LiteralPath $runtime.FullName -Force
}

$remaining = @(
    Get-ChildItem -LiteralPath $internalDir -File |
        Where-Object { $_.Name -match $vcRuntimePattern }
)
if ($remaining.Count -ne 0) {
    throw "Bundled VC runtime shadows remain in $internalDir"
}
