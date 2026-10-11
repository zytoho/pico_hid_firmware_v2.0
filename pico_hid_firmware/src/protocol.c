// Protocol implementation for Pico HID Firmware v2.0
// Binary frame protocol with CRC-16/MODBUS

#include "protocol.h"
#include "hardware/sync.h"
#include "hardware/uart.h"
#include <string.h>

// UART instance for protocol communication
#define PROTO_UART          uart0
#define PROTO_BAUD_RATE     115200

// ============================================================================
// CRC-16/MODBUS Implementation
// ============================================================================

static uint16_t crc16_modbus(const uint8_t *data, uint16_t length) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; j++) {
            if (crc & 0x0001) {
                crc >>= 1;
                crc ^= 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// ============================================================================
// Frame Parser State Machine
// ============================================================================

typedef enum {
    PARSE_WAIT_SOH1,
    PARSE_WAIT_SOH2,
    PARSE_LENGTH,
    PARSE_CMD,
    PARSE_PAYLOAD,
    PARSE_CRC_HIGH,
    PARSE_CRC_LOW
} parse_state_t;

static parse_state_t parse_state = PARSE_WAIT_SOH1;
static uint8_t rx_length = 0;
static uint8_t rx_cmd = 0;
static uint8_t rx_payload[FRAME_MAX_PAYLOAD];
static uint8_t rx_payload_idx = 0;

// Completed frames wait here until the main loop calls protocol_poll().
// cmd_dispatch sleeps and talks to USB; doing that inside the UART ISR wedges the chip.
#define RX_FRAME_QUEUE 16

typedef struct {
    uint8_t cmd;
    uint8_t len;
    uint8_t payload[FRAME_MAX_PAYLOAD];
} rx_frame_t;

static rx_frame_t rx_frames[RX_FRAME_QUEUE];
static volatile uint8_t rx_frame_head = 0;
static volatile uint8_t rx_frame_tail = 0;

static bool rx_frame_push(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    uint8_t next = (uint8_t)((rx_frame_head + 1) % RX_FRAME_QUEUE);
    if (next == rx_frame_tail) {
        return false;
    }
    rx_frames[rx_frame_head].cmd = cmd;
    rx_frames[rx_frame_head].len = len;
    if (len > 0 && payload != NULL) {
        memcpy(rx_frames[rx_frame_head].payload, payload, len);
    }
    __dmb();
    rx_frame_head = next;
    return true;
}

// ============================================================================
// Protocol Implementation
// ============================================================================

void protocol_init(void) {
    parse_state = PARSE_WAIT_SOH1;
    rx_payload_idx = 0;
    rx_frame_head = 0;
    rx_frame_tail = 0;
}

void protocol_process_byte(uint8_t byte) {
    switch (parse_state) {
        case PARSE_WAIT_SOH1:
            if (byte == FRAME_SOH1) {
                parse_state = PARSE_WAIT_SOH2;
            }
            break;
            
        case PARSE_WAIT_SOH2:
            if (byte == FRAME_SOH2) {
                parse_state = PARSE_LENGTH;
            } else {
                // Invalid sequence, reset
                parse_state = PARSE_WAIT_SOH1;
            }
            break;
            
        case PARSE_LENGTH:
            rx_length = byte;
            if (rx_length > FRAME_MAX_PAYLOAD) {
                // Invalid length, send error and reset
                uint8_t error_payload[] = {ERR_BAD_PAYLOAD, 0x00};
                protocol_send_event(EVT_ERROR, error_payload, 2);
                parse_state = PARSE_WAIT_SOH1;
            } else {
                parse_state = PARSE_CMD;
                rx_payload_idx = 0;
            }
            break;
            
        case PARSE_CMD:
            rx_cmd = byte;
            if (rx_length == 0) {
                // No payload, wait for CRC
                parse_state = PARSE_CRC_HIGH;
            } else {
                parse_state = PARSE_PAYLOAD;
            }
            break;
            
        case PARSE_PAYLOAD:
            rx_payload[rx_payload_idx++] = byte;
            if (rx_payload_idx >= rx_length) {
                parse_state = PARSE_CRC_HIGH;
            }
            break;
            
        case PARSE_CRC_HIGH:
            // Store CRC high byte temporarily in rx_payload[rx_length]
            rx_payload[rx_length] = byte;
            parse_state = PARSE_CRC_LOW;
            break;
            
        case PARSE_CRC_LOW: {
            // Store CRC low byte
            rx_payload[rx_length + 1] = byte;
            
            // Extract received CRC
            uint16_t received_crc = ((uint16_t)rx_payload[rx_length] << 8) | 
                                     rx_payload[rx_length + 1];
            
            // Calculate expected CRC (over length + cmd + payload)
            uint8_t crc_buffer[1 + 1 + FRAME_MAX_PAYLOAD];
            crc_buffer[0] = rx_length;
            crc_buffer[1] = rx_cmd;
            memcpy(&crc_buffer[2], rx_payload, rx_length);
            
            uint16_t calculated_crc = crc16_modbus(crc_buffer, 2 + rx_length);
            
            if (received_crc == calculated_crc) {
                if (!rx_frame_push(rx_cmd, rx_payload, rx_length)) {
                    uint8_t error_payload[] = {ERR_QUEUE_FULL, 0x00};
                    protocol_send_event(EVT_ERROR, error_payload, 2);
                }
            } else {
                // CRC error
                uint8_t error_payload[] = {ERR_BAD_CRC, 0x00};
                protocol_send_event(EVT_ERROR, error_payload, 2);
            }
            
            // Reset for next frame
            parse_state = PARSE_WAIT_SOH1;
            break;
        }
    }
}

void protocol_poll(void) {
    while (rx_frame_tail != rx_frame_head) {
        rx_frame_t* frame = &rx_frames[rx_frame_tail];
        cmd_dispatch(frame->cmd, frame->payload, frame->len);
        __dmb();
        rx_frame_tail = (uint8_t)((rx_frame_tail + 1) % RX_FRAME_QUEUE);
    }
}

void protocol_send_response(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    if (len > FRAME_MAX_PAYLOAD) return;
    
    // Build frame: SOH1 SOH2 LENGTH CMD PAYLOAD CRC_HIGH CRC_LOW
    uint8_t frame[FRAME_MAX_LEN];
    uint8_t idx = 0;
    
    frame[idx++] = FRAME_SOH1;
    frame[idx++] = FRAME_SOH2;
    frame[idx++] = len;
    frame[idx++] = cmd;
    
    if (len > 0 && payload != NULL) {
        memcpy(&frame[idx], payload, len);
        idx += len;
    }
    
    // Calculate CRC over length + cmd + payload
    uint16_t crc = crc16_modbus(&frame[2], 1 + 1 + len);
    frame[idx++] = (crc >> 8) & 0xFF;  // CRC high
    frame[idx++] = crc & 0xFF;          // CRC low
    
    // Send frame
    uart_write_blocking(PROTO_UART, frame, idx);
}

void protocol_send_event(uint8_t event, const uint8_t* payload, uint8_t len) {
    protocol_send_response(event, payload, len);
}
