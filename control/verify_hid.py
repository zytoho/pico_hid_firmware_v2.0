#!/usr/bin/env python3
"""
Pico HID 一键验证脚本
自动测试鼠标、键盘、组合键等所有 HID 功能

使用方法:
    python3 verify_hid.py [串口设备]
    
示例:
    python3 verify_hid.py /dev/tty.usbserial-1410
    python3 verify_hid.py /dev/ttyUSB0
    python3 verify_hid.py COM3
"""

import sys
import time
import serial
import argparse
from datetime import datetime


class HIDVerifier:
    """HID 功能验证器"""
    
    def __init__(self, port, baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.results = []
        
    def connect(self):
        """连接串口"""
        print(f"\n{'='*60}")
        print(f"Pico HID 功能验证器")
        print(f"{'='*60}")
        print(f"串口: {self.port}")
        print(f"波特率: {self.baudrate}")
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")
        
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=2)
            time.sleep(2)  # 等待 Pico 启动
            print("✓ 串口连接成功\n")
        except Exception as e:
            print(f"✗ 串口连接失败: {e}")
            print(f"\n请检查:")
            print(f"  1. 设备是否已连接")
            print(f"  2. 串口设备路径是否正确")
            print(f"  3. 是否有其他程序占用串口")
            sys.exit(1)
    
    def send_cmd(self, cmd_str, description=""):
        """发送命令并获取响应"""
        checksum = sum(ord(c) for c in cmd_str) & 0xFF
        frame = f'#{cmd_str}|{checksum:02x}\n'
        
        try:
            self.ser.write(frame.encode())
            time.sleep(0.1)  # 等待响应
            
            resp = self.ser.readline().decode().strip()
            
            success = resp.startswith('+')
            status = "✓" if success else "✗"
            
            if description:
                print(f"  {status} {description:40s} → {resp}")
            else:
                print(f"  {status} 命令: {cmd_str:20s} → {resp}")
            
            self.results.append({
                'cmd': cmd_str,
                'desc': description,
                'success': success,
                'resp': resp
            })
            
            return success, resp
        except Exception as e:
            print(f"  ✗ {description or cmd_str} → 错误: {e}")
            self.results.append({
                'cmd': cmd_str,
                'desc': description,
                'success': False,
                'resp': str(e)
            })
            return False, str(e)
    
    def test_ping(self):
        """测试 1: PING 心跳"""
        print("\n" + "="*60)
        print("测试 1: PING 心跳检测")
        print("="*60)
        print("目的: 验证串口通信和固件响应\n")
        
        self.send_cmd('P:0', 'PING 命令')
        time.sleep(0.5)
    
    def test_mouse_move(self):
        """测试 2: 鼠标相对移动"""
        print("\n" + "="*60)
        print("测试 2: 鼠标相对移动")
        print("="*60)
        print("目的: 验证鼠标移动功能\n")
        print("提示: 在 Windows 上观察鼠标光标移动\n")
        
        self.send_cmd('M:100,0', '右移 100 像素')
        time.sleep(0.3)
        
        self.send_cmd('M:0,100', '下移 100 像素')
        time.sleep(0.3)
        
        self.send_cmd('M:-100,0', '左移 100 像素')
        time.sleep(0.3)
        
        self.send_cmd('M:0,-100', '上移 100 像素')
        time.sleep(0.3)
        
        self.send_cmd('M:-50,-50', '左上移动 50 像素')
        time.sleep(0.3)
    
    def test_mouse_click(self):
        """测试 3: 鼠标点击"""
        print("\n" + "="*60)
        print("测试 3: 鼠标点击")
        print("="*60)
        print("目的: 验证鼠标按键功能\n")
        print("提示: 在 Windows 上观察点击事件\n")
        
        self.send_cmd('C:1', '左键点击')
        time.sleep(0.5)
        
        self.send_cmd('C:2', '右键点击')
        time.sleep(0.5)
        
        self.send_cmd('C:3', '中键点击')
        time.sleep(0.5)
    
    def test_mouse_scroll(self):
        """测试 4: 鼠标滚轮"""
        print("\n" + "="*60)
        print("测试 4: 鼠标滚轮")
        print("="*60)
        print("目的: 验证滚轮功能\n")
        print("提示: 在 Windows 上观察滚动效果\n")
        
        self.send_cmd('S:3', '向上滚动 3 格')
        time.sleep(0.5)
        
        self.send_cmd('S:-3', '向下滚动 3 格')
        time.sleep(0.5)
    
    def test_keyboard_single(self):
        """测试 5: 单个按键"""
        print("\n" + "="*60)
        print("测试 5: 单个按键")
        print("="*60)
        print("目的: 验证键盘输入功能\n")
        print("提示: 在 Windows 记事本中观察字符输入\n")
        
        # keycode 参考: a=4, b=5, c=6, ... z=29, 0=39, 1=30, ... 9=37
        self.send_cmd('K:4,0', '字母 A')
        time.sleep(0.3)
        
        self.send_cmd('K:5,0', '字母 B')
        time.sleep(0.3)
        
        self.send_cmd('K:6,0', '字母 C')
        time.sleep(0.3)
        
        self.send_cmd('K:44,0', '空格键')
        time.sleep(0.3)
    
    def test_keyboard_modifier(self):
        """测试 6: 修饰键组合"""
        print("\n" + "="*60)
        print("测试 6: 修饰键组合")
        print("="*60)
        print("目的: 验证组合键功能\n")
        print("提示: 在 Windows 上观察组合键效果\n")
        
        # modifier: 1=Ctrl, 2=Shift, 4=Alt
        self.send_cmd('K:4,1', 'Ctrl+A (全选)')
        time.sleep(0.5)
        
        self.send_cmd('K:22,1', 'Ctrl+Z (撤销)')
        time.sleep(0.5)
        
        self.send_cmd('K:6,2', 'Shift+C (大写 C)')
        time.sleep(0.5)
    
    def test_keyboard_sequence(self):
        """测试 7: 连续输入"""
        print("\n" + "="*60)
        print("测试 7: 连续输入")
        print("="*60)
        print("目的: 验证快速连续输入\n")
        print("提示: 在 Windows 记事本中观察字符输入\n")
        
        # h=11, e=8, l=15, l=15, o=18
        self.send_cmd('T:11,8,15,15,18', '输入 "hello"')
        time.sleep(0.5)
        
        # 回车键 = 40
        self.send_cmd('K:40,0', '回车键')
        time.sleep(0.3)
        
        # P=19, i=12, c=6, o=18
        self.send_cmd('T:19,12,6,18', '输入 "Pico"')
        time.sleep(0.3)
    
    def test_complex_sequence(self):
        """测试 8: 复杂操作序列"""
        print("\n" + "="*60)
        print("测试 8: 复杂操作序列")
        print("="*60)
        print("目的: 验证组合功能\n")
        print("提示: 在 Windows 上观察综合效果\n")
        
        print("\n  模拟: 移动 → 点击 → 输入 → 回车")
        self.send_cmd('M:50,50', '移动鼠标')
        time.sleep(0.2)
        
        self.send_cmd('C:1', '左键点击')
        time.sleep(0.2)
        
        self.send_cmd('T:11,8,12,12,18', '输入 "hello"')
        time.sleep(0.2)
        
        self.send_cmd('K:40,0', '回车')
        time.sleep(0.2)
    
    def print_summary(self):
        """打印测试汇总"""
        print("\n" + "="*60)
        print("测试汇总")
        print("="*60)
        
        total = len(self.results)
        passed = sum(1 for r in self.results if r['success'])
        failed = total - passed
        
        print(f"\n总测试数: {total}")
        print(f"通过: {passed} ✓")
        print(f"失败: {failed} {'✗' if failed > 0 else ''}")
        
        if failed > 0:
            print("\n失败的测试:")
            for r in self.results:
                if not r['success']:
                    desc = r['desc'] or r['cmd']
                    print(f"  ✗ {desc}")
                    print(f"    响应: {r['resp']}")
        
        print("\n" + "="*60)
        if failed == 0:
            print("✅ 所有测试通过! Pico HID 功能正常")
        else:
            print(f"⚠️  {failed} 个测试失败，请检查固件和硬件连接")
        print("="*60)
        
        print("\n验证提示:")
        print("  1. 如果所有命令都返回 +ACK，说明串口通信正常")
        print("  2. 请在 Windows 端确认实际 HID 事件是否触发:")
        print("     - 鼠标是否移动/点击/滚动")
        print("     - 键盘是否输入字符")
        print("     - 组合键是否生效")
        print("  3. 如命令成功但 Windows 无响应，检查:")
        print("     - Pico USB 是否连接到 Windows")
        print("     - Windows 是否识别到 HID 设备")
        print("     - 设备管理器中是否有感叹号\n")
    
    def run(self):
        """运行完整测试"""
        try:
            self.connect()
            self.test_ping()
            self.test_mouse_move()
            self.test_mouse_click()
            self.test_mouse_scroll()
            self.test_keyboard_single()
            self.test_keyboard_modifier()
            self.test_keyboard_sequence()
            self.test_complex_sequence()
            self.print_summary()
            
        except KeyboardInterrupt:
            print("\n\n用户中断测试")
        finally:
            if self.ser and self.ser.is_open:
                self.ser.close()
                print("\n✓ 串口已关闭")


