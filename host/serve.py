#!/usr/bin/env python3
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""doom-avr chunk server -- SUPERSEDED, kept for the protocol-framing
selftest only. Do not point this at real hardware.

client.py is the real, current host: firmware chunks no longer receive
bytes over the running connection at all (see menu.c/level1.c/stub_*.c --
they send REQ:<name> and halt). client.py answers REQ by fully reflashing
the chip via avrdude/Optiboot instead. The framed-binary response format
below was the original design before that shift and no longer matches
what the firmware expects.

Wire protocol (historical, unused by current firmware)
-------------------------------------------------------
Arduino -> Host, over UART, one line at a time (LF-terminated, a stray CR
may follow per menu.c's write order -- stripped on read):
    Any line NOT starting with "REQ:" is menu/debug text and is just
    printed to the console.
    "REQ:<NAME>"  -- request to load chunk <NAME> (e.g. "LEVEL1.BIN").

Host -> Arduino, response to a REQ, binary framed so a ~2KB-RAM AVR loader
can parse it with no allocation and a fixed-size page buffer:
    byte 0:       0x01 = chunk follows, 0x00 = not found (no further bytes)
    bytes 1-2:    chunk length, uint16 little-endian (only if byte0 == 0x01)
    bytes 3..N:   raw chunk bytes
    byte N+1:     checksum = sum(chunk bytes) & 0xFF

Chunks are read from ./chunks/<NAME> relative to this script.
"""
import argparse
import sys
import time
from pathlib import Path

import serial

CHUNKS_DIR = Path(__file__).parent / "chunks"

STATUS_OK = 0x01
STATUS_ERR = 0x00


def build_response(data: bytes | None) -> bytes:
    if data is None:
        return bytes([STATUS_ERR])
    if len(data) > 0xFFFF:
        raise ValueError("chunk too large for uint16-length framing")
    checksum = sum(data) & 0xFF
    return bytes([STATUS_OK]) + len(data).to_bytes(2, "little") + data + bytes([checksum])


def load_chunk(name: str) -> bytes | None:
    path = CHUNKS_DIR / name
    try:
        # guard against a malformed/malicious REQ escaping chunks/
        path = path.resolve()
        if CHUNKS_DIR.resolve() not in path.parents and path != CHUNKS_DIR.resolve():
            return None
        return path.read_bytes()
    except (FileNotFoundError, IsADirectoryError):
        return None


def handle_line(line: str, ser) -> None:
    line = line.strip("\r\n")
    if not line:
        return
    if line.startswith("REQ:"):
        name = line[len("REQ:"):].strip()
        data = load_chunk(name)
        if data is None:
            print(f"[server] REQ {name!r} -> not found")
        else:
            print(f"[server] REQ {name!r} -> {len(data)} bytes")
        ser.write(build_response(data))
        ser.flush()
    else:
        print(f"[doom] {line}")


def run(ser) -> None:
    buf = b""
    print(f"[server] serving chunks from {CHUNKS_DIR}")
    print("[server] type w/s/Enter + Enter to drive the menu, Ctrl+C to quit")
    import threading

    def stdin_forwarder():
        for ch in iter(lambda: sys.stdin.read(1), ""):
            if ch in ("w", "s"):
                ser.write(ch.encode())
            elif ch == "\n":
                ser.write(b"\r")

    threading.Thread(target=stdin_forwarder, daemon=True).start()

    while True:
        chunk = ser.read(ser.in_waiting or 1)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            handle_line(line.decode(errors="replace"), ser)


def selftest() -> None:
    """Exercise the protocol without any hardware via pyserial's loop:// url."""
    CHUNKS_DIR.mkdir(exist_ok=True)
    sample = CHUNKS_DIR / "TEST.BIN"
    sample.write_bytes(bytes(range(16)) * 4)  # 64 bytes

    resp_found = build_response(sample.read_bytes())
    assert resp_found[0] == STATUS_OK
    length = int.from_bytes(resp_found[1:3], "little")
    assert length == 64
    payload = resp_found[3:3 + length]
    checksum = resp_found[3 + length]
    assert payload == sample.read_bytes()
    assert checksum == (sum(payload) & 0xFF)

    resp_missing = build_response(load_chunk("NOPE.BIN"))
    assert resp_missing == bytes([STATUS_ERR])

    assert load_chunk("../serve.py") is None  # path traversal guard

    sample.unlink()
    print("selftest OK: found-chunk framing, missing-chunk framing, "
          "path traversal guard all verified")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("port", nargs="?", help="serial port, e.g. COM5")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--selftest", action="store_true",
                     help="verify protocol framing with no hardware attached")
    args = ap.parse_args()

    if args.selftest:
        selftest()
        return

    if not args.port:
        ap.error("port is required unless --selftest is given")

    CHUNKS_DIR.mkdir(exist_ok=True)
    with serial.Serial(args.port, args.baud, timeout=0.1) as ser:
        time.sleep(2)  # let the Uno finish its auto-reset-on-open reboot
        try:
            run(ser)
        except KeyboardInterrupt:
            print("\n[server] stopped")


if __name__ == "__main__":
    main()
