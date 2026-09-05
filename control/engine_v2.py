"""
微观拟人轨迹引擎 (v2)
======================
与新 Pico 固件协议完全对接:
- 帧格式: #CMD:ARGS|XX\n
- 支持绝对/相对坐标
- 支持鼠标+键盘
- ACK/NACK 反馈机制
- 五次贝塞尔曲线 + 1/f 噪声 + 高斯时序抖动
"""

import math
import time
import random
import logging
import threading
import numpy as np
import serial
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)

# ============================================================================
# USB HID 键盘码表 (HID Usage Tables)
# ============================================================================

class HIDKey:
    """HID 键盘扫描码常量"""
    # 字母
    A = 0x04; B = 0x05; C = 0x06; D = 0x07; E = 0x08
    F = 0x09; G = 0x0A; H = 0x0B; I = 0x0C; J = 0x0D
    K = 0x0E; L = 0x0F; M = 0x10; N = 0x11; O = 0x12
    P = 0x13; Q = 0x14; R = 0x15; S = 0x16; T = 0x17
    U = 0x18; V = 0x19; W = 0x1A; X = 0x1B; Y = 0x1C
    Z = 0x1D
    
    # 数字
    N1 = 0x1E; N2 = 0x1F; N3 = 0x20; N4 = 0x21; N5 = 0x22
    N6 = 0x23; N7 = 0x24; N8 = 0x25; N9 = 0x26; N0 = 0x27
    
    # 特殊键
    ENTER = 0x28; ESCAPE = 0x29; BACKSPACE = 0x2A; TAB = 0x2B
    SPACE = 0x2C; MINUS = 0x2D; EQUAL = 0x2E
    LEFT_BRACKET = 0x2F; RIGHT_BRACKET = 0x30
    BACKSLASH = 0x31; SEMICOLON = 0x33; QUOTE = 0x34
    GRAVE = 0x35; COMMA = 0x36; PERIOD = 0x37; SLASH = 0x38
    CAPSLOCK = 0x39
    
    # F1-F12
    F1 = 0x3A; F2 = 0x3B; F3 = 0x3C; F4 = 0x3D
    F5 = 0x3E; F6 = 0x3F; F7 = 0x40; F8 = 0x41
    F9 = 0x42; F10 = 0x43; F11 = 0x44; F12 = 0x45
    
    # 导航键
    PRINT_SCREEN = 0x46; SCROLL_LOCK = 0x47; PAUSE = 0x48
    INSERT = 0x49; HOME = 0x4A; PAGE_UP = 0x4B
    DELETE = 0x4C; END = 0x4D; PAGE_DOWN = 0x4E
    RIGHT = 0x4F; LEFT = 0x50; DOWN = 0x51; UP = 0x52

class Modifier:
    """修饰键"""
    NONE = 0x00
    LEFT_CTRL = 0x01; RIGHT_CTRL = 0x10
    LEFT_SHIFT = 0x02; RIGHT_SHIFT = 0x20
    LEFT_ALT = 0x04; RIGHT_ALT = 0x40
    LEFT_GUI = 0x08; RIGHT_GUI = 0x80


# ============================================================================
# 字符 → HID 键码映射
# ============================================================================

