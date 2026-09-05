# pico_hid_firmware 拟人化队列引擎集成设计规格

> **版本**: 1.0  
> **日期**: 2026-09-03  
> **状态**: 已批准，待实施  
> **关联**: MapleStory SDD 执行层集成

---

## 1. 概述

将 `pico_hid_firmware` 从「同步帧协议哑执行器」升级为「智能协处理器」，核心变更：

1. **非阻塞队列执行引擎**：Pico 内部维护 128 槽环形缓冲区，主机下发粗粒度宏序列，Pico 自主消费并拟人化执行
2. **重设计异步帧协议**：替换现有 `#CMD:ARGS|CHECKSUM\n`，采用二进制帧 + 双向异步事件
3. **Profile 系统**：8 个可配置拟人化参数槽位，Flash 持久化，运行时热切换
4. **高斯 RNG**：XORSHIFT PRNG + LUT 查表，纯整数运算，~1μs/样本
5. **Bézier 鼠标轨迹**：二次 Bézier + 缓入缓出时间函数 + 过冲修正

**核心动机**：SDD 要求"硬件拟态"——时序随机性必须由 Pico 固件内部生成，而非主机计算后下发，否则 Pico 只是 USB 串口转换器，失去硬件防封价值。

---

## 2. 系统架构

```
┌──────────────────── pico_hid_firmware ────────────────────────┐
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              UART RX 中断（保持现有设计）              │    │
│  │   帧解析: SOH(0xAA55) + LEN + CMD + PAYLOAD + CRC16  │    │
│  └──────────────────────┬───────────────────────────────┘    │
│                         │ 解析后的指令                        │
│                         ▼                                    │
│  ┌──────────────────────────────────────────────────────┐    │
│  │              命令分发器 (cmd_dispatch)                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │    │
│  │  │ 系统指令  │  │ 原始指令  │  │ 队列/Profile 指令  │   │    │
│  │  │ PING/VER │  │ 直接执行  │  │ QUEUE_PUSH/START  │   │    │
│  │  └──────────┘  └────┬─────┘  └─────────┬─────────┘   │    │
│  └─────────────────────┼──────────────────┼─────────────┘    │
│                        │                  │                  │
│                        ▼                  ▼                  │
│  ┌─────────────┐  ┌──────────────────────────────────────┐  │
│  │ USB HID     │  │         队列执行引擎                   │  │
│  │ 报告发送     │◄─┤  环形缓冲(128) + 非阻塞状态机         │  │
│  │ (mouse/kb)  │  │  ┌──────────┐  ┌─────────────────┐   │  │
│  └─────────────┘  │  │高斯 RNG  │  │ Bézier 鼠标引擎  │   │  │
│                   │  │(LUT 查表) │  │ (缓入缓出+过冲)  │   │  │
│  ┌─────────────┐  │  └──────────┘  └─────────────────┘   │  │
│  │ Flash 存储   │  │  ┌──────────┐  ┌─────────────────┐   │  │
│  │ 8 Profile   │  │  │ Markov   │  │ 事件发射器       │   │  │
│  │ (192B)      │◄─┤  │ 微停顿    │  │ (UART → 主机)   │   │  │
│  └─────────────┘  │  └──────────┘  └─────────────────┘   │  │
│                   └──────────────────────────────────────┘  │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐    │
│  │    主循环: tud_task() → queue_tick() → LED update     │    │
│  │    (非阻塞，每轮 < 20μs)                              │    │
│  └──────────────────────────────────────────────────────┘    │
└───────────────────────────────────────────────────────────────┘
```

### 2.1 内存预算

| 模块 | RAM 占用 | 说明 |
|------|---------|------|
| 队列缓冲区 | 1,280 B | 128 × 10B/项 |
| Profile 存储（RAM 镜像） | 192 B | 8 × 24B/Profile |
| 执行上下文 | 20 B | exec_context_t |
| Bézier 状态 | 28 B | bezier_state_t |
| RNG 状态 | 4 B | xorshift32 state |
| UART 帧缓冲 | 64 B | 保持现有 |
| HID 报告 | 12 B | mouse + keyboard report |
| **合计** | **~1.6 KB** | / 264 KB SRAM (0.6%) |

Flash 占用（.rodata + .text 新增）：

