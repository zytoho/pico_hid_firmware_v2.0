# Pico HID 拟人化队列引擎实施计划

**For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 pico_hid_firmware 从同步帧协议哑执行器升级为智能协处理器，支持非阻塞队列执行、Profile 拟人化配置、高斯 RNG、Bézier 鼠标轨迹和流控机制。

**Architecture:** 二进制帧协议（SOH 0xAA55 + CRC16）+ 128 槽环形队列 + 非阻塞状态机执行引擎 + 8 个可配置 Profile（Flash 持久化）+ XORSHIFT PRNG + 高斯 LUT + 二次 Bézier 鼠标轨迹。所有拟人化逻辑在 Pico 内部完成，主机仅下发粗粒度宏序列。

**Tech Stack:** C (C11), Pico SDK, TinyUSB, hardware_flash API, 无浮点运算（纯整数实现）

**Spec:** `docs/superpowers/specs/2026-09-03-pico-queue-engine-integration-design.md`

## 全局约束

- 主循环每轮 < 20μs（队列运行时）
- RAM 占用 ~1.6KB（队列 1.28KB + Profile 192B + 执行上下文 48B + 其他）
- Flash 占用 ~8.5KB（代码 + 高斯 LUT 256B + Profile 存储区）
- 纯整数运算，不使用浮点（RP2040 无 FPU）
- 协议不向后兼容（完全替换 ASCII 帧格式）
- 所有异步事件通过 UART 上报主机

## 文件结构

```
src/
├── main.c                 # 主循环、初始化
├── usb_descriptors.c      # USB 描述符（保持现有）
├── tusb_config.h          # TinyUSB 配置（保持现有）
├── protocol.h             # 帧格式定义、CMD 枚举、错误码
├── protocol.c             # 帧解析、CRC、命令分发
├── queue.h                # 队列数据结构、状态机定义
├── queue.c                # 队列引擎、queue_tick()、状态转换
├── profile.h              # Profile 结构定义、接口
├── profile.c              # Profile RAM 管理、Flash 持久化、默认配置
├── rng.h                  # RNG 接口
├── rng.c                  # XORSHIFT PRNG + 高斯 LUT
├── bezier.h               # Bézier 状态结构
├── bezier.c               # Bézier 轨迹计算与执行
└── hid.h                  # USB HID 报告发送接口（从 main.c 抽取）

CMakeLists.txt             # 新增所有 .c 文件 + hardware_flash 链接
```

---

## Task 1: 协议层（二进制帧解析 + CRC + 命令分发）

**Files:**
- Create: `src/protocol.h`
- Create: `src/protocol.c`
- Modify: `src/main.c:203-344` (替换 execute_command 为 cmd_dispatch)

**Interfaces:**
- Consumes: UART RX 字节流（已有中断接收）
- Produces: `void protocol_init()`, `void protocol_process_byte(uint8_t byte)`, `void protocol_send_response(uint8_t cmd, const uint8_t* payload, uint8_t len)`

**验证方法:** 通过串口发送构造的二进制帧，观察 ACK 响应和错误码

- [ ] **Step 1: 创建 protocol.h 定义帧格式和 CMD 枚举**

