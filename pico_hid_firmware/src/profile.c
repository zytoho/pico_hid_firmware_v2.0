#include "profile.h"
#include <string.h>
#include "hardware/flash.h"
#include "hardware/sync.h"
#include "pico/stdlib.h"

#define FLASH_TARGET_OFFSET (PICO_FLASH_SIZE_BYTES - FLASH_SECTOR_SIZE)

// Flash storage layout (256 bytes):
// [0-3]:   magic (0x50494348 "PICH")
// [4-163]: profiles[8] (8×20=160 bytes)
// [164-165]: CRC16

typedef struct __attribute__((packed)) {
    uint32_t magic;
    profile_t profiles[PROFILE_COUNT];
    uint16_t crc16;
} flash_profile_data_t;

static flash_profile_data_t flash_data;
static profile_t ram_mirror[PROFILE_COUNT];

// Default profiles (4 presets + 4 empty)
static const profile_t DEFAULT_PROFILES[PROFILE_COUNT] = {
    // Profile 0: Farming - high frequency, low markov
    {
        .id = 0,
        .key_hold_mu = 60, .key_hold_sigma = 12,
        .key_interval_mu = 200, .key_interval_sigma = 40,
        .mouse_curve = 1, .mouse_speed = 8, .mouse_overshoot = 30,
        .markov_prob = 5, .markov_min_ms = 500, .markov_max_ms = 2000,
        .action_rhythm = 1, .pace_adjust = 0
    },
    // Profile 1: Roaming - slow pace, high markov
    {
        .id = 1,
        .key_hold_mu = 90, .key_hold_sigma = 18,
        .key_interval_mu = 350, .key_interval_sigma = 70,
        .mouse_curve = 2, .mouse_speed = 5, .mouse_overshoot = 40,
        .markov_prob = 15, .markov_min_ms = 800, .markov_max_ms = 3000,
        .action_rhythm = 2, .pace_adjust = -10
    },
    // Profile 2: Looting - medium pace, low markov
    {
        .id = 2,
        .key_hold_mu = 75, .key_hold_sigma = 15,
        .key_interval_mu = 250, .key_interval_sigma = 50,
        .mouse_curve = 2, .mouse_speed = 6, .mouse_overshoot = 35,
        .markov_prob = 8, .markov_min_ms = 600, .markov_max_ms = 2500,
        .action_rhythm = 1, .pace_adjust = 0
    },
    // Profile 3: Elite - aggressive, minimal pauses
    {
        .id = 3,
        .key_hold_mu = 50, .key_hold_sigma = 10,
        .key_interval_mu = 150, .key_interval_sigma = 30,
        .mouse_curve = 1, .mouse_speed = 9, .mouse_overshoot = 25,
        .markov_prob = 3, .markov_min_ms = 400, .markov_max_ms = 1500,
        .action_rhythm = 0, .pace_adjust = 10
    },
    // Profiles 4-7: Empty (will be filled with profile 0 as fallback)
    { .id = 4 }, { .id = 5 }, { .id = 6 }, { .id = 7 }
};

// CRC16 calculation
static uint16_t crc16(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (int j = 0; j < 8; j++) {
            if (crc & 1) {
                crc = (crc >> 1) ^ 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}

// Initialize RAM mirror with defaults
static void init_defaults(void) {
    for (int i = 0; i < PROFILE_COUNT; i++) {
        if (DEFAULT_PROFILES[i].key_hold_mu > 0) {
            ram_mirror[i] = DEFAULT_PROFILES[i];
        } else {
            // Empty slots use profile 0 as fallback
            ram_mirror[i] = DEFAULT_PROFILES[0];
            ram_mirror[i].id = i;
        }
    }
}

void profile_init(void) {
    // Check if Flash has valid data
    const uint8_t* flash_ptr = (const uint8_t*)(XIP_BASE + FLASH_TARGET_OFFSET);
    uint32_t magic = *(uint32_t*)flash_ptr;
    
    if (magic == PROFILE_MAGIC) {
        // Load from Flash
        memcpy(&flash_data, flash_ptr, sizeof(flash_data));
        
        // Verify CRC
        uint16_t crc_calc = crc16((uint8_t*)&flash_data.magic, sizeof(flash_data) - 2);
        if (crc_calc == flash_data.crc16) {
            // Valid data, copy to RAM mirror
            memcpy(ram_mirror, flash_data.profiles, sizeof(ram_mirror));
        } else {
            // CRC mismatch, use defaults
            init_defaults();
        }
    } else {
        // No valid data, use defaults
        init_defaults();
    }
}

const profile_t* profile_get(uint8_t id) {
    if (id >= PROFILE_COUNT) return NULL;
    return &ram_mirror[id];
}

bool profile_set(uint8_t id, const profile_t* p) {
    if (id >= PROFILE_COUNT || !p) return false;
    ram_mirror[id] = *p;
    ram_mirror[id].id = id;
    return true;
}

bool profile_flash_valid(void) {
    const uint8_t* flash_ptr = (const uint8_t*)(XIP_BASE + FLASH_TARGET_OFFSET);
    uint32_t magic = *(uint32_t*)flash_ptr;
    if (magic != PROFILE_MAGIC) return false;
    
    const flash_profile_data_t* data = (const flash_profile_data_t*)flash_ptr;
    uint16_t crc_calc = crc16((uint8_t*)&data->magic, sizeof(flash_profile_data_t) - 2);
    return crc_calc == data->crc16;
}

uint8_t profile_save(uint8_t mask) {
    // Prepare flash data
    flash_data.magic = PROFILE_MAGIC;
    memcpy(flash_data.profiles, ram_mirror, sizeof(ram_mirror));
    
    // Calculate CRC
    flash_data.crc16 = crc16((uint8_t*)&flash_data.magic, sizeof(flash_data) - 2);
    
    // Pad to 256 bytes (one Flash page)
    uint8_t page_buf[256];
    memset(page_buf, 0xFF, sizeof(page_buf));
    memcpy(page_buf, &flash_data, sizeof(flash_data));
    
    // Write to Flash (must disable interrupts)
    uint32_t ints = save_and_disable_interrupts();
    flash_range_erase(FLASH_TARGET_OFFSET, FLASH_SECTOR_SIZE);
    flash_range_program(FLASH_TARGET_OFFSET, page_buf, sizeof(page_buf));
    restore_interrupts(ints);
    
    // Verify write
    return profile_flash_valid() ? mask : 0;
}

uint8_t profile_load(uint8_t mask) {
    const uint8_t* flash_ptr = (const uint8_t*)(XIP_BASE + FLASH_TARGET_OFFSET);
    
    // Check magic
    uint32_t magic = *(uint32_t*)flash_ptr;
    if (magic != PROFILE_MAGIC) return 0;
    
    // Read flash data
    memcpy(&flash_data, flash_ptr, sizeof(flash_data));
    
    // Verify CRC
    uint16_t crc_calc = crc16((uint8_t*)&flash_data.magic, sizeof(flash_data) - 2);
    if (crc_calc != flash_data.crc16) return 0;
    
    // Copy requested profiles to RAM mirror
    for (int i = 0; i < PROFILE_COUNT; i++) {
        if (mask & (1 << i)) {
            ram_mirror[i] = flash_data.profiles[i];
        }
    }
    
    return mask;
}
