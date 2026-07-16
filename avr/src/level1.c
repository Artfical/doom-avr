/* doom-avr is an artfical project
 * Copyright (C) 2026 Talha Berk Arslan
 * SPDX-License-Identifier: AGPL-3.0-or-later
 * See LICENSE for the full license text.
 */

/* doom-avr: LEVEL1 -- real E1M1 geometry, movement, collision, on-chip
 * raycasting, AND now a minimal combat loop: hitscan weapon, simple
 * "sees you -> walks at you" enemy AI, player health, death/respawn.
 *
 * Enemies now have a MUTABLE position (enemy_pos[], RAM, initialized
 * from the PROGMEM enemies[] spawn points at boot) since they move.
 * Items stay static/PROGMEM-only -- they never move.
 *
 * Simplifications, documented not hidden:
 *  - "Sees you" = within SIGHT_RADIUS in a straight line, no actual
 *    line-of-sight-through-walls check (would mean per-enemy wall
 *    raycasts every turn -- 103 enemies x 404 walls is too expensive
 *    given the per-frame budget already spent on rendering).
 *  - Enemies do not collide with walls while chasing -- they can clip
 *    through geometry. A real fix needs the same collision code player
 *    movement uses, run per active enemy per turn; skipped for time.
 *  - Combat is turn-based, not real-time: enemies move/attack once per
 *    processed player input (move, turn, or fire), not on a clock.
 *  - The hitscan weapon has unlimited ammo and a fixed narrow cone
 *    (HITSCAN_HALF_ANGLE_TAN) centered on the view direction -- no
 *    weapon switching, no spread/damage falloff, one hit = one kill
 *    (matches the existing melee-bump-is-instant-kill simplification).
 *
 * Wire protocol, sent after every processed input:
 *   STATE:x,y,angle,kills,pickups,health
 *   FRAME:d0:w0:f0,...              (unchanged, see previous version)
 *   SPRITES:E12:c:d,I3:c:d,...      (unchanged, but enemy positions are
 *                                    now their CURRENT position, not
 *                                    their original spawn point)
 *
 * FOV_DEG/NUM_COLS here MUST match client.py's copies (no shared
 * generated file for these two constants).
 */

#include <math.h>
#include <stdio.h>
#include <string.h>
#include "common_uart.h"
#include "map_data.h"
#include "savegame.h"

#if (ENEMY_COUNT + 7) / 8 > EE_ENEMY_BITSET_SIZE
#error "ENEMY_COUNT no longer fits EE_ENEMY_BITSET_SIZE -- widen savegame.h's layout"
#endif
#if (ITEM_COUNT + 7) / 8 > EE_ITEM_BITSET_SIZE
#error "ITEM_COUNT no longer fits EE_ITEM_BITSET_SIZE -- widen savegame.h's layout"
#endif

#define PLAYER_RADIUS 16.0f
#define BUMP_RADIUS   40.0f
#define PICKUP_RADIUS 32.0f

/* Set from EEPROM at boot (see savegame.h) instead of being fixed
 * constants, so the Options chunk's choices actually take effect. */
static float move_step;
static int16_t rotate_step;

#define FOV_DEG   60.0f
#define NUM_COLS  16  /* MUST match client.py's NUM_COLS. Tuning history
                        (all measured on real hardware, not guessed):
                        32 cols, atan2f sprites: ~4.1s/frame (unreliable
                        timing method, later distrusted) -- 32 cols,
                        dot-product sprites: 2.93s -- 20 cols: 1.88s --
                        20 cols + "behind player" candidate reject: 1.385s
                        -- 20 cols + tight FOV-cone candidate reject:
                        0.985s -- 16 cols, same filters: 0.832s. */

#define PLAYER_MAX_HEALTH   100
#define SIGHT_RADIUS        700.0f
#define ATTACK_RADIUS       48.0f
#define ENEMY_MOVE_STEP     12.0f
#define DAMAGE_PER_TURN     8
#define HITSCAN_HALF_ANGLE_DEG 5.0f

static float px, py;
static int16_t angle_deg;
static uint16_t kills, pickups;
static int16_t player_health;

