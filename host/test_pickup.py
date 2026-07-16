# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Walk toward item 0 (spawned 80 units short of it) and confirm pickup
removes it and increments the pickups counter."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=5)
time.sleep(2.5)


def read_lines(n, timeout=8.0):
    lines = []
    deadline = time.time() + timeout
    while len(lines) < n and time.time() < deadline:
        raw = ser.read_until(b"\n")
        if raw:
            t = raw.decode(errors="replace").strip("\r\n")
            if t:
                lines.append(t)
    return lines


print("=== boot ===")
lines = read_lines(4)
for l in lines:
    print(f"  {l[:70]}")

for i in range(4):
    ser.write(b"w")
    lines = read_lines(3)
    state = next(l for l in lines if l.startswith("STATE:"))
    sprites = next(l for l in lines if l.startswith("SPRITES:"))
    print(f"\nw#{i+1}: {state}")
    print(f"  I0 still visible: {'I0:' in sprites}")

ser.close()
