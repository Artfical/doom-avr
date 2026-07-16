#!/usr/bin/env bash
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Builds every doom-avr chunk and drops the raw .bin into host/chunks/
# with the exact filenames the firmware's REQ: table expects.
set -euo pipefail
cd "$(dirname "$0")"

# On Windows, `winget install ZakKemble.avr-gcc` puts avr-gcc/avrdude in a
# per-user "Links" shim directory that isn't always already on PATH in
# every shell. Add it if avr-gcc isn't found and we can locate it, without
# hardcoding any one user's name. No-op on Linux/macOS (LOCALAPPDATA won't
# be set there, and avr-gcc is expected to already be on PATH via apt/brew
# -- see README's Requirements section).
if ! command -v avr-gcc >/dev/null 2>&1 && [ -n "${LOCALAPPDATA:-}" ] && command -v cygpath >/dev/null 2>&1; then
    export PATH="$PATH:$(cygpath -u "$LOCALAPPDATA")/Microsoft/WinGet/Links"
fi

CC=avr-gcc
MCU=atmega328p
CFLAGS="-mmcu=$MCU -DF_CPU=16000000UL -Os -Wall -Wextra -std=gnu11"

mkdir -p build
CHUNKS_DIR="../host/chunks"
mkdir -p "$CHUNKS_DIR"

build_chunk() {
    local src="$1" outname="$2" extra_ldflags="${3:-}"
    local base
    base="$(basename "$src" .c)"
    echo "== $outname (from $src) =="
    $CC $CFLAGS -c "$src" -o "build/$base.o"
    $CC -mmcu=$MCU -Os -o "build/$base.elf" "build/$base.o" $extra_ldflags
    avr-objcopy -O binary -R .eeprom "build/$base.elf" "build/$base.bin"
    avr-size "build/$base.elf"
    cp "build/$base.bin" "$CHUNKS_DIR/$outname"
}

build_chunk src/menu.c          MENU.BIN
build_chunk src/level1.c        LEVEL1.BIN "-lm"
build_chunk src/stub_options.c  OPTIONS.BIN
build_chunk src/stub_loadg.c    LOADG.BIN
build_chunk src/stub_saveg.c    SAVEG.BIN
build_chunk src/stub_readthis.c HELP.BIN

echo
echo "All chunks built into $CHUNKS_DIR:"
ls -la "$CHUNKS_DIR"