static point_t enemy_pos[ENEMY_COUNT];  /* mutable -- enemies move */
static uint8_t enemy_alive[(ENEMY_COUNT + 7) / 8];
static uint8_t item_collected[(ITEM_COUNT + 7) / 8];

static uint8_t bit_get(const uint8_t *arr, uint16_t i) { return (arr[i >> 3] >> (i & 7)) & 1; }
static void bit_clear(uint8_t *arr, uint16_t i) { arr[i >> 3] &= ~(1 << (i & 7)); }

static float deg2rad(float d) { return d * 3.14159265f / 180.0f; }

static uint8_t collides(float x, float y)
{
    for (uint16_t i = 0; i < WALL_COUNT; i++) {
        wall_t w;
        memcpy_P(&w, &walls[i], sizeof(wall_t));

        int16_t minx = (w.x1 < w.x2) ? w.x1 : w.x2;
        int16_t maxx = (w.x1 > w.x2) ? w.x1 : w.x2;
        int16_t miny = (w.y1 < w.y2) ? w.y1 : w.y2;
        int16_t maxy = (w.y1 > w.y2) ? w.y1 : w.y2;
        if (x < minx - PLAYER_RADIUS || x > maxx + PLAYER_RADIUS ||
            y < miny - PLAYER_RADIUS || y > maxy + PLAYER_RADIUS)
            continue;

        float dx = w.x2 - w.x1, dy = w.y2 - w.y1;
        float len2 = dx * dx + dy * dy;
        float t = 0.0f;
        if (len2 > 0.0f) {
            t = ((x - w.x1) * dx + (y - w.y1) * dy) / len2;
            if (t < 0.0f) t = 0.0f;
            if (t > 1.0f) t = 1.0f;
        }
        float projx = w.x1 + t * dx;
        float projy = w.y1 + t * dy;
        float ddx = x - projx, ddy = y - projy;
        if (ddx * ddx + ddy * ddy < PLAYER_RADIUS * PLAYER_RADIUS)
            return 1;
    }
    return 0;
}

static void try_move(float step)
{
    float rad = deg2rad(angle_deg);
    float nx = px + cosf(rad) * step;
    float ny = py + sinf(rad) * step;

    if (!collides(nx, ny)) { px = nx; py = ny; return; }
    if (!collides(nx, py)) { px = nx; return; }
    if (!collides(px, ny)) { py = ny; return; }
}

static void check_bumps_and_pickups(void)
{
    for (uint16_t i = 0; i < ENEMY_COUNT; i++) {
        if (!bit_get(enemy_alive, i)) continue;
        float dx = px - enemy_pos[i].x, dy = py - enemy_pos[i].y;
        if (dx * dx + dy * dy < BUMP_RADIUS * BUMP_RADIUS) {
            bit_clear(enemy_alive, i);
            kills++;
        }
    }
    for (uint16_t i = 0; i < ITEM_COUNT; i++) {
        if (!bit_get(item_collected, i)) continue;
        point_t p;
        memcpy_P(&p, &items[i], sizeof(point_t));
        float dx = px - p.x, dy = py - p.y;
        if (dx * dx + dy * dy < PICKUP_RADIUS * PICKUP_RADIUS) {
            bit_clear(item_collected, i);
            pickups++;
        }
    }
}

static void check_goal(void)
{
    float gdx = px - GOAL_X, gdy = py - GOAL_Y;
    if (gdx * gdx + gdy * gdy < (float)GOAL_RADIUS * (float)GOAL_RADIUS) {
        uart_puts_P(PSTR("LEVEL COMPLETE!\n"));
        request_chunk_P(PSTR("MENU.BIN"));
        for (;;) {}
    }
}

/* Simple "sees you -> walks at you" AI, run once per processed input
 * (turn-based, not real-time). See file header for the simplifications
 * (no line-of-sight-through-walls check, no enemy-vs-wall collision). */
