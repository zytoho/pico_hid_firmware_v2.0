// Pico HID Firmware v2.0
// Smart co-processor with queue engine and humanization
// Main entry point and command dispatcher

#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "pico/stdlib.h"
#include "hardware/uart.h"
#include "hardware/irq.h"
#include "hardware/watchdog.h"
#include "bsp/board.h"
#include "tusb.h"
#include "protocol.h"
#include "queue.h"

// ============================================================================
// Hardware Configuration
// ============================================================================
#define UART_ID         uart0
#define BAUD_RATE       115200
#define UART_TX_PIN     0
#define UART_RX_PIN     1
#define LED_PIN         25

// ============================================================================
// HID Report Definitions
// ============================================================================
#define MOUSE_REPORT_SIZE    4
#define KEYBOARD_REPORT_SIZE 8

typedef struct __attribute__((packed)) {
    uint8_t buttons;
    int8_t  x;
    int8_t  y;
    int8_t  scroll;
} mouse_report_t;

typedef struct __attribute__((packed)) {
    uint8_t modifier;
    uint8_t reserved;
    uint8_t keycode[6];
} keyboard_report_t;

// ============================================================================
// Global State
// ============================================================================
static volatile mouse_report_t    mouse_report   = {0};
static volatile keyboard_report_t kb_report      = {0};
static volatile bool              mouse_pending  = false;
static volatile bool              kb_pending     = false;

// Absolute coordinate tracking
static int16_t cursor_x = 0;
static int16_t cursor_y = 0;

// USB mount state
static bool usb_mounted_last = false;

// Firmware version
#define FW_VERSION_MAJOR 2
#define FW_VERSION_MINOR 0
#define FW_VERSION_PATCH 0

// ============================================================================
// HID Report Sending
// ============================================================================

static void flush_mouse_report(void) {
    if (tud_hid_ready()) {
        tud_hid_mouse_report(1, mouse_report.buttons,
                             mouse_report.x, mouse_report.y,
                             mouse_report.scroll, 0);
        mouse_report.buttons = 0;
        mouse_report.x = 0;
        mouse_report.y = 0;
        mouse_report.scroll = 0;
    }
}

static void flush_keyboard_report(void) {
    if (tud_hid_ready()) {
        tud_hid_keyboard_report(2, kb_report.modifier, (const uint8_t*)kb_report.keycode);
        memset((void*)&kb_report, 0, sizeof(keyboard_report_t));
        kb_pending = false;
    }
}

// Split large movements into int8_t steps
static void send_relative_move(int16_t dx, int16_t dy) {
    while (dx != 0 || dy != 0) {
        int8_t step_x = (dx > 127) ? 127 : (dx < -127) ? -127 : (int8_t)dx;
        int8_t step_y = (dy > 127) ? 127 : (dy < -127) ? -127 : (int8_t)dy;

        mouse_report.x = step_x;
        mouse_report.y = step_y;
        mouse_pending = true;
        flush_mouse_report();

        dx -= step_x;
        dy -= step_y;

        if (dx != 0 || dy != 0) {
            tud_task();
            sleep_us(100);
        }
    }
}

// Button number to bitmask conversion
static uint8_t btn_to_mask(int btn) {
    switch (btn) {
        case 1: return 0x01; // MOUSE_BUTTON_LEFT
        case 2: return 0x02; // MOUSE_BUTTON_RIGHT
        case 3: return 0x04; // MOUSE_BUTTON_MIDDLE
        default: return 0;
    }
}

// ============================================================================
// Command Dispatcher (Protocol v2.0)
// ============================================================================

