# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Measure real on-hardware FRAME computation latency and sanity-check
the wire format (STATE/FRAME/SPRITES) parses correctly."""
import serial
import time

ser = serial.Serial("COM10", 115200, timeout=2)
time.sleep(2.5)


def read_lines(timeout=5.0):
    deadline = time.time() + timeout
    buf = b""
    lines = []
    while time.time() < deadline:
        chunk = ser.read(4096)
        if chunk:
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                lines.append(line.decode(errors="replace").strip("\r\n"))
            if any(l.startswith("SPRITES:") for l in lines):
                break
    return lines


print("=== boot ===")
t0 = time.time()
lines = read_lines()
boot_dt = time.time() - t0
for l in lines:
    if l.startswith("FRAME:"):
        print(f"  FRAME: {len(l)} chars, {l.count(',')+1} columns")
        print(f"  first 3 entries: {l[len('FRAME:'):].split(',')[:3]}")
    elif l.startswith("SPRITES:"):
        print(f"  SPRITES: {l[:120]}{'...' if len(l) > 120 else ''}")
    else:
        print(f"  {l}")
print(f"boot-to-first-frame: {boot_dt:.2f}s")

print("\n=== timing 5x forward moves ===")
times = []
for i in range(5):
    t0 = time.time()
    ser.write(b"w")
    lines = read_lines()
    dt = time.time() - t0
    times.append(dt)
    state = next((l for l in lines if l.startswith("STATE:")), None)
    print(f"  w#{i+1}: {dt:.3f}s  {state}")

print(f"\navg frame latency: {sum(times)/len(times):.3f}s")
ser.close()
