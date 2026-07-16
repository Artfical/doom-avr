/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: "Save Game" info chunk. There's nothing to save from the main
 * menu -- no game is in progress here, same as real DOOM's main-menu Save
 * Game entry is meaningless without a live game -- so this explains the
 * real mechanism (press 'q' while playing) instead of pretending to save
 * empty state. Also reports whether a save currently exists in EEPROM,
 * which is real, not decorative -- see savegame.h. */
#include "common_uart.h"
#include "savegame.h"

static const char chunk_menu[] PROGMEM = "MENU.BIN";

int main(void)
{
    uart_init();
    uart_flush_boot_noise();
    uart_puts_P(PSTR("\n--- SAVE GAME ---\n"));
    uart_puts_P(PSTR("Saving happens DURING play, not from this menu:\n"));
    uart_puts_P(PSTR("press 'q' while in-game to save to EEPROM.\n"));
    if (save_exists()) {
        uart_puts_P(PSTR("(A saved game currently exists.)\n"));
    } else {
        uart_puts_P(PSTR("(No saved game exists yet.)\n"));
    }
    uart_puts_P(PSTR("Press Enter to return to the menu.\n"));

    for (;;) {
        char c = uart_getc();
        if (c == '\r' || c == '\n') {
            request_chunk_P(chunk_menu);
            for (;;) {}
        }
    }
}