| 模块 | Flash 占用 |
|------|-----------|
| 高斯 LUT | 256 B |
| Profile Flash 存储区 | 256 B（1 页，含 wear-leveling 预留） |
| 代码新增（状态机/协议/Bézier） | ~8 KB |

---

## 3. 帧协议规格

### 3.1 帧格式

```
┌──────┬──────┬──────┬──────────┬─────────────┬─────────┐
│ SOH1 │ SOH2 │ LEN  │ CMD      │ PAYLOAD     │ CRC16   │
│ 0xAA │ 0x55 │ 1B   │ 1B       │ 0~248B      │ 2B      │
└──────┴──────┴──────┴──────────┴─────────────┴─────────┘

最小帧: 5 字节（LEN=0，无 payload）
最大帧: 253 字节（LEN=248）
LEN = payload 字节数（不含 SOH/LEN/CMD/CRC16）
CRC16 = CRC-16/MODBUS，覆盖 LEN + CMD + PAYLOAD（共 LEN+3 字节）
```

### 3.2 方向约定

| CMD 范围 | 方向 | 用途 |
|----------|------|------|
| 0x00-0x7F | 主机 → Pico | 请求/指令 |
| 0x80-0xEF | Pico → 主机 | ACK 响应（0x80 + 原 CMD） |
| 0xF0-0xFF | Pico → 主机 | 异步事件 |

### 3.3 完整指令表

#### 系统类 (0x00-0x0F)

| CMD | 名称 | Payload (请求) | Payload (响应) | 说明 |
|-----|------|---------------|---------------|------|
| 0x01 | PING | 无 | 无 | 心跳 |
| 0x02 | RESET | 无 | 无 | 软重置 |
| 0x03 | GET_VERSION | 无 | major(1B), minor(1B), patch(1B) | 固件版本 |

#### 原始指令类 (0x10-0x2F)

绕过拟人化，直接执行。用于调试和精确控制。

| CMD | 名称 | Payload | 说明 |
|-----|------|---------|------|
| 0x10 | KEY_DOWN | keycode(1B) | 按下按键 |
| 0x11 | KEY_UP | keycode(1B) | 松开按键 |
| 0x12 | KEY_TAP | keycode(1B), hold_ms(2B) | 按下 → sleep → 松开 |
| 0x20 | MOUSE_ABS | x(2B, signed), y(2B, signed) | 绝对坐标移动 |
| 0x21 | MOUSE_REL | dx(2B, signed), dy(2B, signed) | 相对位移 |
| 0x22 | MOUSE_CLICK | btn(1B), hold_ms(2B) | 点击（1=左, 2=右, 3=中） |
| 0x23 | MOUSE_SCROLL | delta(2B, signed) | 滚轮 |

#### 队列/宏类 (0x30-0x3F)

**方案 B 核心**。主机批量推入指令序列，Pico 内部拟人化执行。

| CMD | 名称 | Payload (请求) | Payload (响应) | 说明 |
|-----|------|---------------|---------------|------|
| 0x30 | QUEUE_PUSH | items[] (见 3.4) | free_after(2B), depth_after(2B), written(1B) | 推入队列项。ACK 携带写入后剩余空间/深度/实际写入数（见 3.6 流控） |
| 0x31 | QUEUE_START | profile_id(1B) | 无 | 用指定 Profile 开始执行 |
| 0x32 | QUEUE_PAUSE | 无 | 无 | 暂停执行 |
| 0x33 | QUEUE_RESUME | 无 | 无 | 恢复执行 |
| 0x34 | QUEUE_CLEAR | 无 | 无 | 清空队列 |
| 0x35 | QUEUE_STATUS | 无 | depth(2B), state(1B), free(2B) | 查询队列状态 |

#### Profile 类 (0x40-0x4F)

| CMD | 名称 | Payload (请求) | Payload (响应) | 说明 |
|-----|------|---------------|---------------|------|
| 0x40 | PROFILE_SET | profile_id(1B) | 无 | 切换到指定 Profile |
| 0x41 | PROFILE_GET | profile_id(1B) | params(24B) | 读取 Profile 参数 |
| 0x42 | PROFILE_WRITE | profile_id(1B), params(24B) | 无 | 写入 RAM 缓冲 |
| 0x43 | PROFILE_SAVE | save_mask(1B) | saved_mask(1B) | 落盘到 Flash |
| 0x44 | PROFILE_LOAD | load_mask(1B) | loaded_mask(1B) | 从 Flash 加载到 RAM |