CHAR_TO_HID = {
    'a': (HIDKey.A, 0), 'b': (HIDKey.B, 0), 'c': (HIDKey.C, 0),
    'd': (HIDKey.D, 0), 'e': (HIDKey.E, 0), 'f': (HIDKey.F, 0),
    'g': (HIDKey.G, 0), 'h': (HIDKey.H, 0), 'i': (HIDKey.I, 0),
    'j': (HIDKey.J, 0), 'k': (HIDKey.K, 0), 'l': (HIDKey.L, 0),
    'm': (HIDKey.M, 0), 'n': (HIDKey.N, 0), 'o': (HIDKey.O, 0),
    'p': (HIDKey.P, 0), 'q': (HIDKey.Q, 0), 'r': (HIDKey.R, 0),
    's': (HIDKey.S, 0), 't': (HIDKey.T, 0), 'u': (HIDKey.U, 0),
    'v': (HIDKey.V, 0), 'w': (HIDKey.W, 0), 'x': (HIDKey.X, 0),
    'y': (HIDKey.Y, 0), 'z': (HIDKey.Z, 0),
    '1': (HIDKey.N1, 0), '2': (HIDKey.N2, 0), '3': (HIDKey.N3, 0),
    '4': (HIDKey.N4, 0), '5': (HIDKey.N5, 0), '6': (HIDKey.N6, 0),
    '7': (HIDKey.N7, 0), '8': (HIDKey.N8, 0), '9': (HIDKey.N9, 0),
    '0': (HIDKey.N0, 0),
    ' ': (HIDKey.SPACE, 0), '\n': (HIDKey.ENTER, 0), '\t': (HIDKey.TAB, 0),
    '-': (HIDKey.MINUS, 0), '=': (HIDKey.EQUAL, 0),
    '[': (HIDKey.LEFT_BRACKET, 0), ']': (HIDKey.RIGHT_BRACKET, 0),
    '\\': (HIDKey.BACKSLASH, 0), ';': (HIDKey.SEMICOLON, 0),
    "'": (HIDKey.QUOTE, 0), '`': (HIDKey.GRAVE, 0),
    ',': (HIDKey.COMMA, 0), '.': (HIDKey.PERIOD, 0), '/': (HIDKey.SLASH, 0),
    # 大写 (需要 Shift)
    'A': (HIDKey.A, Modifier.LEFT_SHIFT), 'B': (HIDKey.B, Modifier.LEFT_SHIFT),
    'C': (HIDKey.C, Modifier.LEFT_SHIFT), 'D': (HIDKey.D, Modifier.LEFT_SHIFT),
    'E': (HIDKey.E, Modifier.LEFT_SHIFT), 'F': (HIDKey.F, Modifier.LEFT_SHIFT),
    'G': (HIDKey.G, Modifier.LEFT_SHIFT), 'H': (HIDKey.H, Modifier.LEFT_SHIFT),
    'I': (HIDKey.I, Modifier.LEFT_SHIFT), 'J': (HIDKey.J, Modifier.LEFT_SHIFT),
    'K': (HIDKey.K, Modifier.LEFT_SHIFT), 'L': (HIDKey.L, Modifier.LEFT_SHIFT),
    'M': (HIDKey.M, Modifier.LEFT_SHIFT), 'N': (HIDKey.N, Modifier.LEFT_SHIFT),
    'O': (HIDKey.O, Modifier.LEFT_SHIFT), 'P': (HIDKey.P, Modifier.LEFT_SHIFT),
    'Q': (HIDKey.Q, Modifier.LEFT_SHIFT), 'R': (HIDKey.R, Modifier.LEFT_SHIFT),
    'S': (HIDKey.S, Modifier.LEFT_SHIFT), 'T': (HIDKey.T, Modifier.LEFT_SHIFT),
    'U': (HIDKey.U, Modifier.LEFT_SHIFT), 'V': (HIDKey.V, Modifier.LEFT_SHIFT),
    'W': (HIDKey.W, Modifier.LEFT_SHIFT), 'X': (HIDKey.X, Modifier.LEFT_SHIFT),
    'Y': (HIDKey.Y, Modifier.LEFT_SHIFT), 'Z': (HIDKey.Z, Modifier.LEFT_SHIFT),
    # 符号 (Shift 组合)
    '!': (HIDKey.N1, Modifier.LEFT_SHIFT), '@': (HIDKey.N2, Modifier.LEFT_SHIFT),
    '#': (HIDKey.N3, Modifier.LEFT_SHIFT), '$': (HIDKey.N4, Modifier.LEFT_SHIFT),
    '%': (HIDKey.N5, Modifier.LEFT_SHIFT), '^': (HIDKey.N6, Modifier.LEFT_SHIFT),
    '&': (HIDKey.N7, Modifier.LEFT_SHIFT), '*': (HIDKey.N8, Modifier.LEFT_SHIFT),
    '(': (HIDKey.N9, Modifier.LEFT_SHIFT), ')': (HIDKey.N0, Modifier.LEFT_SHIFT),
    '_': (HIDKey.MINUS, Modifier.LEFT_SHIFT), '+': (HIDKey.EQUAL, Modifier.LEFT_SHIFT),
    '{': (HIDKey.LEFT_BRACKET, Modifier.LEFT_SHIFT),
    '}': (HIDKey.RIGHT_BRACKET, Modifier.LEFT_SHIFT),
    '|': (HIDKey.BACKSLASH, Modifier.LEFT_SHIFT),
    ':': (HIDKey.SEMICOLON, Modifier.LEFT_SHIFT),
    '"': (HIDKey.QUOTE, Modifier.LEFT_SHIFT),
    '~': (HIDKey.GRAVE, Modifier.LEFT_SHIFT),
    '<': (HIDKey.COMMA, Modifier.LEFT_SHIFT),
    '>': (HIDKey.PERIOD, Modifier.LEFT_SHIFT),
    '?': (HIDKey.SLASH, Modifier.LEFT_SHIFT),
}


