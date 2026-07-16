# doom-avr is an artfical project
# Copyright (C) 2026 Talha Berk Arslan
# SPDX-License-Identifier: AGPL-3.0-or-later
# See LICENSE for the full license text.

"""doom-avr graphical host client.

Renders the REAL DOOM main menu (title logo, item patches, animated skull
cursor) using assets decoded straight from the user's doom1.wad, at native
320x200 DOOM coordinates scaled up. Takes real keyboard (arrows/Enter) and
mouse (click a menu item) input and drives whatever chunk is currently
running on the Arduino over serial, the same way a human typing w/s/Enter
would.

Loading mechanism: when the running chunk sends "REQ:<name>", this client
does NOT stream chunk bytes over the already-open connection. Instead it
closes the port, shells out to avrdude to fully reflash the chip via the
existing Optiboot bootloader (already proven reliable all session, and
far safer than hand-rolled AVR self-programming), then reopens the port.
The chip auto-resets into the new chunk as a side effect of avrdude's own
DTR toggle. This is the actual "dynamic binary loading" mechanism the
whole project is built around.

Four render modes:
  MENU -- the chunk is menu.c: draw the real title/items/skull cursor.
  GAME -- the chunk is level1.c. As of this rewrite, the Arduino itself
          computes the raycast (wall distance/texture-hit per column,
          via level1.c's cast_ray against the real E1M1 geometry) and
          streams "FRAME:"/"SPRITES:" lines describing the result; this
          client no longer computes any intersection math, it only
          samples real WAD textures/sprites and draws the pixels the
          firmware told it to. There's still no physical display, so
          something has to turn that data into pixels -- but the actual
          3D math (the "renderer") now runs on-chip.
  HELPSCREEN -- the chunk is stub_readthis.c ("Read This!"): it only
          tracks a page number ("PAGE:1"/"PAGE:2") and this client draws
          the real HELP1/HELP2 full-screen graphics from doom1.wad.
  TEXT -- any other chunk (stub_options/loadg/saveg.c): draw whatever
          text lines it prints, terminal-style. Options and Save/Load are
          real (EEPROM-backed, see avr/src/savegame.h), not placeholders
          -- they just don't need graphics, only text.

Layout constants (94,2 logo pos; x=97,y=64 items; LINEHEIGHT=16;
SKULLXOFF=-32, skull y-5) are taken directly from chocolate-doom's
src/doom/m_menu.c -- not guessed.
"""
from __future__ import annotations
import math
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pygame
import serial

sys.path.insert(0, str(Path(__file__).parent))
from wad import (Wad, load_palette, decode_patch, read_pnames,  # noqa: E402
                  read_texture_defs, compose_texture)
import map_data  # noqa: E402

SCALE = 3
DOOM_W, DOOM_H = 320, 200
ITEM_NAMES = ["New Game", "Options", "Load Game", "Save Game", "Read This!", "Quit"]
ITEM_PATCHES = ["M_NGAME", "M_OPTION", "M_LOADG", "M_SAVEG", "M_RDTHIS", "M_QUITG"]
ITEMS_X, ITEMS_Y, LINEHEIGHT = 97, 64, 16
SKULL_XOFF, SKULL_YOFF = -32, -5
LOGO_X, LOGO_Y = 94, 2

CHUNKS_DIR = Path(__file__).parent / "chunks"

NUM_COLS = 16  # MUST match level1.c's NUM_COLS -- no shared codegen for this
WALL_SCALE = 3200.0  # tuned so E1M1's corridor widths read as roughly human-scale
MOVE_REPEAT_MS = 140  # while a movement/turn key is held
SPRITE_SCALE = 2600.0  # analogous to WALL_SCALE but for billboard sprite sizing

