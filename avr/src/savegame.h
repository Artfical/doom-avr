/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* EEPROM-backed save/settings, shared by level1.c, stub_loadg.c,
 * stub_saveg.c, and stub_options.c. EEPROM (1KB on the ATmega328P) is the
 * only storage that survives a chunk reflash -- program flash gets fully
 * overwritten on every REQ, and RAM resets on every reboot -- so it's the
 * one channel chunks have to hand data to each other across a swap. Used
 * two ways here: (1) Load Game sets a flag + leaves save data in EEPROM,
 * then REQs LEVEL1.BIN, which reads that flag at boot; (2) Options writes
 * settings LEVEL1.BIN reads at boot too.
 *
 * Bitset fields are sized generously (16 bytes = up to 128 entries) rather
 * than tied exactly to the current ENEMY_COUNT/ITEM_COUNT (103/85), so a
 * future re-run of tools/gen_map.py with a different map can't silently
 * overflow this layout -- level1.c has a compile-time check that the
 * actual counts still fit before using it.
 */
#ifndef DOOM_AVR_SAVEGAME_H
#define DOOM_AVR_SAVEGAME_H

#include <avr/eeprom.h>
#include <stdint.h>

#define EE_MAGIC_ADDR         ((uint8_t *)0)
#define EE_MAGIC_VALUE        0xA5
#define EE_LOAD_FLAG_ADDR     ((uint8_t *)1)
#define EE_PX_ADDR            ((int16_t *)2)
#define EE_PY_ADDR            ((int16_t *)4)
#define EE_ANGLE_ADDR         ((int16_t *)6)
#define EE_HEALTH_ADDR        ((uint8_t *)8)
#define EE_KILLS_ADDR         ((uint16_t *)9)
#define EE_PICKUPS_ADDR       ((uint16_t *)11)
#define EE_ENEMY_BITSET_ADDR  ((uint8_t *)13)
#define EE_ENEMY_BITSET_SIZE  16
#define EE_ITEM_BITSET_ADDR   ((uint8_t *)29)
#define EE_ITEM_BITSET_SIZE   16
#define EE_TURN_SPEED_ADDR    ((uint8_t *)45)
#define EE_MOVE_SPEED_ADDR    ((uint8_t *)46)

static inline uint8_t save_exists(void)
{
    return eeprom_read_byte(EE_MAGIC_ADDR) == EE_MAGIC_VALUE;
}

static inline void save_game(int16_t px, int16_t py, int16_t angle, uint8_t health,
                              uint16_t kills, uint16_t pickups,
                              const uint8_t *enemy_bits, uint8_t enemy_bits_len,
                              const uint8_t *item_bits, uint8_t item_bits_len)
{
    eeprom_update_word((uint16_t *)EE_PX_ADDR, (uint16_t)px);
    eeprom_update_word((uint16_t *)EE_PY_ADDR, (uint16_t)py);
    eeprom_update_word((uint16_t *)EE_ANGLE_ADDR, (uint16_t)angle);
    eeprom_update_byte(EE_HEALTH_ADDR, health);
    eeprom_update_word(EE_KILLS_ADDR, kills);
    eeprom_update_word(EE_PICKUPS_ADDR, pickups);
    eeprom_update_block(enemy_bits, EE_ENEMY_BITSET_ADDR,
                         enemy_bits_len < EE_ENEMY_BITSET_SIZE ? enemy_bits_len : EE_ENEMY_BITSET_SIZE);
    eeprom_update_block(item_bits, EE_ITEM_BITSET_ADDR,
                         item_bits_len < EE_ITEM_BITSET_SIZE ? item_bits_len : EE_ITEM_BITSET_SIZE);
    eeprom_update_byte(EE_MAGIC_ADDR, EE_MAGIC_VALUE);
}

static inline void load_game(int16_t *px, int16_t *py, int16_t *angle, uint8_t *health,
                              uint16_t *kills, uint16_t *pickups,
                              uint8_t *enemy_bits, uint8_t enemy_bits_len,
                              uint8_t *item_bits, uint8_t item_bits_len)
{
    *px = (int16_t)eeprom_read_word((uint16_t *)EE_PX_ADDR);
    *py = (int16_t)eeprom_read_word((uint16_t *)EE_PY_ADDR);
    *angle = (int16_t)eeprom_read_word((uint16_t *)EE_ANGLE_ADDR);
    *health = eeprom_read_byte(EE_HEALTH_ADDR);
    *kills = eeprom_read_word(EE_KILLS_ADDR);
    *pickups = eeprom_read_word(EE_PICKUPS_ADDR);
    eeprom_read_block(enemy_bits, EE_ENEMY_BITSET_ADDR,
                       enemy_bits_len < EE_ENEMY_BITSET_SIZE ? enemy_bits_len : EE_ENEMY_BITSET_SIZE);
    eeprom_read_block(item_bits, EE_ITEM_BITSET_ADDR,
                       item_bits_len < EE_ITEM_BITSET_SIZE ? item_bits_len : EE_ITEM_BITSET_SIZE);
}

static inline uint8_t load_requested(void) { return eeprom_read_byte(EE_LOAD_FLAG_ADDR); }
static inline void set_load_flag(void) { eeprom_update_byte(EE_LOAD_FLAG_ADDR, 1); }
static inline void clear_load_flag(void) { eeprom_update_byte(EE_LOAD_FLAG_ADDR, 0); }

/* 3 speed presets each; index 1 is "normal" and matches the values this
 * project already shipped with before options existed. */
static const int16_t TURN_SPEED_VALUES[3] = {10, 15, 22};
static const int16_t MOVE_SPEED_VALUES[3] = {20, 32, 46};

static inline uint8_t get_turn_speed_index(void)
{
    uint8_t v = eeprom_read_byte(EE_TURN_SPEED_ADDR);
    return v < 3 ? v : 1;
}
static inline uint8_t get_move_speed_index(void)
{
    uint8_t v = eeprom_read_byte(EE_MOVE_SPEED_ADDR);
    return v < 3 ? v : 1;
}
static inline void set_turn_speed_index(uint8_t v) { eeprom_update_byte(EE_TURN_SPEED_ADDR, v); }
static inline void set_move_speed_index(uint8_t v) { eeprom_update_byte(EE_MOVE_SPEED_ADDR, v); }

#endif