```c
#ifndef PROTOCOL_H
#define PROTOCOL_H

#include <stdint.h>
#include <stdbool.h>

// 帧格式
#define FRAME_SOH1          0xAA
#define FRAME_SOH2          0x55
#define FRAME_MAX_PAYLOAD   248
#define FRAME_MIN_LEN       5       // SOH1+SOH2+LEN+CMD+CRC16
#define FRAME_MAX_LEN       253     // 5 + 248

// 方向约定
#define CMD_DIR_HOST_TO_PICO    0x00
#define CMD_DIR_PICO_TO_HOST    0x80

// 系统类 CMD (0x00-0x0F)
#define CMD_PING            0x01
#define CMD_RESET           0x02
#define CMD_GET_VERSION     0x03

// 原始指令类 CMD (0x10-0x2F)
#define CMD_KEY_DOWN        0x10
#define CMD_KEY_UP          0x11
#define CMD_KEY_TAP         0x12
#define CMD_MOUSE_ABS       0x20
#define CMD_MOUSE_REL       0x21
#define CMD_MOUSE_CLICK     0x22
#define CMD_MOUSE_SCROLL    0x23

// 队列/宏类 CMD (0x30-0x3F)
#define CMD_QUEUE_PUSH      0x30
#define CMD_QUEUE_START     0x31
#define CMD_QUEUE_PAUSE     0x32
#define CMD_QUEUE_RESUME    0x33
#define CMD_QUEUE_CLEAR     0x34
#define CMD_QUEUE_STATUS    0x35

// Profile 类 CMD (0x40-0x4F)
#define CMD_PROFILE_SET     0x40
#define CMD_PROFILE_GET     0x41
#define CMD_PROFILE_WRITE   0x42
#define CMD_PROFILE_SAVE    0x43
#define CMD_PROFILE_LOAD    0x44

// 异步事件 CMD (0xF0-0xFF)
#define EVT_QUEUE_EMPTY     0xF0
#define EVT_QUEUE_LOW       0xF1
#define EVT_QUEUE_HIGH      0xF5
#define EVT_ERROR           0xF2
#define EVT_MOUNT           0xF3
#define EVT_READY           0xF4

// 错误码
#define ERR_NONE            0x00
#define ERR_BAD_CRC         0x01
#define ERR_BAD_CMD         0x02
#define ERR_BAD_PAYLOAD     0x03
#define ERR_QUEUE_FULL      0x04
#define ERR_PROFILE_INVALID 0x05

// 接口函数
void protocol_init(void);
void protocol_process_byte(uint8_t byte);
void protocol_send_response(uint8_t cmd, const uint8_t* payload, uint8_t len);
void protocol_send_event(uint8_t event_cmd, const uint8_t* payload, uint8_t len);

#endif // PROTOCOL_H
```

- [ ] **Step 2: 创建 protocol.c 实现帧解析和 CRC**

```c
#include "protocol.h"
#include "hardware/uart.h"
#include <string.h>

#define UART_ID uart0

// CRC-16/MODBUS
static uint16_t crc16_modbus(const uint8_t* data, uint16_t len) {
    uint16_t crc = 0xFFFF;
    for (uint16_t i = 0; i < len; i++) {
        crc ^= data[i];
        for (uint8_t j = 0; j < 8; j++) {
            crc = (crc >> 1) ^ (0xA001 * (crc & 1));
        }
    }
    return crc;
}

// 帧解析状态机
typedef enum {
    STATE_WAIT_SOH1,
    STATE_WAIT_SOH2,
    STATE_WAIT_LEN,
    STATE_WAIT_CMD,
    STATE_WAIT_PAYLOAD,
    STATE_WAIT_CRC1,
    STATE_WAIT_CRC2,
} parse_state_t;

static parse_state_t parse_state = STATE_WAIT_SOH1;
static uint8_t frame_buf[FRAME_MAX_PAYLOAD + 4]; // LEN + CMD + payload
static uint8_t frame_len = 0;
static uint8_t expected_len = 0;

void protocol_init(void) {
    parse_state = STATE_WAIT_SOH1;
}

// 命令分发（由 task 2+ 实现具体处理）
__attribute__((weak)) void cmd_dispatch(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    protocol_send_response(cmd | 0x80, NULL, 0); // 默认 ACK
}

void protocol_process_byte(uint8_t byte) {
    switch (parse_state) {
        case STATE_WAIT_SOH1:
            if (byte == FRAME_SOH1) parse_state = STATE_WAIT_SOH2;
            break;
            
        case STATE_WAIT_SOH2:
            if (byte == FRAME_SOH2) parse_state = STATE_WAIT_LEN;
            else parse_state = STATE_WAIT_SOH1;
            break;
            
        case STATE_WAIT_LEN:
            if (byte > FRAME_MAX_PAYLOAD) {
                parse_state = STATE_WAIT_SOH1; // 非法长度
            } else {
                frame_buf[0] = byte; // LEN
                expected_len = byte;
                parse_state = STATE_WAIT_CMD;
            }
            break;
            
        case STATE_WAIT_CMD:
            frame_buf[1] = byte; // CMD
            frame_len = 2;
            if (expected_len == 0) {
                parse_state = STATE_WAIT_CRC1;
            } else {
                parse_state = STATE_WAIT_PAYLOAD;
            }
            break;
            
        case STATE_WAIT_PAYLOAD:
            frame_buf[frame_len++] = byte;
            if (frame_len >= expected_len + 2) {
                parse_state = STATE_WAIT_CRC1;
            }
            break;
            
        case STATE_WAIT_CRC1:
            frame_buf[frame_len++] = byte; // CRC high
            parse_state = STATE_WAIT_CRC2;
            break;
            
        case STATE_WAIT_CRC2:
            frame_buf[frame_len++] = byte; // CRC low
            parse_state = STATE_WAIT_SOH1;
            
            // 校验 CRC
            uint16_t expected_crc = (frame_buf[frame_len - 2] << 8) | frame_buf[frame_len - 1];
            uint16_t actual_crc = crc16_modbus(frame_buf, frame_len - 2);
            
            if (expected_crc == actual_crc) {
                cmd_dispatch(frame_buf[1], &frame_buf[2], frame_buf[0]);
            } else {
                uint8_t err = ERR_BAD_CRC;
                protocol_send_response(0xF2, &err, 1); // EVT_ERROR
            }
            break;
    }
}

void protocol_send_response(uint8_t cmd, const uint8_t* payload, uint8_t len) {
    uint8_t frame[FRAME_MAX_LEN];
    frame[0] = FRAME_SOH1;
    frame[1] = FRAME_SOH2;
    frame[2] = len;
    frame[3] = cmd;
    
    if (len > 0 && payload != NULL) {
        memcpy(&frame[4], payload, len);
    }
    
    uint16_t crc = crc16_modbus(&frame[2], len + 2);
    frame[len + 4] = crc >> 8;
    frame[len + 5] = crc & 0xFF;
    
    uart_write_blocking(UART_ID, frame, len + 6);
}

void protocol_send_event(uint8_t event_cmd, const uint8_t* payload, uint8_t len) {
    protocol_send_response(event_cmd, payload, len);
}
```