#### 异步事件 (0xF0-0xFF)

Pico 主动上报，无需主机请求。

| CMD | 名称 | Payload | 触发条件 |
|-----|------|---------|---------|
| 0xF0 | EVT_QUEUE_EMPTY | 无 | 队列消费完毕 |
| 0xF1 | EVT_QUEUE_LOW | remaining(2B) | 队列深度 ≤ low_watermark |
| 0xF5 | EVT_QUEUE_HIGH | free(2B) | 队列深度 ≥ high_watermark（默认 112）。首次越过阈值时触发，后续 PUSH 不再重复触发直到 depth 回落再越过 |
| 0xF2 | EVT_ERROR | err_code(1B), detail(NB) | 内部错误 |
| 0xF3 | EVT_MOUNT | mounted(1B) | USB 挂载状态变化 |
| 0xF4 | EVT_READY | 无 | 固件启动完成 |

### 3.4 QUEUE_PUSH Payload 格式

每条队列项 = `type(1B) + action(1B) + params(NB)`，变长编码，单帧可包含多项。

| type | 名称 | params 格式 | 说明 |
|------|------|------------|------|
| 0x01 | KEY_TAP | keycode(1B), hold_mu(1B), hold_sigma(1B) | 拟人化按键。mu/sigma=0 时用 Profile 默认值 |
| 0x02 | KEY_HOLD | keycode(1B), hold_ms(2B) | 固定时长按键（不拟人化） |
| 0x03 | MOUSE_TO | x(2B), y(2B), speed(1B), bezier(1B) | 鼠标移动到绝对坐标。speed=0 用 Profile 默认。bezier: 0=直线, 1=Bézier |
| 0x04 | MOUSE_REL | dx(2B), dy(2B), speed(1B) | 相对位移 |
| 0x05 | CLICK | btn(1B) | 鼠标点击 |
| 0x06 | WAIT | base_ms(2B), jitter_pct(1B) | 等待。实际时长 = base_ms ± jitter_pct% |
| 0x07 | MARKOV_PAUSE | probability(1B), min_ms(1B), max_ms(1B) | 显式条件停顿。probability 单位 = 0.5%（即值 4 = 2%）。与 Profile 自动 Markov 独立——此项由主机主动插入 |
| 0x08 | LOOP | count(1B), back_offset(2B) | 循环。从当前位置回退 back_offset 项，重复 count 次。back_offset 不得超过当前队列深度（队列引擎会 clamp 到合法范围） |

**单帧最多容纳约 20 条 KEY_TAP 项**（每条约 10 字节，payload 上限 248 字节）。大批量需分多帧 PUSH。

### 3.6 队列流控机制

队列流控采用**双层防护**：PUSH 同步响应 + 高水位异步事件。

#### 第一层：PUSH 同步响应携带队列状态

每次 QUEUE_PUSH 的 ACK 扩展为携带：
- `free_after(2B)`：写入后剩余可用空间
- `depth_after(2B)`：写入后当前队列深度
- `written(1B)`：实际写入的队列项数

主机根据 `free_after` 自行决策推送节奏：
- free > 32 → 继续正常推送
- free ≤ 32 → 减缓推送速度
- free == 0 → 停止推送，等待 EVT_QUEUE_LOW 事件再继续

#### 第二层：高水位异步事件

EVT_QUEUE_HIGH (0xF5) 在队列深度首次越过 high_watermark（默认 112，即 free ≤ 16）时触发。

与 EVT_QUEUE_LOW 的对应关系：
- EVT_QUEUE_LOW：水箱快空了（depth ≤ 16），请补货
- EVT_QUEUE_HIGH：水箱快满了（depth ≥ 112），请暂停

防抖机制：EVT_QUEUE_HIGH 仅在深度从 <112 首次越过到 ≥112 时触发一次，后续 PUSH 不再重复触发，直到 depth 回落到 <112 后再次越过。

#### 第三层：溢出保护

