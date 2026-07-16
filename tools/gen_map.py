#!/usr/bin/env python3
# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""Single source of truth for LEVEL1's map: REAL E1M1 geometry, enemies,
and items pulled straight out of doom1.wad, not invented.

Simplification (documented, not hidden): only one-sided LINEDEFS (no back
sidedef) are used as solid walls, for both collision (firmware) and
rendering (host). Two-sided linedefs (doorways, connecting corridors)
become open passages -- there's no sector/height model, so this is a
single-height version of E1M1's floor plan. The real level exit trigger
(the one linedef with special=11, "S1 Exit Level") is used as the goal;
since our controls don't include a "use" action, reaching it is enough
to trigger completion rather than requiring a switch press.

Enemies/items: E1M1's THINGS lump is filtered to a curated set of known
monster type codes (enemy) and the 2000-2999 pickup range plus keys/
backpack (item), explicitly excluding barrels (2035, treated as scenery,
not simulated) and pure decorations (candles/pillars/etc, type codes
outside both ranges). Enemies have NO combat AI or projectiles -- there's
no shooting control at all in this project -- they're collidable sprites
that are removed on contact (a simplified "melee bump" interaction).
Items are removed on walk-over (simple pickup counter, no real inventory
effects). Each gets a real WAD sprite lump where one is confidently
known and present in the WAD; otherwise it's flagged spriteless and the
host draws a generic marker instead of guessing a wrong lump name.

Emits:
  avr/src/map_data.h -- PROGMEM wall segments + start/goal + enemy/item
                        position arrays, real DOOM map units (fit int16).
  host/map_data.py   -- matching wall segments + sidedef texture names +
                        enemy/item positions + sprite lump names, for the
                        renderer (composites real WAD textures/sprites at
                        runtime via wad.compose_texture / wad.decode_patch).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "host"))
from wad import Wad, read_vertexes, read_linedefs, read_sidedefs, read_things  # noqa: E402

MAP_NAME = "E1M1"
EXIT_SPECIALS = {11, 51, 52, 124}  # S1/W1/S1-secret/W1-secret exit level
GOAL_RADIUS = 64

# type code -> best-effort real sprite lump (frame "A1" faces camera for
# monsters, "A0" is the standard single-rotation frame for pickups).
# Verified against the actual WAD at generation time, not assumed.
ENEMY_SPRITES = {
    3001: "TROOA1",  # Imp
    3002: "SARGA1",  # Demon (Pinky)
    3004: "POSSA1",  # Zombieman
    9:    "SPOSA1",  # Sergeant (shotgun guy)
    58:   "SARGA1",  # Spectre (reuses Demon sprite -- no translucency here)
}
ITEM_SPRITES = {
    2001: "SHOTA0", 2007: "CLIPA0", 2008: "SHELA0", 2011: "STIMA0",
    2012: "MEDIA0", 2013: "SOULA0", 2014: "BON1A0", 2015: "BON2A0",
    2018: "ARM1A0", 2019: "ARM2A0", 2048: "AMMOA0", 2049: "SBOXA0",
    5: "BKEYA0", 6: "YKEYA0", 13: "RKEYA0", 8: "BPAKA0",
}
BARREL_TYPE = 2035