# Real classic DOOM status bar layout, pulled from chocolate-doom's
# src/doom/st_stuff.c (ST_X/ST_Y/ST_HEALTHX/Y/ST_ARMORX/Y/ST_AMMOX/Y/
# ST_FACESX/Y), not guessed. We don't have separate ammo/armor systems
# (unlimited-ammo hitscan, no armor pickups tracked), so those two
# number slots are repurposed to show kills/pickups instead -- same
# real STTNUM digit rendering, different meaning, disclosed here.
ST_X, ST_Y = 0, 168
ST_HEALTHX, ST_HEALTHY = 90, 171   # real health %
ST_AMMOX, ST_AMMOY = 44, 171       # repurposed: kills
ST_ARMORX, ST_ARMORY = 221, 171    # repurposed: pickups
ST_FACESX, ST_FACESY = 143, 168

def _find_avrdude_conf(exe_path: str) -> str | None:
    """The ZakKemble.avr-gcc winget package's avrdude has no built-in
    default config search path -- it needs -C pointed at avrdude.conf
    explicitly regardless of whether the exe itself was found via PATH
    or the winget Links fallback below (confirmed by testing: PATH-only
    discovery without this looked like it worked, since the exe launched
    fine, but every reflash then failed with "cannot find programmer id
    arduino" -- an easy trap since the *program* starts successfully).
    First checks next to the exe itself (some installs do bundle it
    there), then globs winget's Packages tree (version string in the
    folder name changes on updates, so this can't be a fixed path)."""
    next_to_exe = Path(exe_path).parent / "avrdude.conf"
    if next_to_exe.exists():
        return str(next_to_exe)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        packages_dir = Path(local_appdata) / "Microsoft" / "WinGet" / "Packages"
        matches = list(packages_dir.glob("*avr-gcc*/**/avrdude.conf"))
        if matches:
            return str(matches[0])
    return None


def _find_avrdude() -> tuple[str, str | None]:
    """Locate avrdude without assuming any one user's machine layout.
    Tries avrdude on PATH first (apt/brew/manual installs), then the
    winget "Links" shim directory (%LOCALAPPDATA%/Microsoft/WinGet/Links)
    that `winget install ZakKemble.avr-gcc` uses on Windows, which isn't
    always on PATH in every shell. Raises a clear, actionable error if
    nothing is found, instead of silently trying a path that only ever
    existed on one dev machine."""
    exe = shutil.which("avrdude")
    if not exe:
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidate = Path(local_appdata) / "Microsoft" / "WinGet" / "Links" / "avrdude.exe"
            if candidate.exists():
                exe = str(candidate)
    if not exe:
        raise RuntimeError(
            "avrdude not found. Install it (e.g. `winget install ZakKemble.avr-gcc` "
            "on Windows, or your OS package manager elsewhere) and make sure it's "
            "on PATH -- see README.md's Requirements section."
        )
    return exe, _find_avrdude_conf(exe)


AVRDUDE_BIN, AVRDUDE_CONF = _find_avrdude()


def patch_to_surface(raw: bytes, palette) -> pygame.Surface:
    width, height, left, top, pixels = decode_patch(raw, palette)
    surf = pygame.Surface((width, height), pygame.SRCALPHA)
    for y in range(height):
        for x in range(width):
            surf.set_at((x, y), pixels[y][x])
    return surf


class TextureCache:
    """Composites real WAD wall textures on first use (via TEXTURE1+PNAMES)
    and caches the pygame Surface. A texture named in a sidedef but missing
    from TEXTURE1 (shouldn't happen with real E1M1 data, but be defensive)
    falls back to a solid color instead of crashing the renderer."""

    def __init__(self, wad: Wad, palette):
        self.wad = wad
        self.palette = palette
        self.pnames = read_pnames(wad)
        self.texdefs = read_texture_defs(wad)
        self._cache: dict[str, pygame.Surface] = {}

    def get(self, name: str) -> pygame.Surface:
        if name not in self._cache:
            if name in self.texdefs:
                w, h, pixels = compose_texture(self.wad, self.texdefs[name], self.pnames, self.palette)
            else:
                w, h, pixels = 64, 64, [[(150, 40, 40, 255)] * 64 for _ in range(64)]
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            for y in range(h):
                for x in range(w):
                    surf.set_at((x, y), pixels[y][x])
            self._cache[name] = surf
        return self._cache[name]


