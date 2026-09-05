# API 参考文档

本文档提供系统所有核心模块的 API 参考。

## 目录

1. [微观引擎 (engine_v2.py)](#微观引擎)
2. [视觉流水线 (vision_pipeline.py)](#视觉流水线)
3. [宏观代理 (agent_v2.py)](#宏观代理)
4. [性能监控 (monitor.py)](#性能监控)
5. [调试工具](#调试工具)

---

## 微观引擎

**模块**: `engine_v2.py`

### 核心类

#### `HumanMotionEngine`

微观拟人运动引擎，负责生成贝塞尔曲线路径并发送帧协议指令。

**初始化参数**:
```python
def __init__(self, port: str = None, baudrate: int = 115200, timeout: float = 0.1):
    """
    Args:
        port: 串口路径 (如 /dev/ttyUSB0 或 COM3)
        baudrate: 波特率 (默认 115200)
        timeout: 串口超时时间 (秒)
    """
```

**核心方法**:

##### `connect() -> bool`
连接到 Pico 设备。

**返回**: `bool` - 连接成功返回 True

**示例**:
```python
engine = HumanMotionEngine(port='/dev/ttyUSB0')
if engine.connect():
    print("连接成功")
```

##### `disconnect()`
断开连接。

**示例**:
```python
engine.disconnect()
```

##### `move_to(x: int, y: int, curve_intensity: float = 0.3) -> bool`
移动到绝对坐标 (x, y)，使用贝塞尔曲线模拟人类轨迹。

**参数**:
- `x`: 目标 X 坐标 (0-1920)
- `y`: 目标 Y 坐标 (0-1080)
- `curve_intensity`: 曲线弯曲强度 (0.0-1.0，默认 0.3)

**返回**: `bool` - 是否成功

**示例**:
```python
# 移动到屏幕中心
engine.move_to(960, 540)

# 移动到左上角，强曲线
engine.move_to(100, 100, curve_intensity=0.6)
```

##### `move_relative(dx: int, dy: int) -> bool`
相对移动。

**参数**:
- `dx`: X 方向偏移量
- `dy`: Y 方向偏移量

**示例**:
```python
# 向右移动 50 像素
engine.move_relative(50, 0)
```

##### `click(button: int = 1) -> bool`
鼠标点击。

**参数**:
- `button`: 1=左键, 2=右键, 3=中键 (默认 1)

**示例**:
```python
engine.click()        # 左键
engine.click(2)       # 右键
```

##### `double_click() -> bool`
双击。

**示例**:
```python
engine.double_click()
```

##### `drag_to(x: int, y: int, duration: float = 0.5) -> bool`
拖拽到目标位置。

**参数**:
- `x`: 目标 X 坐标
- `y`: 目标 Y 坐标
- `duration`: 拖拽持续时间 (秒，默认 0.5)

**示例**:
```python
engine.drag_to(500, 500, duration=0.8)
```

##### `type_text(text: str, interval: float = 0.05) -> bool`
输入文本。

**参数**:
- `text`: 要输入的文本
- `interval`: 字符间隔 (秒，默认 0.05)

**示例**:
```python
engine.type_text("Hello, World!")
```

##### `press_key(key: int, modifiers: List[int] = None) -> bool`
按下键盘按键。

**参数**:
- `key`: HID 键码 (如 0x04='a', 0x28=Enter)
- `modifiers`: 修饰键列表 (如 [0x01] for Ctrl)

**示例**:
```python
# 按 Enter
engine.press_key(0x28)

# Ctrl+C
engine.press_key(0x06, modifiers=[0x01])
```

##### `scroll(direction: int, clicks: int = 3) -> bool`
鼠标滚轮滚动。

**参数**:
- `direction`: 1=向上, -1=向下
- `clicks`: 滚动格数 (默认 3)

**示例**:
```python
engine.scroll(1, clicks=5)   # 向上滚动 5 格
engine.scroll(-1, clicks=3)  # 向下滚动 3 格
```

##### `heartbeat() -> bool`
发送心跳包，检测设备响应。

**返回**: `bool` - 设备是否在线

**示例**:
```python
if engine.heartbeat():
    print("设备在线")
```

##### `get_stats() -> dict`
获取引擎统计信息。

**返回**: `dict` - 包含以下字段:
```python
{
    'connected': bool,          # 是否已连接
    'commands_sent': int,       # 已发送命令数
    'ack_received': int,        # 收到的 ACK 数
    'ack_failed': int,          # 失败的 ACK 数
    'ack_success_rate': float,  # ACK 成功率 (0.0-1.0)
    'cursor': (int, int)        # 当前光标位置
}
```

**示例**:
```python
stats = engine.get_stats()
print(f"ACK 成功率: {stats['ack_success_rate']:.1%}")
```

---

## 视觉流水线

**模块**: `vision_pipeline.py`

### 核心类

#### `VisionPipeline`

视觉检测流水线，集成 MSS 截图和 YOLO 目标检测。

**初始化参数**:
```python
def __init__(self, model_path: str = 'yolov8n.pt', conf_threshold: float = 0.5):
    """
    Args:
        model_path: YOLO 模型路径
        conf_threshold: 置信度阈值 (0.0-1.0)
    """
```

**核心方法**:

##### `detect_target(target_class: str, region: Tuple[int, int, int, int] = None) -> Optional[Detection]`
检测指定类别的目标。

**参数**:
- `target_class`: 目标类别 (如 'person', 'mouse')
- `region`: 检测区域 (x1, y1, x2, y2)，None 表示全屏

**返回**: `Detection` 对象或 None

**Detection 对象**:
```python
{
    'class': str,           # 类别名
    'confidence': float,    # 置信度
    'bbox': (x1, y1, x2, y2),  # 边界框
    'center': (cx, cy)      # 中心点
}
```

**示例**:
```python
pipeline = VisionPipeline(model_path='yolov8n.pt')

# 检测鼠标
detection = pipeline.detect_target('mouse')
if detection:
    print(f"找到鼠标: {detection['center']}")
    
    # 点击鼠标中心
    engine.move_to(detection['center'][0], detection['center'][1])
    engine.click()
```

##### `detect_all(region: Tuple[int, int, int, int] = None) -> List[Detection]`
检测所有目标。

**参数**:
- `region`: 检测区域，None 表示全屏

**返回**: `List[Detection]` - 检测到的所有目标列表

**示例**:
```python
detections = pipeline.detect_all()
for det in detections:
    print(f"{det['class']}: {det['confidence']:.2f}")
```

##### `capture_screen() -> np.ndarray`
捕获当前屏幕。

**返回**: `np.ndarray` - 屏幕图像 (BGR 格式)

**示例**:
```python
frame = pipeline.capture_screen()
# 可以用 OpenCV 处理
cv2.imshow('Screen', frame)
```

---

## 宏观代理

**模块**: `agent_v2.py`

### 核心类

#### `MacroAgent`

宏观行为代理，管理任务调度、微休息和异常处理。

**初始化参数**:
```python
def __init__(self, work_duration: int = 1200, rest_duration: int = 300):
    """
    Args:
        work_duration: 工作时长 (秒，默认 1200 = 20分钟)
        rest_duration: 休息时长 (秒，默认 300 = 5分钟)
    """
```

**核心方法**:

##### `start()`
启动代理，开始监控工作周期。

**示例**:
```python
agent = MacroAgent(work_duration=1200, rest_duration=300)
agent.start()
```

##### `stop()`
停止代理。

**示例**:
```python
agent.stop()
```

##### `execute_task(task: Callable, *args, **kwargs) -> Any`
执行任务，自动处理异常和重试。

**参数**:
- `task`: 可调用对象
- `*args, **kwargs`: 任务参数

**返回**: 任务返回值

**示例**:
```python
def click_button(x, y):
    engine.move_to(x, y)
    engine.click()

agent.execute_task(click_button, 500, 300)
```

##### `get_status() -> dict`
获取代理状态。

**返回**: `dict` - 包含以下字段:
```python
{
    'state': str,              # 当前状态 (WORKING/RESTING)
    'work_time': float,        # 已工作时间 (秒)
    'rest_time': float,        # 已休息时间 (秒)
    'task_count': int,         # 已执行任务数
    'error_count': int,        # 错误次数
    'last_error': str,         # 最后错误信息
    'next_rest': float         # 距离下次休息 (秒)
}
```

**示例**:
```python
status = agent.get_status()
print(f"状态: {status['state']}")
print(f"已工作: {status['work_time']:.0f} 秒")
print(f"任务数: {status['task_count']}")
```

---

## 性能监控

**模块**: `monitor.py`

### 核心类

#### `PerformanceMetrics`

性能指标收集器。

**初始化参数**:
```python
def __init__(self, max_samples: int = 1000):
    """
    Args:
        max_samples: 最大样本数 (用于计算平均值)
    """
```

**核心方法**:

##### `record_screenshot()`
记录截图时间戳。

**示例**:
```python
metrics.record_screenshot()
```

##### `record_inference()`
记录推理完成时间戳。

**示例**:
```python
metrics.record_inference()
```

##### `record_command_sent()`
记录指令发送时间戳。

**示例**:
```python
metrics.record_command_sent()
```

##### `record_response_received(success: bool = True)`
记录响应接收时间戳。

**参数**:
- `success`: 是否成功 (默认 True)

**示例**:
```python
metrics.record_response_received(success=True)
```

##### `record_task(success: bool = True)`
记录任务结果。

**示例**:
```python
metrics.record_task(success=True)
```

##### `get_snapshot() -> dict`
获取当前性能快照。

**返回**: `dict` - 包含 CPU、内存、延迟、成功率等指标

**示例**:
```python
snapshot = metrics.get_snapshot()
print(f"CPU: {snapshot['cpu_percent']:.1f}%")
print(f"端到端延迟: {snapshot['e2e_latency_avg_ms']:.1f} ms")
```

---

#### `PerformanceMonitor`

性能监控器，提供实时显示和 CSV 导出。

**初始化参数**:
```python
def __init__(self, metrics: PerformanceMetrics, update_interval: float = 1.0, 
             csv_output: str = None, visual_mode: bool = False):
    """
    Args:
        metrics: 性能指标收集器
        update_interval: 更新间隔 (秒)
        csv_output: CSV 输出文件路径
        visual_mode: 是否启用可视化模式
    """
```

**核心方法**:

##### `start()`
启动监控。

**示例**:
```python
metrics = PerformanceMetrics()
monitor = PerformanceMonitor(metrics, csv_output='perf.csv')
monitor.start()
```

##### `stop()`
停止监控。

**示例**:
```python
monitor.stop()
```

---

## 调试工具

### 串口调试器

**模块**: `debug_console.py`

**命令行使用**:
```bash
python debug_console.py --port /dev/ttyUSB0
```

**交互命令**:
```
A:100,200      # 绝对移动到 (100, 200)
M:10,20        # 相对移动 (+10, +20)
C:1            # 左键点击
C:2            # 右键点击
K:04           # 按下 'a' 键
T:Hello        # 输入文本 'Hello'
P:0            # 心跳检测
:history       # 显示历史记录
:quit          # 退出
```

---

### 帧协议分析器

**模块**: `frame_analyzer.py`

**命令行使用**:
```bash
# 从日志文件分析
python frame_analyzer.py --input log.txt

# 实时监控
python frame_analyzer.py --port /dev/ttyUSB0

# 生成报告
python frame_analyzer.py --input log.txt --report stats.json
```

---

### 可视化调试器

**模块**: `visual_debugger.py`

**命令行使用**:
```bash
# 模拟模式
python visual_debugger.py --simulate

# 实时监控
python visual_debugger.py --port /dev/ttyUSB0
```

---

## 帧协议格式

**格式**: `#CMD:ARGS|XX\n`

- `CMD`: 命令字符 (1 字节)
- `ARGS`: 参数 (可变长度)
- `XX`: 校验和 (2 位十六进制)
- `\n`: 换行符

**命令列表**:

| 命令 | 说明 | 参数格式 | 示例 |
|------|------|----------|------|
| `A` | 绝对移动 | `x,y` | `#A:100,200\|CA\n` |
| `M` | 相对移动 | `dx,dy` | `#M:10,20\|52\n` |
| `C` | 点击 | `button` | `#C:1\|23\n` |
| `K` | 按键 | `keycode` | `#K:04\|24\n` |
| `T` | 文本 | `text` | `#T:Hi\|8F\n` |
| `S` | 滚轮 | `direction,clicks` | `#S:1,3\|A1\n` |
| `P` | 心跳 | `0` | `#P:0\|70\n` |

**响应格式**:

- ACK: `+OK\n` 或 `+STATUS\n`
- NACK: `-REASON\n` (如 `-CHECKSUM_ERR\n`)

**校验和计算**:
```python
payload = "A:100,200"
checksum = sum(payload.encode()) & 0xFF
checksum_hex = f"{checksum:02X}"  # "CA"
frame = f"#{payload}|{checksum_hex}\n"
```

---

## 常量定义

### HID 键码

```python
# 字母键
KEY_A = 0x04
KEY_B = 0x05
# ... (0x04 - 0x1D)

# 数字键
KEY_1 = 0x1E
KEY_2 = 0x1F
# ... (0x1E - 0x27)

# 特殊键
KEY_ENTER = 0x28
KEY_ESC = 0x29
KEY_BACKSPACE = 0x2A
KEY_TAB = 0x2B
KEY_SPACE = 0x2C

# 修饰键
MOD_CTRL = 0x01
MOD_SHIFT = 0x02
MOD_ALT = 0x04
```

### 鼠标按钮

```python
BUTTON_LEFT = 1
BUTTON_RIGHT = 2
BUTTON_MIDDLE = 3
```

---

## 错误处理

### 常见异常

```python
class ConnectionError(Exception):
    """连接失败"""
    pass

class TimeoutError(Exception):
    """超时"""
    pass

class ChecksumError(Exception):
    """校验和错误"""
    pass
```

### 错误处理示例

```python
try:
    engine.connect()
    engine.move_to(500, 300)
except ConnectionError as e:
    print(f"连接失败: {e}")
except TimeoutError as e:
    print(f"操作超时: {e}")
except ChecksumError as e:
    print(f"校验和错误: {e}")
```

---

## 完整示例

```python
from engine_v2 import HumanMotionEngine
from vision_pipeline import VisionPipeline
from agent_v2 import MacroAgent

# 初始化
engine = HumanMotionEngine(port='/dev/ttyUSB0')
pipeline = VisionPipeline(model_path='yolov8n.pt')
agent = MacroAgent()

# 连接
engine.connect()
agent.start()

try:
    # 检测目标
    detection = pipeline.detect_target('mouse')
    
    if detection:
        # 移动到目标
        x, y = detection['center']
        engine.move_to(x, y)
        
        # 点击
        engine.click()
        
        # 记录任务
        agent.execute_task(lambda: True)
        
        # 获取统计
        stats = engine.get_stats()
        print(f"ACK 成功率: {stats['ack_success_rate']:.1%}")
    
finally:
    engine.disconnect()
    agent.stop()
```