- [ ] **Step 3: 修改 main.c UART 中断处理调用 protocol_process_byte**

替换 `on_uart_rx()` 中的 `execute_command()` 调用为 `protocol_process_byte(ch)`

- [ ] **Step 4: 修改 CMakeLists.txt 添加 protocol.c**

```cmake
add_executable(pico_hid_firmware
    src/main.c
    src/usb_descriptors.c
    src/protocol.c
)
```

- [ ] **Step 5: 构建并烧录测试**

构建项目，通过串口发送测试帧：
```
PING:  AA 55 00 01 [CRC16]
GET_VERSION: AA 55 00 03 [CRC16]
```

预期：收到 ACK 响应

- [ ] **Step 6: Commit**

```bash
git add src/protocol.h src/protocol.c src/main.c CMakeLists.txt
git commit -m "feat: implement binary frame protocol with CRC-16/MODBUS"
```

---

## Task 2: 队列数据结构 + 事件系统基础

**Files:**
- Create: `src/queue.h`
- Create: `src/queue.c`
- Modify: `src/protocol.c` (添加 cmd_dispatch 实现)

**Interfaces:**
- Consumes: protocol.h (CMD 定义)
- Produces: `void queue_init()`, `uint8_t queue_push(const queue_item_t* items, uint8_t count)`, `void queue_tick()`, `uint8_t queue_depth()`, `uint8_t queue_free()`

- [ ] **Step 1: 创建 queue.h 定义队列结构和接口**

[定义 queue_item_t、exec_queue_t、queue_state_t 和所有接口函数]

- [ ] **Step 2: 创建 queue.c 实现环形缓冲和基本操作**

实现 queue_init、queue_push、queue_depth、queue_free、queue_clear、queue_start/pause/resume

- [ ] **Step 3: 在 protocol.c 中实现 cmd_dispatch 的队列相关命令**

处理 CMD_QUEUE_PUSH/START/PAUSE/RESUME/CLEAR/STATUS

- [ ] **Step 4: 修改 CMakeLists.txt 添加 queue.c**

- [ ] **Step 5: 测试队列基本操作**

通过串口发送 QUEUE_PUSH + QUEUE_STATUS，验证 depth/free 正确返回

- [ ] **Step 6: Commit**

---

## Task 3: Profile 系统（RAM 管理 + 默认配置）

**Files:**
- Create: `src/profile.h`
- Create: `src/profile.c`

