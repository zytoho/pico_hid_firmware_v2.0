"""
示例 7: 模拟人类工作模式
=========================
演示完整的拟人工作循环：工作 → 微休息 → 工作 → 走神 → 工作

运行方式:
    python example_human_pattern.py

注意:
    - 需要 Pico 硬件连接
    - 模拟真实人类的工作节奏
    - 展示 Agent 的疲劳和注意力管理
"""

import time
import sys
from engine_v2 import HumanMotionEngine
from agent_v2 import MacroAgent


def work_task(engine, agent, task_id):
    """模拟一个工作任务"""
    print(f"  [任务 {task_id}] 执行操作...")
    
    # 移动到随机位置
    import random
    x = random.randint(300, 800)
    y = random.randint(200, 600)
    
    engine.move_to(x, y, 
                   fatigue=agent.get_profile().fatigue,
                   focus=agent.get_profile().focus)
    engine.click()
    agent.log_action()
    
    # 模拟任务耗时
    time.sleep(random.uniform(0.5, 2.0))


def main():
    print("=" * 60)
    print("示例 7: 模拟人类工作模式")
    print("=" * 60)
    
    port = '/dev/tty.usbserial-110'  # 修改为你的实际端口
    engine = HumanMotionEngine(serial_port=port)
    
    # 使用较短的疲劳时间常数以便快速看到效果
    agent = MacroAgent(
        fatigue_time_constant=2.0,  # 2分钟后达到 ~63% 疲劳
        focus_base=0.85,
        micro_break_probability=0.15,  # 15% 概率触发微休息
        micro_break_duration_range=(3.0, 8.0)
    )
    
    # 1. 初始化
    print("\n[1/4] 初始化系统...")
    if not engine.connect():
        print("❌ 连接失败")
        sys.exit(1)
    agent.start()
    print("✓ 系统初始化完成")
    print(f"  疲劳时间常数: 2.0 分钟")
    print(f"  微休息概率: 15%")
    
    # 2. 模拟工作循环
    print("\n[2/4] 开始工作循环 (运行 30 秒)...")
    
    task_id = 1
    start_time = time.time()
    duration = 30.0  # 运行 30 秒
    
    while time.time() - start_time < duration:
        # 获取当前状态
        profile = agent.get_profile()
        elapsed = time.time() - start_time
        
        # 打印状态
        print(f"\n[{elapsed:.1f}s] 状态: 疲劳={profile.fatigue:.2f}, "
              f"注意力={profile.focus:.2f}, 间隔={profile.action_interval:.2f}s")
        
        # 检查是否需要微休息
        micro_break_duration = agent.should_micro_break()
        if micro_break_duration is not None:
            print(f"  💤 微休息 {micro_break_duration:.1f}s...")
            time.sleep(micro_break_duration)
            continue
        
        # 执行任务
        work_task(engine, agent, task_id)
        task_id += 1
        
        # 根据疲劳调整间隔
        interval = profile.action_interval
        print(f"  ⏱ 等待 {interval:.2f}s...")
        time.sleep(interval)
    
    # 3. 打印统计
    print("\n" + "=" * 60)
    print("工作循环结束！")
    print("=" * 60)
    
    engine_stats = engine.get_stats()
    agent_status = agent.get_status()
    
    print("\n最终状态:")
    print(f"  疲劳度: {agent_status['profile']['fatigue']:.3f}")
    print(f"  注意力: {agent_status['profile']['focus']:.3f}")
    print(f"  操作间隔: {agent_status['profile']['action_interval']:.3f}s")
    
    print("\n工作统计:")
    print(f"  任务数: {task_id - 1}")
    print(f"  总操作次数: {agent_status['stats']['total_actions']}")
    print(f"  微休息次数: {agent_status['stats']['micro_breaks']}")
    print(f"  走神次数: {agent_status['stats']['zoned_out_count']}")
    
    print("\n引擎统计:")
    print(f"  总指令数: {engine_stats['commands_sent']}")
    print(f"  ACK 成功率: {engine_stats['ack_success_rate']*100:.1f}%")
    
    # 4. 清理
    engine.disconnect()
    agent.stop()
    print("\n✓ 完成")


if __name__ == '__main__':
    main()
