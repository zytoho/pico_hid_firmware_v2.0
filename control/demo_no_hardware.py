"""
无硬件演示 (模拟模式)
=====================
不需要 Pico 硬件即可运行的演示脚本。
通过模拟模式展示系统的工作流程和逻辑。

运行方式:
    python demo_no_hardware.py

功能:
    - 模拟鼠标移动 (打印轨迹)
    - 模拟点击操作 (打印日志)
    - 模拟打字输入 (打印文本)
    - 展示 Agent 的疲劳和注意力管理
"""

import time
import sys
from typing import Tuple

# 模拟引擎 (不依赖硬件)
class MockHumanMotionEngine:
    """模拟版引擎，用于无硬件演示"""
    
    def __init__(self):
        self._cursor_x = 0
        self._cursor_y = 0
        self._cmd_count = 0
        self._connected = False
    
    def connect(self):
        print("[Mock] 模拟连接成功")
        self._connected = True
        return True
    
    def disconnect(self):
        print("[Mock] 模拟断开连接")
        self._connected = False
    
    def move_to(self, x, y, fatigue=0.0, focus=1.0):
        print(f"[Mock] 移动鼠标: ({self._cursor_x}, {self._cursor_y}) → ({x}, {y})")
        print(f"       疲劳={fatigue:.2f}, 注意力={focus:.2f}")
        self._cursor_x = x
        self._cursor_y = y
        self._cmd_count += 1
        time.sleep(0.1)  # 模拟移动耗时
    
    def click(self, button=1):
        btn_name = {1: '左键', 2: '右键', 3: '中键'}[button]
        print(f"[Mock] 点击 ({self._cursor_x}, {self._cursor_y}) - {btn_name}")
        self._cmd_count += 1
        time.sleep(0.05)
    
    def type_string(self, text, wpm=60.0, fatigue=0.0):
        print(f"[Mock] 打字 (WPM={wpm:.0f}, 疲劳={fatigue:.2f}):")
        print(f"       \"{text}\"")
        self._cmd_count += len(text)
        time.sleep(0.2)
    
    def key_press(self, keycode, modifier=0):
        print(f"[Mock] 按键: code={keycode}, mod={modifier}")
        self._cmd_count += 1
        time.sleep(0.05)
    
    def get_stats(self):
        return {
            "connected": self._connected,
            "cursor": (self._cursor_x, self._cursor_y),
            "commands_sent": self._cmd_count,
            "ack_ok": self._cmd_count,
            "ack_fail": 0,
            "ack_success_rate": 1.0,
        }


def demo_1_simple_click():
    """演示 1: 简单的鼠标移动和点击"""
    print("\n" + "=" * 60)
    print("演示 1: 简单的鼠标移动和点击")
    print("=" * 60)
    
    engine = MockHumanMotionEngine()
    engine.connect()
    
    # 移动到屏幕中心
    engine.move_to(960, 540)
    
    # 点击
    engine.click(button=1)
    
    # 双击
    engine.click(button=1)
    time.sleep(0.1)
    engine.click(button=1)
    
    engine.disconnect()
    print("✓ 演示 1 完成")


def demo_2_typing():
    """演示 2: 文本输入"""
    print("\n" + "=" * 60)
    print("演示 2: 文本输入")
    print("=" * 60)
    
    engine = MockHumanMotionEngine()
    engine.connect()
    
    # 慢速打字
    engine.type_string("Hello, World!", wpm=30.0, fatigue=0.0)
    time.sleep(0.3)
    
    # 快速打字
    engine.type_string("This is faster!", wpm=80.0, fatigue=0.0)
    
    engine.disconnect()
    print("✓ 演示 2 完成")


def demo_3_fatigue_simulation():
    """演示 3: 疲劳模拟"""
    print("\n" + "=" * 60)
    print("演示 3: 疲劳对行为的影响")
    print("=" * 60)
    
    from agent_v2 import MacroAgent, PhysicalFatigueModel
    
    # 使用较短的疲劳时间常数以便快速看到效果
    fatigue_model = PhysicalFatigueModel(fatigue_time_constant=1.0)
    agent = MacroAgent(fatigue_model=fatigue_model)
    agent.start()
    
    engine = MockHumanMotionEngine()
    engine.connect()
    
    print("\n模拟 20 秒的工作:")
    for i in range(10):
        profile = agent.get_profile()
        print(f"\n[{i+1}/10] 疲劳={profile.fatigue:.2f}, 注意力={profile.focus:.2f}")
        
        # 移动时考虑疲劳
        engine.move_to(500 + i*50, 300, 
                      fatigue=profile.fatigue, 
                      focus=profile.focus)
        engine.click()
        agent.log_action()
        
        # 根据疲劳调整间隔
        interval = profile.action_interval
        print(f"  间隔: {interval:.2f}s")
        time.sleep(min(interval, 0.5))  # 加速演示
    
    status = agent.get_status()
    print(f"\n最终疲劳: {status['profile']['fatigue']:.3f}")
    print(f"最终注意力: {status['profile']['focus']:.3f}")
    
    engine.disconnect()
    agent.stop()
    print("✓ 演示 3 完成")


def demo_4_workflow():
    """演示 4: 完整工作流程"""
    print("\n" + "=" * 60)
    print("演示 4: 完整的表单填写工作流")
    print("=" * 60)
    
    engine = MockHumanMotionEngine()
    engine.connect()
    
    print("\n步骤 1: 点击用户名输入框")
    engine.move_to(500, 300)
    engine.click()
    time.sleep(0.2)
    
    print("\n步骤 2: 输入用户名")
    engine.type_string("zhangsan", wpm=60.0)
    time.sleep(0.2)
    
    print("\n步骤 3: Tab 到密码框")
    engine.key_press(0x2B, 0)  # TAB
    time.sleep(0.2)
    
    print("\n步骤 4: 输入密码")
    engine.type_string("password123", wpm=70.0)
    time.sleep(0.2)
    
    print("\n步骤 5: 点击登录按钮")
    engine.move_to(500, 500)
    engine.click()
    
    engine.disconnect()
    print("\n✓ 演示 4 完成")


def main():
    print("=" * 60)
    print("无硬件演示 - 模拟人类行为控制系统")
    print("=" * 60)
    print("\n这个演示不需要 Pico 硬件，")
    print("通过模拟模式展示系统的工作流程。")
    print("\n按 Enter 开始...")
    try:
        if sys.stdin.isatty():
            input()
    except EOFError:
        pass
    
    # 运行所有演示
    demo_1_simple_click()
    time.sleep(1)
    
    demo_2_typing()
    time.sleep(1)
    
    demo_3_fatigue_simulation()
    time.sleep(1)
    
    demo_4_workflow()
    
    # 总结
    print("\n" + "=" * 60)
    print("所有演示完成！")
    print("=" * 60)
    print("\n这个系统可以:")
    print("  ✓ 模拟人类的鼠标移动 (贝塞尔曲线)")
    print("  ✓ 模拟拟人化的打字 (WPM 可调)")
    print("  ✓ 管理疲劳和注意力 (物理模型)")
    print("  ✓ 微休息和走神调度")
    print("  ✓ 完整的 RPA 工作流")
    print("\n连接真实硬件后，可以:")
    print("  ✓ 视觉检测 + 自动点击")
    print("  ✓ 硬件级 HID (无法被软件检测)")
    print("  ✓ < 1ms 响应延迟")
    print("\n更多信息请查看 README.md")


if __name__ == '__main__':
    main()