# ============================================================================
# 帧协议编解码器
# ============================================================================

class FrameCodec:
    """
    帧编解码: #CMD:ARGS|CHECKSUM\n
    
    用于与 Pico 固件通信
    """
    
    HEADER = ord('#')
    SEPARATOR = ord('|')
    TERMINATOR = ord('\n')
    
    @staticmethod
    def encode(cmd: str, *args: int) -> bytes:
        """
        编码一帧指令
        
        Args:
            cmd: 命令字符 (A/M/C/S/K/T/D/U/P/O)
            *args: 参数 (整数)
        
        Returns:
            编码后的帧字节
        """
        if args:
            body = f"{cmd}:{','.join(str(a) for a in args)}"
        else:
            body = f"{cmd}:"
        
        # 计算校验和
        checksum = sum(ord(c) for c in body) & 0xFF
        frame = f"#{body}|{checksum:02x}\n"
        return frame.encode('ascii')
    
    @staticmethod
    def decode_ack(data: bytes) -> Tuple[bool, str]:
        """
        解码 ACK/NACK 响应
        
        Returns:
            (success, message)
        """
        text = data.decode('ascii').strip()
        if text.startswith('+'):
            return (True, text[1:])
        elif text.startswith('-'):
            return (False, text[1:])
        else:
            return (False, f"UNKNOWN:{text}")


# ============================================================================
# 五次贝塞尔曲线路径生成器
# ============================================================================

class PathGenerator:
    """
    基于五次贝塞尔曲线 + 1/f 噪声的拟人路径生成
    
    相比三次贝塞尔, 五次曲线能表达更丰富的加速度变化:
    - 起始缓慢加速 (人手从静止开始)
    - 中段可能有过冲/犹豫
    - 末端减速停止 (到达目标时减速)
    """
    
    @staticmethod
    def quintic_bezier(p0, p1, p2, p3, p4, p5, t):
        """五次贝塞尔曲线求值"""
        return (
            (1-t)**5 * p0 +
            5*(1-t)**4 * t * p1 +
            10*(1-t)**3 * t**2 * p2 +
            10*(1-t)**2 * t**3 * p3 +
            5*(1-t) * t**4 * p4 +
            t**5 * p5
        )
    
    @staticmethod
    def generate(
        start: np.ndarray,
        end: np.ndarray,
        fatigue: float = 0.0,
        focus: float = 1.0,
    ) -> np.ndarray:
        """
        生成拟人移动路径
        
        Args:
            start: 起点坐标 (2D)
            end: 终点坐标 (2D)
            fatigue: 疲劳度 0~1 (影响抖动和速度)
            focus: 集中度 0~1 (影响轨迹精度)
        
        Returns:
            路径点数组 (N, 2), int 类型
        """
        dist = np.linalg.norm(end - start)
        
        if dist < 1.0:
            return np.array([end], dtype=int)
        
        # 控制点分布: 沿路径方向 + 垂直于路径的随机抖动
        direction = (end - start) / dist
        perpendicular = np.array([-direction[1], direction[0]])
        
        # 抖动幅度: 疲劳 + 注意力不集中 → 更多偏移
        jitter_scale = (1.0 - focus) * 15.0 + fatigue * 10.0
        
        # 5 个控制点 (含起点终点)
        ctrl1 = start + (end - start) * 0.2 + perpendicular * np.random.uniform(-jitter_scale, jitter_scale)
        ctrl2 = start + (end - start) * 0.4 + perpendicular * np.random.uniform(-jitter_scale, jitter_scale)
        ctrl3 = start + (end - start) * 0.6 + perpendicular * np.random.uniform(-jitter_scale, jitter_scale)
        ctrl4 = start + (end - start) * 0.8 + perpendicular * np.random.uniform(-jitter_scale, jitter_scale)
        
        # 步数: 距离越远步数越多, 疲劳时更慢 (步数更多)
        steps = int(max(12, dist / 10) * (1.0 + fatigue * 0.5))
        
        # 非均匀时间参数: 首尾慢, 中间快 (类似 ease-in-out)
        path = []
        for i in range(steps + 1):
            # 非线性 t: 使用 smoothstep 让首尾慢
            linear_t = i / steps
            # 加入微观速度波动 (1/f 噪声近似)
            micro_jitter = np.random.normal(0, 0.005)
            t = np.clip(linear_t + micro_jitter, 0.0, 1.0)
            
            # 五次贝塞尔求值 (逐分量)
            x = PathGenerator.quintic_bezier(start[0], ctrl1[0], ctrl2[0], ctrl3[0], ctrl4[0], end[0], t)
            y = PathGenerator.quintic_bezier(start[1], ctrl1[1], ctrl2[1], ctrl3[1], ctrl4[1], end[1], t)
            path.append([x, y])
        
        path = np.array(path)
        
        # 转为增量路径 (Pico 固件需要相对位移)
        deltas = np.diff(path, axis=0)
        deltas = np.vstack([path[0], deltas])  # 第一个点作为绝对偏移
        
        return np.round(deltas).astype(int)


