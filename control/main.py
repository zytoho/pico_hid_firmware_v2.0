"""
高性能模拟人类行为控制系统 - 主程序
===================================
整合:
- engine_v2: 微观拟人引擎 (贝塞尔曲线 + 帧协议)
- vision_pipeline: 视觉闭环 (MSS + YOLO)
- agent_v2: 宏观 Agent (物理疲劳模型 + 异常检测)

使用方式:
    python main.py --config config.yaml
    python main.py --demo  # 运行演示任务
"""

import os
import sys
import time
import signal
import logging
import argparse
from pathlib import Path
from typing import Optional, Tuple

import yaml
import numpy as np

# 导入组件
from engine_v2 import HumanMotionEngine, HIDKey, Modifier
from vision_pipeline import VisionPipeline, ContinuousVisionThread, Detection
from agent_v2 import MacroAgent, BehaviorProfile, AgentState, AnomalyType


# ============================================================================
# 配置管理
# ============================================================================

DEFAULT_CONFIG = {
    "serial": {
        "port": "/dev/cu.usbserial-BG03FPHM",
        "baudrate": 115200,
        "ack_timeout": 0.1,
    },
    "vision": {
        "model_path": "yolov8n.pt",
        "window_title": "Moonlight",
        "target_region": None,  # [x, y, width, height] or null for fullscreen
        "fps_limit": 30,
    },
    "agent": {
        "fatigue_time_constant": 120.0,  # 分钟
        "focus_base": 0.85,
        "micro_break_probability": 0.02,
        "stuck_timeout": 30.0,
    },
    "behavior": {
        "typing_wpm": 60.0,
        "action_interval_base": 1.0,
    },
    "logging": {
        "level": "INFO",
        "file": "control_system.log",
    },
}


def load_config(config_path: Optional[str] = None) -> dict:
    """加载配置文件，缺失字段用默认值填充"""
    config = DEFAULT_CONFIG.copy()
    
    if config_path and Path(config_path).exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            user_config = yaml.safe_load(f)
            # 深度合并
            for section, values in user_config.items():
                if section in config and isinstance(config[section], dict):
                    config[section].update(values)
                else:
                    config[section] = values
    
    return config


# ============================================================================
# 任务定义
# ============================================================================

class Task:
    """任务基类"""
    def __init__(self, name: str):
        self.name = name
        self.completed = False
        self.failed = False
    
    def execute(self, system: 'ControlSystem') -> bool:
        """执行任务，返回是否成功"""
        raise NotImplementedError


class ClickTargetTask(Task):
    """点击视觉识别的目标"""
    def __init__(self, target_class: str, timeout: float = 10.0):
        super().__init__(f"Click_{target_class}")
        self.target_class = target_class
        self.timeout = timeout
    
    def execute(self, system: 'ControlSystem') -> bool:
        """找到目标并点击"""
        start_time = time.time()
        
        while time.time() - start_time < self.timeout:
            # 视觉检测
            target = system.vision.find_target(class_name=self.target_class)
            
            if target:
                # 移动到目标中心
                center = target.center
                system.engine.move_to(
                    center[0], center[1],
                    fatigue=system.agent.get_profile().fatigue,
                    focus=system.agent.get_profile().focus,
                )
                # 点击
                system.engine.click(button=1)
                system.agent.log_action()
                return True
            
            # 未找到，短暂等待
            time.sleep(0.1)
        
        # 超时
        system.agent.log_failure(f"Target '{self.target_class}' not found")
        return False


class TypeTextTask(Task):
    """在输入框中打字"""
    def __init__(self, text: str, click_position: Optional[Tuple[int, int]] = None):
        super().__init__("TypeText")
        self.text = text
        self.click_position = click_position
    
    def execute(self, system: 'ControlSystem') -> bool:
        """点击输入框 (可选) 并打字"""
        if self.click_position:
            system.engine.move_to(*self.click_position)
            system.engine.click()
            time.sleep(0.3)
        
        profile = system.agent.get_profile()
        system.engine.type_string(
            self.text,
            wpm=60.0 * (1.0 - profile.fatigue * 0.3),
            fatigue=profile.fatigue,
        )
        system.agent.log_action()
        return True


class KeyboardShortcutTask(Task):
    """执行键盘快捷键"""
    def __init__(self, modifier: int, key: int):
        super().__init__("KeyboardShortcut")
        self.modifier = modifier
        self.key = key
    
    def execute(self, system: 'ControlSystem') -> bool:
        system.engine.key_combo(self.modifier, self.key)
        system.agent.log_action()
        return True


# ============================================================================
# 主控制系统
# ============================================================================

