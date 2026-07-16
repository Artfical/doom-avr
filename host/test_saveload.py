# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
"""End-to-end save/load test: move to a distinctive non-default position,
save with 'q', flash the LOADG chunk (which itself flashes LEVEL1 back),
and confirm the reloaded state matches exactly -- not just "a save
happened" but the actual restored numbers."""
import subprocess
import sys
import time
import serial

PORT = "COM10"


def read_lines(ser, timeout=8.0, stop_on=("SPRITES:",)):
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.read_until(b"\n")
        if raw:
            t = raw.decode(errors="replace").strip("\r\n")
            if t:
                lines.append(t)
                if any(t.startswith(s) for s in stop_on) or t in ("SAVED", "PAGE:1"):
                    break
    return lines


print("=== move to a distinctive position and save ===")
ser = serial.Serial(PORT, 115200, timeout=5)
time.sleep(2.5)
read_lines(ser)
for _ in range(4):
    ser.write(b"w")
    lines = read_lines(ser)
for _ in range(3):
    ser.write(b"a")
    lines = read_lines(ser)
state_before = next(l for l in lines if l.startswith("STATE:"))
print(f"state before save: {state_before}")

ser.write(b"q")
save_result = read_lines(ser)
print(f"save result: {save_result}")
ser.close()

print("\n=== flash LOADG.BIN, which should auto-chain to LEVEL1.BIN ===")
result = subprocess.run([sys.executable, "doomavr.py", "flash", "LOADG.BIN", PORT],
                         cwd="..", capture_output=True, text=True)
print(result.stdout, result.stderr)

print("\n=== wait for LOADG's own reflash-to-LEVEL1 REQ, then read LEVEL1's restored state ===")
ser = serial.Serial(PORT, 115200, timeout=8)
time.sleep(2.5)
lines = read_lines(ser, timeout=10)
for l in lines:
    print(f"  {l[:70]}")
req_line = next((l for l in lines if l.startswith("REQ:")), None)
print(f"REQ seen from LOADG: {req_line}")
ser.close()

if req_line:
    print("\n=== LOADG requested LEVEL1.BIN itself -- flashing it now (this is what client.py's REQ handler would do automatically) ===")
    result = subprocess.run([sys.executable, "doomavr.py", "flash", "LEVEL1.BIN", PORT],
                             cwd="..", capture_output=True, text=True)
    print(result.stdout, result.stderr)

    ser = serial.Serial(PORT, 115200, timeout=8)
    time.sleep(2.5)
    lines = read_lines(ser, timeout=10)
    for l in lines:
        print(f"  {l[:70]}")
    state_after = next((l for l in lines if l.startswith("STATE:")), None)
    print(f"\nstate before save: {state_before}")
    print(f"state after load:  {state_after}")
    print(f"MATCH: {state_before == state_after}")
    ser.close()
