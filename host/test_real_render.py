# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Capture REAL FRAME/SPRITES data from the actual board and feed it
through the real render_game_frame() pipeline, saving a PNG -- proves
the full on-chip-raycast -> host-draw path end to end without needing
any desktop/screenshot tooling."""
import serial
import time
import pygame

ser = serial.Serial("COM10", 115200, timeout=5)
time.sleep(2.5)

lines = []
while len(lines) < 4:
    raw = ser.read_until(b"\n")
    if raw:
        text = raw.decode(errors="replace").strip("\r\n")
        if text:
            lines.append(text)
ser.close()

state = next(l for l in lines if l.startswith("STATE:"))
frame_line = next(l for l in lines if l.startswith("FRAME:"))
sprites_line = next(l for l in lines if l.startswith("SPRITES:"))
print("STATE:", state)
print("FRAME entries:", frame_line.count(",") + 1)
print("SPRITES entries:", sprites_line.count(",") + 1 if sprites_line[len("SPRITES:"):] else 0)

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

pygame.init()
pygame.display.set_mode((1, 1))
from wad import Wad, load_palette
from client import TextureCache, SpriteCache, render_game_frame, DOOM_W, SCALE, DOOM_H

wad = Wad("../wad/doom1.wad")
palette = load_palette(wad)
tex = TextureCache(wad, palette)
spr = SpriteCache(wad, palette)

surf = render_game_frame(tex, spr, DOOM_W * SCALE, DOOM_H * SCALE, frame_cols, sprite_list)
pygame.image.save(surf, "../real_hardware_render.png")
print("saved ../real_hardware_render.png")
