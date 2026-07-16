# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.
#
# Windows setup script. Installs the AVR toolchain (avr-gcc + avrdude),
# installs the Python dependencies, and downloads the DOOM shareware WAD.
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "doom-avr setup (Windows)"
Write-Host "Repository root: $RepoRoot"

# 1. AVR toolchain
Write-Host ""
Write-Host "[1/3] AVR toolchain (avr-gcc, avrdude)"

$avrGcc = Get-Command avr-gcc -ErrorAction SilentlyContinue
if ($avrGcc) {
    Write-Host "avr-gcc already on PATH: $($avrGcc.Source)"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "winget was not found. Install avr-gcc and avrdude manually and re-run this script."
        Write-Host "See: https://github.com/ZakKemble/avr-gcc-build/releases"
    } else {
        Write-Host "Installing ZakKemble.avr-gcc via winget..."
        winget install --id ZakKemble.avr-gcc --source winget --accept-package-agreements --accept-source-agreements
        Write-Host "Installed. A new terminal may be required for PATH changes to take effect."
        Write-Host "doomavr.py and build.sh also auto-detect the winget install location as a fallback."
    }
}

# 2. Python packages
Write-Host ""
Write-Host "[2/3] Python packages (pyserial, pygame)"

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    throw "python was not found on PATH. Install Python 3.12+ from https://www.python.org/downloads/ and re-run this script."
}

python -m pip install -r (Join-Path $RepoRoot "requirements.txt")

# 3. DOOM shareware WAD
Write-Host ""
Write-Host "[3/3] DOOM shareware WAD"

$wadPath = Join-Path $RepoRoot "wad\doom1.wad"
if (Test-Path $wadPath) {
    Write-Host "wad\doom1.wad already present, skipping download."
} else {
    $wadUrl = "https://distro.ibiblio.org/pub/linux/distributions/slitaz/sources/packages/d/doom1.wad"
    Write-Host "Downloading $wadUrl"
    Invoke-WebRequest -Uri $wadUrl -OutFile $wadPath
    Write-Host "Saved to $wadPath"
}

Write-Host ""
Write-Host "Setup complete."
Write-Host "If Device Manager shows the board's driver as failed or missing (common on CH340-based clones), install the WCH CH340 driver separately."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  python doomavr.py ports"
Write-Host "  python doomavr.py build"
Write-Host "  python doomavr.py menu <COM port>"
Write-Host "  python doomavr.py run <COM port>"
