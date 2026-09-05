#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏自动化战斗 Agent
===================
整合 Pico HID 硬件控制 + 游戏视觉模块，实现：
- 自动寻怪并攻击（优先 BOSS > 精英 > 普通怪）
- 自动拾取掉落物
- 自动检测血量/蓝量并补血补蓝
- 智能战斗循环

使用方法:
    python game_agent.py --port /dev/ttyUSB0
    
    # 或自定义配置
    python game_agent.py \
        --port /dev/ttyUSB0 \
        --model game_yolo.pt \
        --player-pos 960,540 \
        --hp-region 50,50,200,20 \
        --mp-region 50,80,200,20 \
        --hp-key 1 \
        --mp-key 2 \
        --pickup-key f
"""

import time
import math
import argparse
import threading
import sys
import signal
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum

# 导入项目模块
from engine_v2 import HumanMotionEngine
from game_vision import GameVision, GameEntity, EntityType, HealthInfo


# ===========================================================================
# HID 键码定义 (用于快捷键绑定)
# ===========================================================================

HID_KEYS = {
    '1': 0x1E, '2': 0x1F, '3': 0x20, '4': 0x21, '5': 0x22,
    '6': 0x23, '7': 0x24, '8': 0x25, '9': 0x26, '0': 0x27,
    'q': 0x14, 'e': 0x08, 'r': 0x15, 'f': 0x09,
    'tab': 0x2B, 'space': 0x2C, 'enter': 0x28,
}


class CombatState(Enum):
    """战斗状态"""
    IDLE = "idle"                    # 空闲
    SEARCHING = "searching"          # 搜索目标
    MOVING_TO_TARGET = "moving"      # 移动到目标
    ATTACKING = "attacking"          # 攻击中
    PICKING_UP = "picking_up"        # 拾取中
    HEALING = "healing"              # 补血/蓝
    RETREATING = "retreating"        # 撤退


@dataclass
class CombatConfig:
    """战斗配置"""
    # 快捷键
    hp_key: str = '1'                # 补血快捷键
    mp_key: str = '2'                # 补蓝快捷键
    pickup_key: str = 'f'            # 拾取快捷键
    attack_key: str = '1'            # 攻击快捷键（鼠标左键也可）
    
    # 攻击方式
    use_mouse_attack: bool = True    # 使用鼠标左键攻击
    use_skill_rotation: bool = False # 使用技能循环
    
    # 战斗参数
    attack_range: float = 150.0      # 攻击范围（像素距离）
    pickup_range: float = 200.0      # 拾取范围（像素距离）
    search_interval: float = 0.3     # 搜索间隔（秒）
    attack_cooldown: float = 0.8     # 攻击冷却（秒）
    
    # 血量阈值
    hp_heal_threshold: float = 30.0  # 血量低于此值自动补血
    mp_heal_threshold: float = 20.0  # 蓝量低于此值自动补蓝
    heal_cooldown: float = 3.0       # 补血/蓝冷却（秒）
    
    # 安全设置
    max_consecutive_fails: int = 10  # 连续失败次数上限
    retreat_distance: float = 300.0  # 撤退距离
    idle_after_kill: float = 0.5     # 击杀后等待时间


class GameCombatAgent:
    """游戏自动化战斗 Agent"""
    
    def __init__(
        self,
        engine: HumanMotionEngine,
        vision: GameVision,
        config: CombatConfig = None
    ):
        """
        初始化战斗 Agent
        
        Args:
            engine: Pico HID 引擎
            vision: 游戏视觉系统
            config: 战斗配置
        """
        self.engine = engine
        self.vision = vision
        self.config = config or CombatConfig()
        
        # 状态
        self.state = CombatState.IDLE
        self.running = False
        self.combat_loop_count = 0
        
        # 统计
        self.stats = {
            'monsters_killed': 0,
            'items_picked': 0,
            'hp_heals': 0,
            'mp_heals': 0,
            'total_attacks': 0,
            'start_time': None,
            'last_attack_time': 0,
            'last_heal_time': 0,
            'consecutive_fails': 0,
        }
        
        # 锁
        self.lock = threading.Lock()
    
    def start(self):
        """启动战斗循环"""
        self.running = True
        self.stats['start_time'] = time.time()
        print(f"\n{'='*60}")
        print(f"  游戏自动化战斗 Agent 已启动")
        print(f"{'='*60}")
        print(f"  状态: {self.state.value}")
        print(f"  攻击冷却: {self.config.attack_cooldown}s")
        print(f"  拾取范围: {self.config.pickup_range}px")
        print(f"  血量阈值: {self.config.hp_heal_threshold}%")
        print(f"  蓝量阈值: {self.config.mp_heal_threshold}%")
        print(f"  按 Ctrl+C 停止")
        print(f"{'='*60}\n")
        
        try:
            self._combat_loop()
        except KeyboardInterrupt:
            print("\n\n[Agent] 用户中断")
        finally:
            self.stop()
    
    def stop(self):
        """停止战斗循环"""
        self.running = False
        self.state = CombatState.IDLE
        self._print_summary()
    
    def _combat_loop(self):
        """主战斗循环"""
        while self.running:
            try:
                # 1. 分析当前帧
                analysis = self.vision.analyze_frame()
                
                if 'error' in analysis:
                    print(f"[Agent] 分析失败: {analysis['error']}")
                    time.sleep(self.config.search_interval)
                    continue
                
                monsters = analysis['monsters']
                loots = analysis['loots']
                health = analysis['health']
                decision = analysis['decision']
                
                # 2. 执行决策
                action = decision['action']
                
                if action == 'heal_hp':
                    self._do_heal_hp()
                
                elif action == 'heal_mp':
                    self._do_heal_mp()
                
                elif action == 'pickup':
                    target = decision['target']
                    self._do_pickup(target)
                
                elif action == 'attack':
                    target = decision['target']
                    self._do_attack(target)
                
                else:
                    # idle - 搜索目标
                    self.state = CombatState.SEARCHING
                
                # 3. 更新统计并打印状态
                self.combat_loop_count += 1
                if self.combat_loop_count % 10 == 0:
                    self._print_status(analysis)
                
                # 4. 帧率控制
                time.sleep(self.config.search_interval)
                
            except Exception as e:
                print(f"[Agent] 循环异常: {e}")
                self.stats['consecutive_fails'] += 1
                
                if self.stats['consecutive_fails'] >= self.config.max_consecutive_fails:
                    print(f"[Agent] 连续失败 {self.stats['consecutive_fails']} 次，停止")
                    break
                
                time.sleep(1.0)
    
    def _do_attack(self, target: GameEntity):
        """执行攻击"""
        now = time.time()
        
        # 检查冷却
        if now - self.stats['last_attack_time'] < self.config.attack_cooldown:
            return
        
        self.state = CombatState.ATTACKING
        
        # 检查距离
        if target.distance > self.config.attack_range:
            # 需要移动到攻击范围
            self.state = CombatState.MOVING_TO_TARGET
            attack_x, attack_y = target.attack_point
            self.engine.move_to(attack_x, attack_y, curve_intensity=0.2)
            time.sleep(0.1)  # 等待移动完成
        
        # 执行攻击
        if self.config.use_mouse_attack:
            self.engine.click(1)  # 鼠标左键
        else:
            # 使用技能快捷键
            skill_keys = ['1', '2', '3', '4']
            skill_idx = self.stats['total_attacks'] % len(skill_keys)
            key = skill_keys[skill_idx]
            self.engine.press_key(HID_KEYS[key])
        
        self.stats['total_attacks'] += 1
        self.stats['last_attack_time'] = now
        self.stats['consecutive_fails'] = 0
        
        # 等待攻击动画
        time.sleep(0.2)
    
    def _do_pickup(self, target: GameEntity):
        """执行拾取"""
        self.state = CombatState.PICKING_UP
        
        # 移动到掉落物位置
        cx, cy = target.center
        self.engine.move_to(cx, cy, curve_intensity=0.3)
        time.sleep(0.2)
        
        # 按拾取键
        pickup_key = HID_KEYS.get(self.config.pickup_key, 0x09)  # 默认 'f'
        self.engine.press_key(pickup_key)
        
        self.stats['items_picked'] += 1
        self.stats['consecutive_fails'] = 0
        
        # 等待拾取动画
        time.sleep(0.3)
    
    def _do_heal_hp(self):
        """执行补血"""
        now = time.time()
        
        # 检查冷却
        if now - self.stats['last_heal_time'] < self.config.heal_cooldown:
            return
        
        self.state = CombatState.HEALING
        
        hp_key = HID_KEYS.get(self.config.hp_key, 0x1E)  # 默认 '1'
        self.engine.press_key(hp_key)
        
        self.stats['hp_heals'] += 1
        self.stats['last_heal_time'] = now
        self.stats['consecutive_fails'] = 0
        
        print(f"[Agent] 补血! HP: {self.vision.get_hp_percent():.1f}%")
        
        # 等待补血动画
        time.sleep(0.5)
    
    def _do_heal_mp(self):
        """执行补蓝"""
        now = time.time()
        
        # 检查冷却
        if now - self.stats['last_heal_time'] < self.config.heal_cooldown:
            return
        
        self.state = CombatState.HEALING
        
        mp_key = HID_KEYS.get(self.config.mp_key, 0x1F)  # 默认 '2'
        self.engine.press_key(mp_key)
        
        self.stats['mp_heals'] += 1
        self.stats['last_heal_time'] = now
        self.stats['consecutive_fails'] = 0
        
        print(f"[Agent] 补蓝! MP: {self.vision.get_mp_percent():.1f}%")
        
        # 等待补蓝动画
        time.sleep(0.5)
    
    def _print_status(self, analysis: Dict):
        """打印状态信息"""
        monsters = analysis['monsters']
        loots = analysis['loots']
        health = analysis['health']
        
        uptime = time.time() - self.stats['start_time']
        minutes = int(uptime // 60)
        seconds = int(uptime % 60)
        
        print(f"\n[{minutes:02d}:{seconds:02d}] "
              f"状态={self.state.value:12s} | "
              f"怪物={len(monsters):2d} | "
              f"掉落={len(loots):2d} | "
              f"HP={health.hp_percent:5.1f}% | "
              f"MP={health.mp_percent:5.1f}% | "
              f"击杀={self.stats['monsters_killed']} | "
              f"拾取={self.stats['items_picked']} | "
              f"FPS={analysis.get('fps', 0):.0f}")
    
    def _print_summary(self):
        """打印战斗总结"""
        uptime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        minutes = int(uptime // 60)
        seconds = int(uptime % 60)
        
        print(f"\n{'='*60}")
        print(f"  战斗总结 (运行时间: {minutes}分{seconds}秒)")
        print(f"{'='*60}")
        print(f"  总攻击次数:   {self.stats['total_attacks']}")
        print(f"  击杀怪物:     {self.stats['monsters_killed']}")
        print(f"  拾取物品:     {self.stats['items_picked']}")
        print(f"  补血次数:     {self.stats['hp_heals']}")
        print(f"  补蓝次数:     {self.stats['mp_heals']}")
        print(f"{'='*60}\n")


# ===========================================================================
# 无需硬件的模拟战斗 Agent (测试用)
# ===========================================================================

class SimulatedEngine:
    """模拟引擎（不需要 Pico 硬件）"""
    
    def __init__(self):
        self.cursor_x = 960
        self.cursor_y = 540
        self.connected = True
        self.command_count = 0
    
    def connect(self):
        return True
    
    def disconnect(self):
        pass
    
    def move_to(self, x, y, curve_intensity=0.3):
        self.cursor_x = x
        self.cursor_y = y
        self.command_count += 1
    
    def click(self, button=1):
        self.command_count += 1
    
    def press_key(self, key, modifiers=None):
        self.command_count += 1
    
    def heartbeat(self):
        return True


class SimulatedVision:
    """模拟视觉系统（不需要真实 YOLO 模型）"""
    
    def __init__(self):
        from game_vision import HealthInfo, GameEntity, EntityType
        self.health_info = HealthInfo(hp_percent=85.0, mp_percent=60.0)
        self.frame_count = 0
        self._simulated_entities = []
        self._generate_simulated_entities()
    
    def _generate_simulated_entities(self):
        """生成模拟实体"""
        from game_vision import GameEntity, EntityType
        import random
        
        # 模拟一个普通怪
        self._simulated_entities.append(GameEntity(
            entity_type=EntityType.NORMAL_MONSTER,
            class_name='normal_monster',
            confidence=0.92,
            bbox=(800, 400, 860, 480),
            center=(830, 440),
            distance=180.0,
            attack_point=(830, 480)
        ))
        
        # 模拟一个掉落物
        self._simulated_entities.append(GameEntity(
            entity_type=EntityType.LOOT,
            class_name='loot',
            confidence=0.88,
            bbox=(1000, 500, 1040, 540),
            center=(1020, 520),
            distance=100.0,
            attack_point=(1020, 540)
        ))
    
    def analyze_frame(self):
        """模拟分析"""
        import random
        
        self.frame_count += 1
        
        from game_vision import HealthInfo
        # 模拟血量波动
        hp = 85.0 + 10 * math.sin(self.frame_count * 0.1) + random.uniform(-3, 3)
        mp = 60.0 + 15 * math.sin(self.frame_count * 0.05) + random.uniform(-2, 2)
        
        health = HealthInfo(
            hp_percent=max(0, min(100, hp)),
            mp_percent=max(0, min(100, mp)),
            hp_low=hp < 30,
            mp_low=mp < 20
        )
        
        monsters = [e for e in self._simulated_entities 
                   if e.entity_type in [EntityType.NORMAL_MONSTER, EntityType.ELITE_MONSTER, EntityType.BOSS]]
        loots = [e for e in self._simulated_entities if e.entity_type == EntityType.LOOT]
        
        decision = {'action': 'idle', 'target': None, 'reason': '无目标'}
        
        if health.hp_low:
            decision = {'action': 'heal_hp', 'target': None, 'reason': f'HP低({hp:.0f}%)'}
        elif health.mp_low:
            decision = {'action': 'heal_mp', 'target': None, 'reason': f'MP低({mp:.0f}%)'}
        elif loots and loots[0].distance < 200:
            decision = {'action': 'pickup', 'target': loots[0], 'reason': f'拾取掉落物({loots[0].distance:.0f}px)'}
        elif monsters:
            decision = {'action': 'attack', 'target': monsters[0], 'reason': f'攻击{monsters[0].class_name}({monsters[0].distance:.0f}px)'}
        
        return {
            'monsters': monsters,
            'loots': loots,
            'health': health,
            'decision': decision,
            'fps': 25.0
        }
    
    def get_hp_percent(self):
        return self.health_info.hp_percent
    
    def get_mp_percent(self):
        return self.health_info.mp_percent
    
    def capture_frame(self):
        import numpy as np
        return np.zeros((1080, 1920, 3), dtype=np.uint8)


# ===========================================================================
# 主程序
# ===========================================================================

def run_with_hardware(args):
    """使用真实硬件运行"""
    print("[Agent] 初始化 Pico HID 引擎...")
    engine = HumanMotionEngine(port=args.port, baudrate=args.baudrate)
    
    if not engine.connect():
        print("[Agent] ✗ 连接 Pico 失败!")
        sys.exit(1)
    
    print(f"[Agent] ✓ 已连接 Pico @ {args.port}")
    
    # 解析区域参数
    capture_region = None
    if args.capture_region:
        capture_region = tuple(map(int, args.capture_region.split(',')))
    
    player_pos = None
    if args.player_pos:
        player_pos = tuple(map(int, args.player_pos.split(',')))
    
    hp_region = None
    if args.hp_region:
        hp_region = tuple(map(int, args.hp_region.split(',')))
    
    mp_region = None
    if args.mp_region:
        mp_region = tuple(map(int, args.mp_region.split(',')))
    
    print(f"[Agent] 初始化游戏视觉系统...")
    vision = GameVision(
        model_path=args.model,
        capture_region=capture_region,
        player_position=player_pos,
        hp_region=hp_region,
        mp_region=mp_region
    )
    
    # 战斗配置
    config = CombatConfig(
        hp_key=args.hp_key,
        mp_key=args.mp_key,
        pickup_key=args.pickup_key,
        attack_cooldown=args.attack_cooldown,
        hp_heal_threshold=args.hp_threshold,
        mp_heal_threshold=args.mp_threshold,
    )
    
    # 创建战斗 Agent
    agent = GameCombatAgent(engine, vision, config)
    
    # 信号处理
    def signal_handler(sig, frame):
        agent.stop()
        engine.disconnect()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # 启动
    agent.start()
    engine.disconnect()


def run_simulation(args):
    """使用模拟环境运行（无需硬件）"""
    print("[Agent] 模拟模式（无需硬件）\n")
    
    engine = SimulatedEngine()
    vision = SimulatedVision()
    
    config = CombatConfig(
        hp_key=args.hp_key,
        mp_key=args.mp_key,
        pickup_key=args.pickup_key,
        attack_cooldown=args.attack_cooldown,
        hp_heal_threshold=args.hp_threshold,
        mp_heal_threshold=args.mp_threshold,
    )
    
    agent = GameCombatAgent(engine, vision, config)
    
    def signal_handler(sig, frame):
        agent.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # 限制模拟运行时间
    import threading
    timer = threading.Timer(args.sim_duration, agent.stop)
    timer.daemon = True
    timer.start()
    
    agent.start()
    timer.cancel()


def main():
    parser = argparse.ArgumentParser(description='游戏自动化战斗 Agent')
    
    # 硬件参数
    parser.add_argument('--port', '-p', type=str, help='Pico 串口路径')
    parser.add_argument('--baudrate', '-b', type=int, default=115200, help='波特率')
    
    # 模型参数
    parser.add_argument('--model', '-m', type=str, default='game_yolo.pt', help='YOLO 模型路径')
    
    # 区域配置
    parser.add_argument('--capture-region', type=str, help='截图区域 (x,y,w,h)')
    parser.add_argument('--player-pos', type=str, help='玩家位置 (x,y)')
    parser.add_argument('--hp-region', type=str, help='血条区域 (x,y,w,h)')
    parser.add_argument('--mp-region', type=str, help='蓝条区域 (x,y,w,h)')
    
    # 快捷键
    parser.add_argument('--hp-key', type=str, default='1', help='补血快捷键')
    parser.add_argument('--mp-key', type=str, default='2', help='补蓝快捷键')
    parser.add_argument('--pickup-key', type=str, default='f', help='拾取快捷键')
    
    # 战斗参数
    parser.add_argument('--attack-cooldown', type=float, default=0.8, help='攻击冷却(秒)')
    parser.add_argument('--hp-threshold', type=float, default=30.0, help='补血阈值(%%)')
    parser.add_argument('--mp-threshold', type=float, default=20.0, help='补蓝阈值(%%)')
    
    # 模拟模式
    parser.add_argument('--simulate', action='store_true', help='模拟模式（无需硬件）')
    parser.add_argument('--sim-duration', type=int, default=15, help='模拟运行时间(秒)')
    
    args = parser.parse_args()
    
    # 决定运行模式
    if args.simulate or not args.port:
        run_simulation(args)
    else:
        run_with_hardware(args)


if __name__ == '__main__':
    main()
