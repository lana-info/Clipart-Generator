param(
    [string]$PythonPath = "",
    [switch]$UseV3
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSCommandPath
Set-Location -LiteralPath $root
$logFile = Join-Path $root "start_clipart_gui_launch.log"

$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
Add-Content -Path $logFile -Value "$timestamp START launcher from $root"

if ($env:QT_QPA_PLATFORM -eq 'offscreen') {
    Remove-Item -Path Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
}
$env:QT_QPA_PLATFORM = "windows"
$env:PYTHONPATH = $root

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $candidate = Join-Path $root ".venv\\Scripts\\python.exe"
    if (Test-Path -LiteralPath $candidate) {
        $PythonPath = $candidate
    }
    else {
        $PythonPath = "python"
    }
}

& $PythonPath -c "import os, pathlib, main; print('MAIN_FILE=' + main.__file__); print('VERSION=' + str(getattr(main,'APP_VERSION','n/a'))); print('CWD=' + str(pathlib.Path('.').resolve())); print('QPA=' + os.getenv('QT_QPA_PLATFORM','<notset>'))"
if ($UseV3) {
    & $PythonPath (Join-Path $root 'run_clipart_gui_v3.py')
}
else {
    & $PythonPath (Join-Path $root 'main.py')
}
