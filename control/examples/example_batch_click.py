"""
示例 6: 批量点击任务
====================
演示如何连续点击多个目标，并处理异常。

运行方式:
    python example_batch_click.py

注意:
    - 需要 Pico 硬件连接
    - 假设有一组需要点击的目标 (如按钮、复选框等)
    - 演示了错误处理和重试逻辑
"""

import time
import sys
from engine_v2 import HumanMotionEngine
from agent_v2 import MacroAgent


def click_target(engine, agent, x, y, name, retry=3):
    """
    点击指定位置的辅助函数
    
    Args:
        engine: 引擎实例
        agent: Agent 实例
        x, y: 目标坐标
        name: 目标名称 (用于日志)
        retry: 重试次数
    
    Returns:
        是否成功
    """
    for attempt in range(retry):
        try:
            # 移动到目标
            engine.move_to(x, y)
            
            # 点击
            engine.click()
            agent.log_action()
            
            # 验证 (这里简化，实际可能需要视觉验证)
            time.sleep(0.3)
            
            return True
            
        except Exception as e:
            print(f"  ⚠ 尝试 {attempt+1} 失败: {e}")
            agent.log_failure(f"{name} - {e}")
            time.sleep(1)
    
    return False


def main():
    print("=" * 60)
    print("示例 6: 批量点击任务")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    agent = MacroAgent()
    
    # 1. 初始化
    print("\n[1/3] 初始化系统...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    agent.start()
    print("✓ 系统初始化完成")
    
    # 2. 定义要点击的目标列表
    targets = [
        {"name": "按钮 1", "x": 200, "y": 300},
        {"name": "按钮 2", "x": 400, "y": 300},
        {"name": "按钮 3", "x": 600, "y": 300},
        {"name": "复选框 1", "x": 200, "y": 500},
        {"name": "复选框 2", "x": 400, "y": 500},
        {"name": "提交按钮", "x": 400, "y": 700},
    ]
    
    print(f"\n[2/3] 准备点击 {len(targets)} 个目标...")
    
    # 3. 批量点击
    success_count = 0
    failure_count = 0
    
    for i, target in enumerate(targets, 1):
        print(f"\n  ({i}/{len(targets)}) 点击: {target['name']} ({target['x']}, {target['y']})")
        
        if click_target(engine, agent, target['x'], target['y'], target['name']):
            print(f"    ✓ 成功")
            success_count += 1
        else:
            print(f"    ✗ 失败")
            failure_count += 1
        
        # 根据 Agent 状态决定间隔
        profile = agent.get_profile()
        interval = profile.action_interval * (1.0 + profile.fatigue * 0.5)
        print(f"    间隔: {interval:.2f}s (疲劳: {profile.fatigue:.2f})")
        time.sleep(interval)
    
    # 4. 统计
    print("\n" + "=" * 60)
    print("批量点击完成！")
    print("=" * 60)
    
    print(f"\n结果:")
    print(f"  成功: {success_count}/{len(targets)}")
    print(f"  失败: {failure_count}/{len(targets)}")
    print(f"  成功率: {success_count/len(targets)*100:.1f}%")
    
    engine_stats = engine.get_stats()
    agent_status = agent.get_status()
    
    print("\n引擎统计:")
    print(f"  总指令数: {engine_stats['commands_sent']}")
    print(f"  ACK 成功率: {engine_stats['ack_success_rate']*100:.1f}%")
    
    print("\nAgent 统计:")
    print(f"  当前疲劳度: {agent_status['profile']['fatigue']:.3f}")
    print(f"  操作次数: {agent_status['stats']['total_actions']}")
    print(f"  失败次数: {agent_status['stats']['total_failures']}")
    
    # 5. 清理
    engine.disconnect()
    agent.stop()
    print("\n✓ 任务完成")


if __name__ == '__main__':
    main()
