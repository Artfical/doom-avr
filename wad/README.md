# wad/

Put your DOOM IWAD here as `doom1.wad`. **Not included in this repo** — see the main [README's Licensing section](../README.md#licensing) for why.

The free shareware release works fine (it's what this project was built and tested against — E1M1, the level `avr/src/level1.c` runs, is in it). One legitimate mirror, verified during development (`IWAD` magic, 1264 lumps, exact known size 4,196,020 bytes):

```
curl -L -o doom1.wad https://distro.ibiblio.org/pub/linux/distributions/slitaz/sources/packages/d/doom1.wad
```

If you already own a commercial IWAD (`DOOM.WAD`, `DOOM2.WAD`, etc.) from a legal copy of the game, that works too — just name it `doom1.wad` (or edit `MAP_NAME`/paths in `tools/gen_map.py` if you want a different starting level than E1M1).

Once it's here, run `python doomavr.py regen-map` if you didn't already have `avr/src/map_data.h` / `host/map_data.py` generated.
