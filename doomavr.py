#!/usr/bin/env python3
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""doom-avr CLI -- one entry point for the whole project.

    doomavr.py build              build every chunk (avr/build.sh) into host/chunks/
    doomavr.py flash <NAME> PORT  flash one chunk (e.g. MENU.BIN) via avrdude
    doomavr.py menu PORT          shortcut: flash MENU.BIN -- the known-good resting
                                   state, useful after any out-of-band testing leaves
                                   the board on a chunk the host doesn't expect
    doomavr.py run PORT           launch the graphical host client (host/client.py)
    doomavr.py ports              list serial ports pyserial can see right now
    doomavr.py regen-map          regenerate avr/src/map_data.h + host/map_data.py
                                   from wad/doom1.wad (tools/gen_map.py)

PORT is a COM port name on Windows (e.g. COM10). See README.md for the
full project writeup and doom_avr_project memory for the build history.
"""
from __future__ import annotations
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "host"))


def _bash_executable() -> str:
    """On Windows, "bash" on PATH often resolves to the WSL launcher stub
    (System32 or WindowsApps) ahead of Git for Windows' real bash.exe. The
    WSL one treats the script argument as a path inside the WSL filesystem,
    not a Windows path, so it fails with "No such file or directory" even
    though the file is right there. Prefer Git for Windows' bash explicitly;
    elsewhere "bash" on PATH is the real thing already."""
    if sys.platform != "win32":
        return "bash"
    for candidate in (r"C:\Program Files\Git\bin\bash.exe",
                      r"C:\Program Files (x86)\Git\bin\bash.exe"):
        if Path(candidate).exists():
            return candidate
    exe = shutil.which("bash")
    if exe and "windowsapps" not in exe.lower() and "system32" not in exe.lower():
        return exe
    raise RuntimeError(
        "No usable bash found (only WSL's bash.exe, if any, which can't run "
        "avr/build.sh since it doesn't understand Windows paths). Install "
        "Git for Windows (https://git-scm.com/download/win) and re-run."
    )


def cmd_build(_args) -> int:
    # Forward slashes: git-bash's own argv parsing treats a bare "\" as an
    # escape character and silently eats backslash-separated Windows paths
    # (e.g. "C:\Users\..." becomes "C:Users...").
    script = (ROOT / "avr" / "build.sh").as_posix()
    result = subprocess.run([_bash_executable(), script], cwd=str(ROOT / "avr"))
    return result.returncode


def cmd_flash(args) -> int:
    from client import reflash  # local import: pulls in pygame, only needed here
    path = ROOT / "host" / "chunks" / args.name
    if not path.exists():
        print(f"error: {path} not found -- run 'doomavr.py build' first?", file=sys.stderr)
        return 1
    ok = reflash(args.port, path)
    return 0 if ok else 1


def cmd_menu(args) -> int:
    args.name = "MENU.BIN"
    return cmd_flash(args)


def cmd_run(args) -> int:
    # client.py always assumes the board is sitting on MENU.BIN when it
    # starts (ArduinoLink.mode defaults to "MENU"). If the board was left
    # on some other chunk from a previous session (e.g. New Game was
    # picked, then the GUI was closed without quitting back to the menu),
    # that assumption goes stale: the client sends menu-navigation bytes
    # to a chunk that interprets them completely differently, which looks
    # exactly like "keys stopped working" (Enter in particular, since it's
    # the byte level1.c's input loop doesn't handle at all and silently
    # ignores). Reflash MENU.BIN first every time so client and board are
    # always in sync at startup, no separate 'menu' step required.
    menu_rc = cmd_menu(args)
    if menu_rc != 0:
        return menu_rc
    result = subprocess.run([sys.executable, str(ROOT / "host" / "client.py"), args.port])
    return result.returncode


def cmd_ports(_args) -> int:
    import serial.tools.list_ports
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        print("no serial ports found")
        return 1
    for p in ports:
        print(f"{p.device}\t{p.description}")
    return 0


def cmd_regen_map(_args) -> int:
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "gen_map.py")], cwd=str(ROOT))
    return result.returncode


def main() -> int:
    ap = argparse.ArgumentParser(prog="doomavr.py", description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)

    sub.add_parser("build", help="build every chunk into host/chunks/").set_defaults(func=cmd_build)

    p_flash = sub.add_parser("flash", help="flash one chunk by name")
    p_flash.add_argument("name", help="chunk filename, e.g. MENU.BIN")
    p_flash.add_argument("port", help="serial port, e.g. COM10")
    p_flash.set_defaults(func=cmd_flash)

    p_menu = sub.add_parser("menu", help="flash MENU.BIN (known-good resting state)")
    p_menu.add_argument("port", help="serial port, e.g. COM10")
    p_menu.set_defaults(func=cmd_menu)

    p_run = sub.add_parser("run", help="launch the graphical host client")
    p_run.add_argument("port", help="serial port, e.g. COM10")
    p_run.set_defaults(func=cmd_run)

    sub.add_parser("ports", help="list available serial ports").set_defaults(func=cmd_ports)
    sub.add_parser("regen-map", help="regenerate map data from wad/doom1.wad").set_defaults(func=cmd_regen_map)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
