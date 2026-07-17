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
#include <avr/interrupt.h>
#include <avr/pgmspace.h>
#include <stdint.h>
#include <stdbool.h>

#define F_CPU 16000000UL
#define BAUD 115200UL
#include <util/delay.h>
/* rounded, not truncated -- see menu.c history: floor-then-minus-1 gave
 * UBRR=7 (8.5% baud error, garbled UART) instead of the correct UBRR=8. */
#define UBRR_VALUE (((F_CPU + 8UL * BAUD) / (16UL * BAUD)) - 1)

/* RX ring buffer, filled by USART_RX_vect below. The ATmega328p's own RX
 * hardware only holds 2 bytes; without this, any byte that arrives while
 * the chunk is busy elsewhere (e.g. mid-way through draw_menu()'s blocking
 * TX writes) gets silently dropped on overrun -- observed as "pressed
 * Enter right after an arrow key and it just didn't register" and as lost
 * bytes from the host's multi-byte mouse-click bursts (several w/s bytes
 * plus \r sent back-to-back with no gap). 32 bytes is far more than one
 * human keypress burst or one mouse-click jump needs. */
#define UART_RX_BUF_SIZE 32
static volatile uint8_t uart_rx_buf[UART_RX_BUF_SIZE];
static volatile uint8_t uart_rx_head = 0;
static volatile uint8_t uart_rx_tail = 0;

ISR(USART_RX_vect)
{
    uint8_t c = UDR0;
    uint8_t next_head = (uint8_t)((uart_rx_head + 1) & (UART_RX_BUF_SIZE - 1));
    if (next_head != uart_rx_tail) {
        uart_rx_buf[uart_rx_head] = c;
        uart_rx_head = next_head;
    } /* else: buffer truly full (32 unread bytes) -- drop, same as before */
}

static inline void uart_init(void)
{
    UBRR0H = (uint8_t)(UBRR_VALUE >> 8);
    UBRR0L = (uint8_t)UBRR_VALUE;
    UCSR0B = (1 << TXEN0) | (1 << RXEN0) | (1 << RXCIE0);
    UCSR0C = (1 << UCSZ01) | (1 << UCSZ00); /* 8N1 */
    sei();
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
    return uart_rx_head != uart_rx_tail;
}

static inline char uart_getc(void)
{
    while (!uart_available()) {}
    char c = (char)uart_rx_buf[uart_rx_tail];
    uart_rx_tail = (uint8_t)((uart_rx_tail + 1) & (UART_RX_BUF_SIZE - 1));
    return c;
}

/* The auto-reset (DTR toggle) that brings up a freshly-flashed chunk
 * glitches the UART RX line for a few ms; left unhandled, that noise can
 * be misread as real 'w'/'s'/'\r' commands right after boot. Call this
 * once at the top of main(), before doing anything else, to drain it. */
static inline void uart_flush_boot_noise(void)
{
    for (uint16_t i = 0; i < 300; i++) {
        while (uart_available()) { (void)uart_getc(); }
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