```c
cmd_result_t handle_queue_push(uint8_t* items, uint8_t count) {
    uint8_t free = QUEUE_CAPACITY - queue_depth();
    
    if (free == 0) {
        emit_event(EVT_QUEUE_HIGH, &free, 2);
        return ERR_QUEUE_FULL;  // NACK: -QFULL
    }
    
    uint8_t to_write = (count > free) ? free : count;
    // 写入 to_write 项
    for (uint8_t i = 0; i < to_write; i++) {
        queue.items[queue.head] = items[i];
        queue.head = (queue.head + 1) % QUEUE_CAPACITY;
    }
    
    // 如果发生了截断
    if (count > to_write) {
        emit_event(EVT_QUEUE_HIGH, &free, 2);
    }
    
    // 检查高水位触发
    uint8_t depth_after = queue_depth();
    if (depth_after >= queue.high_watermark && !queue.high_watermark_triggered) {
        emit_event(EVT_QUEUE_HIGH, &(uint16_t){QUEUE_CAPACITY - depth_after}, 2);
        queue.high_watermark_triggered = true;
    } else if (depth_after < queue.high_watermark) {
        queue.high_watermark_triggered = false;  // 重置，允许下次触发
    }
    
    uint16_t free_after = QUEUE_CAPACITY - depth_after;
    return ACK_WITH_DATA(free_after, depth_after, to_write);
}
```

#### 主机侧流控示例

```python
def feed_queue(serial, macro_items):
    idx = 0
    while idx < len(macro_items):
        batch = pack_items(macro_items[idx:idx+20])
        resp = send_cmd(serial, CMD_QUEUE_PUSH, batch)
        
        free_after = resp.payload[0:2]
        depth_after = resp.payload[2:4]
        written = resp.payload[4]
        
        if free_after == 0:
            # 队列满，等待低水位事件
            wait_for_event(serial, EVT_QUEUE_LOW)
            continue
        
        idx += written
        
        if free_after <= 32:
            # 接近满，主动减速
            sleep_ms(100)
```

### 3.5 CRC-16/MODBUS 实现

```c
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
```

覆盖范围：从 LEN 字节开始到 PAYLOAD 末尾（不含 SOH，不含 CRC 本身）。

---

## 4. Profile 系统

### 4.1 参数结构（14 字段，24 字节/Profile）

```c
typedef struct __attribute__((packed)) {
    // 键盘拟人化
    uint16_t key_hold_mu;          // 按键时长均值 (ms), 典型 60-120
    uint16_t key_hold_sigma;       // 按键时长标准差 (ms), 典型 10-25
    uint16_t key_hold_min;         // 截断下界 (ms)
    uint16_t key_hold_max;         // 截断上界 (ms)
    uint16_t key_interval_mu;      // 连续按键间隔均值 (ms), 典型 200-500
    uint16_t key_interval_sigma;   // 间隔标准差 (ms)

    // Markov 微停顿
    uint8_t  markov_prob;          // 触发概率 (0-100, 单位 %)
    uint16_t markov_min_ms;        // 微停顿最短时长 (ms)
    uint16_t markov_max_ms;        // 微停顿最长时长 (ms)

    // 鼠标拟人化
    uint8_t  mouse_curve;          // 0=直线, 1=Bézier, 2=Bézier+微抖
    uint8_t  mouse_speed;          // 基础速度 (1-10)
    uint16_t mouse_overshoot_mu;   // 过冲均值 (像素), 典型 3-8
    uint8_t  mouse_overshoot_prob; // 过冲概率 (0-100)

    // 节奏特征
    uint8_t  action_rhythm;        // 0=机械(固定间隔), 1=有节奏波动(低频正弦调制间隔), 2=完全随机(每项独立高斯)
    uint16_t global_pace;          // 全局节奏系数 (50=正常, <50=慢, >50=快)。作用于 key_interval_mu 的乘数 (pace/50)
} profile_t;  // 24 bytes
```

### 4.2 存储策略

```
┌─────────────────────────────────────────┐
│              RAM 镜像                    │
│  profiles[0..7]  ← 运行时从此读取       │
│       ↑                                  │
│       │ PROFILE_LOAD / PROFILE_WRITE     │
│       │                                  │
│              Flash 持久化                 │
│  flash_profiles[0..7]  ← 断电不丢失     │
│       ↑                                  │
│       │ PROFILE_SAVE                     │
└─────────────────────────────────────────┘

- 启动时：Flash → RAM（自动加载）
- 运行中：只读写 RAM
- 需要持久化时：主机发 PROFILE_SAVE，RAM → Flash
```

### 4.3 Flash 布局