class SpriteCache:
    """Decodes real WAD sprite/pickup patch lumps on first use and caches
    the pygame Surface. Missing/unmapped lumps (gen_map.py already flags
    these as "") fall back to a small colored marker instead of guessing."""

    def __init__(self, wad: Wad, palette):
        self.wad = wad
        self.palette = palette
        self._cache: dict[str, pygame.Surface] = {}

    def get(self, lump: str, is_enemy: bool) -> pygame.Surface:
        key = lump or ("?E" if is_enemy else "?I")
        if key not in self._cache:
            if lump and lump in self.wad:
                w, h, _, _, pixels = decode_patch(self.wad.read(lump), self.palette)
                surf = pygame.Surface((w, h), pygame.SRCALPHA)
                for y in range(h):
                    for x in range(w):
                        surf.set_at((x, y), pixels[y][x])
            else:
                surf = pygame.Surface((24, 24), pygame.SRCALPHA)
                color = (220, 40, 40, 255) if is_enemy else (40, 200, 80, 255)
                pygame.draw.rect(surf, color, (0, 0, 24, 24))
            self._cache[key] = surf
        return self._cache[key]


def render_game_frame(textures: TextureCache, sprites: SpriteCache, render_w: int, render_h: int,
                       frame_cols: list, sprite_list: list) -> pygame.Surface:
    """Draws pixels purely from what the Arduino already computed:
    frame_cols[i] = (dist, wall_index, frac_0_255) per screen column,
    sprite_list = [(kind, index, col, dist), ...] for visible enemies/items.
    No intersection math happens here anymore -- see level1.c cast_ray."""
    surf = pygame.Surface((render_w, render_h))
    surf.fill((25, 25, 30))
    pygame.draw.rect(surf, (50, 40, 32), (0, render_h // 2, render_w, render_h - render_h // 2))

    n = max(1, len(frame_cols))
    strip_w = render_w / n
    col_heights = [0] * n  # remember wall pixel-height per column for sprite occlusion

    for col, (dist, wall_idx, frac) in enumerate(frame_cols):
        strip_x0 = int(col * strip_w)
        col_w = max(1, int(strip_w) + 1)
        if wall_idx is None or wall_idx >= len(map_data.WALLS):
            continue

        wall_h = min(render_h * 3, (render_h * WALL_SCALE) / max(1, dist) / 64.0)
        col_heights[col] = wall_h
        y0 = int(render_h / 2 - wall_h / 2)
        col_h = max(1, int(wall_h))

        texname = map_data.WALLS[wall_idx][4]
        tex_surf = textures.get(texname)
        tw, th = tex_surf.get_size()
        tex_x = int((frac / 255.0) * tw) % max(1, tw)

        shade = max(0.3, 1.0 - dist / 2200.0)
        column = tex_surf.subsurface((tex_x, 0, 1, th)).copy()
        if shade < 1.0:
            dark = pygame.Surface(column.get_size(), pygame.SRCALPHA)
            dark.fill((0, 0, 0, int((1 - shade) * 255)))
            column.blit(dark, (0, 0))
        scaled = pygame.transform.scale(column, (col_w, col_h))
        surf.blit(scaled, (strip_x0, y0))

    # sprites, back-to-front so nearer ones draw over farther ones
    for kind, idx, col, dist in sorted(sprite_list, key=lambda s: -s[3]):
        if col < 0 or col >= n:
            continue
        wall_h_here = col_heights[col] or render_h
        wall_dist_here = frame_cols[col][0] if frame_cols[col][1] is not None else 1e9
        if dist > wall_dist_here:
            continue  # occluded by a nearer wall at this column
        is_enemy = kind == "E"
        lump = (map_data.ENEMIES if is_enemy else map_data.ITEMS)[idx][2]
        sprite_surf = sprites.get(lump, is_enemy)
        size = max(4, min(render_h, int((render_h * SPRITE_SCALE) / max(1, dist) / 64.0)))
        sw, sh = sprite_surf.get_size()
        scaled = pygame.transform.scale(sprite_surf, (size, int(size * sh / sw)))
        cx = int(col * strip_w)
        cy = int(render_h / 2 + wall_h_here / 2 - scaled.get_height())
        shade = max(0.35, 1.0 - dist / 2200.0)
        if shade < 1.0:
            tinted = scaled.copy()
            dark = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            dark.fill((0, 0, 0, int((1 - shade) * 255)))
            tinted.blit(dark, (0, 0))
            scaled = tinted
        surf.blit(scaled, (cx - size // 2, cy))

    return surf


class StatusBar:
    """The real classic DOOM status bar (STBAR + STTNUM digits + STFST
    face), decoded straight from doom1.wad. See ST_* constants above for
    why the ammo/armor slots show kills/pickups instead."""

    FACE_TIERS = [(80, "STFST00"), (60, "STFST10"), (40, "STFST20"),
                  (20, "STFST30"), (0, "STFST40")]

    def __init__(self, wad: Wad, palette):
        self.bar = patch_to_surface(wad.read("STBAR"), palette)
        self.digits = [patch_to_surface(wad.read(f"STTNUM{d}"), palette) for d in range(10)]
        self.percent = patch_to_surface(wad.read("STTPRCNT"), palette)
        self.faces = {name: patch_to_surface(wad.read(name), palette)
                      for _, name in self.FACE_TIERS}
        self.dead_face = patch_to_surface(wad.read("STFDEAD0"), palette)

    def face_for(self, health: int, died: bool) -> pygame.Surface:
        if died:
            return self.dead_face
        for threshold, name in self.FACE_TIERS:
            if health >= threshold:
                return self.faces[name]
        return self.faces[self.FACE_TIERS[-1][1]]

    def draw_number(self, screen, value: int, anchor_x: int, anchor_y: int, with_percent: bool):
        s = str(max(0, min(999, int(value))))
        x = anchor_x * SCALE
        y = anchor_y * SCALE
        if with_percent:
            p = pygame.transform.scale(
                self.percent, (self.percent.get_width() * SCALE, self.percent.get_height() * SCALE))
            screen.blit(p, (x, y))
        for ch in reversed(s):
            d = self.digits[int(ch)]
            scaled = pygame.transform.scale(d, (d.get_width() * SCALE, d.get_height() * SCALE))
            x -= scaled.get_width()
            screen.blit(scaled, (x, y))

    def draw(self, screen, health: int, kills: int, pickups: int, died: bool):
        bar_scaled = pygame.transform.scale(
            self.bar, (self.bar.get_width() * SCALE, self.bar.get_height() * SCALE))
        screen.blit(bar_scaled, (ST_X * SCALE, ST_Y * SCALE))

        self.draw_number(screen, health, ST_HEALTHX, ST_HEALTHY, with_percent=True)
        self.draw_number(screen, kills, ST_AMMOX, ST_AMMOY, with_percent=False)
        self.draw_number(screen, pickups, ST_ARMORX, ST_ARMORY, with_percent=True)

        face = self.face_for(health, died)
        face_scaled = pygame.transform.scale(face, (face.get_width() * SCALE, face.get_height() * SCALE))
        screen.blit(face_scaled, (ST_FACESX * SCALE, ST_FACESY * SCALE))


def reflash(port: str, chunk_path: Path) -> bool:
    """Reflash the whole chip with chunk_path via avrdude/Optiboot. The
    board auto-resets and starts running the new chunk once this returns."""
    cmd = [AVRDUDE_BIN]
    if AVRDUDE_CONF:
        cmd += ["-C", AVRDUDE_CONF]
    cmd += ["-c", "arduino", "-p", "atmega328p",
            "-P", port, "-b", "115200", "-U", f"flash:w:{chunk_path}:r"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        print(f"[client] avrdude FAILED (exit {result.returncode}):\n{result.stderr}")
        return False
    print(f"[client] reflashed {chunk_path.name} OK")
    return True


class ArduinoLink:
    """Owns the serial connection, tracks which chunk is presumed running
    (MENU vs TEXT rendering mode), and performs reflashes on REQ:<name>."""

    def __init__(self, port: str, baud: int = 115200):
        self.port = port
        self.baud = baud
        self.ser: serial.Serial | None = None
        self._buf = b""
        self.mode = "MENU"
        self.selected = 0
        self.text_lines: list[str] = []
        self.px, self.py, self.angle = float(map_data.START[0]), float(map_data.START[1]), float(map_data.START[2])
        self.kills = 0
        self.pickups = 0
        self.health = 100
        self.frame_cols: list = []   # [(dist, wall_idx_or_None, frac), ...]
        self.sprite_list: list = []  # [(kind, idx, col, dist), ...]
        self.help_page = 1
        self.state_dirty = True
        self.disconnected = False
        self._last_reconnect_attempt = 0.0
        self._connect()

    def _connect(self) -> bool:
        """Returns True on success. Never raises -- a missing/unplugged
        board is an expected condition (the user can pull the USB cable
        at any time), not a crash."""
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0)
            time.sleep(2.0)  # Uno auto-reset-on-open + firmware's own boot-noise flush
            self._buf = b""
            self.disconnected = False
            return True
        except (serial.SerialException, OSError) as e:
            print(f"[client] can't open {self.port}: {e}")
            self.ser = None
            self.disconnected = True
            return False

    def _drop_connection(self, reason: str):
        print(f"[client] lost connection to {self.port}: {reason}")
        if self.ser is not None:
            try:
                self.ser.close()
            except (serial.SerialException, OSError):
                pass
        self.ser = None
        self.disconnected = True

    def maybe_reconnect(self):
        """Call once per frame tick. Retries opening the port every ~1.5s
        while disconnected -- covers the board being unplugged and later
        replugged (same COM port, per this session's earlier experience)."""
        if not self.disconnected:
            return
        now = time.time()
        if now - self._last_reconnect_attempt < 1.5:
            return
        self._last_reconnect_attempt = now
        if self._connect():
            print(f"[client] reconnected to {self.port}")

    def send(self, cmd: bytes):
        if self.ser is None:
            return
        try:
            self.ser.write(cmd)
        except (serial.SerialException, OSError) as e:
            self._drop_connection(str(e))

    def poll(self):
        if self.ser is None:
            return
        try:
            chunk = self.ser.read(4096)
        except (serial.SerialException, OSError) as e:
            self._drop_connection(str(e))
            return
        if not chunk:
            return
        self._buf += chunk
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            self._handle_line(line.decode(errors="replace").strip("\r\n"))

    def _handle_line(self, line: str):
        if not line:
            return
        if line.startswith("REQ:"):
            name = line[len("REQ:"):].strip()
            print(f"[client] Arduino requested chunk: {name!r}")
            self._reflash_to(name)
        elif line.startswith("STATE:"):
            try:
                x, y, a, k, p, h = line[len("STATE:"):].split(",")
                self.px, self.py, self.angle = float(x), float(y), float(a)
                self.kills, self.pickups, self.health = int(k), int(p), int(h)
                self.state_dirty = True
            except ValueError:
                pass
        elif line.startswith("FRAME:"):
            cols = []
            for entry in line[len("FRAME:"):].split(","):
                try:
                    d, w, f = entry.split(":")
                    wi = int(w)
                    cols.append((int(d), wi if wi != 65535 else None, int(f)))
                except ValueError:
                    cols.append((9999, None, 0))
            self.frame_cols = cols
            self.state_dirty = True
        elif line.startswith("SPRITES:"):
            body = line[len("SPRITES:"):].strip()
            sprites = []
            if body:
                for entry in body.split(","):
                    try:
                        kind = entry[0]
                        idx_str, col_str, dist_str = entry[1:].split(":")
                        sprites.append((kind, int(idx_str), int(col_str), int(dist_str)))
                    except (ValueError, IndexError):
                        pass
            self.sprite_list = sprites
        elif line.startswith("PAGE:"):
            try:
                self.help_page = int(line[len("PAGE:"):].strip())
                self.state_dirty = True
            except ValueError:
                pass
        elif self.mode == "MENU" and line.strip().startswith(">"):
            try:
                self.selected = ITEM_NAMES.index(line.strip()[2:])
            except ValueError:
                pass
        elif self.mode in ("TEXT", "GAME"):
            self.text_lines.append(line)
            self.text_lines = self.text_lines[-12:]
        # "--- DOOM ---" and blank separator lines from menu.c: ignored,
        # this client renders its own title from real WAD graphics.

    def _reflash_to(self, name: str):
        path = CHUNKS_DIR / name
        if not path.exists():
            print(f"[client] {name} not found in {CHUNKS_DIR}, staying put")
            return
        if self.ser is not None:
            try:
                self.ser.close()
            except (serial.SerialException, OSError):
                pass
            self.ser = None

        # avrdude blocks this thread for a few seconds (erase+write+verify).
        # Paint one "loading" frame before that freeze starts, or the whole
        # window looks hung/broken with no feedback until it's done.
        surf = pygame.display.get_surface()
        if surf is not None:
            surf.fill((0, 0, 0))
            loading_font = pygame.font.SysFont("consolas", 28, bold=True)
            msg = loading_font.render(f"Loading {name} ...", True, (255, 255, 0))
            surf.blit(msg, (surf.get_width() // 2 - msg.get_width() // 2,
                             surf.get_height() // 2 - msg.get_height() // 2))
            pygame.display.flip()

        ok = reflash(self.port, path)
        self.selected = 0
        self.text_lines = []
        self.state_dirty = True
        if ok:
            if name == "MENU.BIN":
                self.mode = "MENU"
            elif name == "LEVEL1.BIN":
                self.mode = "GAME"
                self.px, self.py, self.angle = float(map_data.START[0]), float(map_data.START[1]), float(map_data.START[2])
                self.kills = self.pickups = 0
                self.health = 100
                self.frame_cols = []
                self.sprite_list = []
            elif name == "HELP.BIN":
                self.mode = "HELPSCREEN"
                self.help_page = 1
            else:
                self.mode = "TEXT"
        else:
            # Don't switch to GAME/MENU on a failed flash -- the chip is
            # still running whatever it was running before, but nothing
            # here matches that anymore. TEXT mode at least SHOWS the
            # failure instead of leaving a blank/stuck GAME screen.
            self.mode = "TEXT"
            self.text_lines = [f"avrdude failed to flash {name}", "check host console"]
        self._connect()


def render_text_mode(screen, font, lines: list[str]):
    screen.fill((0, 0, 0))
    y = 40
    header = font.render("doom-avr", True, (255, 80, 80))
    screen.blit(header, (40, y))
    y += 50
    for line in lines:
        surf = font.render(line, True, (200, 200, 200))
        screen.blit(surf, (40, y))
        y += 28
    hint = font.render("(Enter to go back, where supported)", True, (100, 100, 110))
    screen.blit(hint, (40, y + 20))


def main():
    if len(sys.argv) < 2:
        print("usage: client.py <COM_PORT>")
        sys.exit(1)
    port = sys.argv[1]

    wad_path = Path(__file__).parent.parent / "wad" / "doom1.wad"
    wad = Wad(wad_path)
    palette = load_palette(wad)

    logo = patch_to_surface(wad.read("M_DOOM"), palette)
    item_surfs = [patch_to_surface(wad.read(n), palette) for n in ITEM_PATCHES]
    skull_frames = [patch_to_surface(wad.read(f"M_SKULL{i}"), palette) for i in (1, 2)]
    textures = TextureCache(wad, palette)
    sprites = SpriteCache(wad, palette)
    status_bar = StatusBar(wad, palette)
    help_pages = {1: patch_to_surface(wad.read("HELP1"), palette),
                  2: patch_to_surface(wad.read("HELP2"), palette)}

    arduino = ArduinoLink(port)

    pygame.init()
    screen = pygame.display.set_mode((DOOM_W * SCALE, DOOM_H * SCALE))
    pygame.display.set_caption("doom-avr - real menu assets, live Arduino state")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)
    big_font = pygame.font.SysFont("consolas", 30, bold=True)

    def to_screen(surf):
        return pygame.transform.scale(surf, (surf.get_width() * SCALE, surf.get_height() * SCALE))

    logo_s = to_screen(logo)
    item_s = [to_screen(s) for s in item_surfs]
    skull_s = [to_screen(s) for s in skull_frames]

    item_rects = []
    for i, surf in enumerate(item_s):
        y = ITEMS_Y + i * LINEHEIGHT
        item_rects.append((pygame.Rect(ITEMS_X * SCALE, y * SCALE,
                                        surf.get_width(), surf.get_height()), i))

    skull_frame = 0
    skull_timer = 0.0
    game_frame_cache = None
    move_repeat_timer = 0.0
    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        arduino.poll()
        arduino.maybe_reconnect()

        skull_timer += dt
        if skull_timer > 0.15:
            skull_timer = 0.0
            skull_frame ^= 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif arduino.mode == "MENU":
                    # Update the on-screen selection immediately, don't wait
                    # for the Arduino's "> ItemName" confirmation line --
                    # with any serial lag (or no board attached at all) that
                    # round-trip wait made keypresses look like they were
                    # being ignored. The Arduino is still sent the same
                    # byte and remains authoritative for what actually gets
                    # loaded on Enter; this is just local UI responsiveness.
                    if event.key in (pygame.K_UP, pygame.K_w):
                        arduino.selected = max(0, arduino.selected - 1)
                        arduino.send(b"w")
                    elif event.key in (pygame.K_DOWN, pygame.K_s):
                        arduino.selected = min(len(ITEM_NAMES) - 1, arduino.selected + 1)
                        arduino.send(b"s")
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        arduino.send(b"\r")
                elif arduino.mode in ("TEXT", "HELPSCREEN"):
                    if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        arduino.send(b"\r")
                elif arduino.mode == "GAME":
                    if event.key == pygame.K_SPACE:
                        arduino.send(b"f")  # fire is a discrete action, not held-repeat
                    elif event.key == pygame.K_q:
                        arduino.send(b"q")  # save to EEPROM, see avr/src/savegame.h
                # GAME mode movement is handled below via held-key polling,
                # not KEYDOWN, so forward/back/turn feel continuous.
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if arduino.mode == "MENU":
                    for rect, idx in item_rects:
                        if rect.collidepoint(event.pos):
                            delta = idx - arduino.selected
                            step = b"s" if delta > 0 else b"w"
                            arduino.selected = idx  # immediate local feedback, see KEYDOWN comment above
                            for _ in range(abs(delta)):
                                arduino.send(step)
                            arduino.send(b"\r")
                            break
                elif arduino.mode == "GAME":
                    arduino.send(b"f")  # left-click also fires, common FPS convention

        if arduino.mode == "GAME":
            move_repeat_timer -= dt * 1000
            if move_repeat_timer <= 0:
                keys = pygame.key.get_pressed()
                sent = False
                if keys[pygame.K_UP] or keys[pygame.K_w]:
                    arduino.send(b"w"); sent = True
                elif keys[pygame.K_DOWN] or keys[pygame.K_s]:
                    arduino.send(b"s"); sent = True
                if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                    arduino.send(b"a"); sent = True
                elif keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                    arduino.send(b"d"); sent = True
                if sent:
                    move_repeat_timer = MOVE_REPEAT_MS

        if arduino.mode == "MENU":
            screen.fill((0, 0, 0))
            screen.blit(logo_s, (LOGO_X * SCALE, LOGO_Y * SCALE))
            for i, surf in enumerate(item_s):
                y = ITEMS_Y + i * LINEHEIGHT
                screen.blit(surf, (ITEMS_X * SCALE, y * SCALE))
            skull_y = ITEMS_Y + SKULL_YOFF + arduino.selected * LINEHEIGHT
            screen.blit(skull_s[skull_frame], ((ITEMS_X + SKULL_XOFF) * SCALE, skull_y * SCALE))
        elif arduino.mode == "GAME":
            if (arduino.state_dirty or game_frame_cache is None) and arduino.frame_cols:
                game_frame_cache = render_game_frame(
                    textures, sprites, DOOM_W * SCALE, DOOM_H * SCALE,
                    arduino.frame_cols, arduino.sprite_list)
                arduino.state_dirty = False
            if game_frame_cache is not None:
                screen.blit(game_frame_cache, (0, 0))

            just_died = bool(arduino.text_lines) and "DIED" in arduino.text_lines[-1]
            status_bar.draw(screen, arduino.health, arduino.kills, arduino.pickups, just_died)

            crosshair_x, crosshair_y = DOOM_W * SCALE // 2, (ST_Y * SCALE) // 2
            pygame.draw.line(screen, (255, 255, 255), (crosshair_x - 8, crosshair_y),
                              (crosshair_x + 8, crosshair_y), 2)
            pygame.draw.line(screen, (255, 255, 255), (crosshair_x, crosshair_y - 8),
                              (crosshair_x, crosshair_y + 8), 2)

            if arduino.text_lines:
                last = arduino.text_lines[-1]
                if "COMPLETE" in last:
                    msg = font.render(last, True, (0, 255, 0))
                    screen.blit(msg, (DOOM_W * SCALE // 2 - 100, DOOM_H * SCALE // 2 - 40))
                elif "DIED" in last:
                    msg = font.render(last, True, (255, 40, 40))
                    screen.blit(msg, (DOOM_W * SCALE // 2 - 140, DOOM_H * SCALE // 2 - 40))
                elif last in ("HIT!", "MISS"):
                    msg = font.render(last, True, (0, 255, 0) if last == "HIT!" else (150, 150, 150))
                    screen.blit(msg, (crosshair_x + 16, crosshair_y - 10))
                elif last == "SAVED":
                    msg = font.render("Game saved", True, (0, 255, 0))
                    screen.blit(msg, (10, 10))
        elif arduino.mode == "HELPSCREEN":
            page = help_pages.get(arduino.help_page, help_pages[1])
            scaled = pygame.transform.scale(page, (DOOM_W * SCALE, DOOM_H * SCALE))
            screen.blit(scaled, (0, 0))
            hint = font.render("(Enter to continue)", True, (255, 255, 0))
            screen.blit(hint, (10, DOOM_H * SCALE - 26))
        else:
            render_text_mode(screen, font, arduino.text_lines)

        if arduino.disconnected:
            overlay = pygame.Surface((DOOM_W * SCALE, 60), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 230))
            screen.blit(overlay, (0, 0))
            msg = big_font.render("ARDUINO NOT CONNECTED", True, (255, 60, 60))
            screen.blit(msg, ((DOOM_W * SCALE - msg.get_width()) // 2, 6))
            sub = font.render(f"looking for {arduino.port} -- input has nothing to reach until it's plugged back in",
                               True, (220, 220, 220))
            screen.blit(sub, ((DOOM_W * SCALE - sub.get_width()) // 2, 38))

        fps_surf = font.render(f"{clock.get_fps():.0f} FPS", True, (0, 255, 0))
        screen.blit(fps_surf, (DOOM_W * SCALE - fps_surf.get_width() - 8, 6))

        pygame.display.flip()

    pygame.quit()
    if arduino.ser is not None:
        try:
            arduino.ser.close()
        except (serial.SerialException, OSError):
            pass


if __name__ == "__main__":
    main()
