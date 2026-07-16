# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Push forward repeatedly until we hit a real wall and confirm the
Arduino's collision check actually stops us (position stops changing)."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=1)
time.sleep(2.5)


def read_state():
    time.sleep(0.12)
    data = ser.read(4096).decode(errors="replace")
    last = None
    for line in data.splitlines():
        line = line.strip()
        if line.startswith("STATE:"):
            last = line
        elif line:
            print(f"  [msg] {line}")
    return last


print("boot:", read_state())

prev = None
blocked_count = 0
for i in range(40):
    ser.write(b"w")
    state = read_state()
    print(f"w#{i+1}: {state}")
    if state == prev:
        blocked_count += 1
        if blocked_count >= 3:
            print(f"\n*** CONFIRMED BLOCKED after {i+1} pushes: position stable at {state} ***")
            break
    else:
        blocked_count = 0
    prev = state

ser.close()
