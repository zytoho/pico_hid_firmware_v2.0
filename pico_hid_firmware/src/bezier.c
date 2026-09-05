#include "bezier.h"
#include "rng.h"
#include "pico/stdlib.h"
#include "hardware/timer.h"
#include <stdlib.h>

// Private state
static bezier_traj_t traj;

// Ease-in-out cubic function: t ∈ [0, 1000] -> [0, 1000]
// f(t) = 3t² - 2t³ (in thousandths)
static uint16_t ease_in_out(uint16_t t) {
    if (t >= 1000) return 1000;
    uint32_t t2 = (uint32_t)t * t;
    uint32_t t3 = t2 * t / 1000;
    uint32_t eased = (3 * t2 / 1000) - (2 * t3 / 1000);
    return (uint16_t)(eased > 1000 ? 1000 : eased);
}

// Quadratic Bezier: B(t) = (1-t)²·P0 + 2·(1-t)·t·P1 + t²·P2
// t is in [0, 1000] for integer math
static int16_t bezier_interp(int16_t p0, int16_t p1, int16_t p2, uint16_t t) {
    int32_t one_minus_t = 1000 - t;
    int32_t term0 = (int32_t)one_minus_t * one_minus_t / 1000 * p0;
    int32_t term1 = 2 * one_minus_t * t / 1000 * p1;
    int32_t term2 = (int32_t)t * t / 1000 * p2;
    int32_t result = (term0 + term1 + term2) / 1000;
    return (int16_t)result;
}

void bezier_init(void) {
    traj.active = false;
    traj.step = 0;
    traj.total_steps = 0;
}

void bezier_start(int16_t start_x, int16_t start_y,
                  int16_t end_x, int16_t end_y,
                  uint16_t duration_ms) {
    traj.start_x = start_x;
    traj.start_y = start_y;
    traj.end_x = end_x;
    traj.end_y = end_y;
    traj.cur_x = start_x;
    traj.cur_y = start_y;
    
    // Generate random control point for human-like curve
    // Control point is offset perpendicular to the direct path
    int16_t mid_x = (start_x + end_x) / 2;
    int16_t mid_y = (start_y + end_y) / 2;
    
    // Perpendicular offset (random ±15-40 pixels)
    int16_t offset = 15 + rng_uniform(26);  // [15, 40]
    
    // Determine perpendicular direction
    int16_t dx = end_x - start_x;
    int16_t dy = end_y - start_y;
    
    // Perpendicular vector: (-dy, dx) normalized
    // For simplicity, use the longer axis
    int16_t len = (abs(dx) > abs(dy)) ? abs(dx) : abs(dy);
    if (len == 0) len = 1;
    
    // Add some randomness to direction (can be + or -)
    int8_t sign = (rng_uniform(2) == 0) ? 1 : -1;
    
    if (abs(dx) >= abs(dy)) {
        // Mostly horizontal movement, offset vertically
        traj.ctrl_x = mid_x;
        traj.ctrl_y = mid_y + sign * offset;
    } else {
        // Mostly vertical movement, offset horizontally
        traj.ctrl_x = mid_x + sign * offset;
        traj.ctrl_y = mid_y;
    }
    
    // Calculate total steps (1 step per 8ms, ~125Hz update rate)
    const uint16_t STEP_INTERVAL_MS = 8;
    traj.total_steps = duration_ms / STEP_INTERVAL_MS;
    if (traj.total_steps < 5) traj.total_steps = 5;  // Minimum 5 steps
    
    traj.step_interval_us = STEP_INTERVAL_MS * 1000;
    traj.step = 0;
    traj.last_step_time = time_us_32();
    traj.active = true;
}

bool bezier_tick(void) {
    if (!traj.active) {
        return false;
    }
    
    uint32_t now = time_us_32();
    uint32_t elapsed = now - traj.last_step_time;
    
    if (elapsed < traj.step_interval_us) {
        return true;  // Not time for next step yet
    }
    
    traj.last_step_time = now;
    traj.step++;
    
    if (traj.step >= traj.total_steps) {
        // Trajectory complete, snap to end
        traj.cur_x = traj.end_x;
        traj.cur_y = traj.end_y;
        traj.active = false;
        return false;
    }
    
    // Calculate progress with easing
    uint16_t raw_t = (uint16_t)((uint32_t)traj.step * 1000 / traj.total_steps);
    uint16_t eased_t = ease_in_out(raw_t);
    
    // Interpolate position along Bezier curve
    traj.cur_x = bezier_interp(traj.start_x, traj.ctrl_x, traj.end_x, eased_t);
    traj.cur_y = bezier_interp(traj.start_y, traj.ctrl_y, traj.end_y, eased_t);
    
    return true;  // Trajectory still active
}

void bezier_get_pos(int16_t* x, int16_t* y) {
    if (x) *x = traj.cur_x;
    if (y) *y = traj.cur_y;
}
