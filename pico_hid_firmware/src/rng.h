#ifndef RNG_H
#define RNG_H

#include <stdint.h>

/**
 * RNG Module for Humanization
 * 
 * Provides:
 * - Uniform random number generation (XORSHIFT32)
 * - Gaussian distribution sampling via 256-level LUT
 * - Pure integer arithmetic, no FPU required
 */

/**
 * Initialize RNG with seed
 * @param seed Initial seed value (typically from time_us_32())
 */
void rng_init(uint32_t seed);

/**
 * Generate uniform random number in range [0, max)
 * @param max Upper bound (exclusive)
 * @return Random number in [0, max)
 */
uint32_t rng_uniform(uint32_t max);

/**
 * Generate Gaussian distributed random number
 * Uses 256-level LUT for fast sampling
 * 
 * @param mu Mean value
 * @param sigma Standard deviation (σ)
 * @param min_val Minimum clamp value
 * @param max_val Maximum clamp value
 * @return Sample from N(mu, sigma^2) clamped to [min_val, max_val]
 * 
 * Performance: ~1μs per sample (no FPU)
 */
int16_t rng_gaussian(int16_t mu, int16_t sigma, int16_t min_val, int16_t max_val);

#endif // RNG_H
