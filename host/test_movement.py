# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Raw-serial thorough test of level1.c's movement/collision/rotation,
bypassing pygame/computer-use entirely so timing is unambiguous."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=1)
time.sleep(2.5)  # boot + firmware's own noise-flush window


def drain_and_print(label):
    time.sleep(0.15)
    data = ser.read(4096).decode(errors="replace")
    for line in data.splitlines():
        if line.strip():
            print(f"  [{label}] {line.strip()}")
    return data


print("=== boot ===")
drain_and_print("boot")

print("=== walking forward 10x (one at a time, watching for collision) ===")
last_state = None
for i in range(10):
    ser.write(b"w")
    data = drain_and_print(f"w#{i+1}")
    for line in data.splitlines():
        if line.startswith("STATE:"):
            last_state = line

print(f"\nfinal state after 10x forward: {last_state}")

print("\n=== rotating left (a) 6x -- should cycle 15 deg each, 90 deg total ===")
for i in range(6):
    ser.write(b"a")
    drain_and_print(f"a#{i+1}")

print("\n=== walking forward 5x in new direction ===")
for i in range(5):
    ser.write(b"w")
    drain_and_print(f"w2#{i+1}")

print("\n=== backing up 3x (s) ===")
for i in range(3):
    ser.write(b"s")
    drain_and_print(f"s#{i+1}")

ser.close()
print("\ndone")