```
Flash 保留区域（最后 4KB 的一个 Sector）:
┌──────────┬───────────┬──────────┬──────────┐
│ MAGIC    │ profiles  │ checksum │ reserved │
│ 4B       │ 192B      │ 2B       │ ~3.8KB   │
│ 0x504943 │           │ CRC16    │ (扩展)   │
└──────────┴───────────┴──────────┴──────────┘

MAGIC = 0x50494348 ("PICH") — 用于判断是否已初始化
checksum = CRC-16/MODBUS(profiles[0..7])
启动时校验 MAGIC + checksum，失败则加载默认 Profile
```

### 4.4 默认 Profile（出厂预设）

对应 SDD 的刷怪场景参数：

```c
static const profile_t default_profiles[8] = {
    [0] = {  // 刷怪（高频技能循环）
        .key_hold_mu = 60, .key_hold_sigma = 12,
        .key_hold_min = 30, .key_hold_max = 120,
        .key_interval_mu = 250, .key_interval_sigma = 45,
        .markov_prob = 1, .markov_min_ms = 500, .markov_max_ms = 1500,
        .mouse_curve = 1, .mouse_speed = 8,
        .mouse_overshoot_mu = 4, .mouse_overshoot_prob = 15,
        .action_rhythm = 2, .global_pace = 65,
    },
    [1] = {  // 巡逻（走路为主）
        .key_hold_mu = 120, .key_hold_sigma = 20,
        .key_hold_min = 60, .key_hold_max = 200,
        .key_interval_mu = 400, .key_interval_sigma = 70,
        .markov_prob = 5, .markov_min_ms = 800, .markov_max_ms = 2200,
        .mouse_curve = 2, .mouse_speed = 5,
        .mouse_overshoot_mu = 6, .mouse_overshoot_prob = 25,
        .action_rhythm = 1, .global_pace = 40,
    },
    [2] = {  // 拾取（定点按键）
        .key_hold_mu = 90, .key_hold_sigma = 15,
        .key_hold_min = 40, .key_hold_max = 160,
        .key_interval_mu = 300, .key_interval_sigma = 50,
        .markov_prob = 3, .markov_min_ms = 600, .markov_max_ms = 1800,
        .mouse_curve = 1, .mouse_speed = 6,
        .mouse_overshoot_mu = 3, .mouse_overshoot_prob = 10,
        .action_rhythm = 1, .global_pace = 50,
    },
    [3] = {  // 精英/Rune（紧张状态）
        .key_hold_mu = 50, .key_hold_sigma = 10,
        .key_hold_min = 25, .key_hold_max = 100,
        .key_interval_mu = 180, .key_interval_sigma = 35,
        .markov_prob = 0, .markov_min_ms = 0, .markov_max_ms = 0,
        .mouse_curve = 0, .mouse_speed = 9,
        .mouse_overshoot_mu = 2, .mouse_overshoot_prob = 5,
        .action_rhythm = 0, .global_pace = 80,
    },
    [4..7] = { 0 }  // 空槽位，由主机自定义
};
```

---

## 5. 队列执行引擎

### 5.1 数据结构

```c
#define QUEUE_CAPACITY 128

typedef struct {
    uint8_t  type;        // 队列项类型 (0x01-0x08)
    uint8_t  action;      // 子动作 (keycode / btn / etc.)
    uint16_t param_a;     // 参数1
    uint16_t param_b;     // 参数2
    uint8_t  flags;       // 位域：bezier使能 等
    uint8_t  override_a;  // Profile参数逐条覆盖
    uint8_t  override_b;  // 同上
} queue_item_t;  // 10 bytes

typedef enum {
    QUEUE_IDLE = 0,
    QUEUE_RUNNING,
    QUEUE_PAUSED,
} queue_state_t;

typedef struct {
    queue_item_t items[QUEUE_CAPACITY];
    volatile uint8_t head;          // 写入位置
    volatile uint8_t tail;          // 读取位置
    volatile queue_state_t state;
    uint8_t active_profile_id;
    uint8_t low_watermark;          // 默认 16（depth ≤ 16 时触发 EVT_QUEUE_LOW）
    uint8_t high_watermark;         // 默认 112（depth ≥ 112 时触发 EVT_QUEUE_HIGH）
    bool high_watermark_triggered;  // 防抖标记：已触发过则不重复发送 EVT_QUEUE_HIGH
} exec_queue_t;
```

### 5.2 状态机

