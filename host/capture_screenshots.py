# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Generates docs/screenshots/*.png by driving the REAL board over serial
and rendering with the REAL client.py rendering functions -- every pixel
here comes from actual hardware + actual WAD data, not a mockup."""
import sys
import time
from pathlib import Path

import pygame
import serial

sys.path.insert(0, str(Path(__file__).parent))

PORT = "COM10"
OUT = Path(__file__).parent.parent / "docs" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)


def read_lines(ser, timeout=8.0, stop_on=("SPRITES:", "PAGE:")):
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.read_until(b"\n")
        if raw:
            t = raw.decode(errors="replace").strip("\r\n")
            if t:
                lines.append(t)
                if any(t.startswith(s) for s in stop_on):
                    break
    return lines


def flash(name):
    from client import reflash
    ok = reflash(PORT, Path("chunks") / name)
    print(f"flash {name}: {'OK' if ok else 'FAILED'}")
    return ok


pygame.init()
pygame.display.set_mode((1, 1))

from wad import Wad, load_palette, decode_patch  # noqa: E402
from client import (TextureCache, SpriteCache, StatusBar, render_game_frame,  # noqa: E402
                     patch_to_surface, render_text_mode, DOOM_W, DOOM_H, SCALE,
                     ITEM_PATCHES, ITEMS_X, ITEMS_Y, LINEHEIGHT, SKULL_XOFF, SKULL_YOFF, LOGO_X, LOGO_Y)

wad = Wad("../wad/doom1.wad")
palette = load_palette(wad)
textures = TextureCache(wad, palette)
sprites = SpriteCache(wad, palette)
status_bar = StatusBar(wad, palette)
font = pygame.font.SysFont("consolas", 20)

# ---- 1. Main menu, "New Game" selected -------------------------------
print("=== menu.png ===")
logo = patch_to_surface(wad.read("M_DOOM"), palette)
item_surfs = [patch_to_surface(wad.read(n), palette) for n in ITEM_PATCHES]
skull = patch_to_surface(wad.read("M_SKULL1"), palette)


def to_screen(surf):
    return pygame.transform.scale(surf, (surf.get_width() * SCALE, surf.get_height() * SCALE))


surf = pygame.Surface((DOOM_W * SCALE, DOOM_H * SCALE))
surf.fill((0, 0, 0))
surf.blit(to_screen(logo), (LOGO_X * SCALE, LOGO_Y * SCALE))
for i, s in enumerate(item_surfs):
    y = ITEMS_Y + i * LINEHEIGHT
    surf.blit(to_screen(s), (ITEMS_X * SCALE, y * SCALE))
skull_y = ITEMS_Y + SKULL_YOFF + 0 * LINEHEIGHT
surf.blit(to_screen(skull), ((ITEMS_X + SKULL_XOFF) * SCALE, skull_y * SCALE))
pygame.image.save(surf, str(OUT / "menu.png"))
print("saved menu.png")

# ---- 2 & 3. In-game E1M1 + status bar close-up, real captured frame --
print("=== game.png / statusbar_closeup.png ===")
flash("LEVEL1.BIN")
ser = serial.Serial(PORT, 115200, timeout=8)
time.sleep(2.5)
lines = read_lines(ser)
# walk forward a few steps so the view isn't the very first static frame
for _ in range(3):
    ser.write(b"w")
    lines = read_lines(ser)
state = next(l for l in lines if l.startswith("STATE:"))
x, y, angle, kills, pickups, health = state[len("STATE:"):].split(",")
frame_line = next(l for l in lines if l.startswith("FRAME:"))
sprites_line = next(l for l in lines if l.startswith("SPRITES:"))
ser.close()

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

game_surf = render_game_frame(textures, sprites, DOOM_W * SCALE, DOOM_H * SCALE, frame_cols, sprite_list)
full = pygame.Surface((DOOM_W * SCALE, DOOM_H * SCALE))
full.blit(game_surf, (0, 0))
status_bar.draw(full, int(health), int(kills), int(pickups), died=False)
crosshair_x, crosshair_y = DOOM_W * SCALE // 2, (168 * SCALE) // 2
pygame.draw.line(full, (255, 255, 255), (crosshair_x - 8, crosshair_y), (crosshair_x + 8, crosshair_y), 2)
pygame.draw.line(full, (255, 255, 255), (crosshair_x, crosshair_y - 8), (crosshair_x, crosshair_y + 8), 2)
pygame.image.save(full, str(OUT / "game.png"))
print("saved game.png")

statusbar_crop = full.subsurface((0, 168 * SCALE, DOOM_W * SCALE, (DOOM_H - 168) * SCALE)).copy()
pygame.image.save(statusbar_crop, str(OUT / "statusbar_closeup.png"))
print("saved statusbar_closeup.png")

# ---- 4. Options screen, real captured text ----------------------------
print("=== options.png ===")
flash("OPTIONS.BIN")
ser = serial.Serial(PORT, 115200, timeout=5)
time.sleep(2.5)
lines = read_lines(ser, stop_on=("(w/s",))
ser.write(b"d")  # bump turn speed once so the screenshot shows a non-default value changing
lines2 = read_lines(ser, stop_on=("(w/s",))
ser.close()
text_lines = [l for l in (lines + lines2) if l and not l.startswith("---")]
opt_surf = pygame.Surface((DOOM_W * SCALE, DOOM_H * SCALE))
render_text_mode(opt_surf, font, text_lines[-8:])
pygame.image.save(opt_surf, str(OUT / "options.png"))
print("saved options.png")

# ---- 5. Read This! (real HELP1 WAD graphic) ---------------------------
print("=== help.png ===")
help1 = patch_to_surface(wad.read("HELP1"), palette)
help_surf = pygame.transform.scale(help1, (DOOM_W * SCALE, DOOM_H * SCALE))
pygame.image.save(help_surf, str(OUT / "help.png"))
print("saved help.png")

# ---- 6. Real serial output, terminal-style render ----------------------
print("=== serial_output.png ===")
flash("MENU.BIN")
ser = serial.Serial(PORT, 115200, timeout=5)
time.sleep(2.5)
boot_text = ser.read(500).decode(errors="replace")
ser.write(b"s")
time.sleep(0.3)
after_s = ser.read(500).decode(errors="replace")
ser.write(b"\r")
time.sleep(0.3)
after_enter = ser.read(500).decode(errors="replace")
ser.close()

full_text = (boot_text + "\n$ (pressed 's')\n" + after_s
             + "\n$ (pressed Enter -- REQ sent to host)\n" + after_enter)
term_lines = [l.replace("\r", "") for l in full_text.split("\n")]
mono = pygame.font.SysFont("consolas", 18)
pad, line_h, title_h = 24, 24, 40
width = 720
height = title_h + pad * 2 + line_h * len(term_lines)
term = pygame.Surface((width, height))
term.fill((14, 14, 16))
pygame.draw.rect(term, (48, 48, 52), (0, 0, width, title_h))
for i, (cx, c) in enumerate([(16, (255, 95, 86)), (40, (255, 189, 46)), (64, (39, 201, 63))]):
    pygame.draw.ellipse(term, c, (cx, 12, 16, 16))
term.blit(mono.render("COM10 - 115200 8N1 - real Arduino, real menu.c", True, (220, 220, 220)), (90, 10))
yy = title_h + pad
for line in term_lines:
    if not line.strip():
        yy += line_h
        continue
    color = (139, 233, 253) if line.startswith("---") else (
        (80, 250, 123) if line.strip().startswith(">") else (
            (255, 121, 198) if line.startswith("REQ:") else (
                (120, 120, 130) if line.startswith("$") else (170, 170, 170))))
    term.blit(mono.render(line, True, color), (pad, yy))
    yy += line_h
pygame.image.save(term, str(OUT / "serial_output.png"))
print("saved serial_output.png")

print("\nAll screenshots written to", OUT)
