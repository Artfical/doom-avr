/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: real Options chunk -- turn speed and move speed, persisted to
 * EEPROM (savegame.h) so level1.c picks them up at boot. Not a stub: both
 * settings have a real, measurable effect on gameplay. */
#include <stdio.h>
#include "common_uart.h"
#include "savegame.h"

static const char chunk_menu[] PROGMEM = "MENU.BIN";
static const char *const LEVEL_NAMES[3] = {"Slow", "Normal", "Fast"};

static uint8_t row;       /* 0 = turn speed, 1 = move speed */
static uint8_t turn_idx, move_idx;

static void draw(void)
{
    char buf[32];
    uart_puts_P(PSTR("\n--- OPTIONS ---\n"));

    sprintf(buf, "%sTurn Speed: %s\n", row == 0 ? "> " : "  ", LEVEL_NAMES[turn_idx]);
    uart_puts(buf);
    sprintf(buf, "%sMove Speed: %s\n", row == 1 ? "> " : "  ", LEVEL_NAMES[move_idx]);
    uart_puts(buf);

    uart_puts_P(PSTR("(w/s select, a/d change, Enter = back)\n"));
}

int main(void)
{
    uart_init();
    uart_flush_boot_noise();

    row = 0;
    turn_idx = get_turn_speed_index();
    move_idx = get_move_speed_index();
    draw();

    for (;;) {
        char c = uart_getc();
        if (c == 'w') {
            row = 0;
            draw();
        } else if (c == 's') {
            row = 1;
            draw();
        } else if (c == 'a') {
            if (row == 0 && turn_idx > 0) { turn_idx--; set_turn_speed_index(turn_idx); }
            else if (row == 1 && move_idx > 0) { move_idx--; set_move_speed_index(move_idx); }
            draw();
        } else if (c == 'd') {
            if (row == 0 && turn_idx < 2) { turn_idx++; set_turn_speed_index(turn_idx); }
            else if (row == 1 && move_idx < 2) { move_idx++; set_move_speed_index(move_idx); }
            draw();
        } else if (c == '\r' || c == '\n') {
            request_chunk_P(chunk_menu);
            for (;;) {}
        }
    }
}