def main():
    root = Path(__file__).parent.parent
    wad = Wad(root / "wad" / "doom1.wad")

    verts = read_vertexes(wad, MAP_NAME)
    linedefs = read_linedefs(wad, MAP_NAME)
    sidedefs = read_sidedefs(wad, MAP_NAME)
    things = read_things(wad, MAP_NAME)

    player_starts = [t for t in things if t["type"] == 1]
    if not player_starts:
        raise SystemExit(f"no Player 1 start found in {MAP_NAME}")
    start = player_starts[0]

    exits = [l for l in linedefs if l["special"] in EXIT_SPECIALS]
    if not exits:
        raise SystemExit(f"no exit linedef found in {MAP_NAME}")
    ex = exits[0]
    ev1, ev2 = verts[ex["v1"]], verts[ex["v2"]]
    goal_x = (ev1[0] + ev2[0]) // 2
    goal_y = (ev1[1] + ev2[1]) // 2

    walls = []  # (x1, y1, x2, y2, texture_name)
    for l in linedefs:
        if l["side1"] is not None:
            continue  # two-sided: open passage, not a wall
        v1, v2 = verts[l["v1"]], verts[l["v2"]]
        tex = sidedefs[l["side0"]]["mid"] or "STARTAN3"
        walls.append((v1[0], v1[1], v2[0], v2[1], tex))

    enemies = []  # (x, y, sprite_or_empty)
    for t in things:
        if t["type"] in ENEMY_SPRITES:
            sprite = ENEMY_SPRITES[t["type"]]
            if sprite not in wad:
                sprite = ""
            enemies.append((t["x"], t["y"], sprite))

    items = []  # (x, y, sprite_or_empty)
    for t in things:
        if t["type"] == BARREL_TYPE:
            continue
        if t["type"] in ITEM_SPRITES:
            sprite = ITEM_SPRITES[t["type"]]
            if sprite not in wad:
                sprite = ""
            items.append((t["x"], t["y"], sprite))
        elif 2000 <= t["type"] <= 2999:
            items.append((t["x"], t["y"], ""))  # unmapped pickup type, generic marker

    # sanity: everything must fit int16 (firmware math assumes it)
    coords = ([c for w in walls for c in w[:4]] + [start["x"], start["y"], goal_x, goal_y]
              + [c for e in enemies for c in e[:2]] + [c for i in items for c in i[:2]])
    assert all(-32768 <= c <= 32767 for c in coords), "map coordinates overflow int16"

    print(f"{MAP_NAME}: {len(walls)} solid walls, {len(enemies)} enemies "
          f"({sum(1 for e in enemies if e[2])} with real sprites), "
          f"{len(items)} items ({sum(1 for i in items if i[2])} with real sprites)")
    print(f"start=({start['x']},{start['y']}) angle={start['angle']}, goal=({goal_x},{goal_y})")

    c_lines = ", ".join(f"{{{x1},{y1},{x2},{y2}}}" for x1, y1, x2, y2, _ in walls)

    def c_points(pts):
        return ", ".join(f"{{{x},{y}}}" for x, y, _ in pts)

    c_path = root / "avr" / "src" / "map_data.h"
    c_path.write_text(
        "/* doom-avr is an artfical project\n"
        " * Copyright (C) 2026 Talha Berk Arslan\n"
        " * SPDX-License-Identifier: AGPL-3.0-or-later\n"
        " * See LICENSE for the full license text.\n"
        " *\n"
        " * GENERATED by tools/gen_map.py from real E1M1 data -- do not hand-edit. */\n"
        "#ifndef DOOM_AVR_MAP_DATA_H\n#define DOOM_AVR_MAP_DATA_H\n\n"
        "#include <avr/pgmspace.h>\n\n"
        f"#define WALL_COUNT {len(walls)}\n"
        f"#define START_X {start['x']}\n#define START_Y {start['y']}\n"
        f"#define START_ANGLE {start['angle']}\n"
        f"#define GOAL_X {goal_x}\n#define GOAL_Y {goal_y}\n#define GOAL_RADIUS {GOAL_RADIUS}\n"
        f"#define ENEMY_COUNT {len(enemies)}\n#define ITEM_COUNT {len(items)}\n\n"
        "typedef struct { int16_t x1, y1, x2, y2; } wall_t;\n"
        "typedef struct { int16_t x, y; } point_t;\n\n"
        f"static const wall_t walls[WALL_COUNT] PROGMEM = {{ {c_lines} }};\n"
        f"static const point_t enemies[ENEMY_COUNT] PROGMEM = {{ {c_points(enemies)} }};\n"
        f"static const point_t items[ITEM_COUNT] PROGMEM = {{ {c_points(items)} }};\n\n"
        "#endif\n"
    )

    py_path = root / "host" / "map_data.py"
    py_walls = ",\n    ".join(repr(w) for w in walls)
    py_enemies = ",\n    ".join(repr(e) for e in enemies)
    py_items = ",\n    ".join(repr(i) for i in items)
    py_path.write_text(
        "# doom-avr is an artfical project\n"
        "# Copyright (C) 2026 Talha Berk Arslan\n"
        "# SPDX-License-Identifier: AGPL-3.0-or-later\n"
        "# See LICENSE for the full license text.\n"
        '"""GENERATED by tools/gen_map.py from real E1M1 data -- do not hand-edit."""\n'
        f"MAP_NAME = {MAP_NAME!r}\n"
        f"START = {(start['x'], start['y'], start['angle'])!r}\n"
        f"GOAL = {(goal_x, goal_y, GOAL_RADIUS)!r}\n"
        "# (x1, y1, x2, y2, mid_texture_name)\n"
        f"WALLS = [\n    {py_walls},\n]\n"
        "# (x, y, sprite_lump_or_empty)\n"
        f"ENEMIES = [\n    {py_enemies},\n]\n"
        f"ITEMS = [\n    {py_items},\n]\n"
    )
    print(f"wrote {c_path}\nwrote {py_path}")


if __name__ == "__main__":
    main()