```
   ┌────────┐  QUEUE_START  ┌─────────┐
   |  IDLE  |──────────────>| RUNNING |
   └────────┘               └────┬────┘
        ▲                        │
        │ queue empty        PAUSE
        │                        │
        │                   ┌────v────┐
        │                   | PAUSED  |──── RESUME ────┐
        │                   └─────────┘                │
        │                                              │
        └────── QUEUE_CLEAR (from any state) ──────────┘
```

### 5.3 非阻塞执行步骤

每种队列项类型拆分为多个步骤，每步在主循环中检查时间条件，不阻塞：

**KEY_TAP 步骤**:
```
STEP_PRESS → STEP_WAIT_HOLD → STEP_RELEASE → STEP_WAIT_INTERVAL → STEP_DONE
                                                              ↘ (Markov 触发)
                                                          STEP_MARKOV_PAUSE
```

**MOUSE_TO (Bézier) 步骤**:
```
BEZIER_INIT → BEZIER_STEP (循环 N 次) → [OVERSHOOT_CORRECT] → STEP_DONE
```

**WAIT 步骤**:
```
STEP_WAIT_INIT → STEP_WAITING → STEP_DONE
```

**MARKOV_PAUSE 步骤**:
```
STEP_MARKOV_INIT → STEP_MARKOV_WAIT → STEP_DONE
```

### 5.4 Markov 微停顿：两层独立机制

队列引擎包含**两层独立的 Markov 停顿机制**，互不干扰：

1. **Profile 自动 Markov**：每次 `STEP_DONE`（一条队列项消费完毕）后，引擎按 `profile.markov_prob` 概率自动插入微停顿。这是"底层节拍器"，模拟人类的随机发呆。
2. **队列项 MARKOV_PAUSE (type=0x07)**：主机在队列序列中主动插入的条件停顿项。执行到该项时，按自身 probability/min_ms/max_ms 参数判定是否停顿。这是"战术停顿"，用于特定场景（如换图、等技能 CD）。

两者独立叠加。例如 Profile markov_prob=2% 且队列中包含一项 MARKOV_PAUSE(prob=50%)，两者各自独立掷骰，可能同时触发（停顿叠加）。

### 5.5 主循环

```c
while (1) {
    tud_task();       // USB 栈服务
    queue_tick();     // 队列引擎（非阻塞，< 20μs）
    led_update();     // LED 状态更新
}
```

---

## 6. 高斯 RNG

### 6.1 PRNG：XORSHIFT-32

```c
static uint32_t rng_state;  // 种子: time_us_32()

static inline uint32_t xorshift32(void) {
    rng_state ^= rng_state << 13;
    rng_state ^= rng_state >> 17;
    rng_state ^= rng_state << 5;
    return rng_state;
}

static inline uint32_t rng_uniform(uint32_t max) {
    return (uint64_t)xorshift32() * max >> 32;
}
```

### 6.2 高斯 LUT

```c
#define GAUSS_LUT_SIZE 256

// 预计算：标准正态分布 N(0,1) 的 PPF 采样
// 离线生成: ppf(linspace(0.001, 0.999, 256)) → 缩放到 [-128, 127]
static const int8_t gauss_lut[GAUSS_LUT_SIZE] = { /* ... */ };

static int16_t gaussian(int16_t mu, int16_t sigma, int16_t min_val, int16_t max_val) {
    uint8_t idx = (uint8_t)(xorshift32() >> 24);
    int16_t sample = gauss_lut[idx];
    int16_t result = mu + (int16_t)((int32_t)sample * sigma / 128);
    if (result < min_val) result = min_val;
    if (result > max_val) result = max_val;
    return result;
}

static int16_t rng_range(int16_t min_val, int16_t max_val) {
    return min_val + (int16_t)rng_uniform(max_val - min_val + 1);
}

static bool rng_chance(uint8_t pct) {
    return rng_uniform(100) < pct;
}
```

### 6.3 精度与性能

| 指标 | 值 |
|------|---|
| 单次采样耗时 | ~1μs（无 FPU，纯整数） |
| 分布精度 | LUT 256 级，分辨率 ~0.004σ |
| 在 σ=15ms 下分辨率 | ~0.06ms（远超人感知阈值） |
| RAM 占用 | 0（LUT 在 Flash .rodata） |
| Flash 占用 | 256 B |

---

## 7. Bézier 鼠标轨迹

### 7.1 数学模型

