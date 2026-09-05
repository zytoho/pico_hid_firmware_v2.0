# 开发指南

本文档提供系统架构说明和开发流程指导。

## 目录

1. [系统架构](#系统架构)
2. [硬件架构](#硬件架构)
3. [软件架构](#软件架构)
4. [开发环境搭建](#开发环境搭建)
5. [固件开发](#固件开发)
6. [Python 开发](#python-开发)
7. [测试指南](#测试指南)
8. [性能优化](#性能优化)

---

## 系统架构

### 总体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     MacBook Pro (控制端)                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                  Python 应用层                         │  │
│  │                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────┐ │  │
│  │  │ Vision       │  │ Agent        │  │ Monitor    │ │  │
│  │  │ Pipeline     │  │ (Macro)      │  │            │ │  │
│  │  └──────┬───────┘  └──────┬───────┘  └────────────┘ │  │
│  │         │                  │                          │  │
│  │  ┌──────▼──────────────────▼──────────────────────┐  │  │
│  │  │           HumanMotionEngine (微观)              │  │  │
│  │  │  - 贝塞尔曲线路径生成                            │  │  │
│  │  │  - 帧协议封装                                    │  │  │
│  │  │  - 校验和计算                                    │  │  │
│  │  └──────────────────┬─────────────────────────────┘  │  │
│  │                      │                                 │  │
│  └──────────────────────┼─────────────────────────────────┘  │
│                         │ Serial (115200 baud)               │
└─────────────────────────┼────────────────────────────────────┘
                          │ USB-to-TTL
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Raspberry Pi Pico (执行端)                      │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │                    固件层                              │  │
│  │                                                        │  │
│  │  - UART 中断接收                                       │  │
│  │  - 帧协议解析                                          │  │
│  │  - HID 报告生成                                        │  │
│  │  - TinyUSB 驱动                                        │  │
│  └──────────────────┬─────────────────────────────────────┘  │
│                      │ USB HID                               │
└──────────────────────┼───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Windows Host (目标端)                         │
│                                                              │
│  - 识别为物理 USB HID 设备                                   │
│  - 无法区分软件/硬件鼠标                                     │
│  - 抗驱动级检测                                              │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
1. 视觉检测
   VisionPipeline.detect_target()
   → 目标坐标 (x, y)

2. 路径规划
   HumanMotionEngine.move_to(x, y)
   → 生成贝塞尔曲线路径
   → 拆分为多个中间点

3. 指令发送
   对每个中间点:
   → 封装为帧协议 #A:x,y|XX\n
   → 通过串口发送
   → 等待 ACK 响应

4. 硬件执行
   Pico 接收帧
   → 解析命令
   → 生成 HID 报告
   → 通过 USB 发送
   → Windows 执行鼠标移动

5. 反馈确认
   Pico 发送 ACK/NACK
   → Python 接收响应
   → 更新统计信息
```

---

## 硬件架构

### 硬件清单

| 组件 | 型号 | 用途 | 参考价格 |
|------|------|------|----------|
| 主控电脑 | MacBook Pro | 运行 Python 控制程序 | - |
| 微控制器 | Raspberry Pi Pico | 执行 HID 操作 | ~$4 |
| USB 转串口 | CH340/CP2102 | MacBook 与 Pico 通信 | ~$2 |
| USB 线 | Micro USB | Pico 与 Windows 连接 | ~$1 |
| 杜邦线 | 母对母 | 连接 TTL 与 Pico | ~$1 |

### 接线图

```
MacBook Pro                USB-to-TTL              Raspberry Pi Pico
┌──────────┐              ┌──────────┐             ┌──────────────┐
│          │              │          │             │              │
│  USB-A ──┼──────────────┼─> USB-A  │             │              │
│          │              │          │             │              │
│          │   TX ────────┼──────────┼─────────────┼─> GP1 (RX)   │
│          │   RX ────────┼──────────┼─────────────┼─> GP0 (TX)   │
│          │   GND ───────┼──────────┼─────────────┼─> GND        │
│          │              │          │             │              │
└──────────┘              └──────────┘             │              │
                                                   │   GP25 (LED) │
                                                   │              │
                                                   └──────┬───────┘
                                                          │
                                                     Micro USB
                                                          │
                                                          ▼
                                                   ┌──────────────┐
                                                   │ Windows Host │
                                                   │  (USB-A)     │
                                                   └──────────────┘
```

### 引脚配置

**Pico GPIO 分配**:

| 引脚 | 功能 | 方向 | 说明 |
|------|------|------|------|
| GP0 | UART0 TX | 输出 | 发送数据到 TTL |
| GP1 | UART0 RX | 输入 | 接收数据从 TTL |
| GP25 | LED | 输出 | 板载 LED，状态指示 |

**UART 配置**:
- 波特率: 115200
- 数据位: 8
- 停止位: 1
- 校验: 无
- 流控: 无

---

## 软件架构

### 模块划分

```
pico_hid_control/
├── engine_v2.py          # 微观引擎 (路径规划 + 帧协议)
├── vision_pipeline.py    # 视觉流水线 (截图 + 检测)
├── agent_v2.py           # 宏观代理 (任务调度 + 异常处理)
├── monitor.py            # 性能监控
├── main.py               # 主程序入口
├── config.yaml           # 配置文件
│
├── pico_hid_firmware/    # Pico 固件
│   ├── src/
│   │   └── main.c
│   ├── include/
│   └── CMakeLists.txt
│
├── debug_console.py      # 串口调试器
├── frame_analyzer.py     # 帧协议分析器
├── visual_debugger.py    # 可视化调试器
│
├── examples/             # 使用示例
├── docs/                 # 文档
├── tests/                # 测试
│
├── deploy.sh             # 部署脚本
├── requirements.txt      # Python 依赖
└── README.md             # 项目说明
```

### 核心类关系

```
┌─────────────────────────────────────────────────────────┐
│                    MacroAgent                            │
│  - 任务调度                                              │
│  - 微休息管理                                            │
│  - 异常处理                                              │
└────────────┬──────────────────────┬─────────────────────┘
             │                      │
             │ uses                 │ uses
             ▼                      ▼
┌────────────────────────┐  ┌──────────────────────────────┐
│  HumanMotionEngine     │  │   VisionPipeline             │
│  - 贝塞尔曲线路径      │  │   - MSS 截图                 │
│  - 帧协议封装          │  │   - YOLO 检测                │
│  - 串口通信            │  │   - 坐标转换                 │
└────────────┬───────────┘  └──────────────────────────────┘
             │
             │ controls
             ▼
┌────────────────────────────────────────────────────────┐
│              Pico Firmware                             │
│  - UART 接收                                           │
│  - 帧解析                                              │
│  - HID 报告生成                                        │
│  - TinyUSB 驱动                                        │
└────────────────────────────────────────────────────────┘
```

---

## 开发环境搭建

### 1. Python 环境

**推荐**: Python 3.8+

**安装依赖**:
```bash
# 使用部署脚本 (推荐)
./deploy.sh

# 或手动安装
pip install -r requirements.txt
```

**核心依赖**:
```txt
numpy>=1.24.0
opencv-python>=4.8.0
pyserial>=3.5
mss>=9.0.0
ultralytics>=8.0.0
PyYAML>=6.0
```

### 2. Pico SDK 环境

**macOS**:
```bash
brew install cmake
brew install --cask gcc-arm-embedded
```

**Ubuntu/Debian**:
```bash
sudo apt install cmake gcc-arm-none-eabi
```

**下载 Pico SDK**:
```bash
git clone -b master https://github.com/raspberrypi/pico-sdk.git
cd pico-sdk
git submodule update --init
```

### 3. IDE 配置

**推荐**: VSCode + Python 插件

**settings.json**:
```json
{
  "python.defaultInterpreterPath": "${workspaceFolder}/venv/bin/python",
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.formatting.provider": "black"
}
```

---

## 固件开发

### 编译固件

```bash
cd pico_hid_firmware
mkdir build && cd build
cmake -DPICO_SDK_PATH=/path/to/pico-sdk ..
make
```

### 烧录固件

1. 按住 Pico 上的 **BOOTSEL** 按钮
2. 用 USB 连接电脑
3. 释放 BOOTSEL，Pico 进入 BOOT 模式
4. 将 `build/pico_hid_firmware.uf2` 拖入 RPI-RP2 磁盘

### 固件架构

```c
main.c
├── main()                      # 主函数
│   ├── setup()                 # 初始化
│   │   ├── stdio_init_all()
│   │   ├── uart_init()
│   │   ├── tusb_init()
│   │   └── init_report()
│   │
│   └── loop()                  # 主循环
│       ├── tud_task()          # TinyUSB 任务
│       ├── process_uart()      # 处理 UART 数据
│       └── check_heartbeat()   # 心跳检测
│
├── process_uart()              # UART 处理
│   ├── 读取字符
│   ├── 帧解析状态机
│   └── 执行命令
│
├── execute_command()           # 命令执行
│   ├── CMD_MOUSE_MOVE_ABS
│   ├── CMD_MOUSE_MOVE_REL
│   ├── CMD_MOUSE_CLICK
│   ├── CMD_KEY_PRESS
│   ├── CMD_TYPE_STRING
│   └── CMD_HEARTBEAT
│
└── send_hid_report()           # HID 报告发送
    ├── 构造报告
    └── tud_hid_report()
```

### 帧协议实现

**状态机**:
```c
typedef enum {
    STATE_IDLE,      // 等待 '#'
    STATE_CMD,       // 读取命令
    STATE_ARGS,      // 读取参数
    STATE_CHECKSUM1, // 读取校验和高位
    STATE_CHECKSUM2  // 读取校验和低位
} ParseState;
```

**命令处理**:
```c
void execute_command(char cmd, const char* args) {
    switch (cmd) {
        case 'A':  // 绝对移动
            parse_coords(args, &x, &y);
            move_mouse_abs(x, y);
            send_ack("OK");
            break;
        
        case 'C':  // 点击
            button = atoi(args);
            click_mouse(button);
            send_ack("OK");
            break;
        
        // ... 其他命令
    }
}
```

---

## Python 开发

### 代码风格

**遵循**: PEP 8

**格式化**: Black
```bash
black engine_v2.py vision_pipeline.py agent_v2.py
```

**类型提示**: 推荐使用
```python
def move_to(self, x: int, y: int, curve_intensity: float = 0.3) -> bool:
    """移动到绝对坐标"""
    pass
```

### 开发流程

1. **创建分支**:
   ```bash
   git checkout -b feature/new-feature
   ```

2. **编写代码**:
   - 遵循模块划分
   - 添加类型提示
   - 编写文档字符串

3. **编写测试**:
   ```bash
   # 单元测试
   python -m pytest tests/test_engine.py
   
   # 集成测试
   python test_integration.py
   ```

4. **提交代码**:
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/new-feature
   ```

### 调试技巧

**使用调试控制台**:
```bash
python debug_console.py --port /dev/ttyUSB0
```

**实时监控**:
```bash
python monitor.py --visual
```

**可视化轨迹**:
```bash
python visual_debugger.py --simulate
```

---

## 测试指南

### 单元测试

**运行所有测试**:
```bash
python -m pytest tests/
```

**运行特定模块**:
```bash
python -m pytest tests/test_engine.py -v
```

**示例测试**:
```python
import unittest
from engine_v2 import FrameCodec

class TestFrameCodec(unittest.TestCase):
    def test_compute_checksum(self):
        """测试校验和计算"""
        payload = "A:100,200"
        checksum = FrameCodec.compute_checksum(payload)
        self.assertEqual(checksum, "CA")
    
    def test_build_frame(self):
        """测试帧构建"""
        frame = FrameCodec.build_frame('A', '100,200')
        self.assertEqual(frame, "#A:100,200|CA\n")
```

### 集成测试

**无硬件测试**:
```bash
python demo_no_hardware.py
```

**硬件测试**:
```bash
python test_integration.py
```

### 性能测试

```bash
# 监控性能
python monitor.py -o perf.csv

# 分析帧协议
python frame_analyzer.py --input communication.log --report stats.json
```

---

## 性能优化

### 延迟优化

**目标**: 端到端延迟 < 50ms

**优化点**:

1. **截图优化**:
   ```python
   # 使用 MSS (比 PIL 快 10 倍)
   import mss
   with mss.mss() as sct:
       frame = sct.grab(sct.monitors[1])
   ```

2. **推理优化**:
   ```python
   # 使用小模型
   model_path = 'yolov8n.pt'  # nano 版本
   
   # 降低分辨率
   results = model(frame, imgsz=320)
   ```

3. **串口优化**:
   ```python
   # 使用中断驱动 (固件端)
   uart_set_irq_enables(uart0, true, false);
   ```

### 吞吐量优化

**目标**: 100+ 帧/秒

**优化点**:

1. **批量发送**:
   ```python
   # 不要等待每个 ACK
   for point in path:
       engine.send_move(point.x, point.y, wait_ack=False)
   ```

2. **管道化**:
   ```python
   # 截图和推理并行
   with ThreadPoolExecutor() as executor:
       frame_future = executor.submit(capture_screen)
       # 同时处理上一帧
   ```

### 内存优化

**目标**: < 200MB

**优化点**:

1. **释放模型**:
   ```python
   # 使用后立即释放
   del model
   torch.cuda.empty_cache()
   ```

2. **限制缓冲区**:
   ```python
   # 使用 deque 限制大小
   from collections import deque
   trajectory = deque(maxlen=100)
   ```

---

## 常见问题

### Q: 如何提高轨迹的自然度？

**A**: 调整贝塞尔曲线控制点:
```python
# 增加控制点随机性
offset1 = random.uniform(0.2, 0.4)
offset2 = random.uniform(0.6, 0.8)

# 增加垂直偏移
perp_offset = random.uniform(-50, 50)
```

### Q: 如何处理网络延迟？

**A**: 使用预测算法:
```python
# 卡尔曼滤波预测目标位置
kalman = KalmanFilter()
predicted_pos = kalman.predict(detected_pos)
```

### Q: 如何检测反作弊系统？

**A**: 监控系统调用:
```python
# 检测异常进程
import psutil
for proc in psutil.process_iter():
    if proc.name() in ['anti_cheat.exe', 'game_guard.exe']:
        logger.warning(f"检测到反作弊: {proc.name()}")
```

---

## 贡献指南

1. Fork 项目
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

---

## 许可证

MIT License

---

## 联系方式

- 问题反馈: 提交 Issue
- 功能建议: 提交 Feature Request
