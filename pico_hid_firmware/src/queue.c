#include "queue.h"
#include "hid.h"
#include "rng.h"
#include "profile.h"
#include "protocol.h"
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/timer.h"
#include "hardware/sync.h"

// ============================================================================
// Global Queue Instance
// ============================================================================
static exec_queue_t queue;

// Execution state machine
static struct {
    bool executing;
    uint8_t step;
    uint32_t step_start_us;
    uint32_t delay_us;
    queue_item_t current_item;
} exec_state = {0};

static uint8_t queue_held_keycode = 0;

// Set by queue_clear (UART IRQ context); the release itself is sent from
// queue_tick once the HID endpoint is ready.
static volatile bool queue_release_pending = false;

typedef enum {
    KEY_EMIT_SENT = 0,
    KEY_EMIT_RETRY,
    KEY_EMIT_ABORTED
} key_emit_t;

// ============================================================================
// Queue Initialization
// ============================================================================
void queue_init(void) {
    queue.head = 0;
    queue.tail = 0;
    queue.state = QUEUE_STATE_IDLE;
    queue.active_profile_id = 0;
    queue.low_watermark = QUEUE_LOW_WATERMARK;
    queue.high_watermark = QUEUE_HIGH_WATERMARK;
    queue.high_watermark_triggered = false;
    queue_held_keycode = 0;
    queue_release_pending = false;
    
    // Clear all items
    memset(queue.items, 0, sizeof(queue.items));
}

// ============================================================================
// Queue Depth and Free Space
// ============================================================================
uint8_t queue_depth(void) {
    int16_t depth = (int16_t)queue.head - (int16_t)queue.tail;
    if (depth < 0) {
        depth += QUEUE_CAPACITY;
    }
    return (uint8_t)depth;
}

uint8_t queue_free_space(void) {
    return QUEUE_CAPACITY - queue_depth();
}

// ============================================================================
// Queue Push
// ============================================================================
uint8_t queue_push(const queue_item_t* items, uint8_t count) {
    uint8_t free_space = queue_free_space();
    uint8_t to_write = (count > free_space) ? free_space : count;
    
    if (to_write == 0) {
        // Queue is full
        uint8_t free = 0;
        protocol_send_event(EVT_QUEUE_HIGH, &free, 1);
        return 0;
    }
    
    // Write items to ring buffer
    for (uint8_t i = 0; i < to_write; i++) {
        queue.items[queue.head] = items[i];
        queue.head = (queue.head + 1) % QUEUE_CAPACITY;
    }
    
    // Check high watermark
    uint8_t current_depth = queue_depth();
    if (current_depth >= queue.high_watermark && !queue.high_watermark_triggered) {
        uint8_t free = queue_free_space();
        protocol_send_event(EVT_QUEUE_HIGH, &free, 1);
        queue.high_watermark_triggered = true;
    }
    
    // Reset high watermark flag if depth dropped below threshold
    if (current_depth < queue.high_watermark) {
        queue.high_watermark_triggered = false;
    }
    
    return to_write;
}

// ============================================================================
// Queue Pop
// ============================================================================
bool queue_pop(queue_item_t* item) {
    if (queue_depth() == 0) {
        return false;
    }
    
    *item = queue.items[queue.tail];
    queue.tail = (queue.tail + 1) % QUEUE_CAPACITY;
    
    // Check low watermark
    uint8_t current_depth = queue_depth();
    if (current_depth <= queue.low_watermark) {
        uint8_t remaining = current_depth;
        protocol_send_event(EVT_QUEUE_LOW, &remaining, 1);
    }
    
    return true;
}

// ============================================================================
// Queue Clear
// ============================================================================
void queue_clear(void) {
    queue_release_pending = true;
    exec_state.executing = false;
    exec_state.step = 0;
    queue.head = 0;
    queue.tail = 0;
    queue.state = QUEUE_STATE_IDLE;
    queue.high_watermark_triggered = false;
}

// ============================================================================
// Queue State Management
// ============================================================================
void queue_start(uint8_t profile_id) {
    queue.active_profile_id = profile_id;
    queue.state = QUEUE_STATE_RUNNING;
}

void queue_pause(void) {
    if (queue.state == QUEUE_STATE_RUNNING) {
        queue.state = QUEUE_STATE_PAUSED;
    }
}

void queue_resume(void) {
    if (queue.state == QUEUE_STATE_PAUSED) {
        queue.state = QUEUE_STATE_RUNNING;
    }
}

queue_state_t queue_get_state(void) {
    return queue.state;
}