**二次 Bézier 曲线**:
```
B(t) = (1-t)²·P0 + 2(1-t)t·P1 + t²·P2
t ∈ [0, 1]
```

- P0 = 当前光标位置
- P2 = 目标位置
- P1 = 中点 + 垂直方向随机偏移（±3-8px）

**缓入缓出时间函数（Hermite 插值）**:
```
f(t) = 3t² - 2t³
```

用整数运算实现，t 归一化到 [0, 1000]。

### 7.2 状态结构

```c
#define BEZIER_STEPS_MAX  40
#define BEZIER_STEP_MS    8   // ~120Hz

typedef struct {
    int16_t p0_x, p0_y;
    int16_t p1_x, p1_y;
    int16_t p2_x, p2_y;
    int16_t overshoot_x, overshoot_y;
    uint8_t total_steps;
    uint8_t current_step;
    int16_t last_x, last_y;
} bezier_state_t;
```

### 7.3 执行流程

1. **BEZIER_INIT**：计算控制点、步数、过冲量
2. **BEZIER_STEP**（循环）：每 8ms 执行一次
   - 计算 t = ease_in_out(step / total_steps)
   - 求 B(t) 坐标
   - 发送增量 dx/dy（通过 send_relative_move）
3. **OVERSHOOT_CORRECT**（可选）：过冲后 15-60ms 回正

### 7.4 效果示例

200px 水平移动，25 步：
```
步数:  0    5    10   15   20   25
速度:  慢→快→→→→→→→→→→→→→快→慢
位置:  |--加速--|--匀速--|--减速--|→(过冲)←(回正)
```

---

## 8. 文件结构规划

```
src/
├── main.c              # 主循环，初始化
├── usb_descriptors.c   # USB 描述符（保持现有）
├── tusb_config.h       # TinyUSB 配置（保持现有）
├── protocol.h          # 帧格式定义，CMD 枚举
├── protocol.c          # 帧解析，CRC，命令分发
├── queue.h             # 队列数据结构
├── queue.c             # 队列引擎，状态机，queue_tick()
├── profile.h           # Profile 结构定义
├── profile.c           # Profile RAM/Flash 管理
├── rng.h               # RNG 接口
├── rng.c               # XORSHIFT + 高斯 LUT
├── bezier.h            # Bézier 状态
├── bezier.c            # Bézier 轨迹计算与执行
└── event.h             # 异步事件发射器接口
```

CMakeLists.txt 需要新增所有 .c 文件和 `hardware_flash` 链接。

---

## 9. 向后兼容性

**完全不兼容**。这是一次破坏性升级：
- 帧格式从 ASCII 文本变为二进制
- 校验从简单加和变为 CRC-16
- 主机侧 Python 代码需要完全重写协议层

**迁移策略**：
- 保留一个 `legacy` 分支存放当前固件
- 新固件使用新 Git tag（v2.0.0）
- 主机侧同步开发 Python 协议层

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| 状态机复杂度导致调试困难 | 高 | 每个步骤转换添加调试计数器；EVT_ERROR 上报详细状态 |
| Flash 写入失败导致 Profile 丢失 | 中 | 启动时校验 checksum，失败回退默认 Profile |
| 高斯 LUT 分布不够自然 | 低 | 预留接口切换到 Box-Muller 实时计算 |
| 队列溢出（主机推入速度 > 消费速度） | 中 | QUEUE_PUSH 返回当前 depth，主机自行流控 |
| Bézier 长距离移动时 int8_t 增量溢出 | 低 | send_relative_move 已有 auto-split 逻辑 |

---

## 11. 验收标准

1. **协议**：主机发送二进制帧，Pico 正确解析并响应 ACK；异步事件正确上报
2. **队列**：128 项满队列 PUSH → START → 全部正确消费 → EVT_QUEUE_EMPTY 触发
3. **拟人化**：连续 1000 次 KEY_TAP 的 hold_time 符合 N(μ,σ) 分布（χ² 检验 p > 0.05）
4. **Bézier**：鼠标移动轨迹有可见弯曲（非直线），到达目标点误差 ≤ 1px
5. **Profile**：8 个槽位可独立写入/读取/切换；SAVE 后断电重启参数不丢失
6. **性能**：主循环每轮 < 20μs（队列运行时）
7. **稳定性**：连续运行 24 小时无崩溃、无队列卡死