**Interfaces:**
- Consumes: queue.h (queue_set_profile)
- Produces: `void profile_init()`, `const profile_t* profile_get(uint8_t id)`, `void profile_set(uint8_t id)`, `uint8_t profile_write(uint8_t id, const profile_t* prof)`

- [ ] **Step 1: 创建 profile.h 定义 profile_t 结构和接口**

[定义 14 字段的 profile_t 结构、8 个 Profile 槽、接口函数]

- [ ] **Step 2: 创建 profile.c 实现 RAM 管理和默认配置**

实现 4 个默认 Profile（刷怪/巡逻/拾取/精英），RAM 读写逻辑

- [ ] **Step 3: 在 protocol.c 中实现 Profile 相关命令**

处理 CMD_PROFILE_SET/GET/WRITE（暂不实现 SAVE/LOAD，Flash 在 task 9 实现）

- [ ] **Step 4: 修改 CMakeLists.txt 添加 profile.c**

- [ ] **Step 5: 测试 Profile 切换**

发送 PROFILE_SET + PROFILE_GET，验证参数正确返回

- [ ] **Step 6: Commit**

---

## Task 4: RNG + 高斯采样

**Files:**
- Create: `src/rng.h`
- Create: `src/rng.c`

**Interfaces:**
- Consumes: 无
- Produces: `void rng_init()`, `uint32_t rng_uniform(uint32_t max)`, `int16_t rng_gaussian(int16_t mu, int16_t sigma, int16_t min_val, int16_t max_val)`

- [ ] **Step 1: 创建 rng.h 定义接口**

- [ ] **Step 2: 创建 rng.c 实现 XORSHIFT + 高斯 LUT**

实现 256 级高斯 LUT（预计算值），纯整数运算

- [ ] **Step 3: 修改 CMakeLists.txt 添加 rng.c**

- [ ] **Step 4: 测试 RNG 分布**

连续调用 rng_gaussian(100, 20, 50, 150) 1000 次，通过串口输出样本，验证分布符合 N(100,20) 且截断在 [50,150]

- [ ] **Step 5: Commit**

---

## Task 5: USB HID 适配（键盘/鼠标报告发送）

**Files:**
- Create: `src/hid.h`
- Modify: `src/main.c` (抽取现有 HID 发送逻辑到 hid.c)

**Interfaces:**
- Consumes: TinyUSB tud_hid_* API
- Produces: `void hid_key_press(uint8_t keycode)`, `void hid_key_release(uint8_t keycode)`, `void hid_mouse_move_rel(int16_t dx, int16_t dy)`, `void hid_mouse_click(uint8_t button)`

- [ ] **Step 1: 创建 hid.h 定义接口**

- [ ] **Step 2: 创建 hid.c 抽取 main.c 中的 HID 发送逻辑**

将现有的 flush_keyboard_report、flush_mouse_report、send_relative_move 等函数迁移到 hid.c

- [ ] **Step 3: 修改 main.c 调用 hid.h 接口**

- [ ] **Step 4: 测试原始指令**

发送 CMD_KEY_DOWN/CMD_KEY_UP，验证 USB HID 报告正确发送

- [ ] **Step 5: Commit**

---

## Task 6: 队列执行引擎（状态机 + KEY_TAP 实现）

**Files:**
- Modify: `src/queue.c` (实现 queue_tick 和状态机)

**Interfaces:**
- Consumes: profile.h, rng.h, hid.h
- Produces: `void queue_tick()` (非阻塞执行)

- [ ] **Step 1: 在 queue.c 中实现 queue_tick 框架**

定义执行步骤枚举（STEP_PRESS/WAIT_HOLD/RELEASE/WAIT_INTERVAL/DONE），实现状态机主循环

- [ ] **Step 2: 实现 KEY_TAP 执行逻辑**

在 STEP_PRESS 调用 hid_key_press，STEP_WAIT_HOLD 使用 rng_gaussian 计算 hold 时间，STEP_WAIT_INTERVAL 计算间隔时间

- [ ] **Step 3: 实现 Profile 自动 Markov 检查**

在 STEP_DONE 后，按 profile.markov_prob 概率插入微停顿

- [ ] **Step 4: 修改 main.c 主循环调用 queue_tick**