class ControlSystem:
    """
    高性能模拟人类行为控制系统
    
    整合微观引擎、视觉流水线、宏观 Agent
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.running = False
        
        # 日志设置
        log_level = getattr(logging, config['logging']['level'])
        logging.basicConfig(
            level=log_level,
            format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(config['logging']['file'], encoding='utf-8'),
            ]
        )
        self.logger = logging.getLogger('ControlSystem')
        
        # 初始化组件
        self._init_engine()
        self._init_vision()
        self._init_agent()
        
        # 任务队列
        self.task_queue: list[Task] = []
    
    def _init_engine(self):
        """初始化微观引擎"""
        serial_cfg = self.config['serial']
        self.engine = HumanMotionEngine(
            serial_port=serial_cfg['port'],
            baudrate=serial_cfg['baudrate'],
            ack_timeout=serial_cfg['ack_timeout'],
        )
        self.logger.info(f"引擎初始化: {serial_cfg['port']}")
    
    def _init_vision(self):
        """初始化视觉流水线"""
        vision_cfg = self.config['vision']
        
        # 处理 target_region
        target_region = None
        if vision_cfg.get('target_region'):
            target_region = tuple(vision_cfg['target_region'])
        
        self.vision = VisionPipeline(
            model_path=vision_cfg['model_path'],
            window_title=vision_cfg['window_title'],
            target_region=target_region,
            fps_limit=vision_cfg['fps_limit'],
        )
        self.logger.info(f"视觉流水线初始化: {vision_cfg['model_path']}")
    
    def _init_agent(self):
        """初始化宏观 Agent"""
        agent_cfg = self.config['agent']
        
        self.agent = MacroAgent(
            fatigue_time_constant=agent_cfg['fatigue_time_constant'],
            focus_base=agent_cfg['focus_base'],
            micro_break_probability=agent_cfg['micro_break_probability'],
            stuck_timeout=agent_cfg['stuck_timeout'],
        )
        self.logger.info("宏观 Agent 初始化完成")
    
    def start(self):
        """启动系统"""
        self.logger.info("=== 系统启动 ===")
        
        # 连接引擎
        if not self.engine.connect():
            self.logger.error("引擎连接失败")
            return False
        
        # 启动 Agent
        self.agent.start()
        
        self.running = True
        self.logger.info("系统已启动")
        return True
    
    def stop(self):
        """停止系统"""
        self.logger.info("正在停止系统...")
        self.running = False
        
        # 停止 Agent
        self.agent.stop()
        
        # 断开引擎
        self.engine.disconnect()
        
        self.logger.info("系统已停止")
    
    def add_task(self, task: Task):
        """添加任务到队列"""
        self.task_queue.append(task)
        self.logger.info(f"任务已添加: {task.name}")
    
    def run_tasks(self):
        """执行任务队列"""
        if not self.running:
            self.logger.error("系统未启动")
            return
        
        self.logger.info(f"开始执行 {len(self.task_queue)} 个任务")
        
        while self.task_queue and self.running:
            task = self.task_queue.pop(0)
            self.logger.info(f"执行任务: {task.name}")
            
            try:
                success = task.execute(self)
                if success:
                    self.logger.info(f"任务完成: {task.name}")
                    task.completed = True
                else:
                    self.logger.warning(f"任务失败: {task.name}")
                    task.failed = True
            except Exception as e:
                self.logger.error(f"任务异常: {task.name} - {e}")
                task.failed = True
            
            # 任务间间隔 (根据 Agent 状态)
            if self.task_queue:
                profile = self.agent.get_profile()
                interval = profile.action_interval * (1.0 + profile.fatigue * 0.5)
                self.logger.debug(f"任务间隔: {interval:.2f}s")
                time.sleep(interval)
        
        self.logger.info("任务队列执行完毕")
    
    def get_status(self) -> dict:
        """获取系统状态"""
        return {
            "running": self.running,
            "engine": self.engine.get_stats(),
            "agent": self.agent.get_status(),
            "tasks_pending": len(self.task_queue),
        }


# ============================================================================
# 演示任务
# ============================================================================

def demo_task(system: ControlSystem):
    """演示任务序列"""
    logger = logging.getLogger('Demo')
    logger.info("=== 演示任务开始 ===")
    
    # 任务 1: 移动到屏幕中心并点击
    logger.info("任务 1: 移动到屏幕中心")
    system.engine.move_to(960, 540)  # 假设 1920x1080
    system.engine.click()
    system.agent.log_action()
    time.sleep(1)
    
    # 任务 2: 打字
    logger.info("任务 2: 打字输入")
    system.engine.type_string("Hello, World!")
    system.agent.log_action()
    time.sleep(0.5)
    
    # 任务 3: 快捷键 Ctrl+A (全选)
    logger.info("任务 3: 快捷键 Ctrl+A")
    system.engine.key_combo(Modifier.LEFT_CTRL, HIDKey.A)
    system.agent.log_action()
    time.sleep(0.5)
    
    # 任务 4: 视觉检测并点击 (示例: 检测 "person")
    logger.info("任务 4: 视觉检测 (person)")
    task = ClickTargetTask("person", timeout=5.0)
    system.add_task(task)
    system.run_tasks()
    
    # 任务 5: 滚动
    logger.info("任务 5: 向下滚动")
    system.engine.scroll(-5)
    system.agent.log_action()
    time.sleep(0.5)
    
    logger.info("=== 演示任务完成 ===")


# ============================================================================
# 主程序
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="高性能模拟人类行为控制系统")
    parser.add_argument('--config', type=str, help="配置文件路径 (YAML)")
    parser.add_argument('--demo', action='store_true', help="运行演示任务")
    parser.add_argument('--status', action='store_true', help="打印系统状态")
    args = parser.parse_args()
    
    # 加载配置
    config = load_config(args.config)
    
    # 创建系统
    system = ControlSystem(config)
    
    # 信号处理
    def signal_handler(sig, frame):
        print("\n接收到停止信号...")
        system.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 启动系统
    if not system.start():
        sys.exit(1)
    
    try:
        if args.demo:
            demo_task(system)
        elif args.status:
            import json
            print(json.dumps(system.get_status(), indent=2, ensure_ascii=False))
        else:
            # 默认行为: 等待任务输入 (可扩展为交互式 REPL)
            print("系统已启动，使用 Ctrl+C 停止")
            print("提示: 使用 --demo 运行演示任务")
            while system.running:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        system.stop()


if __name__ == '__main__':
    main()