# ============================================================================
# 主引擎类
# ============================================================================

class HumanMotionEngine:
    """
    拟人运动引擎
    
    整合:
    - 路径生成 (贝塞尔曲线)
    - 帧协议通信 (与 Pico 固件)
    - ACK 确认机制
    - 键盘输入 (HID 键码映射)
    - 打字支持 (字符串 → 逐键输入)
    """
    
    def __init__(
        self,
        serial_port: str = '/dev/cu.usbserial-BG03FPHM',
        baudrate: int = 115200,
        ack_timeout: float = 0.1,
    ):
        """
        初始化引擎
        
        Args:
            serial_port: 串口设备路径
            baudrate: 波特率
            ack_timeout: ACK 等待超时 (秒)
        """
        self.port_path = serial_port
        self.baudrate = baudrate
        self.ack_timeout = ack_timeout
        self.ser: Optional[serial.Serial] = None
        
        # 坐标追踪 (与 Pico 端同步)
        self._cursor_x = 0
        self._cursor_y = 0
        self._lock = threading.Lock()
        
        # 统计
        self._cmd_count = 0
        self._ack_ok = 0
        self._ack_fail = 0
        self._connected = False
    
    def connect(self) -> bool:
        """
        连接 Pico 设备
        
        Returns:
            是否连接成功
        """
        try:
            self.ser = serial.Serial(
                self.port_path, self.baudrate, timeout=0.05
            )
            time.sleep(0.5)  # 等待 Pico 初始化
            
            # 等待 READY 信号
            self._wait_for_ready()
            
            # 发送 PING 验证通信
            self.send_cmd('P', 0, wait_ack=True)
            
            self._connected = True
            logger.info(f"[Engine] 已连接: {self.port_path}")
            return True
            
        except Exception as e:
            logger.error(f"[Engine] 连接失败: {e}")
            self._connected = False
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.ser and self.ser.is_open:
            self.ser.close()
        self._connected = False
        logger.info("[Engine] 已断开")
    
    def _wait_for_ready(self, timeout: float = 3.0):
        """等待 Pico 的 +READY 信号"""
        start = time.time()
        while time.time() - start < timeout:
            if self.ser and self.ser.in_waiting > 0:
                line = self.ser.readline().decode('ascii', errors='ignore').strip()
                if line == '+READY':
                    logger.info("[Engine] Pico 就绪")
                    return
            time.sleep(0.05)
        logger.warning("[Engine] 未收到 READY 信号 (可能已在运行)")
    
    def send_cmd(
        self,
        cmd: str,
        *args: int,
        wait_ack: bool = False
    ) -> Tuple[bool, str]:
        """
        发送命令到 Pico
        
        Args:
            cmd: 命令字符
            *args: 命令参数
            wait_ack: 是否等待 ACK
        
        Returns:
            (success, message)
        """
        if not self._connected or not self.ser:
            return (False, "NOT_CONNECTED")
        
        # 编码帧
        frame = FrameCodec.encode(cmd, *args)
        
        # 清空输入缓冲区
        self.ser.reset_input_buffer()
        
        # 发送
        self.ser.write(frame)
        self._cmd_count += 1
        
        if not wait_ack:
            return (True, "SENT")
        
        # 等待 ACK
        start = time.time()
        while time.time() - start < self.ack_timeout:
            if self.ser.in_waiting > 0:
                data = self.ser.read(self.ser.in_waiting)
                ok, msg = FrameCodec.decode_ack(data)
                if ok:
                    self._ack_ok += 1
                else:
                    self._ack_fail += 1
                return (ok, msg)
            time.sleep(0.001)
        
        self._ack_fail += 1
        return (False, "TIMEOUT")
    
    # ---- 鼠标操作 ----
    
    def move_to(
        self,
        x: int,
        y: int,
        fatigue: float = 0.0,
        focus: float = 1.0,
        wait_ack: bool = False,
    ):
        """
        拟人移动鼠标到绝对坐标
        
        Args:
            x, y: 目标绝对坐标 (屏幕坐标系)
            fatigue: 当前疲劳度 (影响轨迹)
            focus: 当前集中度 (影响精度)
            wait_ack: 是否逐段确认
        """
        with self._lock:
            start = np.array([float(self._cursor_x), float(self._cursor_y)])
            end = np.array([float(x), float(y)])
        
        # 生成路径 (增量序列)
        deltas = PathGenerator.generate(start, end, fatigue, focus)
        
        # 逐段发送
        for delta in deltas:
            dx, dy = int(delta[0]), int(delta[1])
            if dx == 0 and dy == 0:
                continue
            
            self.send_cmd('M', dx, dy, wait_ack=wait_ack)
            
            # 高斯时序抖动 (模拟人类手部微颤抖)
            delay = random.gauss(0.002, 0.0005) * (1.0 + fatigue * 0.4)
            time.sleep(max(0.0008, delay))
        
        # 更新内部坐标
        with self._lock:
            self._cursor_x = x
            self._cursor_y = y
    
    def move_relative(
        self,
        dx: int,
        dy: int,
        fatigue: float = 0.0,
        focus: float = 1.0,
    ):
        """
        拟人相对移动
        
        Args:
            dx, dy: 相对位移
        """
        with self._lock:
            target_x = self._cursor_x + dx
            target_y = self._cursor_y + dy
        
        self.move_to(target_x, target_y, fatigue, focus)
    
    def click(self, button: int = 1):
        """
        鼠标点击
        
        Args:
            button: 1=左键, 2=右键, 3=中键
        """
        # 点击前微小随机延迟 (人类反应时间)
        pre_delay = random.gauss(0.015, 0.005)
        time.sleep(max(0.005, pre_delay))
        
        self.send_cmd('C', button, wait_ack=True)
    
    def double_click(self, button: int = 1):
        """双击"""
        self.click(button)
        time.sleep(random.gauss(0.08, 0.015))
        self.click(button)
    
    def mouse_down(self, button: int = 1):
        """按下鼠标"""
        self.send_cmd('D', button)
    
    def mouse_up(self, button: int = 1):
        """释放鼠标"""
        self.send_cmd('U', button)
    
    def drag_to(
        self,
        x: int,
        y: int,
        button: int = 1,
        fatigue: float = 0.0,
        focus: float = 1.0,
    ):
        """
        拖拽到目标位置
        
        Args:
            x, y: 目标坐标
            button: 拖拽按钮
        """
        self.mouse_down(button)
        time.sleep(random.gauss(0.03, 0.01))
        self.move_to(x, y, fatigue, focus)
        time.sleep(random.gauss(0.02, 0.008))
        self.mouse_up(button)
    
    def scroll(self, delta: int):
        """
        滚轮滚动
        
        Args:
            delta: 正=向上, 负=向下
        """
        # 分段滚动 (模拟人类逐格滚动)
        remaining = delta
        while remaining != 0:
            step = random.randint(1, min(3, abs(remaining)))
            step = step if delta > 0 else -step
            self.send_cmd('S', step)
            remaining -= step
            time.sleep(random.gauss(0.05, 0.015))
    
    # ---- 键盘操作 ----
    
    def key_press(self, keycode: int, modifier: int = 0):
        """
        按下并释放单个键
        
        Args:
            keycode: HID 键码
            modifier: 修饰键 (见 Modifier 类)
        """
        self.send_cmd('K', keycode, modifier, wait_ack=True)
    
    def key_combo(self, modifier: int, keycode: int):
        """
        组合键 (如 Ctrl+C)
        
        Args:
            modifier: 修饰键
            keycode: 主键码
        """
        self.key_press(keycode, modifier)
    
    def hotkey(self, *keys: int):
        """
        多键组合 (如 Ctrl+Shift+Esc)
        
        注: Pico 固件最多支持 6 键同时
        这里用 modifier + 第一个 key 实现常见组合
        """
        if len(keys) < 2:
            return
        # 第一个键作为 modifier, 后面的 key 依次发送
        # 对于 Ctrl+Shift+X 场景: modifier = CTRL|SHIFT, key = X
        combined_mod = 0
        main_key = keys[-1]
        for k in keys[:-1]:
            if k in (HIDKey.LEFT_CTRL, HIDKey.RIGHT_CTRL):
                combined_mod |= Modifier.LEFT_CTRL if k == HIDKey.LEFT_CTRL else Modifier.RIGHT_CTRL
            elif k in (HIDKey.LEFT_SHIFT, HIDKey.RIGHT_SHIFT):
                combined_mod |= Modifier.LEFT_SHIFT if k == HIDKey.LEFT_SHIFT else Modifier.RIGHT_SHIFT
            elif k in (HIDKey.LEFT_ALT, HIDKey.RIGHT_ALT):
                combined_mod |= Modifier.LEFT_ALT if k == HIDKey.LEFT_ALT else Modifier.RIGHT_ALT
            elif k in (0xE3, 0xE7):  # GUI/Win key
                combined_mod |= Modifier.LEFT_GUI if k == 0xE3 else Modifier.RIGHT_GUI
        
        self.key_press(main_key, combined_mod)
    
    def type_string(self, text: str, wpm: float = 60.0, fatigue: float = 0.0):
        """
        拟人打字 (字符串 → 逐键输入)
        
        Args:
            text: 要输入的文本
            wpm: 打字速度 (words per minute, 人类平均 40-80)
            fatigue: 疲劳度 (影响速度和错误率)
        """
        # 计算每键间隔
        # WPM 定义: 1 word = 5 chars, 所以 CPM = WPM * 5
        cpm = wpm * 5.0 * (1.0 - fatigue * 0.3)  # 疲劳时变慢
        key_interval = 60.0 / cpm  # 秒/键
        
        for char in text:
            if char in CHAR_TO_HID:
                keycode, modifier = CHAR_TO_HID[char]
                self.send_cmd('K', keycode, modifier)
                
                # 人类打字间隔: 高斯分布 + 偶尔停顿
                delay = random.gauss(key_interval, key_interval * 0.15)
                
                # 偶尔模拟打字错误 (疲劳越高越容易错)
                if random.random() < fatigue * 0.02:
                    # 打错字 → 退格 → 重新打
                    time.sleep(delay)
                    self.send_cmd('K', HIDKey.BACKSPACE, 0)
                    time.sleep(random.gauss(0.15, 0.05))
                    self.send_cmd('K', keycode, modifier)
                    delay = random.gauss(key_interval, key_interval * 0.15)
                
                time.sleep(max(0.03, delay))
            else:
                logger.warning(f"[Engine] 不支持的字符: '{char}' (U+{ord(char):04X})")
    
    # ---- 坐标管理 ----
    
    def sync_position(self) -> Tuple[int, int]:
        """
        与 Pico 同步当前位置 (通过 PING 命令)
        
        Returns:
            (x, y) 当前位置
        """
        ok, msg = self.send_cmd('P', 0, wait_ack=True)
        if ok and msg.startswith('PONG:'):
            parts = msg[5:].split(',')
            x, y = int(parts[0]), int(parts[1])
            with self._lock:
                self._cursor_x = x
                self._cursor_y = y
            return (x, y)
        return (self._cursor_x, self._cursor_y)
    
    def set_origin(self):
        """重置坐标原点"""
        self.send_cmd('O', 0, 0)
        with self._lock:
            self._cursor_x = 0
            self._cursor_y = 0
    
    def get_position(self) -> Tuple[int, int]:
        """获取当前内部坐标 (不发送指令)"""
        with self._lock:
            return (self._cursor_x, self._cursor_y)
    
    # ---- 状态查询 ----
    
    def get_stats(self) -> dict:
        """获取引擎统计"""
        return {
            "connected": self._connected,
            "cursor": (self._cursor_x, self._cursor_y),
            "commands_sent": self._cmd_count,
            "ack_ok": self._ack_ok,
            "ack_fail": self._ack_fail,
            "ack_success_rate": (
                self._ack_ok / max(1, self._ack_ok + self._ack_fail)
            ),
        }
