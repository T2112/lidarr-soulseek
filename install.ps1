# Run from this folder:
#   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#   .\install.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Error "Python is not on PATH. Install Python 3.11+ from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
}

Write-Host "Python: $(python --version)"
if (-not (Test-Path "$Root\.venv\Scripts\python.exe")) {
    python -m venv "$Root\.venv"
}
& "$Root\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "$Root\.venv\Scripts\python.exe" -m pip install -r "$Root\requirements.txt"

if (-not (Test-Path "$Root\config.toml")) {
    Copy-Item "$Root\config.example.toml" "$Root\config.toml"
    Write-Host "Created config.toml. Edit it before starting."
} else {
    Write-Host "config.toml already exists; left it alone."
}

$ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($ffmpeg) {
    Write-Host "ffmpeg: found"
} else {
    Write-Host "ffmpeg: NOT found. FLAC conversion will fail until you run: winget install Gyan.FFmpeg"
}

Write-Host ""
Write-Host "Next:"
Write-Host "  1. Edit config.toml (quotes required around every text value)."
Write-Host "  2. $Root\.venv\Scripts\python.exe check.py"
Write-Host "  3. .\open-firewall.ps1   (Administrator)"
Write-Host "  4. $Root\.venv\Scripts\python.exe main.py"
Write-Host "  5. .\register-task.ps1"
