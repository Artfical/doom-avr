#!/usr/bin/env bash
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.
#
# Linux setup script (Debian/Ubuntu, apt-based). Installs the AVR toolchain
# (gcc-avr, avr-libc, avrdude), installs the Python dependencies, and
# downloads the DOOM shareware WAD.
#
# NOT YET TESTED on real hardware -- reviewed for correctness only, not run
# end to end on a real Linux machine. Use at your own risk, and please open
# an issue if something breaks.
#
# Usage (from the repository root):
#   chmod +x scripts/setup_linux.sh
#   ./scripts/setup_linux.sh
set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

echo "doom-avr setup (Linux)"
echo "Repository root: $REPO_ROOT"

# 1. AVR toolchain
echo
echo "[1/3] AVR toolchain (gcc-avr, avr-libc, avrdude)"
if command -v avr-gcc >/dev/null 2>&1 && command -v avrdude >/dev/null 2>&1; then
    echo "avr-gcc and avrdude already on PATH: $(command -v avr-gcc), $(command -v avrdude)"
elif command -v apt >/dev/null 2>&1; then
    echo "Installing gcc-avr avr-libc avrdude via apt (needs sudo)..."
    sudo apt update
    sudo apt install -y gcc-avr avr-libc avrdude
else
    echo "apt was not found. Install the equivalent of gcc-avr, avr-libc, and"
    echo "avrdude with your distro's package manager, then re-run this script."
fi

# 2. Python packages
echo
echo "[2/3] Python packages (pyserial, pygame)"
if ! command -v python3 >/dev/null 2>&1; then
    echo "error: python3 was not found on PATH. Install Python 3.12+ and re-run this script." >&2
    exit 1
fi
if ! python3 -m pip install --user -r "$REPO_ROOT/requirements.txt"; then
    echo
    echo "pip install failed (some distros block system-wide installs, PEP 668)."
    echo "Try a virtual environment instead:"
    echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

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
echo "If avrdude can't open the serial port without sudo, add yourself to the"
echo "dialout group and log out and back in again:"
echo "  sudo usermod -aG dialout \$USER"
echo
echo "Next steps:"
echo "  python3 doomavr.py ports"
echo "  python3 doomavr.py build"
echo "  python3 doomavr.py menu <port, e.g. /dev/ttyUSB0>"
echo "  python3 doomavr.py run <port>"