def detect_serial_port():
    """自动检测串口设备"""
    import glob
    
    # 常见的串口路径模式
    patterns = [
        '/dev/tty.usbserial-*',  # macOS USB-to-TTL
        '/dev/tty.usbmodem*',    # macOS CDC
        '/dev/ttyACM*',          # Linux Pico
        '/dev/ttyUSB*',          # Linux USB-to-TTL
    ]
    
    for pattern in patterns:
        devices = glob.glob(pattern)
        if devices:
            return devices[0]
    
    return None


def main():
    parser = argparse.ArgumentParser(
        description='Pico HID 一键验证脚本',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s /dev/tty.usbserial-1410
  %(prog)s /dev/ttyUSB0
  %(prog)s COM3
  
提示:
  - 如不指定串口，脚本会尝试自动检测
  - 验证前请在 Windows 端打开记事本或画图工具
  - 观察鼠标移动、点击、键盘输入等效果
        """
    )
    
    parser.add_argument(
        'port',
        nargs='?',
        help='串口设备路径 (如 /dev/tty.usbserial-1410 或 COM3)'
    )
    
    parser.add_argument(
        '-b', '--baudrate',
        type=int,
        default=115200,
        help='波特率 (默认: 115200)'
    )
    
    args = parser.parse_args()
    
    # 自动检测串口
    port = args.port
    if not port:
        port = detect_serial_port()
        if port:
            print(f"自动检测到串口: {port}")
        else:
            print("✗ 未检测到串口设备")
            print("\n请手动指定串口路径:")
            print("  python3 verify_hid.py /dev/tty.usbserial-XXXX  (macOS)")
            print("  python3 verify_hid.py /dev/ttyUSB0             (Linux)")
            print("  python3 verify_hid.py COM3                     (Windows)")
            sys.exit(1)
    
    # 运行验证
    verifier = HIDVerifier(port, args.baudrate)
    verifier.run()


if __name__ == '__main__':
    main()