// ============================================================================
// Queue Tick - Non-blocking Execution Engine
// ============================================================================

// Helper: Get profile parameter with RNG humanization
static int16_t get_humanized_delay(int16_t base_ms, uint8_t profile_id) {
    // Get profile pointer
    const profile_t* prof = profile_get(profile_id);
    if (!prof) return base_ms;  // fallback
    
    // Apply RNG: use Gaussian distribution with profile's key_interval
    int16_t sigma = prof->key_interval_sigma > 0 ? prof->key_interval_sigma : (base_ms / 5);
    int16_t min_val = base_ms / 2;
    int16_t max_val = base_ms * 2;
    int16_t delay = rng_gaussian(base_ms, sigma, min_val, max_val);
    return delay;
}

// Helper: Check and emit queue low event
static void check_queue_low(void) {
    uint8_t current_depth = queue_depth();
    if (current_depth <= queue.low_watermark) {
        uint8_t remaining = current_depth;
        protocol_send_event(EVT_QUEUE_LOW, &remaining, 1);
    }
}

// Interrupts are masked so a queue_clear from the UART IRQ cannot land between
// the pending check and the report.
static key_emit_t queue_emit_press(uint8_t keycode, uint8_t modifier) {
    uint32_t irq_state = save_and_disable_interrupts();
    if (queue_release_pending) {
        restore_interrupts(irq_state);
        return KEY_EMIT_ABORTED;
    }
    if (!hid_ready()) {
        restore_interrupts(irq_state);
        return KEY_EMIT_RETRY;
    }
    if (modifier > 0) {
        hid_keyboard_press_mod(keycode, modifier);
    } else {
        hid_keyboard_press(keycode);
    }
    queue_held_keycode = keycode;
    restore_interrupts(irq_state);
    return KEY_EMIT_SENT;
}

static key_emit_t queue_emit_release(void) {
    uint32_t irq_state = save_and_disable_interrupts();
    if (queue_release_pending) {
        restore_interrupts(irq_state);
        return KEY_EMIT_ABORTED;
    }
    if (!hid_ready()) {
        restore_interrupts(irq_state);
        return KEY_EMIT_RETRY;
    }
    hid_keyboard_release();
    queue_held_keycode = 0;
    restore_interrupts(irq_state);
    return KEY_EMIT_SENT;
}

// Helper: Execute keyboard tap
static void execute_key_tap(queue_item_t* item, uint8_t profile_id) {
    const profile_t* prof = profile_get(profile_id);
    if (!prof) return;
    
    // Determine keycode and modifiers
    uint8_t keycode = item->action;
    uint8_t modifier = (item->flags >> 4) & 0x0F;
    
    // Calculate humanized hold time using RNG
    int16_t hold_ms = rng_gaussian(prof->key_hold_mu, prof->key_hold_sigma,
                                    prof->key_hold_mu * 0.5, prof->key_hold_mu * 2.0);
    
    // Apply global pace adjustment
    hold_ms = (int16_t)(hold_ms * (100 + prof->pace_adjust) / 100);
    
    // Step 0: Key press
    if (exec_state.step == 0) {
        if (queue_emit_press(keycode, modifier) != KEY_EMIT_SENT) {
            return;
        }
        exec_state.step = 1;
        exec_state.step_start_us = time_us_32();
        exec_state.delay_us = hold_ms * 1000;
    }
    // Step 1: Hold delay
    else if (exec_state.step == 1) {
        uint32_t elapsed = time_us_32() - exec_state.step_start_us;
        if (elapsed >= exec_state.delay_us) {
            if (queue_emit_release() != KEY_EMIT_SENT) {
                return;
            }
            exec_state.executing = false;
        }
    }
}

static void execute_key_down(queue_item_t* item) {
    if (queue_emit_press(item->action, 0) != KEY_EMIT_SENT) {
        return;
    }
    exec_state.executing = false;
}

static void execute_key_up(queue_item_t* item) {
    if (queue_held_keycode == item->action) {
        if (queue_emit_release() != KEY_EMIT_SENT) {
            return;
        }
    }
    exec_state.executing = false;
}

// Helper: Execute mouse move
static void execute_mouse_move(queue_item_t* item, uint8_t profile_id) {
    const profile_t* prof = profile_get(profile_id);
    if (!prof) return;
    
    int16_t dx = (int16_t)item->param_a;
    int16_t dy = (int16_t)item->param_b;
    uint8_t bezier_flag = item->flags & 0x01;
    
    if (bezier_flag && prof->mouse_curve > 0) {
        // TODO: Implement Bézier curve interpolation
        // For now, fall back to direct movement
        hid_mouse_move_rel((int8_t)dx, (int8_t)dy);
    } else {
        // Direct movement
        hid_mouse_move_rel((int8_t)dx, (int8_t)dy);
    }
    
    exec_state.executing = false;
}

