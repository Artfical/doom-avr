# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Capture real FRAME/SPRITES data at several angles after the aggressive
candidate-filter optimization, render each, and save PNGs -- checking the
tighter FOV-cone reject didn't introduce visible gaps/missing walls."""
import serial
import time
import pygame

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


def parse_and_render(lines, label, tex, spr):
    frame_line = next(l for l in lines if l.startswith("FRAME:"))
    sprites_line = next(l for l in lines if l.startswith("SPRITES:"))
    frame_cols = []
    for entry in frame_line[len("FRAME:"):].split(","):
        d, w, f = entry.split(":")
        wi = int(w)
        frame_cols.append((int(d), wi if wi != 65535 else None, int(f)))
    sprite_list = []
    body = sprites_line[len("SPRITES:"):].strip()
    if body:
        for entry in body.split(","):
            kind = entry[0]
            idx_s, col_s, dist_s = entry[1:].split(":")
            sprite_list.append((kind, int(idx_s), int(col_s), int(dist_s)))
    surf = render_game_frame(tex, spr, DOOM_W * SCALE, DOOM_H * SCALE, frame_cols, sprite_list)
    pygame.image.save(surf, f"../regress_{label}.png")
    print(f"{label}: saved, {len(frame_cols)} cols, {len(sprite_list)} sprites")


pygame.init()
pygame.display.set_mode((1, 1))
from wad import Wad, load_palette
from client import TextureCache, SpriteCache, render_game_frame, DOOM_W, SCALE, DOOM_H

wad = Wad("../wad/doom1.wad")
palette = load_palette(wad)
tex = TextureCache(wad, palette)
spr = SpriteCache(wad, palette)

lines = read_lines(4)
parse_and_render(lines, "angle0", tex, spr)

for turn in range(6):
    ser.write(b"a")
    lines = read_lines(3)
state = next(l for l in lines if l.startswith("STATE:"))
print("after 6x turn:", state)
parse_and_render(lines, "angle90", tex, spr)

for turn in range(6):
    ser.write(b"a")
    lines = read_lines(3)
state = next(l for l in lines if l.startswith("STATE:"))
print("after 12x turn:", state)
parse_and_render(lines, "angle180", tex, spr)

ser.close()
