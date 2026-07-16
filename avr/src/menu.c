/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: minimal main-menu chunk.
 * Reference: chocolate-doom src/doom/m_menu.c MainMenu[] item order/labels.
 * This is a from-scratch AVR-native reimplementation, not compiled
 * chocolate-doom source -- see project notes on why the original
 * m_menu.c can't be built for a 2KB-RAM target.
 *
 * Output: menu state as text over UART (the real client.py on the host
 * renders it using actual doom1.wad graphics). Input: single-byte
 * commands from the serial host ('w'/'s' = up/down, '\r' = select).
 *
 * Loading model: this chunk never receives chunk bytes itself. When an
 * item needs a different chunk, it sends "REQ:<name>" and halts -- the
 * host reflashes the whole chip via avrdude/optiboot (the existing,
 * already-reliable bootloader) and the new chunk boots from reset.
 */

#include <string.h>
#include "common_uart.h"

typedef enum {
    MENU_NEW_GAME = 0,
    MENU_OPTIONS,
    MENU_LOAD_GAME,
    MENU_SAVE_GAME,
    MENU_READ_THIS,
    MENU_QUIT,
    MENU_ITEM_COUNT
} menu_item_id_t;

static const char item_new_game[]  PROGMEM = "New Game";
static const char item_options[]   PROGMEM = "Options";
static const char item_load_game[] PROGMEM = "Load Game";
static const char item_save_game[] PROGMEM = "Save Game";
static const char item_read_this[] PROGMEM = "Read This!";
static const char item_quit[]      PROGMEM = "Quit";

static const char *const menu_items[MENU_ITEM_COUNT] PROGMEM = {
    item_new_game, item_options, item_load_game,
    item_save_game, item_read_this, item_quit,
};

/* Chunk names requested from the Python host when an item is chosen.
 * Empty string == handled locally (Quit), no chunk swap. */
static const char chunk_level1[]  PROGMEM = "LEVEL1.BIN";
static const char chunk_options[] PROGMEM = "OPTIONS.BIN";
static const char chunk_loadg[]   PROGMEM = "LOADG.BIN";
static const char chunk_saveg[]   PROGMEM = "SAVEG.BIN";
static const char chunk_readthis[] PROGMEM = "HELP.BIN";
static const char chunk_none[]    PROGMEM = "";

static const char *const menu_chunks[MENU_ITEM_COUNT] PROGMEM = {
    chunk_level1, chunk_options, chunk_loadg,
    chunk_saveg, chunk_readthis, chunk_none,
};

static uint8_t selection = 0;

static void draw_menu(void)
{
    char namebuf[16];
    uart_puts_P(PSTR("\n--- DOOM ---\n"));
    for (uint8_t i = 0; i < MENU_ITEM_COUNT; i++) {
        const char *name_p = (const char *)pgm_read_word(&menu_items[i]);
        strlcpy_P(namebuf, name_p, sizeof(namebuf));
        uart_puts_P(i == selection ? PSTR("> ") : PSTR("  "));
        for (uint8_t j = 0; namebuf[j]; j++) uart_putc(namebuf[j]);
        uart_putc('\r');
        uart_putc('\n');
    }
}

int main(void)
{
    uart_init();
    uart_flush_boot_noise();
    draw_menu();

    for (;;) {
        char c = uart_getc();
        if (c == 'w' && selection > 0) {
            selection--;
            draw_menu();
        } else if (c == 's' && selection + 1 < MENU_ITEM_COUNT) {
            selection++;
            draw_menu();
        } else if (c == '\r' || c == '\n') {
            const char *chunk_p = (const char *)pgm_read_word(&menu_chunks[selection]);
            if (pgm_read_byte(chunk_p) == 0) {
                /* Quit: nothing to load, just say so and halt. */
                uart_puts_P(PSTR("\n--- Thanks for playing! ---\n"));
                for (;;) {}
            }
            request_chunk_P(chunk_p);
            for (;;) {} /* about to be overwritten by the host reflash */
        }
    }
}
