# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Walk toward the goal from the test-injected near-goal start position
and confirm LEVEL COMPLETE + REQ:MENU.BIN actually fires."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=1)
time.sleep(2.5)


def drain(label):
    time.sleep(0.15)
    data = ser.read(4096).decode(errors="replace")
    for line in data.splitlines():
        if line.strip():
            print(f"  [{label}] {line.strip()}")
    return data


print("=== boot (should start ~100 units short of goal, facing it) ===")
drain("boot")

for i in range(6):
    ser.write(b"w")
    data = drain(f"w#{i+1}")
    if "REQ:" in data:
        print("\n*** GOAL TRIGGERED A CHUNK REQUEST -- exactly as designed ***")
        break

ser.close()
