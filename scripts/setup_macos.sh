#!/usr/bin/env bash
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.
#
# macOS setup script (Homebrew-based). Installs the AVR toolchain (avr-gcc,
# avrdude), installs the Python dependencies, and downloads the DOOM
# shareware WAD.
#
# NOT YET TESTED on real hardware -- reviewed for correctness only, not run
# end to end on a real Mac. Use at your own risk, and please open an issue
# if something breaks.
#
# Usage (from the repository root):
#   chmod +x scripts/setup_macos.sh
#   ./scripts/setup_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

echo "doom-avr setup (macOS)"
echo "Repository root: $REPO_ROOT"

# 1. AVR toolchain
echo
echo "[1/3] AVR toolchain (avr-gcc, avrdude)"
if command -v avr-gcc >/dev/null 2>&1 && command -v avrdude >/dev/null 2>&1; then
    echo "avr-gcc and avrdude already on PATH: $(command -v avr-gcc), $(command -v avrdude)"
elif command -v brew >/dev/null 2>&1; then
    echo "Installing avr-gcc and avrdude via Homebrew..."
    brew install avr-gcc avrdude
else
    echo "Homebrew was not found. Install it from https://brew.sh, or install"
    echo "avr-gcc and avrdude some other way, then re-run this script."
fi

# 2. Python packages
echo
echo "[2/3] Python packages (pyserial, pygame)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 was not found on PATH. Install Python 3.12+ and re-run this script." >&2
    exit 1
fi
python3 -m pip install --user -r "$REPO_ROOT/requirements.txt"

# 3. DOOM shareware WAD
echo
echo "[3/3] DOOM shareware WAD"
WAD_PATH="$REPO_ROOT/wad/doom1.wad"
if [ -f "$WAD_PATH" ]; then
    echo "wad/doom1.wad already present, skipping download."
else
    WAD_URL="https://distro.ibiblio.org/pub/linux/distributions/slitaz/sources/packages/d/doom1.wad"
    echo "Downloading $WAD_URL"
    curl -L -o "$WAD_PATH" "$WAD_URL"
    echo "Saved to $WAD_PATH"
fi

echo
echo "Setup complete."
echo "Most Arduino Uno clones need a CH340 or FTDI driver on macOS; if the"
echo "board doesn't show up as /dev/cu.usbserial-* or /dev/cu.wchusbserial*,"
echo "install the matching driver for your board."
echo
echo "Next steps:"
echo "  python3 doomavr.py ports"
echo "  python3 doomavr.py build"
echo "  python3 doomavr.py menu <port, e.g. /dev/cu.usbserial-1420>"
echo "  python3 doomavr.py run <port>"
