# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Offline raycaster smoke test -- no Arduino needed. Renders a few frames
from different positions/angles in E1M1 and saves them as PNGs so the
render pipeline can be checked visually before touching real hardware."""
import pygame
from wad import Wad, load_palette
from client import TextureCache, render_game_frame, DOOM_W, DOOM_H, SCALE
import map_data

pygame.init()
pygame.display.set_mode((1, 1))  # headless-ish: need a display surface for convert/subsurface

wad = Wad("../wad/doom1.wad")
palette = load_palette(wad)
textures = TextureCache(wad, palette)

sx, sy, sa = map_data.START
tests = [
    (sx, sy, sa, "start_facing_spawn_angle"),
    (sx, sy, 90, "start_facing_north"),
    (sx, sy, 180, "start_facing_west"),
    (sx + 200, sy, 0, "moved_forward_200"),
]

for x, y, a, label in tests:
    surf = render_game_frame(textures, DOOM_W * SCALE, DOOM_H * SCALE, x, y, a)
    pygame.image.save(surf, f"../raycast_{label}.png")
    print(f"{label}: saved (pos={x},{y} angle={a})")
