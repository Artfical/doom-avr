# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

from PIL import Image
from wad import Wad, load_palette, read_pnames, read_texture_defs, compose_texture

w = Wad("../wad/doom1.wad")
pal = load_palette(w)
pnames = read_pnames(w)
texdefs = read_texture_defs(w)

for name in ("BROWN1", "STARTAN3", "DOOR3"):
    if name not in texdefs:
        print(f"{name}: not in TEXTURE1")
        continue
    width, height, pixels = compose_texture(w, texdefs[name], pnames, pal)
    img = Image.new("RGBA", (width, height))
    for y in range(height):
        for x in range(width):
            img.putpixel((x, y), pixels[y][x])
    img.save(f"../texture_{name}.png")
    print(f"{name}: {width}x{height} -> texture_{name}.png")
