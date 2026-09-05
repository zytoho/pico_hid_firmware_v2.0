cmake_minimum_required(VERSION 3.13)

# Pull in SDK (must be before project)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(pico_hid_firmware C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(pico_hid_firmware
    src/main.c
    src/usb_descriptors.c
    src/protocol.c
    src/queue.c
    src/rng.c
    src/bezier.c
    src/hid.c
    src/profile.c
)

target_include_directories(pico_hid_firmware PRIVATE
    ${CMAKE_CURRENT_LIST_DIR}/src
)

target_link_libraries(pico_hid_firmware
    pico_stdlib
    tinyusb_device
    tinyusb_board
    hardware_uart
    hardware_irq
)

pico_add_extra_outputs(pico_hid_firmware)
