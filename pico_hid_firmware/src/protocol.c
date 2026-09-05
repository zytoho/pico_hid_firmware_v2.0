// Protocol implementation for Pico HID Firmware v2.0
// Binary frame protocol with CRC-16/MODBUS

#include "protocol.h"
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

// ============================================================================
// Protocol Implementation
// ============================================================================

void protocol_init(void) {
    parse_state = PARSE_WAIT_SOH1;
    rx_payload_idx = 0;
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
                // Valid frame, dispatch command
                cmd_dispatch(rx_cmd, rx_payload, rx_length);
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