static void update_enemies(void)
{
    for (uint16_t i = 0; i < ENEMY_COUNT; i++) {
        if (!bit_get(enemy_alive, i)) continue;
        float dx = px - enemy_pos[i].x, dy = py - enemy_pos[i].y;
        float dist2 = dx * dx + dy * dy;
        if (dist2 > SIGHT_RADIUS * SIGHT_RADIUS) continue;

        float dist = sqrtf(dist2);
        if (dist > ATTACK_RADIUS) {
            float step = ENEMY_MOVE_STEP / dist;
            enemy_pos[i].x += (int16_t)(dx * step);
            enemy_pos[i].y += (int16_t)(dy * step);
        } else {
            player_health -= DAMAGE_PER_TURN;
            if (player_health < 0) player_health = 0;
        }
    }
}

static void check_death(void)
{
    if (player_health <= 0) {
        uart_puts_P(PSTR("YOU DIED! Respawning...\n"));
        px = START_X;
        py = START_Y;
        angle_deg = START_ANGLE;
        player_health = PLAYER_MAX_HEALTH;
    }
}

/* Nearest wall hit along a ray from (ox,oy) in direction (dx,dy) (need
 * not be unit length). candidates==NULL means "scan all WALL_COUNT"
 * (used by the hitscan weapon, which fires rarely enough that skipping
 * the per-frame candidate-list optimization is fine); otherwise searches
 * only the given pre-filtered subset (see send_frame). Wall index
 * 0xFFFF = no hit. */
static void cast_ray(float ox, float oy, float dx, float dy,
                      const uint16_t *candidates, uint16_t num_candidates,
                      float *out_t, uint16_t *out_wall, float *out_s)
{
    float best_t = -1.0f, best_s = 0.0f;
    uint16_t best_i = 0xFFFF;
    uint16_t count = candidates ? num_candidates : WALL_COUNT;
    for (uint16_t c = 0; c < count; c++) {
        uint16_t i = candidates ? candidates[c] : c;
        wall_t w;
        memcpy_P(&w, &walls[i], sizeof(wall_t));
        float bx = w.x2 - w.x1, by = w.y2 - w.y1;
        float denom = dx * by - dy * bx;
        if (denom > -1e-6f && denom < 1e-6f) continue;
        float t = ((w.x1 - ox) * by - (w.y1 - oy) * bx) / denom;
        if (t <= 0.0f) continue;
        float s = ((w.x1 - ox) * dy - (w.y1 - oy) * dx) / denom;
        if (s < 0.0f || s > 1.0f) continue;
        if (best_i == 0xFFFF || t < best_t) { best_t = t; best_i = i; best_s = s; }
    }
    *out_t = best_t; *out_wall = best_i; *out_s = best_s;
}

/* Hitscan fire: nearest wall along the exact view direction, nearest
 * alive enemy within a narrow cone AND closer than that wall, one hit
 * kills (see file header simplifications). */
static void do_fire(void)
{
    float angle_rad = deg2rad(angle_deg);
    float dx = cosf(angle_rad), dy = sinf(angle_rad);

    float wall_t; uint16_t wall_i; float wall_s;
    cast_ray(px, py, dx, dy, NULL, 0, &wall_t, &wall_i, &wall_s);

    float cone_tan = tanf(deg2rad(HITSCAN_HALF_ANGLE_DEG));
    float best_t = -1.0f;
    uint16_t best_i = 0xFFFF;
    for (uint16_t i = 0; i < ENEMY_COUNT; i++) {
        if (!bit_get(enemy_alive, i)) continue;
        float ex = enemy_pos[i].x - px, ey = enemy_pos[i].y - py;
        float fwd = ex * dx + ey * dy;
        if (fwd <= 0.0f) continue;
        float side = -ex * dy + ey * dx;
        float ratio = side / fwd;
        if (ratio < -cone_tan || ratio > cone_tan) continue;
        if (wall_i != 0xFFFF && fwd > wall_t) continue;  /* blocked by a wall */
        if (best_i == 0xFFFF || fwd < best_t) { best_t = fwd; best_i = i; }
    }

    if (best_i != 0xFFFF) {
        bit_clear(enemy_alive, best_i);
        kills++;
        uart_puts_P(PSTR("HIT!\n"));
    } else {
        uart_puts_P(PSTR("MISS\n"));
    }
}

