# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Regression test for the interrupt-driven UART RX buffer (common_uart.h).
Before that fix, uart_getc() polled UDR0 directly with no software buffer,
so a burst of bytes sent with zero inter-byte delay -- exactly what the
GUI's mouse-click handler does (several 'w'/'s' bytes then '\\r' back to
back) or what a fast keyboard press (arrow then immediately Enter) can
produce -- could overrun the hardware's 2-byte FIFO while the chunk was
busy elsewhere (e.g. mid-way through draw_menu()'s blocking TX writes),
silently dropping a byte. The trailing '\\r' was the one most likely to be
that dropped byte, which is exactly what was reported: arrow keys "work"
(single bytes, spaced out) but Enter "sometimes doesn't".

This reflashes MENU.BIN fresh each round and blasts "ssss\\r" with zero
delay between bytes (5 bytes back to back while the AVR is still
transmitting the previous redraw), then checks a REQ: line actually
appears -- proof '\\r' was received, not just that the board is alive.

Confirmed with a scratch instrumented build that directly reported each
received byte plus the hardware DOR (overrun) flag: the old polling-only
uart_getc() dropped 1 of 4 'ssss' bytes on overrun ("s.s.sO\\r." -- lost
byte flagged inline), the new interrupt-driven version dropped none
("s.s.s.s.\\r.") across five repeated runs."""
import subprocess
import sys
import time
import serial

PORT = "COM10"
ROUNDS = 8


def reflash_menu():
    result = subprocess.run([sys.executable, "doomavr.py", "flash", "MENU.BIN", PORT],
                             cwd="..", capture_output=True, text=True)
    if "OK" not in result.stdout and "OK" not in result.stderr:
        print(result.stdout, result.stderr)


drops = 0
for i in range(ROUNDS):
    reflash_menu()
    ser = serial.Serial(PORT, 115200, timeout=3)
    time.sleep(2.5)  # boot + firmware's own boot-noise flush window
    ser.reset_input_buffer()

    # 4x 's' (0 -> Read This!, each a real selection change so draw_menu()
    # actually runs and blocks on TX) then '\r', all with zero delay. 'w'
    # from index 0 would be a no-op (guarded, no redraw), which doesn't
    # exercise the bug at all -- this does.
    ser.write(b"ssss\r")
    time.sleep(0.5)
    data = ser.read(4096).decode(errors="replace")
    ser.close()

    got_req = "REQ:" in data
    print(f"round {i+1}: REQ seen = {got_req}" + ("" if got_req else f"  <-- DROPPED. raw: {data!r}"))
    if not got_req:
        drops += 1

print(f"\n{ROUNDS - drops}/{ROUNDS} rounds honored the burst Enter. {drops} drop(s).")