// Helper: Execute mouse click
static void execute_mouse_click(queue_item_t* item, uint8_t profile_id) {
    const profile_t* prof = profile_get(profile_id);
    if (!prof) return;
    
    uint8_t button = item->action;
    
    // Step 0: Button down
    if (exec_state.step == 0) {
        hid_mouse_button_down(button);
        exec_state.step = 1;
        exec_state.step_start_us = time_us_32();
        // Humanized click duration
        int16_t hold_sigma = prof->mouse_overshoot > 0 ? prof->mouse_overshoot : 10;
        int16_t hold_ms = rng_gaussian(50, hold_sigma, 20, 150);
        exec_state.delay_us = hold_ms * 1000;
    }
    // Step 1: Hold delay
    else if (exec_state.step == 1) {
        uint32_t elapsed = time_us_32() - exec_state.step_start_us;
        if (elapsed >= exec_state.delay_us) {
            hid_mouse_button_up(button);
            exec_state.executing = false;
        }
    }
}

// Helper: Execute wait
static void execute_wait(queue_item_t* item, uint8_t profile_id) {
    int16_t base_ms = (int16_t)item->param_a;
    
    // Step 0: Start waiting
    if (exec_state.step == 0) {
        int16_t delay_ms = get_humanized_delay(base_ms, profile_id);
        exec_state.step = 1;
        exec_state.step_start_us = time_us_32();
        exec_state.delay_us = delay_ms * 1000;
    }
    // Step 1: Wait delay
    else if (exec_state.step == 1) {
        uint32_t elapsed = time_us_32() - exec_state.step_start_us;
        if (elapsed >= exec_state.delay_us) {
            exec_state.executing = false;
        }
    }
}

// Helper: Execute Markov pause
static void execute_markov_pause(queue_item_t* item, uint8_t profile_id) {
    int16_t min_ms = (int16_t)item->param_a;
    int16_t max_ms = (int16_t)item->param_b;
    
    // Step 0: Calculate pause duration
    if (exec_state.step == 0) {
        // Random duration between min and max
        int16_t duration_ms = min_ms + rng_uniform((uint32_t)(max_ms - min_ms));
        exec_state.step = 1;
        exec_state.step_start_us = time_us_32();
        exec_state.delay_us = duration_ms * 1000;
    }
    // Step 1: Pause delay
    else if (exec_state.step == 1) {
        uint32_t elapsed = time_us_32() - exec_state.step_start_us;
        if (elapsed >= exec_state.delay_us) {
            exec_state.executing = false;
        }
    }
}

void queue_tick(void) {
    if (queue_release_pending) {
        if (hid_ready()) {
            hid_keyboard_release();
            queue_held_keycode = 0;
            queue_release_pending = false;
        }
        return;
    }

    if (queue.state != QUEUE_STATE_RUNNING) {
        return;
    }
    
    // Check if queue is empty
    if (queue_depth() == 0 && !exec_state.executing) {
        // Queue empty and not executing anything, transition to IDLE
        queue.state = QUEUE_STATE_IDLE;
        protocol_send_event(EVT_QUEUE_EMPTY, NULL, 0);
        return;
    }
    
    // Check queue low watermark
    check_queue_low();
    
    // If not currently executing, fetch next item
    if (!exec_state.executing) {
        if (queue_pop(&exec_state.current_item)) {
            exec_state.executing = true;
            exec_state.step = 0;
        } else {
            // Queue empty
            return;
        }
    }
    
    // Execute current item based on type
    if (exec_state.executing) {
        switch (exec_state.current_item.type) {
            case QUEUE_ITEM_KEY_TAP:
                execute_key_tap(&exec_state.current_item, queue.active_profile_id);
                break;
            case QUEUE_ITEM_KEY_DOWN:
                execute_key_down(&exec_state.current_item);
                break;
            case QUEUE_ITEM_KEY_UP:
                execute_key_up(&exec_state.current_item);
                break;
            case QUEUE_ITEM_MOUSE_TO:
                execute_mouse_move(&exec_state.current_item, queue.active_profile_id);
                break;
            case QUEUE_ITEM_CLICK:
                execute_mouse_click(&exec_state.current_item, queue.active_profile_id);
                break;
            case QUEUE_ITEM_WAIT:
                execute_wait(&exec_state.current_item, queue.active_profile_id);
                break;
            case QUEUE_ITEM_MARKOV_PAUSE:
                execute_markov_pause(&exec_state.current_item, queue.active_profile_id);
                break;
            default:
                // Unknown type, skip
                exec_state.executing = false;
                break;
        }
    }
}