```c
while (1) {
    tud_task();
    queue_tick();
    led_update();
}
```

- [ ] **Step 5: 测试 KEY_TAP 执行**

发送 QUEUE_PUSH (KEY_TAP) + QUEUE_START，验证按键以拟人化节奏执行（hold 时间符合高斯分布）

- [ ] **Step 6: 测试队列状态机**

测试 QUEUE_PAUSE/RESUME/CLEAR，验证状态转换正确

- [ ] **Step 7: Commit**

---

## Task 7: Bézier 鼠标轨迹

**Files:**
- Create: `src/bezier.h`
- Create: `src/bezier.c`
- Modify: `src/queue.c` (在 queue_tick 中添加 MOUSE_TO 执行逻辑)

**Interfaces:**
- Consumes: hid.h, rng.h
- Produces: `void bezier_init(int16_t x0, int16_t y0, int16_t x2, int16_t y2, uint8_t speed)`, `bool bezier_tick()` (返回 true 表示完成)

- [ ] **Step 1: 创建 bezier.h 定义接口**

- [ ] **Step 2: 创建 bezier.c 实现二次 Bézier 曲线计算**

实现控制点生成（中点 + 随机偏移）、缓入缓出时间函数、步进式轨迹执行

- [ ] **Step 3: 在 queue.c 中添加 MOUSE_TO 执行逻辑**

在 queue_tick 中处理 type=0x03 的 MOUSE_TO 项，调用 bezier 接口

- [ ] **Step 4: 修改 CMakeLists.txt 添加 bezier.c**

- [ ] **Step 5: 测试 Bézier 轨迹**

发送 QUEUE_PUSH (MOUSE_TO)，验证鼠标沿曲线移动（非直线）

- [ ] **Step 6: Commit**

---

## Task 8: 流控机制（高低水位事件）

**Files:**
- Modify: `src/queue.c` (添加 EVT_QUEUE_LOW/HIGH 触发逻辑)

**Interfaces:**
- Consumes: protocol.h (EVT_QUEUE_LOW/HIGH)
- Produces: 自动触发事件

- [ ] **Step 1: 在 queue_push 中添加高水位检查**

当 depth >= high_watermark 且未触发过时，发送 EVT_QUEUE_HIGH

- [ ] **Step 2: 在 queue_tick 中添加低水位检查**

当 depth <= low_watermark 时，发送 EVT_QUEUE_LOW

- [ ] **Step 3: 测试流控事件**

快速 PUSH 填满队列，验证 EVT_QUEUE_HIGH 触发；消费队列，验证 EVT_QUEUE_LOW 触发

- [ ] **Step 4: Commit**

---

## Task 9: Flash 持久化（Profile SAVE/LOAD）

**Files:**
- Modify: `src/profile.c` (添加 Flash 读写逻辑)

**Interfaces:**
- Consumes: hardware_flash API
- Produces: `void profile_save(uint8_t mask)`, `void profile_load(uint8_t mask)`

- [ ] **Step 1: 在 profile.c 中实现 Flash 读写**

使用 hardware_flash API 读写最后 4KB 扇区，实现 MAGIC + checksum 校验

- [ ] **Step 2: 在 protocol.c 中实现 PROFILE_SAVE/LOAD 命令**

- [ ] **Step 3: 修改 profile_init 启动时自动 LOAD**

- [ ] **Step 4: 测试 Flash 持久化**

PROFILE_WRITE + PROFILE_SAVE，断电重启后 PROFILE_GET 验证参数未丢失

- [ ] **Step 5: Commit**

---

## Task 10: 集成测试 + 主循环优化

**Files:**
- Modify: `src/main.c` (优化主循环性能)

- [ ] **Step 1: 性能测试**

使用 GPIO 翻转测量 queue_tick 执行时间，验证 < 20μs

- [ ] **Step 2: 长时间稳定性测试**

连续运行 24 小时，验证无崩溃、无队列卡死

- [ ] **Step 3: 最终集成测试**

完整流程：PROFILE_WRITE → QUEUE_PUSH (混合 KEY_TAP + MOUSE_TO) → QUEUE_START → 验证拟人化执行 + 事件上报

- [ ] **Step 4: Commit**

```bash
git tag v2.0.0
git push origin v2.0.0
```
