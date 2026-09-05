#ifndef HID_H
#define HID_H

#include <stdint.h>
#include <stdbool.h>

/**
 * HID report sending interface
 */

// Report IDs
#define MOUSE_REPORT_ID  1
#define KEYBOARD_REPORT_ID 2

// Mouse buttons (使用 HID_ 前缀避免与 TinyUSB 冲突)
#define HID_MOUSE_BUTTON_LEFT   0x01
#define HID_MOUSE_BUTTON_RIGHT  0x02
#define HID_MOUSE_BUTTON_MIDDLE 0x04

// Initialize HID subsystem
void hid_init(void);

// Mouse reports
void hid_mouse_move_rel(int8_t dx, int8_t dy);
void hid_mouse_click(uint8_t button);
void hid_mouse_scroll(int8_t delta);

// Keyboard reports
void hid_keyboard_press(uint8_t keycode);
void hid_keyboard_press_mod(uint8_t keycode, uint8_t modifier);
void hid_keyboard_release(void);

// Mouse reports (split for press/release)
void hid_mouse_button_down(uint8_t button);
void hid_mouse_button_up(uint8_t button);

// Utility
bool hid_ready(void);

#endif // HID_H
