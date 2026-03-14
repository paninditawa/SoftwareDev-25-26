param(
    [switch]$Clean
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonCandidates = @(
    (Join-Path $ProjectRoot '.venv\Scripts\python.exe'),
    (Join-Path (Split-Path -Parent $ProjectRoot) '.venv\Scripts\python.exe')
)

$PythonExe = $PythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $PythonExe) {
    throw "Could not find venv Python. Checked:`n$($PythonCandidates -join "`n")"
}

if ($Clean) {
    Remove-Item -Recurse -Force (Join-Path $ProjectRoot 'build') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $ProjectRoot 'dist') -ErrorAction SilentlyContinue
}

& $PythonExe -m pip install pyinstaller
& $PythonExe -m PyInstaller --noconfirm --clean "$ProjectRoot\HelloWorldGameSpace.spec"

Write-Host ''
Write-Host 'Build complete.'
Write-Host 'Executable folder:' (Join-Path $ProjectRoot 'dist\HelloWorldGameSpace')
Write-Host 'If Firebase auth is needed on another machine, place .streamlit\secrets.toml next to the executable folder or set FIREBASE_API_KEY.'