static void send_frame(void)
{
    float angle_rad = deg2rad(angle_deg);
    float half_fov = deg2rad(FOV_DEG) / 2.0f;
    float cos_a = cosf(angle_rad), sin_a = sinf(angle_rad);

    /* Precompute once per frame (not once per ray): which walls could
     * possibly be hit by ANY ray this frame. Two cheap rejects, both
     * always-safe (can't exclude anything actually visible):
     *   1. both endpoints behind the view center.
     *   2. both endpoints off the SAME side beyond half_fov+margin.
     * Measured on real hardware: cut ~1.88s/frame to ~0.985s (see
     * doom_avr_project memory for the full tuning history). */
    float half_fov_tan_margin = tanf(half_fov * 1.6f);
    /* Capped well below WALL_COUNT (404) on purpose: a full-size array
     * here was the direct cause of a confirmed stack-overflow bug (see
     * doom_avr_project memory) -- worst-case call depth (main ->
     * send_frame -> cast_ray) needed ~909 bytes of stack but only ~730
     * were free after this array's static allocation, so the stack
     * smashed into px/py/angle_deg/kills/pickups/health right after the
     * first weapon fire. A 60-degree-FOV view of this map never
     * plausibly needs anywhere near 404 candidates simultaneously; the
     * cap below is a large safety margin over anything observed, with
     * an explicit bounded truncation (never a buffer overrun) if wrong. */
    #define MAX_CANDIDATES 140
    static uint16_t candidates[MAX_CANDIDATES];
    uint16_t num_candidates = 0;
    for (uint16_t i = 0; i < WALL_COUNT && num_candidates < MAX_CANDIDATES; i++) {
        wall_t w;
        memcpy_P(&w, &walls[i], sizeof(wall_t));
        float fwd1 = (w.x1 - px) * cos_a + (w.y1 - py) * sin_a;
        float fwd2 = (w.x2 - px) * cos_a + (w.y2 - py) * sin_a;
        if (fwd1 <= 0.0f && fwd2 <= 0.0f) continue;

        if (fwd1 > 0.0f && fwd2 > 0.0f) {
            float side1 = -(w.x1 - px) * sin_a + (w.y1 - py) * cos_a;
            float side2 = -(w.x2 - px) * sin_a + (w.y2 - py) * cos_a;
            float r1 = side1 / fwd1, r2 = side2 / fwd2;
            if (r1 > half_fov_tan_margin && r2 > half_fov_tan_margin) continue;
            if (r1 < -half_fov_tan_margin && r2 < -half_fov_tan_margin) continue;
        }
        candidates[num_candidates++] = i;
    }
    /* Confirmed on real hardware: num_candidates stays around 80-115 in
     * practice (well under MAX_CANDIDATES=140) across tested views. */

    uart_puts_P(PSTR("FRAME:"));
    for (uint8_t col = 0; col < NUM_COLS; col++) {
        float ray_ang = angle_rad - half_fov + ((float)col / (NUM_COLS - 1)) * (2.0f * half_fov);
        float dx = cosf(ray_ang), dy = sinf(ray_ang);
        float t, s; uint16_t wall_i;
        cast_ray(px, py, dx, dy, candidates, num_candidates, &t, &wall_i, &s);

        char buf[24];
        if (wall_i == 0xFFFF) {
            sprintf(buf, "9999:65535:0");
        } else {
            float corrected = t * cosf(ray_ang - angle_rad);
            if (corrected < 1.0f) corrected = 1.0f;
            sprintf(buf, "%d:%u:%u", (int)corrected, wall_i, (unsigned)(s * 255.0f));
        }
        uart_puts(buf);
        if (col + 1 < NUM_COLS) uart_putc(',');
    }
    uart_putc('\n');

    uart_puts_P(PSTR("SPRITES:"));
    float half_fov_tan = tanf(half_fov);
    uint8_t first = 1;
    for (uint16_t i = 0; i < ENEMY_COUNT + ITEM_COUNT; i++) {
        uint8_t is_enemy = i < ENEMY_COUNT;
        uint16_t idx = is_enemy ? i : (i - ENEMY_COUNT);
        if (is_enemy && !bit_get(enemy_alive, idx)) continue;
        if (!is_enemy && !bit_get(item_collected, idx)) continue;

        float ddx, ddy;
        if (is_enemy) {
            ddx = enemy_pos[idx].x - px; ddy = enemy_pos[idx].y - py;
        } else {
            point_t p;
            memcpy_P(&p, &items[idx], sizeof(point_t));
            ddx = p.x - px; ddy = p.y - py;
        }

        float fwd = ddx * cos_a + ddy * sin_a;
        if (fwd <= 1.0f) continue;
        float side = -ddx * sin_a + ddy * cos_a;
        float ratio = side / fwd;
        if (ratio < -half_fov_tan || ratio > half_fov_tan) continue;

        float dist = sqrtf(ddx * ddx + ddy * ddy);
        int col = (int)(((ratio / half_fov_tan) * 0.5f + 0.5f) * (NUM_COLS - 1));

        if (!first) uart_putc(',');
        first = 0;
        char buf[20];
        sprintf(buf, "%c%u:%d:%d", is_enemy ? 'E' : 'I', idx, col, (int)dist);
        uart_puts(buf);
    }
    uart_putc('\n');
}

