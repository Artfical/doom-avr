/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: real "Read This!" chunk -- pages through the actual HELP1/
 * HELP2 full-screen graphics from doom1.wad (real id Software artwork,
 * decoded by the host the same way menu graphics are -- this chunk only
 * tracks which page is showing and tells the host via "PAGE:<n>"). */
#include "common_uart.h"

static const char chunk_menu[] PROGMEM = "MENU.BIN";

int main(void)
{
    uart_init();
    uart_flush_boot_noise();

    uint8_t page = 1;
    uart_puts_P(PSTR("PAGE:1\n"));

    for (;;) {
        char c = uart_getc();
        if (c == '\r' || c == '\n') {
            if (page == 1) {
                page = 2;
                uart_puts_P(PSTR("PAGE:2\n"));
            } else {
                request_chunk_P(chunk_menu);
                for (;;) {}
            }
        }
    }
}
