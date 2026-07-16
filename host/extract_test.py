# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

from PIL import Image
from wad import Wad, load_palette, decode_patch

w = Wad("../wad/doom1.wad")
pal = load_palette(w)

names = ["M_DOOM", "M_SKULL1", "M_SKULL2", "M_NGAME", "M_OPTION",
         "M_LOADG", "M_SAVEG", "M_RDTHIS", "M_QUITG"]

for name in names:
    present = name in w
    print(f"{name}: {'found' if present else 'MISSING'}")
    if not present:
        continue
    raw = w.read(name)
    width, height, left, top, pixels = decode_patch(raw, pal)
    img = Image.new("RGBA", (width, height))
    for y in range(height):
        for x in range(width):
            img.putpixel((x, y), pixels[y][x])
    img.save(f"../extracted_{name}.png")
    print(f"  {width}x{height} -> extracted_{name}.png")
