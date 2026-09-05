#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
游戏自动化战斗示例
=================
演示如何使用 game_vision 和 game_agent 模块实现自动化游戏战斗

功能:
1. 自动识别怪物 (普通怪、精英怪、BOSS)
2. 自动识别掉落物
3. 自动检测血量和蓝量
4. 智能决策: 优先攻击 BOSS > 精英 > 普通怪
5. 自动拾取掉落物
6. 自动补血补蓝

使用方法:
    python example_game_combat.py

作者: Pico HID Firmware Team
日期: 2026
"""

import time
import logging
from engine_v2 import HumanMotionEngine
from game_vision import GameVision, GameEntity, EntityType
from game_agent import GameCombatAgent, CombatConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def example_basic_combat():
    """
    基础战斗示例
    使用默认配置进行自动化战斗
    """
    print("\n" + "="*60)
    print("示例 1: 基础自动化战斗")
    print("="*60)
    
    # 配置战斗参数
    config = CombatConfig(
        player_position=(960, 540),      # 玩家位置 (屏幕中心)
        hp_threshold=30,                  # 血量低于 30% 补血
        mp_threshold=20,                  # 蓝量低于 20% 补蓝
        pickup_range=200,                 # 掉落物拾取范围 (像素)
        attack_range=150,                 # 攻击范围 (像素)
        hp_key='1',                       # 补血快捷键
        mp_key='2',                       # 补蓝快捷键
        pickup_key='f',                   # 拾取快捷键
        attack_cooldown=0.8,              # 攻击冷却时间 (秒)
        use_mouse_attack=True,            # 使用鼠标左键攻击
        attack_key=None                   # 技能快捷键 (None 表示鼠标攻击)
    )
    
    # 初始化引擎
    engine = HumanMotionEngine('/dev/ttyUSB0', baudrate=115200)
    
    # 初始化视觉模块
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(0, 0, 1920, 1080)  # 全屏截图
    )
    
    # 初始化战斗 Agent
    agent = GameCombatAgent(
        engine=engine,
        vision=vision,
        config=config
    )
    
    try:
        print("\n开始自动化战斗...")
        print("按 Ctrl+C 停止\n")
        
        # 启动战斗循环
        agent.run()
        
    except KeyboardInterrupt:
        print("\n\n用户中断，停止战斗")
    
    finally:
        # 停止 Agent
        agent.stop()
        
        # 打印战斗统计
        print("\n" + "="*60)
        print("战斗统计:")
        print(f"总攻击次数: {agent.stats['total_attacks']}")
        print(f"成功攻击: {agent.stats['successful_attacks']}")
        print(f"攻击失败: {agent.stats['failed_attacks']}")
        print(f"拾取次数: {agent.stats['pickups']}")
        print(f"补血次数: {agent.stats['hp_potions_used']}")
        print(f"补蓝次数: {agent.stats['mp_potions_used']}")
        print("="*60)


def example_skill_rotation():
    """
    技能循环示例
    使用技能循环而不是鼠标攻击
    """
    print("\n" + "="*60)
    print("示例 2: 技能循环战斗")
    print("="*60)
    
    # 配置技能循环
    config = CombatConfig(
        player_position=(960, 540),
        hp_threshold=40,
        mp_threshold=30,
        pickup_range=250,
        attack_range=200,
        hp_key='1',
        mp_key='2',
        pickup_key='f',
        attack_cooldown=1.0,
        use_mouse_attack=False,         # 不使用鼠标攻击
        attack_key=None,
        skill_keys=['3', '4', '5', '6'] # 技能循环: 3 -> 4 -> 5 -> 6
    )
    
    engine = HumanMotionEngine('/dev/ttyUSB0', baudrate=115200)
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(0, 0, 1920, 1080)
    )
    
    agent = GameCombatAgent(
        engine=engine,
        vision=vision,
        config=config
    )
    
    try:
        print("\n开始技能循环战斗...")
        print("技能顺序: 3 -> 4 -> 5 -> 6")
        print("按 Ctrl+C 停止\n")
        
        agent.run()
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    
    finally:
        agent.stop()


def example_priority_filter():
    """
    优先级过滤示例
    只攻击特定类型的怪物
    """
    print("\n" + "="*60)
    print("示例 3: 优先级过滤 (只攻击精英怪和 BOSS)")
    print("="*60)
    
    config = CombatConfig(
        player_position=(960, 540),
        hp_threshold=30,
        mp_threshold=20,
        pickup_range=200,
        attack_range=150,
        hp_key='1',
        mp_key='2',
        pickup_key='f',
        attack_cooldown=0.8,
        # 只攻击精英怪和 BOSS，忽略普通怪
        priority_filter=['elite_monster', 'boss']
    )
    
    engine = HumanMotionEngine('/dev/ttyUSB0', baudrate=115200)
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(0, 0, 1920, 1080)
    )
    
    agent = GameCombatAgent(
        engine=engine,
        vision=vision,
        config=config
    )
    
    try:
        print("\n开始优先战斗...")
        print("只攻击精英怪和 BOSS")
        print("按 Ctrl+C 停止\n")
        
        agent.run()
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    
    finally:
        agent.stop()


def example_custom_region():
    """
    自定义截图区域示例
    只对游戏窗口进行截图和检测
    """
    print("\n" + "="*60)
    print("示例 4: 自定义截图区域")
    print("="*60)
    
    config = CombatConfig(
        player_position=(640, 360),  # 相对于游戏窗口的位置
        hp_threshold=30,
        mp_threshold=20,
        pickup_range=200,
        attack_range=150,
        hp_key='1',
        mp_key='2',
        pickup_key='f',
        attack_cooldown=0.8
    )
    
    engine = HumanMotionEngine('/dev/ttyUSB0', baudrate=115200)
    
    # 只对游戏窗口截图 (左上角 1280x720 区域)
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(100, 100, 1280, 720)  # x, y, width, height
    )
    
    agent = GameCombatAgent(
        engine=engine,
        vision=vision,
        config=config
    )
    
    try:
        print("\n开始窗口内战斗...")
        print("截图区域: 100,100 到 1380,820")
        print("按 Ctrl+C 停止\n")
        
        agent.run()
        
    except KeyboardInterrupt:
        print("\n\n用户中断")
    
    finally:
        agent.stop()


def example_vision_only():
    """
    纯视觉检测示例 (不执行操作)
    仅用于测试视觉模块是否正确识别目标
    """
    print("\n" + "="*60)
    print("示例 5: 纯视觉检测 (只观察不操作)")
    print("="*60)
    
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(0, 0, 1920, 1080)
    )
    
    try:
        print("\n开始视觉检测...")
        print("按 Ctrl+C 停止\n")
        
        while True:
            # 截图并检测
            frame = vision.capture_screen()
            entities = vision.detect_entities(frame)
            health = vision.detect_health(frame)
            
            # 打印检测结果
            print("\n" + "-"*60)
            print(f"检测到 {len(entities)} 个实体:")
            
            for entity in entities:
                print(f"  - {entity.monster_type.value}: "
                      f"置信度 {entity.confidence:.2f}, "
                      f"距离 {entity.distance:.1f}像素")
            
            if health:
                print(f"\n状态:")
                print(f"  血量: {health.hp_percent:.1f}%")
                print(f"  蓝量: {health.mp_percent:.1f}%")
            
            print("-"*60)
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n用户中断")


def example_loot_only():
    """
    只拾取示例
    只拾取掉落物，不攻击怪物
    """
    print("\n" + "="*60)
    print("示例 6: 只拾取掉落物")
    print("="*60)
    
    config = CombatConfig(
        player_position=(960, 540),
        hp_threshold=30,
        mp_threshold=20,
        pickup_range=500,    # 扩大拾取范围
        attack_range=150,
        hp_key='1',
        mp_key='2',
        pickup_key='f',
        attack_cooldown=0.8
    )
    
    engine = HumanMotionEngine('/dev/ttyUSB0', baudrate=115200)
    vision = GameVision(
        model_path='game_yolo.pt',
        confidence_threshold=0.5,
        screen_region=(0, 0, 1920, 1080)
    )
    
    agent = GameCombatAgent(
        engine=engine,
        vision=vision,
        config=config
    )
    
    try:
        print("\n开始拾取模式...")
        print("只拾取掉落物，不攻击怪物")
        print("按 Ctrl+C 停止\n")
        
        # 手动循环，只拾取
        while agent.running:
            frame = vision.capture_screen()
            loots = vision.detect_loots(frame)
            
            if loots:
                # 找到最近的掉落物
                nearest = min(loots, key=lambda e: e.distance)
                
                if nearest.distance < config.pickup_range:
                    print(f"\n发现掉落物，距离 {nearest.distance:.1f}像素")
                    print(f"移动到: {nearest.position}")
                    
                    # 移动到掉落物
                    engine.move_to(nearest.position[0], nearest.position[1])
                    time.sleep(0.3)
                    
                    # 按拾取键
                    print("拾取...")
                    engine.press_key(config.pickup_key)
                    
                    agent.stats['pickups'] += 1
            
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\n\n用户中断")
    
    finally:
        print(f"\n拾取统计: {agent.stats['pickups']} 次")


def main():
    """
    主函数 - 选择要运行的示例
    """
    print("\n" + "="*60)
    print("游戏自动化战斗示例")
    print("="*60)
    print("\n可用示例:")
    print("1. 基础自动化战斗")
    print("2. 技能循环战斗")
    print("3. 优先级过滤 (只攻击精英怪和 BOSS)")
    print("4. 自定义截图区域")
    print("5. 纯视觉检测 (只观察不操作)")
    print("6. 只拾取掉落物")
    print("7. 运行所有示例 (演示模式)")
    print("0. 退出")
    
    try:
        choice = input("\n请选择示例 (0-7): ").strip()
        
        if choice == '1':
            example_basic_combat()
        elif choice == '2':
            example_skill_rotation()
        elif choice == '3':
            example_priority_filter()
        elif choice == '4':
            example_custom_region()
        elif choice == '5':
            example_vision_only()
        elif choice == '6':
            example_loot_only()
        elif choice == '7':
            print("\n演示模式: 依次运行所有示例\n")
            example_vision_only()
            time.sleep(2)
            example_basic_combat()
        elif choice == '0':
            print("\n退出")
        else:
            print("\n无效选择")
            
    except KeyboardInterrupt:
        print("\n\n用户中断")
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
