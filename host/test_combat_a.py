# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Test A: fire while facing away from an enemy (expect MISS), rotate
180 degrees toward it over several turns (AI should chase during those
turns, closing distance), then fire again (expect HIT)."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=5)
time.sleep(2.5)


def read_lines(timeout=8.0):
    """Read until a SPRITES: line (always the last line of a frame)."""
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.read_until(b"\n")
        if raw:
            t = raw.decode(errors="replace").strip("\r\n")
            if t:
                lines.append(t)
                if t.startswith("SPRITES:"):
                    break
    return lines


print("=== boot (spawn 200 units from enemy 0, facing away) ===")
lines = read_lines()
for l in lines:
    print(f"  {l[:70]}")
sprites0 = next(l for l in lines if l.startswith("SPRITES:"))
e0_entry = next((e for e in sprites0.split(",") if e.startswith("E0:")), None)
print(f"  E0 entry: {e0_entry}")

print("\n=== fire while facing away (expect MISS) ===")
ser.write(b"f")
lines = read_lines()
msg = next((l for l in lines if l in ("HIT!", "MISS")), "?")
state = next(l for l in lines if l.startswith("STATE:"))
print(f"  result: {msg}  {state}")

print("\n=== rotating 180 deg (12x 'a'), AI chases during each turn ===")
for i in range(12):
    ser.write(b"a")
    lines = read_lines()
sprites = next(l for l in lines if l.startswith("SPRITES:"))
e0_entry_after = next((e for e in sprites.split(",") if e.startswith("E0:")), None)
state = next(l for l in lines if l.startswith("STATE:"))
print(f"  {state}")
print(f"  E0 entry after chase: {e0_entry_after}  (was: {e0_entry})")

print("\n=== fire while facing enemy (expect HIT) ===")
ser.write(b"f")
lines = read_lines()
msg = next((l for l in lines if l in ("HIT!", "MISS")), "?")
state = next(l for l in lines if l.startswith("STATE:"))
sprites = next(l for l in lines if l.startswith("SPRITES:"))
print(f"  result: {msg}  {state}")
print(f"  E0 still in SPRITES: {'E0:' in sprites}")

ser.close()
