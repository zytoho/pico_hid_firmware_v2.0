#!/usr/bin/env python3
"""USB descriptor sanity checks for pico_hid_firmware v2.0."""

from pathlib import Path
import re
import unittest

SRC = Path(__file__).resolve().parents[1] / "src" / "usb_descriptors.c"
HID_H = Path(__file__).resolve().parents[1] / "src" / "hid.h"


class UsbDescriptorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SRC.read_text()
        cls.hid_h = HID_H.read_text()

    def test_bcd_usb_is_2_0_without_bos(self):
        """USB 2.1 (0x0210) requires a BOS descriptor this firmware does not provide."""
        self.assertRegex(
            self.src,
            r"\.bcdUSB\s*=\s*(USB_BCD|0x0200)\b",
            "bcdUSB must be USB 2.0 (0x0200) unless a BOS callback exists",
        )
        self.assertNotRegex(self.src, r"\.bcdUSB\s*=\s*0x0210\b")
        if "0x0210" in self.src or "USB_BCD" in self.src and "0x0210" in self.src:
            self.assertIn("tud_descriptor_bos_cb", self.src)

    def test_hid_report_len_uses_sizeof_not_ep_bufsize(self):
        """wReportDescLen must be sizeof(desc_hid_report), not a hardcoded 64."""
        self.assertIn("TUD_HID_DESCRIPTOR", self.src)
        self.assertIn(
            "sizeof(desc_hid_report)",
            self.src,
            "HID report descriptor length must be sizeof(desc_hid_report)",
        )
        # The old bug hard-coded 64 as wReportDescLen (4th argument).
        self.assertNotRegex(
            self.src,
            r"TUD_HID_DESCRIPTOR\s*\(\s*ITF_NUM_HID\s*,\s*0\s*,\s*HID_ITF_PROTOCOL_NONE\s*,\s*64\s*,",
        )

    def test_mouse_report_matches_tinyusb_mouse_api(self):
        """tud_hid_mouse_report() sends buttons+x+y+wheel+pan; descriptor must include pan."""
        uses_macro = "TUD_HID_REPORT_DESC_MOUSE" in self.src
        has_pan = bool(re.search(r"0x09,\s*0x38", self.src)) and (
            "pan" in self.src.lower() or "0x0C" in self.src or uses_macro
        )
        self.assertTrue(
            uses_macro or has_pan,
            "Mouse report must use TUD_HID_REPORT_DESC_MOUSE or include pan (5-byte report)",
        )

    def test_serial_comes_from_board_unique_id(self):
        self.assertIn("board_usb_get_serial", self.src)
        self.assertNotRegex(self.src, r'"123456"')

    def test_string_h_included(self):
        self.assertRegex(self.src, r"#include\s*<string\.h>")

    def test_report_ids_match_hid_h(self):
        mouse = re.search(r"#define\s+MOUSE_REPORT_ID\s+(\d+)", self.hid_h)
        keyboard = re.search(r"#define\s+KEYBOARD_REPORT_ID\s+(\d+)", self.hid_h)
        self.assertIsNotNone(mouse)
        self.assertIsNotNone(keyboard)
        self.assertIn("MOUSE_REPORT_ID", self.src)
        self.assertIn("KEYBOARD_REPORT_ID", self.src)


if __name__ == "__main__":
    unittest.main()