static void send_state(void)
{
    char buf[56];
    sprintf(buf, "STATE:%d,%d,%d,%u,%u,%d\n",
            (int)px, (int)py, (int)angle_deg, kills, pickups, (int)player_health);
    uart_puts(buf);
}

int main(void)
{
    uart_init();
    uart_flush_boot_noise();

    move_step = MOVE_SPEED_VALUES[get_move_speed_index()];
    rotate_step = TURN_SPEED_VALUES[get_turn_speed_index()];

    for (uint16_t i = 0; i < ENEMY_COUNT; i++) {
        memcpy_P(&enemy_pos[i], &enemies[i], sizeof(point_t));
    }

    if (save_exists() && load_requested()) {
        int16_t ipx, ipy;
        uint8_t health8;
        load_game(&ipx, &ipy, &angle_deg, &health8, &kills, &pickups,
                  enemy_alive, sizeof(enemy_alive), item_collected, sizeof(item_collected));
        px = ipx;
        py = ipy;
        player_health = health8;
        clear_load_flag();  /* one-shot: a plain reboot/New Game won't re-load this */
        uart_puts_P(PSTR("\n--- E1M1 (loaded save) ---\n"));
    } else {
        memset(enemy_alive, 0xFF, sizeof(enemy_alive));
        memset(item_collected, 0xFF, sizeof(item_collected));
        px = START_X;
        py = START_Y;
        angle_deg = START_ANGLE;
        player_health = PLAYER_MAX_HEALTH;
        uart_puts_P(PSTR("\n--- E1M1 (real geometry, on-chip renderer + combat) ---\n"));
    }
    send_state();
    send_frame();

    for (;;) {
        char c = uart_getc();
        uint8_t acted = 0;
        if (c == 'a') {
            angle_deg = (angle_deg + rotate_step) % 360;
            acted = 1;
        } else if (c == 'd') {
            angle_deg = (angle_deg - rotate_step + 360) % 360;
            acted = 1;
        } else if (c == 'w') {
            try_move(move_step);
            check_bumps_and_pickups();
            check_goal();
            acted = 1;
        } else if (c == 's') {
            try_move(-move_step);
            check_bumps_and_pickups();
            check_goal();
            acted = 1;
        } else if (c == 'f') {
            do_fire();
            acted = 1;
        } else if (c == 'q') {
            save_game((int16_t)px, (int16_t)py, angle_deg, (uint8_t)player_health, kills, pickups,
                       enemy_alive, sizeof(enemy_alive), item_collected, sizeof(item_collected));
            uart_puts_P(PSTR("SAVED\n"));
        }
        if (acted) {
            update_enemies();
            check_death();
            send_state();
            send_frame();
        }
    }
}
