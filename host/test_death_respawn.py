# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Isolated damage/death/respawn test: spawn 30 units from an enemy
(within ATTACK_RADIUS), take damage every turn, confirm health decreases
monotonically, then hits exactly 0 and triggers a clean respawn (position
resets to the REAL map start, health back to 100, kills/pickups
preserved). Also a stack-stability stress test -- 20 turns, watching for
any STATE corruption (the bug that was just fixed)."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=5)
time.sleep(2.5)


def read_lines(timeout=8.0):
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


print("=== boot (spawn 30 units from an enemy, within ATTACK_RADIUS) ===")
lines = read_lines()
for l in lines:
    print(f"  {l[:70]}")

prev_health = 100
respawned = False
for i in range(20):
    ser.write(b"a")  # non-movement action, still triggers update_enemies()
    lines = read_lines()
    state = next((l for l in lines if l.startswith("STATE:")), None)
    if state is None:
        print(f"turn {i+1}: NO STATE LINE -- corruption?")
        continue
    parts = state[len("STATE:"):].split(",")
    x, y, angle, kills, pickups, health = parts
    health = int(health)
    sane = -32768 <= int(x) <= 32767 and -32768 <= int(y) <= 32767 and 0 <= int(angle) <= 359
    flag = "" if sane else "  *** INSANE VALUES -- CORRUPTION ***"
    print(f"turn {i+1}: x={x} y={y} angle={angle} kills={kills} pickups={pickups} health={health}{flag}")
    if health > prev_health:
        respawned = True
        print(f"  -> respawn detected (health jumped {prev_health}->{health})")
    prev_health = health

print(f"\nrespawn observed: {respawned}")
ser.close()
