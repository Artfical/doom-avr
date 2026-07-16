# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Minimal DOOM WAD reader + patch/picture decoder + palette loader.

Only what's needed to pull menu-screen graphics (title pic, menu item
patches, skull cursor, credits/help screens, PLAYPAL) out of an IWAD for
the doom-avr host client. Not a general-purpose WAD library.
"""
from __future__ import annotations
import struct
from pathlib import Path


class Wad:
    def __init__(self, path: str | Path):
        self.data = Path(path).read_bytes()
        magic, numlumps, infotableofs = struct.unpack_from("<4sii", self.data, 0)
        if magic not in (b"IWAD", b"PWAD"):
            raise ValueError(f"not a WAD file (magic={magic!r})")
        self.lumps = {}  # name -> (offset, size), last one wins (like real WAD lookup)
        self.order = []
        for i in range(numlumps):
            off, size, name = struct.unpack_from("<ii8s", self.data, infotableofs + i * 16)
            name = name.rstrip(b"\0").decode("ascii", errors="replace")
            self.lumps[name] = (off, size)
            self.order.append(name)

    def read(self, name: str) -> bytes:
        off, size = self.lumps[name]
        return self.data[off:off + size]

    def __contains__(self, name: str) -> bool:
        return name in self.lumps


def load_palette(wad: Wad, index: int = 0) -> list[tuple[int, int, int]]:
    """PLAYPAL is 14 palettes of 256 RGB triples, 768 bytes each."""
    raw = wad.read("PLAYPAL")
    base = index * 768
    return [tuple(raw[base + i * 3: base + i * 3 + 3]) for i in range(256)]


def decode_patch(raw: bytes, palette: list[tuple[int, int, int]]):
    """Decode a DOOM 'patch' (picture) lump into (width, height, rgba_rows).

    Format: header {width, height, leftoffset, topoffset}:int16 x4, then
    `width` int32 column offsets, then per-column posts:
        {topdelta:u8, length:u8, pad:u8, pixels[length]:u8, pad:u8}
    terminated by topdelta==0xFF. Transparent pixels stay unset (alpha=0).
    """
    width, height, left, top = struct.unpack_from("<hhhh", raw, 0)
    col_offs = struct.unpack_from(f"<{width}i", raw, 8)
    pixels = [[(0, 0, 0, 0)] * width for _ in range(height)]
    for x, off in enumerate(col_offs):
        pos = off
        while True:
            topdelta = raw[pos]
            if topdelta == 0xFF:
                break
            length = raw[pos + 1]
            pos += 3  # topdelta, length, unused padding byte
            for i in range(length):
                y = topdelta + i
                if 0 <= y < height:
                    r, g, b = palette[raw[pos + i]]
                    pixels[y][x] = (r, g, b, 255)
            pos += length + 1  # pixel data + trailing padding byte
    return width, height, left, top, pixels


# ---- map geometry ---------------------------------------------------------

def read_vertexes(wad: Wad, map_name: str) -> list[tuple[int, int]]:
    raw = _map_lump(wad, map_name, "VERTEXES")
    return [struct.unpack_from("<hh", raw, i * 4) for i in range(len(raw) // 4)]


def read_linedefs(wad: Wad, map_name: str) -> list[dict]:
    raw = _map_lump(wad, map_name, "LINEDEFS")
    out = []
    for i in range(len(raw) // 14):
        v1, v2, flags, special, tag, side0, side1 = struct.unpack_from("<hhhhhhh", raw, i * 14)
        out.append({"v1": v1, "v2": v2, "flags": flags, "special": special, "tag": tag,
                     "side0": side0 if side0 != -1 else None,
                     "side1": side1 if side1 != -1 else None})
    return out


def read_sidedefs(wad: Wad, map_name: str) -> list[dict]:
    raw = _map_lump(wad, map_name, "SIDEDEFS")
    out = []
    for i in range(len(raw) // 30):
        xoff, yoff, top, bottom, mid, sector = struct.unpack_from("<hh8s8s8sh", raw, i * 30)
        clean = lambda b: b.rstrip(b"\0").decode("ascii", errors="replace").upper()
        out.append({"top": clean(top), "bottom": clean(bottom), "mid": clean(mid), "sector": sector})
    return out


def read_things(wad: Wad, map_name: str) -> list[dict]:
    raw = _map_lump(wad, map_name, "THINGS")
    out = []
    for i in range(len(raw) // 10):
        x, y, angle, ttype, options = struct.unpack_from("<hhhhh", raw, i * 10)
        out.append({"x": x, "y": y, "angle": angle, "type": ttype})
    return out


def _map_lump(wad: Wad, map_name: str, lump_name: str) -> bytes:
    idx = wad.order.index(map_name)
    # standard map lump order after the marker: THINGS,LINEDEFS,SIDEDEFS,
    # VERTEXES,SEGS,SSECTORS,NODES,SECTORS,REJECT,BLOCKMAP
    offset = ["THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES", "SEGS",
              "SSECTORS", "NODES", "SECTORS", "REJECT", "BLOCKMAP"].index(lump_name)
    name = wad.order[idx + 1 + offset]
    if name != lump_name:
        raise ValueError(f"expected {lump_name} at offset {offset} after {map_name}, found {name}")
    return wad.read(name)


# ---- composite wall textures (TEXTURE1 + PNAMES) --------------------------

def read_pnames(wad: Wad) -> list[str]:
    raw = wad.read("PNAMES")
    (count,) = struct.unpack_from("<i", raw, 0)
    names = []
    for i in range(count):
        (name,) = struct.unpack_from("<8s", raw, 4 + i * 8)
        names.append(name.rstrip(b"\0").decode("ascii", errors="replace").upper())
    return names


def read_texture_defs(wad: Wad, lump_name: str = "TEXTURE1") -> dict:
    """Returns {texture_name: {width, height, patches: [(originx, originy, patch_index)]}}"""
    raw = wad.read(lump_name)
    (numtextures,) = struct.unpack_from("<i", raw, 0)
    offsets = struct.unpack_from(f"<{numtextures}i", raw, 4)
    defs = {}
    for off in offsets:
        name, masked, width, height, coldir, patchcount = struct.unpack_from("<8siHHiH", raw, off)
        name = name.rstrip(b"\0").decode("ascii", errors="replace").upper()
        patches = []
        p = off + 22
        for _ in range(patchcount):
            originx, originy, patch_idx, stepdir, colormap = struct.unpack_from("<hhhhh", raw, p)
            patches.append((originx, originy, patch_idx))
            p += 10
        defs[name] = {"width": width, "height": height, "patches": patches}
    return defs


def compose_texture(wad: Wad, texdef: dict, pnames: list[str], palette) -> tuple[int, int, list]:
    """Composite a TEXTURE1 definition into an RGBA pixel grid by blitting
    its constituent patches at their defined origins."""
    width, height = texdef["width"], texdef["height"]
    pixels = [[(0, 0, 0, 0)] * width for _ in range(height)]
    for originx, originy, patch_idx in texdef["patches"]:
        patch_name = pnames[patch_idx]
        if patch_name not in wad:
            continue
        pw, ph, _, _, ppixels = decode_patch(wad.read(patch_name), palette)
        for py in range(ph):
            dy = originy + py
            if not (0 <= dy < height):
                continue
            for px in range(pw):
                dx = originx + px
                if not (0 <= dx < width):
                    continue
                r, g, b, a = ppixels[py][px]
                if a:
                    pixels[dy][dx] = (r, g, b, a)
    return width, height, pixels
