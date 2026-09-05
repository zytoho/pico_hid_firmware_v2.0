// Queue definitions for Pico HID Firmware v2.0
// Non-blocking execution engine with ring buffer

#ifndef QUEUE_H
#define QUEUE_H

#include <stdint.h>
#include <stdbool.h>

// ============================================================================
// Queue Configuration
// ============================================================================
#define QUEUE_CAPACITY      128
#define QUEUE_LOW_WATERMARK 16
#define QUEUE_HIGH_WATERMARK 112

// ============================================================================
// Queue Item Types
// ============================================================================
#define QUEUE_ITEM_KEY_TAP      0x01
#define QUEUE_ITEM_KEY_HOLD     0x02
#define QUEUE_ITEM_MOUSE_TO     0x03
#define QUEUE_ITEM_MOUSE_REL    0x04
#define QUEUE_ITEM_CLICK        0x05
#define QUEUE_ITEM_WAIT         0x06
#define QUEUE_ITEM_MARKOV_PAUSE 0x07
#define QUEUE_ITEM_LOOP         0x08

// ============================================================================
// Queue Item Structure (10 bytes)
// ============================================================================
typedef struct __attribute__((packed)) {
    uint8_t  type;        // Queue item type (0x01-0x08)
    uint8_t  action;      // Sub-action (keycode / button / etc.)
    uint16_t param_a;     // Parameter 1 (hold_mu / x / dx / base_ms / ...)
    uint16_t param_b;     // Parameter 2 (hold_sigma / y / dy / jitter / ...)
    uint8_t  flags;       // Bitfield: bezier enable, etc.
    uint8_t  override_a;  // Profile parameter override
    uint8_t  override_b;  // Profile parameter override
} queue_item_t;

// ============================================================================
// Queue State Machine
// ============================================================================
typedef enum {
    QUEUE_STATE_IDLE = 0,
    QUEUE_STATE_RUNNING,
    QUEUE_STATE_PAUSED
} queue_state_t;

// ============================================================================
// Execution Queue Structure
// ============================================================================
typedef struct {
    queue_item_t items[QUEUE_CAPACITY];
    volatile uint8_t head;              // Write position
    volatile uint8_t tail;              // Read position
    volatile queue_state_t state;
    uint8_t active_profile_id;
    uint8_t low_watermark;              // Default 16
    uint8_t high_watermark;             // Default 112
    bool high_watermark_triggered;      // Debounce flag for EVT_QUEUE_HIGH
} exec_queue_t;

// ============================================================================
// Queue API
// ============================================================================

// Initialize queue
void queue_init(void);

// Push items to queue, returns number of items actually written
uint8_t queue_push(const queue_item_t* items, uint8_t count);

// Get current queue depth
uint8_t queue_depth(void);

// Get free space in queue
uint8_t queue_free_space(void);

// Clear queue
void queue_clear(void);

// Start queue execution with specified profile
void queue_start(uint8_t profile_id);

// Pause queue execution
void queue_pause(void);

// Resume queue execution
void queue_resume(void);

// Get queue state
queue_state_t queue_get_state(void);

// Queue tick - non-blocking execution (call from main loop)
void queue_tick(void);

// Handle queue commands (called from cmd_dispatch)
void queue_handle_command(uint8_t cmd, const uint8_t *payload, uint8_t len);

#endif // QUEUE_H
