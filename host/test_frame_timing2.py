# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Cleaner frame timing test: use read_until so partial-buffer races
can't produce misleading fast timings like the ad-hoc first version did."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=5)
time.sleep(2.5)


def read_expected_lines(n=3, timeout=8.0):
    """Read lines via read_until(b'\\n') until n non-empty lines seen."""
    lines = []
    deadline = time.time() + timeout
    while len(lines) < n and time.time() < deadline:
        raw = ser.read_until(b"\n")
        if not raw:
            continue
        text = raw.decode(errors="replace").strip("\r\n")
        if text:
            lines.append(text)
    return lines


print("=== boot ===")
lines = read_expected_lines(n=4)  # banner + STATE + FRAME + SPRITES
for l in lines:
    print(f"  {l[:80]}{'...' if len(l) > 80 else ''}")

print("\n=== 6x forward, precise timing ===")
times = []
for i in range(6):
    t0 = time.perf_counter()
    ser.write(b"w")
    lines = read_expected_lines(n=3)  # STATE, FRAME, SPRITES
    dt = time.perf_counter() - t0
    times.append(dt)
    state = next((l for l in lines if l.startswith("STATE:")), "?")
    frame = next((l for l in lines if l.startswith("FRAME:")), "")
    sprites = next((l for l in lines if l.startswith("SPRITES:")), "")
    print(f"  w#{i+1}: {dt:.3f}s  {state}  frame_len={len(frame)} sprites_len={len(sprites)}")

print(f"\navg: {sum(times)/len(times):.3f}s  min={min(times):.3f}s  max={max(times):.3f}s")
ser.close()
