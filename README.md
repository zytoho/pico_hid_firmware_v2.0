# Pico HID Firmware

基于 Raspberry Pi Pico 的硬件级 HID 模拟系统，通过物理 USB 设备模拟键鼠操作，完全规避软件层面的检测和驱动劫持。

## 核心特性

- **硬件级 HID**: Raspberry Pi Pico 作为真实 USB 设备，Windows 识别为物理鼠标/键盘
- **拟人化轨迹**: 五次贝塞尔曲线 + 1/f 噪声 + 高斯抖动，模拟真实人类操作
- **游戏自动化**: 集成 YOLO 视觉识别，支持自动战斗、拾取、补血补蓝
- **高性能**: 端到端延迟 < 50ms，支持 100+ 帧/秒
- **帧协议**: `#CMD:ARGS|XX\n` 格式，带校验和确认机制

## 系统架构

```
┌─────────────────────────────────────────┐
│  MacBook Pro (控制端)                    │
│  - game_agent.py (战斗决策)             │
│  - game_vision.py (视觉识别)            │
│  - engine_v2.py (拟人轨迹生成)          │
└─────────────┬───────────────────────────┘
              │ USB 串口 (115200 baud)
              ▼
┌─────────────────────────────────────────┐
│  USB-to-TTL 转换器                      │
│  - CH340/CP2102                         │
│  - UART 转 USB                          │
└─────────────┬───────────────────────────┘
              │ TX/RX/GND
              ▼
┌─────────────────────────────────────────┐
│  Raspberry Pi Pico (固件)               │
│  - C/C++ 固件                           │
│  - TinyUSB HID 设备                     │
│  - 帧协议解析                           │
└─────────────┬───────────────────────────┘
              │ USB HID
              ▼
┌─────────────────────────────────────────┐
│  Windows 主机                            │
│  - 识别为真实鼠标键盘                    │
│  - 游戏/应用运行环境                     │
└─────────────────────────────────────────┘
```

## 快速开始

### 1. 硬件准备

- Raspberry Pi Pico
- USB-to-TTL 转换器 (CH340/CP2102)
- 杜邦线 (母对母)
- Micro USB 数据线

### 2. 接线

```
USB-to-TTL          Raspberry Pi Pico
┌──────────┐        ┌──────────┐
│ TX  ──────────>   │ GP1 (RX) │
│ RX  <──────────   │ GP0 (TX) │
│ GND ───────────   │ GND      │
└──────────┘        │ USB ──────────> Windows
                    └──────────┘
```

### 3. 安装部署

```bash
# 克隆项目
cd ~/pico_hid_firmware

# 安装 Python 依赖
pip install -r requirements.txt

# 编译固件
cd pico_hid_firmware
mkdir build && cd build
cmake ..
make

# 烧录固件
# 按住 Pico 的 BOOTSEL 按钮，连接 USB，拖入 .uf2 文件
```

### 4. 运行

```bash
# 游戏自动化战斗
python game_agent.py --port /dev/ttyUSB0 --model game_yolo.pt

# 无硬件演示
python demo_no_hardware.py

# 性能监控
python monitor.py -o performance.csv

# 调试工具
python debug_console.py --port /dev/ttyUSB0
```

## 项目结构

```
.
├── pico_hid_firmware/          # Pico 固件源码
│   ├── src/main.c             # 主程序
│   ├── include/               # 头文件
│   └── CMakeLists.txt         # 构建配置
│
├── game_vision.py             # 游戏视觉模块
├── game_agent.py              # 游戏自动化 Agent
├── engine_v2.py               # 微观引擎
├── vision_pipeline.py         # 视觉流水线
├── agent_v2.py                # 宏观 Agent
├── monitor.py                 # 性能监控
├── debug_console.py           # 调试工具
├── frame_analyzer.py          # 帧分析器
├── visual_debugger.py         # 可视化调试
├── config.yaml                # 配置文件
├── requirements.txt           # Python 依赖
├── deploy.sh                  # 部署脚本
│
├── examples/                  # 使用示例
│   ├── example_simple_click.py
│   ├── example_typing.py
│   ├── example_vision_click.py
│   ├── example_form_filling.py
│   ├── example_batch_click.py
│   ├── example_human_pattern.py
│   ├── example_game_combat.py
│   └── README.md
│
└── docs/                      # 文档
    ├── API_REFERENCE.md
    ├── DEVELOPMENT_GUIDE.md
    └── GAME_AUTOMATION_GUIDE.md
```

## 帧协议

格式: `#CMD:ARGS|XX\n`

| 命令 | 说明 | 参数 | 示例 |
|------|------|------|------|
| `M` | 相对移动 | `dx,dy` | `#M:10,-5|XX\n` |
| `A` | 绝对移动 | `x,y` | `#A:100,200|XX\n` |
| `C` | 点击 | `button` (1=左,2=右,3=中) | `#C:1|XX\n` |
| `K` | 按键 | `keycode` | `#K:04|XX\n` |
| `T` | 输入文本 | `string` | `#T:Hello|XX\n` |
| `P` | 心跳 | `0` | `#P:0|XX\n` |

