#ifndef BEZIER_H
#define BEZIER_H

#include <stdint.h>
#include <stdbool.h>

/**
 * Bezier mouse trajectory module
 * Generates smooth, human-like mouse movements using quadratic Bezier curves
 */

// Bezier trajectory state
typedef struct {
    bool active;
    
    // Start and end points (absolute coordinates)
    int16_t start_x, start_y;
    int16_t end_x, end_y;
    
    // Control point for quadratic Bezier
    int16_t ctrl_x, ctrl_y;
    
    // Current position
    int16_t cur_x, cur_y;
    
    // Progress
    uint16_t step;
    uint16_t total_steps;
    
    // Timing
    uint32_t step_interval_us;
    uint32_t last_step_time;
} bezier_traj_t;

/**
 * Initialize bezier module
 */
void bezier_init(void);

/**
 * Start a new Bezier trajectory
 * @param start_x, start_y Starting coordinates
 * @param end_x, end_y Target coordinates
 * @param duration_ms Movement duration in milliseconds
 */
void bezier_start(int16_t start_x, int16_t start_y,
                  int16_t end_x, int16_t end_y,
                  uint16_t duration_ms);

/**
 * Update Bezier trajectory (non-blocking)
 * @return true if trajectory is still active, false if completed
 */
bool bezier_tick(void);

/**
 * Get current position
 */
void bezier_get_pos(int16_t* x, int16_t* y);

#endif // BEZIER_H
