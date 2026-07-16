/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: real Load Game chunk. EEPROM (savegame.h) is the only storage
 * that survives a reflash, so "loading" here means: set a flag in EEPROM
 * and hand off to LEVEL1.BIN, which checks that flag at its own boot and
 * restores position/health/kills/pickups/enemy+item state from EEPROM
 * instead of starting fresh. See savegame.h for why EEPROM is used as the
 * cross-chunk handoff channel. */
#include "common_uart.h"
#include "savegame.h"

static const char chunk_menu[] PROGMEM = "MENU.BIN";
static const char chunk_level1[] PROGMEM = "LEVEL1.BIN";

int main(void)
{
    uart_init();
    uart_flush_boot_noise();
    uart_puts_P(PSTR("\n--- LOAD GAME ---\n"));

    if (save_exists()) {
        uart_puts_P(PSTR("Saved game found. Loading...\n"));
        set_load_flag();
        request_chunk_P(chunk_level1);
        for (;;) {}
    }

    uart_puts_P(PSTR("No saved game found (press 'q' during play to save).\n"));
    uart_puts_P(PSTR("Press Enter to return to the menu.\n"));

    for (;;) {
        char c = uart_getc();
        if (c == '\r' || c == '\n') {
            request_chunk_P(chunk_menu);
            for (;;) {}
        }
    }
}
