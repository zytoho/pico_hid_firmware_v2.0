#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
帧协议分析器
============
分析和统计帧协议的通信数据，包括：
- 解析日志文件
- 统计 ACK/NACK 比例
- 检测错误模式
- 生成统计报告

使用方法:
    # 从日志文件分析
    python frame_analyzer.py --input communication.log

    # 实时监控模式
    python frame_analyzer.py --port /dev/tty.usbserial-110

    # 生成报告
    python frame_analyzer.py --input log.txt --report stats.json
"""

import re
import json
import time
from collections import defaultdict, Counter
from datetime import datetime
from typing import Dict, List, Tuple
import argparse


class FrameAnalyzer:
    """帧协议分析器"""
    
    def __init__(self):
        self.frames = []
        self.stats = {
            'total_frames': 0,
            'tx_frames': 0,
            'rx_frames': 0,
            'ack_count': 0,
            'nack_count': 0,
            'unknown_count': 0,
            'checksum_errors': 0,
            'command_stats': defaultdict(int),
            'error_patterns': Counter(),
            'response_times': [],
        }
    
    def parse_log_file(self, filepath: str):
        """解析日志文件"""
        print(f"正在解析日志文件: {filepath}")
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        for line in lines:
            self._parse_line(line.strip())
        
        print(f"✓ 解析完成: {len(self.frames)} 条记录")
    
    def _parse_line(self, line: str):
        """解析单行日志"""
        if not line:
            return
        
        # 尝试匹配帧格式
        # TX: #A:100,200|XX\n
        # RX: +OK\n 或 -ERROR\n
        
        # 发送帧
        tx_match = re.match(r'#([A-Z]):([^|]*)\|([0-9A-F]{2})', line)
        if tx_match:
            command = tx_match.group(1)
            args = tx_match.group(2)
            checksum = tx_match.group(3)
            
            # 验证校验和
            payload = f"{command}:{args}"
            expected_checksum = f"{sum(payload.encode()) & 0xFF:02X}"
            
            frame = {
                'type': 'TX',
                'command': command,
                'args': args,
                'checksum': checksum,
                'checksum_valid': checksum == expected_checksum,
                'raw': line,
                'timestamp': time.time()
            }
            
            self.frames.append(frame)
            self.stats['tx_frames'] += 1
            self.stats['command_stats'][command] += 1
            
            if not frame['checksum_valid']:
                self.stats['checksum_errors'] += 1
            
            return
        
        # 响应帧 (ACK)
        if line.startswith('+'):
            frame = {
                'type': 'RX',
                'status': 'ACK',
                'data': line[1:],
                'raw': line,
                'timestamp': time.time()
            }
            self.frames.append(frame)
            self.stats['rx_frames'] += 1
            self.stats['ack_count'] += 1
            return
        
        # 响应帧 (NACK)
        if line.startswith('-'):
            frame = {
                'type': 'RX',
                'status': 'NACK',
                'data': line[1:],
                'raw': line,
                'timestamp': time.time()
            }
            self.frames.append(frame)
            self.stats['rx_frames'] += 1
            self.stats['nack_count'] += 1
            
            # 记录错误模式
            error_msg = line[1:].strip()
            self.stats['error_patterns'][error_msg] += 1
            return
        
        # 未知格式
        self.stats['unknown_count'] += 1
    
    def generate_report(self) -> Dict:
        """生成统计报告"""
        total = self.stats['tx_frames'] + self.stats['rx_frames']
        
        report = {
            'summary': {
                'total_frames': total,
                'tx_frames': self.stats['tx_frames'],
                'rx_frames': self.stats['rx_frames'],
            },
            'ack_statistics': {
                'ack_count': self.stats['ack_count'],
                'nack_count': self.stats['nack_count'],
                'ack_rate': self.stats['ack_count'] / max(1, self.stats['ack_count'] + self.stats['nack_count']) * 100,
            },
            'command_distribution': dict(self.stats['command_stats']),
            'checksum_errors': self.stats['checksum_errors'],
            'error_patterns': dict(self.stats['error_patterns'].most_common(10)),
        }
        
        return report
    
    def print_report(self):
        """打印统计报告"""
        report = self.generate_report()
        
        print("\n" + "="*60)
        print("帧协议统计报告")
        print("="*60)
        
        # 总体统计
        print("\n【总体统计】")
        print(f"  总帧数:     {report['summary']['total_frames']}")
        print(f"  发送帧:     {report['summary']['tx_frames']}")
        print(f"  接收帧:     {report['summary']['rx_frames']}")
        
        # ACK 统计
        print("\n【ACK 统计】")
        print(f"  ACK 成功:   {report['ack_statistics']['ack_count']}")
        print(f"  NACK 失败:  {report['ack_statistics']['nack_count']}")
        print(f"  成功率:     {report['ack_statistics']['ack_rate']:.2f}%")
        
        # 校验和错误
        print("\n【校验和】")
        print(f"  校验错误:   {report['checksum_errors']}")
        
        # 命令分布
        print("\n【命令分布】")
        for cmd, count in sorted(report['command_distribution'].items()):
            pct = count / max(1, self.stats['tx_frames']) * 100
            print(f"  {cmd}: {count:4d} ({pct:5.1f}%)")
        
        # 错误模式
        if report['error_patterns']:
            print("\n【常见错误】")
            for error, count in list(report['error_patterns'].items())[:5]:
                print(f"  {error}: {count} 次")
    
    def export_report(self, output_file: str):
        """导出报告到 JSON"""
        report = self.generate_report()
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 报告已导出: {output_file}")


def monitor_mode(port: str, baudrate: int = 115200):
    """实时监控模式"""
    import serial
    
    print(f"正在连接 {port} @ {baudrate} baud...")
    
    try:
        ser = serial.Serial(port, baudrate, timeout=1.0)
        print("✓ 已连接\n")
    except serial.SerialException as e:
        print(f"✗ 连接失败: {e}")
        return
    
    analyzer = FrameAnalyzer()
    
    print("="*60)
    print("帧协议实时监控 (按 Ctrl+C 停止)")
    print("="*60)
    print()
    
    try:
        while True:
            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                
                for line in data.split('\n'):
                    line = line.strip()
                    if line:
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"[{timestamp}] ← {line}")
                        
                        analyzer._parse_line(line)
            
            time.sleep(0.1)
            
    except KeyboardInterrupt:
        print("\n\n停止监控")
        analyzer.print_report()
    finally:
        ser.close()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='帧协议分析器')
    
    parser.add_argument('--input', '-i', type=str, help='输入日志文件')
    parser.add_argument('--port', '-p', type=str, help='串口路径 (实时监控模式)')
    parser.add_argument('--baudrate', '-b', type=int, default=115200, help='波特率')
    parser.add_argument('--report', '-r', type=str, help='输出报告文件 (JSON)')
    
    args = parser.parse_args()
    
    # 实时监控模式
    if args.port:
        monitor_mode(args.port, args.baudrate)
        return
    
    # 日志分析模式
    if args.input:
        analyzer = FrameAnalyzer()
        analyzer.parse_log_file(args.input)
        analyzer.print_report()
        
        if args.report:
            analyzer.export_report(args.report)
        
        return
    
    parser.print_help()


if __name__ == '__main__':
    main()
