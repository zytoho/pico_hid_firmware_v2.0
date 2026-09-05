#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
可视化调试界面
==============
实时渲染贝塞尔曲线轨迹和系统状态，包括：
- 鼠标移动轨迹可视化
- 目标检测框显示
- 系统状态仪表板
- 帧发送/响应时间线

使用方法:
    # 模拟模式（无需硬件）
    python visual_debugger.py --simulate

    # 实时监控模式
    python visual_debugger.py --port /dev/tty.usbserial-110
"""

import time
import math
import random
import threading
from typing import List, Tuple, Optional
from collections import deque

try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as patches
    from matplotlib.animation import FuncAnimation
    import matplotlib.gridspec as gridspec
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("警告: matplotlib 未安装，可视化功能不可用")
    print("安装: pip install matplotlib")


class TrajectoryVisualizer:
    """轨迹可视化器"""
    
    def __init__(self, max_points=500):
        self.max_points = max_points
        
        # 轨迹数据
        self.trajectory_x = deque(maxlen=max_points)
        self.trajectory_y = deque(maxlen=max_points)
        
        # 目标点
        self.targets = deque(maxlen=50)
        
        # 检测框
        self.detection_boxes = deque(maxlen=20)
        
        # 屏幕尺寸（假设）
        self.screen_width = 1920
        self.screen_height = 1080
    
    def add_point(self, x: int, y: int):
        """添加轨迹点"""
        self.trajectory_x.append(x)
        self.trajectory_y.append(y)
    
    def add_target(self, x: int, y: int, label: str = "Target"):
        """添加目标点"""
        self.targets.append({
            'x': x,
            'y': y,
            'label': label,
            'time': time.time()
        })
    
    def add_detection_box(self, x1: int, y1: int, x2: int, y2: int, label: str = "", confidence: float = 0.0):
        """添加检测框"""
        self.detection_boxes.append({
            'x1': x1, 'y1': y1,
            'x2': x2, 'y2': y2,
            'label': label,
            'confidence': confidence,
            'time': time.time()
        })
    
    def clear(self):
        """清空数据"""
        self.trajectory_x.clear()
        self.trajectory_y.clear()
        self.targets.clear()
        self.detection_boxes.clear()


class VisualDebugger:
    """可视化调试界面"""
    
    def __init__(self, simulator_mode=False):
        if not MATPLOTLIB_AVAILABLE:
            raise RuntimeError("matplotlib 未安装")
        
        self.simulator_mode = simulator_mode
        self.visualizer = TrajectoryVisualizer()
        
        # 系统状态
        self.system_stats = {
            'cpu': 0.0,
            'memory': 0.0,
            'e2e_latency': 0.0,
            'ack_rate': 100.0,
            'tasks_completed': 0,
        }
        
        # 运行状态
        self.running = False
        self.thread = None
        
        # 创建图形
        self._setup_figure()
    
    def _setup_figure(self):
        """设置图形布局"""
        self.fig = plt.figure(figsize=(14, 10))
        self.fig.suptitle('可视化调试界面', fontsize=16, fontweight='bold')
        
        # 使用 GridSpec 创建布局
        gs = gridspec.GridSpec(2, 2, hspace=0.3, wspace=0.3)
        
        # 1. 轨迹图（左上）
        self.ax_trajectory = self.fig.add_subplot(gs[0, 0])
        self.ax_trajectory.set_title('鼠标移动轨迹')
        self.ax_trajectory.set_xlabel('X (像素)')
        self.ax_trajectory.set_ylabel('Y (像素)')
        self.ax_trajectory.set_xlim(0, 1920)
        self.ax_trajectory.set_ylim(0, 1080)
        self.ax_trajectory.grid(True, alpha=0.3)
        self.ax_trajectory.invert_yaxis()  # Y 轴向下
        
        # 2. 系统状态图（右上）
        self.ax_stats = self.fig.add_subplot(gs[0, 1])
        self.ax_stats.set_title('系统状态')
        self.ax_stats.axis('off')
        
        # 3. 检测框图（左下）
        self.ax_detection = self.fig.add_subplot(gs[1, 0])
        self.ax_detection.set_title('目标检测')
        self.ax_detection.set_xlabel('X (像素)')
        self.ax_detection.set_ylabel('Y (像素)')
        self.ax_detection.set_xlim(0, 1920)
        self.ax_detection.set_ylim(0, 1080)
        self.ax_detection.grid(True, alpha=0.3)
        self.ax_detection.invert_yaxis()
        
        # 4. 时间线图（右下）
        self.ax_timeline = self.fig.add_subplot(gs[1, 1])
        self.ax_timeline.set_title('帧发送/响应时间线')
        self.ax_timeline.set_xlabel('时间 (s)')
        self.ax_timeline.set_ylabel('延迟 (ms)')
        self.ax_timeline.grid(True, alpha=0.3)
        
        # 初始化绘图对象
        self.trajectory_line, = self.ax_trajectory.plot([], [], 'b-', linewidth=2, label='轨迹')
        self.trajectory_points, = self.ax_trajectory.plot([], [], 'ro', markersize=3, label='当前位置')
        
        self.stats_text = self.ax_stats.text(0.1, 0.9, '', transform=self.ax_stats.transAxes,
                                             fontsize=12, verticalalignment='top',
                                             fontfamily='monospace',
                                             bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        self.timeline_x = deque(maxlen=100)
        self.timeline_y = deque(maxlen=100)
        self.timeline_line, = self.ax_timeline.plot([], [], 'g-', linewidth=1.5)
    
    def start(self):
        """启动可视化"""
        self.running = True
        
        # 启动数据更新线程
        if self.simulator_mode:
            self.thread = threading.Thread(target=self._simulate_data, daemon=True)
            self.thread.start()
        
        # 启动动画
        self.ani = FuncAnimation(self.fig, self._update, interval=100, blit=False)
        plt.show()
    
    def stop(self):
        """停止可视化"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
        plt.close(self.fig)
    
    def _update(self, frame):
        """更新动画帧"""
        # 更新轨迹
        if len(self.visualizer.trajectory_x) > 0:
            self.trajectory_line.set_data(
                list(self.visualizer.trajectory_x),
                list(self.visualizer.trajectory_y)
            )
            self.trajectory_points.set_data(
                [self.visualizer.trajectory_x[-1]],
                [self.visualizer.trajectory_y[-1]]
            )
        
        # 更新检测框
        self.ax_detection.clear()
        self.ax_detection.set_title('目标检测')
        self.ax_detection.set_xlabel('X (像素)')
        self.ax_detection.set_ylabel('Y (像素)')
        self.ax_detection.set_xlim(0, 1920)
        self.ax_detection.set_ylim(0, 1080)
        self.ax_detection.grid(True, alpha=0.3)
        self.ax_detection.invert_yaxis()
        
        for box in self.visualizer.detection_boxes:
            rect = patches.Rectangle(
                (box['x1'], box['y1']),
                box['x2'] - box['x1'],
                box['y2'] - box['y1'],
                linewidth=2,
                edgecolor='r',
                facecolor='none'
            )
            self.ax_detection.add_patch(rect)
            self.ax_detection.text(
                box['x1'], box['y1'] - 10,
                f"{box['label']} {box['confidence']:.2f}",
                fontsize=10,
                bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.7)
            )
        
        # 更新系统状态文本
        stats_str = f"""
CPU:       {self.system_stats['cpu']:5.1f}%
内存:      {self.system_stats['memory']:5.1f}%
延迟:      {self.system_stats['e2e_latency']:5.1f} ms
ACK 率:    {self.system_stats['ack_rate']:5.1f}%
完成:      {self.system_stats['tasks_completed']}
        """.strip()
        self.stats_text.set_text(stats_str)
        
        # 更新时间线
        if len(self.timeline_x) > 0:
            self.timeline_line.set_data(
                list(self.timeline_x),
                list(self.timeline_y)
            )
            self.ax_timeline.set_xlim(min(self.timeline_x), max(self.timeline_x) + 1)
            self.ax_timeline.set_ylim(0, max(self.timeline_y) * 1.2)
        
        return [self.trajectory_line, self.trajectory_points, self.stats_text, self.timeline_line]
    
    def _simulate_data(self):
        """模拟数据生成"""
        t = 0
        
        while self.running:
            # 模拟贝塞尔曲线轨迹
            progress = (math.sin(t / 10) + 1) / 2
            x = int(progress * 1920)
            y = int(540 + 200 * math.sin(t / 5))
            
            self.visualizer.add_point(x, y)
            
            # 模拟系统状态
            self.system_stats['cpu'] = 20 + 10 * math.sin(t / 20) + random.uniform(-5, 5)
            self.system_stats['memory'] = 45 + 5 * math.sin(t / 30) + random.uniform(-2, 2)
            self.system_stats['e2e_latency'] = 10 + 5 * math.sin(t / 15) + random.uniform(-2, 2)
            self.system_stats['ack_rate'] = 98 + random.uniform(-2, 0)
            
            if random.random() > 0.95:
                self.system_stats['tasks_completed'] += 1
            
            # 更新时间线
            self.timeline_x.append(t)
            self.timeline_y.append(self.system_stats['e2e_latency'])
            
            # 模拟检测框
            if random.random() > 0.98:
                bx = random.randint(100, 1800)
                by = random.randint(100, 900)
                self.visualizer.add_detection_box(
                    bx, by, bx + 100, by + 80,
                    label="object",
                    confidence=random.uniform(0.7, 0.99)
                )
            
            t += 0.1
            time.sleep(0.1)


def main():
    """主函数"""
    import argparse
    
    if not MATPLOTLIB_AVAILABLE:
        print("错误: matplotlib 未安装")
        print("请先安装: pip install matplotlib")
        return
    
    parser = argparse.ArgumentParser(description='可视化调试界面')
    parser.add_argument('--simulate', action='store_true', help='模拟模式（无需硬件）')
    parser.add_argument('--port', '-p', type=str, help='串口路径（实时监控模式）')
    
    args = parser.parse_args()
    
    # 默认使用模拟模式
    simulator_mode = args.simulate or not args.port
    
    print("="*60)
    print("可视化调试界面")
    print("="*60)
    
    if simulator_mode:
        print("模式: 模拟 (无需硬件)")
    else:
        print(f"模式: 实时监控 ({args.port})")
    
    print("\n关闭窗口退出程序\n")
    
    # 创建调试器
    debugger = VisualDebugger(simulator_mode=simulator_mode)
    
    try:
        debugger.start()
    except KeyboardInterrupt:
        print("\n正在关闭...")
        debugger.stop()
    
    print("已退出")


if __name__ == '__main__':
    main()
