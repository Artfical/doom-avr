# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.
#
# Windows setup script. Installs Python (if missing), Git for Windows (if
# missing -- its bash.exe is what runs avr/build.sh), the AVR toolchain
# (avr-gcc + avrdude), the Python dependencies, and downloads the DOOM
# shareware WAD.
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "doom-avr setup (Windows)"
Write-Host "Repository root: $RepoRoot"

# 1. AVR toolchain
Write-Host ""
Write-Host "[1/5] AVR toolchain (avr-gcc, avrdude)"

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

# 2. Git for Windows (its bash.exe is what runs avr/build.sh -- the
# WSL bash.exe stub that's sometimes ahead of it on PATH can't run it,
# since it treats the script path as a path inside the WSL filesystem)
Write-Host ""
Write-Host "[2/5] Git for Windows (bash.exe for avr/build.sh)"

$gitBashCandidates = @(
    "C:\Program Files\Git\bin\bash.exe",
    "C:\Program Files (x86)\Git\bin\bash.exe"
)
$gitBashPath = $gitBashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($gitBashPath) {
    Write-Host "Git for Windows already installed: $gitBashPath"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "winget was not found. Install Git for Windows manually from https://git-scm.com/download/win and re-run this script."
    } else {
        Write-Host "Installing Git for Windows via winget..."
        winget install --id Git.Git --source winget --accept-package-agreements --accept-source-agreements
        $gitBashPath = $gitBashCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
        if ($gitBashPath) {
            Write-Host "Installed: $gitBashPath"
        } else {
            Write-Host "Git for Windows was installed but bash.exe wasn't found at the expected path. A new terminal may be required."
        }
    }
}

# 3. Python interpreter
Write-Host ""
Write-Host "[3/5] Python interpreter"

$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
$pythonExe = $null
if ($pythonCmd) {
    $pythonExe = $pythonCmd.Source
    Write-Host "python already on PATH: $pythonExe"
} else {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw "python was not found on PATH and winget is not available. Install Python 3.12+ from https://www.python.org/downloads/ and re-run this script."
    }
    Write-Host "python not found. Installing Python via winget..."
    winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements

    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        $pythonExe = $pythonCmd.Source
    } else {
        $candidates = Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue
        if ($candidates) {
            $pythonExe = $candidates[0].FullName
            Write-Host "Found python at $pythonExe (not yet on PATH in this session)."
        } else {
            throw "Python was installed but could not be located automatically. Open a new terminal and re-run this script."
        }
    }
}

# 4. Python packages
Write-Host ""
Write-Host "[4/5] Python packages (pyserial, pygame)"

& $pythonExe -m pip install -r (Join-Path $RepoRoot "requirements.txt")

# 5. DOOM shareware WAD
Write-Host ""
Write-Host "[5/5] DOOM shareware WAD"

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
