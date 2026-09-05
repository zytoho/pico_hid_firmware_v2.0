#ifndef PROFILE_H
#define PROFILE_H

#include <stdint.h>
#include <stdbool.h>

#define PROFILE_COUNT     8
#define PROFILE_MAGIC     0x50494348  // "PICH"

// Profile structure for humanization parameters (packed for Flash storage)
typedef struct __attribute__((packed)) {
    uint8_t id;
    
    // Keyboard timing (Gaussian distribution parameters)
    uint16_t key_hold_mu;       // Mean hold time (ms)
    uint16_t key_hold_sigma;    // Std dev hold time (ms)
    uint16_t key_interval_mu;   // Mean interval (ms)
    uint16_t key_interval_sigma;// Std dev interval (ms)
    
    // Mouse movement
    uint8_t mouse_curve;        // 0=linear, 1=bezier, 2=bezier+microjitter
    uint8_t mouse_speed;        // 1-10 scale
    uint8_t mouse_overshoot;    // 0-100 probability
    
    // Markov pause
    uint8_t markov_prob;        // 0-100 probability
    uint16_t markov_min_ms;     // Minimum pause duration
    uint16_t markov_max_ms;     // Maximum pause duration
    
    // Action rhythm
    uint8_t action_rhythm;      // 0=mechanical, 1=rhythmic, 2=random
    
    // Global pace adjustment
    int16_t pace_adjust;        // -50 to +50 percent adjustment
} profile_t;

// Initialize profile system (loads from Flash or defaults)
void profile_init(void);

// Get pointer to profile in RAM mirror
const profile_t* profile_get(uint8_t id);

// Update profile in RAM mirror
bool profile_set(uint8_t id, const profile_t* p);

// Save selected profiles to Flash (mask: bit N = save profile N)
// Returns mask of successfully saved profiles
uint8_t profile_save(uint8_t mask);

// Load selected profiles from Flash to RAM mirror
// Returns mask of successfully loaded profiles
uint8_t profile_load(uint8_t mask);

// Check if Flash has valid profile data
bool profile_flash_valid(void);

#endif // PROFILE_H