void cmd_dispatch(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    switch (cmd) {
        // System commands
        case CMD_PING:
            protocol_send_response(CMD_PING | 0x80, NULL, 0);
            break;
            
        case CMD_GET_VERSION: {
            uint8_t version[3] = {FW_VERSION_MAJOR, FW_VERSION_MINOR, FW_VERSION_PATCH};
            protocol_send_response(CMD_GET_VERSION | 0x80, version, 3);
            break;
        }
            
        case CMD_RESET:
            // Soft reset via watchdog
            watchdog_reboot(0, 0, 0);
            break;
            
        // Raw keyboard commands
        case CMD_KEY_DOWN:
            if (len >= 1) {
                kb_report.keycode[0] = payload[0];
                kb_pending = true;
                flush_keyboard_report();
                protocol_send_response(CMD_KEY_DOWN | 0x80, NULL, 0);
            }
            break;
            
        case CMD_KEY_UP:
            if (len >= 1) {
                kb_report.keycode[0] = 0;
                kb_pending = true;
                flush_keyboard_report();
                protocol_send_response(CMD_KEY_UP | 0x80, NULL, 0);
            }
            break;
            
        case CMD_KEY_TAP:
            if (len >= 3) {
                uint8_t keycode = payload[0];
                uint16_t hold_ms = (payload[1] << 8) | payload[2];
                
                kb_report.keycode[0] = keycode;
                kb_pending = true;
                flush_keyboard_report();
                
                sleep_ms(hold_ms);
                
                kb_report.keycode[0] = 0;
                kb_pending = true;
                flush_keyboard_report();
                
                protocol_send_response(CMD_KEY_TAP | 0x80, NULL, 0);
            }
            break;
            
        // Raw mouse commands
        case CMD_MOUSE_ABS:
            if (len >= 4) {
                int16_t target_x = (int16_t)((payload[0] << 8) | payload[1]);
                int16_t target_y = (int16_t)((payload[2] << 8) | payload[3]);
                
                int16_t dx = target_x - cursor_x;
                int16_t dy = target_y - cursor_y;
                
                cursor_x = target_x;
                cursor_y = target_y;
                
                send_relative_move(dx, dy);
                protocol_send_response(CMD_MOUSE_ABS | 0x80, NULL, 0);
            }
            break;
            
        case CMD_MOUSE_REL:
            if (len >= 4) {
                int16_t dx = (int16_t)((payload[0] << 8) | payload[1]);
                int16_t dy = (int16_t)((payload[2] << 8) | payload[3]);
                
                cursor_x += dx;
                cursor_y += dy;
                
                send_relative_move(dx, dy);
                protocol_send_response(CMD_MOUSE_REL | 0x80, NULL, 0);
            }
            break;
            
        case CMD_MOUSE_CLICK:
            if (len >= 3) {
                uint8_t btn = payload[0];
                uint16_t hold_ms = (payload[1] << 8) | payload[2];
                
                uint8_t mask = btn_to_mask(btn);
                mouse_report.buttons = mask;
                mouse_pending = true;
                flush_mouse_report();
                
                sleep_ms(hold_ms);
                
                mouse_report.buttons = 0;
                mouse_pending = true;
                flush_mouse_report();
                
                protocol_send_response(CMD_MOUSE_CLICK | 0x80, NULL, 0);
            }
            break;
            
        case CMD_MOUSE_SCROLL:
            if (len >= 2) {
                int16_t delta = (int16_t)((payload[0] << 8) | payload[1]);
                
                while (delta != 0) {
                    int8_t step = (delta > 127) ? 127 : (delta < -127) ? -127 : (int8_t)delta;
                    mouse_report.scroll = step;
                    mouse_pending = true;
                    flush_mouse_report();
                    
                    delta -= step;
                    if (delta != 0) {
                        tud_task();
                        sleep_us(500);
                    }
                }
                
                protocol_send_response(CMD_MOUSE_SCROLL | 0x80, NULL, 0);
            }
            break;
            
        // Queue commands - delegate to queue handler
        case CMD_QUEUE_PUSH:
        case CMD_QUEUE_START:
        case CMD_QUEUE_PAUSE:
        case CMD_QUEUE_RESUME:
        case CMD_QUEUE_CLEAR:
        case CMD_QUEUE_STATUS:
            queue_handle_command(cmd, payload, len);
            break;
            
        // Profile commands - delegate to queue handler
        case CMD_PROFILE_SET:
        case CMD_PROFILE_GET:
        case CMD_PROFILE_WRITE:
        case CMD_PROFILE_SAVE:
        case CMD_PROFILE_LOAD:
            queue_handle_command(cmd, payload, len);
            break;
            
        default:
            // Unknown command
            {
                uint8_t error_payload[] = {ERR_BAD_CMD, cmd};
                protocol_send_event(EVT_ERROR, error_payload, 2);
            }
            break;
    }
}

// ============================================================================
// UART Interrupt Handler
// ============================================================================

static void on_uart_rx(void) {
    while (uart_is_readable(UART_ID)) {
        uint8_t byte = uart_getc(UART_ID);
        protocol_process_byte(byte);
    }
}

// ============================================================================
// TinyUSB HID Callbacks
// ============================================================================

uint16_t tud_hid_get_report_cb(uint8_t instance, uint8_t report_id,
                                hid_report_type_t report_type,
                                uint8_t* buffer, uint16_t reqlen) {
    (void) instance;
    (void) report_id;
    (void) report_type;
    (void) buffer;
    (void) reqlen;
    return 0;
}

void tud_hid_set_report_cb(uint8_t instance, uint8_t report_id,
                            hid_report_type_t report_type,
                            uint8_t const* buffer, uint16_t bufsize) {
    (void) instance;
    (void) report_id;
    if (report_type == HID_REPORT_TYPE_OUTPUT) {
        if (bufsize > 0) {
            if (buffer[0] & 0x02) {
                gpio_put(LED_PIN, 1);
            } else {
                gpio_put(LED_PIN, 0);
            }
        }
    }
}

// ============================================================================
// Main
// ============================================================================

int main(void) {
    board_init();
    tusb_init();
    
    // Initialize protocol
    protocol_init();
    queue_init();
    
    // LED init
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    
    // UART init
    uart_init(UART_ID, BAUD_RATE);
    gpio_set_function(UART_TX_PIN, GPIO_FUNC_UART);
    gpio_set_function(UART_RX_PIN, GPIO_FUNC_UART);
    uart_set_format(UART_ID, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(UART_ID, true);
    
    // Register UART RX interrupt
    irq_set_exclusive_handler(UART0_IRQ, on_uart_rx);
    irq_set_enabled(UART0_IRQ, true);
    uart_set_irq_enables(UART_ID, true, false);
    
    // Startup LED blink
    for (int i = 0; i < 3; i++) {
        gpio_put(LED_PIN, 1);
        sleep_ms(100);
        gpio_put(LED_PIN, 0);
        sleep_ms(100);
    }
    
    // Send EVT_READY
    protocol_send_event(EVT_READY, NULL, 0);
    
    // Main loop
    while (1) {
        tud_task();
        queue_tick();
        
        // LED: solid ON when USB mounted
        bool mounted = tud_mounted();
        if (mounted && !usb_mounted_last) {
            gpio_put(LED_PIN, 1);
            usb_mounted_last = true;
        } else if (!mounted) {
            usb_mounted_last = false;
        }
    }
    
    return 0;
}
