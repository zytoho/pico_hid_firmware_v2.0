/*
 * TinyUSB Configuration for Pico HID Firmware
 * Composite HID: Mouse + Keyboard
 */

#ifndef _TUSB_CONFIG_H_
#define _TUSB_CONFIG_H_

#ifdef __cplusplus
 extern "C" {
#endif

// RP2040 USB port: Device mode, Full Speed
#ifndef CFG_TUSB_RHPORT0_MODE
#define CFG_TUSB_RHPORT0_MODE   (OPT_MODE_DEVICE)
#endif

#define CFG_TUD_ENABLED         1
#define CFG_TUH_ENABLED         0

//--------------------------------------------------------------------
// Device Configuration
//--------------------------------------------------------------------
#define CFG_TUD_ENDPOINT0_SIZE  64

// Class drivers
#define CFG_TUD_CDC             0
#define CFG_TUD_MSC             0
#define CFG_TUD_HID             1
#define CFG_TUD_MIDI            0
#define CFG_TUD_VENDOR          0

//--------------------------------------------------------------------
// HID Configuration
//--------------------------------------------------------------------
#define CFG_TUD_HID_EP_BUFSIZE  64

#ifdef __cplusplus
 }
#endif

#endif /* _TUSB_CONFIG_H_ */