// ============================================================================
// Queue Command Handler (called from protocol.c)
// ============================================================================
void queue_handle_command(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    switch (cmd) {
        case CMD_QUEUE_PUSH: {
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t item_count = payload[0];
            const queue_item_t* items = (const queue_item_t*)(payload + 1);
            
            if (1 + item_count * sizeof(queue_item_t) > len) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t written = queue_push(items, item_count);
            uint8_t response[3] = {written, queue_depth(), queue_free_space()};
            protocol_send_response(CMD_QUEUE_PUSH | 0x80, response, 3);
            break;
        }
        
        case CMD_QUEUE_START: {
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t profile_id = payload[0];
            queue_start(profile_id);
            protocol_send_response(CMD_QUEUE_START | 0x80, NULL, 0);
            break;
        }
        
        case CMD_QUEUE_PAUSE:
            queue_pause();
            protocol_send_response(CMD_QUEUE_PAUSE | 0x80, NULL, 0);
            break;
            
        case CMD_QUEUE_RESUME:
            queue_resume();
            protocol_send_response(CMD_QUEUE_RESUME | 0x80, NULL, 0);
            break;
            
        case CMD_QUEUE_CLEAR:
            queue_clear();
            protocol_send_response(CMD_QUEUE_CLEAR | 0x80, NULL, 0);
            break;
            
        case CMD_QUEUE_STATUS: {
            uint8_t response[3] = {queue_depth(), (uint8_t)queue_get_state(), queue_free_space()};
            protocol_send_response(CMD_QUEUE_STATUS | 0x80, response, 3);
            break;
        }
        
        // ========================================================================
        // Profile Commands
        // ========================================================================
        
        case CMD_PROFILE_SET: {
            // Set active profile for queue execution
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t profile_id = payload[0];
            if (profile_id >= PROFILE_COUNT) {
                uint8_t err = ERR_INVALID_PROFILE;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            queue.active_profile_id = profile_id;
            protocol_send_response(CMD_PROFILE_SET | 0x80, NULL, 0);
            break;
        }
        
        case CMD_PROFILE_GET: {
            // Get profile data
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t profile_id = payload[0];
            if (profile_id >= PROFILE_COUNT) {
                uint8_t err = ERR_INVALID_PROFILE;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            const profile_t* prof = profile_get(profile_id);
            if (!prof) {
                uint8_t err = ERR_PROFILE_NOT_FOUND;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            // Send profile data (22 bytes)
            protocol_send_response(CMD_PROFILE_GET | 0x80, (const uint8_t*)prof, sizeof(profile_t));
            break;
        }
        
        case CMD_PROFILE_WRITE: {
            // Write profile data to RAM
            if (len < 1 + sizeof(profile_t)) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t profile_id = payload[0];
            if (profile_id >= PROFILE_COUNT) {
                uint8_t err = ERR_INVALID_PROFILE;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            const profile_t* prof_data = (const profile_t*)(payload + 1);
            if (!profile_set(profile_id, prof_data)) {
                uint8_t err = ERR_PROFILE_WRITE_FAILED;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            protocol_send_response(CMD_PROFILE_WRITE | 0x80, NULL, 0);
            break;
        }
        
        case CMD_PROFILE_SAVE: {
            // Save profile(s) to Flash
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t mask = payload[0];
            if (mask == 0 || mask >= (1 << PROFILE_COUNT)) {
                uint8_t err = ERR_INVALID_MASK;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t saved_mask = profile_save(mask);
            protocol_send_response(CMD_PROFILE_SAVE | 0x80, &saved_mask, 1);
            break;
        }
        
        case CMD_PROFILE_LOAD: {
            // Load profile(s) from Flash
            if (len < 1) {
                uint8_t err = ERR_BAD_PAYLOAD;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t mask = payload[0];
            if (mask == 0 || mask >= (1 << PROFILE_COUNT)) {
                uint8_t err = ERR_INVALID_MASK;
                protocol_send_event(EVT_ERROR, &err, 1);
                return;
            }
            
            uint8_t loaded_mask = profile_load(mask);
            protocol_send_response(CMD_PROFILE_LOAD | 0x80, &loaded_mask, 1);
            break;
        }
        
        default:
            break;
    }
}
