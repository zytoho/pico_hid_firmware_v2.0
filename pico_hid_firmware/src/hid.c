#include "hid.h"
#include "tusb.h"
#include "pico/stdlib.h"
#include <string.h>

// Mouse report state
static struct {
    uint8_t buttons;
    int8_t  x, y;
    int8_t  scroll;
} mouse_report = {0};

// Keyboard report state
static struct {
    uint8_t modifier;
    uint8_t keycode[6];
} kb_report = {0};

void hid_init(void) {
    memset(&mouse_report, 0, sizeof(mouse_report));
    memset(&kb_report, 0, sizeof(kb_report));
}

bool hid_ready(void) {
    return tud_hid_ready();
}

void hid_mouse_move_rel(int8_t dx, int8_t dy) {
    if (!tud_hid_ready()) return;
    tud_hid_mouse_report(MOUSE_REPORT_ID, 0, dx, dy, 0, 0);
}

void hid_mouse_button_down(uint8_t button) {
    if (!tud_hid_ready()) return;
    mouse_report.buttons |= button;
    tud_hid_mouse_report(MOUSE_REPORT_ID, mouse_report.buttons, 0, 0, 0, 0);
}

void hid_mouse_button_up(uint8_t button) {
    if (!tud_hid_ready()) return;
    mouse_report.buttons &= ~button;
    tud_hid_mouse_report(MOUSE_REPORT_ID, mouse_report.buttons, 0, 0, 0, 0);
}

void hid_mouse_scroll(int8_t delta) {
    if (!tud_hid_ready()) return;
    tud_hid_mouse_report(MOUSE_REPORT_ID, 0, 0, 0, delta, 0);
}

void hid_keyboard_press(uint8_t keycode) {
    if (!tud_hid_ready()) return;
    memset(&kb_report, 0, sizeof(kb_report));
    kb_report.keycode[0] = keycode;
    tud_hid_keyboard_report(KEYBOARD_REPORT_ID, 0, kb_report.keycode);
}

void hid_keyboard_press_mod(uint8_t keycode, uint8_t modifier) {
    if (!tud_hid_ready()) return;
    memset(&kb_report, 0, sizeof(kb_report));
    kb_report.modifier = modifier;
    kb_report.keycode[0] = keycode;
    tud_hid_keyboard_report(KEYBOARD_REPORT_ID, modifier, kb_report.keycode);
}

void hid_keyboard_release(void) {
    if (!tud_hid_ready()) return;
    memset(&kb_report, 0, sizeof(kb_report));
    tud_hid_keyboard_report(KEYBOARD_REPORT_ID, 0, NULL);
}
