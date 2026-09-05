// Protocol definitions for Pico HID Firmware v2.0
// Binary frame protocol with CRC-16/MODBUS

#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

// ============================================================================
// Frame Format
// ============================================================================
#define FRAME_SOH1          0xAA
#define FRAME_SOH2          0x55
#define FRAME_MAX_PAYLOAD   248
#define FRAME_MAX_LEN       253

// ============================================================================
// Command Codes (Host → Pico)
// ============================================================================

// System commands (0x00-0x0F)
#define CMD_PING            0x01
#define CMD_RESET           0x02
#define CMD_GET_VERSION     0x03

// Raw input commands (0x10-0x2F)
#define CMD_KEY_DOWN        0x10
#define CMD_KEY_UP          0x11
#define CMD_KEY_TAP         0x12
#define CMD_MOUSE_ABS       0x20
#define CMD_MOUSE_REL       0x21
#define CMD_MOUSE_CLICK     0x22
#define CMD_MOUSE_SCROLL    0x23

// Queue/macro commands (0x30-0x3F)
#define CMD_QUEUE_PUSH      0x30
#define CMD_QUEUE_START     0x31
#define CMD_QUEUE_PAUSE     0x32
#define CMD_QUEUE_RESUME    0x33
#define CMD_QUEUE_CLEAR     0x34
#define CMD_QUEUE_STATUS    0x35

// Profile commands (0x40-0x4F)
#define CMD_PROFILE_SET     0x40
#define CMD_PROFILE_GET     0x41
#define CMD_PROFILE_WRITE   0x42
#define CMD_PROFILE_SAVE    0x43
#define CMD_PROFILE_LOAD    0x44

// ============================================================================
// Event Codes (Pico → Host)
// ============================================================================
#define EVT_QUEUE_EMPTY     0xF0
#define EVT_QUEUE_LOW       0xF1
#define EVT_ERROR           0xF2
#define EVT_MOUNT           0xF3
#define EVT_READY           0xF4
#define EVT_QUEUE_HIGH      0xF5

// ============================================================================
// Error Codes
// ============================================================================
#define ERR_NONE            0x00
#define ERR_BAD_CRC         0x01
#define ERR_BAD_CMD         0x02
#define ERR_BAD_PAYLOAD     0x03
#define ERR_QUEUE_FULL      0x04
#define ERR_PROFILE_INVALID 0x05
#define ERR_INVALID_PROFILE 0x06
#define ERR_PROFILE_NOT_FOUND 0x07
#define ERR_PROFILE_WRITE_FAILED 0x08
#define ERR_INVALID_MASK    0x09

// ============================================================================
// Protocol API
// ============================================================================

// Initialize protocol state
void protocol_init(void);

// Process received byte (call from UART RX interrupt)
void protocol_process_byte(uint8_t byte);

// Send response frame (CMD | 0x80)
void protocol_send_response(uint8_t cmd, const uint8_t* payload, uint8_t len);

// Send event frame (EVT_xxx)
void protocol_send_event(uint8_t event, const uint8_t* payload, uint8_t len);

// Command handler callback (implemented in main.c)
void cmd_dispatch(uint8_t cmd, const uint8_t* payload, uint8_t len);

#endif // PROTOCOL_H
