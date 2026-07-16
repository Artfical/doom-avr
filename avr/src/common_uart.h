/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* Shared UART helpers for doom-avr chunks. Header-only (all static) since
 * each chunk is compiled+linked as its own independent standalone binary --
 * there's no shared runtime library across chunk swaps, only shared source. */
#ifndef DOOM_AVR_COMMON_UART_H
#define DOOM_AVR_COMMON_UART_H

#include <avr/io.h>
#include <avr/pgmspace.h>
#include <stdint.h>
#include <stdbool.h>

#define F_CPU 16000000UL
#define BAUD 115200UL
#include <util/delay.h>
/* rounded, not truncated -- see menu.c history: floor-then-minus-1 gave
 * UBRR=7 (8.5% baud error, garbled UART) instead of the correct UBRR=8. */
#define UBRR_VALUE (((F_CPU + 8UL * BAUD) / (16UL * BAUD)) - 1)

static inline void uart_init(void)
{
    UBRR0H = (uint8_t)(UBRR_VALUE >> 8);
    UBRR0L = (uint8_t)UBRR_VALUE;
    UCSR0B = (1 << TXEN0) | (1 << RXEN0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); /* 8N1 */
}

static inline void uart_putc(char c)
{
    while (!(UCSR0A & (1 << UDRE0))) {}
    UDR0 = (uint8_t)c;
}

static inline void uart_puts_P(const char *s)
{
    char c;
    while ((c = pgm_read_byte(s++)) != 0) {
        if (c == '\n') uart_putc('\r');
        uart_putc(c);
    }
}

static inline void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n') uart_putc('\r');
        uart_putc(*s++);
    }
}

static inline bool uart_available(void)
{
    return (UCSR0A & (1 << RXC0)) != 0;
}

static inline char uart_getc(void)
{
    while (!uart_available()) {}
    return (char)UDR0;
}

/* The auto-reset (DTR toggle) that brings up a freshly-flashed chunk
 * glitches the UART RX line for a few ms; left unhandled, that noise can
 * be misread as real 'w'/'s'/'\r' commands right after boot. Call this
 * once at the top of main(), before doing anything else, to drain it. */
static inline void uart_flush_boot_noise(void)
{
    for (uint16_t i = 0; i < 300; i++) {
        while (uart_available()) { (void)UDR0; }
        _delay_ms(1);
    }
}

/* Ask the host to reflash this chip with a new chunk. The running chunk
 * is about to be overwritten, so callers should halt right after this. */
static inline void request_chunk_P(const char *name_p)
{
    uart_puts_P(PSTR("REQ:"));
    char c;
    while ((c = pgm_read_byte(name_p++)) != 0) uart_putc(c);
    uart_putc('\r');
    uart_putc('\n');
}

#endif
