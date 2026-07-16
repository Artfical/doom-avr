# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Walk toward enemy 0 (spawned 80 units short of it by the test build)
and confirm the melee-bump kill actually removes it and increments kills."""
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
sprites0 = next(l for l in lines if l.startswith("SPRITES:"))
print(f"\nE0 visible before bump: {'E0:' in sprites0}")

for i in range(3):
    ser.write(b"w")
    lines = read_lines(3)
    state = next(l for l in lines if l.startswith("STATE:"))
    sprites = next(l for l in lines if l.startswith("SPRITES:"))
    print(f"\nw#{i+1}: {state}")
    print(f"  E0 still visible: {'E0:' in sprites}")

ser.close()
