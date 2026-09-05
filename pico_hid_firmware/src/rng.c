#include "rng.h"

// ============================================================================
// XORSHIFT32 PRNG State
// ============================================================================
static uint32_t rng_state;

// ============================================================================
// Gaussian LUT (256 levels, N(0,1) sampled at uniform quantiles)
// Values scaled to [-128, +128) via quantile * 128/3
// Generated: norm.ppf((i+0.5)/256) * 128/3, i in [0,255]
// ============================================================================
static const int8_t gauss_lut[256] = {
    -123,-107,-100, -94, -90, -86, -83, -81, -78, -76, -74, -72, -71, -69, -68, -66,
     -65, -63, -62, -61, -60, -59, -58, -57, -56, -55, -54, -53, -52, -51, -50, -49,
     -49, -48, -47, -46, -46, -45, -44, -43, -43, -42, -41, -41, -40, -39, -39, -38,
     -38, -37, -36, -36, -35, -35, -34, -33, -33, -32, -32, -31, -31, -30, -30, -29,
     -29, -28, -27, -27, -26, -26, -25, -25, -24, -24, -23, -23, -23, -22, -22, -21,
     -21, -20, -20, -19, -19, -18, -18, -17, -17, -16, -16, -16, -15, -15, -14, -14,
     -13, -13, -13, -12, -12, -11, -11, -10, -10,  -9,  -9,  -9,  -8,  -8,  -7,  -7,
      -7,  -6,  -6,  -5,  -5,  -4,  -4,  -4,  -3,  -3,  -2,  -2,  -1,  -1,  -1,   0,
       0,   1,   1,   1,   2,   2,   3,   3,   4,   4,   4,   5,   5,   6,   6,   7,
       7,   7,   8,   8,   9,   9,   9,  10,  10,  11,  11,  12,  12,  13,  13,  13,
      14,  14,  15,  15,  16,  16,  16,  17,  17,  18,  18,  19,  19,  20,  20,  21,
      21,  22,  22,  23,  23,  23,  24,  24,  25,  25,  26,  26,  27,  27,  28,  29,
      29,  30,  30,  31,  31,  32,  32,  33,  33,  34,  35,  35,  36,  36,  37,  38,
      38,  39,  39,  40,  41,  41,  42,  43,  43,  44,  45,  46,  46,  47,  48,  49,
      49,  50,  51,  52,  53,  54,  55,  56,  57,  58,  59,  60,  61,  62,  63,  65,
      66,  68,  69,  71,  72,  74,  76,  78,  81,  83,  86,  90,  94, 100, 107, 123,
};

// ============================================================================
// Initialization
// ============================================================================
void rng_init(uint32_t seed) {
    // Ensure non-zero state
    rng_state = seed ? seed : 0x12345678;
}

// ============================================================================
// XORSHIFT32 Algorithm
// ============================================================================
static uint32_t xorshift32(void) {
    uint32_t x = rng_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    rng_state = x;
    return x;
}

// ============================================================================
// Uniform Random in [0, max)
// Uses rejection sampling to avoid modulo bias
// ============================================================================
uint32_t rng_uniform(uint32_t max) {
    if (max == 0) return 0;
    
    // For small ranges, simple modulo is acceptable
    if (max < 256) {
        return xorshift32() % max;
    }
    
    // For larger ranges, use rejection sampling
    uint32_t threshold = (0xFFFFFFFF / max) * max;
    uint32_t r;
    do {
        r = xorshift32();
    } while (r >= threshold);
    
    return r % max;
}

// ============================================================================
// Gaussian Sampling via LUT
// 
// Algorithm:
// 1. Generate uniform index [0, 255]
// 2. Look up N(0,1) sample from LUT (scaled to [-128, +127])
// 3. Apply linear transform: result = mu + (lut_val * sigma / 128)
// 4. Clamp to [min_val, max_val]
//
// Performance: ~1μs per sample (integer arithmetic only)
// ============================================================================
int16_t rng_gaussian(int16_t mu, int16_t sigma, int16_t min_val, int16_t max_val) {
    // Generate uniform index
    uint8_t idx = (uint8_t)(xorshift32() & 0xFF);
    
    // Look up standard normal sample
    int16_t z = gauss_lut[idx];  // [-128, +127]
    
    // Linear transform: result = mu + z * sigma / 128
    int32_t result = (int32_t)mu + ((int32_t)z * sigma / 128);
    
    // Clamp to range
    if (result < min_val) result = min_val;
    if (result > max_val) result = max_val;
    
    return (int16_t)result;
}
