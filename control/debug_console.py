#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口调试器
==========
交互式串口调试工具，支持：
- 手动发送帧协议命令
- 实时显示响应
- 查看 ACK/NACK 状态
- 自动校验和计算
- 历史记录

使用方法:
    python debug_console.py --port /dev/tty.usbserial-110
"""

import serial
import time
import sys
from typing import Optional


class FrameCodec:
    """帧协议编解码器"""
    
    @staticmethod
    def compute_checksum(data: str) -> str:
        """计算校验和"""
        checksum = sum(data.encode()) & 0xFF
        return f"{checksum:02X}"
    
    @staticmethod
    def build_frame(command: str, args: str = "") -> str:
        """
        构建帧
        
        Args:
            command: 命令字符 (M, A, C, K, T 等)
            args: 参数字符串
        
        Returns:
            完整帧字符串 (包含 #, :, |, XX, \n)
        
        Examples:
            build_frame('A', '100,200') -> '#A:100,200|XX\n'
            build_frame('C', '1') -> '#C:1|XX\n'
        """
        payload = f"{command}:{args}"
        checksum = FrameCodec.compute_checksum(payload)
        return f"#{payload}|{checksum}\n"
    
    @staticmethod
    def parse_response(response: str) -> dict:
        """
        解析响应
        
        Args:
            response: 响应字符串
        
        Returns:
            解析结果字典
        """
        response = response.strip()
        
        if response.startswith('+'):
            return {'type': 'ACK', 'status': response[1:], 'success': True}
        elif response.startswith('-'):
            return {'type': 'NACK', 'reason': response[1:], 'success': False}
        else:
            return {'type': 'UNKNOWN', 'data': response, 'success': None}


class DebugConsole:
    """串口调试控制台"""
    
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.serial: Optional[serial.Serial] = None
        self.history = []
    
    def connect(self) -> bool:
        """连接串口"""
        try:
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=1.0
            )
            print(f"✓ 已连接到 {self.port} @ {self.baudrate} baud")
            return True
        except serial.SerialException as e:
            print(f"✗ 连接失败: {e}")
            return False
    
    def disconnect(self):
        """断开连接"""
        if self.serial and self.serial.is_open:
            self.serial.close()
            print("✓ 已断开连接")
    
    def send_command(self, command: str, args: str = "") -> dict:
        """
        发送命令并等待响应
        
        Args:
            command: 命令字符
            args: 参数
        
        Returns:
            响应结果字典
        """
        if not self.serial or not self.serial.is_open:
            print("✗ 未连接")
            return {'success': False, 'error': 'Not connected'}
        
        # 构建帧
        frame = FrameCodec.build_frame(command, args)
        
        # 发送
        self.serial.write(frame.encode())
        self.serial.flush()
        
        # 记录历史
        self.history.append({
            'time': time.time(),
            'direction': 'TX',
            'data': frame.strip(),
            'command': command,
            'args': args
        })
        
        # 等待响应
        time.sleep(0.1)
        
        if self.serial.in_waiting > 0:
            response = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
            
            # 解析响应
            parsed = FrameCodec.parse_response(response)
            
            # 记录历史
            self.history.append({
                'time': time.time(),
                'direction': 'RX',
                'data': response.strip(),
                'parsed': parsed
            })
            
            return parsed
        else:
            return {'success': None, 'error': 'No response (timeout)'}
    
    def send_raw(self, data: str):
        """发送原始数据（不添加帧格式）"""
        if not self.serial or not self.serial.is_open:
            print("✗ 未连接")
            return
        
        self.serial.write(data.encode())
        self.serial.flush()
        
        self.history.append({
            'time': time.time(),
            'direction': 'TX',
            'data': data.strip(),
            'raw': True
        })
    
    def read_available(self) -> str:
        """读取所有可用数据"""
        if not self.serial or not self.serial.is_open:
            return ""
        
        if self.serial.in_waiting > 0:
            data = self.serial.read(self.serial.in_waiting).decode('utf-8', errors='ignore')
            
            self.history.append({
                'time': time.time(),
                'direction': 'RX',
                'data': data.strip(),
                'raw': True
            })
            
            return data
        return ""
    
    def show_history(self, n: int = 20):
        """显示历史记录"""
        print(f"\n{'='*60}")
        print(f"历史记录 (最近 {n} 条)")
        print(f"{'='*60}")
        
        for item in self.history[-n:]:
            timestamp = time.strftime("%H:%M:%S", time.localtime(item['time']))
            direction = item['direction']
            data = item['data']
            
            if direction == 'TX':
                print(f"[{timestamp}] → {data}")
            else:
                print(f"[{timestamp}] ← {data}")
    
    def interactive(self):
        """交互式模式"""
        print("\n" + "="*60)
        print("串口调试器 - 交互模式")
        print("="*60)
        print("\n命令格式:")
        print("  <command>:<args>  - 发送命令 (自动计算校验和)")
        print("  !<raw_data>       - 发送原始数据")
        print("  :history          - 显示历史记录")
        print("  :quit             - 退出")
        print("\n常用命令示例:")
        print("  A:100,200         - 绝对移动到 (100, 200)")
        print("  M:10,20           - 相对移动 (+10, +20)")
        print("  C:1               - 左键点击")
        print("  C:2               - 右键点击")
        print("  K:04              - 按下 'a' 键 (HID keycode 0x04)")
        print("  T:Hello           - 输入文本 'Hello'")
        print("  P:0               - 心跳检测")
        print("\n输入命令 (输入 :quit 退出):")
        
        while True:
            try:
                user_input = input("\n> ").strip()
                
                if not user_input:
                    continue
                
                if user_input == ':quit' or user_input == ':q':
                    break
                
                if user_input == ':history' or user_input == ':h':
                    self.show_history()
                    continue
                
                if user_input.startswith('!'):
                    # 原始数据
                    raw_data = user_input[1:]
                    self.send_raw(raw_data)
                    print(f"已发送原始数据: {raw_data}")
                else:
                    # 解析命令
                    if ':' in user_input:
                        parts = user_input.split(':', 1)
                        command = parts[0].strip()
                        args = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        command = user_input
                        args = ""
                    
                    # 发送命令
                    print(f"发送: #{command}:{args}|<checksum>\\n")
                    result = self.send_command(command, args)
                    
                    # 显示结果
                    if result.get('success') is True:
                        print(f"✓ ACK: {result.get('status', '')}")
                    elif result.get('success') is False:
                        print(f"✗ NACK: {result.get('reason', '')}")
                    else:
                        print(f"? {result.get('error', 'Unknown')}")
                
            except KeyboardInterrupt:
                print("\n\n中断")
                break
            except Exception as e:
                print(f"\n错误: {e}")
        
        print("\n调试器已退出")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='串口调试器')
    parser.add_argument('--port', '-p', required=True, help='串口路径')
    parser.add_argument('--baudrate', '-b', type=int, default=115200, help='波特率')
    
    args = parser.parse_args()
    
    # 创建调试器
    console = DebugConsole(args.port, args.baudrate)
    
    # 连接
    if not console.connect():
        sys.exit(1)
    
    try:
        # 进入交互模式
        console.interactive()
    finally:
        # 断开连接
        console.disconnect()


if __name__ == '__main__':
    main()