校验和: 所有字节累加和的低 8 位 (十六进制)

## 核心模块

### 微观引擎 (engine_v2.py)

```python
from engine_v2 import HumanMotionEngine

engine = HumanMotionEngine('/dev/ttyUSB0')

# 移动
engine.move_relative(dx=100, dy=50)
engine.move_to(x=500, y=300)

# 点击
engine.click(button=1)
engine.double_click()

# 键盘
engine.type_text("Hello")
engine.press_key(0x28)  # Enter
engine.press_combo([0x01, 0x04])  # Ctrl+A
```

### 游戏视觉 (game_vision.py)

```python
from game_vision import GameVision

vision = GameVision(model_path='game_yolo.pt')

# 检测怪物
monsters = vision.detect_monsters(frame)
for monster in monsters:
    print(f"类型: {monster.monster_type}")
    print(f"距离: {monster.distance}像素")
    print(f"攻击点: {monster.attack_point}")

# 检测掉落物
loots = vision.detect_loots(frame)

# 血量检测
hp = vision.detect_health_bar(frame, region=(50, 50, 200, 20))
```

### 游戏自动化 (game_agent.py)

```python
from game_vision import GameVision
from game_agent import GameCombatAgent, CombatConfig

vision = GameVision(model_path='game_yolo.pt')
config = CombatConfig(
    hp_threshold=30,      # 血量低于 30% 补血
    mp_threshold=20,      # 蓝量低于 20% 补蓝
    pickup_range=200,     # 掉落物拾取范围
    attack_cooldown=0.8   # 攻击冷却
)

agent = GameCombatAgent(vision=vision, config=config)
agent.run()
```

## 游戏自动化

### 训练 YOLO 模型

1. 收集游戏截图 (至少 500 张)
2. 标注目标类别:
   - `normal_monster`: 普通怪
   - `elite_monster`: 精英怪
   - `boss`: BOSS
   - `loot`: 掉落物
   - `hp_bar`: 血条
   - `mp_bar`: 蓝条
3. 训练模型:
   ```bash
   yolo train data=dataset.yaml model=yolov8n.pt epochs=100
   ```

### 运行自动化

```bash
python game_agent.py \
    --port /dev/ttyUSB0 \
    --model game_yolo.pt \
    --hp-key 1 \
    --mp-key 2 \
    --pickup-key f \
    --hp-threshold 30 \
    --mp-threshold 20
```

详细指南: [游戏自动化指南](docs/GAME_AUTOMATION_GUIDE.md)

## 性能指标

| 指标 | 值 |
|------|-----|
| 端到端延迟 | < 50ms |
| 吞吐量 | 100+ 帧/秒 |
| 轨迹平滑度 | 五次贝塞尔曲线 |
| 校验和错误率 | < 0.1% |
| CPU 占用 | < 30% |

## 调试工具

### 串口调试器

```bash
python debug_console.py --port /dev/ttyUSB0
```

交互式发送命令，查看响应。

### 帧协议分析器

```bash
python frame_analyzer.py -i communication.log -r stats.json
```

分析日志文件，生成统计报告。

### 可视化调试

```bash
python visual_debugger.py --simulate
```

实时显示系统状态和轨迹。

## 测试

```bash
# 组件测试
python test_components.py

# 集成测试
python test_integration.py

# 覆盖率
python -m pytest --cov=.
```

## 示例

查看 `examples/` 目录:

- `example_simple_click.py`: 基础点击
- `example_typing.py`: 文本输入
- `example_scroll_navigate.py`: 滚动导航
- `example_vision_click.py`: 视觉点击
- `example_form_filling.py`: 表单填充
- `example_batch_click.py`: 批量操作
- `example_human_pattern.py`: 拟人化模式
- `example_game_combat.py`: 游戏战斗

## 故障排查

### Pico 无法识别

1. 检查 USB 连接
2. 确认固件已烧录
3. 检查设备管理器

### 串口通信失败

1. 检查接线 (TX/RX 是否接反)
2. 确认波特率 (115200)
3. 使用 `debug_console.py` 测试

### 延迟过高

1. 检查 CPU 占用
2. 降低帧率限制
3. 优化 YOLO 模型

## 文档

- [API 参考](docs/API_REFERENCE.md)
- [开发指南](docs/DEVELOPMENT_GUIDE.md)
- [游戏自动化指南](docs/GAME_AUTOMATION_GUIDE.md)

## 技术栈

- **固件**: C/C++, Raspberry Pi Pico SDK, TinyUSB
- **控制端**: Python 3.8+
- **视觉**: OpenCV, Ultralytics YOLO
- **通信**: pyserial
- **监控**: psutil, matplotlib

## 许可证

MIT License
