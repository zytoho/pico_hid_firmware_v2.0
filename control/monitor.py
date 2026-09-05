#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
性能监控工具
============
实时监控系统的各项性能指标，包括：
- CPU/内存占用
- 端到端延迟（截图→推理→指令→响应）
- 任务成功率
- 帧发送/响应统计
- 系统健康状态

使用方法:
    # 启动监控（实时显示）
    python monitor.py

    # 输出到文件
    python monitor.py --output performance.csv

    # 监控特定进程
    python monitor.py --pid 12345

    # 可视化模式（需要 matplotlib）
    python monitor.py --visual
"""

import time
import psutil
import threading
import csv
import json
from collections import deque, defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Callable
import argparse


class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self, max_samples=1000):
        self.max_samples = max_samples
        
        # 时间戳队列（用于计算延迟）
        self.screenshot_times = deque(maxlen=max_samples)
        self.inference_times = deque(maxlen=max_samples)
        self.command_times = deque(maxlen=max_samples)
        self.response_times = deque(maxlen=max_samples)
        
        # 端到端延迟（毫秒）
        self.e2e_latencies = deque(maxlen=max_samples)
        
        # 帧统计
        self.frames_sent = 0
        self.ack_received = 0
        self.ack_failed = 0
        
        # 任务统计
        self.tasks_total = 0
        self.tasks_success = 0
        self.tasks_failed = 0
        
        # 系统资源
        self.cpu_usage = deque(maxlen=max_samples)
        self.memory_usage = deque(maxlen=max_samples)
        self.memory_mb = deque(maxlen=max_samples)
        
        # 启动时间
        self.start_time = time.time()
        
        # 锁
        self.lock = threading.Lock()
    
    def record_screenshot(self):
        """记录截图时间戳"""
        with self.lock:
            self.screenshot_times.append(time.time())
    
    def record_inference(self):
        """记录推理完成时间戳"""
        with self.lock:
            self.inference_times.append(time.time())
    
    def record_command_sent(self):
        """记录指令发送时间戳"""
        with self.lock:
            self.command_times.append(time.time())
            self.frames_sent += 1
    
    def record_response_received(self, success=True):
        """记录响应接收时间戳"""
        with self.lock:
            now = time.time()
            self.response_times.append(now)
            
            if success:
                self.ack_received += 1
            else:
                self.ack_failed += 1
            
            # 计算端到端延迟
            if self.screenshot_times:
                e2e = (now - self.screenshot_times[-1]) * 1000  # 毫秒
                self.e2e_latencies.append(e2e)
    
    def record_task(self, success=True):
        """记录任务结果"""
        with self.lock:
            self.tasks_total += 1
            if success:
                self.tasks_success += 1
            else:
                self.tasks_failed += 1
    
    def update_system_metrics(self):
        """更新系统资源指标"""
        with self.lock:
            cpu = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            
            self.cpu_usage.append(cpu)
            self.memory_usage.append(mem.percent)
            self.memory_mb.append(mem.used / 1024 / 1024)
    
    def get_snapshot(self) -> Dict:
        """获取当前性能快照"""
        with self.lock:
            # 计算平均延迟
            avg_e2e = sum(self.e2e_latencies) / len(self.e2e_latencies) if self.e2e_latencies else 0
            max_e2e = max(self.e2e_latencies) if self.e2e_latencies else 0
            min_e2e = min(self.e2e_latencies) if self.e2e_latencies else 0
            
            # 成功率
            success_rate = (self.ack_received / self.frames_sent * 100) if self.frames_sent > 0 else 0
            task_success_rate = (self.tasks_success / self.tasks_total * 100) if self.tasks_total > 0 else 0
            
            # 当前系统资源
            current_cpu = self.cpu_usage[-1] if self.cpu_usage else 0
            current_mem = self.memory_usage[-1] if self.memory_usage else 0
            current_mem_mb = self.memory_mb[-1] if self.memory_mb else 0
            
            # 运行时间
            uptime = time.time() - self.start_time
            
            return {
                "timestamp": datetime.now().isoformat(),
                "uptime_seconds": uptime,
                
                # 系统资源
                "cpu_percent": current_cpu,
                "memory_percent": current_mem,
                "memory_mb": current_mem_mb,
                
                # 延迟（毫秒）
                "e2e_latency_avg_ms": avg_e2e,
                "e2e_latency_max_ms": max_e2e,
                "e2e_latency_min_ms": min_e2e,
                
                # 帧统计
                "frames_sent": self.frames_sent,
                "ack_received": self.ack_received,
                "ack_failed": self.ack_failed,
                "ack_success_rate": success_rate,
                
                # 任务统计
                "tasks_total": self.tasks_total,
                "tasks_success": self.tasks_success,
                "tasks_failed": self.tasks_failed,
                "task_success_rate": task_success_rate,
                
                # 队列深度
                "screenshot_queue": len(self.screenshot_times),
                "inference_queue": len(self.inference_times),
                "command_queue": len(self.command_times),
                "response_queue": len(self.response_times),
            }
    
    def reset(self):
        """重置所有指标"""
        with self.lock:
            self.screenshot_times.clear()
            self.inference_times.clear()
            self.command_times.clear()
            self.response_times.clear()
            self.e2e_latencies.clear()
            self.cpu_usage.clear()
            self.memory_usage.clear()
            self.memory_mb.clear()
            
            self.frames_sent = 0
            self.ack_received = 0
            self.ack_failed = 0
            self.tasks_total = 0
            self.tasks_success = 0
            self.tasks_failed = 0
            self.start_time = time.time()


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, metrics: Optional[PerformanceMetrics] = None, 
                 update_interval=1.0, 
                 csv_output: Optional[str] = None,
                 visual_mode=False):
        self.metrics = metrics or PerformanceMetrics()
        self.update_interval = update_interval
        self.csv_output = csv_output
        self.visual_mode = visual_mode
        
        self.running = False
        self.thread = None
        self.csv_file = None
        self.csv_writer = None
        
        # 可视化数据
        if visual_mode:
            try:
                import matplotlib.pyplot as plt
                from matplotlib.animation import FuncAnimation
                self.plt = plt
                self.visual_data = {
                    'cpu': [],
                    'memory': [],
                    'latency': [],
                    'time': [],
                }
            except ImportError:
                print("警告: matplotlib 未安装，禁用可视化模式")
                self.visual_mode = False
    
    def start(self):
        """启动监控"""
        self.running = True
        
        # 初始化 CSV 文件
        if self.csv_output:
            self.csv_file = open(self.csv_output, 'w', newline='')
            self.csv_writer = csv.writer(self.csv_file)
            # 写入表头
            self.csv_writer.writerow([
                'timestamp', 'cpu_percent', 'memory_percent', 'memory_mb',
                'e2e_latency_avg_ms', 'e2e_latency_max_ms',
                'frames_sent', 'ack_received', 'ack_success_rate',
                'tasks_total', 'tasks_success', 'task_success_rate'
            ])
        
        # 启动更新线程
        self.thread = threading.Thread(target=self._update_loop, daemon=True)
        self.thread.start()
        
        # 启动可视化
        if self.visual_mode:
            self._start_visualization()
        else:
            self._start_console_display()
    
    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        
        if self.csv_file:
            self.csv_file.close()
        
        if self.visual_mode:
            self.plt.close()
    
    def _update_loop(self):
        """后台更新循环"""
        while self.running:
            # 更新系统指标
            self.metrics.update_system_metrics()
            
            # 获取快照
            snapshot = self.metrics.get_snapshot()
            
            # 写入 CSV
            if self.csv_writer:
                self.csv_writer.writerow([
                    snapshot['timestamp'],
                    snapshot['cpu_percent'],
                    snapshot['memory_percent'],
                    snapshot['memory_mb'],
                    snapshot['e2e_latency_avg_ms'],
                    snapshot['e2e_latency_max_ms'],
                    snapshot['frames_sent'],
                    snapshot['ack_received'],
                    snapshot['ack_success_rate'],
                    snapshot['tasks_total'],
                    snapshot['tasks_success'],
                    snapshot['task_success_rate'],
                ])
                self.csv_file.flush()
            
            # 更新可视化数据
            if self.visual_mode:
                self.visual_data['cpu'].append(snapshot['cpu_percent'])
                self.visual_data['memory'].append(snapshot['memory_percent'])
                self.visual_data['latency'].append(snapshot['e2e_latency_avg_ms'])
                self.visual_data['time'].append(snapshot['uptime_seconds'])
                
                # 保持最近 100 个数据点
                max_points = 100
                for key in self.visual_data:
                    if len(self.visual_data[key]) > max_points:
                        self.visual_data[key] = self.visual_data[key][-max_points:]
            
            time.sleep(self.update_interval)
    
    def _start_console_display(self):
        """控制台实时显示"""
        print("\n" + "="*60)
        print("性能监控启动")
        print("="*60)
        print("按 Ctrl+C 停止\n")
        
        try:
            while self.running:
                snapshot = self.metrics.get_snapshot()
                
                # 清屏
                print("\033[2J\033[H", end="")
                
                print("="*60)
                print("性能监控 (按 Ctrl+C 停止)")
                print("="*60)
                print(f"\n运行时间: {snapshot['uptime_seconds']:.1f}s")
                
                # 系统资源
                print("\n【系统资源】")
                print(f"  CPU:    {snapshot['cpu_percent']:5.1f}% ", end="")
                self._print_bar(snapshot['cpu_percent'], 50)
                print(f"  内存:   {snapshot['memory_percent']:5.1f}% ({snapshot['memory_mb']:.0f} MB) ", end="")
                self._print_bar(snapshot['memory_percent'], 50)
                
                # 延迟
                print("\n【端到端延迟】")
                print(f"  平均:   {snapshot['e2e_latency_avg_ms']:6.1f} ms")
                print(f"  最大:   {snapshot['e2e_latency_max_ms']:6.1f} ms")
                print(f"  最小:   {snapshot['e2e_latency_min_ms']:6.1f} ms")
                
                # 帧统计
                print("\n【帧统计】")
                print(f"  发送:   {snapshot['frames_sent']}")
                print(f"  成功:   {snapshot['ack_received']}")
                print(f"  失败:   {snapshot['ack_failed']}")
                print(f"  成功率: {snapshot['ack_success_rate']:5.1f}% ", end="")
                self._print_bar(snapshot['ack_success_rate'], 50)
                
                # 任务统计
                print("\n【任务统计】")
                print(f"  总数:   {snapshot['tasks_total']}")
                print(f"  成功:   {snapshot['tasks_success']}")
                print(f"  失败:   {snapshot['tasks_failed']}")
                print(f"  成功率: {snapshot['task_success_rate']:5.1f}% ", end="")
                self._print_bar(snapshot['task_success_rate'], 50)
                
                if self.csv_output:
                    print(f"\n数据输出: {self.csv_output}")
                
                time.sleep(self.update_interval)
                
        except KeyboardInterrupt:
            print("\n\n监控已停止")
            self.stop()
    
    def _print_bar(self, value, max_value, width=30):
        """打印进度条"""
        filled = int(width * value / max_value)
        bar = "█" * filled + "░" * (width - filled)
        print(f"[{bar}]", end="")
    
    def _start_visualization(self):
        """启动可视化窗口"""
        fig, axes = self.plt.subplots(2, 2, figsize=(12, 8))
        fig.suptitle('性能监控', fontsize=16)
        
        def update(frame):
            if not self.visual_data['time']:
                return
            
            # CPU 和内存
            ax1 = axes[0, 0]
            ax1.clear()
            ax1.plot(self.visual_data['time'], self.visual_data['cpu'], 'r-', label='CPU %')
            ax1.plot(self.visual_data['time'], self.visual_data['memory'], 'b-', label='Memory %')
            ax1.set_ylim(0, 100)
            ax1.set_xlabel('时间 (s)')
            ax1.set_ylabel('使用率 (%)')
            ax1.set_title('系统资源')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # 延迟
            ax2 = axes[0, 1]
            ax2.clear()
            ax2.plot(self.visual_data['time'], self.visual_data['latency'], 'g-')
            ax2.set_xlabel('时间 (s)')
            ax2.set_ylabel('延迟 (ms)')
            ax2.set_title('端到端延迟')
            ax2.grid(True, alpha=0.3)
            
            # 任务统计
            snapshot = self.metrics.get_snapshot()
            ax3 = axes[1, 0]
            ax3.clear()
            tasks = [snapshot['tasks_success'], snapshot['tasks_failed']]
            if sum(tasks) > 0:
                ax3.pie(tasks, labels=['成功', '失败'], autopct='%1.1f%%', 
                       colors=['green', 'red'], startangle=90)
            ax3.set_title(f"任务统计 (总数: {snapshot['tasks_total']})")
            
            # 帧统计
            ax4 = axes[1, 1]
            ax4.clear()
            frames = [snapshot['ack_received'], snapshot['ack_failed']]
            if sum(frames) > 0:
                ax4.pie(frames, labels=['ACK成功', 'ACK失败'], autopct='%1.1f%%',
                       colors=['blue', 'orange'], startangle=90)
            ax4.set_title(f"帧统计 (总数: {snapshot['frames_sent']})")
            
            self.plt.tight_layout()
        
        ani = self.plt.FuncAnimation(fig, update, interval=1000)
        self.plt.show()


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='性能监控工具')
    parser.add_argument('--output', '-o', type=str, help='CSV 输出文件路径')
    parser.add_argument('--interval', '-i', type=float, default=1.0, help='更新间隔（秒）')
    parser.add_argument('--visual', '-v', action='store_true', help='可视化模式')
    parser.add_argument('--pid', type=int, help='监控特定进程 PID')
    
    args = parser.parse_args()
    
    # 创建监控器
    metrics = PerformanceMetrics()
    monitor = PerformanceMonitor(
        metrics=metrics,
        update_interval=args.interval,
        csv_output=args.output,
        visual_mode=args.visual
    )
    
    # 模拟数据（实际使用时由应用调用 record_* 方法）
    def simulate_data():
        """模拟性能数据"""
        import random
        
        while monitor.running:
            # 模拟截图
            metrics.record_screenshot()
            time.sleep(0.05)
            
            # 模拟推理
            metrics.record_inference()
            time.sleep(random.uniform(0.02, 0.05))
            
            # 模拟发送指令
            metrics.record_command_sent()
            time.sleep(0.01)
            
            # 模拟响应
            success = random.random() > 0.05  # 95% 成功率
            metrics.record_response_received(success)
            
            # 模拟任务
            if random.random() > 0.8:
                task_success = random.random() > 0.1
                metrics.record_task(task_success)
            
            time.sleep(0.1)
    
    # 启动监控
    monitor.start()
    
    # 启动模拟数据生成
    sim_thread = threading.Thread(target=simulate_data, daemon=True)
    sim_thread.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        monitor.stop()
        print("\n监控已停止")


if __name__ == '__main__':
    main()
